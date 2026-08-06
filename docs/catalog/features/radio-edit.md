# Radio edit

## Entry points

- CLI: `ae edl-suggest`, `ae cut`
- Suggest: [`src/agentic_editor/editor/edl_suggest.py`](../../src/agentic_editor/editor/edl_suggest.py)
- Pack: [`src/agentic_editor/editor/pack.py`](../../src/agentic_editor/editor/pack.py)
- EDL: [`edl.py`](../../src/agentic_editor/editor/edl.py)
- Render: [`render.py`](../../src/agentic_editor/editor/render.py)
- Style knobs: `radio_edit.*` in [`styles/tutorial/style.md`](../../styles/tutorial/style.md)

## Behavior

1. `ae edl-suggest .` → `edit/edl.suggest.json` from cam transcript silence gaps
2. Agent proposes keep length / strategy → **wait for confirm**
3. `ae edl-suggest . --apply` (or copy) → `edit/edl.json`
4. `ae cut .` → per-segment extract with 30ms audio fades → `edit/preview.mp4`

### Silence-cut formula (tutorial defaults)

| Knob | Default | Meaning |
|------|---------|---------|
| `gap_cut_sec` | 0.5 | Cut silences ≥ this |
| `hold_if_gap_sec` | 5.0 | Longer gaps (AI waits) keep a short hold |
| `hold_sec` | 1.5 | Hold duration when collapsing long gaps |
| `min_keep_sec` | 0.4 | Drop tiny ranges |
| pads | 0.05 / 0.08 | Word-boundary snap pads |

```bash
ae edl-suggest . --gap-cut 0.5 --hold-if-gap 5 --hold 1.5
ae edl-suggest . --source-end 1887   # CapCut-style source window
# after confirm:
ae edl-suggest . --apply
ae cut .
```

## Test

```bash
uv run pytest tests/test_prefer_screen_edl.py -q
uv run ae edl-suggest /path/to/episode
```
