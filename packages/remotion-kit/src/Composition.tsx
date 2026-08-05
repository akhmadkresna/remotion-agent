import React, { useMemo } from "react";
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
import type { TimelineProps } from "./types";

export const AgenticTimeline: React.FC<TimelineProps> = ({ timeline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  const punchScale = useMemo(() => {
    let scale = 1;
    for (const ef of timeline.effects || []) {
      if (ef.type !== "punch_in") continue;
      const start = ef.fromSec;
      const end = ef.fromSec + ef.durationSec;
      if (t < start || t > end) continue;
      const local = t - start;
      const dur = Math.max(0.05, ef.durationSec);
      const ramp = Math.min(0.25, dur / 3);
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
  }, [timeline.effects, t]);

  const mainClips = (timeline.clips || []).filter((c) => c.layout === "full");
  const pipClips = (timeline.clips || []).filter((c) => c.layout === "pip_corner");

  return (
    <AbsoluteFill style={{ backgroundColor: "#0a0a0a" }}>
      <AbsoluteFill
        style={{
          transform: `scale(${punchScale})`,
          transformOrigin: "center center",
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
            <SourceClip src={src} sourceIn={clip.sourceIn} layout="pip_corner" />
          </Sequence>
        );
      })}

      <CaptionLayer captions={timeline.captions || []} />
    </AbsoluteFill>
  );
};
