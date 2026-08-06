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

Aggressive tutorial defaults — do **not** leave full AI wait / spinner time on screen.

| Knob | Default | Meaning |
|------|---------|---------|
| `gap_cut_sec` | 0.35 | Cut silences ≥ this |
| `hold_if_gap_sec` | 3.5 | Longer gaps (AI/screen waits) → short beat only |
| `hold_sec` | 0.7 | Beat kept when collapsing long gaps (not full wait UI) |
| `min_keep_sec` | 0.35 | Drop tiny ranges |
| `cut_repeats` | true | Drop near-duplicate phrases (Jaccard) |
| `repeat_similarity` | 0.82 | Similarity threshold |
| `repeat_window_sec` | 45 | Look-back for repeats |
| `cut_wait_speech` | true | Clamp "tunggu/sebentar/loading/…" |
| `wait_speech_max_sec` | 0.7 | Max keep for wait-filler speech |
| pads | 0.04 / 0.06 | Word-boundary snap pads |

```bash
ae edl-suggest .                          # style radio_edit.* defaults
ae edl-suggest . --gap-cut 0.35 --hold-if-gap 3.5 --hold 0.7
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
