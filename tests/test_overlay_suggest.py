"""Tests for framing-aware overlay suggest defaults."""

from __future__ import annotations

import json
from pathlib import Path

from agentic_editor.cover.overlay_suggest import (
    caps_for_duration,
    companion_framing_event,
    is_mostly_screen,
    merge_framing_into_events,
    screen_windows,
    suggest_overlays,
)


def test_caps_scale_with_duration():
    short = caps_for_duration(300)
    long = caps_for_duration(1560)
    assert long["target_total"] > short["target_total"]
    assert long["chapter"] >= short["chapter"]
    assert long["emphasis"] >= short["emphasis"]


def test_screen_windows_and_majority():
    wins = screen_windows(
        [
            {"type": "screen_with_cam", "start": 10, "end": 40},
            {"type": "framing", "start": 0, "end": 5, "framing": "close"},
        ]
    )
    assert wins == [(10.0, 40.0)]
    assert is_mostly_screen(12, 20, wins) is True
    assert is_mostly_screen(0, 8, wins) is False


def test_companion_framing_rules():
    assert companion_framing_event(
        kind="chapter", start=1, end=4, on_screen=True, ov_id="c1"
    ) is None
    ch = companion_framing_event(
        kind="chapter", start=1, end=4, on_screen=False, ov_id="c1"
    )
    assert ch is not None
    assert ch["type"] == "framing"
    assert ch["framing"] == "medium"
    diag = companion_framing_event(
        kind="diagram", start=10, end=16, on_screen=False, ov_id="d1"
    )
    assert diag is not None and diag["framing"] == "wide"
    assert (
        companion_framing_event(
            kind="emphasis", start=2, end=3, on_screen=False, ov_id="e1"
        )
        is None
    )


def test_merge_framing_replaces_overlay_notes_only():
    existing = [
        {"type": "screen_with_cam", "start": 10, "end": 40},
        {"type": "framing", "start": 1, "end": 3, "framing": "close", "note": "overlay:old"},
        {"type": "framing", "start": 50, "end": 55, "framing": "close", "note": "manual"},
    ]
    new = [
        {
            "type": "framing",
            "start": 1,
            "end": 4,
            "framing": "medium",
            "note": "overlay:chip-open",
        }
    ]
    merged = merge_framing_into_events(existing, new)
    notes = [str(e.get("note") or "") for e in merged if e.get("type") == "framing"]
    assert "overlay:old" not in notes
    assert "manual" in notes
    assert "overlay:chip-open" in notes
    assert any(e.get("type") == "screen_with_cam" for e in merged)


def test_suggest_emits_framing_for_cam_chapter(tmp_path: Path):
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: demo\nsources:\n  cam: raw/cam.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4"},
                "ranges": [
                    {"source": "cam", "start": 0.0, "end": 20.0, "note": "hook intro"},
                    {
                        "source": "cam",
                        "start": 30.0,
                        "end": 80.0,
                        "note": "phase build flow steps",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    # No cover.json → full cam; chapter/diagram should request framing companions
    (edit / "transcripts").mkdir()
    words = []
    t = 0.0
    for w in "hook intro phase build flow steps model otomatis studio api".split():
        words.append({"type": "word", "word": w, "text": w, "start": t, "end": t + 0.4})
        t += 0.5
    # stretch into ranges
    words[0]["start"], words[0]["end"] = 0.1, 0.5
    words[1]["start"], words[1]["end"] = 0.5, 1.0
    for i, w in enumerate(words[2:], start=2):
        w["start"] = 30.0 + i * 0.5
        w["end"] = w["start"] + 0.4
    (edit / "transcripts" / "cam.json").write_text(
        json.dumps({"language": "id", "backend": "test", "model": "small", "words": words}),
        encoding="utf-8",
    )

    out = suggest_overlays(episode)
    assert out["overlays"]
    kinds = {o["kind"] for o in out["overlays"]}
    assert "chip" in kinds or "chapter" in kinds
    # full-cam chapter/diagram/chip → framing companions
    face_heavy = [o for o in out["overlays"] if o["kind"] in {"chapter", "diagram", "chip"}]
    assert face_heavy
    assert all(o.get("cover_mode") == "full_cam" for o in face_heavy)
    assert out["framing_events"]
    assert all(ev["type"] == "framing" for ev in out["framing_events"])


def test_suggest_skips_framing_on_screen_cover(tmp_path: Path):
    episode = tmp_path / "ep"
    edit = episode / "edit"
    edit.mkdir(parents=True)
    (episode / "project.yaml").write_text(
        "id: demo\nsources:\n  cam: raw/cam.mp4\n  screen: raw/screen.mp4\nstyle: tutorial\n",
        encoding="utf-8",
    )
    (edit / "edl.json").write_text(
        json.dumps(
            {
                "sources": {"cam": "../raw/cam.mp4", "screen": "../raw/screen.mp4"},
                "ranges": [
                    {
                        "source": "cam",
                        "start": 10.0,
                        "end": 100.0,
                        "note": "phase master data flow",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (edit / "cover.json").write_text(
        json.dumps(
            {
                "camera_play": {"snap_on_cuts": True, "home": "medium", "alt": "close"},
                "events": [
                    {"type": "screen_with_cam", "start": 10.0, "end": 100.0, "note": "ui"}
                ],
                "captions": [],
            }
        ),
        encoding="utf-8",
    )
    (edit / "transcripts").mkdir()
    (edit / "transcripts" / "cam.json").write_text(
        json.dumps(
            {
                "language": "id",
                "backend": "test",
                "model": "small",
                "words": [
                    {"type": "word", "word": "phase", "text": "phase", "start": 10.1, "end": 10.5},
                    {"type": "word", "word": "flow", "text": "flow", "start": 11.0, "end": 11.4},
                ],
            }
        ),
        encoding="utf-8",
    )

    out = suggest_overlays(episode)
    assert out["_meta"]["has_cover"] is True
    assert out["_meta"]["screen_event_windows"] == 1
    on_screen = [o for o in out["overlays"] if o.get("cover_mode") == "screen_with_cam"]
    assert on_screen
    # screen overlays should not need framing companions
    for o in on_screen:
        if o["kind"] in {"chapter", "diagram"}:
            assert o.get("requires_framing") is None
