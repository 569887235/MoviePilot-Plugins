import logging
from typing import Any, Dict

try:
    from app.log import logger
except Exception:  # pragma: no cover - fallback for local syntax checks
    logger = logging.getLogger(__name__)

from app.plugins import _PluginBase


class TelegraphVideo(_PluginBase):
    # Plugin metadata must stay in sync with package.v2.json.
    plugin_name = "Telegraph Video"
    plugin_desc = "Telegraph Video MP 接入插件骨架，用于后续接管 STRM 与同步媒体资源。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/Moviepilot_A.png"
    plugin_version = "0.1.1"
    plugin_author = "telegraph-video"
    plugin_config_prefix = "telegraphvideo_"
    plugin_order = 1
    auth_level = 1

    def init_plugin(self, config: dict = None):
        self._config = config or {}
        logger.info(f"[TelegraphVideo] 插件初始化，enabled={bool(self._config.get('enabled'))}")

    def get_state(self) -> bool:
        return bool(self._config.get("enabled"))

    @staticmethod
    def get_command() -> list:
        return []

    def get_api(self) -> list:
        return [
            {
                "path": "/organize",
                "endpoint": self.organize,
                "methods": ["POST"],
                "summary": "Telegraph Video scan item organize",
                "description": "接受业务系统扫描到的视频/STRM条目，并调用 MoviePilot 原生能力整理后返回媒体信息。",
            }
        ]

    def _payload_summary(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "scan_task_id": payload.get("scan_task_id"),
            "scan_item_id": payload.get("scan_item_id"),
            "source_id": payload.get("source_id"),
            "source_path": payload.get("source_path"),
            "source_name": payload.get("source_name"),
            "file_kind": payload.get("file_kind"),
            "file_ext": payload.get("file_ext"),
            "file_size": payload.get("file_size"),
        }

    def organize(self, payload: Dict[str, Any]) -> dict:
        summary = self._payload_summary(payload or {})
        logger.info(f"[TelegraphVideo] 收到整理请求: {summary}")
        try:
            if not self._config.get("enabled"):
                logger.warning(f"[TelegraphVideo] 整理请求被拒绝，插件未启用: {summary}")
                return {
                    "success": False,
                    "message": "Telegraph Video 插件未启用，无法执行整理。",
                }

            # TODO: Wire this to MoviePilot's native transfer/scrape/organize service once
            # the target MP runtime API is confirmed. Returning success here without MP's
            # result would make the business database believe the file has been organized.
            logger.warning(f"[TelegraphVideo] 整理请求未执行，MP 原生整理接口尚未接入: {summary}")
            return {
                "success": False,
                "message": "MP 原生整理接口尚未接入 Telegraph Video 插件。",
                "source_path": payload.get("source_path"),
                "source_name": payload.get("source_name"),
                "scan_item_id": payload.get("scan_item_id"),
            }
        except Exception as err:
            logger.exception(f"[TelegraphVideo] 整理请求处理异常: {summary}")
            return {
                "success": False,
                "message": f"Telegraph Video 插件整理异常: {err}",
                "scan_item_id": payload.get("scan_item_id") if payload else None,
            }

    def get_service(self) -> list:
        return []

    def get_form(self) -> tuple[list, dict]:
        return [
            {
                "component": "VSwitch",
                "model": "enabled",
                "label": "启用插件接口",
            }
        ], {"enabled": False}

    def get_page(self) -> list:
        return []

    def stop_service(self):
        pass
