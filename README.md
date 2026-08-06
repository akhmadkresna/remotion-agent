# remotion-agent (Agentic Editor)

Local agentic pipeline for YouTube-style talking-head edits:

**footage → ASR → radio-edit EDL → cover (cam/screen/punch-in) → Remotion**

This repo is the **framework**. Episodes live elsewhere as thin folders (`project.yaml` + `raw/` + `edit/`).

Repo: https://github.com/akhmadkresna/remotion-agent

---

## Easy setup (paste this prompt)

Copy the block below into Cursor (or any coding agent) on a fresh machine:

```
Set up remotion-agent on this machine.

Clone https://github.com/akhmadkresna/remotion-agent.git into a sensible
dev folder (for example ~/dev/remotion-agent). That clone is the framework —
set AGENTIC_EDITOR_HOME to its absolute path and persist it in my shell
profile so new terminals keep it. Put the framework's .venv/bin on PATH
(or wire an ae alias via uv run) so the ae CLI works.

Install whatever is missing: uv, Node 20+, pnpm, and ffmpeg. On macOS also
install whisper-cpp (brew). Then from AGENTIC_EDITOR_HOME run uv sync and
pnpm install.

On macOS, download ggml-small.bin into $AGENTIC_EDITOR_HOME/models/ from
https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
(about 466 MB; do not commit it). On Windows/Linux skip whisper-cpp —
faster-whisper from uv sync is enough.

Symlink the Cursor skill once:
~/.cursor/skills/agentic-editor → $AGENTIC_EDITOR_HOME/skills/agentic-editor

Finish by running ae doctor and fix anything it reports missing until
ffmpeg, ffprobe, node, pnpm are OK, and either whisper.cpp + a ggml model
or faster-whisper is OK. Then briefly tell me the AGENTIC_EDITOR_HOME path
and how to create a first episode with ae new.
```

After setup, open an **episode** folder in Cursor (not only the framework), drop `raw/cam.mp4`, and ask the agent to ingest and edit. Confirm the radio-edit plan before it writes `edit/edl.json`.

---

## ASR backends

| `asr.backend` | Machine | Engine |
|---------------|---------|--------|
| `auto` (default) | macOS + `whisper-cli` installed | whisper.cpp |
| `auto` | no whisper.cpp, or Windows/Linux | faster-whisper |
| `whisper.cpp` / `faster-whisper` | any | force |

Default ASR language is **Indonesian** (`asr.language: id`); override per episode in `project.yaml`.

---

## Cursor workflow

- Open the **episode** folder when editing a video.
- Skill + `ae` always reach this framework via `AGENTIC_EDITOR_HOME`.
- For promotions (reusable fixes), open a multi-root workspace: episode + this repo. See [`examples/episode.code-workspace`](examples/episode.code-workspace) (edit the framework path to your clone).

---

## Commands

| Command | Purpose |
|---------|---------|
| `ae doctor` | Check deps + chosen ASR backend |
| `ae new <path>` | Scaffold episode |
| `ae ingest .` | Probe + ASR + `takes_packed.md` |
| `ae cut .` | EDL → `edit/preview.mp4` |
| `ae cover .` | EDL + cover → `timeline.json` |
| `ae mezzanine .` | Deliverable proxies → `edit/mezzanine/` (raw untouched) |
| `ae compose . [--studio]` | Remotion preview / render |
| `ae qa .` | Cut-boundary frames in `edit/verify/` |
| `ae promote-check .` | Show `edit/promotions.md` |

---

## Layout

```
src/agentic_editor/    # Python CLI + ASR + editor + cover
packages/schema/       # Zod contracts
packages/remotion-kit/ # Remotion composition
templates/project/     # ae new scaffold
skills/agentic-editor/
styles/tutorial/
docs/catalog/
models/                # ggml *.bin (gitignored — download locally)
```

---

## Hard rules (editing)

1. Confirm strategy before writing `edit/edl.json`.
2. Never cut mid-word; snap to transcript word boundaries; pad 30–200ms.
3. `ae cut` applies 30ms audio fades — do not skip.
4. Cache transcripts — never re-ASR unless source changed (`ae ingest --force`).
5. All outputs in `edit/`. Raw footage is read-only (compose **copies** into public — never hardlinks).
6. Promote reusable changes into this repo, not episode copies.
7. Heavy raw (e.g. 1440p60 multi‑GB): `ae mezzanine .` before compose — CRF16 deliverable proxies, no quality loss for YouTube 1080p.
