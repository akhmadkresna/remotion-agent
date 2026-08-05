"""Cut-boundary QA: extract filmstrip frames around each EDL join."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def extract_frame(video: Path, t: float, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{t:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "4",
        "-vf",
        "scale=480:-2",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def qa_cut_boundaries(
    video: Path,
    edl: dict[str, Any],
    verify_dir: Path,
    *,
    window: float = 1.5,
    verbose: bool = True,
) -> list[Path]:
    """For each cut boundary on the *output* timeline, grab frames at t±window/3."""
    verify_dir.mkdir(parents=True, exist_ok=True)
    offsets: list[float] = []
    acc = 0.0
    for r in edl.get("ranges") or []:
        dur = float(r["end"]) - float(r["start"])
        if acc > 0:
            offsets.append(acc)
        acc += dur

    frames: list[Path] = []
    for i, cut_t in enumerate(offsets):
        for label, t in (
            ("before", max(0.0, cut_t - window / 2)),
            ("at", cut_t),
            ("after", cut_t + window / 2),
        ):
            out = verify_dir / f"cut_{i:02d}_{label}_{t:.2f}.jpg"
            extract_frame(video, t, out)
            frames.append(out)
            if verbose:
                print(f"  QA frame → {out.name}")

    meta = {
        "video": str(video),
        "boundaries": offsets,
        "frames": [str(p) for p in frames],
    }
    (verify_dir / "qa_boundaries.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return frames


def qa_episode_preview(episode: Path, *, verbose: bool = True) -> Path:
    edit = episode / "edit"
    edl_path = edit / "edl.json"
    preview = edit / "preview.mp4"
    if not edl_path.is_file():
        raise FileNotFoundError(f"Missing {edl_path}")
    if not preview.is_file():
        raise FileNotFoundError(f"Missing {preview} — run ae cut first")
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    verify = edit / "verify"
    qa_cut_boundaries(preview, edl, verify, verbose=verbose)
    return verify
