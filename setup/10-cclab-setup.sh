#!/usr/bin/env bash
# CodeAgent ConfigLab - benchmark user setup. Run AS cclab, in a LOGIN shell
# (sudo -i -u cclab). No sudo needed and none is used.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=setup/common.sh
. "$SCRIPT_DIR/common.sh"

# --- identity first: before installing, downloading or writing anything -------
require_linux_wsl2
require_user "$CCLAB_USER"
require_matching_home "$CCLAB_USER"

# The native build auto-updates in the background, which would silently break the
# version pin. Export it in THIS process, before any claude invocation - a line
# in .bashrc would not affect the commands this script runs.
export DISABLE_AUTOUPDATER=1

echo "== environment =="
printf '  user=%s uid=%s home=%s\n' "$(id -un)" "$(id -u)" "$HOME"
printf '  %s\n' "$(wsl2_status_line)"

REPORT="$HOME/$CCLAB_VERSION_REPORT_NAME"
# Checked BEFORE anything is downloaded, installed or written: an existing report
# is the provenance record of an earlier environment, and a re-run must not
# destroy it. The new record is written at the very end, once the checks and the
# shell settings below have completed.
refuse_if_exists "$REPORT" "a setup version report" \
  "Move it aside yourself if you mean to re-run the setup, for example:" \
  "  mv $REPORT $REPORT.\$(date -u +%Y%m%dT%H%M%SZ)" \
  "This script neither deletes nor archives it for you."

DL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cclab-setup.XXXXXX")"
trap 'rm -rf "$DL_DIR"' EXIT

export NVM_DIR="$HOME/.nvm"
NVM_INSTALLER_SHA256="not downloaded (existing install reused)"
CC_INSTALLER_SHA256="not downloaded"

install_nvm() {
  local inst="$DL_DIR/nvm-install.sh"
  curl -fsSL -o "$inst" "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh"
  NVM_INSTALLER_SHA256="$(sha256sum "$inst" | cut -d' ' -f1)"
  bash "$inst"
}

echo
echo "== nvm ($NVM_VERSION) =="
if [ -s "$NVM_DIR/nvm.sh" ]; then
  echo "  $NVM_DIR/nvm.sh exists - verifying the actual version (a present file is not proof)"
else
  install_nvm
fi
# nvm.sh is third-party and not guaranteed to be clean under 'set -eu'; relax
# only for the source, then restore. The check right after catches a bad load.
set +eu
# shellcheck disable=SC1091
. "$NVM_DIR/nvm.sh"
set -eu
command -v nvm >/dev/null 2>&1 || die "$NVM_DIR/nvm.sh was sourced but 'nvm' is not available."
NVM_OBSERVED="$(nvm --version 2>/dev/null || true)"
if [ "$NVM_OBSERVED" != "${NVM_VERSION#v}" ]; then
  if [ "${CCLAB_ALLOW_NVM_REINSTALL:-0}" = "1" ]; then
    echo "  version mismatch (have ${NVM_OBSERVED:-<none>}, want ${NVM_VERSION#v}) - reinstalling on request"
    install_nvm
    set +eu
    # shellcheck disable=SC1091
    . "$NVM_DIR/nvm.sh"
    set -eu
    NVM_OBSERVED="$(nvm --version 2>/dev/null || true)"
    [ "$NVM_OBSERVED" = "${NVM_VERSION#v}" ] \
      || die "nvm is still ${NVM_OBSERVED:-<none>} after reinstall; expected ${NVM_VERSION#v}."
  else
    die "the existing nvm is ${NVM_OBSERVED:-<none>}, but this lab pins ${NVM_VERSION#v}." \
        "Stopping here rather than silently overwriting it. Choose one:" \
        "  - re-run with CCLAB_ALLOW_NVM_REINSTALL=1 to overwrite the nvm in $NVM_DIR, or" \
        "  - accept the drift deliberately by editing NVM_VERSION in setup/common.sh."
  fi
