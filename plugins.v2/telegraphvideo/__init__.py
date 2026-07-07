import logging
from pathlib import Path
from typing import Any, Dict, Optional

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
    plugin_version = "0.1.3"
    plugin_author = "telegraph-video"
    plugin_config_prefix = "telegraphvideo_"
    plugin_order = 1
    auth_level = 1

    def init_plugin(self, config: dict = None):
        self._config = config or {}
        logger.info(
            "[TelegraphVideo] 插件初始化，"
            f"enabled={bool(self._config.get('enabled'))}, "
            f"source_storage={self._config.get('source_storage') or 'local'}, "
            f"target_storage={self._config.get('target_storage') or None}, "
            f"target_path={self._config.get('target_path') or None}, "
            f"transfer_type={self._config.get('transfer_type') or None}, "
            f"scrape={self._config.get('scrape')}"
        )

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

    def _source_storage(self, payload: Dict[str, Any]) -> str:
        return (
            payload.get("source_storage")
            or payload.get("storage")
            or self._config.get("source_storage")
            or "local"
        )

    @staticmethod
    def _file_type(path: str, storage: str, payload: Dict[str, Any]) -> str:
        if payload.get("file_type") in {"file", "dir"}:
            return payload["file_type"]
        if payload.get("type") in {"file", "dir"}:
            return payload["type"]
        if storage == "local" and Path(path).is_dir():
            return "dir"
        return "dir" if str(path).endswith("/") else "file"

    @staticmethod
    def _as_bool(value: Any) -> Optional[bool]:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}

    def _transfer_options(self) -> Dict[str, Any]:
        target_path = self._config.get("target_path") or None
        return {
            "target_storage": self._config.get("target_storage") or None,
            "target_path": Path(target_path) if target_path else None,
            "transfer_type": self._config.get("transfer_type") or None,
            "scrape": self._as_bool(self._config.get("scrape")),
            "force": self._as_bool(self._config.get("force")) or False,
            "background": self._as_bool(self._config.get("background")) or False,
        }

    def organize(self, payload: Dict[str, Any]) -> dict:
        payload = payload or {}
        summary = self._payload_summary(payload)
        logger.info(f"[TelegraphVideo] 收到整理请求: {summary}")
        try:
            if not self._config.get("enabled"):
                logger.warning(f"[TelegraphVideo] 整理请求被拒绝，插件未启用: {summary}")
                return {
                    "success": False,
                    "message": "Telegraph Video 插件未启用，无法执行整理。",
                }

            source_path = payload.get("source_path")
            if not source_path:
                logger.warning(f"[TelegraphVideo] 整理请求缺少 source_path: {summary}")
                return {
                    "success": False,
                    "message": "整理请求缺少 source_path。",
                    "scan_item_id": payload.get("scan_item_id"),
                }

            source_storage = self._source_storage(payload)
            if source_storage != "local" and not str(source_path).startswith("/"):
                source_path = "/" + str(source_path)

            from app.chain.transfer import TransferChain
            from app.schemas import FileItem

            fileitem = FileItem(
                storage=source_storage,
                path=source_path,
                type=self._file_type(source_path, source_storage, payload),
                name=payload.get("source_name"),
                size=payload.get("file_size"),
            )
            options = self._transfer_options()
            fileitem_log = fileitem.model_dump() if hasattr(fileitem, "model_dump") else fileitem.dict()
            logger.info(
                f"[TelegraphVideo] 调用 MP 原生整理: fileitem={fileitem_log}, "
                f"options={options}, summary={summary}"
            )
            state, result = TransferChain().manual_transfer(
                fileitem=fileitem,
                target_storage=options["target_storage"],
                target_path=options["target_path"],
                transfer_type=options["transfer_type"],
                scrape=options["scrape"],
                force=options["force"],
                background=options["background"],
            )
            logger.info(
                f"[TelegraphVideo] MP 原生整理返回: success={state}, result={result}, summary={summary}"
            )
            if not state:
                return {
                    "success": False,
                    "message": result,
                    "scan_item_id": payload.get("scan_item_id"),
                    "source_path": source_path,
                    "source_name": payload.get("source_name"),
                }

            return {
                "success": True,
                "message": "整理完成",
                "organize_result": result,
                "source_path": source_path,
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
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "model": "enabled",
                                        "props": {
                                            "label": "启用插件接口",
                                            "hint": "开启后允许 Telegraph Video 调用本插件整理接口。",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 8},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "扫描任务在 Telegraph Video 系统中创建；这里仅配置 MP 收到条目后如何调用原生整理。",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "model": "source_storage",
                                        "props": {
                                            "label": "源存储类型",
                                            "placeholder": "local / smb / alist / u115 ...",
                                            "hint": "必须与 MoviePilot 中可访问该路径的存储类型一致；扫描目录不在这里配置。",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSelect",
                                        "model": "transfer_type",
                                        "props": {
                                            "label": "整理方式",
                                            "items": [
                                                {"title": "使用 MP 默认", "value": ""},
                                                {"title": "移动", "value": "move"},
                                                {"title": "复制", "value": "copy"},
                                                {"title": "硬链接", "value": "link"},
                                                {"title": "软链接", "value": "softlink"},
                                            ],
                                            "hint": "留空时使用 MoviePilot 当前默认整理方式。",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "model": "target_storage",
                                        "props": {
                                            "label": "目标存储类型",
                                            "placeholder": "留空使用 MP 默认",
                                            "hint": "可选。指定后传给 MP 原生整理作为目标存储。",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "model": "target_path",
                                        "props": {
                                            "label": "目标目录",
                                            "placeholder": "留空使用 MP 默认媒体库目录",
                                            "hint": "可选。不是扫描目录，是整理后的目标目录。",
                                            "persistent-hint": True,
                                            "clearable": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "model": "scrape",
                                        "props": {"label": "刮削元数据"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "model": "force",
                                        "props": {"label": "强制整理"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "model": "background",
                                        "props": {"label": "后台整理"},
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ], {
            "enabled": False,
            "source_storage": "local",
            "target_storage": "",
            "target_path": "",
            "transfer_type": "",
            "scrape": None,
            "force": False,
            "background": False,
        }

    def get_page(self) -> list:
        return []

    def stop_service(self):
        pass
