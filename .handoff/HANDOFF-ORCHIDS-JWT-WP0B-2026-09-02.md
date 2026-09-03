# HANDOFF: The exposed JWT is identified — WP-0b is still open, and owner action is required

**Date:** 2026-09-02
**From:** Halley (LinuxBrain)
**To:** BrightestMinds (owns WP-0b), Haloysius (blocked by it), Halbert, SourcePrep/CoDRAG
**Closes:** the *identification* half of BrightestMinds WP-0b — "rotate the exposed
write-scoped JWT in the sibling tree", 🔴 SECURITY, the stated blocker on Haloysius going public.

---

## 1. Answer: the token was Halley's, and it was an Orchids sync credential

BrightestMinds' WP-0b says *"the sibling tree's `.git/config` has a write-scoped token
exposed."* That token has been found. It was in
`/Volumes/4TB-BAD/HumanAI/LinuxBrain/.git/config`, on a remote named `orchids-sync`.

Decoded claims (the token itself is deliberately not reproduced here):

| Field | Value |
| :--- | :--- |
| Issuer | `orchids` |
| Subject | `@pierre/storage` |
| Repo | a single Orchids-hosted mirror UUID (`65179eae-…`) |
| Scopes | **`git:read`, `git:write`** |
| Issued | 2025-12-28 |
| **Expires** | **2026-12-23** — still live |

It granted push access to one Orchids-hosted mirror of Halley. Not GitHub, not any
application surface, not the account generally. No application code ever read it.

**The remote has been removed** (`git remote remove orchids-sync`), so the token is gone
from Halley's working tree.

---

## 2. WP-0b is NOT closed — two things remain, both owner actions

### 2a. The token is still live and must be rotated

Removing the remote deleted our *copy*. It did **not** revoke the credential. It remains
valid on Orchids' platform until **2026-12-23** with `git:write` scope.

**Owner action:** revoke the token in Orchids, or delete the Orchids project outright.
Orchids was used for roughly a week and is no longer in use, so deletion is the clean
option. No agent can do this.

### 2b. A second copy exists in an archive

Auditing the zips, as WP-0b anticipated:

| Archive | Result |
| :--- | :--- |
| `HumanAI/LinuxBrain2.zip` (36 GB, 2026-01-08) | **TOKEN PRESENT** in `LinuxBrain/.git/config` |
| `HumanAI/LinuxBrain.zip` | clean |
| `HumanAI/Halley.Chat.zip`, `Halley.Chat2.zip` | clean |
| `HumanAI/CoDRAG.zip` | clean (has a `.git/config`, no token) |
| `BrightestMinds-pre-rewrite.bundle` | clean |

So the credential survives outside the repo. **Rotation is required regardless of the
archive**, but the archive is worth deleting or repacking once rotation is done.

**Until the token is rotated, WP-0b stands and Haloysius should not go public.**

---

## 3. Good news: the Orchids exposure is Halley-only

Every sibling tree was swept. Nothing to do in any of them:

| Repo | Orchids remote | Embedded creds in `.git/config` | `.orchids/` dir | Commits authored "Orchids" |
| :--- | :--- | :--- | :--- | :--- |
| **Halley (LinuxBrain)** | ~~yes~~ **removed today** | ~~1~~ **now 0** | absent | 29 |
| Halbert | none | 0 | absent | 0 |
| Haloysius | none | 0 | absent | 0 |
| BrightestMinds | none | 0 | absent | 0 |
| SourcePrep / CoDRAG | none | 0 | absent | 0 |
| CLaRa-Remembers-It-All | none | 0 | absent | 0 |

**No repo other than Halley has, or had, an embedded credential of any kind.** That also
confirms WP-0b was only ever about this one token — there is no second exposure to hunt.

### On the 29 "Orchids Desktop" commits in Halley

Between 2026-01-23 and 2026-03-30, authored under the git identity Orchids configured on
that machine. The content is ordinary Halley feature work — Flux2, video generation, the
GPU coordinator, the helper app. These are the owner's own commits wearing a tool's
name, not autonomous output. Nothing to undo; recorded so the author string is not
misread later as an agent acting alone.

---

## 4. What each repo should do

| Repo | Action |
| :--- | :--- |
| **BrightestMinds** | Update WP-0b: target identified, exposure removed from the working tree, **rotation still outstanding**. Add the `LinuxBrain2.zip` copy to the item. |
| **Haloysius** | Keep the public-launch hold until rotation is confirmed. Nothing else — Haloysius was never exposed. |
| **Halbert**, **SourcePrep/CoDRAG** | Nothing. Swept clean. Recorded here only so the question is not re-opened. |
| **Halley** | Done: remote removed. `.gitignore` keeps its `.orchids/` entry as a guard; the folder does not exist. |

---

## 5. Unrelated finding, for the record

While checking git hygiene in Halley: **18 commits on `main` still carry `Co-Authored-By`
trailers** (10 Devin, 8 Claude), dated 2026-04-08 and 2026-08-22 — despite the existence
of a `backup/before-coauthor-scrub-20260822-210323` branch, which contains **zero**
trailers. The scrub was performed somewhere and never landed on `main`.

Scrubbing would rewrite 75 commits and require a force-push, so it has been left as an
explicit decision. Halley-local; documented in
`LinuxBrain/.handoff/OPEN-GIT-HYGIENE-2026-09-02.md`.

Worth a check in the other repos on the same grounds — trailer counts found while
sweeping: Halbert 11, Haloysius 1, BrightestMinds 1, SourcePrep 2. **Haloysius' single
trailer matters most**, since that repo is intended to go public.
