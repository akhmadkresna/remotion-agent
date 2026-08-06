"""ae CLI — doctor, new, ingest, cut, cover, cover-suggest, overlay-suggest, compose, qa, promote-check."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from agentic_editor import __version__
from agentic_editor.asr.backends import (
    faster_whisper_available,
    resolve_backend,
    whisper_cpp_binary,
)
from agentic_editor.asr.ingest import ingest_episode
from agentic_editor.compose import prepare_compose, render_compose, run_studio
from agentic_editor.compose.mezzanine import build_mezzanines
from agentic_editor.cover import example_cover, write_timeline
from agentic_editor.cover import build_timeline_from_edl_and_cover
from agentic_editor.cover.suggest import suggest_cover, write_cover_suggest
from agentic_editor.cover.overlay_suggest import suggest_overlays, write_overlay_suggest
from agentic_editor.cover.style_load import load_overlays, load_screen_explainer
from agentic_editor.editor.edl import example_edl, load_edl
from agentic_editor.editor.qa import qa_episode_preview
from agentic_editor.editor.render import render_edl
from agentic_editor.paths import framework_home, resolve_episode
from agentic_editor.project import load_project, resolve_source


def cmd_doctor(_: argparse.Namespace) -> int:
    home = framework_home()
    print(f"agentic-editor {__version__}")
    print(f"AGENTIC_EDITOR_HOME = {home}")
    print()

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    print(f"ffmpeg:  {'OK  ' + ffmpeg if ffmpeg else 'MISSING'}")
    print(f"ffprobe: {'OK  ' + ffprobe if ffprobe else 'MISSING'}")

    node = shutil.which("node")
    pnpm = shutil.which("pnpm")
    print(f"node:    {'OK  ' + node if node else 'MISSING'}")
    print(f"pnpm:    {'OK  ' + pnpm if pnpm else 'MISSING (needed for Remotion)'}")

    auto = resolve_backend("auto")
    print(f"\nASR auto backend on this machine: {auto}")

    wbin = whisper_cpp_binary()
    print(f"whisper.cpp CLI: {'OK  ' + wbin if wbin else 'MISSING (brew install whisper-cpp)'}")
    fw = faster_whisper_available()
    print(f"faster-whisper:  {'OK' if fw else 'MISSING (uv sync)'}")

    models = home / "models"
    if models.is_dir():
        bins = list(models.glob("ggml-*.bin"))
        print(f"models/: {len(bins)} ggml file(s) in {models}")
    else:
        print(f"models/: (create {models} and download ggml-small.bin for whisper.cpp)")

    kit = home / "packages" / "remotion-kit" / "package.json"
    print(f"remotion-kit: {'OK' if kit.is_file() else 'MISSING'}")
    public = home / "packages" / "remotion-kit" / "public"
    print(f"remotion public/: {'OK  ' + str(public) if public.is_dir() else 'will create on compose'}")

    print("\nCompose rules (avoid black Studio):")
    print("  Always:  ae compose <episode> --studio   # copy→public/ae-media + passes --props")
    print("  Heavy raw: ae mezzanine <episode>        # 1080p30 CRF16 → edit/mezzanine (raw safe)")
    print("  Never:   pnpm remotion studio   # alone → empty ~3s black timeline")
    print("  Media must be public-relative (ae-media/cam.mov), never /Users/... absolute paths")
    print("  Staging always copies (never hardlinks) so draft proxies cannot clobber raw/")

    print("\nInstall tips:")
    print("  Mac:     brew install whisper-cpp ffmpeg")
    print("           download ggml-small.bin into $AGENTIC_EDITOR_HOME/models/")
    print("  Windows: uv sync  (faster-whisper); install CUDA ctranslate2 if GPU")
    print("  Both:    export AGENTIC_EDITOR_HOME=" + str(home))
    print("           ln -s \"$AGENTIC_EDITOR_HOME/skills/agentic-editor\" ~/.cursor/skills/agentic-editor")
    return 0 if ffmpeg and ffprobe else 1


def cmd_new(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.path)
    home = framework_home()
    template = home / "templates" / "project"
    if episode.exists() and any(episode.iterdir()):
        if not args.force:
            print(f"Refusing to overwrite non-empty {episode} (pass --force)", file=sys.stderr)
            return 1
    episode.mkdir(parents=True, exist_ok=True)
    if template.is_dir():
        for item in template.rglob("*"):
            rel = item.relative_to(template)
            dest = episode / rel
            if item.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() and not args.force:
                    continue
                shutil.copy2(item, dest)
    else:
        (episode / "raw").mkdir(exist_ok=True)
        (episode / "edit").mkdir(exist_ok=True)

    yaml_path = episode / "project.yaml"
    if not yaml_path.exists() or args.force:
        yaml_path.write_text(
            f"""id: {episode.name}
