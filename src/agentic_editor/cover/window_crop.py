"""Smart on-screen window detection for screen-explainer float layout.

Detects the actual window bbox (letterbox/pillarbox + optional browser chrome)
from pixel evidence — not fixed stage percentages.
"""

from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WindowCrop:
    """Pixel crop in source frame coordinates."""

    x: int
    y: int
    w: int
    h: int
    source_w: int
    source_h: int
    chrome_rows_scaled: int = 0
    ok: bool = True

    def as_normalized(self) -> dict[str, float]:
        sw = max(1, self.source_w)
        sh = max(1, self.source_h)
        return {
            "x": self.x / sw,
            "y": self.y / sh,
            "w": self.w / sw,
            "h": self.h / sh,
        }

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["normalized"] = self.as_normalized()
        return d


def _probe_size(path: Path) -> tuple[int, int]:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "csv=p=0",
            str(path),
        ],
        text=True,
    ).strip()
    w_s, h_s = out.split(",")
    return int(w_s), int(h_s)


def _grab_scaled_raw(
    path: Path,
    *,
    t_sec: float | None,
    max_w: int = 480,
) -> tuple[bytes, int, int, int, int]:
    w, h = _probe_size(path)
    sw = min(max_w, w)
    sh = max(1, round(h * sw / w))
    cmd = ["ffmpeg", "-v", "error"]
    if t_sec is not None and t_sec > 0:
        cmd += ["-ss", f"{t_sec:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-vf",
        f"scale={sw}:{sh}:flags=neighbor",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]
    buf = subprocess.check_output(cmd)
    expected = sw * sh * 3
    if len(buf) < expected:
        raise RuntimeError(f"short raw frame from {path} ({len(buf)} < {expected})")
    return buf[:expected], sw, sh, w, h


def _luma(r: int, g: int, b: int) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _median(vals: list[float]) -> float:
    a = sorted(vals)
    n = len(a)
    if n == 0:
        return 0.0
    mid = n // 2
    return a[mid] if n % 2 else (a[mid - 1] + a[mid]) / 2


def _edge_background(buf: bytes, sw: int, sh: int) -> tuple[float, float, float, float]:
    samples: list[tuple[float, float, float]] = []

    def push(x: int, y: int) -> None:
        i = (y * sw + x) * 3
        samples.append((buf[i], buf[i + 1], buf[i + 2]))

    for x in range(sw):
        for t in range(4):
            push(x, t)
            push(x, sh - 1 - t)
    for y in range(sh):
        for t in range(4):
            push(t, y)
            push(sw - 1 - t, y)
    br = _median([s[0] for s in samples])
    bg = _median([s[1] for s in samples])
    bb = _median([s[2] for s in samples])
    by = _median([_luma(*s) for s in samples])
    return br, bg, bb, by


def _is_content(r: int, g: int, b: int, bg: tuple[float, float, float, float]) -> bool:
    br, bgc, bb, by = bg
    y = _luma(r, g, b)
    dist = abs(r - br) + abs(g - bgc) + abs(b - bb)
    if by < 12:
        return y > by + 16 and (dist > 28 or y > 22)
    return dist > 22 or abs(y - by) > 16


def _project_bbox(mask: list[int], sw: int, sh: int) -> tuple[int, int, int, int]:
    col_hits = [0] * sw
    row_hits = [0] * sh
    for y in range(sh):
        for x in range(sw):
            if mask[y * sw + x]:
                col_hits[x] += 1
                row_hits[y] += 1
    max_col = max(col_hits) if col_hits else 1
    max_row = max(row_hits) if row_hits else 1
    min_col = max(4, int(max_col * 0.22))
    min_row = max(4, int(max_row * 0.22))
    left = 0
    while left < sw and col_hits[left] < min_col:
        left += 1
    right = sw - 1
    while right > left and col_hits[right] < min_col:
        right -= 1
    top = 0
    while top < sh and row_hits[top] < min_row:
        top += 1
    bottom = sh - 1
    while bottom > top and row_hits[bottom] < min_row:
        bottom -= 1
    if right <= left or bottom <= top:
        return 0, 0, sw - 1, sh - 1
    return left, top, right, bottom


def _mean_projections(buf: bytes, sw: int, sh: int) -> tuple[list[float], list[float]]:
    col = [0.0] * sw
    row = [0.0] * sh
    for y in range(sh):
        for x in range(sw):
            i = (y * sw + x) * 3
            yv = _luma(buf[i], buf[i + 1], buf[i + 2])
            col[x] += yv
            row[y] += yv
    col = [v / sh for v in col]
    row = [v / sw for v in row]
    return col, row


def _span_above(arr: list[float], thr: float) -> tuple[int, int]:
    a = 0
    while a < len(arr) and arr[a] < thr:
        a += 1
    b = len(arr) - 1
    while b > a and arr[b] < thr:
        b -= 1
    return a, b


def _row_edge_energy(buf: bytes, sw: int, y: int, x0: int, x1: int) -> float:
    e = 0.0
    n = 0
    for x in range(x0 + 1, x1 + 1):
        i0 = (y * sw + x - 1) * 3
        i1 = (y * sw + x) * 3
        y0 = _luma(buf[i0], buf[i0 + 1], buf[i0 + 2])
        y1 = _luma(buf[i1], buf[i1 + 1], buf[i1 + 2])
        e += abs(y1 - y0)
        n += 1
    return e / n if n else 0.0


