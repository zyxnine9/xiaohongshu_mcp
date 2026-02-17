#!/usr/bin/env python3
"""启动 HTTP API 服务（可选：同时挂载 MCP 于 /mcp）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn


def main():
    # 使用 src.servers.http_app:app，以便正确解析项目根
    uvicorn.run(
        "src.servers.http_app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    main()
