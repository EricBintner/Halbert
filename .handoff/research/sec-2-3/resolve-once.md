## 1. What this machine actually has

```
$ arch -arm64 /Volumes/4TB-BAD/Halbert/.venv/bin/python -c '...'
python: 3.10.9 platform: macOS-26.5.1-arm64-arm-64bit arm64
os.O_NOFOLLOW: 0x100        os.O_NOFOLLOW_ANY: 0x20000000
os.O_RESOLVE_BENEATH: ABSENT  os.O_TMPFILE: ABSENT  os.O_PATH: ABSENT
os.openat2: False           RESOLVE_* consts in os: []
```

`O_NOFOLLOW` yes; `openat2` and every `RESOLVE_*` constant absent. Darwin's `O_NOFOLLOW_ANY` (macOS 12+) *is* exposed by Python here, and it works — but it is unusable for us:

```
/etc is symlink: True -> /private/etc      /var -> /private/var   /tmp -> /private/tmp
O_NOFOLLOW_ANY OK   /private/tmp/tmphnf8ung3/real/target
O_NOFOLLOW_ANY FAIL /private/tmp/tmphnf8ung3/link/target ELOOP
```

`/etc` is itself a symlink, so `O_NOFOLLOW_ANY` on any `/etc/...` path fails before it starts. It has no notion of a root either — it is all-or-nothing on the whole path.

Two more measured facts drive the design:

```
openat+O_NOFOLLOW OK   real/target
openat+O_NOFOLLOW OK   link/target      <-- guards only the FINAL component
```

```
/etc/passwd         realpath=/private/etc/passwd   dev=16777232 ino=842850529
/ETC/PASSWD         realpath=/private/etc/PASSWD   dev=16777232 ino=842850529
NFC bytes: b'caf\xc3\xa9'   NFD bytes: b'cafe\xcc\x81'
NFD name resolves to same file: True
realpath(NFD) -> b'/private/tmp/.../cafe\xcc\x81'
```

**`realpath` is not a canonical form on APFS.** Two different strings, one inode. It folds `..` and symlinks; it does not fold case or Unicode form. Any gate that compares `realpath(p)` against a string set is defeated by holding shift — including `ToolSafetyFramework._classify_write` at `halbert_core/halbert_core/tools/safety.py:678-687`, which does `path.startswith(sensitive) or sensitive in path` on the raw argument.

**On Linux I tested nothing.** `docker info` → `Cannot connect to the Docker daemon`; there is no Linux available here. Everything I say about `openat2` is from documentation, not measurement.

## 2. The decision

**Option (d), ending in (b): a component-wise `openat` walk with `O_NOFOLLOW`, returning the descriptor; identity from `fstat`, never from a string.**

- **(a) realpath-then-open is dead on arrival.** It cannot express identity on APFS (above), and it still opens by *string* afterwards — two lookups, so the race is untouched. It is the bug with a longer name.
- **(b) alone** closes the string gap but cannot express "beneath root" without a walk; on macOS there is no way to ask the kernel whether an fd is under a directory except walking `..` upward, which races.
- **(c) openat2/RESOLVE_BENEATH is the better kernel primitive and I am not recommending it.** It costs no dependency — a `ctypes` raw syscall is permitted under the Subtractive Contract — but it is Linux-only, kernel 5.6+, has no CPython binding, and would put the containment guarantee on the one branch that cannot be exercised on the machine the developer is sitting at. The walk gives the same guarantee everywhere and is *one* code path to test. This is where I disagree with nothing in the plan except emphasis: the plan says "realpath, or openat2 … obtained ONCE". The "obtained once" half is exactly right and is the whole insight; the "realpath" half does not survive contact with APFS.

Residual races, stated precisely: **the walk is not atomic.** An attacker who can write inside the root can rename directories between steps. What they cannot do is make us *leave* — each step is anchored to a descriptor we already hold, and a descriptor names an inode, so a rename cannot relocate our anchor. What they *can* do is rename a subtree in from outside; we then descend into it legitimately. Containment holds against escape, not against an attacker who already writes inside the root. TOCTOU is **narrowed to that**, not fixed.

