"""Smart on-screen window detection for screen-explainer float layout.

Finds the floating app window from pixel evidence — not fixed stage percentages.

Handles OBS / display-capture frames shaped like::

    [wallpaper][black pillar][dark UI window][black pillar][wallpaper]
                              ^-- crop this --^

Black pillars are near-uniform dark; the UI has higher luma variance; wallpaper
is bright. Chrome/tab trimming is optional and conservative.
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
    max_w: int = 960,
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
        f"scale={sw}:{sh}:flags=bilinear",
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


def _col_row_stats(
    buf: bytes, sw: int, sh: int, *, dark_thr: float = 55.0
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    col_sum = [0.0] * sw
    col_sq = [0.0] * sw
    col_dark = [0] * sw
    row_sum = [0.0] * sh
    row_dark = [0] * sh
    for y in range(sh):
        for x in range(sw):
            i = (y * sw + x) * 3
            yv = _luma(buf[i], buf[i + 1], buf[i + 2])
            col_sum[x] += yv
            col_sq[x] += yv * yv
            row_sum[y] += yv
            if yv < dark_thr:
                col_dark[x] += 1
                row_dark[y] += 1
    col_mean = [s / sh for s in col_sum]
    col_var = [max(0.0, col_sq[x] / sh - col_mean[x] ** 2) for x in range(sw)]
    col_df = [c / sh for c in col_dark]
    row_mean = [s / sw for s in row_sum]
    row_df = [c / sw for c in row_dark]
    return col_mean, col_var, col_df, row_mean, row_df


def _longest_run(flags: list[bool]) -> tuple[int, int, int]:
    """Return (start, end, length) of longest True run; end inclusive."""
    best_a, best_b, best_n = 0, -1, 0
    i = 0
    n = len(flags)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and flags[j + 1]:
            j += 1
        length = j - i + 1
        if length > best_n:
            best_a, best_b, best_n = i, j, length
        i = j + 1
    return best_a, best_b, best_n


def _classify_columns(
    col_mean: list[float], col_var: list[float]
) -> list[str]:
    """Label each column: wallpaper | black | ui | other."""
    labels: list[str] = []
    for m, v in zip(col_mean, col_var, strict=True):
        # True letterbox/pillar only — very dark AND flat (not dark UI chrome).
        if m <= 8.0 and v <= 100.0:
            labels.append("black")
        elif m >= 80.0:
            labels.append("wallpaper")
        elif v >= 100.0 and m <= 95.0:
            labels.append("ui")
        elif 8.0 < m <= 60.0:
            # Dark UI / sidebar (may be flatter than content).
            labels.append("ui")
        else:
            labels.append("other")
    return labels


def _merge_close_runs(
    runs: list[tuple[int, int]], *, max_gap: int
) -> list[tuple[int, int]]:
    if not runs:
        return []
    runs = sorted(runs)
    out = [runs[0]]
    for a, b in runs[1:]:
        pa, pb = out[-1]
        if a - pb - 1 <= max_gap:
            out[-1] = (pa, max(pb, b))
        else:
            out.append((a, b))
    return out


def _find_ui_span_from_labels(
    labels: list[str],
    col_mean: list[float],
    col_var: list[float],
) -> tuple[int, int]:
    """Window sits between true black pillars, inside outer wallpaper."""
    n = len(labels)

    # Outer wallpaper strips.
    left = 0
    while left < n and labels[left] == "wallpaper":
        left += 1
    right = n - 1
    while right > left and labels[right] == "wallpaper":
        right -= 1

    # Black pillar runs inside the desk region (strict + merge speckles).
    black_runs: list[tuple[int, int]] = []
    i = left
    while i <= right:
        if not (col_mean[i] <= 8.0 and col_var[i] <= 100.0):
            i += 1
            continue
        j = i
        while j + 1 <= right and col_mean[j + 1] <= 8.0 and col_var[j + 1] <= 100.0:
            j += 1
        black_runs.append((i, j))
        i = j + 1
    black_runs = _merge_close_runs(black_runs, max_gap=6)
    # Keep pillars that are meaningfully wide.
    black_runs = [r for r in black_runs if r[1] - r[0] + 1 >= 10]

    if len(black_runs) >= 2:
        left_pillar = black_runs[0]
        right_pillar = black_runs[-1]
        wl = left_pillar[1] + 1
        wr = right_pillar[0] - 1
        if wr - wl >= max(12, int(n * 0.18)):
            return wl, wr

    # Fallback: longest UI run, merging small gaps so sidebar+content stay one span.
    ui_flags = [lab in ("ui", "other") and col_mean[i] < 90 for i, lab in enumerate(labels)]
    # Zero out outer wallpaper / deep pillars.
    for i in range(0, left):
        ui_flags[i] = False
    for i in range(right + 1, n):
        ui_flags[i] = False
    for a, b in black_runs:
        for i in range(a, b + 1):
            ui_flags[i] = False

    # Merge gaps: treat short False gaps between True as True.
    gap = max(3, n // 80)
    i = 0
    while i < n:
        if ui_flags[i]:
            i += 1
            continue
        # look for False run that is a small hole between UI
        j = i
        while j + 1 < n and not ui_flags[j + 1]:
            j += 1
        left_ui = i > 0 and ui_flags[i - 1]
        right_ui = j + 1 < n and ui_flags[j + 1]
        if left_ui and right_ui and (j - i + 1) <= gap:
            for k in range(i, j + 1):
                ui_flags[k] = True
        i = j + 1

    a, b, ln = _longest_run(ui_flags)
    if ln >= max(12, int(n * 0.2)):
        return a, b
    return left, right


def _row_stats_in_x(
    buf: bytes, sw: int, sh: int, x0: int, x1: int
) -> tuple[list[float], list[float]]:
    span = max(1, x1 - x0 + 1)
    means = [0.0] * sh
    var = [0.0] * sh
    for y in range(sh):
        s = 0.0
        sq = 0.0
        for x in range(x0, x1 + 1):
            i = (y * sw + x) * 3
            yv = _luma(buf[i], buf[i + 1], buf[i + 2])
            s += yv
            sq += yv * yv
        m = s / span
        means[y] = m
        var[y] = max(0.0, sq / span - m * m)
    return means, var


def _find_ui_rows(
    row_mean: list[float], row_var: list[float]
) -> tuple[int, int]:
    """UI rows between top letterbox and the black gap above the taskbar."""
    sh = len(row_mean)

    top = 0
    while top < sh and row_mean[top] <= 12.0 and row_var[top] <= 120.0:
        top += 1

    # First sustained near-zero black gap in the lower half = void under the window.
    # (Do NOT treat dark UI gradients ~luma 5–12 as gaps — Odoo/Edge pages fade that way.)
    gap_flags = [
        row_mean[y] <= 2.0 and row_var[y] <= 15.0 for y in range(sh)
    ]
    bot = sh - 1
    i = max(top + 5, sh // 2)
    found_gap = False
    while i < sh:
        if not gap_flags[i]:
            i += 1
            continue
        j = i
        while j + 1 < sh and gap_flags[j + 1]:
            j += 1
        if j - i + 1 >= 3:
            bot = i - 1
            found_gap = True
            break
        i = j + 1

    if not found_gap:
        # Trim busy taskbar from the bottom.
        bot = sh - 1
        guard = max(top + 5, int(sh * 0.75))
        while bot > guard and (
            row_var[bot] >= 150.0
            or (row_mean[bot] >= 28.0 and row_var[bot] >= 60.0)
        ):
            bot -= 1
        while bot > top and row_mean[bot] <= 2.0 and row_var[bot] <= 15.0:
            bot -= 1

    if bot - top < max(10, int(sh * 0.3)):
        flags = [
            (row_var[y] >= 80.0 and 8.0 < row_mean[y] <= 100.0)
            or (12.0 < row_mean[y] <= 70.0)
            for y in range(sh)
        ]
        a, b, ln = _longest_run(flags)
        if ln >= max(10, int(sh * 0.25)):
            return a, b
    return top, max(top + 10, bot)


def _snap_vertical_edge(
    buf: bytes,
    sw: int,
    sh: int,
    *,
    x_guess: int,
    y0: int,
    y1: int,
    search_left: int,
    search_right: int,
    want_dark_on_right: bool,
) -> int:
    y0 = max(0, min(sh - 1, y0))
    y1 = max(y0, min(sh - 1, y1))
    best_x = x_guess
    best_e = -1.0
    lo = max(1, x_guess - search_left)
    hi = min(sw - 2, x_guess + search_right)
    for x in range(lo, hi + 1):
        e = 0.0
        n = 0
        for y in range(y0, y1 + 1, 2):
            i0 = (y * sw + x - 1) * 3
            i1 = (y * sw + x + 1) * 3
            e += abs(
                _luma(buf[i0], buf[i0 + 1], buf[i0 + 2])
                - _luma(buf[i1], buf[i1 + 1], buf[i1 + 2])
            )
            n += 1
        e = e / n if n else 0.0
        mid = (y0 + y1) // 2
        i_l = (mid * sw + max(0, x - 4)) * 3
        i_r = (mid * sw + min(sw - 1, x + 4)) * 3
        yl = _luma(buf[i_l], buf[i_l + 1], buf[i_l + 2])
        yr = _luma(buf[i_r], buf[i_r + 1], buf[i_r + 2])
        if want_dark_on_right and yr > yl + 12:
            e *= 0.35
        if (not want_dark_on_right) and yl > yr + 12:
            e *= 0.35
        if e > best_e:
            best_e = e
            best_x = x
    return best_x


def _snap_horizontal_edge(
    buf: bytes,
    sw: int,
    sh: int,
    *,
    y_guess: int,
    x0: int,
    x1: int,
    search_up: int,
    search_down: int,
) -> int:
    x0 = max(0, min(sw - 1, x0))
    x1 = max(x0, min(sw - 1, x1))
    best_y = y_guess
    best_e = -1.0
    lo = max(1, y_guess - search_up)
    hi = min(sh - 2, y_guess + search_down)
    for y in range(lo, hi + 1):
        e = 0.0
        n = 0
        for x in range(x0, x1 + 1, 2):
            i0 = ((y - 1) * sw + x) * 3
            i1 = ((y + 1) * sw + x) * 3
            e += abs(
                _luma(buf[i0], buf[i0 + 1], buf[i0 + 2])
                - _luma(buf[i1], buf[i1 + 1], buf[i1 + 2])
            )
            n += 1
        e = e / n if n else 0.0
        if e > best_e:
            best_e = e
            best_y = y
    return best_y


def _row_edge_energy(buf: bytes, sw: int, y: int, x0: int, x1: int) -> float:
    e = 0.0
    n = 0
    for x in range(x0 + 1, x1 + 1):
        i0 = (y * sw + x - 1) * 3
        i1 = (y * sw + x) * 3
        e += abs(
            _luma(buf[i0], buf[i0 + 1], buf[i0 + 2])
            - _luma(buf[i1], buf[i1 + 1], buf[i1 + 2])
        )
        n += 1
    return e / n if n else 0.0


def _detect_browser_chrome_top(
    buf: bytes, sw: int, sh: int, bbox: tuple[int, int, int, int]
) -> int:
    left, top, right, bottom = bbox
    h = bottom - top + 1
    w = right - left + 1
    if h < 80 or w < 120:
        return 0
    band = min(h * 18 // 100, sh * 14 // 100)
    energies = [
        _row_edge_energy(buf, sw, top + dy, left, right) for dy in range(max(1, band))
    ]
    body_start = min(h - 1, h * 40 // 100)
    body_end = min(h - 1, h * 60 // 100)
    body_vals = [
        _row_edge_energy(buf, sw, top + y, left, right)
        for y in range(body_start, body_end + 1)
    ]
    body_e = sum(body_vals) / len(body_vals) if body_vals else 0.0
    busy_thr = max(body_e * 2.2, body_e + 8, 10)
    busy_bands = 0
    in_busy = False
    for e in energies:
        busy = e >= busy_thr
        if busy and not in_busy:
            busy_bands += 1
            in_busy = True
        elif not busy:
            in_busy = False
    if busy_bands < 3:
        return 0
    calm_thr = max(body_e * 1.05, 2.0)
    calm_run = 0
    saw_busy = False
    for dy, e in enumerate(energies):
        if e >= busy_thr:
            saw_busy = True
            calm_run = 0
            continue
        if not saw_busy:
            continue
        if e <= calm_thr:
            calm_run += 1
            if calm_run >= 5 and 10 <= dy <= h * 16 // 100:
                return dy
        else:
            calm_run = 0
    return 0


def detect_window_crop(
    path: Path | str,
    *,
    t_sec: float | None = None,
    analysis_max_width: int = 960,
    chrome_side_inset_frac_max: float = 0.08,
    window_relative_pad: float = 0.001,
    trim_browser_chrome: bool = True,
) -> WindowCrop:
    """Detect the on-screen floating window crop at optional timestamp ``t_sec``."""
    path = Path(path)
    buf, sw, sh, w, h = _grab_scaled_raw(
        path, t_sec=t_sec, max_w=analysis_max_width
    )
    col_mean, col_var, _col_df, _row_mean, _row_df = _col_row_stats(buf, sw, sh)
    labels = _classify_columns(col_mean, col_var)
    wl, wr = _find_ui_span_from_labels(labels, col_mean, col_var)

    row_mean_x, row_var_x = _row_stats_in_x(buf, sw, sh, wl, wr)
    wt, wb = _find_ui_rows(row_mean_x, row_var_x)

    search_x = max(4, (wr - wl) // 20)
    search_y = max(4, (wb - wt) // 16)
    # Left: never snap inward (that bites the sidebar). Only refine toward the
    # pillar / outer border, then keep a small outward pad.
    wl0 = wl
    wr0 = wr
    wl = _snap_vertical_edge(
        buf,
        sw,
        sh,
        x_guess=wl0,
        y0=wt,
        y1=wb,
        search_left=max(6, search_x),
        search_right=2,
        want_dark_on_right=True,
    )
    wl = min(wl, wl0)  # refuse inward overcrop on the left
    wr = _snap_vertical_edge(
        buf,
        sw,
        sh,
        x_guess=wr0,
        y0=wt,
        y1=wb,
        search_left=search_x,
        search_right=3,
        want_dark_on_right=False,
    )
    wr = max(wr, wr0)  # refuse inward overcrop on the right
    # Top: allow searching upward so title bar is not bitten.
    wt = _snap_horizontal_edge(
        buf,
        sw,
        sh,
        y_guess=wt,
        x0=wl,
        x1=wr,
        search_up=search_y,
        search_down=max(3, search_y // 3),
    )
    wb = _snap_horizontal_edge(
        buf,
        sw,
        sh,
        y_guess=wb,
        x0=wl,
        x1=wr,
        search_up=max(3, search_y // 3),
        search_down=search_y,
    )

    if wr <= wl + 4 or wb <= wt + 4:
        # Degenerate — fall back to full frame minus bright wallpaper edges.
        left = 0
        while left < sw and col_mean[left] >= 80:
            left += 1
        right = sw - 1
        while right > left and col_mean[right] >= 80:
            right -= 1
        wl, wr, wt, wb = left, right, 0, sh - 1

    chrome = 0
    side_inset = (wl + (sw - 1 - wr)) / max(1, sw)
    if (
        trim_browser_chrome
        and side_inset < chrome_side_inset_frac_max
        and (wr - wl) > sw * 0.85
    ):
        chrome = _detect_browser_chrome_top(buf, sw, sh, (wl, wt, wr, wb))

    sx = w / sw
    sy = h / sh
    # Prefer expanding left slightly (sidebar/title controls) over inward pad.
    left_out = max(2, round((wr - wl) * 0.01))
    pad_right = max(0, round((wr - wl) * window_relative_pad))
    pad_top = max(1, round((wb - wt) * 0.004))
    pad_bot = max(0, round((wb - wt) * window_relative_pad))

    x = int(max(0, (wl - left_out) * sx))
    y = int(max(0, (wt + chrome - pad_top) * sy))
    cw = int((wr - (wl - left_out) + 1 - pad_right) * sx)
    ch = int((wb - (wt + chrome) + 1 + pad_top - pad_bot) * sy)

    x = max(0, min(w - 2, x))
    y = max(0, min(h - 2, y))
    cw = min(w - x, max(2, cw))
    ch = min(h - y, max(2, ch))
    if cw % 2:
        cw -= 1
    if ch % 2:
        ch -= 1
    cw = max(2, cw)
    ch = max(2, ch)

    ok = cw >= w * 0.22 and ch >= h * 0.22
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
