# Tutorial style pack

Defaults for tech talking-head + screen recordings.

**Locked A-roll MG:** Bold type + cool mist sky accent. Do not invent episode-local forks.

```yaml
captions:
  style: off                   # no full/karaoke dialogue captions — use overlays.emphasis
# Locked A-roll overlay presentation (Remotion). Bold + cool mist accent.
overlays:
  preset: bold_mist
  treatment: bold              # type-only — no glass cards
  accent: "#7dd3fc"            # cool mist sky
  accentName: cool_mist_sky
  ink: "#ffffff"
  dim: "rgba(255,255,255,0.55)"
  dwell:
    chip_sec: 4.0
    chapter_sec: 5.0
    diagram_sec: 7.5
    emphasis_sec: 2.4
    min_sec: 1.8
  fonts:
    display: Syne
    ui: Instrument Sans
  chapter:
    kickerSizeCqh: 2.4
    titleSizeCqh: 9
    leftCqw: 4.5
    topCqh: 12
    maxWidthCqw: 42
  emphasis:
    sizeCqh: 16
    leftCqw: 4.5
    bottomCqh: 28             # raised — was too low vs face/PIP
    underline: true
  diagram:
    leftCqw: 4.5
    topCqh: 10
    maxWidthCqw: 40
    stepSizeCqh: 3.6
  chip:
    leftCqw: 4.5
    topCqh: 10
    sizeCqh: 3.4
  safe:
    faceClear: true            # keep middle/face free
    zones: [left_third, lower_third]
  # Framework default (ae overlay-suggest): denser MG + punch coupling
  # - ~1 sting / 32s keep; chapter gap ~50s; emphasis gap ~10s
  # - quiet keep stretches >55s get gap-fill emphasis
  # - punch_in (in EDL) without nearby MG gets a forced emphasis sting
  # - chapter/diagram: prefer screen_with_cam; else framing medium/wide
  # - emphasis: close OK; ID payoff + screen-enter + punch score; bottomCqh 28
punch_in:
  scale: 1.28
  defaultDurationSec: 1.35
# Fake multicam defaults (ae cover / example_cover). Close must read as cam B.
camera_play:
  snap_on_cuts: true
  home: medium
  alt: close
  wide_on_resets: true
  max_hold_sec: 7
  scales:
    wide: 1.0
    medium: 1.22
    close: 1.42
# Smart radio-edit (ae edl-suggest): clause + gap-class — NOT silence packing.
# breath stays; think hard-cuts; long AI waits compress to a short hold beat.
radio_edit:
  breath_max_sec: 0.6
  wait_min_sec: 5.0         # gaps ≥ this → AI wait compress
  activity_wait_min_sec: 3.5
  hold_sec: 0.4             # visible beat (hold_tail survives word-snap)
  min_keep_sec: 0.90
  pad_before_sec: 0.08
  pad_after_sec: 0.12
  cut_repeats: true
  repeat_similarity: 0.75
  repeat_window_sec: 90
  cut_wait_speech: true
  wait_speech_max_sec: 0.9
  # legacy aliases (mapped to wait_min if new keys absent)
  silence_gap_sec: 0.60
  gap_cut_sec: 5.0
  hold_if_gap_sec: 5.0
cover:
  # Show screen when possible (tutorial default). Use mode: balanced for stricter gates.
  mode: prefer_screen
  screen_bias: 0.35
  require_activity_for_deixis: false
  prefer_screen_when:
    - look at
    - look here
    - here
    - this
    - click
    - klik
    - lihat
    - di sini
    - disini
    - UI
    - dashboard
    - screen
    - menu
    - button
    - form
    - field
    - error
    - cursor
    - code
    - terminal
  jump_cut_cover: punch_in
  min_hold_sec: 2.0
  min_active_sec: 1.0
  activity_fps: 2
  activity_threshold: 0.028
  merge_gap_sec: 1.2
  off_hold_sec: 1.5
  pad_before_sec: 0.5
  pad_after_sec: 1.5
# Locked screen-explainer presentation (Remotion). Do not invent episode-local forks.
screen_explainer:
  preset: cozy
  canvas:
    background: "#d9e2ec"       # cool mist
    backgroundDeep: "#c4d0dc"
    gradient: radial
  screen:
    presentation: float_centered
    widthRatio: 0.78            # cozy
    maxHeightRatio: 0.82
    borderRadiusPx: 24          # soft round
    shadow: soft_float
    objectFit: cover            # clean full-frame screen footage
    crop:
      mode: none               # no smart_window_detect — supply clean screen raw
  pip:
    anchor: stage_lower_right   # frame corner — not nested inside screen
    widthRatio: 0.18
    aspectRatio: "4:5"
    insetRightRatio: 0.035
    insetBottomRatio: 0.045
    borderRadiusPx: 14
    border: none
    objectFit: cover
    objectPosition: "center 28%"
```

## Cover modes

| Mode | When | Visual | Audio |
|------|------|--------|-------|
| Full cam | Default / no screen activity | Cam + `camera_play` framing | Cam |
| Screen + soft-float PIP | Deixis keywords **and** screen activity (see `ae cover-suggest`) | Cool-mist canvas, **cozy** floated screen (soft round, full frame) + cam PIP at **stage lower-right** | Cam only |

Agents must load these defaults when `project.yaml` has `style: tutorial` (framework default).

| Layer | Locked look |
|-------|-------------|
| A-roll MG (chapter / emphasis / diagram / chip) | **Bold** type + accent `#7dd3fc` (cool mist sky) |
| Screen + PIP stage | Cool-mist canvas `#d9e2ec` + cozy float (soft round, no smart crop) |

Run `ae cover-suggest .` after the EDL is confirmed when a `screen` source exists.
Supply **clean** screen footage (already cropped / no desktop chrome). Float uses
`crop.mode: none` + soft `borderRadiusPx` — do not hardcode per-episode crop %.
Do not fork overlay colors/fonts per episode — promote changes into this style pack.

**Draft review:** use `ae draft . --seconds 120 --render` (fromSec-safe slice + quality gates).
Do **not** hand-trim `remotion-props.json` by `start`/`end` — overlays use `fromSec`/`durationSec`
and will silently disappear (no opening chip).
