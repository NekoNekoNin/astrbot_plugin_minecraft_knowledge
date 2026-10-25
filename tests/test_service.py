"""Exercise source selection, pagination and failure evidence without networking."""

import json
import tempfile
import unittest
from pathlib import Path

from mc_knowledge.service import KnowledgeService, identify_reference, text_page
from mc_knowledge.transport import SourceError


class FakeFetcher:
    cache_ttl = 300

    def __init__(self):
        self.calls = []

    async def get_text(self, url, params=None, headers=None):
        self.calls.append((url, params))
        return """<rss><channel>
        <item><title>Create</title><link>https://www.mcmod.cn/class/2021.html</link><description>summary only</description></item>
        <item><title>tutorial</title><link>https://www.mcmod.cn/post/2373.html</link></item>
        <item><title>spoof</title><link>https://www.mcmod.cn.evil.example/class/2021.html</link></item>
        <item><title>external</title><link>http://127.0.0.1/class/1.html</link></item>
        </channel></rss>"""


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_source_switches_prevent_every_read_path(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "plugin.json"
            config.write_text(
                json.dumps(
                    {
                        "mcmod_enabled": False,
                        "modrinth_enabled": False,
                        "curseforge_enabled": False,
                    }
                ),
                encoding="utf-8",
            )
            fetcher = FakeFetcher()
            service = KnowledgeService(fetcher, str(config))
            result = await service.search("Create")
            self.assertFalse(result["ok"])
            self.assertTrue(
                all(
                    row["error"]["code"] == "source_disabled"
                    for row in result["groups"]
                )
            )
            for coroutine in [
                service.read("https://www.mcmod.cn/class/2021.html"),
                service.read("https://modrinth.com/mod/sodium"),
                service.related("https://www.mcmod.cn/class/2021.html"),
                service.versions("modrinth", "sodium"),
                service.versions("curseforge", "238222"),
            ]:
                with self.assertRaises(SourceError) as caught:
                    await coroutine
                self.assertEqual(caught.exception.code, "source_disabled")
            self.assertEqual(fetcher.calls, [])
            self.assertTrue(
                all(not row["enabled"] for row in service.sources()["sources"])
            )

    async def test_native_network_settings_reload_without_exposing_key(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "plugin.json"
            config.write_text(
                json.dumps({"request_timeout_seconds": 12, "cache_ttl_seconds": 0}),
                encoding="utf-8",
            )
            fetcher = FakeFetcher()
            service = KnowledgeService(fetcher, str(config))
            service.check_enabled()
            self.assertEqual(fetcher.timeout, 12)
            self.assertEqual(fetcher.cache_ttl, 0)
            config.write_text('{"request_timeout_seconds":false}', encoding="utf-8")
            with self.assertRaises(SourceError):
                service.check_enabled()

    async def test_search_filters_discovery_links_and_never_calls_site_search(self):
        fetcher = FakeFetcher()
        result = await KnowledgeService(fetcher).search("机械动力", source="mcmod")
        group = result["groups"][0]
        self.assertEqual(
            [row["url"] for row in group["results"]],
            ["https://www.mcmod.cn/class/2021.html"],
        )
        self.assertTrue(group["results"][0]["is_summary_only"])
        self.assertIsNone(group["total"])
        self.assertEqual(fetcher.calls[0][0], "https://cn.bing.com/search")
        self.assertNotIn("search.mcmod.cn", json.dumps(fetcher.calls))

    async def test_one_source_failure_does_not_erase_other_evidence(self):
        class Good:
            async def search(self, query, **kwargs):
                return {
                    "source": "modrinth",
                    "results": [{"title": query, "download_count": 123}],
                    "filters": kwargs,
                }

        service = KnowledgeService(FakeFetcher())
        service.modrinth = Good()
        result = await service.search("Create", game_version="1.21.1", loader="fabric")
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["groups"]), 3)
        self.assertEqual(result["groups"][1]["filters"]["game_version"], "1.21.1")
        self.assertFalse(result["groups"][2]["ok"])
        self.assertEqual(result["groups"][2]["error"]["code"], "api_key_missing")
        self.assertNotIn("download_count", result["groups"][2])

    async def test_disabled_config_blocks_queries_and_does_not_expose_credentials(self):
        with tempfile.TemporaryDirectory() as root:
            config = Path(root) / "settings.json"
            config.write_text(
                json.dumps({"enabled": False, "curseforge_api_key": "fixture-secret"}),
                encoding="utf-8",
            )
            fetcher = FakeFetcher()
            service = KnowledgeService(fetcher, str(config))
            self.assertNotIn("fixture-secret", json.dumps(service.sources()))
            with self.assertRaises(SourceError) as caught:
                await service.search("Create")
            self.assertEqual(caught.exception.code, "disabled")
            self.assertEqual(fetcher.calls, [])
            config.write_text('{"enabled":true}', encoding="utf-8")
            self.assertTrue((await service.search("Create", source="mcmod"))["ok"])

    async def test_related_and_versions_validate_source_before_any_read(self):
        service = KnowledgeService(FakeFetcher())
        for url in [
            "https://modrinth.com/mod/sodium",
            "https://www.mcmod.cn/item/1.html",
        ]:
            with self.assertRaises(SourceError):
                await service.related(url)
        for project in [
            "../../secret",
            "https://evil.example/mod/a",
            "https://www.curseforge.com/minecraft/mc-mods/a",
        ]:
            with self.assertRaises(SourceError):
                await service.versions("modrinth", project)
        with self.assertRaises(SourceError):
            await service.search("Create", loader="forged-loader")


class PureServiceTests(unittest.TestCase):
    def test_article_pagination_reconstructs_full_unicode_body(self):
        original = "应力、动力与版本差异。\n" * 3000
        data = {
            "title": "Fixture",
            "text": original,
            "links": [{"url": str(i)} for i in range(80)],
        }
        offset, chunks = 0, []
        while True:
            page = text_page(data, offset, 501)
            chunks.append(page["text"])
            self.assertEqual(page["total_chars"], len(original))
            self.assertEqual(page["links_total"], 80)
            self.assertEqual(len(page["links"]), 20)
            self.assertTrue(page["links_truncated"])
            if page["complete"]:
                self.assertIsNone(page["next_offset"])
                break
            self.assertGreater(page["next_offset"], offset)
            offset = page["next_offset"]
        self.assertEqual("".join(chunks), original)
        self.assertEqual(len(data["links"]), 80)

    def test_invalid_offsets_and_limits_are_failures(self):
        for offset, limit in [
            (-1, 500),
            (4, 500),
            (False, 500),
            (0, 10),
            (0, 999999),
            (0, True),
        ]:
            with self.assertRaises(SourceError):
                text_page({"text": "abc"}, offset, limit)

    def test_only_known_article_and_project_urls_are_resolved(self):
        self.assertEqual(
            identify_reference("https://mcmod.cn/class/2021.html#x"),
            ("mcmod", "https://www.mcmod.cn/class/2021.html"),
        )
        self.assertEqual(
            identify_reference("https://modrinth.com/mod/sodium"),
            ("modrinth", "sodium"),
        )
        for url in [
            "file:///C:/secret",
            "http://www.mcmod.cn/class/1.html",
            "https://www.mcmod.cn@127.0.0.1/class/1.html",
            "https://www.mcmod.cn:444/class/1.html",
            "https://www.mcmod.cn/class/../post/1.html",
            "https://www.mcmod.cn.evil.example/class/1.html",
            "https://modrinth.com/modpack/not-a-mod",
        ]:
            with self.assertRaises(SourceError):
                identify_reference(url)
