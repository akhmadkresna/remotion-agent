export type Framing = "wide" | "medium" | "close";
export type FramingMotion =
  | "hold"
  | "snap"
  | "ease"
  | "ease_in"
  | "ease_out"
  | "drift";

export type ClipLayout = "full" | "float_centered" | "pip_corner";

export type WindowCropNorm = {
  x: number;
  y: number;
  w: number;
  h: number;
};

export type TimelineClip = {
  id: string;
  track: string;
  source: string;
  sourceIn: number;
  sourceOut: number;
  fromSec: number;
  durationSec: number;
  layout: ClipLayout;
  framing: Framing;
  scale: number;
  motion: FramingMotion;
  /** When true (or source !== cam), clip is silent — audio always from cam. */
  muted?: boolean;
  /** Normalized smart-window crop (0–1 of source frame). */
  windowCrop?: WindowCropNorm;
};

export type PunchEffect = {
  type: "punch_in" | "punch_out";
  fromSec: number;
  durationSec: number;
  scale: number;
};

export type Caption = {
  text: string;
  start: number;
  end: number;
};

export type OverlayKind = "chapter" | "emphasis" | "diagram" | "chip";

export type TimelineOverlay = {
  id: string;
  kind: OverlayKind;
  fromSec: number;
  durationSec: number;
  text?: string;
  kicker?: string;
  title?: string;
  steps?: string[];
  note?: string;
};

export type ScreenExplainerStyle = {
  preset?: string;
  canvas?: {
    background?: string;
    backgroundDeep?: string;
    gradient?: string;
  };
  screen?: {
    presentation?: string;
    widthRatio?: number;
    maxHeightRatio?: number;
    borderRadiusPx?: number;
    objectFit?: string;
  };
  pip?: {
    anchor?: string;
    widthRatio?: number;
    aspectRatio?: string;
    insetRightRatio?: number;
    insetBottomRatio?: number;
    borderRadiusPx?: number;
    border?: string;
    objectFit?: string;
    objectPosition?: string;
  };
};

/** Locked A-roll MG: bold type + cool mist sky accent (mirror styles/tutorial). */
export type OverlayStyle = {
  preset?: string;
  treatment?: "bold";
  accent?: string;
  accentName?: string;
  ink?: string;
  dim?: string;
  fonts?: { display?: string; ui?: string };
  chapter?: {
    leftCqw?: number;
    topCqh?: number;
    maxWidthCqw?: number;
    kickerSizeCqh?: number;
    titleSizeCqh?: number;
  };
  emphasis?: {
    leftCqw?: number;
    bottomCqh?: number;
    sizeCqh?: number;
    underline?: boolean;
  };
  diagram?: {
    leftCqw?: number;
    topCqh?: number;
    maxWidthCqw?: number;
    stepSizeCqh?: number;
  };
  chip?: {
    leftCqw?: number;
    topCqh?: number;
    sizeCqh?: number;
  };
};

export const DEFAULT_OVERLAY_STYLE: OverlayStyle = {
  preset: "bold_mist",
  treatment: "bold",
  accent: "#7dd3fc",
  accentName: "cool_mist_sky",
  ink: "#ffffff",
  dim: "rgba(255,255,255,0.55)",
  fonts: {
    display: "Syne",
    ui: "Instrument Sans",
  },
  chapter: { leftCqw: 4.5, topCqh: 12, maxWidthCqw: 42 },
  emphasis: { leftCqw: 4.5, bottomCqh: 28, sizeCqh: 16, underline: true },
  diagram: { leftCqw: 4.5, topCqh: 10, maxWidthCqw: 40 },
  chip: { leftCqw: 4.5, topCqh: 10, sizeCqh: 3.4 },
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
  overlays?: TimelineOverlay[];
  presentation?: {
    screenExplainer?: ScreenExplainerStyle;
    overlays?: OverlayStyle;
  };
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
  overlays: [],
};

/** Locked cozy + cool mist defaults (mirror styles/tutorial). */
export const DEFAULT_SCREEN_EXPLAINER: ScreenExplainerStyle = {
  preset: "cozy",
  canvas: {
    background: "#d9e2ec",
    backgroundDeep: "#c4d0dc",
    gradient: "radial",
  },
  screen: {
    presentation: "float_centered",
    widthRatio: 0.78,
    maxHeightRatio: 0.82,
    borderRadiusPx: 24,
    objectFit: "cover",
  },
  pip: {
    anchor: "stage_lower_right",
    widthRatio: 0.18,
    aspectRatio: "4:5",
    insetRightRatio: 0.035,
    insetBottomRatio: 0.045,
    borderRadiusPx: 14,
    border: "none",
    objectFit: "cover",
    objectPosition: "center 28%",
  },
};
