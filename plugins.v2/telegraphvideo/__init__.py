import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

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
    plugin_version = "0.1.5"
    plugin_author = "telegraph-video"
    plugin_config_prefix = "telegraphvideo_"
    plugin_order = 1
    auth_level = 1

    def init_plugin(self, config: dict = None):
        self._config = config or {}
        logger.info(
            "[TelegraphVideo] 插件初始化，"
            f"enabled={self._enabled()}, "
            f"source_storage={self._config_value('source_storage') or 'local'}, "
            f"target_storage={self._config_value('target_storage') or None}, "
            f"target_path={self._config_value('target_path') or None}, "
            f"transfer_type={self._config_value('transfer_type') or None}, "
            f"scrape={self._config_value('scrape')}, "
            f"business_api_base_url={self._config_value('business_api_base_url') or None}, "
            f"callback_enabled={bool(self._config_value('callback_enabled'))}"
        )

    def _config_value(self, key: str, default: Any = None) -> Any:
        return self._config.get(key, self._config.get(f"{self.plugin_config_prefix}{key}", default))

    def _enabled(self) -> bool:
        return bool(self._config_value("_enabled", self._config_value("enabled", False)))

    def get_state(self) -> bool:
        return self._enabled()

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
            or self._config_value('source_storage')
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
        target_path = self._config_value('target_path') or None
        return {
            "target_storage": self._config_value('target_storage') or None,
            "target_path": Path(target_path) if target_path else None,
            "transfer_type": self._config_value('transfer_type') or None,
            "scrape": self._as_bool(self._config_value('scrape')),
            "force": self._as_bool(self._config_value("force")) or False,
            "background": False,
        }

    @staticmethod
    def _dump_model(value: Any) -> Any:
        if value is None:
            return None
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "dict"):
            return value.dict()
        if isinstance(value, Path):
            return value.as_posix()
        return value

    @staticmethod
    def _media_type(value: Any) -> Optional[str]:
        if value is None:
            return None
        raw = value.value if hasattr(value, "value") else str(value)
        text = str(raw).strip().lower()
        if text in {"movie", "电影", "film"}:
            return "movie"
        if text in {"tv", "电视剧", "series", "show"}:
            return "tv"
        return str(raw)

    @staticmethod
    def _first_episode(episodes: Any) -> Optional[int]:
        if episodes is None:
            return None
        text = str(episodes)
        for part in text.replace(",", " ").split():
            digits = "".join(ch for ch in part if ch.isdigit())
            if digits:
                return int(digits)
        return None

    def _history_to_payload(self, history: Any) -> Dict[str, Any]:
        if not history:
            return {}
        media_type = self._media_type(getattr(history, "type", None))
        season_number = self._first_episode(getattr(history, "seasons", None))
        episode_number = self._first_episode(getattr(history, "episodes", None))
        metadata = {
            "title": getattr(history, "title", None),
            "year": getattr(history, "year", None),
            "media_type": media_type,
            "tmdb_id": getattr(history, "tmdbid", None),
            "imdb_id": getattr(history, "imdbid", None),
            "douban_id": getattr(history, "doubanid", None),
            "season_number": season_number,
            "episode_number": episode_number,
            "poster": getattr(history, "image", None),
        }
        metadata = {k: v for k, v in metadata.items() if v not in (None, "")}
        return {
            "metadata": metadata,
            "media": metadata,
            "transfer_history": {
                "id": getattr(history, "id", None),
                "src": getattr(history, "src", None),
                "src_storage": getattr(history, "src_storage", None),
                "dest": getattr(history, "dest", None),
                "dest_storage": getattr(history, "dest_storage", None),
                "mode": getattr(history, "mode", None),
                "status": getattr(history, "status", None),
                "errmsg": getattr(history, "errmsg", None),
                "files": getattr(history, "files", None),
                "src_fileitem": getattr(history, "src_fileitem", None),
                "dest_fileitem": getattr(history, "dest_fileitem", None),
            }
        }

    def _latest_transfer_history(self, source_path: str, source_storage: str) -> Any:
        try:
            from app.db.transferhistory_oper import TransferHistoryOper
            return TransferHistoryOper().get_by_src(source_path, source_storage)
        except Exception as err:
            logger.warning(f"[TelegraphVideo] 查询整理历史失败: source_path={source_path}, source_storage={source_storage}, error={err}")
            return None

    def _business_callback_config(self) -> Dict[str, Any]:
        base_url = str(self._config_value('business_api_base_url') or "").rstrip("/")
        endpoint = self._config_value("business_callback_endpoint") or "/api/mp/organize-callback"
        token = self._config_value("business_callback_token") or ""
        return {
            "enabled": bool(self._config_value('callback_enabled')),
            "url": base_url + (endpoint if str(endpoint).startswith("/") else "/" + str(endpoint)) if base_url else "",
            "token": token,
        }

    def _post_business_callback(self, callback_payload: Dict[str, Any]) -> None:
        callback = self._business_callback_config()
        if not callback["enabled"]:
            logger.info(f"[TelegraphVideo] 业务回调未启用，跳过: scan_item_id={callback_payload.get('scan_item_id')}")
            return
        if not callback["url"]:
            logger.warning(f"[TelegraphVideo] 业务回调地址未配置，跳过: scan_item_id={callback_payload.get('scan_item_id')}")
            return
        body = json.dumps(callback_payload, ensure_ascii=False, default=str).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if callback["token"]:
            headers["X-API-KEY"] = callback["token"]
        req = urlrequest.Request(callback["url"], data=body, headers=headers, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=15) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                logger.info(
                    f"[TelegraphVideo] 业务回调完成: url={callback['url']}, status={resp.status}, "
                    f"scan_item_id={callback_payload.get('scan_item_id')}, response={text[:500]}"
                )
        except HTTPError as err:
            text = err.read().decode("utf-8", errors="replace") if err.fp else ""
            logger.error(
                f"[TelegraphVideo] 业务回调 HTTP 失败: url={callback['url']}, status={err.code}, "
                f"scan_item_id={callback_payload.get('scan_item_id')}, response={text[:500]}"
            )
        except URLError as err:
            logger.error(f"[TelegraphVideo] 业务回调连接失败: url={callback['url']}, scan_item_id={callback_payload.get('scan_item_id')}, error={err}")
        except Exception as err:
            logger.exception(f"[TelegraphVideo] 业务回调异常: scan_item_id={callback_payload.get('scan_item_id')}, error={err}")

    def organize(self, payload: Dict[str, Any]) -> dict:
        payload = payload or {}
        summary = self._payload_summary(payload)
        logger.info(f"[TelegraphVideo] 收到整理请求: {summary}")
        try:
            if not self._enabled():
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
            history = self._latest_transfer_history(source_path, source_storage)
            history_payload = self._history_to_payload(history)
            response_payload = {
                "success": bool(state),
                "message": "整理完成" if state else result,
                "organize_result": result,
                "transfer_result": result,
                "source_path": source_path,
                "source_name": payload.get("source_name"),
                "scan_task_id": payload.get("scan_task_id"),
                "scan_item_id": payload.get("scan_item_id"),
                **history_payload,
            }
            if not state:
                self._post_business_callback(response_payload)
                return response_payload

            self._post_business_callback(response_payload)
            return response_payload
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
                                        "model": "_enabled",
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
                                        "model": "callback_enabled",
                                        "props": {
                                            "label": "回传整理结果",
                                            "hint": "开启后整理完成会主动回调 Telegraph Video 业务系统。",
                                            "persistent-hint": True,
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "model": "business_api_base_url",
                                        "props": {
                                            "label": "业务系统地址",
                                            "placeholder": "https://video.example.com",
                                            "hint": "Telegraph Video API 的外部访问地址。",
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
                                        "component": "VTextField",
                                        "model": "business_callback_token",
                                        "props": {
                                            "label": "业务回调 Token",
                                            "type": "password",
                                            "hint": "对应业务系统 MP_CALLBACK_TOKEN。",
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
                        ],
                    }
                ],
            }
        ], {
            "_enabled": self._enabled(),
            "source_storage": self._config_value("source_storage", "local"),
            "target_storage": self._config_value("target_storage", ""),
            "target_path": self._config_value("target_path", ""),
            "transfer_type": self._config_value("transfer_type", ""),
            "scrape": self._config_value("scrape", None),
            "force": self._config_value("force", False),
            "callback_enabled": self._config_value("callback_enabled", False),
            "business_api_base_url": self._config_value("business_api_base_url", ""),
            "business_callback_endpoint": self._config_value("business_callback_endpoint", "/api/mp/organize-callback"),
            "business_callback_token": self._config_value("business_callback_token", ""),
        }

    def get_page(self) -> list:
        return []

    def stop_service(self):
        pass
