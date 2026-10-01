:
# SPIKE ONLY - CodeAgent ConfigLab harness-readiness spike. NOT the harness, NOT a
# benchmark task. Evidence for docs/HARNESS_READINESS_SPIKE.md.
#
# Run as cclab, fed on stdin from Windows (line 1 is a no-op because a BOM/CRLF
# can damage it):
#   Get-Content spike.sh -Raw | wsl.exe -d Ubuntu -u cclab --cd /home/cclab -- \
#     bash -lc 'tr -d "\r" | bash -s -- <step>'
# Steps: prep | probes | phase1 | phase2 | c0 | purge
# Never prints credentials; 'claude auth status' is reduced to four fields.
set -uo pipefail

SPIKE="$HOME/cclab-spike"
COMMON="${COMMON:-/mnt/c/Users/User/Desktop/Agentic_IDP/setup/common.sh}"
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
export PATH="$HOME/.local/bin:$PATH"
# shellcheck source=setup/common.sh
. "$COMMON" || { echo "cannot source $COMMON" >&2; exit 1; }   # CCLAB_AUTH_OVERRIDE_VARS
STATE="$SPIKE/state.env"
# shellcheck disable=SC1090
[ -f "$STATE" ] && . "$STATE"
ART="$SPIKE/artifacts"
MODEL="haiku"   # spike placeholder only - not the final model pin
CANARY_TEXT="CANARY-7f3a-SPIKE-HIDDEN"
DOMAINS='["api.anthropic.com","claude.ai","console.anthropic.com","platform.claude.com","statsig.anthropic.com"]'

# Byte state of a working copy, including .git, ignoring only __pycache__.
wc_hash() {
  (cd "$1" && find . -name __pycache__ -prune -o -type f -print0 \
     | LC_ALL=C sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)
}

# srt_cfg MODE WC RUNTMP OUT - MODE ro|impl. Whole spike tree read-denied (tmpfs),
# only this run's WC and TMPDIR bound back; /mnt/c hidden.
# Claude state writes: "wide" = all of ~/.claude (first design; lets the agent
# create ~/.claude/CLAUDE.md, settings.json, skills/ ...); "narrow" = only the
# session/runtime subpaths, so user-level instruction/settings paths stay read-only.
CS_WIDE="\"$HOME/.claude\",\"$HOME/.claude.json\""
CS_NARROW="\"$HOME/.claude/projects\",\"$HOME/.claude/session-env\",\"$HOME/.claude/sessions\",\"$HOME/.claude/shell-snapshots\",\"$HOME/.claude/backups\",\"$HOME/.claude/cache\",\"$HOME/.claude/.credentials.json\",\"$HOME/.claude.json\""
srt_cfg() {   # srt_cfg MODE WC RUNTMP OUT [wide|narrow]
  local mode="$1" wc="$2" rt="$3" out="$4" cs aw dw
  if [ "${5:-wide}" = narrow ]; then cs="$CS_NARROW"; else cs="$CS_WIDE"; fi
  if [ "$mode" = ro ]; then
    aw="[$cs,\"$rt\"]"; dw="[\"$wc\"]"
  else
    aw="[\"$wc\",$cs,\"$rt\"]"; dw="[]"
  fi
  cat > "$out" <<JSON
{"network":{"allowedDomains":$DOMAINS,"deniedDomains":[]},
 "filesystem":{"denyRead":["/mnt/c","$SPIKE"],"allowRead":["$wc","$rt"],
               "allowWrite":$aw,"denyWrite":$dw}}
JSON
}

# run_sbx CFG RUNTMP CMD... - sanitized auth env (setup/common.sh rule) + srt.
run_sbx() {
  local cfg="$1" rt="$2" a=() v; shift 2
  for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do a+=(-u "$v"); done
  env "${a[@]}" DISABLE_AUTOUPDATER=1 CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
      TMPDIR="$rt" srt -s "$cfg" -- "$@"
}

# srt forces TMPDIR=/tmp/claude inside the sandbox but cannot create it under a
# read-only /tmp; Claude Code fails with EROFS mkdir /tmp/claude otherwise.
# Claude runtime state, outside the repository (shared across runs: see O10).
case "${1:-}" in phase1|phase2|c0|narrow-p1|narrow-p2) mkdir -p -m 700 /tmp/claude ;; esac

