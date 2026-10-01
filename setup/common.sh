#!/usr/bin/env bash
# CodeAgent ConfigLab - shared constants and guards.
# Sourced by 00/10/15/20. Defines variables and functions only; no side effects.
#
# Scope note: every check here reads process/user metadata and /proc-/sys status
# files. It never reads the content of personal files.

# --------------------------------------------------------------- versions --
CC_VERSION="2.1.263"    # pinned: version drift is a measured confound (risk R2)
NVM_VERSION="v0.40.7"   # pinned
NODE_MAJOR="22"         # Claude Code npm packages require Node >= 22

# Exact versions observed on the verified install (2026-09-22T14:03:12Z, cclab on WSL2)
# and copied from ~/cclab-setup-versions.txt - measured, not guessed. An empty
# value falls back to major-only / unversioned installs, which are NOT
# reproducible.
NODE_VERSION_PIN="22.23.2"            # empty => install by major only
NPM_VERSION_PIN="10.9.8"              # empty => whatever node ships
SANDBOX_RUNTIME_VERSION_PIN="0.0.77"  # empty => npm dist-tag "latest"

CCLAB_USER="cclab"
CCLAB_VERSION_REPORT_NAME="cclab-setup-versions.txt"

# Authentication: the persisted Claude.ai (Pro) login of cclab, stored under its
# own HOME by Claude Code's normal login flow. Any of these variables would
# override or redirect that login, so every claude invocation must run without
# them (see claude_sanitized below).
CCLAB_AUTH_OVERRIDE_VARS=(
  ANTHROPIC_API_KEY
  ANTHROPIC_AUTH_TOKEN
  CLAUDE_CODE_OAUTH_TOKEN
  CLAUDE_CODE_OAUTH_REFRESH_TOKEN
  CLAUDE_CODE_USE_BEDROCK
  CLAUDE_CODE_USE_VERTEX
  CLAUDE_CODE_USE_FOUNDRY
)
# Legacy, disproven: a manually stored CLAUDE_CODE_OAUTH_TOKEN (from
# 'claude setup-token') failed real requests with "401 Invalid bearer token".
# The file is only checked for presence so a stale token is noticed; it is never
# read, sourced or migrated.
CCLAB_LEGACY_TOKEN_FILE_NAME=".cclab-token"

# Filled in by require_linux_wsl2.
KERNEL_RELEASE="unknown"
WSL2_CONFIRMED="unknown"   # yes | no
WSL_KIND="unknown"         # wsl2 | wsl-unconfirmed | non-wsl

# Filled in by resolve_exe / check helpers.
RESOLVE_NOTE=""

# ---------------------------------------------------------------- helpers --

# die "first line" ["more" ...] - prints to stderr and exits the calling script.
die() {
  printf 'FATAL: %s\n' "$1" >&2
  shift
  while [ "$#" -gt 0 ]; do printf '       %s\n' "$1" >&2; shift; done
  exit 1
}

semver_of() { printf '%s\n' "${1:-}" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -n1; }

strip_trailing_slash() {
  case "$1" in
    /) printf '/\n' ;;
    */) printf '%s\n' "${1%/}" ;;
    *) printf '%s\n' "$1" ;;
  esac
}

# passwd_field USER N  - field N of the passwd entry (6=home, 7=shell).
passwd_field() {
  local user="$1" n="$2" out=""
  if command -v getent >/dev/null 2>&1; then
    out="$(getent passwd "$user" 2>/dev/null | cut -d: -f"$n")"
  fi
  if [ -z "$out" ] && [ -r /etc/passwd ]; then
    out="$(awk -F: -v u="$user" -v n="$n" '$1==u {print $n}' /etc/passwd)"
  fi
  printf '%s\n' "$out"
}
passwd_home()  { passwd_field "$1" 6; }
passwd_shell() { passwd_field "$1" 7; }

path_fstype() { stat -f -c %T -- "$1" 2>/dev/null || printf 'unknown\n'; }

