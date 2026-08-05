"""Remotion compose helpers — write props + invoke remotion CLI."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agentic_editor.cover import build_timeline_from_edl_and_cover, write_timeline
from agentic_editor.editor.edl import load_edl
from agentic_editor.paths import framework_home
from agentic_editor.project import load_project, resolve_source


def remotion_kit_dir() -> Path:
    return framework_home() / "packages" / "remotion-kit"


def prepare_compose(episode: Path, *, verbose: bool = True) -> Path:
    cfg = load_project(episode)
    edit = episode / "edit"
    edl_path = edit / "edl.json"
    if not edl_path.is_file():
        raise FileNotFoundError(f"Missing {edl_path}")
    edl = load_edl(edl_path)

    # Resolve source paths to absolute for Remotion staticFile / absolute file protocol
    abs_sources: dict[str, str] = {}
    for name, rel in (cfg.get("sources") or {}).items():
        abs_sources[name] = str(resolve_source(episode, rel))
    # Also merge EDL sources (may be relative to edit/)
    for name, rel in edl["sources"].items():
        p = Path(rel)
        if not p.is_absolute():
            p = (edit / p).resolve()
        abs_sources.setdefault(name, str(p))

    edl_abs = dict(edl)
    edl_abs["sources"] = abs_sources

    cover_path = edit / "cover.json"
    cover = None
    if cover_path.is_file():
        cover = json.loads(cover_path.read_text(encoding="utf-8"))

    timeline = build_timeline_from_edl_and_cover(
        edl_abs,
        cover,
        fps=int(cfg.get("fps", 30)),
        width=int(cfg.get("width", 1920)),
        height=int(cfg.get("height", 1080)),
    )
    # Prefer project sources for cam/screen
    timeline["sources"] = abs_sources

    out = edit / "timeline.json"
    write_timeline(out, timeline)
    props = edit / "remotion-props.json"
    props.write_text(json.dumps({"timeline": timeline}, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(f"• timeline → {out.relative_to(episode)}")
        print(f"• props → {props.relative_to(episode)}")
    return out


def run_studio(episode: Path) -> None:
    prepare_compose(episode)
    kit = remotion_kit_dir()
    props = episode / "edit" / "remotion-props.json"
    env = os.environ.copy()
    env["AE_TIMELINE_PROPS"] = str(props)
    env["AE_EPISODE"] = str(episode.resolve())
    if not (kit / "package.json").is_file():
        raise FileNotFoundError(f"Remotion kit missing at {kit}")
    cmd = ["pnpm", "exec", "remotion", "studio", "src/index.ts"]
    print(f"$ cd {kit} && AE_TIMELINE_PROPS={props} {' '.join(cmd)}")
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
        "pnpm",
        "exec",
        "remotion",
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
    return shutil.which("pnpm") is not None or shutil.which("npx") is not None
