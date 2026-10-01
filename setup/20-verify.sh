#!/usr/bin/env bash
# CodeAgent ConfigLab - verification of INSTALLATION PREREQUISITES. Run AS cclab.
#
# What this script does: inspect versions, executable paths and file metadata.
# What it does NOT do: log in, call a model, or prove that any sandbox policy is
# actually enforced. See the "NOT VERIFIED" block it prints at the end.
#
# Optional, off by default:
#   CCLAB_RUN_DOCTOR=1       also run 'claude doctor' (see the note below)
#   CCLAB_RUN_BWRAP_SMOKE=1  also run a minimal bwrap smoke test
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=setup/common.sh
. "$SCRIPT_DIR/common.sh"

fail=0
ok()    { printf '  [ok]     %s\n' "$1"; }
bad()   { printf '  [MISS]   %s\n' "$1"; fail=1; }
warn()  { printf '  [warn]   %s\n' "$1"; }
note()  { printf '  [note]   %s\n' "$1"; }
unver() { printf '  [UNVER]  %s\n' "$1"; }

# check_exe NAME -> 0 found and native, 1 not found, 2 found but Windows/mounted
# (case 2 reports itself). On success CHECKED_EXE_PATH holds the resolved path.
CHECKED_EXE_PATH=""
check_exe() {
  local name="$1" w r
  CHECKED_EXE_PATH=""
  w="$(command -v "$name" 2>/dev/null)"
  [ -n "$w" ] || return 1
  r="$(resolve_exe "$name")"
  [ -z "$RESOLVE_NOTE" ] || note "$RESOLVE_NOTE"
  if is_windows_exe "$r"; then
    bad "$name resolves to a Windows / mounted-drive executable: $w -> $r (fstype $(path_fstype "$r"))"
    return 2
  fi
  CHECKED_EXE_PATH="$r"
  return 0
}

# --- identity first: a wrong user or a wrong HOME is a hard error -------------
require_linux_wsl2
require_user "$CCLAB_USER"
require_matching_home "$CCLAB_USER"

# Any claude invocation below must not trigger a background self-update.
export DISABLE_AUTOUPDATER=1

echo "== identity and environment =="
note "user=$(id -un) uid=$(id -u) home=$HOME"
if [ "$WSL2_CONFIRMED" = "yes" ]; then
  ok "$(wsl2_status_line)"
else
  unver "$(wsl2_status_line)"
fi

echo
echo "== sandbox dependencies =="
check_exe bwrap; rc=$?
case "$rc" in
  0) ok "bubblewrap $(bwrap --version 2>/dev/null) at $CHECKED_EXE_PATH" ;;
  1) bad "bubblewrap (bwrap) not found - run setup/00-host-setup.sh, or: sudo apt-get install -y bubblewrap" ;;
esac
check_exe socat; rc=$?
case "$rc" in
  0) ok "socat at $CHECKED_EXE_PATH" ;;
  1) bad "socat not found - run setup/00-host-setup.sh, or: sudo apt-get install -y socat" ;;
esac
check_exe rg; rc=$?
case "$rc" in
  0) ok "$(rg --version 2>/dev/null | head -n1) at $CHECKED_EXE_PATH" ;;
  1) bad "ripgrep (rg) not found - run setup/00-host-setup.sh, or: sudo apt-get install -y ripgrep" ;;
esac

echo
echo "== unprivileged user namespaces / AppArmor =="
# Read the knob directly instead of interpreting sysctl failures: "no key",
# "cannot read" and "command missing" are different situations, and only one of
# them means the restriction is absent.
USERNS_KNOB=/proc/sys/kernel/apparmor_restrict_unprivileged_userns
APPARMOR_STATUS="unknown"
if [ ! -e "$USERNS_KNOB" ]; then
  APPARMOR_STATUS="knob-absent"
  note "$USERNS_KNOB does not exist: this specific restriction is not present on this kernel."
  note "That is not the same as proving unprivileged userns works - the smoke test below decides."
elif [ ! -r "$USERNS_KNOB" ]; then
  APPARMOR_STATUS="unreadable"
  unver "$USERNS_KNOB exists but is not readable by $(id -un) - restriction status unknown."