## 3. The primitive

`/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/halbert_core/halbert_core/utils/containment.py`

```python
def resolve_once(path, *, root, for_write=False, create=False,
                 mode=0o600) -> ResolvedPath
def resolve_under_any(path, roots, **kw) -> ResolvedPath   # allowlist = roots, not prefixes
class PathRefusal(Exception):  # .reason: traversal|symlink|tilde|outside_root|
                               # null_byte|hardlink|not_regular|missing|denied|...
```

It returns **an open descriptor**, and the API makes the second string physically unavailable:

```python
    def __fspath__(self):
        raise PathRefusal(
            "a ResolvedPath is a descriptor, not a name; use .fd",
            reason="reopen_by_name",
        )
```

`open(resolved)` and `os.fspath(resolved)` raise. An API that hands back a validated string and trusts the caller has solved nothing, so this one refuses to be a string. `ResolvedPath` carries `fd`, `st_dev`, `st_ino`, `st_nlink`, `created`, and `on_disk` — the kernel's own name for the descriptor, for audit lines only. On Darwin that is `fcntl(fd, F_GETPATH)`, verified to report the *true* on-disk spelling where `realpath` echoed the caller's:

```
opened as .../passwd ; F_GETPATH says: /private/tmp/tmpav1qk1ae/root/PassWd
```

The walk, in full:

```python
    cur = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    for comp in parts[:-1]:
        nxt = os.open(comp, _OPEN_DIR, dir_fd=cur)   # O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC
        os.close(cur); cur = nxt
```

`..` never enters `parts` — it is refused in `_components`, never cancelled against a prior component. A walk that honours `..` is a walk that can be talked out of its root.

## 4. The awkward cases

**Create.** `O_CREAT|O_EXCL|O_NOFOLLOW` on the parent's fd, one atomic step. A symlink planted at the target loses with `EEXIST`; we then retry without `O_CREAT` and `O_NOFOLLOW` refuses it. This is why I did not adopt the plan's `O_TMPFILE+linkat`: `os.O_TMPFILE` is **ABSENT** on this platform (output above), so it cannot be the primitive — at best a Linux-only optimisation, which is the branch problem again.

**Symlinked parent.** Refused. But the errno is a platform trap I had to measure:

```
ENOTDIR   symlink-to-dir + O_DIRECTORY|O_NOFOLLOW
ELOOP     symlink-to-dir + O_NOFOLLOW only
ENOTDIR   regular file  + O_DIRECTORY|O_NOFOLLOW
```

Darwin reports `ENOTDIR` for a symlinked directory — indistinguishable from a plain file. Containment is identical either way, but the *reason an operator reads* is not, so `_refusal` does an `lstat(comp, dir_fd=...)` to say which it was. My first draft got this wrong and a test caught it.

**Tilde.** Never expanded, and a leading `~` is refused (`reason="tilde"`). That is precisely the `write_file` split — gate reads the raw argument, handler expands — collapsed by making the unexpanded form unrepresentable.

**Mount crossing.** Not detected, and deliberately not made a hard refusal: on this machine `/` is `disk3s1s1` and `/System/Volumes/Data` is `disk3s5`, so a same-device rule would reject legitimate paths. `st_dev` is *reported* on `ResolvedPath` for policy to weigh.

**Case-insensitivity (APFS default) and NFD.** Containment is unaffected — `nginx/NGINX.CONF` is still beneath the root. What breaks is any *policy* that names a file by string. The primitive's answer is that identity is `(st_dev, st_ino)`; both tests below ran (no skips) and passed on this filesystem.

