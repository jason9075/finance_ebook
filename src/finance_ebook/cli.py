from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from threading import Lock

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    tqdm = None

DEFAULT_BACKEND = "codex"
DEFAULT_MODEL_BY_BACKEND = {
    "gemini": "gemini-3.1-pro-preview",
    "codex": "gpt-5.4",
}
DEFAULT_WORKERS = 4
EXTRACT_PROMPT_PATH = Path("prompts/extract.md")
REQUIRED_PROMPT_MARKERS = (
    "## 多空分析",
    "## 總經學習點",
)


README_TEMPLATE = """# 財經逐字稿每日重點

這本 mdBook 由 `python -m finance_ebook` 自動產生。

## 使用方式

```bash
BACKEND=codex PYTHONPATH=src python -m finance_ebook --limit 5
BACKEND=gemini PYTHONPATH=src python -m finance_ebook --limit 5
just generate 5
just generate 5 gpt-5.4 8
just generate 5 gemini-3.1-pro-preview 8
mdbook serve
```

## 說明

- 每篇 `note_YYYYMMDD.md` 對應一天的逐字稿重點。
- `SUMMARY.md` 會依日期自動更新。
- 預設會跳過已存在的筆記；若要重跑已產生的檔案，加入 `--force`。
- 預設 backend 為 `codex`，可用 `BACKEND` 切換為 `gemini`。
- `codex` 預設 model 為 `gpt-5.4`，`gemini` 預設 model 為 `gemini-3.1-pro-preview`。
- 根目錄 `.env` 會在啟動時自動載入。
- 預設使用 `4` 個平行 worker；可用 `--workers` 或 `GEMINI_WORKERS` 覆寫。
"""


@dataclass(slots=True)
class Config:
    root_dir: Path
    transcripts_dir: Path
    ebook_dir: Path
    logs_dir: Path
    backend: str
    model: str
    workers: int
    limit: int | None
    force: bool
    refresh_summary: bool


@dataclass(slots=True)
class DailyTranscript:
    date: str
    title: str
    text: str


class GenerationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"


def load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def default_model_for_backend(backend: str) -> str:
    return DEFAULT_MODEL_BY_BACKEND.get(backend, DEFAULT_MODEL_BY_BACKEND[DEFAULT_BACKEND])


def build_parser() -> argparse.ArgumentParser:
    env_backend = os.environ.get("BACKEND", DEFAULT_BACKEND).strip().lower() or DEFAULT_BACKEND
    parser = argparse.ArgumentParser(
        prog="finance_ebook",
        description="Generate daily mdBook notes from transcript JSON files.",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=non_negative_int,
        default=None,
        help="Only process the first N daily transcripts.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Regenerate notes even if the target file already exists.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=os.environ.get("MODEL", os.environ.get("GEMINI_MODEL", default_model_for_backend(env_backend))),
        help="Model name. Defaults to MODEL, then backend-specific defaults.",
    )
    parser.add_argument(
        "-b",
        "--backend",
        choices=["gemini", "codex"],
        default=env_backend,
        help=f"LLM backend. Defaults to BACKEND or {DEFAULT_BACKEND}.",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=positive_int,
        default=int(os.environ.get("WORKERS", os.environ.get("GEMINI_WORKERS", str(DEFAULT_WORKERS)))),
        help=f"Parallel worker count. Defaults to WORKERS or {DEFAULT_WORKERS}.",
    )
    parser.add_argument(
        "--refresh-summary",
        action="store_true",
        help="Only rebuild README.md and SUMMARY.md from existing notes.",
    )
    return parser


def non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return value


def positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def resolve_config(args: argparse.Namespace) -> Config:
    root_dir = Path(__file__).resolve().parents[2]
    return Config(
        root_dir=root_dir,
        transcripts_dir=Path(os.environ.get("TRANSCRIPTS_DIR", root_dir / "transcripts")),
        ebook_dir=Path(os.environ.get("EBOOK_DIR", root_dir / "ebook")),
        logs_dir=root_dir / "logs",
        backend=args.backend.strip(),
        model=args.model.strip(),
        workers=args.workers,
        limit=args.limit,
        force=args.force,
        refresh_summary=args.refresh_summary,
    )


def load_extract_prompt_template(root_dir: Path) -> str:
    prompt_path = root_dir / EXTRACT_PROMPT_PATH
    if not prompt_path.exists():
        raise SystemExit(f"Prompt template not found: {prompt_path}")
    template = prompt_path.read_text(encoding="utf-8").rstrip() + "\n"
    missing_markers = [marker for marker in REQUIRED_PROMPT_MARKERS if marker not in template]
    if missing_markers:
        missing_text = ", ".join(missing_markers)
        raise SystemExit(f"Prompt template missing required markers: {missing_text}")
    return template


