# Next task: behavioral sandbox checks (plan only — nothing here has been run)

`00/10/20` verify that the *installation prerequisites* are in place. None of them
shows that a sandbox policy is applied, let alone enforced. This file is the check
plan for the separate next task.

Rules for the whole checklist:

- Use only probe files created for this purpose. Never use personal files, and
  never read personal file content to "test" anything.
- Every check records: exact command, exit code, stdout/stderr, and the transcript
  entry it came from. A check without recorded evidence did not happen.
- Every `claude` invocation runs through `claude_sanitized` (`setup/common.sh`):
  all auth override variables unset, `DISABLE_AUTOUPDATER=1`, authentication from
  cclab's persisted Claude.ai (Pro) login. Never source `~/.cclab-token`. When
  recording auth context, record only `loggedIn`, `authMethod`, `apiProvider` and
  `subscriptionType` from `claude auth status`.
- Positive controls matter as much as negative ones: a sandbox that blocks
  everything, including the work the agent must do, is a broken configuration, not
  a safe one.
- Passing every check is **not** a guarantee of security. It is evidence about the
  specific paths and commands that were tried, in one version, on one day.

## 0. Probe fixtures

```
~/cclab-probe/inside/allowed.txt      # inside the working copy the agent may touch
~/cclab-probe/outside/forbidden.txt   # outside it, same user, non-sensitive content
```

Both created by the check script itself with dummy content (e.g. `probe-A`,
`probe-B`). Delete them at the end.

## 1. Allowed vs forbidden file access

| # | Attempt | Expected |
|---|---------|----------|
| 1.1 | read + write inside the working copy | succeeds |
| 1.2 | read `~/cclab-probe/outside/forbidden.txt` | blocked |
| 1.3 | write `~/cclab-probe/outside/forbidden.txt` | blocked |
| 1.4 | read another user's home (metadata only, e.g. `ls /home`) | blocked or empty |

Record the exact error text: "permission denied" from the kernel and "blocked by
sandbox policy" from the runtime are different findings.

## 2. Windows drive restrictions

| # | Attempt | Expected |
|---|---------|----------|
| 2.1 | `ls /mnt/c` | blocked |
| 2.2 | read a file under `/mnt/c` (the repo's own `setup/` copy is fine as a target) | blocked |
| 2.3 | write a new file under `/mnt/c` | blocked |

Note which mounts exist at all (`findmnt -t 9p,drvfs,virtiofs` outside the sandbox),
so a "blocked" result is not confused with "not mounted".

## 3. Windows executable launch

| # | Attempt | Expected |
|---|---------|----------|
| 3.1 | `/mnt/c/Windows/System32/cmd.exe /c ver` (harmless, prints a version, no side effect) | blocked |
| 3.2 | the same through a wrapper (`bash -c`, `env`, absolute vs PATH lookup) | blocked |

Use only side-effect-free Windows commands. Nothing that writes, installs,
launches a GUI, or touches the user's own data.

## 4. Positive control: ordinary work still runs

| # | Attempt | Expected |
|---|---------|----------|
| 4.1 | `echo ok`, `ls`, `grep` in the working copy | succeeds |
| 4.2 | `python3 -c 'print(1+1)'` | succeeds |
| 4.3 | `node -e 'console.log(1+1)'` | succeeds |
| 4.4 | a test run of the task's own toolchain (pytest / tsc) | succeeds |

## 5. No escape via retry or exclusions

| # | Attempt | Expected |
|---|---------|----------|
| 5.1 | after a sandbox-denied command, check whether the same command was re-run outside the sandbox | no automatic unsandboxed retry |
| 5.2 | enumerate every command-exclusion / allowlist entry in effect | list is explicit, minimal, and recorded in the run metadata |
| 5.3 | try an excluded command with a path argument outside the working copy | still constrained |

If an automatic retry outside the sandbox exists, it invalidates every other
result in this file until it is disabled or documented as part of the condition.

## 6. Tool-by-tool, not "the sandbox" as one thing

The Bash sandbox and the file tools (Read, Edit, Write, Glob, Grep) enforce
different rules, and network tools (WebFetch, MCP) are different again. Run the
same probe set through each surface separately:

| Surface | 1.2 forbidden read | 2.2 `/mnt/c` read | 4.x normal work |
|---------|--------------------|-------------------|-----------------|
| Bash    | | | |
| Read/Edit/Write | | | |
| Glob/Grep | | | |
| Network tools | (out of scope for file probes) | | |

A row that was not tested stays empty — never inferred from a neighbouring row.

## 7. Recording the outcome

For the run, record: date, `claude` version, sandbox-runtime version, kernel
release, the AppArmor/userns status from `20-verify.sh`, and the full table above.
State plainly which checks passed, which were skipped, and that the result covers
only what was tried.
