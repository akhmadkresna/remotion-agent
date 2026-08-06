---
name: agentic-editor
description: >
  Local agentic YouTube editor. Ingest cam/screen footage, ASR (whisper.cpp on Mac,
  faster-whisper on Windows), radio-edit via EDL, dual-source cover, Remotion compose.
  Use when editing talking-head or tutorial videos, building EDLs, or promoting fixes
  into the agentic-editor framework.
---

# Agentic Editor

## Setup (once per machine)

```bash
export AGENTIC_EDITOR_HOME=/path/to/remotion   # this framework repo
cd "$AGENTIC_EDITOR_HOME" && uv sync && pnpm install
uv run ae doctor
# symlink this skill:
# ln -s "$AGENTIC_EDITOR_HOME/skills/agentic-editor" ~/.cursor/skills/agentic-editor
```

Workspace for **editing a video** = the episode folder (`project.yaml` + `raw/` + `edit/`).
Framework code is invoked via `ae` / `$AGENTIC_EDITOR_HOME`. Use a multi-root
`.code-workspace` when promoting reusable fixes.

## Hard rules

1. Confirm strategy before writing `edit/edl.json`.
2. Never cut mid-word; snap to transcript word boundaries; pad 30–200ms.
3. `ae cut` applies 30ms audio fades per segment — do not skip.
4. Cache transcripts — never re-ASR unless source changed (`ae ingest --force`).
5. All outputs in `edit/`. Raw footage is read-only — never hardlink `raw/` into
   Remotion `public/` (overwrite would clobber masters). Staging always **copies**.
6. Local ASR only: `auto` → whisper.cpp (darwin) / faster-whisper (else).
   Default language is **Indonesian** (`asr.language: id`); override per episode for other languages.
7. Promote reusable changes into `$AGENTIC_EDITOR_HOME`, not episode copies.
8. Remotion Studio: **only** via `ae compose . --studio` (stages `public/ae-media` + `--props`).
   Never start `remotion studio` bare — that shows a black empty timeline. Absolute `/Users/...`
   media paths will not load in the browser.
9. If raw ≫ deliverable (e.g. 1440p60 multi‑GB vs project 1080p30): `ae mezzanine .`
   then compose — CRF16 mezzanines in `edit/mezzanine/`; does not reduce YouTube quality.
10. **Audio always from cam.** Screen is visual-only (muted). Prefer `screen_with_cam` for UI demos.
11. **Locked look (`style: tutorial`):** A-roll MG = **Bold** type + accent `#7dd3fc` (cool mist sky).
    Screen stage = cool-mist canvas. No full/karaoke captions. Do not invent episode-local
    colors/fonts — change `styles/tutorial/style.md` (+ `style_load.py` / remotion-kit theme) instead.
12. **MG overlays:** after EDL (and preferably cover) is confirmed, run `ae overlay-suggest .`,
    propose the plan, **wait for confirm**, then write `cover.json` `overlays[]` **and** any
    companion `framing` events (or `ae overlay-suggest . --apply` only after confirm).
    Never invent timings mid-word. **Default:** overlay plan is gated by cover mode +
    camera_play — chapter/diagram prefer `screen_with_cam` (wide/hold); on full-cam they
    emit medium/wide framing companions so MG does not fight close zooms (`faceClear` /
    left_third). Emphasis may sit on close. Structure (chip/chapter/diagram + section
    quotas) is reserved first; emphasis is best-fit from an ID payoff lexicon scored by
    screen-enter. Gaps ~90s / ~25s; density ~1 sting / 70s keep.

## Process

1. **Inventory** — `ae ingest .` → `edit/takes_packed.md`
2. **Converse** — describe material; ask shaped questions
3. **Propose** radio-edit strategy (4–8 sentences) → **wait for confirm**
4. **EDL suggest** — `ae edl-suggest .` (aggressive silence + wait-speech clamp + repeat-cut; style `radio_edit.*`) → review `edit/edl.suggest.json`
   → confirm → `--apply` or write `edit/edl.json`
5. **Cut** — `ae cut .` → `edit/preview.mp4`
6. **Cover** (if `sources.screen` exists):
   - Run `ae cover-suggest .` (tutorial default **`prefer_screen`**) → review `edit/cover.suggest.json`
   - Propose full-cam vs `screen_with_cam` → **wait for confirm**
   - Write `edit/cover.json` → `ae cover .`
   - Stricter gate: `ae cover-suggest . --mode balanced`
6b. **Overlays (A-roll MG)** — chapter / emphasis / diagram / chip:
   - Run `ae overlay-suggest .` → `edit/overlays.suggest.json` (includes `framing_events`)
   - Propose sparse Bold-mist plan synced to cover + zoom → **wait for confirm**
   - Dwell must be readable (`overlays.dwell`; fade-out in Remotion) — do not accept ~1s pops
   - Write `cover.json` `overlays[]` + merge companion `framing` into `events[]`
     (source-time, word-snapped) → `ae cover .` / `ae compose .`
