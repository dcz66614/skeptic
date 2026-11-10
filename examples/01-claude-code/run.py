"""Claude Code configuration wrapping and transparent proxy demonstration (D61, S15, ADR-0005).

Demonstrates:
1. Reading Claude Code's project-level MCP configuration (.mcp.json).
2. Using `skeptic wrap` to transparently rewrite MCP servers into `skeptic proxy stdio`.
3. Validating the before-and-after configuration diff.
4. Sending an MCP initialize handshake through the wrapped proxy to verify live relay.
5. Restoring the original configuration byte-for-byte using `skeptic wrap --undo`.
"""

from __future__ import annotations

import argparse
import difflib
import json
import subprocess
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
REPO_ROOT = DIR.parents[1]
MCP_JSON = DIR / ".mcp.json"
MCP_BEFORE = DIR / ".mcp.json.before"
MCP_AFTER = DIR / ".mcp.json.after"


def _run_cli(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a skeptic CLI command via the current Python interpreter."""
    return subprocess.run(
        [sys.executable, "-m", "skeptic_agent.cli", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def show_diff(before_text: str, after_text: str) -> str:
    """Generate a unified diff between two configuration states."""
    diff = difflib.unified_diff(
        before_text.splitlines(keepends=True),
        after_text.splitlines(keepends=True),
        fromfile=".mcp.json (before wrap)",
        tofile=".mcp.json (after wrap)",
    )
    return "".join(diff)


def test_proxy_handshake() -> None:
    """Send an MCP initialize request through the wrapped stdio proxy."""
    cmd = [
        sys.executable,
        "-m",
        "skeptic_agent.cli",
        "proxy",
        "stdio",
        "--profile",
        "none",
        "--",
        sys.executable,
        "-m",
        "skeptic_agent.sandboxes.sb_weather",
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=REPO_ROOT,
    )
    init_request = (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "claude-code-demo", "version": "1.0"},
                },
            }
        )
        + "\n"
    )
    stdout, stderr = proc.communicate(input=init_request, timeout=10)
    assert proc.returncode == 0, f"Proxy failed with stderr: {stderr}"
    response = json.loads(stdout.strip())
    assert response.get("jsonrpc") == "2.0"
    assert "result" in response
    server_info = response["result"].get("serverInfo", {})
    print(f"   [Proxy OK] Connected to sandbox: {server_info.get('name', 'unknown')}")


def run_demo() -> int:
    """Run the complete wrap, diff, test-proxy, and undo cycle."""
    print("=" * 70)
    print("Skeptic Claude Code Example: Configuration Wrap & Transparent Proxy")
    print("=" * 70)

    # 1. Reset .mcp.json to clean before state
    orig_bytes = MCP_BEFORE.read_bytes()
    MCP_JSON.write_bytes(orig_bytes)
    backup_file = Path(f"{MCP_JSON}.skeptic.bak")
    if backup_file.exists():
        backup_file.unlink()

    print("\n[Step 1/5] Initial configuration (.mcp.json before wrap):")
    print(MCP_JSON.read_text(encoding="utf-8"))

    # 2. Wrap configuration
    print(
        "[Step 2/5] Running: skeptic wrap .mcp.json --all "
        "--profile silent-core --guards recommended"
    )
    wrap_res = _run_cli(
        [
            "wrap",
            str(MCP_JSON),
            "--all",
            "--profile",
            "silent-core",
            "--guards",
            "recommended",
        ]
    )
    if wrap_res.returncode != 0:
        print(f"Error wrapping config: {wrap_res.stderr}", file=sys.stderr)
        return wrap_res.returncode
    print(f"   {wrap_res.stdout.strip()}")

    # 3. Inspect wrapped configuration and diff
    wrapped_text = MCP_JSON.read_text(encoding="utf-8")
    print("\n[Step 3/5] Configuration after wrap (diff):")
    diff_text = show_diff(MCP_BEFORE.read_text(encoding="utf-8"), wrapped_text)
    print(diff_text or "   (No differences)")

    # Verify against reference after file
    after_data = json.loads(MCP_AFTER.read_text(encoding="utf-8"))
    wrapped_data = json.loads(wrapped_text)
    assert wrapped_data == after_data, (
        "Wrapped configuration does not match reference .mcp.json.after"
    )
    print("   [Verified] Wrapped configuration matches reference specification.")

    # 4. Test proxy relay
    print("\n[Step 4/5] Testing transparent MCP stdio proxy relay...")
    test_proxy_handshake()

    # 5. Undo wrap
    print("\n[Step 5/5] Running: skeptic wrap .mcp.json --undo")
    undo_res = _run_cli(["wrap", str(MCP_JSON), "--undo"])
    if undo_res.returncode != 0:
        print(f"Error undoing wrap: {undo_res.stderr}", file=sys.stderr)
        return undo_res.returncode
    print(f"   {undo_res.stdout.strip()}")

    # Verify byte-for-byte exact restoration
    restored_bytes = MCP_JSON.read_bytes()
    assert restored_bytes == orig_bytes, "Restored .mcp.json does not match original bytes!"
    assert not backup_file.exists(), "Backup file was not cleaned up after undo"
    print("   [Verified] Byte-for-byte restoration verified successfully.")

    print("\n" + "=" * 70)
    print("Claude Code wrap demo completed successfully!")
    print("=" * 70)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Skeptic Claude Code wrap demo")
    parser.add_argument("--wrap", action="store_true", help="Wrap .mcp.json")
    parser.add_argument("--undo", action="store_true", help="Undo wrap on .mcp.json")
    parser.add_argument("--diff", action="store_true", help="Show before/after diff")
    parser.add_argument("--test-proxy", action="store_true", help="Test stdio proxy handshake")
    args = parser.parse_args()

    if args.wrap:
        res = _run_cli(
            [
                "wrap",
                str(MCP_JSON),
                "--all",
                "--profile",
                "silent-core",
                "--guards",
                "recommended",
            ]
        )
        print(res.stdout.strip() if res.returncode == 0 else res.stderr.strip())
        return res.returncode
    if args.undo:
        res = _run_cli(["wrap", str(MCP_JSON), "--undo"])
        print(res.stdout.strip() if res.returncode == 0 else res.stderr.strip())
        return res.returncode
    if args.diff:
        print(
            show_diff(
                MCP_BEFORE.read_text(encoding="utf-8"),
                MCP_AFTER.read_text(encoding="utf-8"),
            )
        )
        return 0
    if args.test_proxy:
        test_proxy_handshake()
        return 0

    return run_demo()


if __name__ == "__main__":
    sys.exit(main())
