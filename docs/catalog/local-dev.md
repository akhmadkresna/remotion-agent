# Local development

## Install

```bash
git clone https://github.com/akhmadkresna/remotion-agent.git
cd remotion-agent
export AGENTIC_EDITOR_HOME="$(pwd)"
uv sync
pnpm install
uv run ae doctor
```

See the root [README.md](../../README.md) for prerequisites, ASR models, and Cursor skill symlink.

## Tests / smoke

```bash
uv run ae doctor
uv run ae new /tmp/ae-smoke-ep --force
# (optional) copy a short mp4 to /tmp/ae-smoke-ep/raw/cam.mp4
# uv run ae ingest /tmp/ae-smoke-ep
```

## Skill

```bash
ln -sfn "$AGENTIC_EDITOR_HOME/skills/agentic-editor" ~/.cursor/skills/agentic-editor
```