sources:
  cam: raw/cam.mp4
  # screen: raw/screen.mp4
style: tutorial
asr:
  backend: auto
  model: small
  language: id
fps: 30
aspect: "16:9"
width: 1920
height: 1080
""",
            encoding="utf-8",
        )
    print(f"Created episode at {episode}")
    print("Drop footage into raw/, then: ae ingest .")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    ingest_episode(episode, force=args.force, verbose=not args.quiet)
    return 0


def cmd_cut(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    cfg = load_project(episode)
    edit = episode / "edit"
    edl_path = Path(args.edl) if args.edl else edit / "edl.json"
    if not edl_path.is_file():
        # seed example if missing
        print(f"No {edl_path}; writing example scaffold (edit before shipping)")
        example = example_edl("../raw/cam.mp4")
        edl_path.write_text(json.dumps(example, indent=2) + "\n", encoding="utf-8")
        print("Update edit/edl.json with real keep ranges, then re-run ae cut")
        return 1
    out = render_edl(
        edl_path,
        edit,
        preview=not args.final,
        fps=int(cfg.get("fps", 30)),
        verbose=not args.quiet,
    )
    print(f"Wrote {out}")
    return 0


def cmd_cover(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    cfg = load_project(episode)
    edit = episode / "edit"
    edl_path = edit / "edl.json"
    if not edl_path.is_file():
        print("Missing edit/edl.json — run radio-edit first", file=sys.stderr)
        return 1
    cover_path = edit / "cover.json"
    if not cover_path.is_file():
        cover_path.write_text(json.dumps(example_cover(), indent=2) + "\n", encoding="utf-8")
        print(f"Seeded {cover_path.relative_to(episode)} — edit cover events, re-run ae cover")
    edl = load_edl(edl_path)
    # absolutize sources from project
    sources = {}
    for name, rel in (cfg.get("sources") or {}).items():
        p = Path(rel)
        sources[name] = str((episode / p).resolve() if not p.is_absolute() else p)
    for name, rel in edl["sources"].items():
        sources.setdefault(name, str((edit / rel).resolve() if not Path(rel).is_absolute() else rel))
    edl["sources"] = sources
    cover = json.loads(cover_path.read_text(encoding="utf-8"))
    style_name = str(cfg.get("style") or "tutorial")
    timeline = build_timeline_from_edl_and_cover(
        edl,
        cover,
        fps=int(cfg.get("fps", 30)),
        width=int(cfg.get("width", 1920)),
        height=int(cfg.get("height", 1080)),
        screen_explainer=load_screen_explainer(style_name),
        overlays=load_overlays(style_name),
    )
    out = edit / "timeline.json"
    write_timeline(out, timeline)
    n_ov = len(timeline.get("overlays") or [])
    print(
        f"Wrote {out.relative_to(episode)} "
        f"({len(timeline['clips'])} clips, {n_ov} overlays, {timeline['durationSec']:.1f}s)"
    )
    return 0


def cmd_cover_suggest(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    cfg = load_project(episode)
    sources = cfg.get("sources") or {}
    if "screen" not in sources:
        print("No screen source in project.yaml — nothing to suggest (full-cam only)", file=sys.stderr)
        return 1
    suggestion = suggest_cover(episode, skip_activity_probe=bool(args.skip_activity))
    out = write_cover_suggest(episode, suggestion)
    meta = suggestion.get("_meta") or {}
    events = suggestion.get("events") or []
    print(
        f"Wrote {out.relative_to(episode)} "
        f"({len(events)} screen_with_cam event(s); "
        f"deixis={meta.get('deixis_hits', 0)}, activity_bins={meta.get('activity_bins', 0)})"
    )
    print("Review, copy into edit/cover.json (or merge events), then: ae cover .")
    if args.apply and events:
        cover_path = episode / "edit" / "cover.json"
        if cover_path.is_file():
            cover = json.loads(cover_path.read_text(encoding="utf-8"))
        else:
            cover = example_cover()
        # Replace prior screen_with_cam / cam_pip suggestions; keep framing/punch
        kept = [
            e
            for e in (cover.get("events") or [])
            if str(e.get("type") or "").lower() not in ("screen_with_cam", "cam_pip")
        ]
        cover["events"] = kept + list(events)
        cover.setdefault("camera_play", suggestion.get("camera_play") or {})
        cover_path.write_text(json.dumps(cover, indent=2) + "\n", encoding="utf-8")
        print(f"Merged suggested events into {cover_path.relative_to(episode)}")
    return 0


def cmd_overlay_suggest(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    suggestion = suggest_overlays(episode)
    out = write_overlay_suggest(episode, suggestion)
    meta = suggestion.get("_meta") or {}
    counts = meta.get("counts") or {}
    overlays = suggestion.get("overlays") or []
    framing_events = suggestion.get("framing_events") or []
    print(
        f"Wrote {out.relative_to(episode)} "
        f"({counts.get('total', len(overlays))} overlays: "
        f"chapter={counts.get('chapter', 0)}, "
        f"emphasis={counts.get('emphasis', 0)}, "
        f"diagram={counts.get('diagram', 0)}, "
        f"chip={counts.get('chip', 0)}; "
        f"framing_companions={counts.get('framing_companions', len(framing_events))}; "
        f"screen={counts.get('on_screen', 0)} cam={counts.get('on_cam', 0)})"
    )
    if not meta.get("has_cover"):
        print(
            "Note: no edit/cover.json yet — chapter/diagram will attach medium/wide "
            "framing companions for full-cam. Prefer running cover first."
        )
    print("Propose/adjust with the user, then confirm before writing cover.json.")
    print(
        "After confirm: merge overlays[] + framing companions into cover.json events[], "
        "then: ae cover ."
    )
    if args.apply and overlays:
        from agentic_editor.cover.overlay_suggest import merge_framing_into_events

        cover_path = episode / "edit" / "cover.json"
        if cover_path.is_file():
            cover = json.loads(cover_path.read_text(encoding="utf-8"))
        else:
            cover = example_cover()
        cover["overlays"] = list(overlays)
        cover["events"] = merge_framing_into_events(
            list(cover.get("events") or []),
            list(framing_events),
        )
        cover_path.write_text(json.dumps(cover, indent=2) + "\n", encoding="utf-8")
        print(
            f"Wrote overlays + {len(framing_events)} framing companion(s) into "
            f"{cover_path.relative_to(episode)} (--apply)"
        )
    return 0


def cmd_mezzanine(args: argparse.Namespace) -> int:
    """Encode deliverable-sized proxies into edit/mezzanine/ (raw stays read-only)."""
    episode = resolve_episode(args.episode)
    cfg = load_project(episode)
    sources: dict[str, Path] = {}
    for name, rel in (cfg.get("sources") or {}).items():
        sources[name] = resolve_source(episode, rel)
    if not sources:
        print("No sources in project.yaml", file=sys.stderr)
        return 1
    missing = [n for n, p in sources.items() if not p.is_file()]
    if missing:
        print(f"Missing source file(s): {', '.join(missing)}", file=sys.stderr)
        return 1
    built = build_mezzanines(
        episode,
        sources,
        width=int(cfg.get("width", 1920)),
        height=int(cfg.get("height", 1080)),
        fps=int(cfg.get("fps", 30)),
        crf=int(args.crf),
        force=bool(args.force),
        verbose=not args.quiet,
    )
    print(f"Mezzanines ready: {', '.join(f'{n}→{p}' for n, p in built.items())}")
    print("Next: ae compose . --studio   # stages mezzanines, not multi-GB raw")
    return 0


def cmd_compose(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    if args.studio:
        run_studio(episode)
        return 0
    if args.prepare_only:
        prepare_compose(episode)
        return 0
    out = render_compose(episode, output=Path(args.output) if args.output else None)
    print(f"Wrote {out}")
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    verify = qa_episode_preview(episode, verbose=not args.quiet)
    print(f"QA frames in {verify}")
    return 0


def cmd_promote_check(args: argparse.Namespace) -> int:
    episode = resolve_episode(args.episode)
    path = episode / "edit" / "promotions.md"
    if not path.is_file():
        print("No edit/promotions.md — nothing pending")
        return 0
    print(path.read_text(encoding="utf-8"))
    print(f"\nPromote into: {framework_home()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ae",
        description="Agentic Editor — local ASR, radio-edit, Remotion compose",
    )
    p.add_argument("--version", action="version", version=f"ae {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="Check ffmpeg, ASR backends, Remotion kit")
    d.set_defaults(func=cmd_doctor)

    n = sub.add_parser("new", help="Scaffold an episode folder")
    n.add_argument("path", help="Episode directory to create")
    n.add_argument("--force", action="store_true")
    n.set_defaults(func=cmd_new)

    ing = sub.add_parser("ingest", help="Probe + ASR + pack transcripts")
    ing.add_argument("episode", nargs="?", default=".")
    ing.add_argument("--force", action="store_true", help="Ignore ASR cache")
    ing.add_argument("--quiet", action="store_true")
    ing.set_defaults(func=cmd_ingest)

    cut = sub.add_parser("cut", help="Render EDL → preview/a_roll via ffmpeg")
    cut.add_argument("episode", nargs="?", default=".")
    cut.add_argument("--edl", help="Path to edl.json (default edit/edl.json)")
    cut.add_argument("--final", action="store_true", help="Higher quality a_roll.mp4")
    cut.add_argument("--quiet", action="store_true")
    cut.set_defaults(func=cmd_cut)

    cov = sub.add_parser("cover", help="Merge EDL + cover.json → timeline.json")
    cov.add_argument("episode", nargs="?", default=".")
    cov.set_defaults(func=cmd_cover)

    cs = sub.add_parser(
        "cover-suggest",
        help="Suggest screen_with_cam ranges from transcript deixis + screen activity",
    )
    cs.add_argument("episode", nargs="?", default=".")
    cs.add_argument(
        "--skip-activity",
        action="store_true",
        help="Skip ffmpeg screen activity probe (deixis-only)",
    )
    cs.add_argument(
        "--apply",
        action="store_true",
        help="Merge suggested screen_with_cam events into edit/cover.json",
    )
    cs.set_defaults(func=cmd_cover_suggest)

    osug = sub.add_parser(
        "overlay-suggest",
        help=(
            "Suggest sparse A-roll MG overlays (chapter/emphasis/diagram/chip) "
            "from EDL + ASR, gated by cover mode + camera_play framing"
        ),
    )
    osug.add_argument("episode", nargs="?", default=".")
    osug.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Write overlays[] + companion framing events into edit/cover.json "
            "(only after user confirm)"
        ),
    )
    osug.set_defaults(func=cmd_overlay_suggest)

    mez = sub.add_parser(
        "mezzanine",
        help="Encode deliverable-size proxies → edit/mezzanine (raw untouched)",
    )
    mez.add_argument("episode", nargs="?", default=".")
    mez.add_argument(
        "--crf",
        type=int,
        default=16,
        help="libx264 CRF (default 16 = near-transparent for 1080p YouTube)",
    )
    mez.add_argument("--force", action="store_true", help="Rebuild even if up-to-date")
    mez.add_argument("--quiet", action="store_true")
    mez.set_defaults(func=cmd_mezzanine)

    com = sub.add_parser("compose", help="Remotion studio / render from timeline")
    com.add_argument("episode", nargs="?", default=".")
    com.add_argument("--studio", action="store_true")
    com.add_argument("--prepare-only", action="store_true")
    com.add_argument("-o", "--output")
    com.set_defaults(func=cmd_compose)

    qa = sub.add_parser("qa", help="Extract cut-boundary frames from preview.mp4")
    qa.add_argument("episode", nargs="?", default=".")
    qa.add_argument("--quiet", action="store_true")
    qa.set_defaults(func=cmd_qa)

    pr = sub.add_parser("promote-check", help="Show edit/promotions.md")
    pr.add_argument("episode", nargs="?", default=".")
    pr.set_defaults(func=cmd_promote_check)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except BrokenPipeError:
        return 0
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
