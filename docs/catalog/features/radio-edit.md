# Radio edit (gap-class)

## Entry points

- CLI: `ae edl-suggest`, `ae cut`
- Core: [`edl_suggest.py`](../../src/agentic_editor/editor/edl_suggest.py)
- Gap classes: [`gap_class.py`](../../src/agentic_editor/editor/gap_class.py)
- Style: `radio_edit.*` in [`styles/tutorial/style.md`](../../styles/tutorial/style.md)

## Architecture (do not regress)

**Silence is not discourse.** The old model packed words by silence and cut every gap ≥ a threshold — that shredded Indonesian talking-head speech (breath / think / stare-at-UI).

Smart pipeline:

1. **Clauses** from ASR `segments` (fallback: word phrases)
2. **Classify** each inter-clause gap:
   - `breath` — keep
   - `think` — keep (mid-thought / look-at-UI)
   - `ai_wait` — compress to `hold_sec` beat with **hold_tail** (survives word-snap)
   - `retake` — drop near-duplicate clause
3. Snap speech edges; preserve wait-beat tails
4. Cover projects screen intent in source time, then stitches through the keep mask

### Knobs

| Knob | Default | Meaning |
|------|---------|---------|
| `wait_min_sec` | 5.0 | Gaps ≥ this compress as AI wait |
| `breath_max_sec` | 1.2 | Short pause class |
| `hold_sec` | 1.0 | Visible wait beat (not full spinner) |
| `activity_wait_min_sec` | 3.5 | Earlier wait if screen busy in gap |
| `cut_repeats` | true | Drop near-duplicate clauses |
| `cut_wait_speech` | true | Clamp short wait-prompt lines only |

```bash
ae edl-suggest . --source-end 1887
# review _meta.gap_classes + keep_sec, then:
ae edl-suggest . --apply
ae cut .
```

## Invariants (tests)

- Mid-thought pause (~2–4s) stays inside one keep
- Wait beat end is not pulled back by speech-only snap
- Near-duplicate clauses → one keep
- Cover screen intent is continuous across keep holes inside one demo

## Test

```bash
uv run pytest tests/test_prefer_screen_edl.py tests/test_gap_class.py -q
```
