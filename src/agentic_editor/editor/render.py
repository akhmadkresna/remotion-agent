"""Radio-edit render: per-segment extract → lossless concat (video-use hard rules)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from agentic_editor.editor.edl import load_edl


def _run_ffmpeg(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def is_portrait(video: Path) -> bool:
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        w, h = map(int, out.stdout.strip().split(","))
        return h > w
    except Exception:
        return False


def extract_segment(
    source: Path,
    seg_start: float,
    duration: float,
    out_path: Path,
    *,
    preview: bool = False,
    fps: int = 30,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    portrait = is_portrait(source)
    if preview:
        scale = "scale=-2:720" if not portrait else "scale=-2:1280"
        preset, crf = "ultrafast", "28"
    else:
        scale = "scale=1920:-2" if not portrait else "scale=-2:1920"
        preset, crf = "fast", "20"

    fade_out_start = max(0.0, duration - 0.03)
    af = f"afade=t=in:st=0:d=0.03,afade=t=out:st={fade_out_start:.3f}:d=0.03"

    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{seg_start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        scale,
        "-af",
        af,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        crf,
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(fps),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(cmd)


def concat_segments(segment_paths: list[Path], out_path: Path, edit_dir: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    concat_list = edit_dir / "_concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.resolve()}'\n" for p in segment_paths), encoding="utf-8"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list),
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    _run_ffmpeg(cmd)
    concat_list.unlink(missing_ok=True)


def resolve_path(maybe_path: str, base: Path) -> Path:
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    # EDL paths are relative to edit/ by convention (../raw/cam.mp4)
    return (base / p).resolve()


def render_edl(
    edl_path: Path,
    edit_dir: Path,
    *,
    output: Path | None = None,
    preview: bool = True,
    fps: int = 30,
    verbose: bool = True,
) -> Path:
    edl = load_edl(edl_path)
    ranges = edl["ranges"]
    sources = edl["sources"]
    clips_dir = edit_dir / ("clips_preview" if preview else "clips_graded")
    clips_dir.mkdir(parents=True, exist_ok=True)

    seg_paths: list[Path] = []
    if verbose:
        print(f"extracting {len(ranges)} segment(s) → {clips_dir.name}/")
    for i, r in enumerate(ranges):
        src_name = r["source"]
        src_path = resolve_path(sources[src_name], edit_dir)
        start = float(r["start"])
        end = float(r["end"])
        duration = end - start
        out_seg = clips_dir / f"seg_{i:02d}_{src_name}.mp4"
        note = r.get("note") or r.get("beat") or ""
        if verbose:
            print(f"  [{i:02d}] {src_name} {start:.2f}-{end:.2f} ({duration:.2f}s) {note}")
        extract_segment(
            src_path, start, duration, out_seg, preview=preview, fps=fps
        )
        seg_paths.append(out_seg)

    out = output or (edit_dir / ("preview.mp4" if preview else "a_roll.mp4"))
    if verbose:
        print(f"concat → {out.name}")
    concat_segments(seg_paths, out, edit_dir)
    return out