fi
echo "  [ok] nvm $NVM_OBSERVED"

echo
echo "== node =="
if [ -n "$NODE_VERSION_PIN" ]; then
  nvm install "$NODE_VERSION_PIN"
  nvm alias default "$NODE_VERSION_PIN"
else
  nvm install "$NODE_MAJOR"
  nvm alias default "$NODE_MAJOR"
fi
nvm use default >/dev/null
if [ -n "$NPM_VERSION_PIN" ]; then
  npm install -g "npm@$NPM_VERSION_PIN"
fi
NODE_OBSERVED="$(node -v 2>/dev/null || true)"
NPM_OBSERVED="$(npm -v 2>/dev/null || true)"
if [ -n "$NODE_VERSION_PIN" ] && [ "$(semver_of "$NODE_OBSERVED")" != "$(semver_of "$NODE_VERSION_PIN")" ]; then
  die "node version mismatch: expected $NODE_VERSION_PIN, observed ${NODE_OBSERVED:-<none>}."
fi
if [ -n "$NPM_VERSION_PIN" ] && [ "$(semver_of "$NPM_OBSERVED")" != "$(semver_of "$NPM_VERSION_PIN")" ]; then
  die "npm version mismatch: expected $NPM_VERSION_PIN, observed ${NPM_OBSERVED:-<none>}."
fi
printf '  [ok] node %s / npm %s\n' "${NODE_OBSERVED:-<none>}" "${NPM_OBSERVED:-<none>}"

echo
echo "== sandbox seccomp filter package =="
if [ -n "$SANDBOX_RUNTIME_VERSION_PIN" ]; then
  npm install -g "@anthropic-ai/sandbox-runtime@$SANDBOX_RUNTIME_VERSION_PIN"
else
  npm install -g @anthropic-ai/sandbox-runtime
fi
SBX_OBSERVED="$(npm ls -g --depth=0 2>/dev/null \
  | sed -n 's|.*@anthropic-ai/sandbox-runtime@\([0-9][^ ]*\).*|\1|p' | head -n1)"
[ -n "$SBX_OBSERVED" ] || die "@anthropic-ai/sandbox-runtime is not listed by 'npm ls -g --depth=0' after install."
if [ -n "$SANDBOX_RUNTIME_VERSION_PIN" ] && [ "$SBX_OBSERVED" != "$SANDBOX_RUNTIME_VERSION_PIN" ]; then
  die "@anthropic-ai/sandbox-runtime version mismatch: expected $SANDBOX_RUNTIME_VERSION_PIN, observed $SBX_OBSERVED."
fi
echo "  [ok] @anthropic-ai/sandbox-runtime $SBX_OBSERVED"
echo "  [note] installed only. That the package exists is NOT evidence that a filter is"
echo "         loaded, nor that it actually blocks anything at run time."

echo
echo "== Claude Code (native build, pinned to $CC_VERSION) =="
CC_INSTALLER="$DL_DIR/claude-install.sh"
curl -fsSL -o "$CC_INSTALLER" https://claude.ai/install.sh
CC_INSTALLER_SHA256="$(sha256sum "$CC_INSTALLER" | cut -d' ' -f1)"
bash "$CC_INSTALLER" "$CC_VERSION"
export PATH="$HOME/.local/bin:$PATH"

