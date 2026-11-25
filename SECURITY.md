# Security Policy

## Session File Protection

`telegram-user-mcp` authenticates directly against Telegram MTProto servers using your own `TELEGRAM_API_ID` and `TELEGRAM_API_HASH`.

- **Never share or commit `.env` or `data/*.session` files.** Both are ignored by `.gitignore` by default.
- Revoke compromised sessions immediately inside **Telegram > Settings > Devices**.

## Scoping Agent Permissions (`TELEGRAM_READ_ONLY`)

When connecting autonomous coding or research agents that only need to read channels, search messages, or inspect folders, set:

```ini
TELEGRAM_READ_ONLY=true
```

Enabling `TELEGRAM_READ_ONLY` enforces a server-level guard that blocks `send_message`, `send_file`, `forward_messages`, `edit_message`, `delete_messages`, and `pin_message` before any network call is made.

## Reporting Vulnerabilities

Please report security issues privately via GitHub Security Advisories on [tarikra1/telegram-user-mcp](https://github.com/tarikra1/telegram-user-mcp/security).
