"""Verify the real stdio protocol and public sources without sending chat messages."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--server", type=Path, default=Path(__file__).resolve().parents[1] / "server.py"
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    checks = []
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(args.server)],
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
        names = {tool.name for tool in listed.tools}
        assert names == {
            "minecraft_search",
            "minecraft_read",
            "minecraft_related",
            "minecraft_versions",
            "minecraft_sources",
        }
        checks.append(
            {"check": "stdio_list_tools", "passed": True, "count": len(names)}
        )

        async def call(name, arguments):
            response = await session.call_tool(name, arguments)
            assert not response.isError, f"MCP protocol failure: {name}"
            return json.loads(
                next(part.text for part in response.content if part.type == "text")
            )

        status = await call("minecraft_sources", {})
        assert status["ok"] and status["enabled"]
        checks.append(
            {
                "check": "sources",
                "passed": True,
                "cache_ttl_seconds": status["cache_ttl_seconds"],
            }
        )
        search = await call(
            "minecraft_search", {"query": "机械动力", "source": "mcmod", "limit": 3}
        )
        assert search["ok"] and any(
            "/class/2021.html" in row["url"] for row in search["groups"][0]["results"]
        ), search
        checks.append(
            {
                "check": "mcmod_discovery",
                "passed": True,
                "results": len(search["groups"][0]["results"]),
            }
        )
        article = await call(
            "minecraft_read",
            {"url": "https://www.mcmod.cn/class/2021.html", "max_chars": 1200},
        )
        assert (
            article["ok"]
            and article["next_offset"] == 1200
            and article["total_chars"] > 1200
        ), article
        continuation = await call(
            "minecraft_read",
            {
                "url": article["url"],
                "offset": article["next_offset"],
                "max_chars": 1200,
            },
        )
        assert (
            continuation["ok"]
            and continuation["offset"] == 1200
            and continuation["text"] != article["text"]
        )
        checks.append(
            {
                "check": "mcmod_mod_and_continuation",
                "passed": True,
                "title": article["title"],
                "total_chars": article["total_chars"],
            }
        )
        related = await call(
            "minecraft_related", {"mod_url": article["url"], "limit": 3}
        )
        assert related["ok"] and related["total"] >= 3 and related["has_more"], related
        checks.append(
            {
                "check": "mcmod_tutorial_links",
                "passed": True,
                "observed_total": related["total"],
            }
        )
        for route, label in [
            ("item/330128.html", "mcmod_mechanism"),
            ("post/2373.html", "mcmod_tutorial"),
        ]:
            item = await call(
                "minecraft_read", {"url": "https://www.mcmod.cn/" + route}
            )
            assert item["ok"] and item["text"].strip() and item["total_chars"] > 300, (
                item
            )
            checks.append(
                {
                    "check": label,
                    "passed": True,
                    "title": item["title"],
                    "total_chars": item["total_chars"],
                }
            )
        search = await call(
            "minecraft_search",
            {
                "query": "sodium",
                "source": "modrinth",
                "game_version": "1.21.1",
                "loader": "fabric",
                "limit": 1,
            },
        )
        assert search["ok"] and search["groups"][0]["results"], search
        checks.append({"check": "modrinth_search", "passed": True})
        project = await call(
            "minecraft_read", {"url": "https://modrinth.com/mod/sodium"}
        )
        assert (
            project["ok"]
            and project["metadata"]["download_count"] > 0
            and "Sodium" in project["title"]
        ), project
        checks.append(
            {
                "check": "modrinth_project_stats",
                "passed": True,
                "title": project["title"],
                "download_count": project["metadata"]["download_count"],
            }
        )
        versions = await call(
            "minecraft_versions",
            {
                "platform": "modrinth",
                "project": "sodium",
                "game_version": "1.21.1",
                "loader": "fabric",
                "limit": 2,
            },
        )
        assert versions["ok"] and versions["versions"], versions
        assert all(
            "1.21.1" in row["game_versions"] and "fabric" in row["loaders"]
            for row in versions["versions"]
        )
        checks.append(
            {
                "check": "modrinth_joint_version_filter",
                "passed": True,
                "returned": len(versions["versions"]),
            }
        )
        cf = next(row for row in status["sources"] if row["source"] == "curseforge")
        if not cf["api_key_configured"]:
            missing = await call(
                "minecraft_search", {"query": "sodium", "source": "curseforge"}
            )
            assert (
                not missing["ok"]
                and missing["groups"][0]["error"]["code"] == "api_key_missing"
            ), missing
            checks.append(
                {"check": "curseforge_missing_key_is_explicit", "passed": True}
            )
        denied = await call("minecraft_read", {"url": "http://127.0.0.1/private"})
        assert not denied["ok"] and denied["error"]["code"] == "invalid_reference"
        checks.append({"check": "unsupported_url_denied", "passed": True})
    result = {
        "completed": True,
        "check_count": len(checks),
        "checks": checks,
        "qq_messages_sent": 0,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
