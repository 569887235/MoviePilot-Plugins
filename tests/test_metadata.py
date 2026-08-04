import importlib.util
import pathlib
import unittest


MODULE_PATH = pathlib.Path(__file__).parents[1] / "plugins.v2" / "telegraphvideo" / "metadata.py"
SPEC = importlib.util.spec_from_file_location("telegraphvideo_metadata", MODULE_PATH)
metadata = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metadata)


class MetadataPayloadTest(unittest.TestCase):
    def test_context_is_complete_without_duplicate_media_branches(self):
        payload = metadata.normalize_media_context({
            "meta_info": {
                "title": "Example", "begin_season": 2, "begin_episode": 3,
                "customization": "retain",
            },
            "media_info": {
                "type": "电视剧",
                "title": "Example",
                "year": "2025",
                "original_name": "Original",
                "provider_ids": {"tmdb": 10, "custom": "future-id"},
                "genre_ids": [1, 2],
                "poster_path": "/poster.jpg",
                "poster_url": "https://image.tmdb.org/t/p/original/poster.jpg",
                "runtime": 45,
                "plot": "Same overview",
                "overview": "Same overview",
                "vote_average": 8.5,
                "actors": [{"id": 1, "name": "Actor", "profile_path": "/actor.jpg"}],
                "people": [{"id": 1, "name": "Actor"}],
                "directors": [
                    {"id": 2, "name": "Director", "job": "Director"},
                    {"id": 3, "name": "Writer", "job": "Writer"},
                    "Director Two",
                ],
                "writers": ["Writer Two"],
                "created_by": [{"id": 4, "name": "Creator"}],
                "season_info": [{"season_number": 2, "name": "Season 2"}],
                "names": ["Example", "Example Show"],
            },
        })

        self.assertEqual(payload["schema_version"], 2)
        self.assertNotIn("metadata", payload)
        self.assertNotIn("media", payload)
        self.assertNotIn("recognize_result", payload)
        self.assertEqual(payload["media_info"]["runtime_seconds"], 2700)
        self.assertEqual(payload["media_info"]["names"], ["Example", "Example Show"])
        self.assertEqual(len(payload["media_info"]["credits"]["cast"]), 1)
        self.assertEqual([item["job"] for item in payload["media_info"]["credits"]["crew"]], ["Director", "Writer", "Director", "Writer", "Creator"])
        self.assertNotIn("actors", payload["media_info"])
        self.assertNotIn("people", payload["media_info"])

        self.assertEqual(payload["media_info"]["original_title"], "Original")
        self.assertNotIn("original_name", payload["media_info"])
        self.assertEqual(payload["media_info"]["provider_ids"], {"custom": "future-id"})
        self.assertEqual(payload["media_info"]["genre_ids"], [1, 2])
        self.assertEqual(payload["media_info"]["overview"], "Same overview")
        self.assertNotIn("plot", payload["media_info"])
        self.assertEqual(payload["recognition_info"], {"meta_info": {"customization": "retain"}})

        without_catalog_aliases = metadata.remove_catalog_aliases(payload["media_info"])
        self.assertNotIn("season_info", without_catalog_aliases)
        self.assertEqual(without_catalog_aliases["names"], ["Example", "Example Show"])

if __name__ == "__main__":
    unittest.main()
