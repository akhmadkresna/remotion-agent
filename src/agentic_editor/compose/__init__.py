"""Remotion compose helpers — write props + invoke remotion CLI."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agentic_editor.compose.mezzanine import resolve_compose_sources
from agentic_editor.cover import build_timeline_from_edl_and_cover, write_timeline
from agentic_editor.editor.edl import load_edl
from agentic_editor.paths import framework_home
from agentic_editor.project import load_project, resolve_source

# Absolute / drive-letter paths are not loadable in Remotion Studio (browser).
_ABS_PATH = re.compile(r"^(?:/|[A-Za-z]:[\\/]|\\\\)")


def remotion_kit_dir() -> Path:
    return framework_home() / "packages" / "remotion-kit"


def _pnpm_cmd() -> str:
    """Resolve pnpm for subprocess (Windows: prefer .cmd over .ps1 shim)."""
    if os.name == "nt":
        for name in ("pnpm.cmd", "pnpm.exe", "pnpm"):
            found = shutil.which(name)
            if found:
                return found
    found = shutil.which("pnpm")
    if found:
        return found
    raise FileNotFoundError(
        "pnpm not found on PATH — install pnpm, then retry ae compose"
    )


def _remotion_cli(kit: Path) -> list[str]:
    """Prefer local remotion bin; fall back to pnpm exec."""
    if os.name == "nt":
        local = kit / "node_modules" / ".bin" / "remotion.CMD"
    else:
        local = kit / "node_modules" / ".bin" / "remotion"
    if local.is_file():
        return [str(local)]
    return [_pnpm_cmd(), "exec", "remotion"]


def stage_sources_for_remotion(
    abs_sources: dict[str, str], *, verbose: bool = True
) -> dict[str, str]:
    """Copy episode media into remotion-kit/public for Studio HTTP serve.

    Always **copy** — never hardlink. On Windows, overwriting a hardlinked
    ``public/ae-media/*.mp4`` rewrites the same inode as episode ``raw/``, which
    can destroy masters when draft proxies are copied into public.

    Remotion cannot load absolute filesystem paths in the browser — only ``public/``
    via ``staticFile()``. Symlinks that escape ``public/`` are also rejected.
    See https://www.remotion.dev/docs/miscellaneous/absolute-paths
    """
    public = remotion_kit_dir() / "public" / "ae-media"
    if public.exists():
        shutil.rmtree(public)
    public.mkdir(parents=True, exist_ok=True)

    staged: dict[str, str] = {}
    for name, abs_path in abs_sources.items():
        src = Path(abs_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Source {name!r} missing: {src}")
        dest_name = f"{name}{src.suffix.lower()}"
        dest = public / dest_name
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        shutil.copy2(src, dest)
        if not dest.is_file():
            raise RuntimeError(f"Failed to stage source {name!r} into {dest}")
        # Guaranteed independent file — overwriting dest must not touch src.
        if dest.resolve() == src:
            raise RuntimeError(
                f"staged path for {name!r} resolves to source {src} — refusing"
            )
        try:
            if os.path.samefile(src, dest):
                raise RuntimeError(
                    f"staged {dest} is the same file as source {src} "
                    "(hardlink/symlink) — refusing to protect raw masters"
                )
        except OSError:
            pass
        # path relative to public/ — SourceClip wraps with staticFile()
        staged[name] = f"ae-media/{dest_name}"
        if verbose:
            print(f"• staged {name} → public/{staged[name]} ({dest.stat().st_size} bytes)")
    return staged


def validate_timeline_for_studio(timeline: dict[str, Any], props_path: Path) -> list[str]:
    """Return human-readable errors if Studio would show black/empty media."""
    errors: list[str] = []
    clips = timeline.get("clips") or []
    sources = timeline.get("sources") or {}
    frames = int(timeline.get("durationInFrames") or 0)
    dur = float(timeline.get("durationSec") or 0)

    if not clips:
        errors.append("timeline has no clips (did you write edit/edl.json?)")
    if frames < 30 or dur < 1.0:
        errors.append(
            f"timeline too short ({dur:.2f}s / {frames} frames) — looks like empty defaults"
        )

    public = remotion_kit_dir() / "public"
    for name, rel in sources.items():
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"source {name!r} is empty")
            continue
        if _ABS_PATH.match(rel) or rel.startswith("file:"):
            errors.append(
                f"source {name!r} is an absolute path ({rel!r}) — "
                "Studio cannot read disk paths; must be public-relative (ae-media/…)"
            )
            continue
        if rel.startswith("http://") or rel.startswith("https://"):
            continue
        disk = public / rel
        if not disk.is_file():
            errors.append(f"staged file missing for {name!r}: expected {disk}")

    if not props_path.is_file():
        errors.append(f"missing props file {props_path}")
    return errors


def prepare_compose(episode: Path, *, verbose: bool = True) -> Path:
    cfg = load_project(episode)
    edit = episode / "edit"
    edl_path = edit / "edl.json"
    if not edl_path.is_file():
        raise FileNotFoundError(f"Missing {edl_path}")
    edl = load_edl(edl_path)

    abs_sources: dict[str, str] = {}
    for name, rel in (cfg.get("sources") or {}).items():
        abs_sources[name] = str(resolve_source(episode, rel))
    for name, rel in edl["sources"].items():
        p = Path(rel)
        if not p.is_absolute():
            p = (edit / p).resolve()
        abs_sources.setdefault(name, str(p))

    # Prefer edit/mezzanine/* (deliverable size) over multi-GB raw masters.
    compose_sources = resolve_compose_sources(
        episode, abs_sources, cfg, verbose=verbose
    )
    staged_sources = stage_sources_for_remotion(compose_sources, verbose=verbose)

    edl_abs = dict(edl)
    edl_abs["sources"] = staged_sources

    cover_path = edit / "cover.json"
    cover = None
    if cover_path.is_file():
        cover = json.loads(cover_path.read_text(encoding="utf-8"))

    from agentic_editor.cover.style_load import load_overlays, load_screen_explainer

    style_name = str(cfg.get("style") or "tutorial")
    screen_explainer = load_screen_explainer(style_name)
    overlays = load_overlays(style_name)

    timeline = build_timeline_from_edl_and_cover(
        edl_abs,
        cover,
        fps=int(cfg.get("fps", 30)),
        width=int(cfg.get("width", 1920)),
        height=int(cfg.get("height", 1080)),
        screen_explainer=screen_explainer,
        overlays=overlays,
    )
    timeline["sources"] = staged_sources
    # absolute paths for tooling: compose media + raw masters
    timeline["sourcePaths"] = compose_sources
    timeline["rawSourcePaths"] = abs_sources

    # Dynamic smart window crop per float_centered clip (midpoint sample).
    crop_cfg = ((screen_explainer.get("screen") or {}).get("crop") or {})
    if str(crop_cfg.get("mode") or "") == "smart_window_detect":
        _attach_smart_window_crops(
            timeline,
            abs_sources,
            crop_cfg=crop_cfg,
            episode=episode,
            verbose=verbose,
        )

    out = edit / "timeline.json"
    write_timeline(out, timeline)
    props = edit / "remotion-props.json"
    props.write_text(json.dumps({"timeline": timeline}, indent=2) + "\n", encoding="utf-8")

    errors = validate_timeline_for_studio(timeline, props)
    if errors:
        msg = "compose preflight failed:\n  - " + "\n  - ".join(errors)
        raise RuntimeError(msg)

    if verbose:
        print(f"• timeline → {out.relative_to(episode)}")
        print(f"• props → {props.relative_to(episode)}")
        print(f"• duration {timeline['durationSec']:.1f}s / {timeline['durationInFrames']} frames")
        print("• preflight OK (staged public media + non-empty timeline)")
    return out


def _load_stable_window_crop(episode: Path) -> dict[str, Any] | None:
    """Prefer hand-tuned / verified edit/window_crop.json when present."""
    path = episode / "edit" / "window_crop.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stable = data.get("stable") if isinstance(data, dict) else None
    if not isinstance(stable, dict) or not stable.get("ok", True):
        return None
    norm = stable.get("normalized")
    if not isinstance(norm, dict):
        return None
    try:
        return {
            "normalized": {
                "x": float(norm["x"]),
                "y": float(norm["y"]),
                "w": float(norm["w"]),
                "h": float(norm["h"]),
            },
            "px": {
                "x": int(stable["x"]),
                "y": int(stable["y"]),
                "w": int(stable["w"]),
                "h": int(stable["h"]),
            },
        }
    except (KeyError, TypeError, ValueError):
        return None


def _attach_smart_window_crops(
    timeline: dict[str, Any],
    abs_sources: dict[str, str],
    *,
    crop_cfg: dict[str, Any],
    episode: Path | None = None,
    verbose: bool = True,
) -> None:
    """Annotate float_centered clips with normalized windowCrop from pixel detect."""
    from agentic_editor.cover.window_crop import detect_window_crop

    stable = _load_stable_window_crop(episode) if episode is not None else None
    if stable is not None:
        n = 0
        for clip in timeline.get("clips") or []:
            if clip.get("layout") != "float_centered":
                continue
            clip["windowCrop"] = dict(stable["normalized"])
            clip["windowCropPx"] = dict(stable["px"])
            n += 1
        if verbose and n:
            print(
                f"• smart_window_detect → {n} float clip(s) "
                f"(stable edit/window_crop.json)"
            )
        return

    kwargs = {
        "analysis_max_width": int(crop_cfg.get("analysisMaxWidth") or 480),
        "chrome_side_inset_frac_max": float(
            crop_cfg.get("chromeSideInsetFracMax") or 0.12
        ),
        "window_relative_pad": float(crop_cfg.get("windowRelativePad") or 0.003),
    }
    cache: dict[tuple[str, float], dict[str, Any]] = {}
    n = 0
    for clip in timeline.get("clips") or []:
        if clip.get("layout") != "float_centered":
            continue
        src_name = str(clip.get("source") or "")
        abs_path = abs_sources.get(src_name)
        if not abs_path or not Path(abs_path).is_file():
            continue
        mid = float(clip.get("sourceIn") or 0) + float(clip.get("durationSec") or 0) / 2
        mid = round(mid, 2)
        key = (src_name, mid)
        if key not in cache:
            try:
                crop = detect_window_crop(abs_path, t_sec=mid, **kwargs)
                cache[key] = crop.as_dict()
            except Exception as exc:  # noqa: BLE001 — compose must not die on crop
                if verbose:
                    print(f"• window crop skipped for {src_name}@{mid}s: {exc}")
                cache[key] = {}
        if cache[key]:
            clip["windowCrop"] = cache[key]["normalized"]
            clip["windowCropPx"] = {
                "x": cache[key]["x"],
                "y": cache[key]["y"],
                "w": cache[key]["w"],
                "h": cache[key]["h"],
            }
            n += 1
    if verbose and n:
        print(f"• smart_window_detect → {n} float clip(s)")


def run_studio(episode: Path) -> None:
    prepare_compose(episode)
    kit = remotion_kit_dir()
    props = episode / "edit" / "remotion-props.json"
    # Re-check after write (belt + suspenders)
    timeline = json.loads(props.read_text(encoding="utf-8")).get("timeline") or {}
    errors = validate_timeline_for_studio(timeline, props)
    if errors:
        raise RuntimeError("refusing to start Studio:\n  - " + "\n  - ".join(errors))

    env = os.environ.copy()
    env["AE_TIMELINE_PROPS"] = str(props)
    env["AE_EPISODE"] = str(episode.resolve())
    if not (kit / "package.json").is_file():
        raise FileNotFoundError(f"Remotion kit missing at {kit}")
    cmd = [
        *_remotion_cli(kit),
        "studio",
        "src/index.ts",
        "--props",
        str(props),
    ]
    print(f"$ cd {kit} && {' '.join(cmd)}")
    print("  (always pass --props — without it Studio shows a ~3s black empty timeline)")
    subprocess.run(cmd, cwd=str(kit), env=env, check=True)


def render_compose(episode: Path, *, output: Path | None = None) -> Path:
    prepare_compose(episode)
    kit = remotion_kit_dir()
    props = episode / "edit" / "remotion-props.json"
    out = output or (episode / "edit" / "final.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["AE_TIMELINE_PROPS"] = str(props)
    env["AE_EPISODE"] = str(episode.resolve())
    cmd = [
        *_remotion_cli(kit),
        "render",
        "src/index.ts",
        "AgenticTimeline",
        str(out),
        "--props",
        str(props),
    ]
    print(f"$ cd {kit} && {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(kit), env=env, check=True)
    return out


def npx_available() -> bool:
    try:
        _pnpm_cmd()
        return True
    except FileNotFoundError:
        return shutil.which("npx") is not None
