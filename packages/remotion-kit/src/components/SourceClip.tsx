import React from "react";
import {
  AbsoluteFill,
  Easing,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { FramingMotion } from "../types";

type Props = {
  src: string;
  sourceIn: number;
  layout: "full" | "pip_corner";
  scale?: number;
  motion?: FramingMotion;
  durationSec?: number;
};

/** Resolve public-relative paths via staticFile; leave http(s) alone. */
function resolveSrc(src: string): string {
  if (
    src.startsWith("http://") ||
    src.startsWith("https://") ||
    src.startsWith("data:") ||
    src.startsWith("blob:")
  ) {
    return src;
  }
  // Already a root URL served by Studio
  if (src.startsWith("/") && !src.startsWith("/Users") && !src.startsWith("/home")) {
    return src;
  }
  // Absolute disk paths are not loadable in the browser — caller should stage to public/
  if (src.startsWith("/") || /^[A-Za-z]:[\\/]/.test(src)) {
    console.warn(
      `Absolute media path will not load in Studio: ${src}. Re-run ae compose to stage into public/.`,
    );
    return src;
  }
  return staticFile(src);
}

function useMotionScale(
  baseScale: number,
  motion: FramingMotion,
  durationSec: number,
): number {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const ramp = Math.min(0.35, Math.max(0.12, durationSec / 5));

  if (motion === "hold" || motion === "snap") {
    return baseScale;
  }

  if (motion === "drift") {
    const end = baseScale * 1.035;
    return interpolate(t, [0, Math.max(0.05, durationSec)], [baseScale, end], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.linear,
    });
  }

  if (motion === "ease_out") {
    // start tight, ease to base (punch-out feel)
    const from = Math.min(baseScale * 1.08, 1.28);
    return interpolate(t, [0, ramp], [from, baseScale], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });
  }

  // ease / ease_in: push from slightly wider into baseScale
  const from = Math.max(1, baseScale * 0.94);
  return interpolate(t, [0, ramp], [from, baseScale], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
}

export const SourceClip: React.FC<Props> = ({
  src,
  sourceIn,
  layout,
  scale = 1,
  motion = "snap",
  durationSec = 1,
}) => {
  const { width, height, fps } = useVideoConfig();
  const startFrom = Math.max(0, Math.round(sourceIn * fps));
  const liveScale = useMotionScale(scale, motion, durationSec);
  const resolvedSrc = resolveSrc(src);

  if (layout === "pip_corner") {
    const pipW = Math.round(width * 0.28);
    const pipH = Math.round(height * 0.28);
    return (
      <AbsoluteFill>
        <div
          style={{
            position: "absolute",
            right: 48,
            bottom: 48,
            width: pipW,
            height: pipH,
            borderRadius: 12,
            overflow: "hidden",
            boxShadow: "0 8px 32px rgba(0,0,0,0.45)",
            border: "2px solid rgba(255,255,255,0.2)",
          }}
        >
          <OffthreadVideo
            src={resolvedSrc}
            startFrom={startFrom}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              transform: `scale(${liveScale})`,
              transformOrigin: "center center",
            }}
          />
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <OffthreadVideo
        src={resolvedSrc}
        startFrom={startFrom}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${liveScale})`,
          transformOrigin: "center 42%",
        }}
      />
    </AbsoluteFill>
  );
};
