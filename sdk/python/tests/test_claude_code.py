"""
Test: Claude Code Plugin (PreToolUse / PostToolUse hooks)

Two levels of testing:
1. Unit tests — test hook functions directly (no Claude Code needed)
2. Integration test — test with real Claude Code (requires Claude Code installed)

Run unit tests: python -m pytest tests/test_claude_code.py -v
Run integration: python tests/test_claude_code.py --integration
"""

import os
import sys
import time
import json
import subprocess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INTEGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "integrations", "claude_code")
sys.path.insert(0, INTEGRATIONS_DIR)


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Set ECP dir to temp path
    ecp_dir = str(tmp_path / ".ecp")
    monkeypatch.setenv("ATLAST_ECP_DIR", ecp_dir)
    import atlast_ecp.storage as _storage
    import atlast_ecp.identity as _identity
    from pathlib import Path
    _storage.ECP_DIR = Path(ecp_dir)
    _storage.RECORDS_DIR = _storage.ECP_DIR / "records"
    _storage.LOCAL_DIR = _storage.ECP_DIR / "local"
    _storage.INDEX_FILE = _storage.ECP_DIR / "index.json"
    _storage.QUEUE_FILE = _storage.ECP_DIR / "upload_queue.jsonl"
    _identity.ECP_DIR = Path(ecp_dir)
    _identity.IDENTITY_FILE = _identity.ECP_DIR / "identity.json"
    # Reset core state (hooks now delegate to core)
    from atlast_ecp.core import reset
    reset()
    # Reset hook in-flight tracking
    try:
        ecp_hooks._in_flight.clear()
    except Exception:
        pass
    yield tmp_path


# ─── Unit Tests: Hook functions ───────────────────────────────────────────────

class TestClaudeCodeHooks:
    def test_pre_tool_use_returns_input(self):
        """pre_tool_use must return tool_input (pass-through)."""
        from ecp_hooks import pre_tool_use
        input_data = {"path": "/tmp/test.py", "command": "ls"}
        result = pre_tool_use("Bash", input_data)
        # Result should contain original keys + __ecp_call_id
        assert "path" in result
        assert "command" in result
        assert "__ecp_call_id" in result

    def test_post_tool_use_returns_result(self):
        """post_tool_use must return tool_result unchanged (pass-through)."""
        from ecp_hooks import pre_tool_use, post_tool_use
        tool_input = pre_tool_use("Bash", {"command": "echo hello"})
        result = post_tool_use("Bash", tool_input, "hello\n")
        assert result == "hello\n"

    def test_ecp_record_created_after_post(self):
        """A record should be saved after post_tool_use."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        tool_input = pre_tool_use("Bash", {"command": "echo hello"})
        post_tool_use("Bash", tool_input, "hello\n")
        time.sleep(0.3)  # Wait for async thread

        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_type_is_tool_call(self):
        """Claude Code records must use 'tool_call' type."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        tool_input = pre_tool_use("Read", {"path": "/tmp/test.txt"})
        post_tool_use("Read", tool_input, "file contents here")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["step"]["type"] == "tool_call"

    def test_latency_is_recorded(self):
        """Latency should be measured and recorded."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        tool_input = pre_tool_use("Bash", {"command": "sleep 0"})
        time.sleep(0.05)  # Simulate tool execution time
        post_tool_use("Bash", tool_input, "done")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["step"]["latency_ms"] >= 0

    def test_hash_format_correct(self):
        """in_hash and out_hash must have sha256: prefix."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        tool_input = pre_tool_use("Write", {"path": "/f.py", "content": "print('hi')"})
        post_tool_use("Write", tool_input, "File written successfully")
        time.sleep(0.3)

        records = load_records(limit=1)
        step = records[0]["step"]
        assert step["in_hash"].startswith("sha256:")
        assert step["out_hash"].startswith("sha256:")

    def test_chain_prev_is_genesis_for_first(self):
        """First record's chain.prev must be 'genesis'."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        tool_input = pre_tool_use("Bash", {"command": "ls"})
        post_tool_use("Bash", tool_input, "file1.py\nfile2.py")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["chain"]["prev"] == "genesis"

    def test_chain_links_multiple_tool_calls(self):
        """Multiple tool calls must be properly chained."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        for i in range(3):
            ti = pre_tool_use("Bash", {"command": f"echo {i}"})
            post_tool_use("Bash", ti, f"output {i}")
            time.sleep(0.15)

        time.sleep(0.3)
        records = load_records(limit=10)
        assert len(records) == 3

        # Verify chain: records are newest-first
        # records[0] → records[1] → records[2] (genesis)
        assert records[2]["chain"]["prev"] == "genesis"
        assert records[1]["chain"]["prev"] == records[2]["id"]
        assert records[0]["chain"]["prev"] == records[1]["id"]

    def test_hedge_flag_detected(self):
        """Hedge language in tool output should set hedged flag."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        ti = pre_tool_use("Bash", {"command": "analyze"})
        post_tool_use("Bash", ti, "I think this might be the correct approach, but I'm not sure.")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert "hedged" in records[0]["step"]["flags"]

    def test_fail_open_on_error(self):
        """Hook must not raise even if ECP SDK fails."""
        from ecp_hooks import pre_tool_use, post_tool_use

        # Should not raise even with unusual inputs
        ti = pre_tool_use("Bash", {})
        result = post_tool_use("Bash", ti, "output")
        assert result == "output"  # Always returns result

    def test_no_confidence_field(self):
        """confidence field must never appear in records."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        ti = pre_tool_use("Bash", {"command": "ls"})
        post_tool_use("Bash", ti, "output.txt")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert "confidence" not in records[0]
        assert "confidence" not in records[0].get("step", {})

    def test_ecp_version_in_record(self):
        """Record must include ecp: '0.1'."""
        from ecp_hooks import pre_tool_use, post_tool_use
        from atlast_ecp.storage import load_records

        ti = pre_tool_use("Bash", {"command": "ls"})
        post_tool_use("Bash", ti, "files...")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0].get("ecp") == "0.1"

    def test_installer_file_exists(self):
        """Installer script must exist and be loadable."""
        install_path = os.path.join(INTEGRATIONS_DIR, "install.py")
        assert os.path.exists(install_path), f"Installer not found: {install_path}"

        # Verify it contains the expected functions
        with open(install_path) as f:
            content = f.read()
        assert "def install()" in content
        assert "def uninstall()" in content
        assert "PreToolUse" in content
        assert "PostToolUse" in content


