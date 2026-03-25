#!/bin/bash
# ECP SDK — Run All Tests
# Usage: bash tests/run_all.sh [--integration]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_DIR="$(dirname "$SCRIPT_DIR")"

echo "═══════════════════════════════════════════════════════════"
echo "  ATLAST ECP SDK — Test Suite"
echo "═══════════════════════════════════════════════════════════"
echo ""

cd "$SDK_DIR"
export PYTHONPATH="$SDK_DIR:$SDK_DIR/integrations/claude_code:$SDK_DIR/integrations/openclaw"

# ─── Unit Tests ───────────────────────────────────────────────────────────────

echo "▶ Running Core SDK Tests..."
python3 -m pytest tests/test_core.py -v --tb=short 2>&1
echo ""

echo "▶ Running Library Mode Tests (wrap)..."
python3 -m pytest tests/test_library_mode.py -v --tb=short 2>&1
echo ""

echo "▶ Running Claude Code Plugin Tests..."
python3 -m pytest tests/test_claude_code.py -v --tb=short 2>&1
echo ""

echo "▶ Running OpenClaw Plugin Tests..."
python3 -m pytest tests/test_openclaw.py -v --tb=short 2>&1
echo ""

# ─── Integration Tests ────────────────────────────────────────────────────────

if [[ "$1" == "--integration" ]]; then
    echo "═══════════════════════════════════════════════════════════"
    echo "  Integration Tests (requires Claude Code + OpenClaw)"
    echo "═══════════════════════════════════════════════════════════"
    echo ""

    echo "▶ Claude Code Integration Test..."
    python3 tests/test_claude_code.py --integration
    echo ""

    echo "▶ OpenClaw Integration Test..."
    python3 tests/test_openclaw.py --integration
    echo ""
fi

echo "═══════════════════════════════════════════════════════════"
echo "  All unit tests complete."
echo "  For integration tests: bash tests/run_all.sh --integration"
echo "═══════════════════════════════════════════════════════════"
