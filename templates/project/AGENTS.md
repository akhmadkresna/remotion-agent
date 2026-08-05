# Episode agent notes

This folder is the **episode**. The framework lives in `$AGENTIC_EDITOR_HOME`.

## Always

1. Read `project.yaml` and `edit/takes_packed.md` (after ingest).
2. Run tools via `ae` (not ad-hoc ffmpeg scripts).
3. **Confirm** the radio-edit strategy with the user before writing `edit/edl.json`.
4. Snap cuts to word boundaries; pad 30–200ms; 30ms audio fades (handled by `ae cut`).
5. Outputs only under `edit/`. Never modify `raw/`.

## Commands

```bash
ae doctor
ae ingest .
ae cut .          # needs edit/edl.json
ae cover .        # needs edit/cover.json (cam/screen/punch_in)
ae compose . --studio
ae qa .
```

## Promote to framework

If you invent a reusable fix (caption style, Remotion component, ASR quirk):

1. Append a note to `edit/promotions.md`.
2. Patch files under `$AGENTIC_EDITOR_HOME` (multi-root workspace preferred).
3. Re-run preview on **this** episode.

Do not leave one-off Remotion forks inside `edit/` unless truly episode-specific.
