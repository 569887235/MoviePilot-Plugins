import importlib.util
import json
import pathlib
import shutil
import sys
import tempfile
import types
import unittest
from enum import Enum
from unittest.mock import patch


class MediaType(Enum):
    MOVIE = "电影"
    TV = "电视剧"


class YurenmeiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.transfers, self.recognitions, self.histories = [], [], {}
        owner = self

        class Base:
            def get_data_path(self):
                return owner.root / "plugin"

        class MediaChain:
            def recognize_by_path(self, path, **options):
                owner.recognitions.append((path, options))
                return {"media_info": {"type": MediaType.TV, "tmdb_id": 123, "title": "测试剧", "year": "2026"},
                        "meta_info": {"begin_season": 1, "begin_episode": 2}}

        class TransferChain:
            def manual_transfer(self, **options):
                owner.transfers.append(options)
                source = pathlib.Path(options["fileitem"].path)
                target = options["target_path"] / source.name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                owner.histories[str(source)] = types.SimpleNamespace(id=len(owner.transfers), status=True, dest=str(target))
                return True, ""

        class TransferHistoryOper:
            def get_by_src(self, path, storage):
                return owner.histories.get(path)

        modules = {name: types.ModuleType(name) for name in [
            "app", "app.plugins", "app.chain", "app.chain.media", "app.chain.transfer",
            "app.db", "app.db.transferhistory_oper", "app.schemas", "app.schemas.types",
        ]}
        modules["app.plugins"]._PluginBase = Base
        modules["app.chain.media"].MediaChain = MediaChain
        modules["app.chain.transfer"].TransferChain = TransferChain
        modules["app.db.transferhistory_oper"].TransferHistoryOper = TransferHistoryOper
        modules["app.schemas"].FileItem = lambda **values: types.SimpleNamespace(**values)
        modules["app.schemas.types"].MediaType = MediaType
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        path = pathlib.Path(__file__).parents[1] / "plugins.v2/yurenmei/__init__.py"
        spec = importlib.util.spec_from_file_location("yurenmei_fixture", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.plugin = self.module.Yurenmei()
        self.plugin.init_plugin({"enabled": True, "target_path": str(self.root / "library")})

    def tearDown(self):
        self.plugin._executor.shutdown(wait=True)
        self.plugin._executor = None
        self.patcher.stop()
        self.temp.cleanup()

    def run_job(self, method, payload):
        response = method(payload)
        self.assertTrue(response["success"], response)
        future = self.plugin._futures.get(payload["request_id"])
        if future:
            future.result(timeout=5)
        return self.plugin.get_job(payload["request_id"])["data"]

    def recognize(self):
        return self.run_job(self.plugin.recognize, {"request_id": "preview", "name": "测试剧 S01E02"})

    def payload(self, request_id="import720", resolution="720p", key="a"):
        return {"request_id": request_id, "recognition_id": "preview", "confirmed": True,
                "season": 1, "episode": 2, "resolution": resolution,
                "play_url": f'https://business.test/play/yrm/{key * 64}/stream'}

    def test_recognition_returns_metadata_without_transfer_or_strm(self):
        job = self.recognize()
        self.assertEqual(job["status"], "success")
        self.assertEqual(job["result"]["media"]["tmdbId"], 123)
        self.assertEqual(job["result"]["media"]["mediaType"], "tv")
        self.assertEqual(self.transfers, [])
        self.assertFalse((self.root / "plugin/strm").exists())

    def test_confirmation_and_successful_preview_are_both_required(self):
        self.assertEqual(self.run_job(self.plugin.import_strm, self.payload())["status"], "failed")
        self.recognize()
        self.assertEqual(self.run_job(self.plugin.import_strm, {**self.payload("unconfirmed"), "confirmed": False})["status"], "failed")
        self.assertEqual(self.transfers, [])

    def test_same_resolution_reuses_one_strm_and_other_resolution_has_its_own(self):
        self.recognize()
        a = self.run_job(self.plugin.import_strm, self.payload())
        duplicate = self.run_job(self.plugin.import_strm, self.payload("another720"))
        b = self.run_job(self.plugin.import_strm, self.payload("import1080", "1080p", "b"))
        self.assertEqual([a["status"], duplicate["status"], b["status"]], ["success"] * 3)
        self.assertEqual(len(self.transfers), 2)
        self.assertEqual(a["result"]["strm_path"], duplicate["result"]["strm_path"])
        self.assertNotEqual(a["result"]["strm_path"], b["result"]["strm_path"])
        for call in self.transfers:
            self.assertFalse(call["force"])
            self.assertEqual(call["tmdbid"], 123)
            self.assertEqual(call["mtype"], MediaType.TV)
            self.assertEqual(call["season"], 1)
        self.assertIn("/720p/", a["result"]["strm_path"])
        self.assertIn("/1080p/", b["result"]["strm_path"])
        for job in [a, b]:
            self.assertEqual(pathlib.Path(job["result"]["strm_path"]).read_text().strip(), job["result"]["play_url"])

    def test_duplicate_requests_cannot_change_payload_or_stable_url(self):
        self.recognize()
        first = self.run_job(self.plugin.import_strm, self.payload())
        self.assertEqual(first["status"], "success")
        self.assertFalse(self.plugin.import_strm(self.payload(key="b"))["success"])
        conflict = self.run_job(self.plugin.import_strm, self.payload("other", key="b"))
        self.assertEqual(conflict["status"], "failed")
        self.assertEqual(len(self.transfers), 1)

    def test_failed_transfer_is_not_reported_as_success_and_retry_keeps_identity(self):
        self.recognize()
        with patch.object(sys.modules["app.chain.transfer"].TransferChain, "manual_transfer", return_value=(False, "native failure")):
            failed = self.run_job(self.plugin.import_strm, self.payload())
        self.assertEqual(failed["status"], "failed")
        self.assertIn("native failure", failed["error"])
        success = self.run_job(self.plugin.import_strm, self.payload())
        self.assertEqual(success["status"], "success")
        self.assertEqual(len(self.transfers), 1)

    def test_interrupted_job_and_lost_receipt_recover_without_duplicate_transfer(self):
        self.recognize()
        job = self.run_job(self.plugin.import_strm, self.payload())
        ledger = next((self.root / "plugin/strm").glob("*/import.json"))
        ledger.unlink()  # Native transfer finished, but the receipt was not persisted.
        job.update(status="running")
        self.plugin._write_job(job)
        self.plugin._futures.pop("import720")
        self.assertEqual(self.plugin.get_job("import720")["data"]["status"], "failed")
        self.assertEqual(self.run_job(self.plugin.import_strm, self.payload())["status"], "success")
        self.assertEqual(len(self.transfers), 1)

    def test_deleted_target_is_not_falsely_reported_as_success_for_new_task(self):
        self.recognize()
        job = self.run_job(self.plugin.import_strm, self.payload())
        pathlib.Path(job["result"]["strm_path"]).unlink()
        self.assertEqual(self.run_job(self.plugin.import_strm, self.payload("check-deleted"))["status"], "failed")

    def test_disabled_plugin_and_invalid_inputs_have_no_import_side_effects(self):
        self.plugin._config["enabled"] = False
        self.assertFalse(self.plugin.recognize({"request_id": "x", "name": "test"})["success"])
        self.plugin._config["enabled"] = True
        self.assertFalse(self.plugin.recognize({"request_id": "../escape", "name": "test"})["success"])
        self.recognize()
        for payload in [{**self.payload("unknown"), "resolution": "unknown"},
                        {**self.payload("raw"), "play_url": "https://media.test/temporary.m3u8"},
                        {**self.payload("bad-episode"), "episode": 0}]:
            self.assertEqual(self.run_job(self.plugin.import_strm, payload)["status"], "failed")
        self.assertEqual(self.transfers, [])

    def test_market_metadata_and_standalone_entry_are_aligned(self):
        index = json.loads((pathlib.Path(__file__).parents[1] / "package.v2.json").read_text())
        entry = index["Yurenmei"]
        for key, field in [("name", "plugin_name"), ("description", "plugin_desc"), ("version", "plugin_version"), ("icon", "plugin_icon"), ("author", "plugin_author")]:
            self.assertEqual(entry[key], getattr(self.plugin, field))
        self.assertEqual(self.plugin.get_service(), [])
        self.assertTrue(all(api.get("allow_anonymous") is not True for api in self.plugin.get_api()))
        self.assertIn("TelegraphVideo", index)


if __name__ == "__main__":
    unittest.main()
