set shell := ["bash", "-euo", "pipefail", "-c"]

default:
  just --list

generate limit="" force="false":
  if [[ "{{force}}" == "true" ]]; then \
    scripts/generate_daily_notes.sh {{ if limit != "" { "--limit " + limit } else { "" } }} --force; \
  else \
    scripts/generate_daily_notes.sh {{ if limit != "" { "--limit " + limit } else { "" } }}; \
  fi

serve:
  mdbook serve

build:
  mdbook build

clean:
  rm -rf book
