# Radio edit

## Entry points

- CLI: `ae edl-suggest`, `ae cut`
- Suggest: [`src/agentic_editor/editor/edl_suggest.py`](../../src/agentic_editor/editor/edl_suggest.py)
- Pack: [`src/agentic_editor/editor/pack.py`](../../src/agentic_editor/editor/pack.py)
- EDL: [`edl.py`](../../src/agentic_editor/editor/edl.py)
- Render: [`render.py`](../../src/agentic_editor/editor/render.py)
- Style knobs: `radio_edit.*` in [`styles/tutorial/style.md`](../../styles/tutorial/style.md)

## Behavior

1. `ae edl-suggest .` → `edit/edl.suggest.json` from cam transcript (silence + wait + repeat)
2. Agent proposes keep length / strategy → **wait for confirm**
3. `ae edl-suggest . --apply` (or copy) → `edit/edl.json`
4. `ae cut .` → per-segment extract with 30ms audio fades → `edit/preview.mp4`

### Silence / wait / repeat (tutorial defaults)

Goal: **clean sentences**, short AI waits — not shredded speech.

| Knob | Default | Meaning |
|------|---------|---------|
| `silence_gap_sec` | 0.55 | Pack words into sentence-ish phrases |
| `gap_cut_sec` | 0.70 | Cut silences ≥ this (keep mid-sentence breaths) |
| `hold_if_gap_sec` | 5.0 | Longer gaps (AI/screen waits) → short beat only |
| `hold_sec` | 1.0 | Beat kept when collapsing long gaps |
| `min_keep_sec` | 0.90 | Drop tiny fragments |
| `cut_repeats` | true | Drop near-duplicate phrases (Jaccard + containment) |
| `bridge_gap_sec` | 2.5 | Merge ASR-overlap / same-thought neighbors |
| `cut_wait_speech` | true | Clamp short wait prompts only |
| `wait_speech_max_sec` | 0.9 | Max keep for wait-filler speech |
| pads | 0.08 / 0.12 | Word-boundary snap pads |

```bash
ae edl-suggest .                          # style radio_edit.* defaults
ae edl-suggest . --source-end 1887        # CapCut-style source window
# after confirm:
ae edl-suggest . --apply
ae cut .
```

## Test

```bash
uv run pytest tests/test_prefer_screen_edl.py -q
uv run ae edl-suggest /path/to/episode
```
