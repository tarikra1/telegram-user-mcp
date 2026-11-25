# telegram-user-mcp

[![CI](https://github.com/tarikra1/telegram-user-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/tarikra1/telegram-user-mcp/actions/workflows/ci.yml)
[![Version](https://img.shields.io/badge/release-v0.3.0-0EA5E9.svg)](CHANGELOG.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776AB.svg)](pyproject.toml)
[![MCP](https://img.shields.io/badge/MCP-stdio-6E56CF.svg)](https://modelcontextprotocol.io)

An asynchronous **Model Context Protocol (MCP)** server and CLI that connects AI coding agents (**Claude Code**, **Claude Desktop**, **Cursor**, **Gemini**, and custom MCP hosts) directly to a **personal Telegram MTProto account** via [Telethon](https://github.com/LonamiWebs/Telethon).

Unlike standard Telegram Bot API wrappers—which can only see chats where a bot was explicitly invited—`telegram-user-mcp` operates through your authenticated user session with **automatic SQLite session-lock recovery**, **idle auto-disconnect**, and a server-enforced **`TELEGRAM_READ_ONLY` safety guard**.

---

## Key Capabilities

- **19 MCP Tools Out of the Box:** Full coverage for authentication (OTP + 2FA cloud password), custom chat folders (`DialogFilter`), unread dialog filtering, global cross-chat search, message sending/editing/forwarding/pinning, and media uploads/downloads.
- **Read-Only Safety Guard (`TELEGRAM_READ_ONLY=true`):** Safely grant agents full read/search access across your Telegram workspace while blocking all mutating tools (`send`, `edit`, `forward`, `delete`, `pin`) at the server layer.
- **Zero-Lock Session Lifecycle:** Automatically disconnects idle Telethon SQLite sessions after 20 seconds of inactivity and retries transient SQLite locks with exponential backoff.
- **Smart Entity Resolution:** Target any chat seamlessly using `"me"` (Saved Messages), `@username`, `t.me/` links, numeric IDs, or fuzzy dialog titles.
- **Clean `stdio` Transport & CLI Parity:** Directs all diagnostic logging strictly to `stderr` and exposes every tool from the terminal via `telegram-mcp-cli`.

---

## Installation

```bash
git clone https://github.com/tarikra1/telegram-user-mcp.git
cd telegram-user-mcp
python -m venv .venv
# Windows: .venv\Scripts\activate | macOS/Linux: source .venv/bin/activate
pip install -e .
```

### Configuration

1. Create an application at [https://my.telegram.org/apps](https://my.telegram.org/apps) to obtain your `api_id` and `api_hash`.
2. Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```ini
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_32_character_telegram_api_hash
TELEGRAM_PHONE=+15550109999
TELEGRAM_READ_ONLY=false
```

---

## Connecting to Claude Code / Claude Desktop / Cursor

Add the server to your MCP configuration (`claude_desktop_config.json` or `.mcp.json`):

```json
{
  "mcpServers": {
    "telegram": {
      "command": "telegram-user-mcp",
      "env": {
        "TELEGRAM_API_ID": "12345678",
        "TELEGRAM_API_HASH": "your_api_hash",
        "TELEGRAM_PHONE": "+15550109999",
        "TELEGRAM_READ_ONLY": "false"
      }
    }
  }
}
```

On first use, ask your agent to call `auth_send_code` followed by `auth_verify_code` (including Two-Step Verification password support if 2FA is enabled on your Telegram account).

---

## Available MCP Tools (19)

| Category | Tool | Description |
| :--- | :--- | :--- |
| **Auth & Profile** | `auth_status` | Check session auth state and `read_only` guard status |
| | `auth_send_code` | Request an OTP login code via Telegram / SMS |
| | `auth_verify_code` | Complete sign-in with OTP code and optional 2FA password |
| | `get_me` | Retrieve profile details of the authenticated account |
| **Discovery & Folders** | `list_folders` | List custom Telegram chat folders (`DialogFilter` tabs) |
| | `get_folder_chats` | List all peers pinned/included inside a specific folder |
| | `list_chats` | List dialogs filtered by `all`, `user`, `bot`, 'group', `channel`, or `unread_only` |
| | `search_chats` | Search local dialogs + global Telegram directory |
| | `get_chat_info` | Fetch bio, participant count, and metadata for any entity |
| **Reading & Search** | `get_messages` | Read recent or filtered messages from a specific chat |
| | `search_messages_global` | Full-text search across all chats, groups, and channels |
| **Messaging & Media** | `send_message` | Send Markdown, HTML, or plain-text messages (blocked in read-only mode) |
| | `send_file` | Upload documents, images, or videos with captions (blocked in read-only mode) |
| | `download_media` | Download attachments from any message ID to disk |
| | `forward_messages` | Forward message batches across chats (blocked in read-only mode) |
| | `edit_message` | Edit previously sent messages (blocked in read-only mode) |
| | `delete_messages` | Delete/revoke messages (blocked in read-only mode) |
| | `mark_as_read` | Acknowledge unread messages in a dialog |
| | `pin_message` | Pin a message silently or with notification (blocked in read-only mode) |

---

## CLI Usage

```bash
# List all registered tools
telegram-mcp-cli list

# List top 10 unread channels
telegram-mcp-cli list_chats --chat-type channel --unread-only --limit 10

# Search across all chats
telegram-mcp-cli search_messages_global --query "deployment" --limit 5
```

---

## Project Links

- [Changelog (`CHANGELOG.md`)](CHANGELOG.md)
- [Engineering Roadmap (`ROADMAP.md`)](ROADMAP.md)
- [Security Policy (`SECURITY.md`)](SECURITY.md)
- [Contributing Guide (`CONTRIBUTING.md`)](CONTRIBUTING.md)

## Running Tests

```bash
python -m unittest discover -s tests -v
```

## License

Released under the [MIT License](LICENSE).
