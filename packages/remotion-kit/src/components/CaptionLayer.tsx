import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import type { Caption } from "../types";

type Props = { captions: Caption[] };

export const CaptionLayer: React.FC<Props> = ({ captions }) => {
  const frame = useCurrentFrame();
  const { fps, height } = useVideoConfig();
  const t = frame / fps;
  const active = captions.filter((c) => t >= c.start && t <= c.end);
  if (!active.length) return null;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "flex-end",
        alignItems: "center",
        paddingBottom: Math.round(height * 0.12),
        pointerEvents: "none",
      }}
    >
      {active.map((c, i) => (
        <div
          key={`${c.start}-${i}`}
          style={{
            fontFamily: "Helvetica, Arial, sans-serif",
            fontWeight: 800,
            fontSize: 54,
            color: "#fff",
            textTransform: "uppercase",
            textAlign: "center",
            textShadow: "0 2px 8px rgba(0,0,0,0.85)",
            maxWidth: "80%",
            lineHeight: 1.15,
          }}
        >
          {c.text}
        </div>
      ))}
    </AbsoluteFill>
  );
};