**Hardlinks — the one thing a component walk genuinely cannot see.** A hardlink inside `/etc` to `/root/.ssh/authorized_keys` is truly beneath the root and truly also outside it. No path-resolution primitive can detect this, so for writes `resolve_once` refuses `st_nlink > 1` outright. Also refused for writes: anything not `S_ISREG`, opened `O_NONBLOCK` first so a FIFO planted at the target cannot park the writer before we look at it.

## 5. The exploits, as tests

`/Volumes/4TB-BAD/Halbert/.claude/worktrees/sec-1-one-door/halbert_core/tests/test_path_containment.py` — **21 passed, 0 skipped**.

The helper's entire check, and what it lets through:

```
$ bash prefix.sh
helper ACCEPTS /etc/../root/.ssh/authorized_keys (matched prefix /etc/)
```

```python
def test_dotdot_escape_is_refused(root):
    attack = root + "/../root/.ssh/authorized_keys"
    assert attack.startswith(root + "/")        # the helper's whole test
    assert _refusal(resolve_once, attack, root=root).reason == "traversal"

def test_symlinked_parent_is_refused(root):
    os.symlink(os.path.join(root, "..", "root", ".ssh"),
               os.path.join(root, "keys"))
    assert _refusal(resolve_once, "keys/authorized_keys", root=root).reason == "symlink"

def test_tilde_is_refused_never_expanded(root):
    assert _refusal(resolve_once, "~/.ssh/authorized_keys", root=root).reason == "tilde"

def test_relative_path_is_anchored_to_root_not_cwd(root, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path / "root" / ".ssh")
    assert os.path.exists("authorized_keys")    # cwd really does hold it
    assert _refusal(resolve_once, "authorized_keys", root=root).reason == "missing"

def test_create_over_a_planted_symlink_does_not_follow_it(root, tmp_path):
    target = tmp_path / "root" / ".ssh" / "authorized_keys"
    os.symlink(str(target), os.path.join(root, "nginx", "new.conf"))
    assert _refusal(resolve_once, "nginx/new.conf", root=root,
                    for_write=True, create=True).reason == "symlink"
    assert target.read_text() == "ssh-rsa MINE\n"   # untouched
```

Plus `test_resolved_path_cannot_be_used_as_a_path` (`open(r)` raises `reopen_by_name`), `test_the_root_itself_may_be_a_symlink` (the `/etc → /private/etc` case must keep working), the hardlink and FIFO refusals, and the two filesystem-ambiguity tests.

## 6. Residual risk, honestly

1. **The walk is not atomic.** An attacker with write access *inside* the root can rename subtrees between steps and cause us to descend into content they placed. We cannot be walked out of the root; we can be walked into a surprise within it. `openat2(RESOLVE_BENEATH)` would not fix this either — it also resolves against whatever is there.
2. **Linux is untested.** No container runtime on this host. The walk uses only `os.open(dir_fd=...)` and `O_NOFOLLOW`, both POSIX, so I expect it to hold; the `/proc/self/fd` branch of `_true_name` is unexercised and affects audit text only, never containment.
3. **Hardlinks are refused, not resolved.** A legitimate hardlinked config in `/etc` will be rejected for writing. I judged that the right trade; it is a behaviour change worth naming.
4. **The root is opened by name and trusted.** Necessarily — `/etc` is a symlink here. Anyone who can replace `/etc` itself has already won.
5. **String pre-filter for absolute inputs.** An absolute path must literally start with the root, so `/private/etc/nginx.conf` is refused under `root="/etc"` though it is the same directory. A false negative, and a safe one; there are no users to migrate.
6. **This closes the primitive, not the seventeen findings.** `resolve_once` is unused so far. The findings die when the call sites adopt it: `dashboard/routes/editor.py:339` and `:379` (`path.startswith('/')`), `read_file_content`/`write_file_content` at `:182`/`:236` including the `sudo -n tee` fallbacks at `:268-271` that skip the helper's allowlist entirely, `tools/safety.py:678`, and both bash helpers — whose prefix and basename tests cannot be repaired in bash and should be replaced by argv-templated Python calling this.