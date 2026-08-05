# Cover + Remotion

## Entry points

- CLI: `ae cover`, `ae compose`
- Timeline: [`src/agentic_editor/cover/__init__.py`](../../src/agentic_editor/cover/__init__.py)
- Compose staging: [`src/agentic_editor/compose/__init__.py`](../../src/agentic_editor/compose/__init__.py)
- Remotion: [`packages/remotion-kit/src/Composition.tsx`](../../packages/remotion-kit/src/Composition.tsx)

## Behavior

- `cover.json` `camera_play`: fake 2-cam (`wide` / `medium` / `close`), `snap_on_cuts`, `max_hold_sec` auto-splits
- Events: `framing`, `punch_in`, `punch_out`, `screen`, `pip` + captions
- Merges with EDL into `edit/timeline.json`
- Remotion: per-clip scale + motion (`snap` / `ease` / `drift`) and punch effects

## Studio preflight (do not regress)

Remotion runs in a **browser** — absolute disk paths and missing `--props` yield a black ~3s timeline.

`ae compose` always:

1. Hardlink/copy sources into `packages/remotion-kit/public/ae-media/`
2. Write `edit/remotion-props.json` with **public-relative** sources (`ae-media/cam.mov`)
3. Pass `--props` to `remotion studio` / `render`
4. Fail loudly if timeline is empty or sources are still absolute

UI fallback: `MissingTimelineBanner` if Studio somehow loads empty props.

## Test

```bash
uv run ae cover /path/to/episode
uv run ae compose /path/to/episode --prepare-only
# preflight must print "preflight OK"
uv run ae compose /path/to/episode --studio
```
