"""Exercise MC百科 parsing with live-source excerpts and hostile HTML variants."""

import base64
import unittest
from pathlib import Path

from mc_knowledge.mcmod import McmodSource
from mc_knowledge.transport import SourceError

FIXTURES = Path(__file__).parent / "fixtures" / "mcmod"
MOD_URL = "https://www.mcmod.cn/class/2021.html"
ITEM_URL = "https://www.mcmod.cn/item/330128.html"
COMMUNITY_URL = "https://www.mcmod.cn/post/2373.html"
PERSONAL_URL = "https://www.mcmod.cn/post/2285.html"


def fixture(name):
    """Read a deliberately abbreviated real public page fixture."""
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """Record requests and refuse every URL not explicitly supplied by a test."""

    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    async def get_text(self, url, params=None, headers=None):
        self.calls.append((url, params, headers))
        value = self.pages[url]
        if isinstance(value, Exception):
            raise value
        return value


class McmodSourceTests(unittest.IsolatedAsyncioTestCase):
    """Verify grounding, complete reads, explicit failures and safe link handling."""

    def source(self, url, html):
        """Build a source whose transport can fetch exactly one article."""
        fetcher = FakeFetcher({url: html})
        return McmodSource(fetcher), fetcher

    async def test_real_mod_title_versions_authors_and_edit_time(self):
        source, fetcher = self.source(MOD_URL, fixture("class-2021-excerpt.html"))
        result = await source.read(MOD_URL)
        self.assertEqual(result["type"], "mod")
        self.assertEqual(result["title"], "机械动力 (Create)")
        self.assertEqual(result["metadata"]["updated"], "2026-10-19 23:46:04")
        self.assertIn(
            "Simibubi", [author["name"] for author in result["metadata"]["authors"]]
        )
        self.assertEqual(
            result["metadata"]["loader_versions"]["NeoForge"], ["1.21.1", "1.20.1"]
        )
        self.assertIn("Forge", result["metadata"]["loaders"])
        self.assertIn("1.20.1", result["metadata"]["game_versions"])
        self.assertEqual([call[0] for call in fetcher.calls], [MOD_URL])

    async def test_real_item_has_mod_breadcrumb_and_mechanism_text(self):
        source, _ = self.source(ITEM_URL, fixture("item-330128-excerpt.html"))
        result = await source.read("https://mcmod.cn/item/330128.html#description")
        self.assertEqual(result["url"], ITEM_URL)
        self.assertEqual(result["type"], "item")
        self.assertIn("应力", result["title"])
        self.assertIn("扭矩", result["text"])
        self.assertEqual(result["metadata"]["mod"]["url"], MOD_URL)
        self.assertEqual(result["metadata"]["updated"], "2025-03-01 18:49:35")

    async def test_community_tutorial_does_not_invent_a_single_author(self):
        source, _ = self.source(COMMUNITY_URL, fixture("post-2373-excerpt.html"))
        result = await source.read(COMMUNITY_URL)
        self.assertEqual(result["type"], "tutorial")
        self.assertEqual(result["title"], "Create机械动力 站内教程目录大纲")
        self.assertEqual(result["metadata"]["updated"], "2026-06-29 01:09:12")
        self.assertNotIn("authors", result["metadata"])
        self.assertEqual(result["metadata"]["mod"]["url"], MOD_URL)

    async def test_personal_tutorial_retains_author_and_republication_notice(self):
        source, _ = self.source(PERSONAL_URL, fixture("post-2285-excerpt.html"))
        result = await source.read(PERSONAL_URL)
        self.assertEqual(result["title"], "小机械——无限圆石")
        self.assertEqual(result["metadata"]["authors"][0]["name"], "雪菜肉丝面")
        self.assertIn("禁止转载", result["metadata"]["copyright"])

    async def test_outbound_wrappers_are_decoded_locally_without_requests(self):
        source, fetcher = self.source(MOD_URL, fixture("class-2021-excerpt.html"))
        result = await source.read(MOD_URL)
        urls = {link["url"] for link in result["links"]}
        self.assertIn("https://www.curseforge.com/minecraft/mc-mods/create", urls)
        self.assertIn("https://modrinth.com/mod/create", urls)
        self.assertIn("https://modrinth.com/mod/create-fabric", urls)
        self.assertFalse(any("link.mcmod.cn" in url for url in urls))
        self.assertEqual(len(fetcher.calls), 1)

    async def test_related_tutorial_pagination_uses_only_observed_links(self):
        source, fetcher = self.source(MOD_URL, fixture("class-2021-excerpt.html"))
        first = await source.related(MOD_URL, limit=2)
        second = await source.related(MOD_URL, limit=2, page=2)
        self.assertEqual(first["total"], 4)
        self.assertEqual(len(first["results"]), 2)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["next_page"], 2)
        self.assertEqual(len(second["results"]), 2)
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_page"])
        self.assertTrue(
            all(
                link["type"] == "tutorial"
                for link in first["results"] + second["results"]
            )
        )
        self.assertEqual({call[0] for call in fetcher.calls}, {MOD_URL})

    async def test_related_filter_is_case_insensitive_and_has_honest_scope(self):
        source, _ = self.source(MOD_URL, fixture("class-2021-excerpt.html"))
        result = await source.related(MOD_URL, query="ae2")
        self.assertEqual(result["total"], 1)
        self.assertIn("AE2", result["results"][0]["title"])
        self.assertEqual(
            result["results"][0]["url"], "https://www.mcmod.cn/post/6617.html"
        )
        self.assertIn("coverage", result)

    async def test_related_item_links_are_distinct_from_tutorials_and_catalogs(self):
        source, _ = self.source(MOD_URL, fixture("class-2021-excerpt.html"))
        result = await source.related(MOD_URL, kind="item")
        self.assertGreater(result["total"], 0)
        self.assertTrue(all(link["type"] == "item" for link in result["results"]))
        self.assertIn(
            "https://www.mcmod.cn/item/330128.html",
            {link["url"] for link in result["results"]},
        )
        beyond = await source.related(MOD_URL, kind="item", page=99)
        self.assertEqual(beyond["results"], [])
        self.assertFalse(beyond["has_more"])

    async def test_lazy_images_tables_code_and_headings_survive_markdown(self):
        html = """<div class="itemname"><h5>Fixture mechanism</h5></div>
        <div class="item-content">
          <p><span class="common-text-title common-text-title-1">Setup</span></p>
          <table><tr><th>Input</th><th>Output</th></tr><tr><td>Ore</td><td>Dust</td></tr></table>
          <pre><code>first_line\nsecond_line</code></pre>
          <img src="/static/public/images/loading-colourful.gif"
            data-src="https://i.mcmod.cn/editor/upload/20220512/1652326424_394483_uOSM.webp"
            alt="Example layout">
          <script>do_not_include_this()</script>
        </div>"""
        source, _ = self.source(ITEM_URL, html)
        result = await source.read(ITEM_URL)
        text = result["text"]
        self.assertIn("## Setup", text)
        self.assertIn("| Input | Output |", text)
        self.assertIn("| Ore | Dust |", text)
        self.assertIn("first_line\nsecond_line", text)
        self.assertIn("![Example layout](https://i.mcmod.cn/", text)
        self.assertNotIn("loading-colourful.gif", text)
        self.assertNotIn("do_not_include_this", text)

    async def test_read_does_not_silently_shorten_a_long_article(self):
        paragraphs = "".join(
            f"<p>Step {index}: observed evidence.</p>" for index in range(700)
        )
        html = (
            '<div class="itemname"><h5>Long fixture</h5></div><div class="item-content">'
            + paragraphs
            + "<p>FINAL OBSERVED PARAGRAPH</p></div>"
        )
        source, _ = self.source(ITEM_URL, html)
        result = await source.read(ITEM_URL)
        self.assertGreater(len(result["text"]), 20000)
        self.assertTrue(result["text"].endswith("FINAL OBSERVED PARAGRAPH"))
        self.assertEqual(result["text"].count("observed evidence."), 700)

    async def test_unsafe_or_unknown_destinations_are_not_exposed(self):
        encoded = base64.b64encode(b"http://127.0.0.1/private").decode()
        html = f"""<div class="itemname"><h5>Link fixture</h5></div><div class="item-content">
        <p>Observed mechanism.</p>
        <a href="javascript:alert(1)">Unsafe script</a>
        <a href="https://unknown.example/source">Unknown external site</a>
        <a href="https://link.mcmod.cn/target/{encoded}">Private destination</a>
        <a href="https://link.mcmod.cn/target/not!valid">Invalid wrapper</a>
        <a href="//www.mcmod.cn/post/2373.html">Known tutorial</a>
        <img src="http://127.0.0.1/pixel" alt="Private image">
        </div>"""
        source, fetcher = self.source(ITEM_URL, html)
        result = await source.read(ITEM_URL)
        self.assertEqual([link["url"] for link in result["links"]], [COMMUNITY_URL])
        self.assertNotIn("127.0.0.1", result["text"])
        self.assertNotIn("unknown.example", result["text"])
        self.assertNotIn("javascript:", result["text"])
        self.assertEqual(len(fetcher.calls), 1)

    async def test_missing_or_empty_article_body_is_an_error(self):
        for html in (
            "<html><title>MC百科</title><body>Login required</body></html>",
            '<div class="itemname"><h5>Empty</h5></div><div class="item-content"></div>',
            "",
        ):
            with self.subTest(html=html):
                source, _ = self.source(ITEM_URL, html)
                with self.assertRaises(SourceError):
                    await source.read(ITEM_URL)

    async def test_verification_pages_do_not_become_successful_empty_articles(self):
        html = '<html><title>访问验证 - 人机验证</title><div class="itemname"><h5>Placeholder</h5></div><div class="item-content">Challenge text</div></html>'
        source, _ = self.source(ITEM_URL, html)
        with self.assertRaises(SourceError) as raised:
            await source.read(ITEM_URL)
        self.assertEqual(raised.exception.code, "access_blocked")

    async def test_related_does_not_turn_an_empty_mod_article_into_no_results(self):
        html = '<div class="class-title"><h3>Empty fixture</h3></div><div class="class-menu-main" data-frame="2"><ul><li data-id="1"></li></ul></div>'
        source, _ = self.source(MOD_URL, html)
        with self.assertRaises(SourceError) as raised:
            await source.related(MOD_URL)
        self.assertEqual(raised.exception.code, "parse_error")

    async def test_transport_denials_are_preserved(self):
        denial = SourceError("http_403", "Upstream access denied.")
        source, _ = self.source(ITEM_URL, denial)
        with self.assertRaises(SourceError) as raised:
            await source.read(ITEM_URL)
        self.assertIs(raised.exception, denial)

    async def test_disallowed_urls_fail_before_network_access(self):
        source, fetcher = self.source(ITEM_URL, "unused")
        for url in (
            "http://www.mcmod.cn/item/330128.html",
            "https://mcmod.cn.evil.example/item/330128.html",
            "https://user@www.mcmod.cn/item/330128.html",
            "https://www.mcmod.cn:8080/item/330128.html",
            "https://www.mcmod.cn/item/../post/1.html",
            "https://www.mcmod.cn/item/0.html",
            "https://www.mcmod.cn/item/add/330128/",
            "https://search.mcmod.cn/s?key=create",
            "https://127.0.0.1/item/330128.html",
            "https://www.mcmod.cn/item/330128.html?download=1",
        ):
            with self.subTest(url=url), self.assertRaises(SourceError):
                await source.read(url)
        self.assertEqual(fetcher.calls, [])

    async def test_related_arguments_and_non_mod_input_fail_before_fetch(self):
        source, fetcher = self.source(MOD_URL, "unused")
        cases = [
            {"kind": "all"},
            {"limit": 0},
            {"limit": 51},
            {"limit": True},
            {"page": 0},
            {"page": True},
            {"query": None},
        ]
        for arguments in cases:
            with self.subTest(arguments=arguments), self.assertRaises(SourceError):
                await source.related(MOD_URL, **arguments)
        with self.assertRaises(SourceError):
            await source.related(ITEM_URL)
        self.assertEqual(fetcher.calls, [])


if __name__ == "__main__":
    unittest.main()