else
  v="$(cat "$USERNS_KNOB" 2>/dev/null)"
  case "$v" in
    0) APPARMOR_STATUS="unrestricted"; ok "unprivileged userns unrestricted (value=0)" ;;
    1) APPARMOR_STATUS="restricted"
       unver "unprivileged userns restricted (value=1). This alone is NOT a verdict: a suitable"
       unver "  AppArmor profile for bwrap may already exist. Profile detection is not attempted"
       unver "  here - settle it with the bwrap smoke test, not with this number." ;;
    *) APPARMOR_STATUS="unexpected:$v"; note "unexpected value in $USERNS_KNOB: '$v'" ;;
  esac
fi
if [ -r /sys/module/apparmor/parameters/enabled ]; then
  note "apparmor module enabled=$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)"
else
  note "apparmor module parameter not readable (module may be absent in this kernel)"
fi
if [ -r /proc/sys/user/max_user_namespaces ]; then
  note "max_user_namespaces=$(cat /proc/sys/user/max_user_namespaces 2>/dev/null)"
fi
command -v sysctl >/dev/null 2>&1 || note "sysctl binary not available (the /proc read above is the source of truth here)"
note "No change is proposed to AppArmor: disabling it system-wide, or relaxing it globally, is out"
note "  of scope here. The legitimate fix is a narrow profile for bwrap and that is an admin decision."

echo
echo "== toolchain =="
export NVM_DIR="$HOME/.nvm"
# Observed versions are captured unconditionally: the setup-record comparison
# further down needs them whether or not a pin is set.
OBS_NVM=""; OBS_NODE=""; OBS_NPM=""; OBS_SBX=""; OBS_CLAUDE=""
if [ -s "$NVM_DIR/nvm.sh" ]; then
  # nvm.sh is third-party and not guaranteed to be clean under 'set -u'.
  set +u
  # shellcheck disable=SC1091
  . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  set -u
  nvm_observed="$(nvm --version 2>/dev/null)"
  OBS_NVM="$nvm_observed"
  if [ -z "$nvm_observed" ]; then
    bad "$NVM_DIR/nvm.sh exists but 'nvm' does not run - a present file is not a working install"
  elif [ "$nvm_observed" != "${NVM_VERSION#v}" ]; then
    bad "nvm $nvm_observed, pinned ${NVM_VERSION#v} - file presence is not proof of the pinned version"
  else
    ok "nvm $nvm_observed (pin ${NVM_VERSION#v})"
  fi
else
  bad "nvm not installed at $NVM_DIR - run setup/10-cclab-setup.sh"
fi

for tool in node npm git python3; do
  check_exe "$tool"; rc=$?
  case "$rc" in
    0) case "$tool" in
         node) ok "node $(node -v 2>/dev/null) at $CHECKED_EXE_PATH" ;;
         npm)  ok "npm $(npm -v 2>/dev/null) at $CHECKED_EXE_PATH" ;;
         git)  ok "$(git --version 2>/dev/null) at $CHECKED_EXE_PATH" ;;
         *)    ok "$(python3 --version 2>&1) at $CHECKED_EXE_PATH" ;;
       esac ;;
    1) bad "$tool not found" ;;
  esac
done

OBS_NODE="$(semver_of "$(node -v 2>/dev/null)")"
OBS_NPM="$(semver_of "$(npm -v 2>/dev/null)")"
if [ -n "$NODE_VERSION_PIN" ]; then
  [ "$OBS_NODE" = "$(semver_of "$NODE_VERSION_PIN")" ] \
    || bad "node ${OBS_NODE:-<none>} does not match the pin $NODE_VERSION_PIN"
fi
if [ -n "$NPM_VERSION_PIN" ]; then
  [ "$OBS_NPM" = "$(semver_of "$NPM_VERSION_PIN")" ] \
    || bad "npm ${OBS_NPM:-<none>} does not match the pin $NPM_VERSION_PIN"
fi

sbx_observed="$(npm ls -g --depth=0 2>/dev/null \
  | sed -n 's|.*@anthropic-ai/sandbox-runtime@\([0-9][^ ]*\).*|\1|p' | head -n1)"
OBS_SBX="$sbx_observed"
if [ -n "$sbx_observed" ]; then
  ok "@anthropic-ai/sandbox-runtime $sbx_observed installed"
  if [ -n "$SANDBOX_RUNTIME_VERSION_PIN" ] && [ "$sbx_observed" != "$SANDBOX_RUNTIME_VERSION_PIN" ]; then
    bad "sandbox-runtime $sbx_observed does not match the pin $SANDBOX_RUNTIME_VERSION_PIN"
  fi
  unver "package installed != filter loaded != blocking actually enforced. Only the first is checked here."
