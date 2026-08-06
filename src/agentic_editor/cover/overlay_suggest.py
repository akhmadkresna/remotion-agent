"""Suggest sparse A-roll MG overlays (chapter / emphasis / diagram / chip).

Default logic couples overlays to cover mode + camera_play framing so MG
does not fight close talking-head zooms (safe zones: left_third, faceClear).

Density / relevance (framework defaults):
  1. Reserve structure budget (chip/chapter/diagram) before emphasis fill
  2. Section quotas on long screen windows + min gaps
  3. ID payoff lexicon + short-phrase cleaner (not raw EDL notes / filler ASR)
  4. Score emphasis by screen-enter proximity + payoff hits (best-fit, not first-fit)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from agentic_editor.cover.style_load import load_overlays
from agentic_editor.cover.suggest import load_cam_words, snap_window_to_words
from agentic_editor.editor.edl import load_edl
from agentic_editor.project import load_project

CHAPTER_NOTE_RE = re.compile(
    r"(hook|chapter|lesson|fase|phase|section|reset|intro|outro|setup|bab)",
    re.I,
)
DIAGRAM_NOTE_RE = re.compile(r"(pipeline|flow|step|langkah|fase|phase|alur)", re.I)

SCREEN_EVENT_TYPES = frozenset(
    {"screen_with_cam", "cam_pip", "screen", "screen_full"}
)

# Holds (seconds) — long enough to read; OverlayLayer also fades out
EMPHASIS_PAD = 0.12
EMPHASIS_MIN_HOLD = 2.4
CHAPTER_HOLD = 5.0
CHIP_HOLD = 4.0
DIAGRAM_HOLD = 7.5

# Spacing / density
SEC_PER_OVERLAY = 70.0  # denser than 90s for long tutorials
CHAPTER_MIN_GAP = 90.0
EMPHASIS_MIN_GAP = 25.0
SECTION_QUOTA_SEC = 120.0  # long screen window → ensure entry MG
SCREEN_ENTER_BOOST_SEC = 8.0

# Remap drops tiny slices; suggest must never emit below this
OVERLAY_MIN_SEC = 1.8

FACE_HEAVY_KINDS = frozenset({"chapter", "diagram"})
CHIP_PREFERS_MEDIUM = True

# Filler tokens rejected in emphasis phrases
FILLER = frozenset(
    {
        "ini",
        "itu",
        "ya",
        "yah",
        "guys",
        "oke",
        "ok",
        "nah",
        "dan",
        "atau",
        "yang",
        "di",
        "ke",
        "dari",
        "juga",
        "sih",
        "dong",
        "lah",
        "nih",
        "the",
        "a",
        "an",
        "of",
        "to",
        "for",
    }
)

# Multi-word first, then singles — display label is curated
PAYOFF_PHRASES: list[tuple[str, str]] = [
    ("odoo studio", "Odoo Studio"),
    ("satu app", "Satu App"),
    ("one app", "Satu App"),
    ("free app", "Satu App"),
    ("kartu stok", "Kartu Stok"),
    ("kartu stock", "Kartu Stok"),
    ("master data", "Master Data"),
    ("res partner", "res.partner"),
    ("diterima", "Diterima"),
    ("chatter", "Chatter"),
    ("tracking", "Tracking"),
    ("otomatis", "Otomatis"),
    ("otomatisasi", "Otomatis"),
    ("pembelian", "Pembelian"),
    ("penjualan", "Penjualan"),
    ("kategori", "Kategori"),
    ("produk", "Produk"),
    ("gambar", "Gambar"),
    ("stok", "Stok"),
    ("stock", "Stok"),
    ("studio", "Studio"),
    ("roadmap", "Roadmap"),
    ("bug", "Bug"),
    ("status", "Status"),
    ("confirm", "Confirm"),
    ("validate", "Validate"),
]

# Map messy EDL notes → short chapter/chip labels
NOTE_LABEL_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"hook|lanjut|continue|plan|roadmap", re.I), "Lanjut Toko Material"),
    (re.compile(r"one.?app|free app|from scratch", re.I), "Satu App"),
    (re.compile(r"not only|usaha|toko listrik", re.I), "Bukan Cuma Toko Material"),
    (re.compile(r"phase\s*3|kartu\s*stok|kartu\s*stock|stock card", re.I), "Kartu Stok"),
    (
        re.compile(r"purchase demo|pembelian|\bbug\b|diterima|status button", re.I),
        "Pembelian",
    ),
    (re.compile(r"chatter|tracking|restrict|proteksi", re.I), "Proteksi Data"),
    (re.compile(r"outro|cta|\bnext\b|penjualan|\bpos\b|subscribe", re.I), "Next"),
    (
        re.compile(r"master|phase\s*1|partner|kategori|seed", re.I),
        "Master Data",
    ),
    (re.compile(r"gambar|produk", re.I), "Produk"),
]


def _norm_token(text: str) -> str:
    return re.sub(r"[^\w]+", "", text.lower(), flags=re.UNICODE)


def short_label(note: str, *, fallback: str | None = None) -> str:
    """Prefer curated short labels over dumping full EDL notes."""
    raw = (note or "").strip()
    if not raw:
        return fallback or "Section"
    for pat, label in NOTE_LABEL_RULES:
        if pat.search(raw):
            return label
    t = re.sub(r"[_\-]+", " ", raw)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(
        r"^(hook|chapter|lesson|fase|phase|section|reset|intro|outro|setup|bab)\s*[:\-]?\s*",
        "",
        t,
        flags=re.I,
    )
    # keep first clause only
    t = re.split(r"\s*[+|•]\s*|\s+→\s*", t)[0].strip()
    if len(t) > 40:
        t = t[:37].rstrip() + "…"
    return t or (fallback or "Section")


# Back-compat alias used by older tests / callers
def _clean_title(note: str) -> str:
    return short_label(note)


def caps_for_duration(keep_sec: float) -> dict[str, int]:
    """Scale overlay budgets; structure reserved before emphasis fill."""
    factor = max(1.0, float(keep_sec) / 600.0)  # 1.0 at ~10 min
    target = max(8, int(round(float(keep_sec) / SEC_PER_OVERLAY)))
    chapter = min(10, max(3, int(round(4 * factor))))
    diagram = min(4, max(1, int(round(2 * factor))))
    chip = min(4, 1 + (1 if keep_sec >= 900 else 0) + (1 if keep_sec >= 1500 else 0))
    structure = chapter + diagram + chip
    emphasis = max(4, min(16, target - structure + 2))  # leftover + small flex
    return {
        "chapter": chapter,
        "emphasis": emphasis,
        "diagram": diagram,
        "chip": chip,
        "structure_reserve": structure,
        "target_total": max(target, structure + 4),
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


def min_gap_ok(
    start: float,
    kind_spans: list[tuple[float, float]],
    *,
    min_gap: float,
) -> bool:
    """Require start to be at least min_gap from any prior span start."""
    for a, _b in kind_spans:
        if abs(start - a) < min_gap:
            return False
    return True


def companion_framing_event(
    *,
    kind: str,
    start: float,
    end: float,
    on_screen: bool,
    ov_id: str,
) -> dict[str, Any] | None:
    """Full-cam chapter/diagram/chip get medium/wide framing companions."""
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


def _in_edl(ranges: list[dict[str, Any]], s: float, e: float) -> bool:
    return any(
        float(r["start"]) < e and float(r["end"]) > s
        for r in ranges
        if str(r.get("source") or "cam") == "cam"
    )


def get_dwell_holds(style_name: str = "tutorial") -> dict[str, float]:
    """Resolve per-kind dwell from style pack ``overlays.dwell``."""
    ov = load_overlays(style_name)
    dwell = ov.get("dwell") if isinstance(ov.get("dwell"), dict) else {}
    return {
        "emphasis": float(dwell.get("emphasis_sec", EMPHASIS_MIN_HOLD)),
        "chip": float(dwell.get("chip_sec", CHIP_HOLD)),
        "chapter": float(dwell.get("chapter_sec", CHAPTER_HOLD)),
        "diagram": float(dwell.get("diagram_sec", DIAGRAM_HOLD)),
        "min": float(dwell.get("min_sec", OVERLAY_MIN_SEC)),
    }


def ensure_overlay_dwell(
    start: float,
    end: float,
    *,
    kind: str,
    edl_ranges: list[dict[str, Any]] | None = None,
    holds: dict[str, float] | None = None,
) -> tuple[float, float]:
    """Force readable on-screen time; overlays used to vanish in ~1s."""
    h = holds or {
        "emphasis": EMPHASIS_MIN_HOLD,
        "chip": CHIP_HOLD,
        "chapter": CHAPTER_HOLD,
        "diagram": DIAGRAM_HOLD,
        "min": OVERLAY_MIN_SEC,
    }
    floor = float(h.get("min", OVERLAY_MIN_SEC))
    min_hold = max(float(h.get(kind, floor)), floor)
    s, e = float(start), float(end)
    if e - s < min_hold:
        e = s + min_hold
    # Clamp to an overlapping EDL keep range when possible
    if edl_ranges:
        for r in edl_ranges:
            if str(r.get("source") or "cam") != "cam":
                continue
            rs, re = float(r["start"]), float(r["end"])
            if re <= s or rs >= e:
                continue
            e = min(e, re)
            if e - s < floor and re - rs >= floor:
                e = min(re, s + min_hold)
            break
    if e <= s:
        e = s + floor
    return s, e


def _note_for_window(
    ranges: list[dict[str, Any]], w0: float, w1: float
) -> str:
    for r in ranges:
        if float(r["end"]) > w0 and float(r["start"]) < w1:
            return str(r.get("note") or r.get("beat") or "")
    return ""


def find_payoff_hits(
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return curated emphasis candidates from payoff lexicon (best-fit pool)."""
    if not words:
        return []
    texts = [str(w.get("text") or "") for w in words]
    lower = [t.lower() for t in texts]
    joined_norm = [" ".join(lower[i : i + 4]) for i in range(len(lower))]
    hits: list[dict[str, Any]] = []
    used_i: set[int] = set()

    for phrase, label in PAYOFF_PHRASES:
        parts = phrase.split()
        n = len(parts)
        for i in range(len(words) - n + 1):
            if any(j in used_i for j in range(i, i + n)):
                continue
            window = " ".join(lower[i : i + n])
            # allow light punctuation in tokens
            window_cmp = re.sub(r"[^\w\s]+", "", window)
            phrase_cmp = re.sub(r"[^\w\s]+", "", phrase)
            if window_cmp != phrase_cmp and not window_cmp.startswith(phrase_cmp):
                # also try token-normalized equality
                if [_norm_token(x) for x in lower[i : i + n]] != [
                    _norm_token(x) for x in parts
                ]:
                    continue
            # reject if surrounding filler-only expansion
            chunk = texts[i : i + n]
            if any(_norm_token(c) in FILLER for c in chunk):
                # single payoff tokens like "stok" are fine; filler check is for extras
                if n > 1:
                    continue
            s = float(words[i]["start"])
            e = float(words[i + n - 1]["end"])
            hits.append(
                {
                    "text": label,
                    "start": s,
                    "end": e,
                    "phrase": phrase,
                    "index": i,
                }
            )
            used_i.update(range(i, i + n))
    return hits


