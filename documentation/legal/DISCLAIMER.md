# Disclaimer of Liability — Autonomous Administrative Actions

**Effective date:** 2026-08-25
**Applies to:** Halbert core engine, Halbert Pro, the Tauri dashboard, the
`halbert` CLI, and any binary or source distribution of the Halbert project.

---

## 1. Summary

Halbert is an autonomous system administration assistant. It can read system
state, propose changes to configuration files, start and stop services, mount
and unmount volumes, edit `/etc/fstab`, modify `launchd` daemons, rewrite
network configurations, install or remove packages, and schedule recurring
tasks. **These are destructive, irreversible-in-practice operations on a live
operating system.**

Halbert is free software provided under the GNU General Public License v3.0.
Section 15 of the GPL-3.0 excludes all implied warranties and Section 16
disclaims liability for damages. This document restates and **extends** that
disclaimer to the specific operational risks introduced by an autonomous system
administration agent, because the generic GPL disclaimer does not, by itself,
clearly cover claims arising from production outages, data loss, or third-party
damage caused by autonomous actions.

> **By installing, running, or permitting Halbert to operate on any system, you
> accept full and exclusive responsibility for every action Halbert takes, and
> you release the maintainers and contributors from any and all liability.**

---

## 2. No Warranty

HALBERT IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,
INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A
PARTICULAR PURPOSE, AND NON-INFRINGEMENT. THE ENTIRE RISK AS TO THE QUALITY AND
PERFORMANCE OF HALBERT IS WITH YOU. SHOULD HALBERT PROVE DEFECTIVE, YOU ASSUME
THE COST OF ALL NECESSARY SERVICING, REPAIR, OR CORRECTION.

In no event unless required by applicable law will any maintainer, contributor,
copyright holder, or distributor of Halbert be liable to you for damages,
including any general, special, incidental, or consequential damages arising
out of the use or inability to use Halbert (including but not limited to loss of
data, loss of service availability, corruption of the boot volume, destruction
of filesystems, misconfiguration of network security controls, unauthorized
remote access enabled by a proposed change, or losses sustained by you or third
parties), even if such maintainer or contributor has been advised of the
possibility of such damages.

---

## 3. Specific Operational Risks

Halbert's autonomous action surface includes, without limitation:

| Capability | Example action | Potential consequence |
| :--- | :--- | :--- |
| Service management | `systemctl stop nginx` | Production web server outage |
| Filesystem editing | Editing `/etc/fstab` | Boot failure; unmountable volumes |
| Daemon scheduling | Writing a `launchd` plist | Recurring runaway process; CPU drain |
| Network configuration | Rewriting `pf.conf` / `iptables` | Loss of remote access; firewall lockout |
| Package management | `apt purge ...` / `brew uninstall ...` | Removal of a dependency of a critical service |
| User & group management | `usermod`, `dseditgroup` | Locked-out administrator account |
| Disk operations | `diskutil apfs resizeContainer` | Data loss on the boot container |
| Config drop-in writes | Writing `sshd_config.d/` overrides | Open SSH to wider scope than intended |

This list is illustrative, not exhaustive. Halbert may propose or execute any
operation that the operating user account has permission to perform.

---

## 4. Your Responsibilities

You are solely and exclusively responsible for:

1. **Testing proposed actions** in a non-production environment (a VM, a
   snapshot, or a staging host) before approving them on a production machine.
2. **Maintaining offline, verified, restorable backups** of every system on
   which Halbert operates. "Online" backups on the same volume do not count — a
   runaway `rm` or a corrupted `fstab` will take them with it.
3. **Reviewing every dry-run preview** before approving an action. Halbert's
   dry-run output is a *proposal*, not a guarantee of safety.
4. **Constraining Halbert's permissions** to the minimum required. Do not run
   Halbert as `root` or with `sudo` NOPASSWD unless you have explicitly accepted
   the blast radius that implies.
5. **Auditing the policy file** (`config/policy.yml`) for your environment
   before enabling autonomous execution.
6. **Supervising autonomous sessions.** Halbert's "human approval" gate is a
   control, not a substitute for judgment. If you approve without reading, the
   outcome is your responsibility, not Halbert's.

---

## 5. Human Approval Is Not a Guarantee

Halbert gates high-risk actions behind a human approval step and presents a
dry-run preview before execution. **These are harm-reduction controls, not
safety guarantees.** Specifically:

- The dry-run preview describes the *intended* action as Halbert understands
  it. It may not surface side effects, dependency chains, or second-order
  consequences (e.g. stopping a service that another undocumented service
  depends on).
- The approval dialog is a binary confirm. It does not and cannot verify that
  the action is *safe for your specific environment*.
- The rollback capability restores previously captured state for the specific
  file or unit Halbert touched. It does **not** roll back side effects on other
  services, running processes, or remote systems that reacted to the change.

A human approval click does not transfer liability from you to Halbert.

---

## 6. Local-First, No Remote Oversight

Halbert runs locally. There is no remote kill switch, no central monitoring, and
no operator on call to intervene if Halbert proposes a destructive action on
your host. **You are the only supervisor.** If you walk away from an autonomous
session, you accept whatever Halbert does in your absence within the bounds of
the policy you configured.

---

## 7. Third-Party Services and Data

When an optional Cloud API key (OpenAI, Anthropic, Google, or other provider)
is configured, prompts and system context leave your local machine and are
processed by the configured provider under that provider's terms. Halbert's
maintainers are not party to that relationship and bear no responsibility for
the provider's handling, retention, or training use of your data. See
[`PRIVACY.md`](./PRIVACY.md) § "Cloud API mode" for the full disclosure.

---

## 8. Children, Regulated Industries, and High-Risk Uses

Halbert is not intended for use by children. Halbert is not intended for use in
regulated environments (HIPAA, PCI-DSS, SOX, FedRAMP, ITAR, GDPR Article 22
automated decision-making contexts, or any jurisdiction's safety-critical
system classification) without an independent qualified review. Halbert is not
intended for use on life-critical, aviation, medical, automotive, or
infrastructure-control systems. If you deploy Halbert in any such context, you
do so at your sole risk and accept all resulting liability.

---

## 9. Indemnification

To the fullest extent permitted by applicable law, you agree to indemnify,
defend, and hold harmless the Halbert maintainers, contributors, copyright
holders, and distributors from any claim, demand, action, loss, or damages
(including reasonable attorneys' fees) arising out of or related to your use of
Halbert, your approval of any Halbert-proposed action, your configuration of
the policy engine, or your deployment of Halbert on any system — including
claims brought by third parties affected by actions Halbert took on a system
under your control.

---

## 10. Governing Language

This disclaimer is authored in English. Any translation is provided as a
courtesy only; the English text is the legally binding version.

---

## 11. Severability

If any provision of this disclaimer is held to be unenforceable, invalid, or
illegal by a court of competent jurisdiction, the remaining provisions shall
continue in full force and effect, and the unenforceable provision shall be
modified to the minimum extent necessary to make it enforceable while preserving
its intent.

---

## 12. First-Run Acknowledgment

Halbert's first-run onboarding (CLI and GUI) presents this disclaimer in
condensed form and requires explicit user acceptance before enabling autonomous
action execution. Acceptance is recorded in
`~/.local/share/halbert/accepted_disclaimer.txt` with a timestamp and the
disclaimer version. Re-acceptance is required if this document is materially
updated.

> **Disclaimer version:** 1.0
> **License cross-reference:** [LICENSE.md](./LICENSE.md) (GPL-3.0 §15, §16)
> **Security cross-reference:** [SECURITY.md](./SECURITY.md)
