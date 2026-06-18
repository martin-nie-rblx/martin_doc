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
| **Resolution-independent** | Overlay geometry uses **normalized [0,1] coordinates** and `Canvas` stores only an **aspect ratio** (no fixed output pixels), so a project renders correctly at any network-adapted resolution. |
| **Deterministic timing** | All times are **int64 milliseconds** (not float seconds) to avoid drift across clients and keep keyframes/trims exact. |
| **One model, two profiles** | The same messages serve both the **authoring** (creation SDK) document and the simplified **playback** (post-transcode) output — see below. |

## One model, two profiles

`Post.profile` distinguishes the two ends of the pipeline; both reuse the exact
same messages:

- **`AUTHORING`** (creation side / editor SDK) — the full document. Media may
  still be **local, unuploaded files**; generators (TTS) may be unsynthesized;
  every trim / effect / transition / mix parameter is live and re-editable.
- **`PLAYBACK`** (consumption side) — produced **after transcoding**. The heavy
  composite (stitch + transitions + filters + the full audio mix) is **baked
  into a single transcoded media asset**, so authoring-only parameters fall
  away. Only what the player composites live (toggleable captions, interactive
  stickers) remains as `Element`s. Fields used only for editing are tagged
  `[authoring]` in the `.proto`.

This means the consumption document is typically just: a `Canvas`, one
`MAIN_VIDEO` track with a single `MediaSegment` pointing at the transcoded
asset, plus optional live `Caption` / `Sticker` overlays — a tiny subset of the
authoring schema, no new types.

## Asset references (local files → global assets)

The timeline never embeds bytes or URLs. Every clip references an entry in
`Post.assets` by a **document-local key** (`asset_ref`). The `MediaAsset` entry
holds a `source` oneof describing the current binding:

```
LocalSource  --upload-->  global_asset_id  --(input to)-->  transcode
```

- **`LocalSource`** — on-device file/capture not yet uploaded (creation side).
- **`global_asset_id`** — resolved via the global asset resolution system; the
  only binding that appears on the playback side.
- **`CatalogRef`** — licensed/built-in catalog items (music, sticker packs, sfx).

Because clips reference the stable `asset_ref` key, a clip's reference never
changes while its underlying binding migrates *local → uploaded → transcoded*.
`UploadStatus` tracks that lifecycle on the creation side.

## Core structure

```
Post  (schema_version + profile + editing content only; post id / owner / title
       are stored separately by the backend, not embedded here)
├── profile           (AUTHORING | PLAYBACK)
├── Canvas            (aspect ratio + fps + background; NO fixed output pixels)
├── Timeline
│   └── Track[]       (kind: MAIN_VIDEO | OVERLAY_VIDEO | AUDIO | CAPTION | STICKER)
│       └── Element[] (placed on the timeline via TimeRange)
│           ├── content (oneof): MediaSegment | AudioSegment | TtsSegment
│           │                    | Caption | Sticker | TextOverlay
│           ├── effects[]        (color, adjustments, blur, chroma key, named)
│           └── enter/exit Animation
├── assets: map<asset_ref, MediaAsset>  (local | global | catalog bindings)
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
  synthesized, the generated audio is materialized as an asset referenced by
  `output_asset_ref`; on playback it is mixed into the composite.
- **Caption / subtitles** — `Caption` with `TextStyle`, optional `word_timings`
  for karaoke highlighting, and a link to the audio element it transcribes
  (`source_audio_element_id`) for auto-caption + resync.
- **Sticker** — `Sticker` referencing an asset (`asset_ref`, whose binding may
  be an uploaded image/GIF/Lottie or a `CatalogRef`) or an inline unicode emoji.
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
2. **Asset storage** — the model stores **no byte locations** and **no
   rendition-specific properties** (pixel size, mime/codec, bitrate, file
   size). `MediaAsset` is a pure reference (`asset_ref` key → local / global /
   catalog binding, plus rendition-independent hints like `duration_ms`);
   clients resolve global media through the global asset resolution system,
   which is the source of truth.
3. **TTS caching** — assumes synthesized audio is materialized to an asset
   (`output_asset_ref`) for playback determinism; confirm whether on-the-fly
   synthesis is preferred.
4. **Playback bake boundary** — confirm what stays *live* on the playback side
   vs. burned into the transcoded composite. The model supports either: live
   captions/stickers remain as `Element`s; burned-in ones simply don't appear
   in the `PLAYBACK` document.
5. **Local handle format** — `LocalSource.local_handle` is intentionally opaque
   (photo-library id, content URI, temp path). Confirm the per-platform form.
