"""Tests for MG overlay remap + suggest heuristics."""

from __future__ import annotations

from agentic_editor.cover import build_timeline_from_edl_and_cover
from agentic_editor.cover.overlay_suggest import (
    CHAPTER_NOTE_RE,
    _clean_title,
)
from agentic_editor.cover.remap import build_timeline_overlays, remap_source_window


def test_remap_source_window_basic():
    edl = {
        "ranges": [
            {"source": "cam", "start": 10.0, "end": 20.0},
            {"source": "cam", "start": 30.0, "end": 40.0},
        ]
    }
    # window fully in first keep
    slices = remap_source_window(edl, 12.0, 15.0)
    assert len(slices) == 1
    assert abs(slices[0]["fromSec"] - 2.0) < 1e-6
    assert abs(slices[0]["durationSec"] - 3.0) < 1e-6

    # window spans cut gap — only kept parts
    slices2 = remap_source_window(edl, 18.0, 32.0)
    assert len(slices2) == 2
    assert abs(slices2[0]["fromSec"] - 8.0) < 1e-6  # 18-20 → out 8-10
    assert abs(slices2[0]["durationSec"] - 2.0) < 1e-6
    assert abs(slices2[1]["fromSec"] - 10.0) < 1e-6  # 30-32 → out 10-12
    assert abs(slices2[1]["durationSec"] - 2.0) < 1e-6


def test_timeline_includes_remapped_overlays():
    edl = {
        "sources": {"cam": "/tmp/cam.mp4"},
        "ranges": [{"source": "cam", "start": 0.0, "end": 20.0, "note": "hook"}],
    }
    cover = {
        "camera_play": {"snap_on_cuts": False},
        "events": [],
        "overlays": [
            {
                "kind": "chapter",
                "start": 2.0,
                "end": 5.0,
                "kicker": "Chapter 01",
                "text": "Extend kontak",
            },
            {
                "kind": "emphasis",
                "start": 8.0,
                "end": 9.2,
                "text": "Studio API",
            },
        ],
    }
    tl = build_timeline_from_edl_and_cover(edl, cover, fps=30)
    assert tl["presentation"]["overlays"]["treatment"] == "bold"
    assert tl["presentation"]["overlays"]["accent"] == "#7dd3fc"
    ov = tl["overlays"]
    assert len(ov) == 2
    assert ov[0]["kind"] == "chapter"
    assert abs(ov[0]["fromSec"] - 2.0) < 1e-6
    assert ov[1]["kind"] == "emphasis"
    assert "Studio" in (ov[1].get("text") or "")


def test_overlay_cut_out_of_edl_dropped():
    edl = {
        "sources": {"cam": "/tmp/cam.mp4"},
        "ranges": [{"source": "cam", "start": 0.0, "end": 5.0}],
    }
    cover = {
        "overlays": [
            {"kind": "chip", "start": 20.0, "end": 23.0, "text": "gone"},
        ]
    }
    assert build_timeline_overlays(edl, cover) == []


def test_overlay_spanning_gap_keeps_longest_slice():
    """EDL holes must not blink multi-instances or drop the MG entirely."""
    edl = {
        "ranges": [
            {"source": "cam", "start": 0.0, "end": 10.0},
            {"source": "cam", "start": 20.0, "end": 30.0},
        ]
    }
    cover = {
        "overlays": [
            {
                "id": "ch-1",
                "kind": "chapter",
                "start": 8.0,
                "end": 24.0,
                "text": "Across cut",
                "kicker": "Chapter 01",
            }
        ]
    }
    # Remap yields 2s + 4s; pick longest only
    ov = build_timeline_overlays(edl, cover)
    assert len(ov) == 1
    assert ov[0]["id"] == "ch-1"
    assert abs(ov[0]["fromSec"] - 10.0) < 1e-6  # second keep: 20-24 → out 10-14
    assert ov[0]["durationSec"] >= 4.0


def test_overlay_sole_short_slice_not_dropped():
    edl = {
        "ranges": [{"source": "cam", "start": 0.0, "end": 10.0}],
    }
    cover = {
        "overlays": [
            {"id": "em-1", "kind": "emphasis", "start": 9.7, "end": 10.0, "text": "API"},
        ]
    }
    ov = build_timeline_overlays(edl, cover)
    assert len(ov) == 1
    assert ov[0]["id"] == "em-1"
    # dwell floor for emphasis, clamped to remaining timeline (0.3s left)
    assert ov[0]["durationSec"] <= 0.3 + 1e-6
    assert ov[0]["durationSec"] >= 0.05


def test_chapter_note_and_title_helpers():
    assert CHAPTER_NOTE_RE.search("fase 2 setup")
    # curated short labels (not raw note dumps)
    assert _clean_title("hook: Extend kontak") == "Lanjut Toko Material"
    assert _clean_title("hook + plan: continue toko material, roadmap") == "Roadmap"
    assert _clean_title("phase 1 done menus") == "Master Data"
