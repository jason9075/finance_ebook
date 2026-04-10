# 財經逐字稿每日重點

這本 mdBook 由 `scripts/generate_daily_notes.sh` 自動產生。

## 使用方式

```bash
scripts/generate_daily_notes.sh --limit 5
mdbook serve
```

## 說明

- 每篇 `note_YYYYMMDD.md` 對應一天的逐字稿重點。
- `SUMMARY.md` 會依日期自動更新。
- 若要重跑已產生的檔案，加入 `--force`。
