"""Verify the real HTTP transport with bounded in-memory HTTPX responses."""

import json
import unittest

import httpx

from mc_knowledge.transport import Fetcher, SourceError, validate_url


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_cached_text_and_json_retain_values_without_repeating_requests(self):
        calls = []

        async def handler(request):
            calls.append(request)
            return httpx.Response(200, json={"downloads": 123}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = Fetcher(client=client)
            for _ in range(2):
                value = await fetcher.get_json(
                    "https://api.modrinth.com/v2/project/sodium"
                )
                self.assertEqual(value["downloads"], 123)
            self.assertEqual(len(calls), 1)
            self.assertIn("AstrBot-MinecraftKnowledge", calls[0].headers["user-agent"])

    async def test_credential_changes_do_not_reuse_another_authenticated_response(self):
        async def handler(request):
            return httpx.Response(200, json={"ok": True}, request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = Fetcher(client=client)
            for key in ["fixture-one", "fixture-two"]:
                await fetcher.get_json(
                    "https://api.curseforge.com/v1/mods/1", headers={"x-api-key": key}
                )
            self.assertEqual(len(fetcher.cache), 2)
            self.assertNotIn("fixture-one", json.dumps(list(fetcher.cache)))

    async def test_private_redirects_challenges_statuses_and_large_responses_are_errors(
        self,
    ):
        cases = [
            (302, {"location": "http://127.0.0.1/secret"}, b"", "invalid_url"),
            (
                302,
                {"location": "https://api.modrinth.com/v2/project/sodium"},
                b"",
                "redirect_blocked",
            ),
            (403, {}, b"secret body", "access_blocked"),
            (429, {}, b"", "rate_limited"),
            (200, {}, b"<title>Just a moment...</title>", "access_blocked"),
            (200, {}, b"a" * (3 * 1024 * 1024 + 1), "response_too_large"),
        ]
        for status, headers, body, code in cases:

            async def handler(request, status=status, headers=headers, body=body):
                return httpx.Response(
                    status, headers=headers, content=body, request=request
                )

            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler)
            ) as client:
                with self.assertRaises(SourceError) as caught:
                    await Fetcher(client=client).get_text(
                        "https://www.mcmod.cn/class/2021.html"
                    )
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn("secret body", caught.exception.message)

    async def test_expected_bing_region_redirect_keeps_query_and_does_not_follow_other_hosts(
        self,
    ):
        requests = []

        async def handler(request):
            requests.append(str(request.url))
            if request.url.host == "www.bing.com":
                return httpx.Response(
                    302,
                    headers={
                        "location": "https://cn.bing.com/search?q=Create&format=rss"
                    },
                    request=request,
                )
            return httpx.Response(200, text="<rss />", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await Fetcher(client=client).get_text(
                "https://www.bing.com/search", params={"q": "Create"}
            )
            self.assertEqual(result, "<rss />")
            self.assertEqual(len(requests), 2)
            self.assertIn("format=rss", requests[-1])


class UrlTests(unittest.TestCase):
    def test_untrusted_and_non_reference_routes_are_never_requested(self):
        for url in [
            "http://127.0.0.1/",
            "https://api.modrinth.com.evil.example/v2/a",
            "https://user:secret@api.modrinth.com/v2/a",
            "https://www.mcmod.cn/class/edit/1",
            "https://search.mcmod.cn/s?key=x",
            "https://www.bing.com/images",
            "file:///secret",
        ]:
            with self.assertRaises(SourceError):
                validate_url(url)
