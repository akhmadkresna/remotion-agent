import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  DEFAULT_OVERLAY_STYLE,
  type OverlayStyle,
  type TimelineOverlay,
} from "../types";

const DISPLAY =
  'Syne, "Segoe UI", "Helvetica Neue", Arial, sans-serif';
const UI = '"Instrument Sans", "Segoe UI", system-ui, sans-serif';

function useStyle(style?: OverlayStyle) {
  return {
    ...DEFAULT_OVERLAY_STYLE,
    ...style,
    fonts: { ...DEFAULT_OVERLAY_STYLE.fonts, ...style?.fonts },
  };
}

function Enter({ children }: { children: React.ReactNode }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 18, stiffness: 140 } });
  const y = interpolate(s, [0, 1], [14, 0]);
  const opacity = interpolate(frame, [0, 8], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div style={{ opacity, transform: `translateY(${y}px)` }}>{children}</div>
  );
}

const Chapter: React.FC<{
  ov: TimelineOverlay;
  style: ReturnType<typeof useStyle>;
  h: number;
}> = ({ ov, style, h }) => (
  <div
    style={{
      position: "absolute",
      left: "4.5%",
      top: "14%",
      maxWidth: "42%",
      color: style.ink,
      textShadow: "0 8px 28px rgba(0,0,0,0.55)",
    }}
  >
    <Enter>
      {ov.kicker ? (
        <div
          style={{
            fontFamily: UI,
            fontSize: Math.round(h * 0.024),
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: style.accent,
            marginBottom: Math.round(h * 0.012),
          }}
        >
          {ov.kicker}
        </div>
      ) : null}
      <div
        style={{
          fontFamily: DISPLAY,
          fontWeight: 800,
          fontSize: Math.round(h * 0.09),
          lineHeight: 0.98,
          letterSpacing: "-0.03em",
        }}
      >
        {ov.text || ov.title}
      </div>
    </Enter>
  </div>
);

const Emphasis: React.FC<{
  ov: TimelineOverlay;
  style: ReturnType<typeof useStyle>;
  h: number;
  w: number;
}> = ({ ov, style, h, w }) => {
  const frame = useCurrentFrame();
  const line = interpolate(frame, [6, 18], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const parts = (ov.text || "").split(/\s+/).filter(Boolean);
  const head = parts.slice(0, -1).join(" ");
  const tail = parts.slice(-1)[0] || ov.text || "";
  return (
    <div
      style={{
        position: "absolute",
        left: "4.5%",
        bottom: "16%",
        maxWidth: "55%",
        color: style.ink,
        textShadow: "0 8px 28px rgba(0,0,0,0.55)",
      }}
    >
      <Enter>
        <div
          style={{
            fontFamily: DISPLAY,
            fontWeight: 800,
            fontSize: Math.round(h * 0.14),
            lineHeight: 0.92,
            letterSpacing: "-0.04em",
          }}
        >
          {head ? (
            <>
              {head}{" "}
              <span style={{ color: style.accent }}>{tail}</span>
            </>
          ) : (
            <span style={{ color: style.accent }}>{tail}</span>
          )}
        </div>
        <div
          style={{
            marginTop: Math.round(h * 0.02),
            width: Math.round(w * 0.22),
            height: 3,
            background: style.accent,
            transform: `scaleX(${line})`,
            transformOrigin: "left center",
          }}
        />
      </Enter>
    </div>
  );
};

const Diagram: React.FC<{
  ov: TimelineOverlay;
  style: ReturnType<typeof useStyle>;
  h: number;
}> = ({ ov, style, h }) => {
  const steps = ov.steps || [];
  return (
    <div
      style={{
        position: "absolute",
        left: "4.5%",
        top: "12%",
        maxWidth: "40%",
        color: style.ink,
        textShadow: "0 8px 24px rgba(0,0,0,0.5)",
      }}
    >
      <Enter>
        <div
          style={{
            fontFamily: UI,
            fontSize: Math.round(h * 0.024),
            fontWeight: 600,
            letterSpacing: "0.14em",
            textTransform: "uppercase",
            color: style.dim,
            marginBottom: Math.round(h * 0.01),
          }}
        >
          {ov.kicker || "Flow"}
        </div>
        <div
          style={{
            fontFamily: DISPLAY,
            fontWeight: 800,
            fontSize: Math.round(h * 0.055),
            letterSpacing: "-0.02em",
            marginBottom: Math.round(h * 0.022),
          }}
        >
          {ov.title || ov.text}
        </div>
        <div style={{ display: "grid", gap: Math.round(h * 0.012) }}>
          {steps.map((step, i) => (
            <div
              key={`${i}-${step}`}
              style={{
                display: "grid",
                gridTemplateColumns: "auto 1fr",
                gap: 14,
                alignItems: "center",
                fontFamily: UI,
                fontWeight: 700,
                fontSize: Math.round(h * 0.036),
              }}
            >
              <span style={{ color: style.accent }}>{i + 1}</span>
              <span>{step}</span>
            </div>
          ))}
        </div>
      </Enter>
    </div>
  );
};

const Chip: React.FC<{
  ov: TimelineOverlay;
  style: ReturnType<typeof useStyle>;
  h: number;
}> = ({ ov, style, h }) => (
  <div
    style={{
      position: "absolute",
      left: "4.5%",
      top: "12%",
      display: "inline-flex",
      alignItems: "center",
      gap: 10,
      color: style.ink,
      fontFamily: UI,
      fontWeight: 600,
      fontSize: Math.round(h * 0.034),
      textShadow: "0 6px 18px rgba(0,0,0,0.5)",
    }}
  >
    <Enter>
      <span
        style={{
          width: Math.round(h * 0.016),
          height: Math.round(h * 0.016),
          borderRadius: "50%",
          background: style.accent,
          display: "inline-block",
        }}
      />
      {ov.text}
    </Enter>
  </div>
);

const OneOverlay: React.FC<{
  ov: TimelineOverlay;
  styleTokens?: OverlayStyle;
}> = ({ ov, styleTokens }) => {
  const { height, width } = useVideoConfig();
  const style = useStyle(styleTokens);
  if (ov.kind === "chapter") return <Chapter ov={ov} style={style} h={height} />;
  if (ov.kind === "emphasis")
    return <Emphasis ov={ov} style={style} h={height} w={width} />;
  if (ov.kind === "diagram") return <Diagram ov={ov} style={style} h={height} />;
  if (ov.kind === "chip") return <Chip ov={ov} style={style} h={height} />;
  return null;
};

export const OverlayLayer: React.FC<{
  overlays: TimelineOverlay[];
  styleTokens?: OverlayStyle;
}> = ({ overlays, styleTokens }) => {
  const { fps } = useVideoConfig();
  if (!overlays?.length) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: "none" }}>
      {overlays.map((ov) => {
        const from = Math.round(ov.fromSec * fps);
        const duration = Math.max(1, Math.round(ov.durationSec * fps));
        return (
          <Sequence key={ov.id} from={from} durationInFrames={duration} name={ov.id}>
            <AbsoluteFill
              style={{
                background:
                  "linear-gradient(90deg, rgba(0,0,0,0.42) 0%, rgba(0,0,0,0.1) 32%, transparent 50%)",
              }}
            />
            <OneOverlay ov={ov} styleTokens={styleTokens} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
