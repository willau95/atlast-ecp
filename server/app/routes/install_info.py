"""Install-info endpoint.

Lets every deployed dashboard fetch the *current* install / upgrade commands
at runtime rather than reading a value that was hardcoded at pip-install
time. When we need to change the recommended install command (e.g. to add
`--user` for PEP 668), we update this endpoint once and every user's
dashboard reflects it on its next /api/version refresh — no client upgrade
required.
"""
from fastapi import APIRouter

router = APIRouter()

# Canonical commands. Update here → every deployed dashboard sees the change.
#
# --user works on:
#   - macOS Homebrew Python (PEP 668)
#   - Debian 12+ / Ubuntu 23+ (PEP 668)
#   - Any system Python
# Inside a venv the client SDK drops --user automatically; for everyone
# else this is the safe default.
_INSTALL_CMD = "pip3 install --user atlast-ecp"
_UPGRADE_CMD = "pip3 install --user --upgrade atlast-ecp"
_INSTALL_SCRIPT_BASH = "curl -sSL https://weba0.com/install.sh | bash"
_INSTALL_SCRIPT_PS1 = "irm https://weba0.com/install.ps1 | iex"


@router.get("/v1/install-info")
async def install_info():
    """Return the current recommended install / upgrade commands.

    Dashboards fetch this each time the update banner renders, so a single
    server-side change propagates to every client instantly. Cache-Control
    is short (5 min) because this info changes rarely but users should
    still pick up edits quickly.
    """
    return {
        "schema_version": 1,
        "install_command": _INSTALL_CMD,
        "upgrade_command": _UPGRADE_CMD,
        "install_script_bash": _INSTALL_SCRIPT_BASH,
        "install_script_ps1": _INSTALL_SCRIPT_PS1,
        # Humans / LLMs reading the raw response get the full story:
        "notes": (
            "Prefer --user on Homebrew / PEP 668 systems; drop it inside a venv."
        ),
    }