# claude_sanitized ARGS... - run claude with every auth override variable removed
# and the autoupdater disabled, so the persisted Claude.ai login is what is used.
# The future headless runner must invoke claude through this (or the same rule).
claude_sanitized() {
  local a=() v
  for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do a+=(-u "$v"); done
  env "${a[@]}" DISABLE_AUTOUPDATER=1 claude "$@"
}

# resolve_exe NAME - prints the real executable path with symlinks resolved.
# Returns 1 if NAME is not found. Sets RESOLVE_NOTE when resolution was partial.
resolve_exe() {
  local name="$1" p r
  RESOLVE_NOTE=""
  p="$(command -v "$name" 2>/dev/null)" || return 1
  [ -n "$p" ] || return 1
  case "$p" in
    /*) ;;
    *)  RESOLVE_NOTE="'$name' is a shell builtin/alias/function ($p), not a file on disk"
        printf '%s\n' "$p"; return 0 ;;
  esac
  if r="$(readlink -f "$p" 2>/dev/null)" && [ -n "$r" ]; then
    printf '%s\n' "$r"
  else
    RESOLVE_NOTE="could not resolve symlinks for $p; reporting the unresolved path"
    printf '%s\n' "$p"
  fi
}

# is_windows_exe PATH - true for Windows binaries and for anything living on a
# mounted Windows drive. The filesystem list is a heuristic; the caller prints
# the detected fstype so a false positive stays visible rather than silent.
is_windows_exe() {
  local p="${1:-}" fstype
  case "$p" in
    *.exe|*.EXE|*.Exe) return 0 ;;
    /mnt/[a-zA-Z]/*|/mnt/[a-zA-Z]) return 0 ;;
  esac
  fstype="$(path_fstype "$p")"
  case "$fstype" in
    9p|v9fs|drvfs|drv_fs|cifs|smb2|virtiofs) return 0 ;;
  esac
  return 1
}

# ----------------------------------------------------------------- guards --

# Hard requirement: a Linux kernel. WSL2 itself is reported, never assumed:
# if it cannot be confirmed, WSL2_CONFIRMED stays "no" and callers must print
# that as UNVERIFIED instead of quietly treating it as success.
require_linux_wsl2() {
  local sys osrelease procversion
  sys="$(uname -s 2>/dev/null || echo unknown)"
  if [ "$sys" != "Linux" ]; then
    die "this script must run inside WSL2 Ubuntu, but 'uname -s' reports '$sys'." \
        "Open a WSL2 shell (wsl.exe -d <distro>) and run it from there."
  fi
  osrelease="$(cat /proc/sys/kernel/osrelease 2>/dev/null || true)"
  procversion="$(cat /proc/version 2>/dev/null || true)"
  KERNEL_RELEASE="${osrelease:-unknown}"
  case "$osrelease $procversion" in
    *WSL2*|*wsl2*)           WSL_KIND="wsl2";            WSL2_CONFIRMED="yes" ;;
    *icrosoft*|*Microsoft*)  WSL_KIND="wsl-unconfirmed"; WSL2_CONFIRMED="no"  ;;
    *)                       WSL_KIND="non-wsl";         WSL2_CONFIRMED="no"  ;;
  esac
}

wsl2_status_line() {
  case "$WSL_KIND" in
    wsl2)            printf 'WSL2 confirmed (kernel %s)\n' "$KERNEL_RELEASE" ;;
    wsl-unconfirmed) printf 'UNVERIFIED: WSL detected but WSL2 could not be confirmed (kernel %s)\n' "$KERNEL_RELEASE" ;;
    non-wsl)         printf 'UNVERIFIED: Linux, but no WSL marker found (kernel %s) - not the documented lab environment\n' "$KERNEL_RELEASE" ;;
    *)               printf 'UNVERIFIED: WSL2 status unknown (require_linux_wsl2 was not called)\n' ;;
  esac
}

# The wrong user is a hard error, not a warning: it would install into the wrong
# home directory and silently change the measured environment.
require_user() {
  local want="$1" actual
  actual="$(id -un 2>/dev/null || echo unknown)"
  if [ "$actual" != "$want" ]; then
    die "must run as user '$want', but this shell runs as '$actual' (uid $(id -u 2>/dev/null || echo '?'))." \
        "Start a login shell for the benchmark user and re-run:" \
        "  sudo -i -u $want"
  fi
}

# HOME must match the account's registered home directory: 'sudo -u cclab bash'
# keeps the caller's HOME, which would scatter the setup across two homes.
require_matching_home() {
  local user="$1" registered want got
  registered="$(passwd_home "$user")"
  [ -n "$registered" ] || die "no passwd home directory field for user '$user'." \
                              "Run setup/00-host-setup.sh from your normal WSL user first."
  [ -n "${HOME:-}" ] || die "HOME is unset; expected $registered."
  want="$(strip_trailing_slash "$registered")"
  got="$(strip_trailing_slash "$HOME")"
  if [ "$want" != "$got" ]; then
    die "HOME does not match the registered home directory of '$user'." \
        "  HOME            = $got" \
        "  passwd home dir = $want" \
        "This usually means the shell was started with 'sudo -u $user bash' (which keeps the" \
        "caller's HOME) instead of the login form. Use:  sudo -i -u $user"
  fi
}

# 00 runs on the host account: not root (it calls sudo itself) and not cclab.
require_host_user() {
  local actual
  actual="$(id -un 2>/dev/null || echo unknown)"
  if [ "$(id -u 2>/dev/null || echo 1)" -eq 0 ]; then
    die "do not run the host step as root." \
        "Run it as your normal WSL user; it calls sudo only for the steps that need it."
  fi
  if [ "$actual" = "$CCLAB_USER" ]; then
    die "this is the host step; run it as your normal WSL user, not as '$CCLAB_USER'." \
        "The '$CCLAB_USER' account has no sudo rights and none will be granted."
  fi
}

# refuse_if_exists PATH WHAT [HINT ...] - stop rather than overwrite.
# The symlink test comes first because -e follows links: a dangling symlink is
# invisible to -e but must still be refused. Nothing is deleted, moved or
# archived here - clearing the path is the user's deliberate action.
refuse_if_exists() {
  local path="$1" what="$2"
  shift 2
  if [ -L "$path" ]; then
    die "$what already exists as a symlink: $path -> $(readlink "$path" 2>/dev/null || echo '?')" \
        "Refusing to write through it. Nothing was deleted, moved or archived." "$@"
  fi
  if [ -e "$path" ]; then
    die "$what already exists: $path" \
        "$(stat -c '  current: owner=%U mode=%a bytes=%s modified=%y' "$path" 2>/dev/null || echo '  (stat failed)')" \
        "Refusing to overwrite it. Nothing was deleted, moved or archived." "$@"
  fi
  return 0
}

# ------------------------------------------------- setup-record parsing ----
# The version report is DATA, never shell code: it is parsed with awk and is
# never sourced or eval'd. Lines look like "key: value"; '#' lines are comments.
# The caller is responsible for checking that FILE is a regular file first.

# report_field_count FILE KEY - how many data lines start with "KEY:".
# 0 means missing, >1 means duplicated; both are errors for the caller.
report_field_count() {
  awk -v k="$2" '
    /^[[:space:]]*#/ { next }
    index($0, k ":") == 1 { n++ }
    END { print n+0 }
  ' "$1" 2>/dev/null
}

# report_field_value FILE KEY - value of the last "KEY:" line, trimmed.
report_field_value() {
  awk -v k="$2" '
    /^[[:space:]]*#/ { next }
    index($0, k ":") == 1 {
      v = substr($0, length(k) + 2)
      sub(/^[[:space:]]+/, "", v)
      sub(/[[:space:]]+$/, "", v)
      last = v
    }
    END { print last }
  ' "$1" 2>/dev/null
}
