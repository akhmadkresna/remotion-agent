"""Cover / timeline JSON for dual-source + Remotion."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def build_timeline_from_edl_and_cover(
    edl: dict[str, Any],
    cover: dict[str, Any] | None,
    *,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
) -> dict[str, Any]:
    """Merge radio-edit EDL with optional cover decisions into a Remotion timeline."""
    cover = cover or {}
    cover_events = cover.get("events") or []
    clips: list[dict[str, Any]] = []
    effects: list[dict[str, Any]] = []
    captions: list[dict[str, Any]] = list(cover.get("captions") or [])

    out_t = 0.0
    for r in edl["ranges"]:
        dur = float(r["end"]) - float(r["start"])
        src = r["source"]
        visual_src = src
        layout = "full"
        pip_ev = None

        for ev in cover_events:
            ev_start = float(ev.get("start", 0))
            ev_end = float(ev.get("end", 0))
            if ev_end <= float(r["start"]) or ev_start >= float(r["end"]):
                continue
            kind = (ev.get("type") or ev.get("layout") or "screen").lower()
            if kind in ("screen", "screen_full"):
                visual_src = ev.get("source") or "screen"
                layout = "full"
            elif kind in ("pip", "screen_pip"):
                pip_ev = ev
            elif kind in ("punch_in", "punch"):
                local = max(0.0, ev_start - float(r["start"]))
                effects.append(
                    {
                        "type": "punch_in",
                        "fromSec": out_t + local,
                        "durationSec": float(
                            ev.get("duration", max(0.1, ev_end - ev_start))
                        ),
                        "scale": float(ev.get("scale", 1.15)),
                    }
                )
            break

        clips.append(
            {
                "id": f"a-{len(clips)}",
                "track": "a_roll",
                "source": visual_src,
                "sourceIn": float(r["start"]),
                "sourceOut": float(r["end"]),
                "fromSec": out_t,
                "durationSec": dur,
                "layout": layout,
            }
        )

        if pip_ev is not None:
            local = max(0.0, float(pip_ev.get("start", r["start"])) - float(r["start"]))
            pip_dur = min(
                dur - local,
                float(pip_ev.get("end", r["end"])) - float(pip_ev.get("start", r["start"])),
            )
            clips.append(
                {
                    "id": f"pip-{len(clips)}",
                    "track": "overlay",
                    "source": pip_ev.get("source") or "screen",
                    "sourceIn": float(pip_ev.get("start", r["start"])),
                    "sourceOut": float(pip_ev.get("end", r["end"])),
                    "fromSec": out_t + local,
                    "durationSec": max(0.05, pip_dur),
                    "layout": "pip_corner",
                }
            )

        out_t += dur

    sources = dict(edl.get("sources") or {})
    return {
        "fps": fps,
        "width": width,
        "height": height,
        "durationInFrames": max(1, int(round(out_t * fps))),
        "durationSec": out_t,
        "sources": sources,
        "clips": clips,
        "effects": effects,
        "captions": captions,
    }


def write_timeline(path: Path, timeline: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(timeline, indent=2) + "\n", encoding="utf-8")


def example_cover() -> dict[str, Any]:
    return {
        "events": [
            {
                "type": "punch_in",
                "start": 2.0,
                "end": 4.0,
                "duration": 2.0,
                "scale": 1.15,
                "note": "emphasize key line",
            },
            {
                "type": "screen",
                "source": "screen",
                "start": 5.0,
                "end": 12.0,
                "note": "show UI while explaining",
            },
        ],
        "captions": [],
    }
