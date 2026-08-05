import React from "react";
import { AbsoluteFill } from "remotion";

/** Shown when Studio was started without --props / empty timeline. */
export const MissingTimelineBanner: React.FC<{ reason: string }> = ({ reason }) => {
  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#1a0000",
        color: "#ffb4b4",
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
        fontSize: 28,
        padding: 64,
        justifyContent: "center",
        lineHeight: 1.45,
      }}
    >
      <div style={{ fontSize: 42, fontWeight: 800, color: "#fff", marginBottom: 24 }}>
        No episode timeline loaded
      </div>
      <div style={{ maxWidth: 1100 }}>{reason}</div>
      <div style={{ marginTop: 32, color: "#ffd0d0" }}>
        Fix: from the episode folder run{" "}
        <code style={{ color: "#fff" }}>ae compose . --studio</code>
        <br />
        That command stages media into{" "}
        <code style={{ color: "#fff" }}>public/ae-media/</code> and passes{" "}
        <code style={{ color: "#fff" }}>--props edit/remotion-props.json</code>.
      </div>
    </AbsoluteFill>
  );
};
