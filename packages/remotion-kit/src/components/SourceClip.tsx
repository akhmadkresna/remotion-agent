import React from "react";
import { AbsoluteFill, OffthreadVideo, useVideoConfig } from "remotion";

type Props = {
  src: string;
  sourceIn: number;
  layout: "full" | "pip_corner";
};

export const SourceClip: React.FC<Props> = ({ src, sourceIn, layout }) => {
  const { width, height, fps } = useVideoConfig();
  const startFrom = Math.max(0, Math.round(sourceIn * fps));

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
            src={src}
            startFrom={startFrom}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        </div>
      </AbsoluteFill>
    );
  }

  return (
    <AbsoluteFill>
      <OffthreadVideo
        src={src}
        startFrom={startFrom}
        style={{ width: "100%", height: "100%", objectFit: "cover" }}
      />
    </AbsoluteFill>
  );
};
