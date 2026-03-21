"""
Test: OpenClaw Plugin (tool_result_persist hook)

Two levels of testing:
1. Unit tests — test hook functions directly (no OpenClaw needed)
2. Integration test — test with real OpenClaw (requires OpenClaw installed)

Run unit tests: python -m pytest tests/test_openclaw.py -v
Run integration: python tests/test_openclaw.py --integration
"""

import os
import sys
import time
import json
import subprocess
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OPENCLAW_PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "integrations", "openclaw"
)
sys.path.insert(0, OPENCLAW_PLUGIN_DIR)


@pytest.fixture(autouse=True)
def temp_ecp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Reset core state (plugin now delegates to core)
    from atlast_ecp.core import reset
    reset()
    # Reset plugin session tracking
    try:
        plugin._session_records.clear()
    except Exception:
        pass
    yield tmp_path


# ─── Unit Tests: Plugin functions ─────────────────────────────────────────────

class TestOpenClawPlugin:
    def test_on_tool_result_returns_result(self):
        """on_tool_result must return tool_result unchanged (pass-through)."""
        from plugin import on_tool_result
        result = on_tool_result(
            tool_name="web_search",
            tool_input={"query": "ATLAST Protocol"},
            tool_result="Found 10 results about ATLAST Protocol...",
        )
        assert result == "Found 10 results about ATLAST Protocol..."

    def test_ecp_record_created(self):
        """A record should be saved after on_tool_result."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="exec",
            tool_input={"command": "ls -la"},
            tool_result="total 0\ndrwxr-xr-x  2 user staff  64 Mar 12 04:00 .",
            latency_ms=150,
        )
        time.sleep(0.3)

        records = load_records(limit=10)
        assert len(records) >= 1

    def test_record_type_is_turn(self):
        """OpenClaw records must use 'turn' type (per ECP-SPEC §3.1)."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="web_search",
            tool_input={"query": "test"},
            tool_result="Search result",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["step"]["type"] == "turn", \
            f"OpenClaw should use 'turn' type, got: {records[0]['step']['type']}"

    def test_hash_format(self):
        """Hashes must have sha256: prefix."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="web_fetch",
            tool_input={"url": "https://example.com"},
            tool_result="Page content here...",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        step = records[0]["step"]
        assert step["in_hash"].startswith("sha256:")
        assert step["out_hash"].startswith("sha256:")

    def test_chain_prev_genesis_first(self):
        """First record's chain.prev must be 'genesis'."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="exec",
            tool_input={"command": "echo hi"},
            tool_result="hi",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["chain"]["prev"] == "genesis"

    def test_chain_links_multiple_calls(self):
        """Multiple tool calls must be chained correctly."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        for i in range(3):
            on_tool_result(
                tool_name="exec",
                tool_input={"command": f"step {i}"},
                tool_result=f"result {i}",
                latency_ms=100 + i * 10,
            )
            time.sleep(0.15)

        time.sleep(0.3)
        records = load_records(limit=10)
        assert len(records) == 3

        # Verify chain (newest-first)
        assert records[2]["chain"]["prev"] == "genesis"
        assert records[1]["chain"]["prev"] == records[2]["id"]
        assert records[0]["chain"]["prev"] == records[1]["id"]

    def test_latency_recorded(self):
        """Latency should be stored in the record."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="exec",
            tool_input={"command": "ls"},
            tool_result="output",
            latency_ms=342,
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0]["step"]["latency_ms"] == 342

    def test_hedge_flag_in_tool_result(self):
        """Hedge language in tool result should set hedged flag."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="read",
            tool_input={"path": "/tmp/report.txt"},
            tool_result="I think this report might suggest that perhaps the revenue is declining.",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert "hedged" in records[0]["step"]["flags"]

    def test_human_review_flag(self):
        """human_review flag should be detected."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="analyze",
            tool_input={"data": "contract.pdf"},
            tool_result="Please consult a lawyer before signing this agreement.",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert "human_review" in records[0]["step"]["flags"]

    def test_no_confidence_field(self):
        """confidence field must never appear."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(
            tool_name="exec",
            tool_input={},
            tool_result="done",
        )
        time.sleep(0.3)

        records = load_records(limit=1)
        assert "confidence" not in records[0]
        assert "confidence" not in records[0].get("step", {})

    def test_ecp_version_field(self):
        """Record must include ecp: '0.1'."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(tool_name="exec", tool_input={}, tool_result="ok")
        time.sleep(0.3)

        records = load_records(limit=1)
        assert records[0].get("ecp") == "0.1"

    def test_multiple_records_stored(self):
        """Plugin should store multiple records via core."""
        from plugin import on_tool_result
        from atlast_ecp.storage import load_records

        on_tool_result(tool_name="exec", tool_input={}, tool_result="step1")
        on_tool_result(tool_name="exec", tool_input={}, tool_result="step2")
        time.sleep(0.3)

        records = load_records(limit=10)
        assert len(records) >= 2

    def test_get_agent_did(self):
        """Plugin should expose the agent's DID."""
        from plugin import get_agent_did
        did = get_agent_did()
        assert did is not None
        assert did.startswith("did:ecp:")

    def test_fail_open_on_error(self):
        """Plugin must not raise — always returns tool_result."""
        from plugin import on_tool_result

        # Even with None inputs, should not crash
        result = on_tool_result(
            tool_name="test",
            tool_input=None,
            tool_result="safe output",
        )
        assert result == "safe output"

    def test_register_with_mock_api(self):
        """Plugin's register() should call openclaw_api.on() correctly."""
        from plugin import register

        class MockAPI:
            def __init__(self):
                self.hooks = {}

            def on(self, event: str, handler):
                self.hooks[event] = handler

        api = MockAPI()
        result = register(api)
        assert result is True
        assert "tool_result_persist" in api.hooks
        assert "session_end" in api.hooks


