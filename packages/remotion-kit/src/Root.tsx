import React from "react";
import { Composition, getInputProps } from "remotion";
import { AgenticTimeline } from "./Composition";
import type { TimelineProps } from "./types";
import { emptyTimeline } from "./types";

/**
 * Props come from Remotion CLI: `remotion studio … --props=…/remotion-props.json`
 * (`ae compose --studio` passes this).
 */
const loadDefaultProps = (): TimelineProps => {
  const fromCli = getInputProps() as Partial<TimelineProps>;
  if (fromCli?.timeline) {
    return { timeline: fromCli.timeline };
  }
  console.warn(
    "No timeline props — use: ae compose <episode> --studio (passes --props). Using empty timeline.",
  );
  return { timeline: emptyTimeline };
};

export const RemotionRoot: React.FC = () => {
  const defaults = loadDefaultProps();
  const tl = defaults.timeline;
  return (
    <>
      <Composition
        id="AgenticTimeline"
        component={AgenticTimeline}
        durationInFrames={Math.max(1, tl.durationInFrames || 30 * 10)}
        fps={tl.fps || 30}
        width={tl.width || 1920}
        height={tl.height || 1080}
        defaultProps={defaults}
        calculateMetadata={async ({ props }) => {
          const t = props.timeline;
          return {
            durationInFrames: Math.max(1, t.durationInFrames || 1),
            fps: t.fps || 30,
            width: t.width || 1920,
            height: t.height || 1080,
          };
        }}
      />
    </>
  );
};
