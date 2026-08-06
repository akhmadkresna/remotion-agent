"""Smart window crop — dynamic bbox from pillars + UI, not fixed percentages."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentic_editor.cover.window_crop import detect_window_crop


def _make_scene_png(
    path: Path,
    *,
    w: int = 640,
    h: int = 360,
    win: tuple[int, int, int, int] = (140, 36, 360, 250),
) -> None:
    """wallpaper edges + black pillars + dark UI window + taskbar."""
    wx, wy, ww, wh = win
    vf = (
        f"color=c=0x88AA66:s={w}x{h}:d=0.04,"  # wallpaper
        f"drawbox=x=48:y=0:w=72:h={h}:color=black:t=fill,"  # left pillar
        f"drawbox=x=520:y=0:w=72:h={h}:color=black:t=fill,"  # right pillar
        f"drawbox=x={wx}:y={wy}:w={ww}:h={wh}:color=0x2A2A2A:t=fill,"  # window
        f"drawbox=x={wx}:y={wy + wh}:w={ww}:h=18:color=black:t=fill,"  # gap
        f"drawbox=x=0:y={h - 28}:w={w}:h=28:color=0x3A3A50:t=fill"  # taskbar
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            vf,
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_detect_window_trims_wallpaper_and_pillars(tmp_path: Path) -> None:
    img = tmp_path / "scene.png"
    try:
        _make_scene_png(img)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ffmpeg not available")
    crop = detect_window_crop(img, analysis_max_width=640)
    assert crop.ok
    assert crop.x >= 80
    assert crop.x <= 160
    assert crop.w <= 480
    assert crop.w >= 300
    assert crop.y <= 60
    assert crop.y + crop.h <= 340
    norm = crop.as_normalized()
    assert 0.08 < norm["x"] < 0.35
    assert 0.4 < norm["w"] < 0.85


def test_detect_rejects_hardcoded_full_bleed(tmp_path: Path) -> None:
    img = tmp_path / "scene.png"
    try:
        _make_scene_png(img)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ffmpeg not available")
    crop = detect_window_crop(img, analysis_max_width=640)
    assert crop.w < 640 * 0.9
    assert crop.x > 10
