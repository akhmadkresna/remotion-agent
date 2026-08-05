# Cover + Remotion

## Entry points

- CLI: `ae cover`, `ae compose`
- Timeline: [`src/agentic_editor/cover/__init__.py`](../../src/agentic_editor/cover/__init__.py)
- Remotion: [`packages/remotion-kit/src/Composition.tsx`](../../packages/remotion-kit/src/Composition.tsx)

## Behavior

- `cover.json` events: `screen`, `pip`, `punch_in`
- Merges with EDL into `edit/timeline.json`
- Remotion renders layouts, punch-in scale, captions

## Test

```bash
uv run ae cover /path/to/episode
uv run ae compose /path/to/episode --prepare-only
uv run ae compose /path/to/episode --studio
```
