# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One resolution, one file, one descriptor.

Every SEC-3 finding is the same shape: the code checks one string and opens
another. `/etc/../root/.ssh/authorized_keys` passes a prefix test and then
`cat >` writes somewhere else entirely; `~/.ssh/x` misses a gate that expands
tildes one frame later.

So the primitive here refuses to hand back a string. `resolve_once` walks the
path a component at a time, anchored to a descriptor it already holds, and
returns the open descriptor itself. There is no second lookup to race and no
second spelling to disagree with the first. `ResolvedPath.__fspath__` raises
on purpose: passing one of these to `open()` is the bug this module exists to
prevent, so it fails loudly rather than quietly reopening by name.

Not used: `realpath`. On APFS it is not a canonical form -- `/etc/PASSWD`
realpaths to `/private/etc/PASSWD`, a different string than
`/private/etc/passwd` for the same inode, and an NFD argument comes back NFD
though the directory entry is NFC. Anything that compares resolved strings is
defeated by pressing shift. Identity here is `(st_dev, st_ino)` off a
descriptor.

Not used: `openat2(RESOLVE_BENEATH)`. It is the better kernel primitive and it
is Linux-only, kernel 5.6+, has no CPython binding, and would need a ctypes
raw syscall. That costs no dependency, but it would put the containment
guarantee on a branch that cannot be exercised on a developer's Mac. The walk
below gives the same guarantee everywhere and is one thing to test.
"""
from __future__ import annotations

import errno
import os
import platform
import stat
from dataclasses import dataclass
from typing import Iterable, List, Optional

__all__ = ["PathRefusal", "ResolvedPath", "resolve_once", "resolve_under_any"]

_OPEN_DIR = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_F_GETPATH = 50  # Darwin fcntl.h


class PathRefusal(Exception):
    """Raised when a path cannot be resolved inside its root."""

    def __init__(self, message: str, *, reason: str = "refused"):
        super().__init__(message)
        self.reason = reason


@dataclass
class ResolvedPath:
    """An open descriptor and the facts about what it actually is.

    `fd` is the file. `on_disk` is what the kernel says that descriptor is
    named, which is not necessarily what the caller asked for -- it is for
    audit lines, never for reopening.
    """

    fd: int
    root: str
    requested: str
    on_disk: Optional[str]
    st_dev: int
    st_ino: int
    st_nlink: int
    created: bool

    def __fspath__(self):
        raise PathRefusal(
            "a ResolvedPath is a descriptor, not a name; use .fd",
            reason="reopen_by_name",
        )

    def __enter__(self) -> "ResolvedPath":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def read_bytes(self) -> bytes:
        os.lseek(self.fd, 0, os.SEEK_SET)
        out = bytearray()
        while True:
            chunk = os.read(self.fd, 1 << 16)
            if not chunk:
                return bytes(out)
            out += chunk

    def write_bytes(self, data: bytes) -> int:
        os.ftruncate(self.fd, 0)
        os.lseek(self.fd, 0, os.SEEK_SET)
        return os.write(self.fd, data)


def _true_name(fd: int) -> Optional[str]:
    """What the kernel calls this descriptor, or None if it will not say."""
    try:
        if platform.system() == "Darwin":
            import fcntl

            raw = fcntl.fcntl(fd, _F_GETPATH, b"\x00" * 1024)
            return raw.split(b"\x00", 1)[0].decode(errors="replace")
        return os.readlink("/proc/self/fd/%d" % fd)
    except Exception:
        return None


def _components(path: str, root: str) -> List[str]:
    if "\x00" in path:
        raise PathRefusal("path contains a null byte", reason="null_byte")
    if path.startswith("~"):
        # The gate that reads the raw argument and the handler that expands it
        # are looking at two different files. Neither side expands here.
        raise PathRefusal("unexpanded home reference: %s" % path,
                          reason="tilde")

    stem = root.rstrip("/")
    if path.startswith("/"):
        if path.rstrip("/") == stem:
            rest = ""
        elif path.startswith(stem + "/"):
            rest = path[len(stem) + 1:]
        else:
            raise PathRefusal("%s is not under %s" % (path, root),
                              reason="outside_root")
    else:
        rest = path

    parts = []
    for comp in rest.split("/"):
        if comp in ("", "."):
            continue
        if comp == "..":
            # Never resolved, never cancelled against a prior component: a
            # walk that honours `..` is a walk that can be talked out of its
            # root.
            raise PathRefusal("traversal component in %s" % path,
                              reason="traversal")
        parts.append(comp)
    return parts


def resolve_once(
    path: str,
    *,
    root: str,
    for_write: bool = False,
    create: bool = False,
    mode: int = 0o600,
) -> ResolvedPath:
    """Open `path` beneath `root`, refusing anything that leaves.

    `root` is trusted and opened by name -- on macOS `/etc` is itself a
    symlink to `/private/etc`, so refusing symlinks above the root would
    refuse the real system paths. Everything below it is walked one component
    at a time with O_NOFOLLOW, which guards the final component of each open;
    with single-component names that is every component.

    With `create`, the final step is O_CREAT|O_EXCL so a symlink planted at
    the target loses with EEXIST instead of winning.

    Raises PathRefusal. Returns an open ResolvedPath; the caller closes it.
    """
    parts = _components(path, root)

    cur = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    opened = -1
    try:
        for comp in parts[:-1]:
            try:
                nxt = os.open(comp, _OPEN_DIR, dir_fd=cur)
            except OSError as e:
                raise _refusal(e, comp, path, cur) from e
            os.close(cur)
            cur = nxt

        if not parts:
            opened, cur, created = cur, -1, False
        else:
            opened, created = _open_leaf(cur, parts[-1], path, for_write,
                                         create, mode)

        st = os.fstat(opened)
        if for_write:
            if not stat.S_ISREG(st.st_mode):
                raise PathRefusal("%s is not a regular file" % path,
                                  reason="not_regular")
            if st.st_nlink > 1:
                # The one escape a component walk cannot see: a hardlink is
                # genuinely beneath the root and genuinely also somewhere else.
                raise PathRefusal("%s has %d links" % (path, st.st_nlink),
                                  reason="hardlink")

        resolved = ResolvedPath(
            fd=opened, root=root, requested=path, on_disk=_true_name(opened),
            st_dev=st.st_dev, st_ino=st.st_ino, st_nlink=st.st_nlink,
            created=created,
        )
        opened = -1
        return resolved
    finally:
        for fd in (cur, opened):
            if fd >= 0:
                os.close(fd)


def _open_leaf(dir_fd: int, name: str, path: str, for_write: bool,
               create: bool, mode: int):
    base = os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
    flags = base | (os.O_RDWR if for_write else os.O_RDONLY)
    if create:
        try:
            fd = os.open(name, flags | os.O_CREAT | os.O_EXCL, mode,
                         dir_fd=dir_fd)
            _clear_nonblock(fd)
            return fd, True
        except FileExistsError:
            pass
        except OSError as e:
            raise _refusal(e, name, path, dir_fd) from e
    try:
        fd = os.open(name, flags, dir_fd=dir_fd)
    except OSError as e:
        raise _refusal(e, name, path, dir_fd) from e
    # O_NONBLOCK is only there so a FIFO planted at the target cannot park the
    # writer forever before we get to look at what we opened.
    _clear_nonblock(fd)
    return fd, False


def _clear_nonblock(fd: int) -> None:
    import fcntl

    fcntl.fcntl(fd, fcntl.F_SETFL,
                fcntl.fcntl(fd, fcntl.F_GETFL) & ~os.O_NONBLOCK)


def _refusal(e: OSError, comp: str, path: str, dir_fd: int) -> PathRefusal:
    # Darwin reports ENOTDIR, not ELOOP, when O_DIRECTORY|O_NOFOLLOW lands on
    # a symlink to a directory -- the same errno a plain file gives. The
    # refusal is identical either way; the reason an operator reads is not,
    # so ask the directory entry what it is rather than guessing from errno.
    if e.errno in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR):
        try:
            if stat.S_ISLNK(os.lstat(comp, dir_fd=dir_fd).st_mode):
                return PathRefusal("%r in %s is a symlink" % (comp, path),
                                   reason="symlink")
        except OSError:
            pass
    if e.errno == errno.ENOTDIR:
        return PathRefusal("%r in %s is not a directory" % (comp, path),
                           reason="not_directory")
    if e.errno in (errno.ELOOP, errno.EMLINK):
        return PathRefusal("%r in %s is a symlink" % (comp, path),
                           reason="symlink")
    if e.errno == errno.ENOENT:
        return PathRefusal("%r in %s does not exist" % (comp, path),
                           reason="missing")
    if e.errno in (errno.EACCES, errno.EPERM):
        return PathRefusal("%r in %s is not readable" % (comp, path),
                           reason="denied")
    return PathRefusal("%s: %s" % (path, e.strerror), reason="open_failed")


def resolve_under_any(path: str, roots: Iterable[str], **kw) -> ResolvedPath:
    """First root that accepts `path`. An allowlist is roots, not prefixes.

    A relative path can legitimately miss in the first root and exist in the
    second, so every root is tried. What is reported is the most specific
    refusal seen -- "is a symlink" tells an operator more than "not under".
    """
    seen = []
    for root in roots:
        try:
            return resolve_once(path, root=root, **kw)
        except PathRefusal as e:
            seen.append(e)
    for e in seen:
        if e.reason not in ("outside_root", "missing"):
            raise e
    raise seen[0] if seen else PathRefusal("no root given for %s" % path,
                                           reason="outside_root")