def ensure_requirements(config: Config) -> None:
    command = config.backend
    if shutil.which(command) is None:
        raise SystemExit(f"Missing required command: {command}")
    if not config.transcripts_dir.is_dir():
        raise SystemExit(f"Transcript directory not found: {config.transcripts_dir}")


def init_ebook(config: Config) -> None:
    config.ebook_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)
    book_toml = config.root_dir / "book.toml"
    if not book_toml.exists():
        book_toml.write_text(
            "[book]\n"
            'title = "Finance Daily Notes"\n'
            'authors = ["Codex"]\n'
            'language = "zh-TW"\n'
            'src = "ebook"\n',
            encoding="utf-8",
        )

    readme_path = config.ebook_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(README_TEMPLATE, encoding="utf-8")

    summary_path = config.ebook_dir / "SUMMARY.md"
    if not summary_path.exists():
        summary_path.write_text("# Summary\n\n- [首頁](./README.md)\n", encoding="utf-8")


def iter_transcript_files(config: Config) -> list[Path]:
    return sorted(config.transcripts_dir.glob("*.txt"), reverse=True)


def iter_daily_transcripts(transcript_file: Path) -> list[DailyTranscript]:
    payload = json.loads(transcript_file.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Transcript file must contain a JSON array: {transcript_file}")

    items: list[DailyTranscript] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"Transcript entry must be an object: {transcript_file}")
        date = str(item.get("date", "")).strip()
        if not date:
            raise ValueError(f"Transcript entry missing date: {transcript_file}")
        items.append(
            DailyTranscript(
                date=date,
                title=str(item.get("title") or "Untitled"),
                text=str(item.get("text") or ""),
            )
        )
    return items


def build_prompt(prompt_template: str, date: str, title: str) -> str:
    return prompt_template.format(date=date, title=title)


def make_log_file(config: Config) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return config.logs_dir / f"generate-{timestamp}.log"


def append_log(log_file: Path, message: str, log_lock: Lock) -> None:
    with log_lock:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip())
            handle.write("\n\n")


def is_rate_limited(stderr: str, stdout: str) -> bool:
    haystack = f"{stderr}\n{stdout}".lower()
    patterns = [
        "rate limit",
        "rate_limit",
        "too many requests",
        "resource has been exhausted",
        "quota exceeded",
        "429",
    ]
    return any(pattern in haystack for pattern in patterns)


def build_backend_command(backend: str, model: str, prompt: str) -> list[str]:
    if backend == "codex":
        return ["codex", "-m", model, "exec", prompt]
    return ["gemini", "-m", model, "-p", prompt]


def generate_note(
    entry: DailyTranscript,
    note_path: Path,
    backend: str,
    model: str,
    prompt_template: str,
    log_file: Path,
    log_lock: Lock,
) -> GenerationStatus:
    prompt = f"{build_prompt(prompt_template, entry.date, entry.title)}\n\n{entry.text}"
    command = build_backend_command(backend, model, prompt)
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        if note_path.exists():
            note_path.unlink()
        status = (
            GenerationStatus.RATE_LIMITED
            if is_rate_limited(completed.stderr, completed.stdout)
            else GenerationStatus.FAILED
        )
        append_log(
            log_file,
            "\n".join(
                [
                    f"[{entry.date}] {backend} command {status.value}",
                    f"backend: {backend}",
                    f"model: {model}",
                    f"command: {' '.join(command[:4])}",
                    f"note: {note_path}",
                    f"returncode: {completed.returncode}",
                    "",
                    "stderr:",
                    completed.stderr.strip() or "(empty)",
                    "",
                    "stdout:",
                    completed.stdout.strip() or "(empty)",
                ]
            ),
            log_lock,
        )
        return status

    note_path.write_text(completed.stdout, encoding="utf-8")
    return GenerationStatus.SUCCESS


def process_entry(
    entry: DailyTranscript,
    note_path: Path,
    config: Config,
    prompt_template: str,
    log_file: Path,
    log_lock: Lock,
) -> tuple[str, GenerationStatus]:
    try:
        status = generate_note(entry, note_path, config.backend, config.model, prompt_template, log_file, log_lock)
        return entry.date, status
    except Exception:
        append_log(
            log_file,
            "\n".join(
                [
                    f"[{entry.date}] unexpected exception",
                    f"note: {note_path}",
                    "",
                    traceback.format_exc().rstrip(),
                ]
            ),
            log_lock,
        )
        return entry.date, GenerationStatus.FAILED


def collect_entries(config: Config) -> tuple[list[tuple[DailyTranscript, Path]], int]:
    items: list[tuple[DailyTranscript, Path]] = []
    skipped_existing = 0
    for transcript_file in iter_transcript_files(config):
        for entry in iter_daily_transcripts(transcript_file):
            note_path = config.ebook_dir / f"note_{entry.date}.md"
            if note_path.exists() and not config.force:
                skipped_existing += 1
                continue
            items.append((entry, note_path))
            if config.limit is not None and len(items) >= config.limit:
                return items, skipped_existing
    return items, skipped_existing


