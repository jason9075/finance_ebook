set shell := ["bash", "-euo", "pipefail", "-c"]

default:
  just --list

generate limit="" model="gemini-3.1-pro-preview":
  PYTHON_BIN="$(command -v python3 || command -v python || true)"; \
  if [[ -z "$PYTHON_BIN" ]]; then \
    echo "Missing required command: python3 (or python)" >&2; \
    exit 1; \
  fi; \
  MODEL="{{model}}"; \
  if [[ -z "$MODEL" ]]; then \
    MODEL="${GEMINI_MODEL:-}"; \
  fi; \
  PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m finance_ebook {{ if limit != "" { "--limit " + limit } else { "" } }} --model "$MODEL";

regenerate limit="" model="gemini-3.1-pro-preview":
  PYTHON_BIN="$(command -v python3 || command -v python || true)"; \
  if [[ -z "$PYTHON_BIN" ]]; then \
    echo "Missing required command: python3 (or python)" >&2; \
    exit 1; \
  fi; \
  MODEL="{{model}}"; \
  if [[ -z "$MODEL" ]]; then \
    MODEL="${GEMINI_MODEL:-}"; \
  fi; \
  PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m finance_ebook {{ if limit != "" { "--limit " + limit } else { "" } }} --force --model "$MODEL";

serve:
  mdbook serve

build:
  mdbook build

clean:
  rm -rf book
  rm -f ebook/note_*.md
  rm -f ebook/README.md ebook/SUMMARY.md
