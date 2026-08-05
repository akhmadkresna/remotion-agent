# ASR ingest

## Entry points

- CLI: `ae ingest`, `ae doctor`
- Code: [`src/agentic_editor/asr/ingest.py`](../../src/agentic_editor/asr/ingest.py)
- Backends: [`backends.py`](../../src/agentic_editor/asr/backends.py), [`whisper_cpp.py`](../../src/agentic_editor/asr/whisper_cpp.py), [`faster_whisper_backend.py`](../../src/agentic_editor/asr/faster_whisper_backend.py)

## Behavior

- `asr.backend: auto` → whisper.cpp on darwin, faster-whisper elsewhere
- Default `asr.language: id` (Indonesian speaker); override per episode if needed
- Cache by source fingerprint + backend + model + language under `edit/transcripts/`
- Packs `edit/takes_packed.md` after ASR

## Test

```bash
uv run ae doctor
uv run ae ingest /path/to/episode
```
