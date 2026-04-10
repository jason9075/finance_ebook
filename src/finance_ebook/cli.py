from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    from tqdm import tqdm
except ModuleNotFoundError:
    tqdm = None

DEFAULT_MODEL = "gemini-3.1-pro-preview"


README_TEMPLATE = """# 財經逐字稿每日重點

這本 mdBook 由 `python -m finance_ebook` 自動產生。

## 使用方式

```bash
PYTHONPATH=src python -m finance_ebook --limit 5
mdbook serve
```

## 說明

- 每篇 `note_YYYYMMDD.md` 對應一天的逐字稿重點。
- `SUMMARY.md` 會依日期自動更新。
- 預設會跳過已存在的筆記；若要重跑已產生的檔案，加入 `--force`。
- 預設 model 為 `gemini-3.1-pro-preview`；可用 `--model` 或 `GEMINI_MODEL` 覆寫。
"""


@dataclass(slots=True)
class Config:
    root_dir: Path
    transcripts_dir: Path
    ebook_dir: Path
    model: str
    limit: int | None
    force: bool


@dataclass(slots=True)
class DailyTranscript:
    date: str
    title: str
    text: str


def build_parser() -> argparse.ArgumentParser:
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
        default=os.environ.get("GEMINI_MODEL", DEFAULT_MODEL),
        help=f"Gemini model name. Defaults to GEMINI_MODEL or {DEFAULT_MODEL}.",
    )
    return parser


def non_negative_int(raw: str) -> int:
    value = int(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return value


def resolve_config(args: argparse.Namespace) -> Config:
    root_dir = Path(__file__).resolve().parents[2]
    return Config(
        root_dir=root_dir,
        transcripts_dir=Path(os.environ.get("TRANSCRIPTS_DIR", root_dir / "transcripts")),
        ebook_dir=Path(os.environ.get("EBOOK_DIR", root_dir / "ebook")),
        model=args.model.strip(),
        limit=args.limit,
        force=args.force,
    )


def ensure_requirements(config: Config) -> None:
    if shutil.which("gemini") is None:
        raise SystemExit("Missing required command: gemini")
    if not config.transcripts_dir.is_dir():
        raise SystemExit(f"Transcript directory not found: {config.transcripts_dir}")


def init_ebook(config: Config) -> None:
    config.ebook_dir.mkdir(parents=True, exist_ok=True)
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
    return sorted(config.transcripts_dir.glob("*.txt"))


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


def build_prompt(date: str, title: str) -> str:
    return f"""請你把以下財經節目逐字稿整理成可直接存成 markdown 的每日筆記。

要求：
1. 使用繁體中文（台灣用語）。
2. 第一行標題固定為：# {date} 財經重點整理
3. 第二段使用 `> ` blockquote 寫一段 120-180 字的「今日總覽」，先交代大盤主軸、風險焦點與最重要的市場變化。
4. 接著輸出 `## 核心關鍵字`，列出 3-5 個最重要主題，每點只寫關鍵詞或短語。
5. 接著輸出 `## 重點整理`，列出 4-6 點；每點使用 `### ` 小標，並用 2-4 句說明具體事實、因果與講者觀點。
6. 若逐字稿內有明確數字、資產價格、經濟數據或產業指標，再輸出 `## 市場數據與動態`，以條列方式整理；若沒有明確數據，可省略此節。
7. 最後一定要輸出 `## 市場觀察` 與 `## 後續關注` 兩節，各用 2-4 個條列說明。
8. 請優先保留對投資判斷有用的內容，並清楚區分已發生的事實與講者的推論或預測。
9. 請移除講者名稱、主持人口吻、對話輪次與人物標記，改寫成不帶講者識別的書面整理；只有在人物身分本身構成分析重點時才保留。
10. 如果逐字稿內容雜訊很多，請主動去蕪存菁，不要逐字重寫。
11. 只輸出 markdown，不要加前言、不要解釋你怎麼做的。

資料日期：{date}
資料標題：{title}

以下是逐字稿全文：
"""


def generate_note(entry: DailyTranscript, note_path: Path, model: str) -> bool:
    prompt = f"{build_prompt(entry.date, entry.title)}\n\n{entry.text}"
    completed = subprocess.run(
        ["gemini", "-m", model, "-p", prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if completed.returncode != 0:
        if note_path.exists():
            note_path.unlink()
        return False

    note_path.write_text(completed.stdout, encoding="utf-8")
    return True


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
    return sorted(config.ebook_dir.glob("note_*.md"))


def build_summary(config: Config) -> None:
    lines = ["# Summary", "", "- [首頁](./README.md)"]
    for note_file in note_files(config):
        note_date = note_file.stem.removeprefix("note_")
        lines.append(f"- [{note_date}](./{note_file.name})")
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
        "PYTHONPATH=src python -m finance_ebook --limit 5",
        "just generate 5",
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
            note_date = note_file.stem.removeprefix("note_")
            lines.append(f"- [{note_date}](./{note_file.name})")
    (config.ebook_dir / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config: Config) -> int:
    ensure_requirements(config)
    init_ebook(config)

    queued, skipped = collect_entries(config)
    attempted = 0

    if not queued:
        build_summary(config)
        build_homepage(config)
        print(f"done  attempted=0 skipped={skipped} ebook={config.ebook_dir}")
        return 0

    if tqdm is None:
        for entry, note_path in queued:
            print(f"write {entry.date}")
            attempted += 1
            if not generate_note(entry, note_path, config.model):
                print(f"error {entry.date}")
    else:
        progress = tqdm(queued, desc="Generating notes", unit="note")
        for entry, note_path in progress:
            progress.set_postfix_str(entry.date)
            attempted += 1
            if not generate_note(entry, note_path, config.model):
                tqdm.write(f"error {entry.date}")

    build_summary(config)
    build_homepage(config)
    print(f"done  attempted={attempted} skipped={skipped} ebook={config.ebook_dir}")
    return 0


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = resolve_config(args)
    return run(config)


if __name__ == "__main__":
    raise SystemExit(main())
