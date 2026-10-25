"""Read public MC百科 articles without crawling its disallowed search endpoint."""

from __future__ import annotations

import base64
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag
from markdownify import markdownify

from .transport import SourceError

_ARTICLE_PATH = re.compile(r"^/(class|item|post)/([1-9][0-9]*)\.html$")
_TYPES = {"class": "mod", "item": "item", "post": "tutorial"}
_ARTICLE_HOSTS = {"mcmod.cn", "www.mcmod.cn"}
_LINK_HOSTS = _ARTICLE_HOSTS | {
    "curseforge.com",
    "www.curseforge.com",
    "modrinth.com",
    "www.modrinth.com",
    "github.com",
    "minecraft.net",
    "www.minecraft.net",
    "minecraft.wiki",
    "zh.minecraft.wiki",
    "www.bilibili.com",
    "bilibili.com",
    "youtu.be",
    "www.youtube.com",
    "youtube.com",
}
_IMAGE_HOSTS = _ARTICLE_HOSTS | {"i.mcmod.cn", "static.mcmod.cn"}
_BODY_SELECTORS = {
    "mod": '.class-menu-main[data-frame="2"] > ul > li[data-id="1"]',
    "item": ".item-content",
    "tutorial": ".post-content > .text",
}
_TITLE_SELECTORS = {
    "mod": ".class-title h3",
    "item": ".itemname h5",
    "tutorial": ".postname h5",
}
_BLOCKED_TITLE = re.compile(
    r"验证码|人机验证|访问验证|访问过于频繁|访问被拒绝|"
    r"access denied|\bforbidden\b|just a moment|too many requests|cloudflare",
    re.IGNORECASE,
)


def _text(node: Tag | None) -> str:
    """Return normalized visible text from a selected node."""
    return node.get_text(" ", strip=True) if node else ""


def _canonical_article(url: str, *, require_mod: bool = False) -> tuple[str, str]:
    """Validate a numeric public article URL and return its canonical form."""
    if not isinstance(url, str):
        raise SourceError("invalid_url", "MC百科 URL must be a string.")
    try:
        parts = urlsplit(url.strip())
        match = _ARTICLE_PATH.fullmatch(parts.path)
        valid = (
            parts.scheme == "https"
            and parts.hostname in _ARTICLE_HOSTS
            and parts.port in (None, 443)
            and not parts.username
            and not parts.password
            and not parts.query
            and match is not None
        )
    except ValueError:
        valid, match = False, None
    if not valid or match is None or (require_mod and match[1] != "class"):
        raise SourceError(
            "invalid_url",
            "Use an official HTTPS MC百科 numeric class/item/post article URL.",
        )
    return f"https://www.mcmod.cn{parts.path}", _TYPES[match[1]]


