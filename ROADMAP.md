# Engineering Roadmap

Planned milestones for `telegram-user-mcp`:

- [x] **v0.2.0 — Zero-Lock Session Pooling & Dual CLI/MCP Interface:** Automatic 20s idle SQLite disconnect, transient lock retry, and `telegram-mcp-cli` parity across all 19 tools.
- [x] **v0.3.0 — Read-Only Agent Guard (`TELEGRAM_READ_ONLY`) & CI Matrix:** Server-enforced write blocking for research-only MCP sessions and multi-Python automated test suites.
- [ ] **v0.4.0 — Token-Efficient Pagination & Compact Payloads:** Add `compact=true` output mode and `next_offset_id` cursors on `get_messages` and `search_messages_global` so large channel histories stay context-efficient inside Claude Code and Claude Desktop.
- [ ] **v0.5.0 — `FloodWaitError` Backoff & Supergroup Forum Topics:** Bounded exponential retry for Telegram rate limits plus `topic_id` (`reply_to_top_id`) thread filtering for forum supergroups.
- [ ] **v0.6.0 — Per-Folder / Per-Chat Allowlists:** Granular write-scoping rules (e.g., permitting writes only to `"me"` Saved Messages while keeping external groups strictly read-only).