else
  bad "@anthropic-ai/sandbox-runtime not found in 'npm ls -g --depth=0'"
fi

echo
echo "== version pins =="
if [ -z "$NODE_VERSION_PIN" ] || [ -z "$NPM_VERSION_PIN" ] || [ -z "$SANDBOX_RUNTIME_VERSION_PIN" ]; then
  unver "node major selection and unversioned npm / sandbox-runtime installs do NOT give exact"
  unver "  reproducibility. Pin the observed exact versions in setup/common.sh before the final runs."
fi

echo
echo "== claude code =="
export PATH="$HOME/.local/bin:$PATH"
check_exe claude; rc=$?
case "$rc" in
  0) cc_observed="$(semver_of "$(claude --version 2>/dev/null)")"
     OBS_CLAUDE="$cc_observed"
     if [ -z "$cc_observed" ]; then
       bad "claude --version produced no version string"
     elif [ "$cc_observed" != "$CC_VERSION" ]; then
       bad "claude $cc_observed does not match the pinned $CC_VERSION - version drift is a confound"
     else
       ok "claude $cc_observed (pin $CC_VERSION) at $CHECKED_EXE_PATH"
     fi
     case "$CHECKED_EXE_PATH" in
       "$HOME"/*) ok "resolved inside the cclab home - per-user native install" ;;
       *) warn "resolved outside \$HOME ($CHECKED_EXE_PATH) - confirm this is the build you measure" ;;
     esac ;;
  1) bad "claude not found on PATH" ;;
esac

echo
echo "== setup record vs. what runs now =="
REPORT="$HOME/$CCLAB_VERSION_REPORT_NAME"
# The record is DATA: parsed with the awk helpers in common.sh, never sourced or
# eval'd. It is not read at all unless it is a plain regular file.
report_readable=1
if [ -L "$REPORT" ]; then
  bad "$REPORT is a symlink - refusing to read it"; report_readable=0
elif [ ! -e "$REPORT" ]; then
  bad "$REPORT is missing - run setup/10-cclab-setup.sh; with no record there is nothing to compare"
  report_readable=0
elif [ ! -f "$REPORT" ]; then
  bad "$REPORT exists but is not a regular file - refusing to read it"; report_readable=0
fi

# field_get KEY -> sets FIELD_VALUE, returns 1 (and reports) when the field is
# missing, duplicated or empty. It reports through bad() in the current shell,
# so it must never be called inside a command substitution.
FIELD_VALUE=""
field_get() {
  local key="$1" count
  FIELD_VALUE=""
  count="$(report_field_count "$REPORT" "$key")"
  case "$count" in
    ''|*[!0-9]*) bad "setup record: field '$key' could not be counted (unreadable record)"; return 1 ;;
  esac
  if [ "$count" -eq 0 ]; then
    bad "setup record: required field '$key' is missing"; return 1
  fi
  if [ "$count" -gt 1 ]; then
    bad "setup record: field '$key' appears $count times - the record is ambiguous"; return 1
  fi
  FIELD_VALUE="$(report_field_value "$REPORT" "$key")"
  if [ -z "$FIELD_VALUE" ]; then
    bad "setup record: field '$key' is empty"; return 1
  fi
  return 0
}

compare_recorded() {   # KEY OBSERVED LABEL
  local key="$1" observed="$2" label="$3" recorded first
  field_get "$key" || return 0
  # Only the first whitespace-separated token is the recorded version; the rest
  # of the line is the "(pin ...)" annotation. Scanning the whole line would let
  # a malformed value such as "<none> (pin 2.1.263)" pick up the pin and pass.
  first="${FIELD_VALUE%% *}"
  recorded="$(semver_of "$first")"
  if [ -z "$recorded" ]; then
    bad "setup record: field '$key' is malformed - no version in: $FIELD_VALUE"
    return 0
  fi
  if [ -z "$observed" ]; then
    bad "$label: record says $recorded, but no version could be observed now - cannot compare"
    return 0
  fi
  if [ "$recorded" != "$observed" ]; then
    bad "$label drift since setup: record says $recorded, now observed $observed"
  else
    ok "$label $observed matches the setup record"
  fi
}

if [ "$report_readable" -eq 1 ]; then
  if field_get date_utc; then note "record written at $FIELD_VALUE (UTC)"; fi
  if field_get user; then
    [ "$FIELD_VALUE" = "$(id -un)" ] \
      || bad "setup record was written by user '$FIELD_VALUE', but this is '$(id -un)'"
  fi
  if field_get home; then
    [ "$FIELD_VALUE" = "$HOME" ] \
      || bad "setup record was written for home '$FIELD_VALUE', but HOME is '$HOME'"
  fi

  compare_recorded nvm             "$OBS_NVM"    "nvm"
  compare_recorded node            "$OBS_NODE"   "node"
  compare_recorded npm             "$OBS_NPM"    "npm"
  compare_recorded sandbox_runtime "$OBS_SBX"    "sandbox-runtime"
  compare_recorded claude          "$OBS_CLAUDE" "claude"

  note "installer hashes recorded at install time (historical record only):"
  note "  nvm:    $(report_field_value "$REPORT" nvm_installer_sha256)"
  note "  claude: $(report_field_value "$REPORT" claude_installer_sha256)"
  unver "Those hashes are NOT re-computed or re-checked here. This script does not verify the"
  unver "  integrity of the installed files - only that recorded versions match what runs now."
fi

echo
echo "== autoupdater control =="
if [ "${DISABLE_AUTOUPDATER:-}" = "1" ]; then
  ok "DISABLE_AUTOUPDATER=1 in this process (this script exports it itself)"
else
  bad "DISABLE_AUTOUPDATER is '${DISABLE_AUTOUPDATER:-<unset>}' in this process"
fi
BASHRC="$HOME/.bashrc"
AUTOUPDATER_LINE='export DISABLE_AUTOUPDATER=1'
if [ -L "$BASHRC" ]; then
  bad "$BASHRC is a symlink - not inspected"
elif [ ! -f "$BASHRC" ]; then
  bad "$BASHRC missing - run setup/10-cclab-setup.sh"
else
  conflict=0
  while IFS= read -r raw; do
    [ -n "$raw" ] || continue
    text="${raw#*:}"
    text="${text#"${text%%[![:space:]]*}"}"
    case "$text" in
      "$AUTOUPDATER_LINE") ;;
      \#*) ;;
      *) conflict=1; printf '  [MISS]   conflicting line in %s: %s\n' "$BASHRC" "$raw"; fail=1 ;;
    esac
  done < <(grep -n 'DISABLE_AUTOUPDATER' "$BASHRC" 2>/dev/null || true)
  if [ "$conflict" -eq 1 ]; then
    note "a line mentioning DISABLE_AUTOUPDATER is not proof the value is 1; fix the line above by hand"
  elif grep -qxF "$AUTOUPDATER_LINE" "$BASHRC"; then
    ok "$BASHRC contains exactly: $AUTOUPDATER_LINE"
  else
    bad "$BASHRC does not contain: $AUTOUPDATER_LINE"
  fi
fi
note "Interactive shells only. A headless runner does not source .bashrc and must set"
note "  DISABLE_AUTOUPDATER=1 explicitly in the environment it gives to 'claude -p'."

echo
echo "== Claude.ai authentication (local state only; no model call) =="
# Verified design: cclab's persisted Claude.ai (Pro) login, used by 'claude -p'
# with every auth override variable unset. Values are never printed below.
for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do
  if [ -n "${!v+x}" ]; then
    bad "$v is set in this environment - it would override the Claude.ai login (value not shown)"
  fi
done
ok "override variables checked in this process: ${CCLAB_AUTH_OVERRIDE_VARS[*]} (set ones are listed above as [MISS])"
note "This covers this process only; the runner must unset them in its own environment (claude_sanitized)."

# Legacy manual-token file: metadata only, content never read, nothing deleted.
LEGACY_TOKEN_FILE="$HOME/$CCLAB_LEGACY_TOKEN_FILE_NAME"
if [ -L "$LEGACY_TOKEN_FILE" ] || [ -e "$LEGACY_TOKEN_FILE" ]; then
  bad "legacy token file present: $LEGACY_TOKEN_FILE ($(stat -c 'owner=%U mode=%a' "$LEGACY_TOKEN_FILE" 2>/dev/null || echo 'stat failed'))"
  note "  It holds a manually stored CLAUDE_CODE_OAUTH_TOKEN from the disproven approach (401 on real"
  note "  requests); sourcing it would override the Claude.ai login. Content not read. Remove it yourself."
else
  ok "no legacy token file ($LEGACY_TOKEN_FILE)"
fi

# Shell startup files: grep -q only - a matching line could itself hold a secret.
for f in "$HOME/.bashrc" "$HOME/.profile" "$HOME/.bash_profile"; do
  [ -f "$f" ] || continue
  if grep -qE 'cclab-token|CLAUDE_CODE_OAUTH_TOKEN|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN' "$f" 2>/dev/null; then
    bad "$f mentions a token/API-key override (line not shown) - remove it by hand"
  fi
done

# 'claude auth status' reads local state. Its raw output may contain account
# identifiers, so it is never printed: only four fields are extracted.
if command -v claude >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
  auth_rc=0
  auth_out="$(timeout 30 bash -c '. "$1"; claude_sanitized auth status' _ "$SCRIPT_DIR/common.sh" </dev/null 2>/dev/null)" || auth_rc=$?
  auth_fields="$(printf '%s' "$auth_out" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(1)
def f(k):
    v = d.get(k)
    return json.dumps(v) if isinstance(v, bool) else str(v)
print(" ".join(k + "=" + f(k) for k in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")))
' 2>/dev/null)" || auth_fields=""
  unset auth_out
  want_fields="loggedIn=true authMethod=claude.ai apiProvider=firstParty subscriptionType=pro"
  if [ "$auth_rc" -ne 0 ]; then
    bad "'claude auth status' exited $auth_rc${auth_fields:+ ($auth_fields)} - log in via the Claude.ai flow"
  elif [ -z "$auth_fields" ]; then
    bad "'claude auth status' output could not be parsed as JSON (output not shown)"
  elif [ "$auth_fields" = "$want_fields" ]; then
    ok "Claude.ai authentication appears configured for $CCLAB_USER (local state: $auth_fields)"
  else
    bad "unexpected local auth state: $auth_fields (expected $want_fields)"
  fi
else
  bad "cannot check local auth state: claude or python3 not available"
fi

# Credential storage: metadata only. The location is an implementation detail,
# so absence is a note, not a failure.
CRED_FILE="$HOME/.claude/.credentials.json"
if [ -L "$CRED_FILE" ]; then
  bad "$CRED_FILE is a symlink - auth state is expected to be owned by $CCLAB_USER under its HOME"
elif [ -f "$CRED_FILE" ]; then
  c_owner="$(stat -c %U "$CRED_FILE" 2>/dev/null)"
  c_mode="$(stat -c %a "$CRED_FILE" 2>/dev/null)"
  if [ "$c_owner" = "$CCLAB_USER" ]; then
    ok "credential store owned by $CCLAB_USER, mode $c_mode (content not read): $CRED_FILE"
  else
    bad "credential store owner is '$c_owner', expected '$CCLAB_USER': $CRED_FILE"
  fi
else
  note "no $CRED_FILE (storage location is not a contract; the status check above decides)"
fi
unver "Local auth state != server-side acceptance != successful inference. The retired manual-token"
unver "  path showed healthy local status and still failed with 401. Pro / model access requires a"
unver "  separate headless smoke test; this script made no model call."

echo
echo "== isolation preconditions (existence and emptiness; contents are not read) =="
check_config_dir() {
  local d="$1" label="$2"
  if [ -L "$d" ]; then
    bad "$label is a symlink ($d -> $(readlink "$d" 2>/dev/null || echo '?')) - target not audited"
  elif [ ! -e "$d" ]; then
    ok "no $label"
  elif [ ! -d "$d" ]; then
    bad "$label exists but is not a directory: $d"
  elif [ -z "$(find "$d" -mindepth 1 -print -quit 2>/dev/null)" ]; then
    ok "$label exists but is empty: $d"
  else
    bad "$label is NOT empty - it would apply to every arm (entry names only, contents not read):"
    find "$d" -mindepth 1 -maxdepth 2 -printf '           %P\n' 2>/dev/null | head -n 20
  fi
}
if [ -f "$HOME/.claude/CLAUDE.md" ]; then
  bad "cclab has a user-level CLAUDE.md - it would leak into every arm"
else
  ok "no user-level CLAUDE.md"
fi
check_config_dir "$HOME/.claude/skills"   "user-level skills"
check_config_dir "$HOME/.claude/rules"    "user-level rules"
check_config_dir "$HOME/.claude/agents"   "user-level agents"
check_config_dir "$HOME/.claude/commands" "user-level commands"
check_config_dir "$HOME/.claude/plugins"  "user-level plugins"
if [ -f /etc/claude-code/CLAUDE.md ]; then
  bad "managed-policy CLAUDE.md exists and CANNOT be excluded"
else
  ok "no managed-policy CLAUDE.md"
fi
if [ -d "$HOME/.claude/projects" ] && [ -n "$(find "$HOME/.claude/projects" -name MEMORY.md -print -quit 2>/dev/null)" ]; then
  bad "auto-memory MEMORY.md found - must be empty before runs"
else
  ok "no auto-memory index yet"
fi

echo
echo "== settings sources (presence only - NOT audited) =="
for f in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json" "$HOME/.claude.json" \
         "$HOME/.claude/mcp.json" /etc/claude-code/managed-settings.json; do
  if [ -e "$f" ]; then
    note "present, content NOT audited: $f"
  else
    note "absent: $f"
  fi
done
unver "Settings, environment variables (beyond the auth overrides above) and plugin contents are not inspected by this script."
unver "  Their absence from the [MISS] list is a scope limit, not a clean bill of health."

echo
echo "== optional checks (off by default) =="
# 'claude doctor' is NOT run automatically: it has not been verified here that it
# is non-interactive and side-effect-free in this version, so it stays a separate,
# deliberate step. When enabled, its exit code counts - it is never swallowed.
if [ "${CCLAB_RUN_DOCTOR:-0}" = "1" ]; then
  echo "  -- claude doctor (enabled via CCLAB_RUN_DOCTOR=1) --"
  doctor_rc=0
  doctor_out="$(timeout 60 claude doctor </dev/null 2>&1)" || doctor_rc=$?
  printf '%s\n' "$doctor_out" | sed 's/^/           /'
  if [ "$doctor_rc" -eq 0 ]; then
    ok "claude doctor exited 0"
  else
    bad "claude doctor exited $doctor_rc (a failure here is a failure of this run)"
  fi
else
  note "claude doctor not run. Run it yourself when you want its diagnostics:  claude doctor"
  note "  Left manual on purpose: this script has not verified that it is read-only or"
  note "  non-interactive, so it must not hide behind a green result here."
fi

# Minimal, harmless bwrap smoke test: enter a user+pid namespace with a read-only
# view of / and run /bin/true. It writes nothing. Off by default.
if [ "${CCLAB_RUN_BWRAP_SMOKE:-0}" = "1" ]; then
  echo "  -- bwrap smoke test (enabled via CCLAB_RUN_BWRAP_SMOKE=1) --"
  if command -v bwrap >/dev/null 2>&1; then
    smoke_rc=0
    smoke_out="$(bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid -- /bin/true 2>&1)" || smoke_rc=$?
    if [ "$smoke_rc" -eq 0 ]; then
      ok "bwrap can create an unprivileged user namespace"
    else
      bad "bwrap smoke test failed (rc=$smoke_rc): ${smoke_out:-<no output>}"
    fi
  else
    bad "bwrap smoke test requested but bwrap is not installed"
  fi
else
  note "bwrap smoke test not run. To check namespace creation later:"
  note "  CCLAB_RUN_BWRAP_SMOKE=1 bash setup/20-verify.sh"
  note "  (equivalent to: bwrap --ro-bind / / --dev /dev --unshare-user --unshare-pid -- /bin/true)"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "RESULT: installation prerequisites verified"
else
  echo "RESULT: installation prerequisites NOT verified - fix the [MISS] lines above"
fi

cat <<MSG

NOT VERIFIED BY THIS SCRIPT
  - Pro authentication ................ local Claude.ai state checked only; server-side
                                        acceptance and model access not verified (no
                                        login, no model call was made)
  - Seccomp filter effective at run time not verified (package presence only)
  - Behavioral file/network isolation .. not verified
  - Readiness to start the benchmark ... not confirmed
  - WSL2 environment .................. ${WSL2_CONFIRMED}
  - Unprivileged userns / AppArmor .... ${APPARMOR_STATUS} (not a verdict on bwrap; see smoke test)
  - Settings sources .................. listed above, contents not audited
  - Installed-file integrity .......... not verified (recorded installer hashes are
                                        a historical note, not re-checked here)

  These are distinct levels and must not be collapsed into one another:
  package installed  !=  filter detected  !=  blocking actually enforced.

  A separate user plus a clean working copy is isolation hygiene, not a security
  sandbox. The behavioral checks that would actually test enforcement are listed
  in setup/NEXT-behavioral-checks.md and have not been run.
MSG

exit "$fail"
