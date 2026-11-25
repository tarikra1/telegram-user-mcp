# Changelog

All notable changes to `telegram-user-mcp` are documented in this file.

## [0.3.0] - 2026-11-25

### Added
- **`TELEGRAM_READ_ONLY` Safety Mode:** Added `_is_read_only()` and `_require_write_permission()` blocking mutating MCP tools (`send_message`, `send_file`, `forward_messages`, `edit_message`, `delete_messages`, `pin_message`) when `TELEGRAM_READ_ONLY=true`, while keeping all discovery, reading, and search tools active.
- Compatibility shim supporting both `mcp.server.mcpserver.MCPServer` and `mcp.server.fastmcp.FastMCP` across MCP SDK versions.
- Multi-version GitHub Actions CI matrix (`Python 3.10`, `3.11`, `3.12`), `SECURITY.md`, and `ROADMAP.md`.

## [0.2.0] - 2026-11-25

### Added
- Initial public release with 19 async Telethon MTProto tools over `stdio` JSON-RPC, automatic SQLite session-lock retry, 20-second idle auto-disconnect, `telegram-mcp-cli`, and headless 2FA helper.
