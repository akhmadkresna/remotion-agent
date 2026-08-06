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

## Process

1. **Inventory** — `ae ingest .` → `edit/takes_packed.md`
2. **Converse** — describe material; ask shaped questions
3. **Propose** radio-edit strategy (4–8 sentences) → **wait for confirm**
4. **Write** `edit/edl.json` (`sources` + `ranges[]` with `source`/`start`/`end`)
5. **Cut** — `ae cut .` → `edit/preview.mp4`
6. **Cover** (if screen) — write `edit/cover.json` → `ae cover .`
6b. **Mezzanine** (if raw is multi‑GB / higher than project res/fps) — `ae mezzanine .`
7. **Compose** — `ae compose . --studio` or render
8. **QA** — `ae qa .` inspect `edit/verify/` cut frames
9. **Iterate** — natural language; never re-transcribe casually

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
    "max_hold_sec": 16,
    "scales": { "wide": 1.0, "medium": 1.1, "close": 1.18 }
  },
  "events": [
    { "type": "framing", "start": 10.0, "end": 18.0, "framing": "close", "motion": "ease" },
    { "type": "punch_in", "start": 35.5, "end": 41.0, "scale": 1.12 },
    { "type": "screen", "source": "screen", "start": 14.0, "end": 20.0 }
  ],
  "captions": []
}
```

Framing presets simulate a 2–3 camera setup from one cam. Propose a camera-play plan from the transcript before writing `cover.json`.

## Promote

Append to `edit/promotions.md`, then patch framework packages and re-preview.
Run `ae promote-check .` to list pending notes.
