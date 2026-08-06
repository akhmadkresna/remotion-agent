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
import type {
  ClipLayout,
  FramingMotion,
  ScreenExplainerStyle,
  WindowCropNorm,
} from "../types";
import { DEFAULT_SCREEN_EXPLAINER } from "../types";

type Props = {
  src: string;
  sourceIn: number;
  layout: ClipLayout;
  scale?: number;
  motion?: FramingMotion;
  durationSec?: number;
  /** Explicit mute; if omitted, non-cam sources are muted by volume prop. */
  muted?: boolean;
  volume?: number;
  windowCrop?: WindowCropNorm;
  screenExplainer?: ScreenExplainerStyle;
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
  if (src.startsWith("/") && !src.startsWith("/Users") && !src.startsWith("/home")) {
    return src;
  }
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
    const from = Math.min(baseScale * 1.08, 1.28);
    return interpolate(t, [0, ramp], [from, baseScale], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    });
  }

  const from = Math.max(1, baseScale * 0.94);
  return interpolate(t, [0, ramp], [from, baseScale], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
}

function CroppedVideo({
  src,
  startFrom,
  volume,
  liveScale,
  transformOrigin,
  windowCrop,
  objectFit = "cover",
  objectPosition = "center center",
}: {
  src: string;
  startFrom: number;
  volume: number;
  liveScale: number;
  transformOrigin: string;
  windowCrop?: WindowCropNorm;
  objectFit?: string;
  objectPosition?: string;
}) {
  if (!windowCrop || windowCrop.w <= 0 || windowCrop.h <= 0) {
    return (
      <OffthreadVideo
        src={src}
        startFrom={startFrom}
        volume={volume}
        style={{
          width: "100%",
          height: "100%",
          objectFit: objectFit as React.CSSProperties["objectFit"],
          objectPosition,
          transform: `scale(${liveScale})`,
          transformOrigin,
        }}
      />
    );
  }

  const { x, y, w, h } = windowCrop;
  // Map source frame so the crop rect fills the container.
  const widthPct = (1 / w) * 100;
  const heightPct = (1 / h) * 100;
  const leftPct = (-x / w) * 100;
  const topPct = (-y / h) * 100;

  return (
    <div style={{ width: "100%", height: "100%", overflow: "hidden", position: "relative" }}>
      <OffthreadVideo
        src={src}
        startFrom={startFrom}
        volume={volume}
        style={{
          position: "absolute",
          width: `${widthPct}%`,
          height: `${heightPct}%`,
          left: `${leftPct}%`,
          top: `${topPct}%`,
          objectFit: "fill",
          transform: `scale(${liveScale})`,
          transformOrigin,
        }}
      />
    </div>
  );
}

export const SourceClip: React.FC<Props> = ({
  src,
  sourceIn,
  layout,
  scale = 1,
  motion = "snap",
  durationSec = 1,
  muted = false,
  volume,
  windowCrop,
  screenExplainer,
}) => {
  const { width, height, fps } = useVideoConfig();
  const startFrom = Math.max(0, Math.round(sourceIn * fps));
  const liveScale = useMotionScale(scale, motion, durationSec);
  const resolvedSrc = resolveSrc(src);
  const vol = volume ?? (muted ? 0 : 1);
  const se = screenExplainer || DEFAULT_SCREEN_EXPLAINER;
  const screenCfg = { ...DEFAULT_SCREEN_EXPLAINER.screen, ...se.screen };
  const pipCfg = { ...DEFAULT_SCREEN_EXPLAINER.pip, ...se.pip };

  if (layout === "pip_corner") {
    const pipW = Math.round(width * (pipCfg.widthRatio ?? 0.18));
    const pipH = Math.round(pipW * 1.25); // 4:5
    const right = Math.round(width * (pipCfg.insetRightRatio ?? 0.035));
    const bottom = Math.round(height * (pipCfg.insetBottomRatio ?? 0.045));
    const radius = pipCfg.borderRadiusPx ?? 14;
    return (
      <AbsoluteFill>
        <div
          style={{
            position: "absolute",
            right,
            bottom,
            width: pipW,
            height: pipH,
            borderRadius: radius,
            overflow: "hidden",
            boxShadow:
              "0 22px 44px rgba(18, 24, 32, 0.32), 0 6px 14px rgba(18, 24, 32, 0.18)",
            // border: none (locked)
            background: "#0a0a0a",
          }}
        >
          <OffthreadVideo
            src={resolvedSrc}
            startFrom={startFrom}
            volume={vol}
            style={{
              width: "100%",
              height: "100%",
              objectFit: "cover",
              objectPosition: pipCfg.objectPosition ?? "center 28%",
              transform: `scale(${liveScale})`,
              transformOrigin: "center center",
            }}
          />
        </div>
      </AbsoluteFill>
    );
  }

  if (layout === "float_centered") {
    const widthRatio = screenCfg.widthRatio ?? 0.78;
    const maxH = height * (screenCfg.maxHeightRatio ?? 0.82);
    const floatW = Math.round(width * widthRatio);
    const cropAr =
      windowCrop && windowCrop.w > 0 && windowCrop.h > 0
        ? windowCrop.w / windowCrop.h
        : 16 / 9;
    let floatH = Math.round(floatW / cropAr);
    if (floatH > maxH) {
      floatH = Math.round(maxH);
    }
    const radius = screenCfg.borderRadiusPx ?? 24;
    const fit = (screenCfg.objectFit as string | undefined) ?? "cover";
    return (
      <AbsoluteFill>
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: floatW,
            height: floatH,
            transform: "translate(-50%, -50%)",
            borderRadius: radius,
            overflow: "hidden",
            boxShadow:
              "0 36px 70px rgba(28, 36, 48, 0.22), 0 12px 28px rgba(28, 36, 48, 0.14)",
            background: "#141414",
          }}
        >
          <CroppedVideo
            src={resolvedSrc}
            startFrom={startFrom}
            volume={vol}
            liveScale={liveScale}
            transformOrigin="center top"
            windowCrop={windowCrop}
            objectFit={fit}
          />
        </div>
      </AbsoluteFill>
    );
  }

  // full cam / edge-to-edge
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <OffthreadVideo
        src={resolvedSrc}
        startFrom={startFrom}
        volume={vol}
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