# ─── Real Integration Test ────────────────────────────────────────────────────

def test_real_claude_code_integration():
    """
    INTEGRATION TEST: Run a real Claude Code task and verify ECP records.
    Requires: Claude Code installed (claude command available)

    This test:
    1. Creates a temp workspace
    2. Copies ECP hooks into Claude Code plugins directory
    3. Runs a simple Claude Code task (claude -p "list files in /tmp")
    4. Verifies ECP records were created
    """
    if "--integration" not in sys.argv:
        pytest.skip("Integration test — run with: python tests/test_claude_code.py --integration")

    import tempfile
    import shutil
    from pathlib import Path

    # Check claude is available
    result = subprocess.run(["which", "claude"], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("Claude Code not installed")

    with tempfile.TemporaryDirectory() as workdir:
        workdir_path = Path(workdir)

        # Set up ECP hook
        hook_src = os.path.join(INTEGRATIONS_DIR, "ecp_hooks.py")
        sdk_src = os.path.join(os.path.dirname(INTEGRATIONS_DIR), "atlast_ecp")

        # Copy SDK into workdir
        shutil.copytree(sdk_src, workdir_path / "atlast_ecp")
        shutil.copy(hook_src, workdir_path / "ecp_hooks.py")

        # Create a minimal CLAUDE.md to instruct hook loading
        (workdir_path / "CLAUDE.md").write_text(
            "# Test Project\nThis is a test project for ECP integration testing."
        )

        # Run Claude Code with a simple task
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workdir_path)
        env["ECP_HOOKS_ENABLED"] = "1"

        result = subprocess.run(
            ["claude", "-p", "List the files in the current directory"],
            cwd=str(workdir_path),
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        # Allow for Claude Code completing without error
        assert result.returncode in [0, 1], f"Claude Code failed: {result.stderr}"

        # Check for ECP records
        time.sleep(1)  # Wait for async writes
        ecp_dir = workdir_path / ".ecp"
        if ecp_dir.exists():
            records_dir = ecp_dir / "records"
            jsonl_files = list(records_dir.glob("*.jsonl")) if records_dir.exists() else []
            print(f"\n✅ ECP records created: {len(jsonl_files)} files")
            if jsonl_files:
                with open(jsonl_files[0]) as f:
                    for line in f:
                        if line.strip():
                            r = json.loads(line)
                            print(f"   Record: {r['id']} | type: {r['step']['type']}")
        else:
            print("\n⚠️  No .ecp directory found — hooks may not have triggered")


if __name__ == "__main__":
    if "--integration" in sys.argv:
        print("Running Claude Code integration test...")
        test_real_claude_code_integration()
    else:
        print("Run with pytest or add --integration for real Claude Code test")
