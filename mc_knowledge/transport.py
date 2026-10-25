"""Bounded HTTPS transport for fixed public information sources."""

import asyncio
import hashlib
import json
import re
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlsplit

import httpx

ALLOWED_HOSTS = {
    "www.mcmod.cn",
    "mcmod.cn",
    "api.modrinth.com",
    "api.curseforge.com",
    "www.bing.com",
    "cn.bing.com",
}


class SourceError(Exception):
    """Expose a safe machine-readable source failure without response secrets."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def validate_url(url: str) -> str:
    """Allow only public HTTPS URLs used by the source adapters.

    Args:
        url: An adapter-generated URL.

    Returns:
        The validated URL without its fragment.

    Raises:
        SourceError: The host, scheme, authority, or route is unsupported.
    """
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or "\\" in url
            or re.search(r"[\x00-\x20\x7f]", url)
        ):
            raise ValueError
        if parsed.hostname in {"mcmod.cn", "www.mcmod.cn"}:
            if not re.fullmatch(r"/(class|item|post)/[1-9]\d*\.html", parsed.path):
                raise ValueError
        elif (
            (
                parsed.hostname in {"www.bing.com", "cn.bing.com"}
                and parsed.path != "/search"
            )
            or parsed.hostname == "api.modrinth.com"
            and not parsed.path.startswith("/v2/")
            or parsed.hostname == "api.curseforge.com"
            and not parsed.path.startswith("/v1/")
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise SourceError(
            "invalid_url", "Only supported public Minecraft source URLs can be read"
        ) from None
    return parsed._replace(fragment="").geturl()


class Fetcher:
    """Cache bounded source responses and serialize requests to each host."""

    def __init__(self, *, client=None, timeout=18, cache_ttl=300):
        self.client = client
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.cache = OrderedDict()
        self.locks = {}
        self.last_request = {}
        self.slots = asyncio.Semaphore(3)

    async def get_text(self, url, params=None, headers=None):
        """Read limited source text, refusing internal redirects and challenges.

        Args:
            url: A fixed supported source endpoint.
            params: Public query parameters.
            headers: Optional provider authentication, retained only in memory.

        Returns:
            Decoded source text.

        Raises:
            SourceError: The request is blocked, limited, invalid, or unavailable.
        """
        url = validate_url(str(url))
        # Credential digests distinguish cache entries without persisting a key.
        key = hashlib.sha256(
            json.dumps([url, params, headers], sort_keys=True, default=str).encode()
        ).hexdigest()
        cached = self.cache.get(key)
        if cached and time.monotonic() - cached[0] < self.cache_ttl:
            self.cache.move_to_end(key)
            return cached[1]
        own_client = self.client is None
        client = self.client or httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            trust_env=urlsplit(url).hostname != "api.modrinth.com",
        )
        try:
            async with self.slots:
                response_text = await asyncio.wait_for(
                    self._read(client, url, params, headers), timeout=self.timeout + 2
                )
        finally:
            if own_client:
                await client.aclose()
        self.cache[key] = (time.monotonic(), response_text)
        self.cache.move_to_end(key)
        while len(self.cache) > 48:
            self.cache.popitem(last=False)
        return response_text

    async def _read(self, client, url, params, headers):
        """Execute the redirect and streaming loop within a total deadline.

        Args:
            client: The HTTPX client.
            url: A validated endpoint.
            params: Public query parameters.
            headers: Optional in-memory provider headers.

        Returns:
            Decoded source response.

        Raises:
            SourceError: A source or transport constraint fails.
        """
        request_headers = {
            "User-Agent": "AstrBot-MinecraftKnowledge/1.0 (read-only Minecraft reference assistant)",
            "Accept": "application/json,text/html,application/rss+xml,application/xml;q=0.9",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            **(headers or {}),
        }
        original_host = urlsplit(url).hostname
        try:
            for _ in range(4):
                host = urlsplit(url).hostname
                lock = self.locks.setdefault(host, asyncio.Lock())
                async with lock:
                    gap = 0.5 - (time.monotonic() - self.last_request.get(host, 0))
                    if gap > 0:
                        await asyncio.sleep(gap)
                    self.last_request[host] = time.monotonic()
                    async with client.stream(
                        "GET", url, params=params, headers=request_headers
                    ) as response:
                        if response.status_code in (301, 302, 303, 307, 308):
                            redirected = validate_url(
                                urljoin(
                                    str(response.url),
                                    response.headers.get("location", ""),
                                )
                            )
                            bing_family = {"www.bing.com", "cn.bing.com"}
                            if (
                                urlsplit(redirected).hostname != original_host
                                and not {
                                    urlsplit(redirected).hostname,
                                    original_host,
                                }
                                <= bing_family
                            ):
                                raise SourceError(
                                    "redirect_blocked",
                                    "Cross-source redirects are not followed",
                                )
                            url, params = redirected, None
                            continue
                        if response.status_code == 429:
                            raise SourceError(
                                "rate_limited",
                                "Source rate limit reached; retry later",
                            )
                        if response.status_code in (401, 403):
                            raise SourceError(
                                "access_blocked",
                                "Source denied this request or requires valid API credentials",
                            )
                        if response.status_code == 404:
                            raise SourceError(
                                "not_found",
                                "The source page or project was not found",
                            )
                        if not 200 <= response.status_code < 300:
                            raise SourceError(
                                "source_http_error",
                                f"Source returned HTTP {response.status_code}",
                            )
                        body = bytearray()
                        async for block in response.aiter_bytes():
                            body.extend(block)
                            if len(body) > 3 * 1024 * 1024:
                                raise SourceError(
                                    "response_too_large",
                                    "Source response exceeds the bounded reading limit",
                                )
                        text = bytes(body).decode(
                            response.encoding or "utf-8", errors="replace"
                        )
                        title = re.search(
                            r"<title[^>]*>(.*?)</title>",
                            text[:150000],
                            re.IGNORECASE | re.DOTALL,
                        )
                        if title and re.search(
                            r"just a moment|access denied|captcha|人机验证|安全验证|访问验证",
                            title.group(1),
                            re.IGNORECASE,
                        ):
                            raise SourceError(
                                "access_blocked",
                                "Source returned a verification page rather than reference content",
                            )
                        return text
            raise SourceError("redirect_limit", "Source exceeded the redirect limit")
        except SourceError:
            raise
        except (httpx.HTTPError, TimeoutError, OSError):
            raise SourceError(
                "network_error", "The reference source is temporarily unreachable"
            ) from None

    async def get_json(self, url, params=None, headers=None):
        """Decode a provider JSON response without leaking malformed bodies.

        Args:
            url: Provider API endpoint.
            params: Public query parameters.
            headers: Optional in-memory provider authentication.

        Returns:
            A JSON object or array.

        Raises:
            SourceError: The response is not valid structured data.
        """
        try:
            result = json.loads(await self.get_text(url, params, headers))
            if not isinstance(result, (dict, list)):
                raise TypeError
            return result
        except (ValueError, TypeError):
            raise SourceError(
                "invalid_response", "Source returned invalid structured data"
            ) from None
