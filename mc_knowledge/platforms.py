"""Read-only adapters for the official Minecraft mod distribution APIs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, ClassVar
from urllib.parse import urlsplit

from .transport import SourceError

_PROJECT = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_GAME_VERSION = re.compile(r"^(?:\d+\.\d+(?:\.\d+)?(?:[- ].*)?|\d{2}w\d{2}[a-z])$")
_CF_LOADERS = {
    "forge": 1,
    "cauldron": 2,
    "liteloader": 3,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}
_CF_LOADER_NAMES = {value: key for key, value in _CF_LOADERS.items()}
_CF_SORTS = {"relevance": 2, "downloads": 6, "updated": 3, "newest": 11, "name": 4}
_MR_SORTS = {"relevance", "downloads", "updated", "newest", "follows"}
_MR_LOADERS = set(_CF_LOADERS) | {
    "rift",
    "modloader",
    "risugamis-modloader",
    "babric",
    "ornithe",
    "legacy-fabric",
    "nilloader",
}


def _project(value: Any) -> str:
    """Validate an already normalized project identifier.

    Args:
        value: A project ID or slug, rather than a URL or path.

    Returns:
        The validated identifier.
    """
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise SourceError("invalid_argument", "项目必须是有效的 ID 或 slug。")
    result = str(value).strip()
    if not _PROJECT.fullmatch(result):
        raise SourceError("invalid_argument", "项目必须是有效的 ID 或 slug。")
    return result


def _paging(limit: int, page: int) -> tuple[int, int]:
    """Validate bounded, one-based pagination parameters."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise SourceError("invalid_argument", "每页数量必须为 1 至 50。")
    if isinstance(page, bool) or not isinstance(page, int) or not 1 <= page <= 10000:
        raise SourceError("invalid_argument", "页码必须为正整数且不超过 10000。")
    return limit, (page - 1) * limit


def _query(value: str) -> str:
    """Validate a bounded search term without changing its language."""
    if not isinstance(value, str) or not value.strip() or len(value) > 200:
        raise SourceError("invalid_argument", "请提供不超过 200 字的搜索词。")
    return value.strip()


def _filters(game_version: str, loader: str) -> tuple[str, str]:
    """Normalize bounded version and loader filter values."""
    if not isinstance(game_version, str) or len(game_version) > 80:
        raise SourceError("invalid_argument", "游戏版本筛选无效。")
    if not isinstance(loader, str) or len(loader) > 40:
        raise SourceError("invalid_argument", "加载器筛选无效。")
    return game_version.strip(), loader.strip().lower()


def _url(value: Any) -> str:
    """Keep public HTTPS links as data without following them."""
    if not isinstance(value, str):
        return ""
    try:
        parsed = urlsplit(value)
        return (
            value
            if parsed.scheme == "https"
            and parsed.hostname
            and not parsed.username
            and not parsed.password
            else ""
        )
    except ValueError:
        return ""


def _links(values: dict[str, Any]) -> list[dict[str, str]]:
    """Create a compact set of verified-shape source links."""
    return [
        {"title": label, "url": link}
        for label, value in values.items()
        if (link := _url(value))
    ]


def _date_key(value: Any) -> float:
    """Sort actual ISO publication dates rather than version names."""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()  # noqa: FURB162 - Python 3.10 compatibility.
    except (ValueError, TypeError, OverflowError):
        return 0.0


def _page_result(
    source: str, key: str, rows: list, total: int, page: int, limit: int
) -> dict:
    """Build a source-scoped pagination envelope."""
    has_more = page * limit < total
    return {
        "source": source,
        key: rows,
        "total": total,
        "page": page,
        "has_more": has_more,
        "next_page": page + 1 if has_more else None,
    }


