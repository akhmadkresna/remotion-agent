export type TimelineClip = {
  id: string;
  track: string;
  source: string;
  sourceIn: number;
  sourceOut: number;
  fromSec: number;
  durationSec: number;
  layout: "full" | "pip_corner";
};

export type PunchEffect = {
  type: "punch_in";
  fromSec: number;
  durationSec: number;
  scale: number;
};

export type Caption = {
  text: string;
  start: number;
  end: number;
};

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  durationSec: number;
  sources: Record<string, string>;
  clips: TimelineClip[];
  effects: PunchEffect[];
  captions: Caption[];
};

export type TimelineProps = {
  timeline: Timeline;
};

export const emptyTimeline: Timeline = {
  fps: 30,
  width: 1920,
  height: 1080,
  durationInFrames: 90,
  durationSec: 3,
  sources: {},
  clips: [],
  effects: [],
  captions: [],
};
