# Launch video clips

`clips.mjs` records the launch video's raw clips from the real viewer with Playwright, each clip its own file, in
landscape (1920×1080) and portrait (1080×1350). The camera moves are scripted through `window.__dbg`; the cursor is
hidden except for the clicks and drags that matter, where a drawn cursor shows.

| # | Clip | Length | What it shows |
|---|------|--------|---------------|
| 01 | `timeline` | 15 s | The timeline playing from 1100 to today over Gamla stan and the Norrström, the camera slowly turning |
| 02 | `hills` | 12 s | The Hills slider dragged from flat to 2.5×, the camera low at Söder's cliffs |
| 03 | `cards` | 18 s | Three Gamla stan building cards with photos, clicked open in turn |
| 04 | `search` | 12 s | "Götgatan" typed into search, the flight there, a card open |
| 05 | `bluehour` | 10 s | The Blå timmen look chosen, then a slow orbit over the water |
| 06 | `scene` | 15 s | The history scene `?scene=vasa-1628`: past its warning, three beats |

## Command

Needs Node 22+, `npm ci` and `npx playwright install chromium`, and a server of this checkout on any port but 8642
(the owner's preview of the main checkout; the script refuses it):

```sh
python3 scripts/serve.py 8653
HFH_PORT=8653 node scripts/record/clips.mjs /tmp/hfh-clips
# options: --url http://127.0.0.1:8653/  --clips timeline,hills  --formats landscape|portrait|landscape,portrait
```

The out folder (default `/tmp/hfh-clips`) must be outside the repository. Each clip is written as
`<nn>-<clip>-<format>.webm`, with a `.json` beside it. Playwright records from the moment the page starts loading:
with `ffmpeg` on the PATH the video is cut to the clip, and without it the `.json`'s `trimStart` says where the clip
starts.

Notes:
- Record from the whole-city build. On the fixture (`HFH_FIXTURE=1`, Gamla stan and Riddarholmen only), the clips run,
  but some show little: no Söder cliffs, no Götgatan.
- The viewer has no place search yet. Until it does, `search` flies to the Götgatan street name and says so. Once a
  search box exists (`input[type=search]` outside the people filter), the script types into it.
- Headless Chromium renders with a software GPU here; on the owner's machine, the frame rate depends on the GPU.
