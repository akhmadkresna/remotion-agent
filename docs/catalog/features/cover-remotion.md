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

1. Prefer `edit/mezzanine/<name>.mp4` when present (deliverable size), else raw
2. **Copy** (never hardlink) into `packages/remotion-kit/public/ae-media/` — hardlinks
   on Windows make overwriting Studio media destroy episode `raw/`
3. Write `edit/remotion-props.json` with **public-relative** sources (`ae-media/cam.mov`)
4. Pass `--props` to `remotion studio` / `render`
5. Fail loudly if timeline is empty or sources are still absolute

### Why multi‑GB raw ≠ deliverable quality loss

Native cam is often 1440p60 at ~15–20 Mbps (~4 GB / 30 min). Episode `project.yaml`
targets 1920×1080@30. Run:

```bash
ae mezzanine .                 # CRF 16 → edit/mezzanine/ (raw untouched)
ae compose . --studio          # stages mezzanines
```

CRF 16 at deliverable size is near-transparent for YouTube (platform re-encodes).
This shrinks Remotion I/O without lowering published quality.

UI fallback: `MissingTimelineBanner` if Studio somehow loads empty props.

## Test

```bash
uv run pytest tests/test_compose_staging.py
uv run ae cover /path/to/episode
uv run ae mezzanine /path/to/episode   # if raw ≫ deliverable
uv run ae compose /path/to/episode --prepare-only
# preflight must print "preflight OK"
uv run ae compose /path/to/episode --studio
```
