import React from "react";
import {
  AbsoluteFill,
  Sequence,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import { SourceClip } from "./components/SourceClip";
import { CaptionLayer } from "./components/CaptionLayer";
import { MissingTimelineBanner } from "./components/MissingTimelineBanner";
import type { TimelineProps } from "./types";

function looksLikeEmptyTimeline(timeline: TimelineProps["timeline"]): string | null {
  const clips = timeline?.clips || [];
  const frames = timeline?.durationInFrames || 0;
  const sources = timeline?.sources || {};
  if (!clips.length || frames < 30) {
    return "Timeline is empty or ~3s default — Studio was probably started without --props.";
  }
  for (const [name, src] of Object.entries(sources)) {
    if (!src) return `Source ${name} is empty.`;
    if (
      src.startsWith("/") ||
      src.startsWith("file:") ||
      /^[A-Za-z]:[\\/]/.test(src)
    ) {
      return `Source ${name} is an absolute disk path (${src}). Remotion Studio cannot read the filesystem — re-run ae compose . --studio to stage public/ae-media/.`;
    }
  }
  return null;
}

export const AgenticTimeline: React.FC<TimelineProps> = ({ timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const emptyReason = looksLikeEmptyTimeline(timeline);
  if (emptyReason) {
    return <MissingTimelineBanner reason={emptyReason} />;
  }

  const punchScale = (() => {
    let scale = 1;
    for (const ef of timeline.effects || []) {
      const start = ef.fromSec;
      const end = ef.fromSec + ef.durationSec;
      if (t < start || t > end) continue;
      const local = t - start;
      const dur = Math.max(0.05, ef.durationSec);
      const ramp = Math.min(0.25, dur / 3);
      if (ef.type === "punch_out") {
        const down = interpolate(local, [0, ramp], [ef.scale, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.out(Easing.cubic),
        });
        scale = local < ramp ? down : 1;
        continue;
      }
      const up = interpolate(local, [0, ramp], [1, ef.scale], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.out(Easing.cubic),
      });
      const down = interpolate(local, [dur - ramp, dur], [ef.scale, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: Easing.in(Easing.cubic),
      });
      scale = local < dur - ramp ? up : down;
    }
    return scale;
  })();

  const mainClips = (timeline.clips || []).filter((c) => c.layout === "full");
  const pipClips = (timeline.clips || []).filter((c) => c.layout === "pip_corner");

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      <AbsoluteFill
        style={{
          overflow: "hidden",
          transform: `scale(${punchScale})`,
          transformOrigin: "center 42%",
        }}
      >
        {mainClips.map((clip) => {
          const from = Math.round(clip.fromSec * fps);
          const duration = Math.max(1, Math.round(clip.durationSec * fps));
          const src = timeline.sources[clip.source];
          if (!src) return null;
          return (
            <Sequence key={clip.id} from={from} durationInFrames={duration} name={clip.id}>
              <SourceClip
                src={src}
                sourceIn={clip.sourceIn}
                layout="full"
                scale={clip.scale ?? 1}
                motion={clip.motion ?? "snap"}
                durationSec={clip.durationSec}
              />
            </Sequence>
          );
        })}
      </AbsoluteFill>

      {pipClips.map((clip) => {
        const from = Math.round(clip.fromSec * fps);
        const duration = Math.max(1, Math.round(clip.durationSec * fps));
        const src = timeline.sources[clip.source];
        if (!src) return null;
        return (
          <Sequence key={clip.id} from={from} durationInFrames={duration} name={clip.id}>
            <SourceClip
              src={src}
              sourceIn={clip.sourceIn}
              layout="pip_corner"
              scale={clip.scale ?? 1}
              motion={clip.motion ?? "snap"}
              durationSec={clip.durationSec}
            />
          </Sequence>
        );
      })}

      <CaptionLayer captions={timeline.captions || []} />
    </AbsoluteFill>
  );
};
