# telegraph-video-mp-plugin

MP plugin placeholder.

Responsibilities:

- Discover existing MP media items and `.strm` files.
- Push MP media to `POST /api/business/media/mp-push`.
- Rewrite MP `.strm` files to the returned business play URL.
- Execute business-originated MP import tasks by writing `.strm` files containing `/play/{mediaId}`.
- Backfill scraped metadata through `POST /api/business/media/mp-backfill`.

Required behavior:

- A taken-over `.strm` is not rolled back to the original real URL.
- The plugin must preserve original STRM content by sending it to the business API before rewriting.
- Plugin task IDs should be written back to `mp_import_task_item.plugin_task_id` once the plugin protocol is implemented.
