# AGENTS.md

## Cursor Cloud specific instructions

This repo is the **framework** for a local, agent-driven video editor. It is not a
long-running service: there is no HTTP server, database, or Docker. "Running the app"
means running the Python `ae` CLI pipeline against an *episode* folder and rendering
(or previewing) with Remotion. See `README.md` for the command reference and the hard
editing rules.

### Toolchain / how to invoke things
- Two package managers are used: **uv** (Python) and **pnpm** (Node ≥20). The update
  script installs `uv` (to `~/.local/bin`) and runs `uv sync --extra dev` + `pnpm install`.
  If `uv` is not on `PATH`, add `~/.local/bin` to it.
- Run the CLI as `uv run ae <cmd>` (console script defined in `pyproject.toml`). Health
  check: `uv run ae doctor` (exits non-zero only if ffmpeg/ffprobe are missing).
- Lint: `uv run ruff check .` (there is no `[tool.ruff]` config; the repo currently has
  pre-existing findings — do not treat those as environment breakage). Tests:
  `uv run pytest` (no test suite exists yet). TS build: `pnpm -r run build`.

### AGENTIC_EDITOR_HOME (non-obvious)
- When you run `ae` from *inside* the framework repo, it auto-resolves the framework
  root. When you run it from an **episode folder elsewhere on disk**, you must
  `export AGENTIC_EDITOR_HOME=<abs path to this repo>` so `ae new`/templates/Remotion
  kit resolve. Episodes are thin folders (`project.yaml` + `raw/` + `edit/`) that live
  *outside* this repo.

### First-run network downloads (cached afterward)
- `ae ingest` uses **faster-whisper**, which downloads model weights from HuggingFace on
  first use (cached in `~/.cache/huggingface`). For quick smoke tests set `asr.model: tiny`
  in the episode `project.yaml` (default is `small`, ~460 MB). An unauthenticated HF-rate
  warning is normal.
- `ae compose` / `pnpm -r run build` download **Chrome Headless Shell** for Remotion on
  first render (cached under the Remotion cache). Expect a one-time download.
- `whisper.cpp` is the macOS-only ASR path; on Linux the `auto` backend is always
  `faster-whisper`, so a missing `whisper.cpp`/`ggml-*.bin` is expected and fine.

### End-to-end pipeline (the "run the app" flow)
`ae new <ep>` → drop `raw/cam.mp4` → `ae ingest <ep>` → write `<ep>/edit/edl.json`
(non-empty `ranges`) → `ae cut <ep>` → `ae cover <ep>` → `ae compose <ep>` (renders
`edit/final.mp4`) or `ae compose <ep> --studio` (interactive Remotion Studio server).
Always launch Studio via `ae compose --studio` (it stages media into
`packages/remotion-kit/public/ae-media` and passes `--props`); a bare
`pnpm remotion studio` shows an empty ~3s black timeline.
