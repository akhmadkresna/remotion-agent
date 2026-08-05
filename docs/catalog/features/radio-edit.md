# Radio edit

## Entry points

- CLI: `ae cut`
- Pack: [`src/agentic_editor/editor/pack.py`](../../src/agentic_editor/editor/pack.py)
- EDL: [`edl.py`](../../src/agentic_editor/editor/edl.py)
- Render: [`render.py`](../../src/agentic_editor/editor/render.py)

## Behavior

- Agent writes `edit/edl.json` after user confirms strategy
- Per-segment extract with 30ms audio fades → lossless concat → `edit/preview.mp4`

## Test

```bash
# after edl.json exists
uv run ae cut /path/to/episode
```
