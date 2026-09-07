# SEC-2 / SEC-3 research and critique — reference material, not shipped code

**Nothing in this directory is wired into Halbert. Do not import it.**

`containment.py` and `test_path_containment.py.txt` were written by a research
agent directly into `halbert_core/` during the 2026-09-07 investigation. They
were moved here because they are a *proposal*, not a decision: nothing imports
the module, it has not been reviewed against the critiques in this same
directory, and leaving it under `halbert_core/tests/` meant its 21 tests were
being collected into the suite count for code that does not run in production.

The test file carries a `.txt` suffix for the same reason — so pytest does not
collect it.

## What is here

| File | What it is |
|---|---|
| `classifier-shape.md` | Measured recognition rates for the command classifier against a corpus mined from the tree. The numbers that killed the plan's `unknown → HIGH` proposal. |
| `seatbelt.md` | A proposed macOS seatbelt profile, tested live on an Apple Silicon host. |
| `sandbox-fail-direction.md` | What should happen when the platform sandbox is missing; an inventory of permissive fallthroughs. |
| `resolve-once.md` | The TOCTOU-safe path primitive — why `realpath` loses on APFS, and what to use instead. |
| `privileged-write.md` | Replacing the two bash root helpers; the macOS question (there is no polkit). |
| `chokepoint.md` | Every path from a caller or the model to process execution or a filesystem write. |
| `critic-over-correction.md` | Where the six proposals would fire on ordinary use. **Found the pager escape.** |
| `critic-still-open.md` | Attacker pass on the proposals. Found five live bypasses in the classifier patch. |
| `critic-buildability.md` | Measured landing cost against the full suite. **Found that `diskutil list` returns rc=0 and zero bytes under the proposed seatbelt profile.** |
| `containment.py` | The proposed path primitive. Correctly rejects `realpath` (on APFS `/etc/PASSWD` and `/etc/passwd` are one inode with two spellings), returns a descriptor, makes `__fspath__` raise. **Known defect: `write_bytes` is `ftruncate(0)` then `write` — a crash mid-write on `sshd_config` leaves it empty.** Needs an atomic-replace method before use. |

## Why none of it landed

Read `.handoff/REVIEW-PACKET-12-SECURITY-REMEDIATION-2026-09-07.md` §5. In short:

- The **classifier** proposal has five live defects, including a `basename`-keyed
  identity check (the same mistake the audit calls arbitrary root execution in
  `halbert-exec-helper`) and a quoting bypass that skips the credential tier.
- The **seatbelt** proposal fails silently, which is disqualifying for a machine
  the agent is supposed to observe.
- The **path primitive** cannot be dropped into `editor.py`: on macOS it needs a
  root allowlist (a product decision), and `ResolvedPath` cannot be threaded
  through code that uses the path as a string in six places.

Two findings from this work *were* acted on, because they were live in the tree
and cheap to close — the pager escape and the credential-read gate, both in
commit `79dca611`.
