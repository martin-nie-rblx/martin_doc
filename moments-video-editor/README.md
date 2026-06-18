# Roblox Moments — Video Editor Data Model

A protobuf schema (`editing_model.proto`) that fully represents an editing
session for a Roblox Moments post (image or video) with all editing tools:
**stitch, music, voice over, text-to-speech, captions, stickers, text, filters,
transitions, and animations**.

## Design goals

| Goal | How the schema achieves it |
| --- | --- |
| **Declarative & reproducible** | The `Post` document fully describes the rendered output. A renderer can reproduce the final video from the document + referenced assets alone. |
| **Non-destructive** | Source media is referenced via `MediaAsset` and never mutated. Trims, speed, volume, crops, filters, and transforms are all parameters. |
| **Composable** | A standard layered **Timeline → Track → Element** model (like every modern NLE) lets stitch / overlay / audio / caption / sticker compose on a shared time axis. |
| **Extensible** | New tools become new variants of the `Element` `oneof` or new `Effect` types. `NamedEffect` + `extra` maps give an escape hatch with no schema break. |
| **Resolution-independent** | Overlay geometry uses **normalized [0,1] coordinates**, so a project renders correctly at any output resolution. |
| **Deterministic timing** | All times are **int64 milliseconds** (not float seconds) to avoid drift across clients and keep keyframes/trims exact. |

## Core structure

```
Post  (schema_version + editing content only; post id / owner / title are
       stored separately by the backend, not embedded here)
├── Canvas            (output: resolution, fps, aspect ratio, image vs video)
├── Timeline
│   └── Track[]       (kind: MAIN_VIDEO | OVERLAY_VIDEO | AUDIO | CAPTION | STICKER)
│       └── Element[] (placed on the timeline via TimeRange)
│           ├── content (oneof): MediaSegment | AudioSegment | TtsSegment
│           │                    | Caption | Sticker | TextOverlay
│           ├── effects[]        (color, adjustments, blur, chroma key, named)
│           └── enter/exit Animation
├── assets: map<id, MediaAsset>  (the shared source library)
└── publish: PublishMetadata     (description, hashtags, cover, visibility)
```

The key idea: an **`Element`** is any placed item on a track. Its
`oneof content` selects which editing tool produced it. Everything shares
timeline placement (`TimeRange`), a stack of `Effect`s, and enter/exit
animations.

## How each requested tool maps to the model

- **Video stitch** — multiple `MediaSegment` elements placed end-to-end on a
  `MAIN_VIDEO` track. Each has its own `SourceTrim`, `speed`, `reverse`, and a
  `Transition` between neighbors (crossfade, slide, etc.). No special "stitch"
  object is needed — sequential segments *are* the stitch.
- **Music** — `AudioSegment` with `kind = MUSIC` on an `AUDIO` track, with
  `AudioProperties` for volume, fade in/out, and optional `Ducking` (auto-lower
  music under voiceover).
- **Voice over** — `AudioSegment` with `kind = VOICEOVER` (user-recorded).
- **Text-to-speech** — `TtsSegment` (text + voice/pitch/rate/language). Once
  synthesized, the generated clip is cached as an asset via `cached_asset_id`.
- **Caption / subtitles** — `Caption` with `TextStyle`, optional `word_timings`
  for karaoke highlighting, and a link to the audio element it transcribes
  (`source_audio_element_id`) for auto-caption + resync.
- **Sticker** — `Sticker` sourced from an uploaded asset, a built-in catalog id,
  or a unicode emoji; static, animated (GIF/Lottie), or emoji.
- **Free text / titles** — `TextOverlay`.
- **Filters / color / blur / green-screen** — stackable `Effect`s on any element.
- **Motion** — `Transform.keyframes` animate position/scale/rotation/opacity;
  `Animation` covers preset enter/exit (fade, pop, slide).

## Conventions

- **Time**: `int64` milliseconds on the project timeline. `TimeRange` is a
  half-open interval `[start_ms, start_ms + duration_ms)`. `SourceTrim` is in
  *source* media time, not timeline time.
- **Geometry**: normalized `[0,1]` relative to the canvas, `(0,0)` top-left.
  `Transform.anchor` defaults to `(0.5,0.5)` (center).
- **Color**: sRGB, straight alpha, channels `0..1`.
- **Compositing order**: `Track.z_order` ascending = back-to-front.

## Extensibility notes

- Add a new tool → add a variant to `Element.content`. Old clients ignore
  unknown variants (proto3 forward-compatibility) and can skip rendering them.
- Add a new effect → add to `Effect.effect` oneof, or ship it immediately via
  `NamedEffect` (id + float/string param maps) with no schema change.
- `schema_version` + `EditTimestamps.last_editor_app_version` support document
  migration across app releases.

## Open questions / assumptions to confirm

1. **Image posts / slideshows** — modeled as `MediaSegment`s with `IMAGE`
   assets on the main track (each with its own duration). Confirm whether
   slideshow transitions need a dedicated type.
2. **Asset storage** — the model stores **no byte locations**. `MediaAsset` is a
   pure reference (`asset_id` + optional cached hints); clients resolve media
   through the global asset resolution system, which is the source of truth.
3. **TTS caching** — assumes synthesized audio is materialized to an asset for
   playback determinism; confirm whether on-the-fly synthesis is preferred.
4. **Server vs client rendering** — schema is render-target-agnostic; confirm
   whether the same document drives both preview (client) and final export
   (server) to keep them consistent.
