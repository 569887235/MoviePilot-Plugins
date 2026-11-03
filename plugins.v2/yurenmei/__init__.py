"""MoviePilot V2 adapter for reviewed Yurenmei STRM imports."""

import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from app.plugins import _PluginBase


class Yurenmei(_PluginBase):
    plugin_name = "余人美"
    plugin_desc = "余人美两阶段识别与人工确认入库，同集同分辨率复用稳定 STRM。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/Moviepilot_A.png"
    plugin_version = "0.1.1"
    plugin_author = "569887235"
    plugin_config_prefix = "yurenmei_"
    plugin_order = 2
    auth_level = 1
    _config = {}
    _executor = None
    _item_lock = threading.Lock()
    resolutions = {"144p", "240p", "360p", "480p", "576p", "720p", "1080p", "1440p", "2160p", "4320p"}

    def init_plugin(self, config: dict = None):
        self.stop_service()
        self._config = config or {}
        self._lock = threading.RLock()
        self._futures = {}
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yurenmei")

    def get_state(self) -> bool:
        return self._config.get("enabled") is True

    def status(self) -> dict:
        return {"success": True, "data": {"plugin_id": "Yurenmei", "version": self.plugin_version,
                                         "enabled": self.get_state()}}

    def get_api(self) -> list:
        return [
            {"path": "/status", "endpoint": self.status, "methods": ["GET"], "summary": "余人美插件状态"},
            {"path": "/recognize", "endpoint": self.recognize, "methods": ["POST"], "summary": "仅识别并返回待确认结果"},
            {"path": "/import", "endpoint": self.import_strm, "methods": ["POST"], "summary": "按已确认结果整理 STRM"},
            {"path": "/jobs/{request_id}", "endpoint": self.get_job, "methods": ["GET"], "summary": "查询识别或入库结果"},
        ]

    @staticmethod
    def _jsonable(value):
        if isinstance(value, Enum):
            return value.value
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if hasattr(value, "to_dict"):
            return Yurenmei._jsonable(value.to_dict())
        if hasattr(value, "model_dump"):
            return Yurenmei._jsonable(value.model_dump())
        if isinstance(value, dict):
            return {str(k): Yurenmei._jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [Yurenmei._jsonable(v) for v in value]
        if hasattr(value, "__dict__"):
            return {k: Yurenmei._jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
        return str(value)

    @staticmethod
    def _safe_name(value):
        name = re.sub(r'[\x00-\x1f\\/?:*"<>|]', "_", str(value)).strip(" .")[:120]
        if not name:
            raise ValueError("识别名称不能为空")
        return name

    def _job_path(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
            raise ValueError("任务编号无效")
        directory = self.get_data_path() / "jobs"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{request_id}.json"

    def _read_job(self, request_id):
        path = self._job_path(request_id)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None

    def _write_job(self, job):
        with self._lock:
            path = self._job_path(job["request_id"])
            temp = path.with_suffix(".tmp")
            temp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
            temp.replace(path)

    def get_job(self, request_id: str) -> dict:
        try:
            with self._lock:
                job = self._read_job(request_id)
                if not job:
                    return {"success": True, "data": {"request_id": request_id, "status": "not_found"}}
                if job["status"] in {"pending", "running"} and request_id not in self._futures:
                    job.update(status="failed", error="插件已重新加载，任务结果未确认；可使用原任务编号重试。")
                    self._write_job(job)
                return {"success": True, "data": job}
        except (ValueError, OSError):
            return {"success": False, "message": "读取任务失败"}

    def _submit(self, kind, payload):
        if not self.get_state():
            return {"success": False, "message": "余人美插件未启用"}
        try:
            if not isinstance(payload, dict):
                raise ValueError("请求格式无效")
            request_id = payload.get("request_id")
            self._job_path(request_id)
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            with self._lock:
                previous = self._read_job(request_id)
                if previous:
                    if previous["kind"] != kind or previous["fingerprint"] != fingerprint:
                        raise ValueError("同一任务编号不能用于不同请求")
                    future = self._futures.get(request_id)
                    if previous["status"] == "success" or (future and not future.done()):
                        return {"success": True, "data": previous}
                job = {"request_id": request_id, "kind": kind, "status": "pending", "fingerprint": fingerprint}
                self._write_job(job)
                self._futures[request_id] = self._executor.submit(self._run, job, dict(payload))
                return {"success": True, "data": job}
        except (ValueError, OSError, RuntimeError) as error:
            return {"success": False, "message": str(error)}

    def _run(self, job, payload):
        job = dict(job)
        job["status"] = "running"
        self._write_job(job)
        try:
            result = self._recognize(payload) if job["kind"] == "recognize" else self._import(payload)
            job.update(status="success", result=result)
            job.pop("error", None)
        except Exception as error:
            job.update(status="failed", error=str(error)[:512])
        self._write_job(job)

    def recognize(self, payload: dict) -> dict:
        return self._submit("recognize", payload)

    def import_strm(self, payload: dict) -> dict:
        return self._submit("import", payload)

    def _recognize(self, payload):
        from app.chain.media import MediaChain

        # Native path recognition only parses the name; it neither transfers a
        # file nor fetches the episode's temporary playback URL.
        name = self._safe_name(payload.get("name") or "")
        context = self._jsonable(MediaChain().recognize_by_path(f"{name}.strm", obtain_images=True)) or {}
        info, meta = context.get("media_info") or {}, context.get("meta_info") or {}
        media_type = {"电影": "movie", "电视剧": "tv", "movie": "movie", "tv": "tv"}.get(str(info.get("type")))
        tmdb_id = info.get("tmdb_id") or info.get("tmdbid")
        if not media_type or not str(tmdb_id or "").isdigit() or int(tmdb_id) < 1 or not info.get("title"):
            raise ValueError("MoviePilot 未返回完整的媒体类型、片名和 TMDB 编号，请调整名称重新识别")
        return {"media": {"mediaType": media_type, "tmdbId": int(tmdb_id), "title": info["title"],
                          "year": info.get("year"), "season": meta.get("begin_season"),
                          "episode": meta.get("begin_episode")}, "context": context}

    def _import(self, payload):
        from app.chain.media import MediaChain
        from app.chain.transfer import TransferChain
        from app.db.transferhistory_oper import TransferHistoryOper
        from app.helper.directory import DirectoryHelper
        from app.schemas import FileItem
        from app.schemas.types import MediaType

        preview = self._read_job(payload.get("recognition_id"))
        if not preview or preview.get("kind") != "recognize" or preview["status"] != "success":
            raise ValueError("必须先完成识别并由业务端确认")
        media = preview["result"]["media"]
        if payload.get("confirmed") is not True:
            raise ValueError("缺少人工确认")
        season, episode = payload.get("season"), payload.get("episode")
        if media["mediaType"] == "movie":
            if season != 0 or episode != 0:
                raise ValueError("电影的季集必须为0")
        elif type(season) is not int or not 0 <= season <= 999 or type(episode) is not int or not 1 <= episode <= 99999:
            raise ValueError("电视剧的季集无效")
        resolution = payload.get("resolution")
        if resolution not in self.resolutions:
            raise ValueError("标准分辨率无效")
        play_url = payload.get("play_url") or ""
        url = urlparse(play_url)
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment or not re.fullmatch(r"/play/yrm/[a-f0-9]{64}/stream", url.path):
            raise ValueError("必须提供余人美稳定播放地址")
        identity = f'{media["mediaType"]}:{media["tmdbId"]}:{season}:{episode}:{resolution}'
        key = hashlib.sha256(identity.encode()).hexdigest()
        directory = self.get_data_path() / "strm" / key
        directory.mkdir(parents=True, exist_ok=True)
        ledger = directory / "import.json"
        with self._item_lock:
            if ledger.is_file():
                saved = json.loads(ledger.read_text(encoding="utf-8"))
                if saved["play_url"] != play_url:
                    raise ValueError("该媒体季集分辨率已使用另一稳定地址入库")
                dest = Path(saved["strm_path"])
                if not dest.is_file() or dest.read_text(encoding="utf-8").strip() != play_url:
                    raise ValueError("已入库的 STRM 不存在或内容已更改，请核对媒体库")
                return {**saved, "reused": True}
            marker = directory / "source.json"
            if marker.is_file():
                source = json.loads(marker.read_text(encoding="utf-8"))
                if source["play_url"] != play_url:
                    raise ValueError("该入库身份已绑定另一稳定地址")
                filename = source["filename"]
            else:
                suffix = f".S{season:02d}E{episode:02d}" if media["mediaType"] == "tv" else ""
                filename = f'{self._safe_name(media["title"])}{suffix}.{resolution}.strm'
                marker.write_text(json.dumps({"filename": filename, "play_url": play_url}), encoding="utf-8")
            path = directory / filename
            path.write_text(play_url + "\n", encoding="utf-8")
            oper = TransferHistoryOper()
            history = oper.get_by_src(str(path), "local")
            if not history or not getattr(history, "status", False):
                media_type = MediaType.MOVIE if media["mediaType"] == "movie" else MediaType.TV
                media_info = MediaChain().recognize_media(tmdbid=media["tmdbId"], mtype=media_type)
                if not media_info or media_info.tmdb_id != media["tmdbId"] or media_info.type != media_type:
                    raise ValueError("MoviePilot 媒体信息与已确认的 TMDB 或类型不一致")
                target = deepcopy(DirectoryHelper().get_dir(media=media_info, storage="local", src_path=path))
                if not target or not target.library_path:
                    raise ValueError("未匹配 MoviePilot 媒体库目录，请核对 MoviePilot 的目录与分类配置")
                if target.library_storage != "local" or not Path(target.library_path).is_absolute():
                    raise ValueError("当前 STRM 入库需要 MoviePilot 配置本地存储的绝对媒体库目录")
                # Keep MoviePilot's directory selection and category settings.
                # Isolate resolutions beneath its selected library root so a
                # rename template without quality cannot overwrite another STRM.
                target.library_path = str(Path(target.library_path) / resolution)
                state, message = TransferChain().do_transfer(
                    fileitem=FileItem(storage="local", path=str(path), type="file", name=filename, size=path.stat().st_size),
                    mediainfo=media_info, target_directory=target, target_storage=target.library_storage,
                    season=season if media["mediaType"] == "tv" else None,
                    transfer_type="copy", min_filesize=0, scrape=self._config.get("scrape", True) is True,
                    force=False, background=False, manual=True,
                )
                if not state:
                    raise ValueError(str(message or "MoviePilot 整理失败"))
                history = oper.get_by_src(str(path), "local")
            dest = getattr(history, "dest", None) if history else None
            if not history or not getattr(history, "status", False) or not dest or not Path(dest).is_file():
                raise ValueError("尚未取得实际目标 STRM 和成功整理历史，请刷新或重试")
            if Path(dest).suffix.lower() != ".strm" or Path(dest).read_text(encoding="utf-8").strip() != play_url:
                raise ValueError("目标 STRM 内容与稳定播放地址不一致")
            result = {"identity": identity, "play_url": play_url, "strm_path": str(dest),
                      "history_id": getattr(history, "id", None), "resolution": resolution}
            temp = ledger.with_suffix(".tmp")
            temp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            temp.replace(ledger)
            return result

    def get_form(self) -> tuple[list, dict]:
        return [{"component": "VForm", "content": [
            {"component": "VSwitch", "props": {"model": "enabled", "label": "启用余人美插件"}},
            {"component": "VAlert", "props": {"type": "info", "variant": "tonal", "text":
             "入库沿用 MoviePilot 的目录与分类配置，在匹配的本地媒体库目录下按分辨率整理，无需另填容器目录。"}},
            {"component": "VSwitch", "props": {"model": "scrape", "label": "刮削元数据"}},
        ]}], {"enabled": self.get_state(),
              "scrape": self._config.get("scrape", True)}

    @staticmethod
    def get_command() -> list:
        return []

    def get_service(self) -> list:
        return []

    def get_page(self) -> list:
        return []

    def stop_service(self):
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