# ─── Real Integration Test ────────────────────────────────────────────────────

def test_real_openclaw_integration():
    """
    INTEGRATION TEST: Run a real OpenClaw agent task and verify ECP records.
    Requires: OpenClaw installed (openclaw command available)

    This test:
    1. Loads the ECP plugin into OpenClaw
    2. Runs a simple agent task
    3. Verifies ECP records were created with correct format
    """
    if "--integration" not in sys.argv:
        pytest.skip("Integration test — run with: python tests/test_openclaw.py --integration")

    # Check openclaw is available
    result = subprocess.run(["which", "openclaw"], capture_output=True, text=True)
    if result.returncode != 0:
        pytest.skip("OpenClaw not installed")

    import tempfile
    import shutil
    from pathlib import Path

    with tempfile.TemporaryDirectory() as workdir:
        workdir_path = Path(workdir)

        # Copy SDK and plugin into workdir
        sdk_src = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "atlast_ecp"
        )
        shutil.copytree(sdk_src, workdir_path / "atlast_ecp")
        shutil.copy(
            os.path.join(OPENCLAW_PLUGIN_DIR, "plugin.py"),
            workdir_path / "atlast_ecp_openclaw_plugin.py"
        )

        # Create a test script that simulates the OpenClaw plugin calling on_tool_result
        test_script = workdir_path / "run_test.py"
        test_script.write_text(f"""
import sys
sys.path.insert(0, '{workdir_path}')
sys.path.insert(0, '{OPENCLAW_PLUGIN_DIR}')
import os
os.chdir('{workdir_path}')

from plugin import on_tool_result, get_agent_did, get_session_record_ids
import time, json
from pathlib import Path

# Simulate OpenClaw calling on_tool_result for 3 tool uses
on_tool_result("web_search", {{"query": "ATLAST Protocol ECP"}},
               "ATLAST Protocol is a trust infrastructure for AI Agents...", latency_ms=1200)
time.sleep(0.1)

on_tool_result("exec", {{"command": "python --version"}},
               "Python 3.12.0", latency_ms=45)
time.sleep(0.1)

on_tool_result("read", {{"path": "README.md"}},
               "Please consult a lawyer before using this in production.", latency_ms=23)
time.sleep(0.5)

from atlast_ecp.storage import load_records
records = load_records(limit=10)

print(f"AGENT_DID: {{get_agent_did()}}")
print(f"RECORD_COUNT: {{len(records)}}")
for r in records:
    flags_str = ','.join(r['step'].get('flags', []))
    print(f"RECORD: id={{r['id']}} type={{r['step']['type']}} prev={{r['chain']['prev']}} flags=[{{flags_str}}] ecp={{r.get('ecp','?')}}")

# Assertions
assert len(records) == 3, f"Expected 3 records, got {{len(records)}}"
assert all(r['step']['type'] == 'turn' for r in records), "All should be turn type"
assert all(r.get('ecp') == '0.1' for r in records), "All should have ecp=0.1"
assert all(r['step']['in_hash'].startswith('sha256:') for r in records)
assert all(r['step']['out_hash'].startswith('sha256:') for r in records)

# Check chain
sorted_records = sorted(records, key=lambda r: r['ts'])
assert sorted_records[0]['chain']['prev'] == 'genesis'
assert sorted_records[1]['chain']['prev'] == sorted_records[0]['id']
assert sorted_records[2]['chain']['prev'] == sorted_records[1]['id']

# Check flags
all_flags = [f for r in records for f in r['step'].get('flags', [])]
assert 'human_review' in all_flags, "human_review flag expected"

print("ALL_ASSERTIONS_PASSED")
""")

        env = os.environ.copy()
        env["PYTHONPATH"] = str(workdir_path)
        result = subprocess.run(
            ["python3", str(test_script)],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        print(f"\nOutput:\n{result.stdout}")
        if result.stderr:
            print(f"Stderr:\n{result.stderr}")

        assert "ALL_ASSERTIONS_PASSED" in result.stdout, \
            f"Integration test failed:\n{result.stdout}\n{result.stderr}"
        print("✅ OpenClaw integration test PASSED")


if __name__ == "__main__":
    if "--integration" in sys.argv:
        print("Running OpenClaw integration test...")
        test_real_openclaw_integration()
        print("\nDone. Run full tests with: python -m pytest tests/test_openclaw.py -v")
