"""
ECP Claude Code Installer
Run: python install.py
Or:  npx atlast-ecp install (uses this script internally)

Writes the ECP plugin into Claude Code's plugin directory.
"""

import json
import shutil
import sys
from pathlib import Path

CLAUDE_CONFIG = Path.home() / ".claude" / "settings.json"
CLAUDE_PLUGINS_DIR = Path.home() / ".claude" / "plugins"
ECP_PLUGIN_FILE = CLAUDE_PLUGINS_DIR / "atlast_ecp.py"
ECP_HOOKS_SRC = Path(__file__).parent / "ecp_hooks.py"


def install():
    print("🔗 ATLAST ECP — Claude Code Plugin Installer")
    print()

    # Create plugins directory
    CLAUDE_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    # Copy hook file
    shutil.copy(ECP_HOOKS_SRC, ECP_PLUGIN_FILE)
    print(f"  ✅ Plugin installed: {ECP_PLUGIN_FILE}")

    # Update Claude Code settings.json
    _update_claude_settings()

    print()
    print("  ✅ ECP is now active for all Claude Code sessions.")
    print(f"  📁 Evidence chain stored in: .ecp/ (local, private)")
    print(f"  🔍 View records: atlast view")
    print()
    print("  Your Agent's DID will be generated on first run.")
    print("  Register your Agent with an ECP server")


def _update_claude_settings():
    """Register ECP hooks in Claude Code settings."""
    settings = {}
    if CLAUDE_CONFIG.exists():
        try:
            settings = json.loads(CLAUDE_CONFIG.read_text())
        except (json.JSONDecodeError, IOError):
            settings = {}

    # Register pre/post tool use hooks
    hooks = settings.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])
    post_hooks = hooks.setdefault("PostToolUse", [])

    ecp_pre = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": f"python {ECP_PLUGIN_FILE} pre_tool_use"
        }]
    }
    ecp_post = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": f"python {ECP_PLUGIN_FILE} post_tool_use"
        }]
    }

    # Avoid duplicates
    if not any("atlast_ecp" in str(h) for h in pre_hooks):
        pre_hooks.append(ecp_pre)
    if not any("atlast_ecp" in str(h) for h in post_hooks):
        post_hooks.append(ecp_post)

    CLAUDE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    CLAUDE_CONFIG.write_text(json.dumps(settings, indent=2))
    print(f"  ✅ Claude Code settings updated: {CLAUDE_CONFIG}")


def uninstall():
    """Remove ECP plugin from Claude Code."""
    if ECP_PLUGIN_FILE.exists():
        ECP_PLUGIN_FILE.unlink()
        print(f"  ✅ Plugin removed: {ECP_PLUGIN_FILE}")

    if CLAUDE_CONFIG.exists():
        try:
            settings = json.loads(CLAUDE_CONFIG.read_text())
            hooks = settings.get("hooks", {})
            for hook_list in hooks.values():
                to_remove = [h for h in hook_list if "atlast_ecp" in str(h)]
                for h in to_remove:
                    hook_list.remove(h)
            CLAUDE_CONFIG.write_text(json.dumps(settings, indent=2))
            print(f"  ✅ Hooks removed from settings")
        except Exception:
            pass


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()
