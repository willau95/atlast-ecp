#!/usr/bin/env bash
# atlast-scan — quickly inspect a machine for atlast-ecp installations.
#
# Survives the common false-negatives:
#   - `atlast --version` says "command not found" when CLI is in a
#     pip --user bin that isn't on PATH (macOS default)
#   - Multi-Python installs where each `pip install` picks a different
#     interpreter, leaving stale copies behind
#   - Dashboard running but bound to 0.0.0.0 (LAN exposure)
#
# Usage (local):    bash atlast-scan.sh
# Usage (remote):   ssh HOST 'bash -s' < atlast-scan.sh
# Or pipe:          curl -sSL https://.../atlast-scan.sh | bash
#
# Exit codes:
#   0  atlast-ecp installed cleanly (single Python, single dashboard, no issues)
#   1  atlast-ecp not installed anywhere
#   2  atlast-ecp installed but has one or more issues (multi-Python, PATH, LAN-exposed)
#
# Works on bash 3.2+ (macOS default) and doesn't rely on zsh glob quirks.

set -u

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; D=$'\033[2m'; B=$'\033[1m'; Z=$'\033[0m'
else
    G=''; R=''; Y=''; D=''; B=''; Z=''
fi
ok()   { printf "  ${G}✅${Z} %s\n" "$*"; }
miss() { printf "  ${D}⚫ %s${Z}\n" "$*"; }
warn() { printf "  ${Y}⚠  %s${Z}\n" "$*"; }
fail() { printf "  ${R}❌ %s${Z}\n" "$*"; }
info() { printf "     ${D}%s${Z}\n" "$*"; }
sec()  { printf "\n${B}%s${Z}\n" "$*"; }

ISSUES=0
HOST_NAME="$(hostname 2>/dev/null || echo unknown)"
USER_NAME="${USER:-$(whoami 2>/dev/null || echo unknown)}"
OS_NAME="$(uname -s 2>/dev/null || echo unknown)"
printf "${B}atlast-scan${Z}  host=%s user=%s os=%s  date=%s\n" \
    "$HOST_NAME" "$USER_NAME" "$OS_NAME" "$(date '+%Y-%m-%d %H:%M')"

# ── 1. Enumerate candidate Python interpreters ────────────────────────────
# Build an explicit list instead of shell globs (zsh errors on no-match).
CANDIDATES=""
add() { [ -x "$1" ] && CANDIDATES="$CANDIDATES $1"; }

# macOS & Linux system Pythons
add /usr/bin/python3
add /usr/bin/python
add /usr/local/bin/python3
add /usr/local/bin/python

# Apple Xcode Command Line Tools (real path behind /usr/bin/python3)
add /Library/Developer/CommandLineTools/usr/bin/python3

# Homebrew (macOS) — enumerate minor versions explicitly
for minor in 9 10 11 12 13 14; do
    add "/opt/homebrew/bin/python3.$minor"
    add "/usr/local/bin/python3.$minor"
done
add /opt/homebrew/bin/python3
add /opt/homebrew/bin/python

# python.org frameworks (macOS)
for minor in 9 10 11 12 13 14; do
    add "/Library/Frameworks/Python.framework/Versions/3.$minor/bin/python3"
done
add /Library/Frameworks/Python.framework/Versions/Current/bin/python3

# PATH-resolved python3 / python (catches pyenv, venv-in-shell, etc.)
for name in python3 python; do
    p=$(command -v "$name" 2>/dev/null || true)
    [ -n "${p:-}" ] && [ -x "$p" ] && CANDIDATES="$CANDIDATES $p"
done

# Dedupe by realpath (so /usr/bin/python3 and CLT Python don't double-count)
SEEN=""
UNIQUE=""
for py in $CANDIDATES; do
    real=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$py" 2>/dev/null \
           || readlink -f "$py" 2>/dev/null \
           || echo "$py")
    case " $SEEN " in
        *" $real "*) : ;;
        *) SEEN="$SEEN $real"; UNIQUE="$UNIQUE $py" ;;
    esac
done

# ── 2. Query each Python for atlast-ecp ───────────────────────────────────
sec "1. atlast-ecp across Python interpreters"
INSTALLED=0
VERSIONS_SEEN=""
INSTALL_REALPATHS=""
for py in $UNIQUE; do
    pyver=$("$py" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))' 2>/dev/null || echo "?")
    info_line=$("$py" -c 'from importlib.metadata import version; import atlast_ecp; print(version("atlast-ecp"), atlast_ecp.__file__)' 2>/dev/null)
    if [ -n "$info_line" ]; then
        set -- $info_line
        ver="$1"; pkgfile="$2"
        pkgreal=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$pkgfile" 2>/dev/null || echo "$pkgfile")
        # Dedupe by install location (two pythons sharing same site-packages = 1 install)
        case " $INSTALL_REALPATHS " in
            *" $pkgreal "*)
                info "$py (py$pyver) → atlast-ecp $ver (same as above)" ;;
            *)
                ok "$py (py$pyver) → atlast-ecp $ver"
                INSTALL_REALPATHS="$INSTALL_REALPATHS $pkgreal"
                INSTALLED=$((INSTALLED + 1))
                VERSIONS_SEEN="$VERSIONS_SEEN $ver" ;;
        esac
    else
        miss "$py (py$pyver) — no atlast-ecp"
    fi
done

if [ "$INSTALLED" -eq 0 ]; then
    echo
    fail "atlast-ecp NOT installed on this machine"
    info "Install: curl -sSL https://weba0.com/install.sh | bash"
    exit 1
fi