def _safe_url(value: str, base: str, *, image: bool = False) -> str | None:
    """Resolve an observed URL; decode outbound wrappers without fetching them."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        resolved = urljoin(base, value.strip())
        parts = urlsplit(resolved)
        if parts.hostname == "link.mcmod.cn" and parts.path.startswith("/target/"):
            encoded = unquote(parts.path.removeprefix("/target/"))
            if len(encoded) > 8192:
                return None
            encoded = encoded.replace("-", "+").replace("_", "/")
            decoded = base64.b64decode(
                encoded + "=" * (-len(encoded) % 4), validate=True
            ).decode("utf-8")
            resolved = urljoin("https://www.mcmod.cn/", decoded)
            parts = urlsplit(resolved)
        allowed = _IMAGE_HOSTS if image else _LINK_HOSTS
        if (
            parts.scheme not in ("http", "https")
            or parts.hostname not in allowed
            or parts.port not in (None, 80, 443)
            or parts.username
            or parts.password
        ):
            return None
        # These public services support HTTPS; no wrapper or redirect is requested.
        return urlunsplit(
            ("https", parts.hostname, parts.path, parts.query, parts.fragment)
        )
    except (ValueError, UnicodeError):
        return None


def _link_type(url: str) -> str:
    """Classify an observed link without guessing a target URL."""
    parts = urlsplit(url)
    match = _ARTICLE_PATH.fullmatch(parts.path)
    if parts.hostname in _ARTICLE_HOSTS and match:
        return _TYPES[match[1]]
    if parts.hostname in _ARTICLE_HOSTS and parts.path.startswith("/item/list/"):
        return "catalog"
    if parts.hostname in {"curseforge.com", "www.curseforge.com"}:
        return "curseforge"
    if parts.hostname in {"modrinth.com", "www.modrinth.com"}:
        return "modrinth"
    return "external"


def _links(nodes: list[Tag], base: str) -> list[dict[str, str]]:
    """Collect distinct, allowed links from explicitly selected article sections."""
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for node in nodes:
        for anchor in node.select("a[href]"):
            url = _safe_url(anchor.get("href", ""), base)
            if not url or url.split("#", 1)[0] == base or url in seen:
                continue
            title = (
                _text(anchor)
                or anchor.get("data-original-title")
                or anchor.get("title")
            )
            if not title:
                image = anchor.select_one("img[alt]")
                title = image.get("alt", "") if image else ""
            if not title:
                continue
            seen.add(url)
            result.append({"title": str(title), "url": url, "type": _link_type(url)})
    return result


def _markdown(body: Tag, base: str) -> str:
    """Convert the full article body while retaining safe figures, tables and code."""
    fragment = BeautifulSoup(str(body), "html.parser")
    for node in fragment.select(
        "script, style, iframe, object, embed, form, button, input, textarea, "
        ".common-tag-mark[data-type='title-menu']"
    ):
        node.decompose()
    for node in fragment.select("img"):
        url = _safe_url(node.get("data-src") or node.get("src", ""), base, image=True)
        if not url or "loading-colourful.gif" in url or "loadfail.gif" in url:
            node.decompose()
            continue
        node["src"] = url
        node["alt"] = node.get("alt") or "MC百科 illustration"
    for anchor in fragment.select("a[href]"):
        url = _safe_url(anchor.get("href", ""), base)
        if url:
            anchor["href"] = url
        else:
            anchor.unwrap()
    for heading in fragment.select(".common-text-title"):
        classes = " ".join(heading.get("class", []))
        level = re.search(r"common-text-title-([1-6])(?:\s|$)", classes)
        heading.name = f"h{min(int(level[1]) + 1, 6)}" if level else "h2"
    # The text is deliberately not shortened here. Pagination belongs to the service.
    return markdownify(str(fragment), heading_style="ATX", bullets="-").strip()


def _metadata(soup: BeautifulSoup, kind: str, base: str) -> dict[str, Any]:
    """Extract fields evidenced by the article rather than navigation or guesses."""
    result: dict[str, Any] = {}
    author_selector = (
        ".class-info-left .author .member .name a"
        if kind == "mod"
        else ".post-user-name a"
    )
    authors = []
    for anchor in soup.select(author_selector):
        name = _text(anchor)
        if name and name not in {author["name"] for author in authors}:
            author = {"name": name}
            url = _safe_url(anchor.get("href", ""), base)
            if url:
                author["url"] = url
            authors.append(author)
    if authors:
        result["authors"] = authors

    notice = soup.select_one(".post-cc") or soup.select_one(".copyleft")
    if notice and _text(notice):
        result["copyright"] = _text(notice)
    rows = (
        soup.select(".class-info-left > ul > li")
        if kind == "mod"
        else soup.select(".common-rowlist-2 > li")
    )
    details = {}
    for row in rows:
        visible = _text(row)
        label, separator, value = re.sub(r"\s+", " ", visible).partition(
            ":" if ":" in visible else "："
        )
        if not separator:
            continue
        label, value = label.strip(), value.strip()
        timestamp = row.get("data-original-title", "")
        if label in {"最后编辑", "最后更新"} and timestamp:
            result["updated"] = timestamp
        if label in {"创建日期", "收录时间"} and timestamp:
            result["created"] = timestamp
        if label in {"浏览量", "浏览次数"}:
            digits = value.replace(",", "")
            if digits.isdigit():
                result["views"] = int(digits)
        if label in {"支持平台", "运行环境", "教程权限", "编辑次数", "模组标签"}:
            details[label] = value
    if details:
        result["details"] = details

    versions = []
    loader_versions = {}
    for title in soup.select(".class-info-left .mcver-title"):
        loader = re.split(r"\s*\(", _text(title), maxsplit=1)[0].rstrip(" :：")
        row = title.find_next_sibling(class_="mcver-row")
        found = []
        if row:
            for anchor in row.select("a[href]"):
                version = parse_qs(urlsplit(anchor["href"]).query).get("mcver", [""])[0]
                if (
                    re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version)
                    and version not in found
                ):
                    found.append(version)
                    if version not in versions:
                        versions.append(version)
        if loader and found:
            loader_versions[loader] = found
    if versions:
        result["game_versions"] = versions
    if loader_versions:
        result["loaders"] = list(loader_versions)
        result["loader_versions"] = loader_versions
    if kind == "mod":
        status = _text(soup.select_one(".class-status"))
        if status:
            result["status"] = status
    else:
        breadcrumb = soup.select_one('.common-nav a[href^="/class/"]')
        # A category breadcrumb precedes the numeric mod link on some pages.
        for anchor in soup.select(".common-nav a[href]"):
            url = _safe_url(anchor.get("href", ""), base)
            if url and _link_type(url) == "mod":
                breadcrumb = anchor
                result["mod"] = {"title": _text(breadcrumb), "url": url}
                break
    return result


class McmodSource:
    """Read allowed MC百科 article paths through a supplied bounded fetcher.

    Args:
        fetcher: Object exposing async ``get_text(url, params=None, headers=None)``.
    """

    def __init__(self, fetcher: Any):
        self.fetcher = fetcher

    async def _load(
        self, url: str, *, require_mod: bool = False
    ) -> tuple[str, str, BeautifulSoup, Tag, str]:
        """Fetch and validate the expected article body, failing closed on error pages."""
        canonical, kind = _canonical_article(url, require_mod=require_mod)
        html = await self.fetcher.get_text(canonical)
        if not isinstance(html, str) or not html.strip():
            raise SourceError("empty_response", "MC百科 returned an empty response.")
        soup = BeautifulSoup(html, "html.parser")
        if _BLOCKED_TITLE.search(_text(soup.title)):
            raise SourceError(
                "access_blocked",
                "MC百科 returned a verification or access-denied page.",
            )
        body = soup.select_one(_BODY_SELECTORS[kind])
        if body is None:
            raise SourceError(
                "parse_error",
                "MC百科 article body is missing; access may be blocked or its layout changed.",
            )
        title = _text(soup.select_one(_TITLE_SELECTORS[kind]))
        if kind == "mod" and not title:
            title = _text(soup.select_one(".class-title h4"))
        text = _markdown(body, canonical)
        if not title or not text:
            raise SourceError(
                "parse_error", "MC百科 article title or readable body is empty."
            )
        return canonical, kind, soup, body, text

    async def read(self, url: str) -> dict[str, Any]:
        """Read one complete article for grounded summarization, retaining its notice.

        Args:
            url: Official numeric mod, item or tutorial article URL.

        Returns:
            Full Markdown body, observed metadata and safe observed links.

        Raises:
            SourceError: The URL is unsupported or no genuine article was obtained.
        """
        canonical, kind, soup, body, text = await self._load(url)
        title = _text(soup.select_one(_TITLE_SELECTORS[kind]))
        if kind == "mod":
            english = _text(soup.select_one(".class-title h4"))
            if english and english != title:
                title = f"{title} ({english})" if title else english
        sections = [body]
        if kind == "mod":
            sections.extend(
                soup.select(
                    '.class-info-left, .class-menu-main[data-frame="1"] > ul > li[data-id="1"], .text-area-post'
                )
            )
        elif kind in {"item", "tutorial"}:
            sections.extend(soup.select(".common-nav"))
        return {
            "source": "mcmod",
            "type": kind,
            "title": title,
            "url": canonical,
            "text": text,
            "metadata": _metadata(soup, kind, canonical),
            "links": _links(sections, canonical),
        }

    async def related(
        self,
        mod_url: str,
        kind: str = "tutorial",
        query: str = "",
        limit: int = 10,
        page: int = 1,
    ) -> dict[str, Any]:
        """Page links actually exposed by a mod page, not the complete MC百科 database.

        Args:
            mod_url: Official numeric mod article URL.
            kind: ``tutorial`` for the tutorial tab or ``item`` for linked entries.
            query: Case-insensitive title substring filter.
            limit: Number of links per page, from 1 through 50.
            page: One-based page number of this observed link collection.

        Returns:
            Matching links and transparent pagination of the selected collection.
        """
        if kind not in {"tutorial", "item"}:
            raise SourceError(
                "invalid_argument", "Related kind must be tutorial or item."
            )
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 50
        ):
            raise SourceError(
                "invalid_argument", "Related limit must be an integer from 1 to 50."
            )
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise SourceError(
                "invalid_argument", "Related page must be a positive integer."
            )
        if not isinstance(query, str):
            raise SourceError("invalid_argument", "Related query must be text.")
        canonical, _, soup, body, _ = await self._load(mod_url, require_mod=True)
        if kind == "tutorial":
            sections = soup.select(
                '.class-menu-main[data-frame="2"] > ul > li[data-id="2"]'
            )
        else:
            sections = [body]
            sections.extend(
                soup.select('.class-menu-main[data-frame="1"] > ul > li[data-id="1"]')
            )
        candidates = [
            link
            for link in _links(sections, canonical)
            if link["type"] == kind
            and query.strip().casefold() in link["title"].casefold()
        ]
        start = (page - 1) * limit
        has_more = start + limit < len(candidates)
        return {
            "source": "mcmod",
            "url": canonical,
            "kind": kind,
            "results": candidates[start : start + limit],
            "total": len(candidates),
            "page": page,
            "has_more": has_more,
            "next_page": page + 1 if has_more else None,
            "coverage": "Links exposed in this mod page's tutorial tab or introduction; not a complete database search.",
        }