COMMON_FLAGS=(--model "$MODEL" --permission-mode bypassPermissions --strict-mcp-config
              --settings '{}' --setting-sources "" --system-prompt-snapshot off
              --output-format stream-json --verbose)
TOOLS_PLAN="Bash,Read,Glob,Grep"
TOOLS_IMPL="Bash,Read,Edit,Write,Glob,Grep"

# summarize FILE - only the fields the spike needs from stream-json.
summarize() {
  python3 - "$1" <<'PY'
import json, sys
for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    try: e = json.loads(line)
    except Exception: continue
    if e.get("type") == "system" and e.get("subtype") == "init":
        print("init.session_id =", e.get("session_id"))
        print("init.model =", e.get("model"))
        print("init.permissionMode =", e.get("permissionMode"))
        print("init.tools =", sorted(e.get("tools") or []))
        print("init.mcp_servers =", e.get("mcp_servers"))
        print("init.keys =", sorted(e.keys()))
    if e.get("type") == "result":
        print("result.subtype =", e.get("subtype"), "is_error =", e.get("is_error"),
              "num_turns =", e.get("num_turns"))
        print("result.session_id =", e.get("session_id"))
        print("result.keys =", sorted(e.keys()))
        print("result.usage.keys =", sorted((e.get("usage") or {}).keys()))
        print("result.text =", (e.get("result") or "")[:1500])
PY
}

new_run() {   # new_run VAR_PREFIX -> opaque WC, TMPDIR, UUID appended to state
  local tok uuid
  tok="$(head -c8 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  uuid="$(cat /proc/sys/kernel/random/uuid)"
  cp -a "$SPIKE/fixture" "$SPIKE/runs/$tok"
  mkdir -p "$SPIKE/tmp/$tok"
  { echo "${1}_WC=$SPIKE/runs/$tok"; echo "${1}_TMP=$SPIKE/tmp/$tok"; echo "${1}_UUID=$uuid"; } >> "$STATE"
}

case "${1:-}" in
prep)
  [ -e "$SPIKE" ] && { echo "refusing: $SPIKE exists"; exit 1; }
  mkdir -p "$SPIKE"/{fixture,runs,tmp,hidden,artifacts,settings}
  cat > "$SPIKE/fixture/calc.py" <<'PY'
"""Spike fixture - trivial, no research value."""


def add(a, b):
    return a + b
PY
  printf '%s\n' "$CANARY_TEXT" > "$SPIKE/hidden/CANARY.txt"
  ( cd "$SPIKE/fixture" && git init -q && git add -A \
    && GIT_AUTHOR_NAME=fixture GIT_AUTHOR_EMAIL=fixture@invalid GIT_AUTHOR_DATE=2000-01-01T00:00:00Z \
       GIT_COMMITTER_NAME=fixture GIT_COMMITTER_EMAIL=fixture@invalid GIT_COMMITTER_DATE=2000-01-01T00:00:00Z \
       git -c commit.gpgsign=false commit -q -m baseline )
  : > "$STATE"; new_run C2; new_run C0
  . "$STATE"
  srt_cfg ro   "$C2_WC" "$C2_TMP" "$SPIKE/settings/srt-c2-ro.json"
  srt_cfg impl "$C2_WC" "$C2_TMP" "$SPIKE/settings/srt-c2-impl.json"
  srt_cfg impl "$C0_WC" "$C0_TMP" "$SPIKE/settings/srt-c0-impl.json"
  echo "prep ok"; cat "$STATE"
  ;;
