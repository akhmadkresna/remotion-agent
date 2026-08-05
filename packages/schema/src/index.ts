import { z } from "zod";

export const AsrConfigSchema = z.object({
  backend: z.enum(["auto", "whisper.cpp", "faster-whisper"]).default("auto"),
  model: z.string().default("small"),
  language: z.string().default("id"),
  word_timestamps: z.boolean().default(true),
  diarize: z.boolean().default(false),
});

export const ProjectSchema = z.object({
  id: z.string(),
  sources: z.record(z.string()).default({ cam: "raw/cam.mp4" }),
  style: z.string().default("tutorial"),
  asr: AsrConfigSchema.default({}),
  fps: z.number().int().positive().default(30),
  aspect: z.string().default("16:9"),
  width: z.number().int().positive().default(1920),
  height: z.number().int().positive().default(1080),
});

export const TranscriptWordSchema = z.object({
  type: z.string().optional(),
  word: z.string().optional(),
  text: z.string().optional(),
  start: z.number(),
  end: z.number(),
  score: z.number().optional(),
  speaker_id: z.union([z.string(), z.number()]).optional(),
});

export const TranscriptSchema = z.object({
  language: z.string(),
  backend: z.string(),
  model: z.string(),
  words: z.array(TranscriptWordSchema),
  segments: z
    .array(
      z.object({
        start: z.number(),
        end: z.number(),
        text: z.string(),
      }),
    )
    .default([]),
});

export const EdlRangeSchema = z.object({
  source: z.string(),
  start: z.number(),
  end: z.number(),
  note: z.string().optional(),
  beat: z.string().optional(),
});

export const EdlSchema = z.object({
  sources: z.record(z.string()),
  ranges: z.array(EdlRangeSchema).min(1),
  grade: z.string().nullable().optional(),
});

/** Fake 2–3 cam framing presets (single source, digital crop). */
export const FramingSchema = z.enum(["wide", "medium", "close"]);
export const FramingMotionSchema = z.enum([
  "hold",
  "snap",
  "ease",
  "ease_in",
  "ease_out",
  "drift",
]);

export const CoverEventSchema = z.object({
  type: z.enum([
    "screen",
    "screen_full",
    "pip",
    "screen_pip",
    "punch_in",
    "punch",
    "punch_out",
    "framing",
  ]),
  source: z.string().optional(),
  start: z.number(),
  end: z.number(),
  duration: z.number().optional(),
  scale: z.number().optional(),
  framing: FramingSchema.optional(),
  motion: FramingMotionSchema.optional(),
  note: z.string().optional(),
});

export const CameraPlaySchema = z.object({
  /** Alternate home/alt framing at each EDL join when no framing event wins. */
  snap_on_cuts: z.boolean().default(true),
  home: FramingSchema.default("medium"),
  alt: FramingSchema.default("close"),
  /** Use wide on topic-reset beats (notes containing reset/lesson/howto/outro). */
  wide_on_resets: z.boolean().default(true),
  scales: z
    .object({
      wide: z.number().default(1.0),
      medium: z.number().default(1.1),
      close: z.number().default(1.18),
    })
    .default({}),
});

export const CoverSchema = z.object({
  camera_play: CameraPlaySchema.default({}),
  events: z.array(CoverEventSchema).default([]),
  captions: z
    .array(
      z.object({
        text: z.string(),
        start: z.number(),
        end: z.number(),
      }),
    )
    .default([]),
});

export const TimelineClipSchema = z.object({
  id: z.string(),
  track: z.string(),
  source: z.string(),
  sourceIn: z.number(),
  sourceOut: z.number(),
  fromSec: z.number(),
  durationSec: z.number(),
  layout: z.enum(["full", "pip_corner"]).default("full"),
  framing: FramingSchema.default("medium"),
  scale: z.number().default(1),
  motion: FramingMotionSchema.default("snap"),
});

export const TimelineSchema = z.object({
  fps: z.number(),
  width: z.number(),
  height: z.number(),
  durationInFrames: z.number(),
  durationSec: z.number(),
  sources: z.record(z.string()),
  clips: z.array(TimelineClipSchema),
  effects: z
    .array(
      z.object({
        type: z.enum(["punch_in", "punch_out"]),
        fromSec: z.number(),
        durationSec: z.number(),
        scale: z.number().default(1.15),
      }),
    )
    .default([]),
  captions: z
    .array(
      z.object({
        text: z.string(),
        start: z.number(),
        end: z.number(),
      }),
    )
    .default([]),
});

export type Project = z.infer<typeof ProjectSchema>;
export type Transcript = z.infer<typeof TranscriptSchema>;
export type Edl = z.infer<typeof EdlSchema>;
export type Cover = z.infer<typeof CoverSchema>;
export type Timeline = z.infer<typeof TimelineSchema>;
export type Framing = z.infer<typeof FramingSchema>;
export type FramingMotion = z.infer<typeof FramingMotionSchema>;
