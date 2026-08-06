# Cover + Remotion

## Entry points

- CLI: `ae cover`, `ae cover-suggest`, `ae compose`
- Timeline: [`src/agentic_editor/cover/__init__.py`](../../src/agentic_editor/cover/__init__.py)
- Suggest: [`src/agentic_editor/cover/suggest.py`](../../src/agentic_editor/cover/suggest.py)
- Compose staging: [`src/agentic_editor/compose/__init__.py`](../../src/agentic_editor/compose/__init__.py)
- Remotion: [`packages/remotion-kit/src/Composition.tsx`](../../packages/remotion-kit/src/Composition.tsx)

## Visual modes

| Mode | Cover event | Visual | Audio |
|------|-------------|--------|-------|
| Full me | (default / framing / punch) | Cam + fake multicam framing | Cam |
| Screen + soft-float PIP | `screen_with_cam` (alias `cam_pip`) | Cool-mist canvas, **cozy** floated screen (`float_centered`) + cam PIP at **stage lower-right** | Cam only |

**Locked tutorial presentation** (`styles/tutorial`):
- A-roll MG (`overlays`): **Bold** type + accent **cool mist sky** `#7dd3fc` — no glass cards, no full/karaoke captions
- Screen stage (`screen_explainer`): preset **cozy** (screen width 78%), canvas **cool mist** `#d9e2ec`
- PIP: no border, stage lower-right (not nested in the screen window)
- Crop: `smart_window_detect` (`cover/window_crop.py`) — dynamic window bbox + optional browser-chrome trim; annotated on clips as `windowCrop` at compose time
- Tokens load via `style_load.load_overlays` / `load_screen_explainer` → `timeline.presentation`

## A-roll MG overlays

| Step | Command / artifact |
|------|--------------------|
| Draft | `ae overlay-suggest .` → `edit/overlays.suggest.json` (`overlays` + `framing_events`) |
| Confirm | Agent proposes plan → **wait** |
| Write | `cover.json` `overlays[]` **and** companion `framing` in `events[]` (cam source time) |
| Remap | `ae cover` / compose → `timeline.overlays[]` (output `fromSec`) |
| Render | Remotion `OverlayLayer` (Bold mist) |

Kinds: `chapter` · `emphasis` · `diagram` · `chip`. See skill hard rule 11.

**Default gate (camera / zoom play):** suggest reads `cover.json` screen windows + `camera_play`. Chapter/diagram prefer `screen_with_cam` (already wide/hold). On full-cam they emit companion `framing` medium/wide so MG does not fight close multicam crops (`faceClear`, left_third). Emphasis may use close. Caps scale with keep duration (~1 sting / 90s).

**Audio rule (hard):** every non-`cam` clip is muted in Remotion. Screen never contributes audio.

## Behavior

- `cover.json` `camera_play`: fake 2-cam (`wide` / `medium` / `close`), `snap_on_cuts`, `max_hold_sec` auto-splits — **skipped** while screen is the A-roll visual
- Events: `framing`, `punch_in`, `punch_out`, `screen`, `screen_with_cam`, `pip` + captions
- `screen` / `screen_full` also force a cam PIP underlay (audio + face) — prefer writing `screen_with_cam` explicitly
- Merges with EDL into `edit/timeline.json`
- Remotion: per-clip scale + motion (`snap` / `ease` / `drift`), punch effects, soft-float `pip_corner`

### `screen_with_cam` example

```json
{
  "type": "screen_with_cam",
  "start": 14.0,
  "end": 42.0,
  "note": "demo UI"
}
```

## When to switch (detectability formula)

`ae cover-suggest` scores windows with two signals:

1. **Transcript deixis** — cam ASR phrases from style pack `cover.prefer_screen_when` (lihat, klik, UI, …), padded −0.4s / +1.2s, snapped to words
2. **Screen activity** — ffmpeg samples screen at ~2 fps; mean abs frame-diff per 1s bin; active if ≥ `activity_threshold` (default 0.035)

```
use_screen_pip  iff  has_screen_source
                 AND duration >= min_hold (2.5s)
                 AND (deixis_hit OR sustained_activity >= min_active_sec)
                 AND screen_activity_in_window
```

Else stay full cam. Adjacent windows merge with gap ≤ 0.8s.

```bash
ae cover-suggest .              # → edit/cover.suggest.json
ae cover-suggest . --apply      # merge events into edit/cover.json
ae cover .
```

Do not invent screen ranges with no deixis and no activity.

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
uv run pytest tests/test_cover.py tests/test_overlay_suggest.py -q
uv run ae cover /path/to/episode
uv run ae cover-suggest /path/to/episode
uv run ae overlay-suggest /path/to/episode
uv run ae compose /path/to/episode --prepare-only
# preflight must print "preflight OK"
uv run ae compose /path/to/episode --studio
```