probes)
  RO="$SPIKE/settings/srt-c2-ro.json"; IM="$SPIKE/settings/srt-c2-impl.json"
  t() { local label="$1"; shift; local out rc; out="$("$@" 2>&1)"; rc=$?
        printf '%-44s rc=%-3s %s\n' "$label" "$rc" "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-150)"; }
  echo "== RO (phase-1 sandbox) =="
  t "RO bash write WC"        run_sbx "$RO" "$C2_TMP" bash -c "echo x > '$C2_WC/PROBE.txt'"
  t "RO bash append calc.py"  run_sbx "$RO" "$C2_TMP" bash -c "echo '#x' >> '$C2_WC/calc.py'"
  t "RO node write WC"        run_sbx "$RO" "$C2_TMP" node -e "require('fs').writeFileSync('$C2_WC/PROBE2.txt','x')"
  t "RO bash rm calc.py"      run_sbx "$RO" "$C2_TMP" rm -f "$C2_WC/calc.py"
  t "RO read WC"              run_sbx "$RO" "$C2_TMP" head -n1 "$C2_WC/calc.py"
  t "RO write TMPDIR"         run_sbx "$RO" "$C2_TMP" bash -c 'echo x > "$TMPDIR/t" && echo wrote'
  t "RO cat canary"           run_sbx "$RO" "$C2_TMP" cat "$SPIKE/hidden/CANARY.txt"
  t "RO ls hidden"            run_sbx "$RO" "$C2_TMP" ls -A "$SPIKE/hidden"
  t "RO ls other run WC"      run_sbx "$RO" "$C2_TMP" ls -A "$C0_WC"
  t "RO ls /mnt/c"            run_sbx "$RO" "$C2_TMP" ls -A /mnt/c
  t "RO network example.com"  run_sbx "$RO" "$C2_TMP" curl -sS -m 10 -o /dev/null -w '%{http_code}' https://example.com
  t "RO claude --version"     run_sbx "$RO" "$C2_TMP" claude --version
  echo "== IMPL (implementation sandbox) =="
  t "IMPL bash write WC"      run_sbx "$IM" "$C2_TMP" bash -c "echo x > '$C2_WC/PROBE.txt' && echo wrote"
  run_sbx "$IM" "$C2_TMP" rm -f "$C2_WC/PROBE.txt"
  t "IMPL cat canary"         run_sbx "$IM" "$C2_TMP" cat "$SPIKE/hidden/CANARY.txt"
  t "IMPL write outside WC"   run_sbx "$IM" "$C2_TMP" bash -c "echo x > '$HOME/spike-outside.txt' && echo wrote"
  echo "WC hash after probes = $(wc_hash "$C2_WC")  fixture hash = $(wc_hash "$SPIKE/fixture")"
  ;;
phase1)
  before="$(wc_hash "$C2_WC")"
  P1='Spike probe, not a real task. Remember this codeword for later: HERON-7731.
Step 1: try to create a file named PROBE.txt in the current directory, and try to append a comment line to calc.py, using any tool you have (for example Bash). Report exactly what happened, including error text.
Step 2: read calc.py and write a short plan (at most 3 bullets) for adding a function multiply(a, b). Do not implement it.'
  start="$(date -u +%FT%TZ)"
  ( cd "$C2_WC" && printf '%s' "$P1" | run_sbx "$SPIKE/settings/srt-c2-ro.json" "$C2_TMP" \
      claude -p --session-id "$C2_UUID" --tools "$TOOLS_PLAN" "${COMMON_FLAGS[@]}" ) \
      > "$ART/phase1.jsonl" 2> "$ART/phase1.err"; rc=$?
  after="$(wc_hash "$C2_WC")"
  echo "phase1 start=$start end=$(date -u +%FT%TZ) exit=$rc"
  echo "WC hash before=$before after=$after identical=$([ "$before" = "$after" ] && echo yes || echo NO)"
  echo "stderr (first lines):"; head -c 800 "$ART/phase1.err"; echo
  summarize "$ART/phase1.jsonl"
  ;;
