# Contributing to telegram-user-mcp

Contributions, bug reports, and feature requests are welcome!

## Development Setup

1. Fork and clone the repository.
2. Create a virtual environment and install in editable mode:
   ```bash
   python -m venv .venv
   pip install -e .
   ```
3. Run the unit test suite before submitting a pull request:
   ```bash
   python -m unittest discover -s tests -v
   ```

## Guidelines

- **Stdout Hygiene:** Never use `print()` inside `server.py`. All logs must go to `sys.stderr` so MCP stdio JSON-RPC frames remain valid.
- **Session Safety:** Never include real phone numbers, API hashes, or `.session` fixtures in tests or commits.
