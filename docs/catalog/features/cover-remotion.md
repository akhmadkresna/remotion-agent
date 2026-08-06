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
- Crop: `none` — supply clean full-frame screen footage; float uses soft round (`borderRadiusPx: 24`) + `objectFit: cover`
- Tokens load via `style_load.load_overlays` / `load_screen_explainer` → `timeline.presentation`
- **Quality gates** on `ae compose` / `ae draft`: missing remapped overlays, timid camera scales, soft punches
  (windowCrop required only if `crop.mode` is `smart_window_detect`)
- **Draft:** `ae draft . --seconds 120 [--render]` — fromSec-safe slice (do not hand-trim props)

## A-roll MG overlays

| Step | Command / artifact |
|------|--------------------|
| Draft | `ae overlay-suggest .` → `edit/overlays.suggest.json` (`overlays` + `framing_events`) |
| Confirm | Agent proposes plan → **wait** |
| Write | `cover.json` `overlays[]` **and** companion `framing` in `events[]` (cam source time) |
| Remap | `ae cover` / compose → `timeline.overlays[]` (output `fromSec`) |
| Render | Remotion `OverlayLayer` (Bold mist) |

Kinds: `chapter` · `emphasis` · `diagram` · `chip`. See skill hard rule 11.

**Default gate (camera / zoom play):** suggest reads `cover.json` screen windows + `camera_play`. Chapter/diagram prefer `screen_with_cam` (already wide/hold). On full-cam they emit companion `framing` medium/wide so MG does not fight close multicam crops (`faceClear`, left_third). Emphasis may use close.

**Density / relevance:** structure (chip/chapter/diagram + long-screen section quotas) is reserved first; emphasis is best-fit from an ID payoff lexicon, scored by screen-enter proximity. Min gaps (~90s chapters, ~25s emphasis). Caps ~1 sting / 70s keep.

**Dwell (readable MG):** style `overlays.dwell` — chip ~4s, chapter ~5s, diagram ~7.5s, emphasis ≥2.4s (min 1.8s). Remap floors `durationSec` by kind; Remotion `OverlayLayer` fades in/out (no hard pop-off).

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

`ae cover-suggest` scores windows with two signals + a **mode**:

| Mode | Behavior |
|------|----------|
| `prefer_screen` (tutorial default) | Deixis **or** activity → screen; deixis may keep screen even if idle; `off_hold_sec` extends past last motion; `screen_bias` lowers gates |
| `balanced` | Deixis needs activity confirmation when bins exist |

1. **Transcript deixis** — cam ASR phrases from style pack `cover.prefer_screen_when`
2. **Screen activity** — ffmpeg ~2 fps frame-diff bins

```bash
ae cover-suggest .                         # style mode (prefer_screen)
ae cover-suggest . --mode prefer_screen --screen-bias 0.5
ae cover-suggest . --mode balanced         # stricter
ae cover-suggest . --apply                 # only after confirm
ae cover .
```

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
uv run pytest tests/test_compose_staging.py tests/test_cover.py tests/test_overlay_suggest.py tests/test_draft_quality.py -q
uv run ae cover /path/to/episode
uv run ae cover-suggest /path/to/episode
uv run ae overlay-suggest /path/to/episode
uv run ae mezzanine /path/to/episode   # if raw ≫ deliverable
uv run ae compose /path/to/episode --prepare-only
# preflight must print "preflight OK"; quality WARN/ERROR if soft cam or missing overlays
uv run ae draft /path/to/episode --seconds 120 --render
uv run ae compose /path/to/episode --studio
```
