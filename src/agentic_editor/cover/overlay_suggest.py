"""Suggest sparse A-roll MG overlays (chapter / emphasis / diagram / chip).

Default logic couples overlays to cover mode + camera_play framing so MG
does not fight close talking-head zooms (safe zones: left_third, faceClear).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentic_editor.cover.suggest import load_cam_words, snap_window_to_words
from agentic_editor.editor.edl import load_edl
from agentic_editor.project import load_project

CHAPTER_NOTE_RE = re.compile(
    r"(hook|chapter|lesson|fase|phase|section|reset|intro|outro|setup|bab)",
    re.I,
)
EMPHASIS_WORDS = {
    "studio",
    "api",
    "odoo",
    "workflow",
    "pipeline",
    "otomatis",
    "otomatisasi",
    "penting",
    "kunci",
    "custom",
    "field",
    "model",
}
DIAGRAM_NOTE_RE = re.compile(r"(pipeline|flow|step|langkah|fase|phase|alur)", re.I)

SCREEN_EVENT_TYPES = frozenset(
    {"screen_with_cam", "cam_pip", "screen", "screen_full"}
)

# Holds (seconds)
EMPHASIS_PAD = 0.08
CHAPTER_HOLD = 3.5
CHIP_HOLD = 2.8
DIAGRAM_HOLD = 6.0

# Kinds that need a clear left third / must not sit on close face crop
FACE_HEAVY_KINDS = frozenset({"chapter", "diagram"})
CHIP_PREFERS_MEDIUM = True

# Soft density: ~1 sting per this many keep-seconds (scales caps)
SEC_PER_OVERLAY = 90.0


def _clean_title(note: str) -> str:
    t = re.sub(r"[_\-]+", " ", note).strip()
    t = re.sub(r"\s+", " ", t)
    if not t:
        return "Section"
    t = re.sub(
        r"^(hook|chapter|lesson|fase|phase|section|reset|intro|outro|setup|bab)\s*[:\-]?\s*",
        "",
        t,
        flags=re.I,
    )
    return t[:72] if t else note[:72]


def _phrase_around(
    words: list[dict[str, Any]], i: int, *, max_words: int = 3
) -> tuple[str, float, float]:
    """Build a short emphasis phrase centered on word i."""
    start_i = i
    end_i = i
    while end_i + 1 < len(words) and end_i - start_i + 1 < max_words:
        nxt = words[end_i + 1]["text"]
        if nxt.lower().strip(".,!?;:") in EMPHASIS_WORDS or nxt[:1].isupper():
            end_i += 1
            continue
        break
    while start_i > 0 and end_i - start_i + 1 < max_words:
        prev = words[start_i - 1]["text"]
        if prev.lower().strip(".,!?;:") in EMPHASIS_WORDS:
            start_i -= 1
            continue
        break
    chunk = words[start_i : end_i + 1]
    text = " ".join(w["text"].strip(".,!?;:") for w in chunk).strip()
    return text, float(chunk[0]["start"]), float(chunk[-1]["end"])


def _load_cover(edit: Path) -> dict[str, Any]:
    path = edit / "cover.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _keep_duration(ranges: list[dict[str, Any]]) -> float:
    return sum(max(0.0, float(r["end"]) - float(r["start"])) for r in ranges)


def caps_for_duration(keep_sec: float) -> dict[str, int]:
    """Scale overlay budgets with radio-edit length (~1 sting / 90s keep)."""
    factor = max(1.0, float(keep_sec) / 600.0)  # 1.0 at ~10 min
    target = max(6, int(round(float(keep_sec) / SEC_PER_OVERLAY)))
    return {
        "chapter": min(10, max(3, int(round(4 * factor)))),
        "emphasis": min(14, max(4, int(round(6 * factor)))),
        "diagram": min(4, max(1, int(round(2 * factor)))),
        "chip": min(3, 1 + (1 if keep_sec >= 900 else 0) + (1 if keep_sec >= 1500 else 0)),
        "target_total": target,
    }


def screen_windows(events: list[dict[str, Any]]) -> list[tuple[float, float]]:
    wins: list[tuple[float, float]] = []
    for ev in events:
        kind = str(ev.get("type") or "").lower()
        if kind not in SCREEN_EVENT_TYPES:
            continue
        s, e = float(ev.get("start", 0)), float(ev.get("end", 0))
        if e > s:
            wins.append((s, e))
    wins.sort()
    return wins


def overlap_sec(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def is_mostly_screen(
    start: float,
    end: float,
    wins: list[tuple[float, float]],
    *,
    min_frac: float = 0.55,
) -> bool:
    dur = max(1e-6, end - start)
    covered = sum(overlap_sec(start, end, w0, w1) for w0, w1 in wins)
    return (covered / dur) >= min_frac


def overlaps_any(start: float, end: float, spans: list[tuple[float, float]]) -> bool:
    return any(not (end <= a or start >= b) for a, b in spans)


def companion_framing_event(
    *,
    kind: str,
    start: float,
    end: float,
    on_screen: bool,
    ov_id: str,
) -> dict[str, Any] | None:
    """
    When MG is on full-cam, emit an explicit framing event so camera_play
    does not leave the shot on close (which fights left_third / faceClear).

    Screen ranges already force wide/hold in ae cover — no companion needed.
    """
    if on_screen:
        return None
    if kind in FACE_HEAVY_KINDS:
        framing = "wide" if kind == "diagram" else "medium"
        motion = "ease" if kind == "chapter" else "hold"
        return {
            "type": "framing",
            "start": round(start, 3),
            "end": round(end, 3),
            "framing": framing,
            "motion": motion,
            "note": f"overlay:{ov_id}",
        }
    if kind == "chip" and CHIP_PREFERS_MEDIUM:
        return {
            "type": "framing",
            "start": round(start, 3),
            "end": round(end, 3),
            "framing": "medium",
            "motion": "hold",
            "note": f"overlay:{ov_id}",
        }
    # emphasis: close / home framing OK
    return None


def _annotate(
    ov: dict[str, Any],
    *,
    on_screen: bool,
    framing_ev: dict[str, Any] | None,
) -> dict[str, Any]:
    ov = dict(ov)
    ov["cover_mode"] = "screen_with_cam" if on_screen else "full_cam"
    if framing_ev:
        ov["requires_framing"] = framing_ev.get("framing")
        ov["framing_motion"] = framing_ev.get("motion")
    else:
        ov["requires_framing"] = None
        if on_screen:
            ov["framing_note"] = "screen_holds_wide"
        elif ov.get("kind") == "emphasis":
            ov["framing_note"] = "close_ok"
    return ov


def suggest_overlays(episode: Path) -> dict[str, Any]:
    """
    Draft overlay creatives in *source (cam) time*, gated by cover + framing.

    Returns overlays plus companion `framing_events` for full-cam chapter/diagram/chip.
    Agent must confirm before writing into cover.json.
    """
    episode = episode.resolve()
    cfg = load_project(episode)
    edit = episode / "edit"
    edl_path = edit / "edl.json"
    if not edl_path.is_file():
        raise FileNotFoundError("Missing edit/edl.json — confirm radio-edit first")

    edl = load_edl(edl_path)
    words = load_cam_words(edit)
    ranges = list(edl.get("ranges") or [])
    cover = _load_cover(edit)
    cover_events = list(cover.get("events") or [])
    camera_play = dict(cover.get("camera_play") or {})
    screen_wins = screen_windows(cover_events)
    keep_sec = _keep_duration(ranges)
    caps = caps_for_duration(keep_sec)

    overlays: list[dict[str, Any]] = []
    framing_events: list[dict[str, Any]] = []
    used_spans: list[tuple[float, float]] = []

    meta: dict[str, Any] = {
        "word_count": len(words),
        "range_count": len(ranges),
        "keep_sec": round(keep_sec, 1),
        "style": str(cfg.get("style") or "tutorial"),
        "preset": "bold_mist",
        "has_cover": bool(cover),
        "screen_event_windows": len(screen_wins),
        "camera_play": {
            "home": camera_play.get("home", "medium"),
            "alt": camera_play.get("alt", "close"),
            "snap_on_cuts": camera_play.get("snap_on_cuts", True),
        },
        "caps": caps,
        "rules": {
            "chapter_diagram": "prefer screen_with_cam; else emit framing medium/wide",
            "chip": "prefer medium framing on full cam",
            "emphasis": "close framing OK",
            "safe_zones": ["left_third", "lower_third"],
            "faceClear": True,
        },
    }

    def try_add(ov: dict[str, Any]) -> bool:
        nonlocal overlays, framing_events, used_spans
        if len(overlays) >= int(caps["target_total"]):
            return False
        s, e = float(ov["start"]), float(ov["end"])
        if overlaps_any(s, e, used_spans):
            return False
        on_screen = is_mostly_screen(s, e, screen_wins)
        # chapter/diagram on full cam only if we can reserve medium/wide framing
        if ov["kind"] in FACE_HEAVY_KINDS and not on_screen and not screen_wins:
            # no cover yet — still allow but attach framing companion
            pass
        framing_ev = companion_framing_event(
            kind=str(ov["kind"]),
            start=s,
            end=e,
            on_screen=on_screen,
            ov_id=str(ov.get("id") or ov["kind"]),
        )
        ov = _annotate(ov, on_screen=on_screen, framing_ev=framing_ev)
        overlays.append(ov)
        used_spans.append((s, e))
        if framing_ev:
            framing_events.append(framing_ev)
        return True

    # --- chip (opening) ---
    if ranges and caps["chip"] > 0:
        r0 = ranges[0]
        rs, r_end = float(r0["start"]), float(r0["end"])
        end = min(r_end, rs + CHIP_HOLD)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        title = str(cfg.get("id") or episode.name).replace("-", " ").replace("_", " ")
        try_add(
            {
                "id": "chip-open",
                "kind": "chip",
                "start": rs,
                "end": max(rs + 0.8, end),
                "text": title.title(),
                "note": "opening chip",
            }
        )

    # --- chapters from EDL notes (prefer starts of ranges; screen-friendly) ---
    chapter_i = 0
    for r in ranges:
        if chapter_i >= caps["chapter"]:
            break
        note = str(r.get("note") or r.get("beat") or "")
        if not note or not CHAPTER_NOTE_RE.search(note):
            continue
        rs, r_end = float(r["start"]), float(r["end"])
        end = min(r_end, rs + CHAPTER_HOLD)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        # Prefer chapter at start of screen sections when available; still OK on cam with framing
        on_screen = is_mostly_screen(rs, end, screen_wins)
        # If this range is mixed, snap chapter into the screen portion when possible
        if screen_wins and not on_screen:
            for w0, w1 in screen_wins:
                if overlap_sec(rs, r_end, w0, w1) >= CHAPTER_HOLD * 0.8:
                    rs = max(rs, w0)
                    end = min(w1, rs + CHAPTER_HOLD)
                    if words:
                        rs, end = snap_window_to_words(rs, end, words)
                    break
        chapter_i += 1
        if not try_add(
            {
                "id": f"chapter-{chapter_i:02d}",
                "kind": "chapter",
                "start": rs,
                "end": max(rs + 1.2, end),
                "kicker": f"Chapter {chapter_i:02d}",
                "text": _clean_title(note),
                "note": note,
            }
        ):
            chapter_i -= 1

    # Extra section chips on long screen windows (density for long cuts)
    chip_n = sum(1 for o in overlays if o["kind"] == "chip")
    for wi, (w0, w1) in enumerate(screen_wins):
        if chip_n >= caps["chip"]:
            break
        if (w1 - w0) < 90:
            continue
        # skip if opening chip already near this window
        if overlaps_any(w0, w0 + CHIP_HOLD, used_spans):
            continue
        rs, end = w0, min(w1, w0 + CHIP_HOLD)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        chip_n += 1
        label = f"Section {chip_n}"
        # pull label from overlapping EDL note if any
        for r in ranges:
            if float(r["end"]) > w0 and float(r["start"]) < w1:
                label = _clean_title(str(r.get("note") or label))[:40]
                break
        if not try_add(
            {
                "id": f"chip-sec-{wi+1:02d}",
                "kind": "chip",
                "start": rs,
                "end": max(rs + 0.8, end),
                "text": label,
                "note": "section chip on long screen window",
            }
        ):
            chip_n -= 1

    # --- diagrams from pipeline-ish notes (prefer screen) ---
    diagram_i = 0
    for r in ranges:
        if diagram_i >= caps["diagram"]:
            break
        note = str(r.get("note") or "")
        if not note or not DIAGRAM_NOTE_RE.search(note):
            continue
        rs, r_end = float(r["start"]), float(r["end"])
        end = min(r_end, rs + DIAGRAM_HOLD)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        # Prefer a screen window inside this range
        for w0, w1 in screen_wins:
            if overlap_sec(rs, r_end, w0, w1) >= min(DIAGRAM_HOLD, r_end - rs) * 0.5:
                rs = max(float(r["start"]), w0)
                end = min(w1, rs + DIAGRAM_HOLD)
                if words:
                    rs, end = snap_window_to_words(rs, end, words)
                break
        # If chapter already claimed the range head, slide diagram later in-range
        if overlaps_any(rs, end, used_spans) and (r_end - rs) > DIAGRAM_HOLD + CHAPTER_HOLD:
            rs = min(r_end - DIAGRAM_HOLD, rs + CHAPTER_HOLD + 0.5)
            end = min(r_end, rs + DIAGRAM_HOLD)
            if words:
                rs, end = snap_window_to_words(rs, end, words)
        parts = re.split(r"\s*[→>;|/]\s*|\s+-\s+", note)
        steps = [_clean_title(p) for p in parts if len(p.strip()) > 2][:4]
        if len(steps) < 2:
            steps = ["Setup", "Customize", "Seed data", "Ship"]
        diagram_i += 1
        if not try_add(
            {
                "id": f"diagram-{diagram_i:02d}",
                "kind": "diagram",
                "start": rs,
                "end": max(rs + 2.0, end),
                "title": _clean_title(note)[:40],
                "kicker": "Flow",
                "steps": steps,
                "text": "",
                "note": note,
            }
        ):
            diagram_i -= 1

    # --- emphasis from keyword words (sparse; close OK) ---
    if words:
        emph_n = 0
        min_gap = 12.0  # don't stack emphasis every keyword
        last_emph_end = -1e9
        for i, w in enumerate(words):
            if emph_n >= caps["emphasis"]:
                break
            if len(overlays) >= int(caps["target_total"]):
                break
            token = w["text"].lower().strip(".,!?;:\"'")
            if token not in EMPHASIS_WORDS:
                continue
            text, s, e = _phrase_around(words, i)
            if len(text) < 2:
                continue
            s = max(0.0, s - EMPHASIS_PAD)
            e = e + EMPHASIS_PAD
            s, e = snap_window_to_words(s, e, words)
            if s < last_emph_end + min_gap:
                continue
            if overlaps_any(s, e, used_spans):
                continue
            if not any(
                float(r["start"]) < e and float(r["end"]) > s
                for r in ranges
                if str(r.get("source") or "cam") == "cam"
            ):
                continue
            emph_n += 1
            if try_add(
                {
                    "id": f"emphasis-{emph_n:02d}",
                    "kind": "emphasis",
                    "start": s,
                    "end": max(s + 0.6, e),
                    "text": text,
                    "note": f"keyword:{token}",
                }
            ):
                last_emph_end = e
            else:
                emph_n -= 1

    overlays.sort(key=lambda o: float(o["start"]))
    framing_events.sort(key=lambda o: float(o["start"]))
    meta["counts"] = {
        "chapter": sum(1 for o in overlays if o["kind"] == "chapter"),
        "emphasis": sum(1 for o in overlays if o["kind"] == "emphasis"),
        "diagram": sum(1 for o in overlays if o["kind"] == "diagram"),
        "chip": sum(1 for o in overlays if o["kind"] == "chip"),
        "total": len(overlays),
        "framing_companions": len(framing_events),
        "on_screen": sum(1 for o in overlays if o.get("cover_mode") == "screen_with_cam"),
        "on_cam": sum(1 for o in overlays if o.get("cover_mode") == "full_cam"),
    }
    return {
        "overlays": overlays,
        "framing_events": framing_events,
        "_meta": meta,
    }


def merge_framing_into_events(
    existing: list[dict[str, Any]],
    framing_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace prior overlay:* framing notes; keep screen/punch/etc."""
    kept = [
        ev
        for ev in existing
        if not (
            str(ev.get("type") or "").lower() == "framing"
            and str(ev.get("note") or "").startswith("overlay:")
        )
    ]
    merged = kept + list(framing_events)
    merged.sort(key=lambda ev: float(ev.get("start", 0)))
    return merged


def write_overlay_suggest(episode: Path, suggestion: dict[str, Any]) -> Path:
    edit = episode / "edit"
    edit.mkdir(parents=True, exist_ok=True)
    out = edit / "overlays.suggest.json"
    out.write_text(json.dumps(suggestion, indent=2) + "\n", encoding="utf-8")
    return out
