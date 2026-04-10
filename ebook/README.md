# 財經逐字稿每日重點

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
