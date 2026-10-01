#!/usr/bin/env bash
# CodeAgent ConfigLab - RETIRED. Kept only so old references fail loudly.
#
# This script used to store a CLAUDE_CODE_OAUTH_TOKEN printed by
# 'claude setup-token' in ~/.cclab-token, for the runner to source. That path was
# tested with two separately generated tokens: 'claude auth status' reported
# local OAuth state, but every real 'claude -p' failed with
# "401 Invalid bearer token". It is not used.
#
# Verified path instead: cclab logs in through Claude Code's normal Claude.ai
# login flow; the state persists under cclab's HOME and headless 'claude -p' uses
# it, with every auth override variable unset (claude_sanitized in common.sh).
#
# This stub stores nothing and never reads, moves or deletes an existing
# ~/.cclab-token.
set -euo pipefail

cat >&2 <<'MSG'
FATAL: setup/15-store-token.sh is retired - the manual OAuth-token approach was
       disproven (real requests failed with "401 Invalid bearer token").
       Do not run 'claude setup-token' and do not source ~/.cclab-token.

       Instead, as cclab in a login shell:
         1) start 'claude' interactively and complete the normal Claude.ai login
            (/login) with the existing Pro account
         2) bash setup/20-verify.sh
       If ~/.cclab-token still exists, remove it yourself; 20-verify reports it.
MSG
exit 1