def note_files(config: Config) -> list[Path]:
    return sorted(config.ebook_dir.glob("note_*.md"), reverse=True)


def note_link_label(note_file: Path) -> str:
    fallback = note_file.stem.removeprefix("note_")
    try:
        with note_file.open(encoding="utf-8") as handle:
            first_line = handle.readline().strip()
    except OSError:
        return fallback

    if not first_line.startswith("# "):
        return fallback

    heading = first_line[2:].strip()
    return heading or fallback


def build_summary(config: Config) -> None:
    lines = ["# Summary", "", "- [首頁](./README.md)"]
    for note_file in note_files(config):
        lines.append(f"- [{note_link_label(note_file)}](./{note_file.name})")
    (config.ebook_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_homepage(config: Config) -> None:
    notes = note_files(config)
    lines = [
        "# 財經逐字稿每日重點",
        "",
        "這本 mdBook 由 `python -m finance_ebook` 自動整理每日逐字稿，並彙整成重點摘要。",
        "",
        f"目前已產生 `{len(notes)}` 篇每日筆記。",
        "",
        "## 使用方式",
        "",
        "```bash",
        "BACKEND=codex PYTHONPATH=src python -m finance_ebook --limit 5",
        "BACKEND=gemini PYTHONPATH=src python -m finance_ebook --limit 5",
        "just generate 5",
        "just generate 5 gpt-5.4 8",
        "just generate 5 gemini-3.1-pro-preview 8",
        "mdbook serve",
        "```",
        "",
        "## 筆記列表",
        "",
    ]
    if not notes:
        lines.append("目前尚未產生任何每日筆記。")
    else:
        for note_file in notes:
            lines.append(f"- [{note_link_label(note_file)}](./{note_file.name})")
    (config.ebook_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config: Config) -> int:
    init_ebook(config)

    if config.refresh_summary:
        build_summary(config)
        build_homepage(config)
        print(f"done  refreshed=1 ebook={config.ebook_dir}")
        return 0

    ensure_requirements(config)
    prompt_template = load_extract_prompt_template(config.root_dir)

    log_file = make_log_file(config)
    log_lock = Lock()
    queued, skipped = collect_entries(config)
    attempted = 0
    errors = 0
    rate_limited = False

    if not queued:
        build_summary(config)
        build_homepage(config)
        print(f"done  attempted=0 skipped={skipped} ebook={config.ebook_dir}")
        return 0

    progress = tqdm(total=len(queued), desc="Generating notes", unit="note") if tqdm else None
    max_workers = min(config.workers, len(queued))

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        queue_iter = iter(queued)
        in_flight = {}

        for _ in range(max_workers):
            try:
                entry, note_path = next(queue_iter)
            except StopIteration:
                break
            future = executor.submit(process_entry, entry, note_path, config, prompt_template, log_file, log_lock)
            in_flight[future] = entry.date

        while in_flight:
            done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED)
            for future in done:
                date = in_flight.pop(future)
                completed_date, status = future.result()
                attempted += 1
                if progress is None:
                    print(f"write {completed_date}")
                else:
                    progress.set_postfix_str(date)
                    progress.update(1)

                if status != GenerationStatus.SUCCESS:
                    errors += 1
                    if progress is None:
                        print(f"error {completed_date} log={log_file}")
                    else:
                        tqdm.write(f"error {completed_date} log={log_file}")

                if status == GenerationStatus.RATE_LIMITED:
                    rate_limited = True
                    if progress is None:
                        print("rate limit detected, stopping new submissions")
                    else:
                        tqdm.write("rate limit detected, stopping new submissions")

                if rate_limited:
                    continue

                try:
                    next_entry, next_note_path = next(queue_iter)
                except StopIteration:
                    continue
                next_future = executor.submit(
                    process_entry,
                    next_entry,
                    next_note_path,
                    config,
                    prompt_template,
                    log_file,
                    log_lock,
                )
                in_flight[next_future] = next_entry.date

    if progress is not None:
        progress.close()

    build_summary(config)
    build_homepage(config)
    if errors == 0 and log_file.exists():
        log_file.unlink()
    elif rate_limited:
        append_log(log_file, "[run] stopped early due to rate limit", log_lock)
    print(
        f"done  attempted={attempted} skipped={skipped} errors={errors} rate_limited={int(rate_limited)} ebook={config.ebook_dir}"
    )
    return 0


def main() -> int:
    root_dir = Path(__file__).resolve().parents[2]
    load_dotenv(root_dir / ".env")
    parser = build_parser()
    args = parser.parse_args()
    config = resolve_config(args)
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
