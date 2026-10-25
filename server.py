"""Standalone stdio MCP entry point for the Minecraft knowledge plugin."""

from typing import Literal

from mcp.server.fastmcp import FastMCP

from mc_knowledge.service import GUIDANCE, KnowledgeService
from mc_knowledge.transport import SourceError

service = KnowledgeService()
mcp = FastMCP("Minecraft Knowledge", instructions=GUIDANCE, log_level="WARNING")


async def result_or_error(awaitable):
    try:
        return await awaitable
    except SourceError as error:
        return {
            "ok": False,
            "error": {"code": error.code, "message": error.message},
            "guidance": GUIDANCE,
        }


@mcp.tool()
async def minecraft_search(
    query: str,
    source: Literal["all", "mcmod", "modrinth", "curseforge"] = "all",
    kind: Literal["mod", "item", "tutorial", "any"] = "mod",
    game_version: str = "",
    loader: str = "",
    limit: int = 5,
    page: int = 1,
    sort: str = "relevance",
) -> dict:
    """搜索Minecraft模组、MC百科物品/机制和教程。中文模组名优先MC百科定位；Modrinth提供官方简介和本平台下载量；CurseForge需自有API Key。搜索摘要仅作定位，回答教程/机制前用minecraft_read读正文。不要合并不同平台下载量。"""
    return await result_or_error(
        service.search(query, source, kind, game_version, loader, limit, page, sort)
    )


@mcp.tool()
async def minecraft_read(url: str, offset: int = 0, max_chars: int = 12000) -> dict:
    """读取MC百科模组(class)、物品/机制(item)、教程(post)正文，或Modrinth/CurseForge模组官方长介绍和下载量。传真实来源URL。长文返回next_offset供同URL续读；保留表格、代码和示意图链接。面向用户概述并引用，尊重作者版权，不整篇转载。"""
    return await result_or_error(service.read(url, offset, max_chars))


@mcp.tool()
async def minecraft_related(
    mod_url: str,
    kind: Literal["tutorial", "item"] = "tutorial",
    query: str = "",
    limit: int = 10,
    page: int = 1,
) -> dict:
    """列出已知MC百科模组主页里实际出现的教程或资料链接；mod_url用class页，可用query筛选标题，再用minecraft_read阅读。结果只是该页面已列链接，不声称枚举整个百科数据库。"""
    return await result_or_error(service.related(mod_url, kind, query, limit, page))


@mcp.tool()
async def minecraft_versions(
    platform: Literal["modrinth", "curseforge"],
    project: str,
    game_version: str = "",
    loader: str = "",
    limit: int = 5,
    page: int = 1,
) -> dict:
    """核实Minecraft模组某版本/加载器的真实发布文件、发布日期、依赖、文件下载量及官方链接。project用平台ID/slug或项目URL。安装兼容性必须检查同一文件的game_versions与loaders，不能靠项目汇总支持列表推断。只返回链接，不下载或执行jar。"""
    return await result_or_error(
        service.versions(platform, project, game_version, loader, limit, page)
    )


@mcp.tool()
async def minecraft_sources() -> dict:
    """查看Minecraft资料工具启用状态、可用来源与CurseForge Key是否已配置；不暴露Key、不修改设置。来源读取失败时先检查，不反复重试被拒绝的来源。"""
    try:
        return service.sources()
    except SourceError as error:
        return {"ok": False, "error": {"code": error.code, "message": error.message}}


if __name__ == "__main__":
    mcp.run(transport="stdio")