# Multi-install analysis
if [ "$INSTALLED" -gt 1 ]; then
    unique_vers=$(printf '%s\n' $VERSIONS_SEEN | sort -u)
    unique_count=$(printf '%s\n' "$unique_vers" | wc -l | tr -d ' ')
    if [ "$unique_count" -gt 1 ]; then
        fail "Version drift: $INSTALLED installs, $unique_count different versions"
        info "Fix: atlast doctor --fix"
        ISSUES=$((ISSUES + 1))
    else
        warn "Multi-Python: $INSTALLED separate installs (same version — drift-prone)"
        info "Fix: atlast doctor --fix"
        ISSUES=$((ISSUES + 1))
    fi
fi

# ── 3. CLI in interactive PATH? ───────────────────────────────────────────
sec "2. atlast CLI reachable from shell"
cli_in_path=$(/bin/zsh -ilc 'command -v atlast' 2>/dev/null | grep -vE 'compdef|openclaw' | tail -1)
if [ -z "$cli_in_path" ]; then
    cli_in_path=$(/bin/bash -ilc 'command -v atlast' 2>/dev/null | tail -1)
fi
if [ -n "$cli_in_path" ] && [ -x "$cli_in_path" ]; then
    ok "atlast binary: $cli_in_path"
else
    warn "atlast not on interactive PATH"
    ISSUES=$((ISSUES + 1))
    for bin_dir in "$HOME/Library/Python/3.9/bin" "$HOME/Library/Python/3.10/bin" \
                   "$HOME/Library/Python/3.11/bin" "$HOME/Library/Python/3.12/bin" \
                   "$HOME/Library/Python/3.13/bin" "$HOME/Library/Python/3.14/bin" \
                   "$HOME/.local/bin" /opt/homebrew/bin /usr/local/bin; do
        [ -x "$bin_dir/atlast" ] && info "exists at $bin_dir/atlast"
    done
    info "Fix: echo 'export PATH=\"\$HOME/Library/Python/3.9/bin:\$PATH\"' >> ~/.zprofile"
fi

# ── 4. Local storage ──────────────────────────────────────────────────────
sec "3. ~/.ecp storage"
if [ -d "$HOME/.ecp" ]; then
    records=$(ls "$HOME/.ecp/records" 2>/dev/null | wc -l | tr -d ' ')
    id_status="missing"
    [ -f "$HOME/.ecp/identity.json" ] && id_status="present"
    vault_count=$(ls "$HOME/.ecp/vault" 2>/dev/null | wc -l | tr -d ' ')
    ok "~/.ecp exists — records=$records, vault=$vault_count, identity.json=$id_status"
    # DID fingerprint (first 12 chars) so user can distinguish machines
    if [ -f "$HOME/.ecp/identity.json" ]; then
        did=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["did"][:24])' "$HOME/.ecp/identity.json" 2>/dev/null)
        [ -n "$did" ] && info "DID: ${did}..."
    fi
else
    miss "~/.ecp/ not present (never initialized — run 'atlast init')"
fi

# ── 5. Dashboard on :3827 ─────────────────────────────────────────────────
sec "4. Dashboard (:3827)"
dash_row=$(lsof -nP -iTCP:3827 -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print; exit}')
if [ -n "$dash_row" ]; then
    dash_pid=$(echo "$dash_row" | awk '{print $2}')
    dash_bind=$(echo "$dash_row" | awk '{print $9}')
    ok "running PID $dash_pid  bind: $dash_bind"
    case "$dash_bind" in
        127.0.0.1:*|\[::1\]:*|localhost:*)
            info "loopback only — safe" ;;
        *)
            warn "bound beyond loopback — records/DID readable over network"
            info "Fix: kill $dash_pid; relaunch with default (127.0.0.1) host"
            ISSUES=$((ISSUES + 1)) ;;
    esac
    # PID file (v0.32.13+ writes one)
    if [ -f "$HOME/.ecp/dashboard.pid" ]; then
        pidf_ver=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version","?"))' "$HOME/.ecp/dashboard.pid" 2>/dev/null)
        [ -n "$pidf_ver" ] && info "PID-file version: $pidf_ver"
    fi
    # Also count total dashboard processes (singleton check)
    total=$(lsof -nP -iTCP:3827 -sTCP:LISTEN 2>/dev/null | awk 'NR>1' | wc -l | tr -d ' ')
    if [ "$total" -gt 1 ]; then
        warn "$total processes listening on 3827 (pre-v0.32.13 bug, or stale)"
        ISSUES=$((ISSUES + 1))
    fi
else
    miss "no dashboard on :3827"
fi

# ── 6. LaunchAgents (macOS only) ──────────────────────────────────────────
if [ "$OS_NAME" = "Darwin" ]; then
    sec "5. LaunchAgents (auto-start on reboot)"
    la_dir="$HOME/Library/LaunchAgents"
    plist_list=$(ls "$la_dir"/ai.atlast.ecp.*.plist 2>/dev/null)
    if [ -n "$plist_list" ]; then
        for p in $plist_list; do ok "$(basename "$p")"; done
    else
        miss "no atlast LaunchAgents — dashboard won't auto-restart on reboot"
        info "Fix: atlast init (idempotent; preserves identity)"
    fi
fi

# ── 7. Summary ────────────────────────────────────────────────────────────
sec "Summary"
if [ "$ISSUES" -eq 0 ]; then
    printf "  ${G}✅ atlast-ecp installed cleanly — no issues found${Z}\n\n"
    exit 0
else
    printf "  ${Y}⚠  $ISSUES issue(s) — see hints above (${D}atlast doctor --fix${Z}${Y} fixes most)${Z}\n\n"
    exit 2
fi
