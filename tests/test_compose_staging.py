"""Compose staging + mezzanine selection — protect raw masters."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentic_editor.compose import stage_sources_for_remotion
from agentic_editor.compose.mezzanine import (
    oversized_for_deliverable,
    resolve_compose_sources,
)


def test_stage_copies_not_hardlinks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kit = tmp_path / "kit"
    (kit / "public").mkdir(parents=True)
    monkeypatch.setattr(
        "agentic_editor.compose.remotion_kit_dir", lambda: kit
    )

    src = tmp_path / "raw" / "cam.mp4"
    src.parent.mkdir(parents=True)
    payload = b"fake-master-bytes-do-not-clobber"
    src.write_bytes(payload)

    staged = stage_sources_for_remotion({"cam": str(src)}, verbose=False)
    assert staged["cam"] == "ae-media/cam.mp4"

    dest = kit / "public" / "ae-media" / "cam.mp4"
    assert dest.is_file()
    assert dest.read_bytes() == payload

    # Overwriting the staged file must not destroy the episode master.
    dest.write_bytes(b"DRAFT-PROXY-OVERWRITE")
    assert src.read_bytes() == payload


def test_resolve_prefers_mezzanine(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "cam.mp4"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"raw-master")
    mezz = tmp_path / "edit" / "mezzanine" / "cam.mp4"
    mezz.parent.mkdir(parents=True)
    mezz.write_bytes(b"deliverable-mezz")

    out = resolve_compose_sources(
        tmp_path,
        {"cam": str(raw)},
        {"width": 1920, "height": 1080, "fps": 30},
        verbose=False,
    )
    assert Path(out["cam"]).resolve() == mezz.resolve()


def test_oversized_1440p60_for_1080p30() -> None:
    probe = {
        "width": 2560,
        "height": 1440,
        "fps": 60.0,
        "size": 4_300_000_000,
        "codec": "h264",
    }
    assert oversized_for_deliverable(
        probe, width=1920, height=1080, fps=30
    )


def test_deliverable_size_not_oversized() -> None:
    probe = {
        "width": 1920,
        "height": 1080,
        "fps": 30.0,
        "size": 250_000_000,
        "codec": "h264",
    }
    assert not oversized_for_deliverable(
        probe, width=1920, height=1080, fps=30
    )