def score_emphasis(
    hit: dict[str, Any],
    *,
    screen_wins: list[tuple[float, float]],
) -> float:
    """Higher = more relevant. Screen-enter + payoff order matter."""
    s = float(hit["start"])
    e = float(hit["end"])
    score = 1.0
    # Payoff list order ≈ priority (earlier phrases slightly higher)
    phrase = str(hit.get("phrase") or "")
    for rank, (p, _) in enumerate(PAYOFF_PHRASES):
        if p == phrase:
            score += max(0.0, 3.0 - rank * 0.05)
            break
    # Boost near start of a screen_with_cam window (UI enter)
    for w0, w1 in screen_wins:
        if w0 <= s <= w1:
            if s - w0 <= SCREEN_ENTER_BOOST_SEC:
                score += 4.0 * (1.0 - (s - w0) / SCREEN_ENTER_BOOST_SEC)
            else:
                score += 0.5  # still on-screen
            break
    else:
        # full-cam payoff still useful but lower
        score += 0.25
    # Prefer slightly longer hold words
    score += min(1.0, (e - s))
    return score


def suggest_overlays(episode: Path) -> dict[str, Any]:
    """
    Draft overlay creatives in *source (cam) time*, gated by cover + framing.

    Structure first (chip/chapter/diagram + section quotas), then best-fit emphasis.
    """
    episode = episode.resolve()
    cfg = load_project(episode)
    style_name = str(cfg.get("style") or "tutorial")
    holds = get_dwell_holds(style_name)
    chip_hold = holds["chip"]
    chapter_hold = holds["chapter"]
    diagram_hold = holds["diagram"]
    emphasis_hold = holds["emphasis"]
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
    chapter_spans: list[tuple[float, float]] = []
    emphasis_spans: list[tuple[float, float]] = []

    meta: dict[str, Any] = {
        "word_count": len(words),
        "range_count": len(ranges),
        "keep_sec": round(keep_sec, 1),
        "style": style_name,
        "preset": "bold_mist",
        "has_cover": bool(cover),
        "screen_event_windows": len(screen_wins),
        "camera_play": {
            "home": camera_play.get("home", "medium"),
            "alt": camera_play.get("alt", "close"),
            "snap_on_cuts": camera_play.get("snap_on_cuts", True),
        },
        "caps": caps,
        "dwell": holds,
        "rules": {
            "chapter_diagram": "prefer screen_with_cam; else emit framing medium/wide",
            "chip": "prefer medium framing on full cam",
            "emphasis": "close OK; scored by payoff lexicon + screen-enter",
            "structure_first": True,
            "chapter_min_gap_sec": CHAPTER_MIN_GAP,
            "emphasis_min_gap_sec": EMPHASIS_MIN_GAP,
            "section_quota_sec": SECTION_QUOTA_SEC,
            "safe_zones": ["left_third", "lower_third"],
            "faceClear": True,
            "dwell_readable": True,
        },
    }

    def kind_count(kind: str) -> int:
        return sum(1 for o in overlays if o["kind"] == kind)

    def try_add(ov: dict[str, Any], *, structural: bool) -> bool:
        nonlocal overlays, framing_events, used_spans, chapter_spans, emphasis_spans
        kind = str(ov["kind"])
        s, e = ensure_overlay_dwell(
            float(ov["start"]),
            float(ov["end"]),
            kind=kind,
            edl_ranges=ranges,
            holds=holds,
        )
        ov = {**ov, "start": round(s, 3), "end": round(e, 3)}

        if structural:
            # Structure may use reserved slots even before emphasis fill
            if kind == "chapter" and kind_count("chapter") >= caps["chapter"]:
                return False
            if kind == "diagram" and kind_count("diagram") >= caps["diagram"]:
                return False
            if kind == "chip" and kind_count("chip") >= caps["chip"]:
                return False
            if kind == "chapter" and not min_gap_ok(
                s, chapter_spans, min_gap=CHAPTER_MIN_GAP
            ):
                return False
        else:
            # Emphasis only after structure; respect remaining total + emphasis cap
            struct_n = sum(
                1 for o in overlays if o["kind"] in {"chip", "chapter", "diagram"}
            )
            emph_n = kind_count("emphasis")
            if emph_n >= caps["emphasis"]:
                return False
            if struct_n + emph_n >= caps["target_total"]:
                return False
            if not min_gap_ok(s, emphasis_spans, min_gap=EMPHASIS_MIN_GAP):
                return False

        if overlaps_any(s, e, used_spans):
            return False
        if not _in_edl(ranges, s, e):
            return False

        on_screen = is_mostly_screen(s, e, screen_wins)
        framing_ev = companion_framing_event(
            kind=kind,
            start=s,
            end=e,
            on_screen=on_screen,
            ov_id=str(ov.get("id") or kind),
        )
        ov = _annotate(ov, on_screen=on_screen, framing_ev=framing_ev)
        overlays.append(ov)
        used_spans.append((s, e))
        if framing_ev:
            framing_events.append(framing_ev)
        if kind == "chapter":
            chapter_spans.append((s, e))
        if kind == "emphasis":
            emphasis_spans.append((s, e))
        return True

    # ---------- STRUCTURE PHASE ----------
    # 1) Opening chip
    if ranges and caps["chip"] > 0:
        r0 = ranges[0]
        rs, r_end = float(r0["start"]), float(r0["end"])
        end = min(r_end, rs + chip_hold)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        title = short_label(
            str(cfg.get("id") or episode.name).replace("-", " ").replace("_", " "),
            fallback="Episode",
        )
        # Prefer brand-ish chip from id tokens
        if "studio" in title.lower() or "odoo" in title.lower():
            chip_text = "Odoo Studio"
        else:
            chip_text = title
        try_add(
            {
                "id": "chip-open",
                "kind": "chip",
                "start": rs,
                "end": max(rs + 0.8, end),
                "text": chip_text,
                "note": "opening chip",
            },
            structural=True,
        )

    # 2) Chapters from EDL notes (curated labels + gap)
    chapter_i = 0
    for r in ranges:
        if kind_count("chapter") >= caps["chapter"]:
            break
        note = str(r.get("note") or r.get("beat") or "")
        if not note or not CHAPTER_NOTE_RE.search(note):
            continue
        rs, r_end = float(r["start"]), float(r["end"])
        end = min(r_end, rs + chapter_hold)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        if screen_wins and not is_mostly_screen(rs, end, screen_wins):
            for w0, w1 in screen_wins:
                if overlap_sec(rs, r_end, w0, w1) >= chapter_hold * 0.8:
                    rs = max(rs, w0)
                    end = min(w1, rs + chapter_hold)
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
                "kicker": f"Bab {chapter_i:02d}",
                "text": short_label(note),
                "note": note,
            },
            structural=True,
        ):
            chapter_i -= 1

    # 3) Section quota — long screen windows get entry chapter/chip
    for wi, (w0, w1) in enumerate(screen_wins):
        if (w1 - w0) < SECTION_QUOTA_SEC:
            continue
        head_end = min(w1, w0 + chapter_hold)
        if overlaps_any(w0, head_end, used_spans):
            continue  # already have MG at enter
        note = _note_for_window(ranges, w0, w1)
        label = short_label(note, fallback=f"Section {wi + 1}")
        rs, end = w0, head_end
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        # Prefer chapter if budget; else chip
        if kind_count("chapter") < caps["chapter"] and min_gap_ok(
            rs, chapter_spans, min_gap=CHAPTER_MIN_GAP
        ):
            chapter_i = kind_count("chapter") + 1
            try_add(
                {
                    "id": f"chapter-sec-{wi+1:02d}",
                    "kind": "chapter",
                    "start": rs,
                    "end": max(rs + 1.2, end),
                    "kicker": f"Bab {chapter_i:02d}",
                    "text": label,
                    "note": f"section quota screen@{w0:.0f}",
                },
                structural=True,
            )
        elif kind_count("chip") < caps["chip"]:
            try_add(
                {
                    "id": f"chip-sec-{wi+1:02d}",
                    "kind": "chip",
                    "start": rs,
                    "end": max(rs + 0.8, min(end, rs + chip_hold)),
                    "text": label,
                    "note": f"section quota chip screen@{w0:.0f}",
                },
                structural=True,
            )

    # 4) Diagrams (prefer screen; slide past chapter head)
    diagram_i = 0
    for r in ranges:
        if kind_count("diagram") >= caps["diagram"]:
            break
        note = str(r.get("note") or "")
        if not note or not DIAGRAM_NOTE_RE.search(note):
            continue
        rs, r_end = float(r["start"]), float(r["end"])
        end = min(r_end, rs + diagram_hold)
        if words:
            rs, end = snap_window_to_words(rs, end, words)
        for w0, w1 in screen_wins:
            if overlap_sec(rs, r_end, w0, w1) >= min(diagram_hold, r_end - rs) * 0.5:
                rs = max(float(r["start"]), w0)
                end = min(w1, rs + diagram_hold)
                if words:
                    rs, end = snap_window_to_words(rs, end, words)
                break
        if overlaps_any(rs, end, used_spans) and (r_end - rs) > diagram_hold + chapter_hold:
            rs = min(r_end - diagram_hold, rs + chapter_hold + 0.5)
            end = min(r_end, rs + diagram_hold)
            if words:
                rs, end = snap_window_to_words(rs, end, words)
        # Curated default steps for tutorial material apps
        steps = ["Master data", "Produk + gambar", "Kartu stok", "Pembelian"]
        if re.search(r"partner|kategori|seed", note, re.I):
            steps = ["res.partner", "Seed kategori", "Gambar produk", "Kartu stok"]
        diagram_i += 1
        if not try_add(
            {
                "id": f"diagram-{diagram_i:02d}",
                "kind": "diagram",
                "start": rs,
                "end": max(rs + 2.0, end),
                "title": short_label(note, fallback="Toko Material")[:40],
                "kicker": "Alur",
                "steps": steps,
                "text": "",
                "note": note,
            },
            structural=True,
        ):
            diagram_i -= 1

    structure_n = sum(
        1 for o in overlays if o["kind"] in {"chip", "chapter", "diagram"}
    )

    # ---------- EMPHASIS PHASE (best-fit) ----------
    candidates: list[dict[str, Any]] = []
    for hit in find_payoff_hits(words):
        s = max(0.0, float(hit["start"]) - EMPHASIS_PAD)
        e = float(hit["end"]) + EMPHASIS_PAD
        if words:
            s, e = snap_window_to_words(s, e, words)
        if overlaps_any(s, e, used_spans):
            continue
        if not _in_edl(ranges, s, e):
            continue
        sc = score_emphasis(hit, screen_wins=screen_wins)
        candidates.append(
            {
                "text": hit["text"],
                "start": s,
                "end": max(s + emphasis_hold, e),
                "score": sc,
                "phrase": hit.get("phrase"),
            }
        )
    candidates.sort(key=lambda c: (-float(c["score"]), float(c["start"])))

    emph_n = 0
    for cand in candidates:
        if emph_n >= caps["emphasis"]:
            break
        if structure_n + emph_n >= caps["target_total"]:
            break
        emph_n += 1
        if try_add(
            {
                "id": f"emphasis-{emph_n:02d}",
                "kind": "emphasis",
                "start": cand["start"],
                "end": cand["end"],
                "text": cand["text"],
                "note": f"payoff:{cand.get('phrase')} score={cand['score']:.2f}",
                "score": round(float(cand["score"]), 3),
            },
            structural=False,
        ):
            pass
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
        "structure": structure_n,
        "emphasis_candidates": len(candidates),
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
