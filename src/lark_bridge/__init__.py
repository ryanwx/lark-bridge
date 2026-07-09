"""lark-bridge: Unofficial Feishu/Lark Web SDK."""

from lark_bridge.client import LarkBridge

__all__ = ["LarkBridge"]
__version__ = "0.5.0"


def serve() -> None:
    """Start the MCP server (requires mcp extra: pip install lark-bridge[mcp])."""
    from lark_bridge.mcp_server import main

    main()
