import asyncio
import json
import sys
from typing import Any, Dict, List
from mcp.server.models import InitializationOptions
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool

from app.tools_math import sanjay_profit, math_eval


server = Server("jay-math")


@server.list_tools()
async def list_tools() -> List[Tool]:
    """
    Expose our math tools to MCP clients (e.g. nanobot).
    """
    return [
        Tool(
            name="math_eval",
            description="Evaluate a basic mathematical expression (Python-style).",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {"type": "string"},
                },
                "required": ["expression"],
            },
        ),
        Tool(
            name="sanjay_profit",
            description="it process the sanjay_profit  for given values n and m",
            inputSchema={
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "m": {"type": "integer"},
                },
                "required": ["n", "m"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    print("TOOL CALLED:", name, arguments, file=sys.stderr)
    """
    Handle tool invocation from the MCP client.
    """
    if name == "math_eval":
        expr = str(arguments.get("expression", ""))
        result = math_eval(expr)
        text = f"{result}"
    elif name == "sanjay_profit":
        n = int(arguments.get("n", 0))
        m = int(arguments.get("m", 0))
        result = sanjay_profit(n, m)
        text = f"{result}"
    else:
        text = f"Unknown tool: {name}"

    return CallToolResult(
        content=[TextContent(type="text", text=text)],
    )


async def main() -> None:
    async with stdio_server() as (read, write):

        init_options = InitializationOptions(
            server_name="math-server",
            server_version="0.1.0",
            capabilities={}
        )

        await server.run(read, write, init_options)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