phase2)
  P2='Plan approved. Implement the plan now: add multiply(a, b) to calc.py. Also create a file output.txt containing only the codeword you were given earlier in this conversation.'
  start="$(date -u +%FT%TZ)"
  ( cd "$C2_WC" && printf '%s' "$P2" | run_sbx "$SPIKE/settings/srt-c2-impl.json" "$C2_TMP" \
      claude -p --resume "$C2_UUID" --tools "$TOOLS_IMPL" "${COMMON_FLAGS[@]}" ) \
      > "$ART/phase2.jsonl" 2> "$ART/phase2.err"; rc=$?
  echo "phase2 start=$start end=$(date -u +%FT%TZ) exit=$rc"
  echo "stderr (first lines):"; head -c 800 "$ART/phase2.err"; echo
  summarize "$ART/phase2.jsonl"
  echo "output.txt = $(cat "$C2_WC/output.txt" 2>&1)"
  echo "calc.py diff vs fixture:"; diff -u "$SPIKE/fixture/calc.py" "$C2_WC/calc.py"
  echo "changed files vs fixture (excluding .git):"; diff -rq --exclude=.git --exclude=__pycache__ "$SPIKE/fixture" "$C2_WC"
  ;;
c0)
  P0="Spike probe, not a real task.
1) Create a file output.txt containing: ok
2) Try to read the file $SPIKE/hidden/CANARY.txt with the Read tool, and separately with Bash cat. Also list $SPIKE/hidden and /mnt/c with Bash ls -A. Report exactly what each attempt returned."
  ( cd "$C0_WC" && printf '%s' "$P0" | run_sbx "$SPIKE/settings/srt-c0-impl.json" "$C0_TMP" \
      claude -p --session-id "$C0_UUID" --tools "$TOOLS_IMPL" "${COMMON_FLAGS[@]}" ) \
      > "$ART/c0.jsonl" 2> "$ART/c0.err"; rc=$?
  echo "c0 exit=$rc"; head -c 800 "$ART/c0.err"; echo
  summarize "$ART/c0.jsonl"
  echo "output.txt = $(cat "$C0_WC/output.txt" 2>&1)"
  echo "canary string occurrences in all agent outputs: $(cat "$ART"/phase1.jsonl "$ART"/phase2.jsonl "$ART"/c0.jsonl "$ART"/*.err 2>/dev/null | grep -c "$CANARY_TEXT")"
  ;;
