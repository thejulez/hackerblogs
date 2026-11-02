"""Run the local Claude Code CLI for one structured-output request, isolated from this project's setup.

Without isolation every call loads the project's hooks, plugins, MCP servers and memory, which made calls
about 3.6x slower. Here: no setting sources, no MCP servers, no slash commands, an empty working directory.
"""

import json
import subprocess
import tempfile

EMPTY_DIR = tempfile.mkdtemp(prefix="claude-batch-")
ISOLATED = ["--setting-sources", "", "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--disable-slash-commands"]


def ask(prompt: str, system: str, schema: dict, model: str, timeout: int = 600) -> tuple[dict | None, str]:
    """Return (structured output, stderr tail); None when the call failed or timed out."""
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--tools",
        "",
        "--no-session-persistence",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(schema),
        "--system-prompt",
        system,
        *ISOLATED,
    ]
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=EMPTY_DIR, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    try:
        out = json.loads(p.stdout)
        return out.get("structured_output") or json.loads(out["result"]), ""
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, (p.stderr or p.stdout)[-300:]