echo
echo "== executable and version verification =="
# command -v alone is not enough: it can point at a symlink, and on WSL it can
# point at a Windows build under /mnt/c. Resolve the real file, reject mounts.
verify_linux_exe() {   # name -> prints the resolved path; dies on a Windows build
  local name="$1" w r
  w="$(command -v "$name" 2>/dev/null || true)"
  [ -n "$w" ] || die "$name is not on PATH."
  r="$(resolve_exe "$name")"
  [ -z "$RESOLVE_NOTE" ] || echo "  [note] $RESOLVE_NOTE" >&2
  if is_windows_exe "$r"; then
    die "$name resolves to a Windows / mounted-drive executable:" \
        "  command -v : $w" \
        "  real path  : $r  (fstype: $(path_fstype "$r"))" \
        "A Windows build is not the Linux installation this benchmark measures."
  fi
  printf '%s\n' "$r"
}
CLAUDE_WHICH="$(command -v claude 2>/dev/null || true)"
CLAUDE_REAL="$(verify_linux_exe claude)"
NODE_REAL="$(verify_linux_exe node)"
NPM_REAL="$(verify_linux_exe npm)"
case "$CLAUDE_REAL" in
  "$HOME"/*) ;;
  *) echo "  [warn] claude resolves outside \$HOME ($CLAUDE_REAL); that is not the per-user"
     echo "         native install path - confirm this is the build you intend to measure." ;;
esac

CC_OBSERVED="$(semver_of "$(claude --version 2>/dev/null || true)")"
if [ "$CC_OBSERVED" != "$CC_VERSION" ]; then
  die "claude version mismatch: expected $CC_VERSION, observed ${CC_OBSERVED:-<none>}." \
      "  command -v : $CLAUDE_WHICH" \
      "  real path  : $CLAUDE_REAL" \
      "Version drift is a measured confound, so this is a failure, not a warning."
fi
printf '  [ok] claude %s at %s (via %s)\n' "$CC_OBSERVED" "$CLAUDE_REAL" "$CLAUDE_WHICH"
printf '  [ok] node %s at %s\n' "${NODE_OBSERVED:-<none>}" "$NODE_REAL"
printf '  [ok] npm %s at %s\n'  "${NPM_OBSERVED:-<none>}"  "$NPM_REAL"

echo
echo "== persistent shell settings (only \$HOME/.bashrc of $CCLAB_USER) =="
BASHRC="$HOME/.bashrc"
[ ! -L "$BASHRC" ] || die "$BASHRC is a symlink; refusing to write through it."
[ -e "$BASHRC" ] || : > "$BASHRC"
[ -f "$BASHRC" ] || die "$BASHRC exists but is not a regular file."

AUTOUPDATER_LINE='export DISABLE_AUTOUPDATER=1'
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'

# An existing DISABLE_AUTOUPDATER line is NOT evidence that the right value is in
# effect - it may set 0. Appending a second, contradicting line would make the
# result depend on line order, so report the conflict instead of "fixing" it.
conflict=0
while IFS= read -r raw; do
  [ -n "$raw" ] || continue
  text="${raw#*:}"
  text="${text#"${text%%[![:space:]]*}"}"
  case "$text" in
    "$AUTOUPDATER_LINE") ;;
    \#*) ;;
    *) conflict=1; printf '  [CONFLICT] %s\n' "$raw" ;;
  esac
done < <(grep -n 'DISABLE_AUTOUPDATER' "$BASHRC" 2>/dev/null || true)

if [ "$conflict" -eq 1 ]; then
  die "$BASHRC already sets DISABLE_AUTOUPDATER to something other than 1 (see [CONFLICT] above)." \
      "Nothing was appended. Fix the existing line by hand, then re-run this script." \
      "The install above was still pin-safe: this process exported DISABLE_AUTOUPDATER=1" \
      "itself. The conflict concerns future shells."
fi

if grep -qxF "$AUTOUPDATER_LINE" "$BASHRC"; then
  echo "  [ok]  already present, not duplicated: $AUTOUPDATER_LINE"
else
  printf '%s\n' "$AUTOUPDATER_LINE" >> "$BASHRC"
  echo "  [add] $AUTOUPDATER_LINE"
fi

if grep -qxF "$PATH_LINE" "$BASHRC"; then
  echo "  [ok]  already present, not duplicated: $PATH_LINE"
else
  if grep -q '\.local/bin' "$BASHRC"; then
    echo "  [note] another .local/bin line already exists in $BASHRC; appending the canonical one"
  fi
  printf '%s\n' "$PATH_LINE" >> "$BASHRC"
  echo "  [add] $PATH_LINE"
fi

echo
echo "== observed versions (recorded to $REPORT) =="
# Written last, after the version checks and the shell settings above: this file
# is the record of a completed setup, so it must not appear when the setup did
# not complete. 'set -C' turns the redirect into O_CREAT|O_EXCL, so it fails if
# anything occupies the path now - including a symlink created since the check at
# the start of this script. Nothing existing is deleted, archived or overwritten.
( set -C; : > "$REPORT" ) 2>/dev/null \
  || die "could not create $REPORT without overwriting something now at that path." \
         "Nothing was deleted or archived. Inspect the path, move it aside yourself, and re-run."
{
  echo "# CodeAgent ConfigLab - observed environment"
  echo "# generated by setup/10-cclab-setup.sh; contains no secrets"
  echo "date_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "user: $(id -un)"
  echo "home: $HOME"
  echo "kernel_release: $KERNEL_RELEASE"
  echo "wsl2_confirmed: $WSL2_CONFIRMED"
  echo "nvm: ${NVM_OBSERVED:-<none>} (pin ${NVM_VERSION#v})"
  echo "node: ${NODE_OBSERVED:-<none>} (pin: ${NODE_VERSION_PIN:-none - installed by major $NODE_MAJOR})"
  echo "npm: ${NPM_OBSERVED:-<none>} (pin: ${NPM_VERSION_PIN:-none})"
  echo "sandbox_runtime: ${SBX_OBSERVED:-<none>} (pin: ${SANDBOX_RUNTIME_VERSION_PIN:-none})"
  echo "claude: ${CC_OBSERVED:-<none>} (pin $CC_VERSION)"
  echo "claude_path_command_v: $CLAUDE_WHICH"
  echo "claude_path_resolved: $CLAUDE_REAL"
  echo "node_path_resolved: $NODE_REAL"
  echo "npm_path_resolved: $NPM_REAL"
  echo "nvm_installer_sha256: $NVM_INSTALLER_SHA256"
  echo "claude_installer_sha256: $CC_INSTALLER_SHA256"
} >> "$REPORT"
sed 's/^/  /' "$REPORT"

if [ -z "$NODE_VERSION_PIN" ] || [ -z "$NPM_VERSION_PIN" ] || [ -z "$SANDBOX_RUNTIME_VERSION_PIN" ]; then
  cat <<'MSG'

  REPRODUCIBILITY: choosing node by major version and installing npm /
  sandbox-runtime without a version does NOT give exact reproducibility - a later
  run can pick up different exact versions. The values just observed are recorded
  above; copy them into NODE_VERSION_PIN / NPM_VERSION_PIN /
  SANDBOX_RUNTIME_VERSION_PIN in setup/common.sh before the final experiment.
  They are left empty until observed here, rather than guessed.
MSG
fi

cat <<MSG

HEADLESS NOTE: a non-interactive shell does not source .bashrc. The future
headless runner must set DISABLE_AUTOUPDATER=1 explicitly in the environment it
hands to 'claude -p', otherwise the pinned version can update underneath a run.
It must also remove every auth override variable from that environment
(${CCLAB_AUTH_OVERRIDE_VARS[*]})
so the persisted Claude.ai login is what is used - claude_sanitized in
setup/common.sh does both. It must never source ~/$CCLAB_LEGACY_TOKEN_FILE_NAME.

Next, still as $CCLAB_USER:

  1) Start 'claude' interactively and complete its normal Claude.ai login
     (/login) with the existing Pro account. The login state stays under
     $HOME, owned by $CCLAB_USER. No API key, no extra service and no new
     subscription is involved. Do NOT run 'claude setup-token' and do NOT export
     any token or API key - a manually stored OAuth token was tested and failed
     real requests with "401 Invalid bearer token".

  2) bash $SCRIPT_DIR/20-verify.sh
     Checks local auth state only. Actual Pro / model access is established
     only by a separate headless smoke test.
MSG