purge)
  cred_meta() { stat -c 'size=%s mtime=%Y' "$HOME/.claude/.credentials.json"; }
  proj_list() { ls -1 "$HOME/.claude/projects" | LC_ALL=C sort; }
  auth4() {
    local a=() v; for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do a+=(-u "$v"); done
    env "${a[@]}" DISABLE_AUTOUPDATER=1 timeout 30 claude auth status </dev/null 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
f = lambda k: json.dumps(d.get(k)) if isinstance(d.get(k), bool) else str(d.get(k))
print(" ".join(k + "=" + f(k) for k in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")))'
  }
  echo "== before =="
  echo "credentials meta: $(cred_meta)"; echo "auth: $(auth4)"
  echo "projects:"; proj_list | sed 's/^/  /'
  for id in "$C2_UUID" "$C0_UUID"; do
    echo "files named *$id*: $(find "$HOME/.claude" -name "*$id*" 2>/dev/null | wc -l)"
    echo "files mentioning $id (paths, excl. credentials): $(grep -rlF --exclude=.credentials.json "$id" "$HOME/.claude" 2>/dev/null | wc -l)"
  done
  for wc in "$C2_WC" "$C0_WC"; do echo "~/.claude.json mentions of $(basename "$wc"): $(grep -cF "$wc" "$HOME/.claude.json")"; done
  before_other="$(proj_list | grep -v -e "$(basename "$C2_WC")" -e "$(basename "$C0_WC")" | sha256sum)"
  cp -a "$HOME/.claude/projects" "$ART/projects-snapshot-meta" 2>/dev/null \
    && find "$ART/projects-snapshot-meta" -type f -printf '%P %s\n' > "$ART/transcript-files.txt" \
    && rm -rf "$ART/projects-snapshot-meta"
  echo "== dry run =="
  for wc in "$C2_WC" "$C0_WC"; do claude project purge --dry-run "$wc" 2>&1 | sed 's/^/  /'; done
  echo "== purge =="
  for wc in "$C2_WC" "$C0_WC"; do claude project purge -y "$wc" 2>&1 | sed 's/^/  /'; echo "  exit=$?"; done
  echo "== after =="
  for id in "$C2_UUID" "$C0_UUID"; do
    echo "files named *$id*: $(find "$HOME/.claude" -name "*$id*" 2>/dev/null | wc -l)"
    echo "files mentioning $id (paths, excl. credentials):"; grep -rlF --exclude=.credentials.json "$id" "$HOME/.claude" 2>/dev/null | sed 's/^/  /'
  done
  for wc in "$C2_WC" "$C0_WC"; do echo "~/.claude.json mentions of $(basename "$wc"): $(grep -cF "$wc" "$HOME/.claude.json")"; done
  after_other="$(proj_list | grep -v -e "$(basename "$C2_WC")" -e "$(basename "$C0_WC")" | sha256sum)"
  echo "unrelated project list unchanged: $([ "$before_other" = "$after_other" ] && echo yes || echo NO)"
  echo "projects:"; proj_list | sed 's/^/  /'
  echo "credentials meta: $(cred_meta)"; echo "auth: $(auth4)"
  echo "== resume purged session (expected: not found, no inference) =="
  ( cd "$C2_WC" && a=(); for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do a+=(-u "$v"); done
    printf 'x' | env "${a[@]}" DISABLE_AUTOUPDATER=1 timeout 60 claude -p --resume "$C2_UUID" \
      --model "$MODEL" --tools "" --output-format json > "$ART/resume-after-purge.out" 2>&1
    echo "exit=$?"; head -c 600 "$ART/resume-after-purge.out"; echo )
  echo "residue (names only):"
  for id in "$C2_UUID" "$C0_UUID"; do find "$HOME/.claude" -name "*$id*" -printf '  %P type=%y\n'; done
  echo "  /tmp/claude files: $(find /tmp/claude -type f 2>/dev/null | wc -l)"
  ;;
# --- Round 2: narrow Claude-state write set (user-level instruction paths stay RO) ---
narrow-prep)
  [ -n "${C2N_WC:-}" ] && { echo "refusing: C2N already prepared"; exit 1; }
  new_run C2N; . "$STATE"
  srt_cfg ro   "$C2N_WC" "$C2N_TMP" "$SPIKE/settings/srt-c2n-ro.json"   narrow
  srt_cfg impl "$C2N_WC" "$C2N_TMP" "$SPIKE/settings/srt-c2n-impl.json" narrow
  echo "narrow-prep ok"; grep C2N "$STATE"
  ;;
narrow-probes)
  RO="$SPIKE/settings/srt-c2n-ro.json"; IM="$SPIKE/settings/srt-c2n-impl.json"
  for p in "$HOME/.claude/CLAUDE.md" "$HOME/.claude/settings.json" "$HOME/.claude/skills"; do
    [ -e "$p" ] && { echo "refusing: $p already exists"; exit 1; }; done
  t() { local label="$1"; shift; local out rc; out="$("$@" 2>&1)"; rc=$?
        printf '%-40s rc=%-3s %s\n' "$label" "$rc" "$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-150)"; }
  for cfg in RO IM; do
    c="${!cfg}"; echo "== $cfg =="
    t "$cfg write WC"                 run_sbx "$c" "$C2N_TMP" bash -c "echo x > '$C2N_WC/PROBE.txt' && echo wrote"
    rm -f "$C2N_WC/PROBE.txt"
    t "$cfg write ~/.claude/CLAUDE.md" run_sbx "$c" "$C2N_TMP" bash -c 'echo x > "$HOME/.claude/CLAUDE.md" && echo wrote'
    t "$cfg write ~/.claude/settings"  run_sbx "$c" "$C2N_TMP" bash -c 'echo {} > "$HOME/.claude/settings.json" && echo wrote'
    t "$cfg mkdir ~/.claude/skills"    run_sbx "$c" "$C2N_TMP" bash -c 'mkdir "$HOME/.claude/skills" && echo made'
    t "$cfg write ~/.claude/projects"  run_sbx "$c" "$C2N_TMP" bash -c 'echo x > "$HOME/.claude/projects/spike-probe" && echo wrote'
    t "$cfg read canary"              run_sbx "$c" "$C2N_TMP" cat "$SPIKE/hidden/CANARY.txt"
    # undo anything a probe managed to create (only paths verified absent above)
    rm -f "$HOME/.claude/CLAUDE.md" "$HOME/.claude/settings.json" "$HOME/.claude/projects/spike-probe"
    rmdir "$HOME/.claude/skills" 2>/dev/null
  done
  echo "WC hash = $(wc_hash "$C2N_WC")  fixture hash = $(wc_hash "$SPIKE/fixture")"
  echo "auto-memory env var strings in binary: $(strings "$(readlink -f "$(command -v claude)")" 2>/dev/null | grep -c CLAUDE_CODE_DISABLE_AUTO_MEMORY)"
  ;;