def _detect_browser_chrome_top(
    buf: bytes, sw: int, sh: int, bbox: tuple[int, int, int, int]
) -> int:
    left, top, right, bottom = bbox
    h = bottom - top + 1
    w = right - left + 1
    if h < 40 or w < 80:
        return 0
    band = min(h * 22 // 100, sh * 18 // 100)
    energies = [
        _row_edge_energy(buf, sw, top + dy, left, right) for dy in range(band)
    ]
    body_start = min(h - 1, h * 40 // 100)
    body_end = min(h - 1, h * 60 // 100)
    body_vals = [
        _row_edge_energy(buf, sw, top + y, left, right)
        for y in range(body_start, body_end + 1)
    ]
    body_e = sum(body_vals) / len(body_vals) if body_vals else 0.0
    busy_thr = max(body_e * 1.8, body_e + 5, 6)
    calm_thr = max(body_e * 1.1, 1.8)

    busy_bands = 0
    in_busy = False
    calm_run = 0
    calm_start = 0
    saw_busy = False
    last_good = 0
    max_chrome = h * 20 // 100

    for dy, e in enumerate(energies):
        busy = e >= busy_thr
        if busy:
            if not in_busy:
                busy_bands += 1
                in_busy = True
            saw_busy = True
            calm_run = 0
            continue
        in_busy = False
        if not saw_busy:
            continue
        if e <= calm_thr:
            if calm_run == 0:
                calm_start = dy
            calm_run += 1
            if calm_run >= 6 and busy_bands >= 2:
                if 12 <= calm_start <= max_chrome:
                    last_good = calm_start
        else:
            calm_run = 0
    return last_good


def detect_window_crop(
    path: Path | str,
    *,
    t_sec: float | None = None,
    analysis_max_width: int = 480,
    chrome_side_inset_frac_max: float = 0.12,
    window_relative_pad: float = 0.003,
) -> WindowCrop:
    """Detect the on-screen window crop at optional timestamp ``t_sec``."""
    path = Path(path)
    buf, sw, sh, w, h = _grab_scaled_raw(
        path, t_sec=t_sec, max_w=analysis_max_width
    )
    bg = _edge_background(buf, sw, sh)
    mask = [0] * (sw * sh)
    for y in range(sh):
        for x in range(sw):
            i = (y * sw + x) * 3
            mask[y * sw + x] = (
                1 if _is_content(buf[i], buf[i + 1], buf[i + 2], bg) else 0
            )
    ml, mt, mr, mb = _project_bbox(mask, sw, sh)
    col, row = _mean_projections(buf, sw, sh)
    bg_floor = max(10.0, bg[3] + 10.0)
    ca, cb = _span_above(col, bg_floor)
    ra, rb = _span_above(row, bg_floor)
    left = max(ml, ca)
    right = min(mr, cb)
    top = max(mt, ra)
    bottom = min(mb, rb)
    if right <= left or bottom <= top:
        left, right, top, bottom = ca, cb, ra, rb

    side_inset = (left + (sw - 1 - right)) / max(1, sw)
    chrome = 0
    if side_inset < chrome_side_inset_frac_max:
        chrome = _detect_browser_chrome_top(buf, sw, sh, (left, top, right, bottom))

    sx = w / sw
    sy = h / sh
    pad_x = max(0, round((right - left) * window_relative_pad))
    pad_y = max(0, round((bottom - top) * window_relative_pad))
    x = int((left + pad_x) * sx)
    y = int((top + chrome + pad_y) * sy)
    cw = int((right - left + 1 - pad_x * 2) * sx)
    ch = int((bottom - (top + chrome) + 1 - pad_y * 2) * sy)

    x = max(0, min(w - 2, x))
    y = max(0, min(h - 2, y))
    cw = min(w - x, cw)
    ch = min(h - y, ch)
    if cw % 2:
        cw -= 1
    if ch % 2:
        ch -= 1
    cw = max(2, cw)
    ch = max(2, ch)

    ok = cw >= w * 0.35 and ch >= h * 0.35
    if not ok:
        return WindowCrop(0, 0, w - (w % 2), h - (h % 2), w, h, chrome, False)
    return WindowCrop(x, y, cw, ch, w, h, chrome, True)


def detect_window_crop_stable(
    path: Path | str,
    *,
    sample_times: list[float] | None = None,
    **kwargs: Any,
) -> WindowCrop:
    """Sample a few timestamps and pick the median crop (stable window)."""
    path = Path(path)
    if sample_times is None:
        # Probe duration for relative samples
        try:
            dur_s = subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=nw=1:nk=1",
                    str(path),
                ],
                text=True,
            ).strip()
            dur = max(1.0, float(dur_s))
        except (subprocess.CalledProcessError, ValueError):
            dur = 10.0
        sample_times = [dur * 0.15, dur * 0.5, dur * 0.85]

    crops = [detect_window_crop(path, t_sec=t, **kwargs) for t in sample_times]
    ok_crops = [c for c in crops if c.ok] or crops
    xs = sorted(c.x for c in ok_crops)
    ys = sorted(c.y for c in ok_crops)
    ws = sorted(c.w for c in ok_crops)
    hs = sorted(c.h for c in ok_crops)
    mid = len(ok_crops) // 2
    rep = ok_crops[mid]
    return WindowCrop(
        xs[mid],
        ys[mid],
        ws[mid],
        hs[mid],
        rep.source_w,
        rep.source_h,
        rep.chrome_rows_scaled,
        True,
    )
