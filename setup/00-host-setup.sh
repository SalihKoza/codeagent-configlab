#!/usr/bin/env bash
# CodeAgent ConfigLab - host setup (WSL2 Ubuntu).
# Run as your NORMAL WSL user; it asks for your sudo password for the apt step.
#
#   bash setup/00-host-setup.sh            install packages, create cclab if absent
#   bash setup/00-host-setup.sh --check    diagnose only, install/create nothing
#
# It never edits sudoers, and it never deletes, recreates or re-privileges an
# existing cclab account: if an existing account does not match the expected
# shape it stops and explains instead.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=setup/common.sh
. "$SCRIPT_DIR/common.sh"

CHECK_ONLY=0
case "${1:-}" in
  --check) CHECK_ONLY=1 ;;
  "")      ;;
  *)       echo "usage: $0 [--check]" >&2; exit 2 ;;
esac

require_linux_wsl2
require_host_user

echo "== environment =="
printf '  user=%s uid=%s home=%s\n' "$(id -un)" "$(id -u)" "${HOME:-<unset>}"
printf '  %s\n' "$(wsl2_status_line)"
if [ "$WSL2_CONFIRMED" != "yes" ]; then
  printf '  %s\n' "This is reported, not waved through: the lab environment is documented as WSL2 Ubuntu."
fi

echo
echo "== apt packages =="
echo "  socat      - network relay used by the sandbox"
echo "  bubblewrap - bwrap, required by 20-verify.sh and by the sandbox runtime"
echo "  ripgrep    - rg, required by the sandbox runtime (srt)"
# Host packages are not version-pinned (same as socat / bubblewrap): an apt
# revision string is release-specific and a pin would abort the host step on any
# other archive. Observed on the verified host: ripgrep 15.1.0 (15.1.0-1ubuntu1).
if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "  --check: would run: sudo apt-get update && sudo apt-get install -y socat bubblewrap ripgrep"
else
  sudo apt-get update
  sudo apt-get install -y socat bubblewrap ripgrep
fi
for tool in socat bwrap rg; do
  if command -v "$tool" >/dev/null 2>&1; then
    case "$tool" in
      socat) printf '  [ok] socat: %s\n' "$(socat -V 2>/dev/null | head -n1)" ;;
      bwrap) printf '  [ok] bwrap: %s\n' "$(bwrap --version 2>/dev/null)" ;;
      rg)    printf '  [ok] rg: %s\n' "$(rg --version 2>/dev/null | head -n1)" ;;
    esac
  else
    printf '  [MISS] %s is not on PATH\n' "$tool"
  fi
done

echo
echo "== benchmark user: $CCLAB_USER =="
if id -u "$CCLAB_USER" >/dev/null 2>&1; then
  echo "  account already exists - it will NOT be modified, only inspected (metadata only)."
  home="$(passwd_home "$CCLAB_USER")"
  shell="$(passwd_shell "$CCLAB_USER")"
  problems=()
  if [ -z "$home" ]; then
    problems+=("passwd entry has no home directory field")
  elif [ ! -d "$home" ]; then
    problems+=("home directory '$home' does not exist or is not a directory")
  else
    owner="$(stat -c %U "$home" 2>/dev/null || echo '?')"
    [ "$owner" = "$CCLAB_USER" ] || problems+=("home directory '$home' is owned by '$owner', expected '$CCLAB_USER'")
  fi
  case "$shell" in
    ""|*/nologin|*/false) problems+=("login shell is '${shell:-<empty>}'; the benchmark needs an interactive shell") ;;
  esac
  if [ "${#problems[@]}" -gt 0 ]; then
    echo "  [STOP] the existing '$CCLAB_USER' account does not match the expected shape:"
    printf '         - %s\n' "${problems[@]}"
    cat <<MSG

The '$CCLAB_USER' account was NOT changed: this script does not repair, recreate
or re-privilege an existing account - that is your call, with your own admin
commands.

It is not true that this run changed nothing at all: the apt step above already
ran before this check was reached, so socat, bubblewrap and ripgrep may have
been installed system-wide. Use '--check' to get this diagnosis without
installing.

Decide deliberately, then re-run this script:
  - inspect:  getent passwd $CCLAB_USER
  - or pick a different benchmark user by editing CCLAB_USER in setup/common.sh
MSG
    exit 1
  fi
  printf '  [ok] home=%s shell=%s owner=%s (home contents were not read or listed)\n' "$home" "$shell" "$CCLAB_USER"
else
  if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "  --check: account missing; would run: sudo adduser --disabled-password --gecos \"\" $CCLAB_USER"
  else
    echo "  creating: no password, no sudo rights, no sudoers change"
    sudo adduser --disabled-password --gecos "" "$CCLAB_USER"
  fi
fi

cat <<MSG

Done (host step). What this run may have changed: the apt packages socat,
bubblewrap and ripgrep (system-wide), and the $CCLAB_USER account only if it
did not exist before. No sudoers entry, no Windows setting and no file of your
personal account was touched.

Next, open a LOGIN shell as $CCLAB_USER (the login form matters: it sets HOME):

  sudo -i -u $CCLAB_USER
  bash $SCRIPT_DIR/10-cclab-setup.sh

Reminder: a separate user plus a clean working copy is isolation hygiene, not a
security sandbox on its own.
MSG
