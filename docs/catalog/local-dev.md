# Local development

## Setup

Paste the **Easy setup** natural-language prompt from the root [README.md](../../README.md) into Cursor on a fresh machine. Do not hand-roll a parallel bash checklist here — that prompt is the source of truth.

## Smoke after setup

```bash
uv run ae doctor
uv run ae new /tmp/ae-smoke-ep --force
```
