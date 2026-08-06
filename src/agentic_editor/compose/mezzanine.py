"""Deliverable mezzanines for Remotion — keep raw masters intact, shrink Studio I/O.

Native cam (e.g. 2560×1440@60) is often multi‑GB. YouTube delivery here is typically
1920×1080@30. A CRF‑16 H.264 mezzanine at project size is visually lossless for that
target and much smaller — Remotion should stage those, never rewrite ``raw/``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


MEZZANINE_DIRNAME = "mezzanine"
# Near-transparent for 1080p YouTube (platform re-encodes anyway).
DEFAULT_CRF = 16
DEFAULT_PRESET = "medium"
# Warn / suggest mezzanine when a source is clearly heavier than deliverable.
SIZE_WARN_BYTES = 800 * 1024 * 1024


def mezzanine_dir(episode: Path) -> Path:
    return episode / "edit" / MEZZANINE_DIRNAME


def mezzanine_path(episode: Path, name: str) -> Path:
    return mezzanine_dir(episode) / f"{name}.mp4"


def probe_video(path: Path) -> dict[str, Any]:
    """Return width/height/fps/duration/size/codec for the first video stream."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,codec_name:format=duration,size",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams") or [{}]
    stream = streams[0] if streams else {}
    fmt = data.get("format") or {}
    rate = str(stream.get("r_frame_rate") or "0/1")
    fps = 0.0
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            fps = float(num) / float(den) if float(den) else 0.0
        except ValueError:
            fps = 0.0
    try:
        duration = float(fmt.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    try:
        size = int(fmt.get("size") or path.stat().st_size)
    except (TypeError, ValueError, OSError):
        size = path.stat().st_size if path.is_file() else 0
    return {
        "width": int(stream.get("width") or 0),
        "height": int(stream.get("height") or 0),
        "fps": fps,
        "duration": duration,
        "size": size,
        "codec": stream.get("codec_name") or "",
    }


def oversized_for_deliverable(
    probe: dict[str, Any],
    *,
    width: int,
    height: int,
    fps: int,
    size_warn_bytes: int = SIZE_WARN_BYTES,
) -> bool:
    """True when source is larger than the episode deliverable (res/fps/bytes)."""
    pw = int(probe.get("width") or 0)
    ph = int(probe.get("height") or 0)
    pfps = float(probe.get("fps") or 0)
    psz = int(probe.get("size") or 0)
    if pw > int(width * 1.05) or ph > int(height * 1.05):
        return True
    if pfps > float(fps) + 0.51:
        return True
    if psz >= size_warn_bytes:
        return True
    return False


def encode_mezzanine(
    src: Path,
    dest: Path,
    *,
    width: int,
    height: int,
    fps: int,
    crf: int = DEFAULT_CRF,
    preset: str = DEFAULT_PRESET,
) -> Path:
    """Re-encode ``src`` to project frame size/fps at high quality (does not touch raw)."""
    if not src.is_file():
        raise FileNotFoundError(f"mezzanine source missing: {src}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg not found on PATH")

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Keep a real .mp4 extension so ffmpeg can pick the muxer (`.mp4.partial` fails).
    tmp = dest.with_name(f"{dest.stem}.partial{dest.suffix}")
    if tmp.exists():
        tmp.unlink()

    # Fit inside deliverable canvas; pad to exact project size (16:9 safe).
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
    )
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-r",
        str(fps),
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "48000",
        "-movflags",
        "+faststart",
        "-f",
        "mp4",
        str(tmp),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    tmp.replace(dest)
    return dest


def build_mezzanines(
    episode: Path,
    sources: dict[str, Path],
    *,
    width: int,
    height: int,
    fps: int,
    crf: int = DEFAULT_CRF,
    force: bool = False,
    verbose: bool = True,
) -> dict[str, Path]:
    """Write ``edit/mezzanine/<name>.mp4`` for each source; skip up-to-date unless force."""
    out: dict[str, Path] = {}
    for name, src in sources.items():
        dest = mezzanine_path(episode, name)
        if (
            not force
            and dest.is_file()
            and dest.stat().st_mtime >= src.stat().st_mtime
            and dest.stat().st_size > 0
        ):
            if verbose:
                print(f"• mezzanine {name}: reuse {dest} ({dest.stat().st_size} bytes)")
            out[name] = dest
            continue
        if verbose:
            print(
                f"• mezzanine {name}: {src.name} → "
                f"{width}x{height}@{fps} CRF{crf} → {dest.relative_to(episode)}"
            )
        encode_mezzanine(
            src, dest, width=width, height=height, fps=fps, crf=crf
        )
        if verbose:
            print(f"  wrote {dest.stat().st_size} bytes")
        out[name] = dest
    return out


def resolve_compose_sources(
    episode: Path,
    abs_sources: dict[str, str],
    cfg: dict[str, Any],
    *,
    verbose: bool = True,
) -> dict[str, str]:
    """Prefer ``edit/mezzanine/*.mp4`` when present; otherwise raw + oversized warning."""
    width = int(cfg.get("width", 1920))
    height = int(cfg.get("height", 1080))
    fps = int(cfg.get("fps", 30))
    resolved: dict[str, str] = {}
    for name, abs_path in abs_sources.items():
        raw = Path(abs_path)
        mezz = mezzanine_path(episode, name)
        if mezz.is_file() and mezz.stat().st_size > 0:
            resolved[name] = str(mezz.resolve())
            if verbose:
                print(
                    f"• compose source {name}: mezzanine "
                    f"({mezz.stat().st_size} bytes) — raw untouched"
                )
            continue
        resolved[name] = str(raw.resolve())
        if not raw.is_file():
            continue
        try:
            probe = probe_video(raw)
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            continue
        if oversized_for_deliverable(probe, width=width, height=height, fps=fps):
            mb = probe["size"] / (1024 * 1024)
            if verbose:
                print(
                    f"! {name} is heavy for Remotion "
                    f"({probe['width']}x{probe['height']}@{probe['fps']:.0f}, "
                    f"{mb:.0f} MB). Deliverable is {width}x{height}@{fps}. "
                    f"Run: ae mezzanine .   # CRF{DEFAULT_CRF}, no raw rewrite"
                )
    return resolved
