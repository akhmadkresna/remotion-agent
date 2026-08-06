"""Smart window crop — dynamic bbox, not fixed percentages."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from agentic_editor.cover.style_load import DEFAULT_SCREEN_EXPLAINER, load_screen_explainer
from agentic_editor.cover.window_crop import detect_window_crop


def _make_pillarbox_png(path: Path, *, w: int = 320, h: int = 180, inset: int = 40) -> None:
    """Dark UI window on black desktop — ffmpeg lavfi."""
    # black frame + gray rectangle inset
    vf = (
        f"color=c=black:s={w}x{h}:d=0.04,"
        f"drawbox=x={inset}:y={inset // 2}:w={w - inset * 2}:h={h - inset}"
        f":color=0x404040:t=fill"
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


def test_style_locks_cozy_cool_mist():
    se = load_screen_explainer("tutorial")
    assert se["preset"] == "cozy"
    assert se["canvas"]["background"] == "#d9e2ec"
    assert se["screen"]["widthRatio"] == 0.78
    assert se["screen"]["crop"]["mode"] == "smart_window_detect"
    assert se["pip"]["anchor"] == "stage_lower_right"
    assert DEFAULT_SCREEN_EXPLAINER["preset"] == "cozy"


def test_detect_window_trims_pillarbox(tmp_path: Path):
    img = tmp_path / "win.png"
    try:
        _make_pillarbox_png(img, w=320, h=180, inset=40)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("ffmpeg not available")
    crop = detect_window_crop(img, analysis_max_width=320)
    assert crop.ok
    # Should trim substantial left/right black — not keep full 320
    assert crop.x >= 20
    assert crop.w <= 280
    # Normalized ratios must be dynamic (not a hardcoded 0.03 stage trim)
    norm = crop.as_normalized()
    assert 0.05 < norm["x"] < 0.25
    assert 0.5 < norm["w"] < 0.9