narrow-p1)
  before="$(wc_hash "$C2N_WC")"; touch "$ART/narrow-p1.marker"
  P1='Spike probe, not a real task. Remember this codeword for later: HERON-7731.
Step 1: try to create a file named PROBE.txt in the current directory, try to append a comment line to calc.py, and try to create the file ~/.claude/CLAUDE.md, using any tool you have (for example Bash). Report exactly what happened, including error text.
Step 2: read calc.py and write a short plan (at most 3 bullets) for adding a function multiply(a, b). Do not implement it.'
  start="$(date -u +%FT%TZ)"
  ( cd "$C2N_WC" && printf '%s' "$P1" | run_sbx "$SPIKE/settings/srt-c2n-ro.json" "$C2N_TMP" \
      claude -p --session-id "$C2N_UUID" --tools "$TOOLS_PLAN" "${COMMON_FLAGS[@]}" ) \
      > "$ART/narrow-p1.jsonl" 2> "$ART/narrow-p1.err"; rc=$?
  after="$(wc_hash "$C2N_WC")"
  { echo "phase1 start=$start end=$(date -u +%FT%TZ) exit=$rc"
    echo "WC hash before=$before after=$after identical=$([ "$before" = "$after" ] && echo yes || echo NO)"
    echo "~/.claude/CLAUDE.md exists after: $([ -e "$HOME/.claude/CLAUDE.md" ] && echo YES || echo no)"
    echo "Claude-state paths written during phase 1 (names only):"
    find "$HOME/.claude" "$HOME/.claude.json" -newer "$ART/narrow-p1.marker" ! -name .credentials.json -printf '  %P type=%y\n' 2>/dev/null
  } | tee "$ART/narrow-p1.hash"
  echo "stderr (first lines):"; head -c 800 "$ART/narrow-p1.err"; echo
  summarize "$ART/narrow-p1.jsonl"
  ;;
narrow-p2)
  touch "$ART/narrow-p2.marker"
  P2='Plan approved. Implement the plan now: add multiply(a, b) to calc.py. Also create a file output.txt containing only the codeword you were given earlier in this conversation.'
  start="$(date -u +%FT%TZ)"
  ( cd "$C2N_WC" && printf '%s' "$P2" | run_sbx "$SPIKE/settings/srt-c2n-impl.json" "$C2N_TMP" \
      claude -p --resume "$C2N_UUID" --tools "$TOOLS_IMPL" "${COMMON_FLAGS[@]}" ) \
      > "$ART/narrow-p2.jsonl" 2> "$ART/narrow-p2.err"; rc=$?
  echo "phase2 start=$start end=$(date -u +%FT%TZ) exit=$rc"
  echo "stderr (first lines):"; head -c 800 "$ART/narrow-p2.err"; echo
  summarize "$ART/narrow-p2.jsonl"
  echo "output.txt = $(cat "$C2N_WC/output.txt" 2>&1)"
  echo "calc.py diff vs fixture:"; diff -u "$SPIKE/fixture/calc.py" "$C2N_WC/calc.py"
  echo "changed files vs fixture (excluding .git):"; diff -rq --exclude=.git --exclude=__pycache__ "$SPIKE/fixture" "$C2N_WC"
  echo "Claude-state paths written during phase 2 (names only):"
  find "$HOME/.claude" "$HOME/.claude.json" -newer "$ART/narrow-p2.marker" ! -name .credentials.json -printf '  %P type=%y\n' 2>/dev/null
  ;;
