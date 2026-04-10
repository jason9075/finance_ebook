set shell := ["bash", "-euo", "pipefail", "-c"]

default:
  just --list

generate limit="" model="" workers="":
  PYTHON_BIN="$(command -v python3 || command -v python || true)"; \
  if [[ -z "$PYTHON_BIN" ]]; then \
    echo "Missing required command: python3 (or python)" >&2; \
    exit 1; \
  fi; \
  PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m finance_ebook {{ if limit != "" { "--limit " + limit } else { "" } }} {{ if model != "" { "--model " + model } else { "" } }} {{ if workers != "" { "--workers " + workers } else { "" } }};

regenerate limit="" model="" workers="":
  PYTHON_BIN="$(command -v python3 || command -v python || true)"; \
  if [[ -z "$PYTHON_BIN" ]]; then \
    echo "Missing required command: python3 (or python)" >&2; \
    exit 1; \
  fi; \
  PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m finance_ebook {{ if limit != "" { "--limit " + limit } else { "" } }} --force {{ if model != "" { "--model " + model } else { "" } }} {{ if workers != "" { "--workers " + workers } else { "" } }};

serve:
  mdbook serve

build:
  mdbook build

refresh-summary:
  PYTHON_BIN="$(command -v python3 || command -v python || true)"; \
  if [[ -z "$PYTHON_BIN" ]]; then \
    echo "Missing required command: python3 (or python)" >&2; \
    exit 1; \
  fi; \
  PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m finance_ebook --refresh-summary;

clean:
  rm -rf book
  rm -f ebook/note_*.md
  rm -f ebook/README.md ebook/SUMMARY.md
