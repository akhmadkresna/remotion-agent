"""Gap classification for smart radio-edit.

Silence is NOT discourse. Gaps are classified so we:
  - keep breath / think pauses inside a keep (natural speech)
  - compress long AI / UI waits to a short beat
  - drop retakes / near-duplicate clauses

This replaces the old one-threshold silence cutter that shredded Indonesian
talking-head tutorials.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GapClass(str, Enum):
    BREATH = "breath"  # short pause — always keep
    THINK = "think"  # mid-thought / look-at-UI — keep (do not shred)
    AI_WAIT = "ai_wait"  # long idle — compress to a beat
    RETAKE = "retake"  # near-duplicate clause — drop later


@dataclass(frozen=True)
class GapPolicy:
    """Style-tunable thresholds (seconds)."""

    breath_max: float = 1.2
    # Anything below wait_min that isn't a retake stays in the keep
    wait_min: float = 5.0
    hold_sec: float = 1.0
    # Optional: if screen activity is available, boost wait detection
    activity_wait_min: float = 3.5


DEFAULT_GAP_POLICY = GapPolicy()


def classify_gap(
    gap: float,
    *,
    policy: GapPolicy = DEFAULT_GAP_POLICY,
    screen_active: bool | None = None,
    is_retake: bool = False,
) -> GapClass:
    """Classify the silence between two speech clauses."""
    if gap <= 0.05:
        return GapClass.BREATH
    if is_retake:
        return GapClass.RETAKE
    if gap <= policy.breath_max:
        return GapClass.BREATH
    # Long pause while screen is busy → treat as wait a bit earlier
    wait_floor = policy.wait_min
    if screen_active is True:
        wait_floor = min(policy.wait_min, policy.activity_wait_min)
    if gap >= wait_floor:
        return GapClass.AI_WAIT
    # Mid pauses are think/look — keep them. This is the shredding fix.
    return GapClass.THINK


def activity_in_gap(
    activity_bins: list[dict[str, Any]] | None,
    gap_start: float,
    gap_end: float,
    *,
    threshold: float = 0.028,
) -> bool | None:
    """Return True if screen looks busy inside the gap, False if idle, None if unknown."""
    if not activity_bins or gap_end <= gap_start:
        return None
    active = 0.0
    total = 0.0
    for b in activity_bins:
        bs, be = float(b["start"]), float(b["end"])
        s = max(bs, gap_start)
        e = min(be, gap_end)
        if e <= s:
            continue
        dur = e - s
        total += dur
        if b.get("active") or float(b.get("activity") or 0) >= threshold:
            active += dur
    if total <= 0:
        return None
    return (active / total) >= 0.35
