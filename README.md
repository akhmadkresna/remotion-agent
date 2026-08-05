# remotion-agent (Agentic Editor)

Local agentic pipeline for YouTube-style talking-head edits:

**footage → ASR → radio-edit EDL → cover (cam/screen/punch-in) → Remotion**

This repo is the **framework**. Episodes live elsewhere as thin folders (`project.yaml` + `raw/` + `edit/`).

Repo: https://github.com/akhmadkresna/remotion-agent

---

## Easy setup (one machine)

### 1. Prerequisites

| Tool | Why | Install |
|------|-----|---------|
| **Git** | clone | already on most Macs |
| **uv** | Python env + `ae` CLI | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node ≥ 20** + **pnpm** | Remotion | `brew install node` then `npm i -g pnpm` (or `brew install pnpm`) |
| **ffmpeg** | cut / QA | `brew install ffmpeg` |
| **whisper-cpp** (macOS, recommended) | fast local ASR | `brew install whisper-cpp` |

Windows / Linux: skip whisper-cpp; `uv sync` installs **faster-whisper** and `ae` uses it automatically.

### 2. Clone and install

```bash
git clone https://github.com/akhmadkresna/remotion-agent.git
cd remotion-agent

# remember this path — every shell / Cursor session needs it
export AGENTIC_EDITOR_HOME="$(pwd)"

uv sync
pnpm install
```

Put `ae` on your PATH (pick one):

```bash
# option A — this shell only
export PATH="$AGENTIC_EDITOR_HOME/.venv/bin:$PATH"

# option B — always via uv
alias ae='uv run --directory "$AGENTIC_EDITOR_HOME" ae'
```

Persist the env var (recommended):

```bash
# zsh
echo 'export AGENTIC_EDITOR_HOME="$HOME/dev/remotion-agent"' >> ~/.zshrc
echo 'export PATH="$AGENTIC_EDITOR_HOME/.venv/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Adjust the path if you cloned somewhere else.

### 3. ASR model (macOS / whisper.cpp)

```bash
mkdir -p "$AGENTIC_EDITOR_HOME/models"
curl -L -o "$AGENTIC_EDITOR_HOME/models/ggml-small.bin" \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

(~466 MB; not committed to git.)

### 4. Verify

```bash
ae doctor
```

You want `ffmpeg` / `ffprobe` / `node` / `pnpm` OK, plus either `whisper.cpp CLI: OK` + a ggml model, or `faster-whisper: OK`.

### 5. Cursor skill (once)

```bash
mkdir -p ~/.cursor/skills
ln -sfn "$AGENTIC_EDITOR_HOME/skills/agentic-editor" ~/.cursor/skills/agentic-editor
```

### 6. First episode

```bash
ae new ~/Videos/my-ep
cd ~/Videos/my-ep
# drop raw/cam.mp4 (and optional raw/screen.mp4)
ae ingest .
```

Then edit with the Cursor agent (skill loaded). Confirm a radio-edit plan before writing `edit/edl.json`, then:

```bash
ae cut .
ae cover .            # if you have edit/cover.json
ae compose . --studio
ae qa .
```

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
5. All outputs in `edit/`. Raw footage is read-only.
6. Promote reusable changes into this repo, not episode copies.
