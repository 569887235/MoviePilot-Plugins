# MoviePilot-Plugins

MoviePilot V2 插件仓库，现包含独立的 `TelegraphVideo` 与 `Yurenmei` 插件。安装一个插件无需安装另一个插件，配置和数据目录各自独立。

## 余人美 / Yurenmei

- 目录：`plugins.v2/yurenmei`；市场插件名：**余人美**，默认关闭。
- 在 MoviePilot 添加本仓库后安装并启用“余人美”。入库沿用 MoviePilot 的目录选择与分类配置，无需另外填写容器目录；整理目标为 `<匹配的本地媒体库目录>/<标准分辨率>/…`，供 Emby 扫描，使用原生整理和可选刮削。媒体库目录需在 MoviePilot 中配置为本地存储。
- 先调用 `POST /api/v1/plugin/Yurenmei/recognize`，传入 `request_id`、`name`。这是纯识别，不创建 STRM 或调用整理。
- 使用 `GET /api/v1/plugin/Yurenmei/jobs/{request_id}` 获取识别结果；业务后台人工核对片名、年份、TMDB 与季集后，再调用 `POST /api/v1/plugin/Yurenmei/import`。
- 入库参数：新的 `request_id`、第一阶段 `recognition_id`、`confirmed: true`、`season`、`episode`、`resolution`、`play_url`。电影的季集为0；电视剧须人工确认季集。`play_url` 必须是业务提供的 `/play/yrm/<64位随机键>/stream` 稳定地址。
- 唯一身份是 `媒体类型 + TMDB + 季 + 集 + 标准分辨率`。720p 与1080p分别整理，同档多源共用一条STRM；完整尺寸和临时媒体URL不进入唯一键。相同任务编号重试保持相同载荷，相同身份不会重复整理或改为其他稳定地址。
- `GET /api/v1/plugin/Yurenmei/status` 返回连接状态；接口沿用 MoviePilot 默认 API Key 鉴权。识别、入库均异步串行处理，状态持久化；刷新/重启后的未确认任务明确失败，可用原任务编号重试。目标 STRM 及其内容实际存在后才记成功，不自动清理原生历史或强制覆盖。

仅本地源码实现不等于已发布至插件市场或已在真实 MoviePilot/Emby 验证。余人美业务侧还需配置 `YRM_MOVIEPILOT_URL`、`YRM_MOVIEPILOT_API_KEY` 和 `PUBLIC_ORIGIN`，并应用014迁移；凭据仅放本机/部署环境，不写入仓库。

## Telegraph Video

MoviePilot V2 plugin repository for Telegraph Video.

This repository follows the MoviePilot official plugin repository layout:

- `package.v2.json` is the V2 plugin market index.
- `plugins.v2/telegraphvideo/__init__.py` contains the `TelegraphVideo` plugin class.
- The plugin directory name is the lowercase plugin class name.
- Market metadata in `package.v2.json` must stay aligned with the `plugin_*` class fields.

Current state:

- The plugin exposes `POST /api/v1/plugin/TelegraphVideo/organize`.
- The plugin exposes `POST /api/v1/plugin/TelegraphVideo/rewrite-strm` for source-switch URL refreshes.
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
- Execute business-originated MP import tasks by writing `.strm` files containing `/play/{mediaId}/{中文规范名}.{真实后缀}`; the Chinese filename remains readable UTF-8 text and the suffix reflects the selected playback source.
- Default business `transfer` requests to forced MoviePilot transfer, pass request-level `force=true`, and clear the matching old transfer history so explicit re-import can restore MP-side items deleted outside Telegraph Video.
- Backfill scraped metadata through `POST /api/business/media/mp-backfill`.

Required behavior:

- A taken-over `.strm` is not rolled back to the original real URL.
- A source-switch rewrite must update only the existing target STRM content and must not trigger MoviePilot recognition or transfer.
- The plugin must preserve original STRM content by sending it to the business API before rewriting.
- Resource-level plugin task IDs are returned as `plugin_job_id` and stored directly on `mp_import_task`. Scan-origin requests remain identified by `scan_item_id` until the callback creates a business media resource.