class _DescriptionText(HTMLParser):
    """Extract readable HTML description text without executing page content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if self.hidden:
            return
        if tag in {
            "p",
            "div",
            "li",
            "br",
            "h1",
            "h2",
            "h3",
            "h4",
            "tr",
            "blockquote",
            "pre",
        }:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")
        if tag == "img":
            alt = dict(attrs).get("alt")
            if alt:
                self.parts.append(f"[图片：{alt}]")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {
            "p",
            "div",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "tr",
            "blockquote",
            "pre",
        }:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", "".join(self.parts)).strip()


class ModrinthSource:
    """Read public mod metadata through the official Modrinth v2 API.

    Args:
        fetcher: A transport exposing async get_json and get_text methods.
    """

    source = "modrinth"
    api = "https://api.modrinth.com/v2"
    headers: ClassVar[dict[str, str]] = {
        "User-Agent": "QQBridgeMinecraftKnowledge/1.0",
        "Accept": "application/json",
    }

    def __init__(self, fetcher: Any) -> None:
        self.fetcher = fetcher

    async def search(
        self,
        query: str,
        game_version: str = "",
        loader: str = "",
        limit: int = 5,
        page: int = 1,
        sort: str = "relevance",
    ) -> dict:
        """Search mod projects while preserving platform-specific statistics.

        Args:
            query: A mod name or search phrase.
            game_version: An optional exact Minecraft version.
            loader: An optional mod loader.
            limit: The maximum results per page, from 1 to 50.
            page: A one-based page number.
            sort: An official Modrinth search ordering.

        Returns:
            A source-scoped result page with exact platform download counts.
        """

        query = _query(query)
        limit, offset = _paging(limit, page)
        game_version, loader = _filters(game_version, loader)
        if sort not in _MR_SORTS:
            raise SourceError("invalid_argument", "不支持此 Modrinth 排序方式。")
        facets = [["project_type:mod"]]
        if game_version:
            facets.append([f"versions:{game_version}"])
        if loader:
            facets.append([f"categories:{loader}"])
        params = {
            "query": query,
            "facets": json.dumps(facets, ensure_ascii=False, separators=(",", ":")),
            "limit": limit,
            "offset": offset,
            "index": sort,
        }
        data = await self.fetcher.get_json(
            f"{self.api}/search",
            params=params,
            headers=self.headers,
        )
        rows = []
        for hit in data.get("hits", []):
            if hit.get("project_type") != "mod":
                continue
            rows.append(
                {
                    "project_id": hit.get("project_id"),
                    "slug": hit.get("slug"),
                    "title": hit.get("title", ""),
                    "url": f"https://modrinth.com/mod/{_project(hit.get('slug') or hit.get('project_id'))}",
                    "description": hit.get("description", ""),
                    "download_count": hit.get("downloads"),
                    "download_count_scope": "Modrinth 项目累计下载量（仅该平台）",
                    "authors": [hit["author"]] if hit.get("author") else [],
                    "game_versions": hit.get("versions", []),
                    "loaders": [
                        value
                        for value in hit.get("categories", [])
                        if value in _MR_LOADERS
                    ],
                    "categories": hit.get("categories", []),
                    "updated": hit.get("date_modified"),
                    "published": hit.get("date_created"),
                }
            )
        return _page_result(
            self.source,
            "results",
            rows,
            int(data.get("total_hits", len(rows))),
            page,
            limit,
        )

    async def _get_project(self, project: str) -> dict:
        """Verify a project is a mod before reading its contents or releases."""
        data = await self.fetcher.get_json(
            f"{self.api}/project/{_project(project)}", headers=self.headers
        )
        if data.get("project_type") != "mod":
            raise SourceError(
                "unsupported_project", "该 Modrinth 项目不是 Minecraft 模组。"
            )
        return data

    async def read(self, project: str) -> dict:
        """Read the complete author description and project metadata.

        Args:
            project: A public mod project ID or slug.

        Returns:
            The full description, metadata, and related HTTPS links.
        """
        data = await self._get_project(project)
        slug = _project(data.get("slug") or data.get("id"))
        url = f"https://modrinth.com/mod/{slug}"
        metadata = {
            "project_id": data.get("id"),
            "slug": slug,
            "summary": data.get("description", ""),
            "download_count": data.get("downloads"),
            "download_count_scope": "Modrinth 项目累计下载量（仅该平台）",
            "game_versions": data.get("game_versions", []),
            "loaders": data.get("loaders", []),
            "updated": data.get("updated"),
            "published": data.get("published"),
            "authors": data.get("authors", []),
            "team_id": data.get("team"),
            "organization_id": data.get("organization"),
            "license": data.get("license"),
            "environment": data.get("environment"),
            "client_side": data.get("client_side"),
            "server_side": data.get("server_side"),
            "status": data.get("status"),
        }
        return {
            "source": self.source,
            "type": "mod",
            "title": data.get("title", slug),
            "url": url,
            "text": data.get("body") or data.get("description", ""),
            "metadata": metadata,
            "links": _links(
                {
                    "项目主页": url,
                    "源码": data.get("source_url"),
                    "Wiki": data.get("wiki_url"),
                    "问题反馈": data.get("issues_url"),
                }
            ),
        }

    async def versions(
        self,
        project: str,
        game_version: str = "",
        loader: str = "",
        limit: int = 5,
        page: int = 1,
    ) -> dict:
        """Read files that satisfy both filters on the same release object.

        Args:
            project: A public mod project ID or slug.
            game_version: An optional exact Minecraft version.
            loader: An optional mod loader.
            limit: The maximum releases per page, from 1 to 50.
            page: A one-based page number.

        Returns:
            A release page preserving dependencies and official download links.
        """

        project = _project(project)
        limit, offset = _paging(limit, page)
        game_version, loader = _filters(game_version, loader)
        project_data = await self._get_project(project)
        params: dict[str, Any] = {"include_changelog": "false"}
        if game_version:
            params["game_versions"] = json.dumps([game_version], separators=(",", ":"))
        if loader:
            params["loaders"] = json.dumps([loader], separators=(",", ":"))
        data = await self.fetcher.get_json(
            f"{self.api}/project/{project}/version", params=params, headers=self.headers
        )
        matches = [
            row
            for row in data
            if row.get("project_id") == project_data.get("id")
            and (not game_version or game_version in row.get("game_versions", []))
            and (not loader or loader in row.get("loaders", []))
        ]
        matches.sort(key=lambda row: _date_key(row.get("date_published")), reverse=True)
        rows = []
        for item in matches[offset : offset + limit]:
            rows.append(
                {
                    "version_id": item.get("id"),
                    "project_id": item.get("project_id"),
                    "name": item.get("name", ""),
                    "version_number": item.get("version_number", ""),
                    "release_type": item.get("version_type"),
                    "published": item.get("date_published"),
                    "download_count": item.get("downloads"),
                    "download_count_scope": "Modrinth 该版本累计下载量（仅该平台）",
                    "game_versions": item.get("game_versions", []),
                    "loaders": item.get("loaders", []),
                    "environment": item.get("environment"),
                    "dependencies": item.get("dependencies", []),
                    "url": f"https://modrinth.com/mod/{project}/version/{_project(item.get('id'))}",
                    "files": [
                        {
                            "filename": file.get("filename"),
                            "url": _url(file.get("url")),
                            "size": file.get("size"),
                            "primary": file.get("primary", False),
                            "hashes": file.get("hashes", {}),
                        }
                        for file in item.get("files", [])
                    ],
                }
            )
        return _page_result(self.source, "versions", rows, len(matches), page, limit)


class CurseForgeSource:
    """Read Minecraft mods through an explicitly configured CurseForge key.

    Args:
        fetcher: A transport exposing async get_json and get_text methods.
        key_provider: A callable returning the owner's configured API key.
    """

    source = "curseforge"
    api = "https://api.curseforge.com/v1"

    def __init__(
        self, fetcher: Any, key_provider: Callable[[], str] = lambda: ""
    ) -> None:
        self.fetcher = fetcher
        self.key_provider = key_provider

    def _headers(self) -> dict[str, str]:
        """Keep API credentials inside transport headers only."""
        key = self.key_provider()
        if not isinstance(key, str) or not key.strip():
            raise SourceError(
                "api_key_missing",
                "CurseForge 官方 API 需要管理员配置自己的 API key。申请说明：https://support.curseforge.com/support/solutions/articles/9000208346-about-the-curseforge-api-and-how-to-apply-for-a-key 。当前仍可查询 MC 百科和 Modrinth。",
            )
        return {
            "x-api-key": key.strip(),
            "Accept": "application/json",
            "User-Agent": "QQBridgeMinecraftKnowledge/1.0",
        }

    @staticmethod
    def _validate(data: dict) -> dict:
        """Reject other games and non-mod Minecraft project classes."""
        if data.get("gameId") != 432 or data.get("classId") != 6:
            raise SourceError(
                "unsupported_project", "该 CurseForge 项目不是 Minecraft 模组。"
            )
        return data

    async def _resolve(self, project: str, headers: dict) -> dict:
        """Resolve a numeric ID or exact mod slug without fuzzy substitution."""
        project = _project(project)
        if project.isdigit():
            response = await self.fetcher.get_json(
                f"{self.api}/mods/{project}", headers=headers
            )
            return self._validate(response.get("data", {}))
        response = await self.fetcher.get_json(
            f"{self.api}/mods/search",
            params={"gameId": 432, "classId": 6, "slug": project, "pageSize": 1},
            headers=headers,
        )
        for data in response.get("data", []):
            if data.get("slug") == project:
                return self._validate(data)
        raise SourceError("not_found", "未找到对应的 CurseForge Minecraft 模组。")

    @staticmethod
    def _metadata(data: dict) -> dict:
        """Normalize project metadata without treating loader names as versions."""
        versions: set[str] = set()
        loaders: set[str] = set()
        for file in data.get("latestFiles", []):
            for version in file.get("gameVersions", []):
                if _GAME_VERSION.fullmatch(str(version)):
                    versions.add(str(version))
                elif str(version).lower() in _CF_LOADERS:
                    loaders.add(str(version).lower())
        for file in data.get("latestFilesIndexes", []):
            if _GAME_VERSION.fullmatch(str(file.get("gameVersion", ""))):
                versions.add(file["gameVersion"])
            if file.get("modLoader") in _CF_LOADER_NAMES:
                loaders.add(_CF_LOADER_NAMES[file["modLoader"]])
        return {
            "project_id": data.get("id"),
            "slug": data.get("slug"),
            "summary": data.get("summary", ""),
            "download_count": data.get("downloadCount"),
            "download_count_scope": "CurseForge 项目累计下载量（仅该平台）",
            "game_versions": sorted(versions),
            "loaders": sorted(loaders),
            "versions_scope": "CurseForge 项目最近文件索引，完整组合请查询版本列表",
            "updated": data.get("dateModified"),
            "published": data.get("dateReleased") or data.get("dateCreated"),
            "created": data.get("dateCreated"),
            "authors": [
                author.get("name", "")
                for author in data.get("authors", [])
                if author.get("name")
            ],
            "categories": [
                category.get("name", "")
                for category in data.get("categories", [])
                if category.get("name")
            ],
            "allow_mod_distribution": data.get("allowModDistribution"),
        }

    @staticmethod
    def _project_url(data: dict) -> str:
        """Use canonical Minecraft mod links rather than arbitrary links in HTML."""
        return f"https://www.curseforge.com/minecraft/mc-mods/{_project(data.get('slug') or data.get('id'))}"

    async def search(
        self,
        query: str,
        game_version: str = "",
        loader: str = "",
        limit: int = 5,
        page: int = 1,
        sort: str = "relevance",
    ) -> dict:
        """Search only Minecraft's mod class with official API filters.

        Args:
            query: A mod name or search phrase.
            game_version: An optional exact Minecraft version.
            loader: An optional loader, requiring game_version for this API.
            limit: The maximum results per page, from 1 to 50.
            page: A one-based page number within the API's 10000-result cap.
            sort: A normalized supported search ordering.

        Returns:
            A source-scoped project page, without exposing API credentials.
        """
        headers = self._headers()
        query = _query(query)
        limit, offset = _paging(limit, page)
        game_version, loader = _filters(game_version, loader)
        if offset + limit > 10000 or sort not in _CF_SORTS:
            raise SourceError("invalid_argument", "CurseForge 页码或排序超出支持范围。")
        if loader and loader not in _CF_LOADERS:
            raise SourceError("invalid_argument", "不支持此 CurseForge 加载器。")
        if loader and not game_version:
            raise SourceError(
                "invalid_argument", "CurseForge 按加载器搜索时还需指定 Minecraft 版本。"
            )
        params: dict[str, Any] = {
            "gameId": 432,
            "classId": 6,
            "searchFilter": query,
            "pageSize": limit,
            "index": offset,
            "sortField": _CF_SORTS[sort],
            "sortOrder": "desc",
        }
        if game_version:
            params["gameVersion"] = game_version
        if loader:
            params["modLoaderType"] = _CF_LOADERS[loader]
        data = await self.fetcher.get_json(
            f"{self.api}/mods/search", params=params, headers=headers
        )
        rows = []
        for item in data.get("data", []):
            if item.get("gameId") != 432 or item.get("classId") != 6:
                continue
            row = self._metadata(item)
            row.update(
                {
                    "title": item.get("name", ""),
                    "description": item.get("summary", ""),
                    "url": self._project_url(item),
                }
            )
            rows.append(row)
        pagination = data.get("pagination", {})
        total = int(pagination.get("totalCount", offset + len(rows)))
        return _page_result(self.source, "results", rows, total, page, limit)

    async def read(self, project: str) -> dict:
        """Read the complete official HTML description as inert plain text.

        Args:
            project: A numeric mod ID or exact mod slug.

        Returns:
            The full description, metadata, and related HTTPS links.
        """
        headers = self._headers()
        data = await self._resolve(project, headers)
        response = await self.fetcher.get_json(
            f"{self.api}/mods/{data['id']}/description", headers=headers
        )
        parser = _DescriptionText()
        parser.feed(str(response.get("data", "")))
        parser.close()
        url = self._project_url(data)
        related = data.get("links") or {}
        return {
            "source": self.source,
            "type": "mod",
            "title": data.get("name", ""),
            "url": url,
            "text": parser.text() or data.get("summary", ""),
            "metadata": self._metadata(data),
            "links": _links(
                {
                    "项目主页": url,
                    "Wiki": related.get("wikiUrl"),
                    "源码": related.get("sourceUrl"),
                    "问题反馈": related.get("issuesUrl"),
                }
            ),
        }

    async def versions(
        self,
        project: str,
        game_version: str = "",
        loader: str = "",
        limit: int = 5,
        page: int = 1,
    ) -> dict:
        """Read paged mod files and verify each file's loader/version pair.

        Args:
            project: A numeric mod ID or exact mod slug.
            game_version: An optional exact Minecraft version.
            loader: An optional recognized Minecraft mod loader.
            limit: The maximum files per page, from 1 to 50.
            page: A one-based page number within the API's 10000-result cap.

        Returns:
            A file page preserving dependencies and official download links.
        """
        headers = self._headers()
        limit, offset = _paging(limit, page)
        game_version, loader = _filters(game_version, loader)
        if offset + limit > 10000 or (loader and loader not in _CF_LOADERS):
            raise SourceError(
                "invalid_argument", "CurseForge 页码或加载器超出支持范围。"
            )
        project_data = await self._resolve(project, headers)
        params: dict[str, Any] = {"index": offset, "pageSize": limit}
        if game_version:
            params["gameVersion"] = game_version
        if loader:
            params["modLoaderType"] = _CF_LOADERS[loader]
        data = await self.fetcher.get_json(
            f"{self.api}/mods/{project_data['id']}/files",
            params=params,
            headers=headers,
        )
        rows = []
        for item in data.get("data", []):
            versions = [
                str(value)
                for value in item.get("gameVersions", [])
                if _GAME_VERSION.fullmatch(str(value))
            ]
            loaders = [
                str(value).lower()
                for value in item.get("gameVersions", [])
                if str(value).lower() in _CF_LOADERS
            ]
            if (
                item.get("modId") != project_data["id"]
                or (game_version and game_version not in versions)
                or (loader and loader not in loaders)
            ):
                continue
            rows.append(
                {
                    "version_id": item.get("id"),
                    "project_id": item.get("modId"),
                    "name": item.get("displayName", ""),
                    "version_number": item.get("displayName", ""),
                    "release_type": {1: "release", 2: "beta", 3: "alpha"}.get(
                        item.get("releaseType"), "unknown"
                    ),
                    "published": item.get("fileDate"),
                    "download_count": item.get("downloadCount"),
                    "download_count_scope": "CurseForge 该文件累计下载量（仅该平台）",
                    "game_versions": versions,
                    "loaders": loaders,
                    "dependencies": item.get("dependencies", []),
                    "available": item.get("isAvailable"),
                    "url": f"{self._project_url(project_data)}/files/{item['id']}",
                    "files": [
                        {
                            "filename": item.get("fileName"),
                            "url": _url(item.get("downloadUrl")),
                            "size": item.get("fileLength"),
                            "hashes": item.get("hashes", []),
                        }
                    ],
                }
            )
        rows.sort(key=lambda row: _date_key(row.get("published")), reverse=True)
        total = int(data.get("pagination", {}).get("totalCount", offset + len(rows)))
        return _page_result(self.source, "versions", rows, total, page, limit)