6c. **Mezzanine** (if raw is multi‑GB / higher than project res/fps) — `ae mezzanine .`
6d. **Draft review** — `ae draft . --seconds 120 --render` (quality gates; never hand-slice props)
7. **Compose** — `ae compose . --studio` or render
8. **QA** — `ae qa .` inspect `edit/verify/` cut frames
9. **Iterate** — natural language; never re-transcribe casually

### Why drafts used to look broken (framework gates)

| Miss | Cause | Gate now |
|------|-------|----------|
| No opening chip / OverlayLayer | Draft trim used `start`/`end`; overlays are `fromSec`/`durationSec` | `ae draft` + `slice_timeline` |
| Soft / boring zoom | Default scales 1.1/1.18; punches disabled for whole ep if any float existed | Punchier defaults; frame-aware punchScale; quality WARN |
| “Dumb” screen crop | Per-clip detect wider than verified window | Prefer `edit/window_crop.json` stable; ERROR if float lacks crop |

## EDL shape

```json
{
  "sources": { "cam": "../raw/cam.mp4" },
  "ranges": [
    { "source": "cam", "start": 12.4, "end": 18.1, "note": "hook" }
  ]
}
```

Paths in EDL are relative to `edit/`.

## Cover shape

```json
{
  "camera_play": {
    "snap_on_cuts": true,
    "home": "medium",
    "alt": "close",
    "wide_on_resets": true,
    "max_hold_sec": 7,
    "scales": { "wide": 1.0, "medium": 1.22, "close": 1.42 }
  },
  "events": [
    { "type": "framing", "start": 10.0, "end": 18.0, "framing": "close", "motion": "ease" },
    { "type": "punch_in", "start": 35.5, "end": 41.0, "scale": 1.28 },
    { "type": "screen_with_cam", "start": 14.0, "end": 42.0, "note": "demo UI" }
  ],
  "captions": []
}
```

Default scales are punchy on purpose (`close` ≥ 1.32). Soft scales (1.1 / 1.18) fail the
compose quality **warning** gate — multicam will look like no cut at all.
### Overlay shape (`cover.json` → remapped in `timeline.overlays`)

```json
{
  "overlays": [
    {
      "kind": "chapter",
      "start": 12.0,
      "end": 15.5,
      "kicker": "Chapter 01",
      "text": "Extend kontak dengan Studio"
    },
    { "kind": "emphasis", "start": 40.0, "end": 41.4, "text": "Studio API" },
    {
      "kind": "diagram",
      "start": 88.0,
      "end": 94.0,
      "kicker": "Flow",
      "title": "Toko Material",
      "steps": ["res.partner fields", "Seed kategori", "Gambar produk", "Kartu stok"]
    },
    { "kind": "chip", "start": 0.0, "end": 2.8, "text": "Odoo Studio" }
  ]
}
```

Times are **cam source seconds**. `ae cover` / compose remaps through the EDL onto output `fromSec`.

**Overlay ↔ camera_play (framework default in `ae overlay-suggest`):**

| Kind | Prefer cover | Framing on full-cam |
|------|----------------|---------------------|
| `chapter` / `diagram` | `screen_with_cam` (wide/hold already) | companion `framing` **medium** / **wide** |
| `chip` | either | companion **medium** |
| `emphasis` | either | close OK — no companion |

Safe zones stay `left_third` + `faceClear`. Suggest also scales density with keep length (~1 sting / 90s) and writes companion events as `framing_events` (merged into `cover.events` on `--apply`).

### Full cam vs screen + soft-float PIP

| Mode | Visual | Audio |
|------|--------|-------|
| Full me (default) | Cam + `camera_play` framing | Cam |
| `screen_with_cam` | Cool-mist canvas + cozy floated screen (smart window crop) + cam PIP at stage lower-right | Cam only |

**Formula** (also implemented by `ae cover-suggest`):

- Signal A: transcript deixis (`prefer_screen_when` — lihat, klik, UI, …)
- Signal B: screen frame-diff activity ≥ threshold
- Use PIP only when both make sense (deixis **or** sustained activity, **and** activity in window), hold ≥ 2.5s
- Do not invent screen ranges with neither signal

Framing presets simulate a 2–3 camera setup from one cam. Propose a camera-play plan from the transcript before writing `cover.json`. On screen ranges, skip framing zooms.

**Screen explainer (locked in `styles/tutorial`):** cozy + cool mist + `smart_window_detect`. Do not hardcode crop % per episode — `ae compose` attaches `windowCrop` from pixel detection. PIP anchors to the **frame** lower-right.

**Screen explainer (locked in `styles/tutorial`):** cozy + cool mist + `smart_window_detect`. Do not hardcode crop % per episode — `ae compose` attaches `windowCrop` from pixel detection. PIP anchors to the **frame** lower-right.

## Promote

Append to `edit/promotions.md`, then patch framework packages and re-preview.
Run `ae promote-check .` to list pending notes.
