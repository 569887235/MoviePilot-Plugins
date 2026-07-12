# telegraph-video-mp-plugin

MoviePilot V2 plugin repository for Telegraph Video.

This repository follows the MoviePilot official plugin repository layout:

- `package.v2.json` is the V2 plugin market index.
- `plugins.v2/telegraphvideo/__init__.py` contains the `TelegraphVideo` plugin class.
- The plugin directory name is the lowercase plugin class name.
- Market metadata in `package.v2.json` must stay aligned with the `plugin_*` class fields.

Current state:

- The plugin exposes `POST /api/v1/plugin/TelegraphVideo/organize`.
- The organize endpoint calls MoviePilot `TransferChain().manual_transfer(...)`.
- Enable the plugin interface in MoviePilot plugin settings before calling it.

Install in MoviePilot:

1. Publish this repository to `https://github.com/569887235/MoviePilot-Plugins` on the `main` branch.
2. Add `https://github.com/569887235/MoviePilot-Plugins` as a third-party plugin repository in MoviePilot.
3. Refresh the plugin market and install `Telegraph Video`.

Responsibilities:

- Discover existing MP media items and `.strm` files.
- Push MP media to `POST /api/business/media/mp-push`.
- Rewrite MP `.strm` files to the returned business play URL.
- Execute business-originated MP import tasks by writing `.strm` files containing `/play/{mediaId}`.
- Default business `transfer` requests to forced MoviePilot transfer, pass request-level `force=true`, and clear the matching old transfer history so explicit re-import can restore MP-side items deleted outside Telegraph Video.
- Backfill scraped metadata through `POST /api/business/media/mp-backfill`.

Required behavior:

- A taken-over `.strm` is not rolled back to the original real URL.
- The plugin must preserve original STRM content by sending it to the business API before rewriting.
- Resource-level plugin task IDs are returned as `plugin_job_id` and stored directly on `mp_import_task`. Scan-origin requests remain identified by `scan_item_id` until the callback creates a business media resource.
