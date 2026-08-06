"""Draft slice + quality audit — prevent silent bad public drafts."""

from __future__ import annotations

from pathlib import Path

from agentic_editor.compose.draft_slice import slice_timeline
from agentic_editor.compose.quality import audit_timeline_quality
from agentic_editor.compose import _attach_smart_window_crops, _load_stable_window_crop


def _base_timeline(**kwargs):
    tl = {
        "fps": 30,
        "width": 1920,
        "height": 1080,
        "durationSec": 180.0,
        "durationInFrames": 5400,
        "sources": {"cam": "ae-media/cam.mp4", "screen": "ae-media/screen.mp4"},
        "clips": [
            {
                "id": "a-0",
                "layout": "full",
                "source": "cam",
                "fromSec": 0.0,
                "durationSec": 10.0,
                "scale": 1.42,
                "framing": "close",
                "motion": "ease",
            },
            {
                "id": "a-1",
                "layout": "float_centered",
                "source": "screen",
                "fromSec": 55.0,
                "durationSec": 40.0,
                "scale": 1.0,
                "framing": "wide",
                "motion": "hold",
                "windowCrop": {"x": 0.12, "y": 0.05, "w": 0.78, "h": 0.91},
            },
        ],
        "effects": [
            {"type": "punch_in", "fromSec": 33.0, "durationSec": 1.35, "scale": 1.28}
        ],
        "overlays": [
            {
                "id": "chip-open",
                "kind": "chip",
                "fromSec": 0.08,
                "durationSec": 2.76,
                "text": "Odoo Studio",
            }
        ],
        "captions": [],
        "camera_play": {
            "max_hold_sec": 7,
            "scales": {"wide": 1.0, "medium": 1.22, "close": 1.42},
        },
    }
    tl.update(kwargs)
    return tl


def test_slice_keeps_fromsec_overlays():
    """Regression: hand trim on start/end dropped the opening chip."""
    sliced = slice_timeline(_base_timeline(), 120.0)
    assert sliced["durationSec"] == 120.0
    assert sliced["durationInFrames"] == 3600
    ovs = sliced["overlays"]
    assert len(ovs) == 1
    assert ovs[0]["id"] == "chip-open"
    assert ovs[0]["fromSec"] == 0.08
    assert len(sliced["effects"]) == 1
    assert len(sliced["clips"]) == 2


def test_slice_clips_overlay_past_limit():
    tl = _base_timeline(
        overlays=[
            {
                "id": "late",
                "kind": "emphasis",
                "fromSec": 100.0,
                "durationSec": 40.0,
                "text": "Late",
            }
        ]
    )
    sliced = slice_timeline(tl, 120.0)
    assert len(sliced["overlays"]) == 1
    assert sliced["overlays"][0]["durationSec"] == 20.0


def test_quality_flags_missing_overlays():
    tl = _base_timeline(overlays=[])
    cover = {"overlays": [{"id": "chip-open", "kind": "chip", "start": 1.0, "end": 4.0}]}
    errors, _warnings = audit_timeline_quality(tl, cover=cover)
    assert any("timeline.overlays is empty" in e for e in errors)


def test_quality_flags_timid_scales():
    tl = _base_timeline(
        camera_play={"scales": {"wide": 1.0, "medium": 1.1, "close": 1.18}, "max_hold_sec": 16}
    )
    _errors, warnings = audit_timeline_quality(tl)
    assert any("close=" in w for w in warnings)
    assert any("max_hold_sec" in w for w in warnings)


def test_quality_flags_overwide_float_crop_only_when_smart():
    tl = _base_timeline()
    tl["clips"][1]["windowCrop"] = {"x": 0.05, "y": 0.05, "w": 0.9, "h": 0.9}
    # Default crop.mode none — no over-wide warn
    _errors, warnings = audit_timeline_quality(tl)
    assert not any("wider than" in w for w in warnings)
    tl["presentation"] = {
        "screenExplainer": {
            "screen": {"crop": {"mode": "smart_window_detect"}},
        }
    }
    _errors, warnings = audit_timeline_quality(tl)
    assert any("wider than" in w for w in warnings)


def test_quality_errors_missing_window_crop_only_when_smart():
    tl = _base_timeline()
    del tl["clips"][1]["windowCrop"]
    # mode none (default): float without crop is OK
    errors, _warnings = audit_timeline_quality(tl)
    assert not any("missing windowCrop" in e for e in errors)
    tl["presentation"] = {
        "screenExplainer": {
            "screen": {"crop": {"mode": "smart_window_detect"}},
        }
    }
    errors, _warnings = audit_timeline_quality(tl)
    assert any("missing windowCrop" in e for e in errors)


def test_quality_flags_dropped_overlay_ids():
    tl = _base_timeline(
        overlays=[
            {
                "id": "chip-open",
                "kind": "chip",
                "fromSec": 0.08,
                "durationSec": 2.76,
                "text": "Odoo Studio",
            }
        ]
    )
    cover = {
        "overlays": [
            {"id": "chip-open", "kind": "chip", "start": 1.0, "end": 4.0, "text": "ok"},
            {"id": "gone", "kind": "emphasis", "start": 99.0, "end": 100.0, "text": "x"},
        ]
    }
    errors, _warnings = audit_timeline_quality(tl, cover=cover)
    assert any("missing from timeline after remap" in e for e in errors)


def test_stable_window_crop_preferred(tmp_path: Path):
    episode = tmp_path
    edit = episode / "edit"
    edit.mkdir()
    (edit / "window_crop.json").write_text(
        """{
          "stable": {
            "ok": true,
            "x": 228, "y": 58, "w": 1506, "h": 982,
            "normalized": {"x": 0.11875, "y": 0.0537, "w": 0.784375, "h": 0.909}
          }
        }
        """,
        encoding="utf-8",
    )
    loaded = _load_stable_window_crop(episode)
    assert loaded is not None
    assert loaded["px"]["w"] == 1506

    tl = {
        "clips": [
            {"id": "f1", "layout": "float_centered", "source": "screen"},
            {"id": "f2", "layout": "float_centered", "source": "screen"},
        ]
    }
    _attach_smart_window_crops(
        tl, {"screen": str(tmp_path / "missing.mp4")}, crop_cfg={}, episode=episode, verbose=False
    )
    assert tl["clips"][0]["windowCrop"]["w"] == 0.784375
    assert tl["clips"][1]["windowCropPx"]["x"] == 228
