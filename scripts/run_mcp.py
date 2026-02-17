#!/usr/bin/env python3
"""独立启动 MCP 服务（Streamable HTTP）。MCP 自带 lifespan 会启动浏览器。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.servers.mcp_server import mcp

# 默认 18060 与 xiaohongshu-mcp 一致，便于 Cursor/Claude 配置
if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=18060,
    )