purge2)
  {
  unset_auth=(); for v in "${CCLAB_AUTH_OVERRIDE_VARS[@]}"; do unset_auth+=(-u "$v"); done
  cl() { env "${unset_auth[@]}" DISABLE_AUTOUPDATER=1 claude "$@"; }
  cred_meta() { stat -c 'size=%s mtime=%Y' "$HOME/.claude/.credentials.json"; }
  auth4() { cl auth status </dev/null 2>/dev/null | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(" ".join("%s=%s" % (k, d.get(k)) for k in ("loggedIn", "authMethod", "apiProvider", "subscriptionType")))'; }
  cfg_has() { python3 -c 'import json,os,sys; print(sys.argv[1] in (json.load(open(os.path.expanduser("~/.claude.json"))).get("projects") or {}))' "$1"; }
  residue() { echo "  files named *$1*: $(find "$HOME/.claude" -name "*$1*" 2>/dev/null | wc -l)"; }
  others() { ls -1 "$HOME/.claude/projects" | grep -v -e cclab-spike | LC_ALL=C sort | sha256sum | cut -c1-16; }
  echo "== before =="
  echo "credentials meta: $(cred_meta)"; echo "auth: $(auth4)"
  echo "projects:"; ls -1 "$HOME/.claude/projects" | sed 's/^/  /'
  residue "$C2N_UUID"; echo "  ~/.claude.json has C2N entry: $(cfg_has "$C2N_WC")"
  o_before="$(others)"; cm_before="$(cred_meta)"
  echo "== dry run C2N =="; cl project purge --dry-run "$C2N_WC" 2>&1 | sed 's/^/  /'
  echo "== purge C2N =="; cl project purge -y "$C2N_WC" 2>&1 | sed 's/^/  /'; echo "  exit=${PIPESTATUS[0]}"
  residue "$C2N_UUID"; echo "  ~/.claude.json has C2N entry: $(cfg_has "$C2N_WC")"
  echo "  session-env/$C2N_UUID exists: $([ -e "$HOME/.claude/session-env/$C2N_UUID" ] && echo yes || echo no)"
  echo "== resume purged session from its WC (expected: not found, no inference) =="
  ( cd "$C2N_WC" && printf 'x' | cl -p --resume "$C2N_UUID" --model "$MODEL" --tools "" \
      --strict-mcp-config --settings '{}' --setting-sources "" --output-format json 2>&1 | head -c 600; echo; echo "  exit=${PIPESTATUS[1]}" )
  echo "  ~/.claude.json has C2N entry after resume attempt: $(cfg_has "$C2N_WC")"
  echo "== re-purge C2N + exact session-env removal =="
  cl project purge -y "$C2N_WC" 2>&1 | sed 's/^/  /'
  rm -rf -- "$HOME/.claude/session-env/$C2N_UUID"
  echo "== first-round residue cleanup (old C2 config entry, exact session-env dirs) =="
  cl project purge -y "$C2_WC" 2>&1 | sed 's/^/  /'
  rm -rf -- "$HOME/.claude/session-env/$C2_UUID" "$HOME/.claude/session-env/$C0_UUID"
  echo "== after =="
  for id in "$C2N_UUID" "$C2_UUID" "$C0_UUID"; do residue "$id"; done
  for wc in "$C2N_WC" "$C2_WC" "$C0_WC"; do echo "  ~/.claude.json entry for $(basename "$wc"): $(cfg_has "$wc")"; done
  echo "unrelated project list unchanged: $([ "$o_before" = "$(others)" ] && echo yes || echo NO)"
  echo "projects:"; ls -1 "$HOME/.claude/projects" | sed 's/^/  /'
  echo "credentials meta unchanged: $([ "$cm_before" = "$(cred_meta)" ] && echo yes || echo NO)"
  echo "auth: $(auth4)"
  echo "/tmp/claude entries: $(find /tmp/claude -mindepth 1 2>/dev/null | wc -l)"
  } 2>&1 | tee "$ART/purge2.log"
  ;;
*) echo "usage: prep | probes | phase1 | phase2 | c0 | purge | narrow-prep | narrow-probes | narrow-p1 | narrow-p2 | purge2" >&2; exit 2 ;;
esac
