# Sample edit documents

Each file is a protobuf **text-format** (`.textproto`) instance of the `Post`
message from [`../editing_model.proto`](../editing_model.proto). They show how
common editing cases are represented in the data model.

Because they are real text-format protos, they parse directly into a `Post`:

```python
from google.protobuf import text_format
import editing_model_pb2 as pb   # generated from editing_model.proto

post = text_format.Parse(open("01_single_video.textproto").read(), pb.Post())
```

### Validating

[`../validate.py`](../validate.py) compiles the schema and parses every sample,
so these stay in lock-step with `editing_model.proto`:

```bash
pip install grpcio-tools
python3 moments-video-editor/validate.py
```

All samples are confirmed to parse against the current schema.

## Cases

| File | Scenario |
| --- | --- |
| `01_single_video.textproto` | One video, no edits — the minimal Moment. |
| `02_video_with_audio.textproto` | Video + one background music track. |
| `03_video_with_multiple_audios.textproto` | Video + music + voiceover + sfx, with music ducking under the voiceover. |
| `04_video_with_sticker.textproto` | Video + an animated catalog sticker and an inline emoji with pop/fade animations. |
| `05_video_with_caption.textproto` | Video + two sequential captions, the second karaoke-timed per word. |
| `06_video_with_music_and_caption.textproto` | Video + music bed + a styled caption (typical combined case). |
| `07_two_video_stitch.textproto` | Two clips stitched with a crossfade; clip A trimmed + slowed, clip B a not-yet-uploaded local file. |
| `08_video_with_tts_and_caption.textproto` | Video + text-to-speech narration + a caption linked to the TTS for resync. |
| `09_image_slideshow.textproto` | Image post: three stills in sequence with slide transitions + music (`post_type: IMAGE`). |
| `10_playback_transcoded.textproto` | The `PLAYBACK` profile for case 06 after transcoding: the composite baked into one asset, caption kept live. Same messages, far fewer fields. |

## Things to notice across the cases

- **Stitch = sequential `MediaSegment`s** on the `MAIN_VIDEO` track (cases 07, 09);
  no dedicated stitch object.
- **Tracks layer by `z_order`**; captions/stickers sit above the video.
- **Assets are referenced by a document-local `asset_ref` key**; the
  `MediaAsset` entry decides the binding (`global_asset_id`, `local`, or
  `catalog`). Case 07 shows a `local` (pre-upload) binding alongside a global one.
- **Times are milliseconds**; `source_trim` is in source-media time, everything
  else is timeline time.
- **Geometry is normalized `[0,1]`** on the canvas (see the `transform` blocks).
- **Authoring vs playback**: compare `06` (authoring) with `10` (playback) to
  see the same schema carry the rich edit and its simplified transcoded output.

> Note: proto3 scalar fields default to zero. For multiplier-style fields
> (`speed`, `volume`, `opacity`, `scale`) a renderer should treat an unset value
> as the natural unity (1.0), not literal zero. The samples set these explicitly
> wherever it affects the result.
