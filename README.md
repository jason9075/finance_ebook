# finance_ebook

把每日財經內容整理成可閱讀的 Markdown 筆記，並輸出成 mdBook。

## 需求

- Python 3.11 以上
- `codex` 或 `gemini` CLI 其一
- 若要本機預覽電子書，另外安裝 `mdbook`
- 可選：`just`，方便用簡短指令執行常用流程

## 安裝

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

如果你用 `uv`、`poetry` 或 `nix` 管理環境，也可以，只要最後能執行 `python -m finance_ebook` 即可。

## 來源格式

預設會讀取 [transcripts](/home/jason9075/data/finance_ebook/transcripts) 內的 `*.txt` 檔。實際內容必須是 JSON array，每個元素至少包含：

```json
[
  {
    "date": "2026-04-11",
    "title": "標題",
    "text": "全文"
  }
]
```

欄位說明：

- `date`：每天筆記的日期，會用來命名輸出檔 `note_YYYY-MM-DD.md`
- `title`：原始標題
- `text`：全文

## 快速開始

最基本的跑法：

```bash
PYTHONPATH=src python -m finance_ebook --limit 5
```

若你已經 `pip install -e .`，也可以直接用：

```bash
finance-ebook --limit 5
```

常用例子：

```bash
BACKEND=codex PYTHONPATH=src python -m finance_ebook --limit 5
BACKEND=gemini PYTHONPATH=src python -m finance_ebook --limit 5
PYTHONPATH=src python -m finance_ebook --limit 10 --workers 8
PYTHONPATH=src python -m finance_ebook --limit 3 --force
PYTHONPATH=src python -m finance_ebook --refresh-summary
```

## 用 `just` 執行

[Justfile](/home/jason9075/data/finance_ebook/Justfile) 已包好幾個常用指令：

```bash
just generate 5
just generate 5 gpt-5.4 8
just generate 5 gemini-3.1-pro-preview 8
just regenerate 5
just refresh-summary
just serve
just build
```

## 參數說明

`python -m finance_ebook` 支援這些常用參數：

- `--limit N`：只處理前 `N` 筆逐日資料
- `--force`：即使筆記已存在也重新生成
- `--model MODEL_NAME`：指定模型
- `--backend codex|gemini`：指定後端
- `--workers N`：平行處理數
- `--refresh-summary`：只重建 `ebook/README.md` 與 `ebook/SUMMARY.md`

## 環境變數

程式啟動時會自動載入根目錄 [`.env`](/home/jason9075/data/finance_ebook/.env)。

可用的環境變數：

- `BACKEND`：預設後端，預設值為 `codex`
- `MODEL`：預設模型名稱
- `GEMINI_MODEL`：未指定 `MODEL` 時，作為備援模型設定
- `WORKERS`：預設平行數
- `GEMINI_WORKERS`：未指定 `WORKERS` 時的備援平行數
- `TRANSCRIPTS_DIR`：覆寫資料資料夾位置
- `EBOOK_DIR`：覆寫輸出資料夾位置

最小 `.env` 範例：

```env
BACKEND=codex
```

## 輸出位置

生成後的內容預設寫到 [ebook](/home/jason9075/data/finance_ebook/ebook)：

- `ebook/note_YYYY-MM-DD.md`：單日筆記
- `ebook/README.md`：首頁
- `ebook/SUMMARY.md`：mdBook 目錄

執行過程中的錯誤與 rate limit 紀錄會寫到 [logs](/home/jason9075/data/finance_ebook/logs)。

## 預覽與建置

本機預覽：

```bash
mdbook serve
```

輸出靜態站：

```bash
mdbook build
```

## Prompt 規格

資料整理的完整章節規格只有一份來源，放在 [prompts/extract.md](/home/jason9075/data/finance_ebook/prompts/extract.md)。

如果你要調整：

- `多空分析`
- `總經學習點`
- 標題格式
- 條列數量
- 各章節順序

只需要修改 [prompts/extract.md](/home/jason9075/data/finance_ebook/prompts/extract.md)，不需要再改 [AGENTS.md](/home/jason9075/data/finance_ebook/AGENTS.md) 或 [system.md](/home/jason9075/data/finance_ebook/.gemini/system.md)。
