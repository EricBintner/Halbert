# Halbert Domain Modules & Four Whys Mechanics

**Version:** 1.0.0  
**Date:** 2026-08-23  
**Status:** Approved Technical Design Specification  
**Lead:** Visual Design Lead & Systems Architect  
**Reads with:** `documentation/design/DESIGN-SYSTEM-SPEC.md`, `documentation/design/COMPONENT-ARCHITECTURE.md`, `documentation/design/USER-JOURNEY-METHODOLOGY.md`  

---

## 1. Domain Module Architecture & Lifecycle

In Halbert, the right-hand container is not a fixed dashboard of arbitrary tabs; it is an **intelligent context stage** where domain modules are summoned dynamically based on conversational context.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DOMAIN MODULE LIFECYCLE FSM                            │
│                                                                             │
│  [ UNLOADED ] ──(Trigger: Agent mentions /dev/sda1)──> [ SUMMONING ]        │
│                                                              │              │
│                                                       (GSAP 500ms ease)     │
│                                                              │              │
│  [ DISMISSED ] <──(Close/Timeout)── [ SUMMONED (Active) ] <──┘              │
│                                           │                                 │
│                                     (User Clicks Pin)                       │
│                                           │                                 │
│                                           ▼                                 │
│                                     [ PINNED STAGE ]                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Module States:
1. **Unloaded (Idle):** Module is unmounted, consuming zero CPU/render overhead.
2. **Summoning:** Triggered by an agent tool call or semantic mention in chat. Slides into the right pane with `--ease-smooth` (`500ms`).
3. **Active (Summoned):** Renders live telemetry, AST diffs, or journal logs synchronized with the active conversation turn.
4. **Pinned:** User clicks `[Pin Module]` to preserve the view across subsequent conversational turns.
5. **Dismissed:** Smoothly fades out upon topic transition or explicit user dismissal.

---

## 2. The 5 Core Domain Modules

---

### Module 1: `VitalsModule` (Host Physiology)

Visualizes the computer's biological state (temperature, load, compute capacity).

```
┌────────────────────────────────────────────────────────────────────────┐
│ VITALS & PHYSIOLOGY — ubuntu-server-01                 [Live: 1s Tick] │
├────────────────────────────────────────────────────────────────────────┤
│ CPU TEMP: 45°C [Nominal]            LOAD AVG: 0.15, 0.22, 0.18         │
│ [████████░░░░░░░░░░░░░░░░░░░░] 38%  [███░░░░░░░░░░░░░░░░░░░░░░░░░] 12% │
│                                                                        │
│ MEMORY: 18.2 GB / 64.0 GB (28%)     SWAP: 0 MB / 8.0 GB (0%)           │
│ [███████░░░░░░░░░░░░░░░░░░░░░]      [░░░░░░░░░░░░░░░░░░░░░░░░░░░░]     │
│                                                                        │
│ UPTIME: 42 days, 14 hours           THERMAL STATUS: Cool & Quiet       │
└────────────────────────────────────────────────────────────────────────┘
```

- **Sensors:** `/sys/class/hwmon`, `os.getloadavg()`, `/proc/meminfo`.
- **Styling:** Recessed `#EFECE4` cards with crisp `1px` hairlines, desaturated status bars (`#2D7A56` for nominal, `#C4781C` for >80°C).

---

### Module 2: `ConfigDiffModule` (AST & Precedence Visualizer)

Visualizes drop-in configuration hierarchies and AST diffs with precedence analysis.

```
┌────────────────────────────────────────────────────────────────────────┐
│ CONFIGURATION INSPECTOR: /etc/ssh/sshd_config.d/              [ AST ]  │
├────────────────────────────────────────────────────────────────────────┤
│ DROP-IN PRECEDENCE HIERARCHY:                                          │
│ ├─ 10-default.conf       (Base OS defaults)                            │
│ ├─ 50-custom.conf        (User modifications) ◄ ACTIVE OVERRIDE        │
│ └─ 90-cloud-init.conf    (Provider drop-in)   [ Shadowed Key ]         │
├────────────────────────────────────────────────────────────────────────┤
│ ATOMIC DIFF VIEW:                                                      │
│ Line 14: - Port 22                                                     │
│ Line 14: + Port 2222                                                   │
│ Line 28: - PasswordAuthentication yes                                  │
│ Line 28: + PasswordAuthentication no                                   │
├────────────────────────────────────────────────────────────────────────┤
│ BLAST RADIUS: Low · Affects SSH daemon reload · Zero downtime          │
└────────────────────────────────────────────────────────────────────────┘
```

- **Features:** Side-by-side or inline AST token diffs; automated detection of shadowed configuration keys in `.d` directories.

---

### Module 3: `StorageSensorsModule` (Drive Health & Filesystems)

Deep diagnostic view into physical drives, bcachefs/ZFS/Btrfs pools, and SMART health.

```
┌────────────────────────────────────────────────────────────────────────┐
│ STORAGE & POOLS                                           [SMART Check]│
├────────────────────────────────────────────────────────────────────────┤
│ /dev/nvme0n1 · 2.0 TB NVMe SSD · Temp: 38°C               [ HEALTHY ]  │
│ Mounted on / (bcachefs) · 840 GB used / 2.0 TB (42%)                   │
│ Compression: lz4 · Background writeback: Active                        │
├────────────────────────────────────────────────────────────────────────┤
│ /dev/sda1 · 8.0 TB HDD Array · Temp: 48°C                 [ ATTENTION ]│
│ Mounted on /mnt/data · 3 Read Errors logged at 08:00 today             │
│ Reallocated Sectors: 0 · Pending Sectors: 3 · SMART: Degraded          │
│ [ Schedule Extended SMART Self-Test ]   [ View Error History ]         │
└────────────────────────────────────────────────────────────────────────┘
```

- **Sensors:** `smartctl -a`, `lsblk -J`, `df -h`, `/sys/block/`.

---

### Module 4: `EvidenceDrawerModule` (Raw Logs & Doc Citations)

Cryptographically verifiable provenance for all claims and autonomous discoveries.

```
┌────────────────────────────────────────────────────────────────────────┐
│ EVIDENCE & PROVENANCE                                     [Copy SHA256]│
├────────────────────────────────────────────────────────────────────────┤
│ LOG EXCERPT: journald --unit=sshd.service                              │
│ Aug 23 08:14:02 ubuntu-server sshd[4102]: Failed password for invalid   │
│ user admin from 192.168.1.104 port 54122 ssh2                          │
├────────────────────────────────────────────────────────────────────────┤
│ SOURCEPREP KNOWLEDGE CITATION:                                         │
│ Document: Ubuntu Server 24.04 Hardening Guide (§4.2 SSH Port Isolation)│
│ "Binding SSH to a non-standard port reduces automated scan noise by 95%"│
│ Hash: 8f4b2e...c901  · Match Score: 0.94                               │
└────────────────────────────────────────────────────────────────────────┘
```

- **Verification:** Links directly to SourcePrep indexed documentation chunks and live journald cursors.

---

### Module 5: `ApprovalRollbackModule` (Dry-Run Safety Gate)

The human-in-the-loop control center for modifying system configuration.

```
┌────────────────────────────────────────────────────────────────────────┐
│ ⚠ PRIVILEGE ELEVATION REQUIRED: Modify /etc/fstab                      │
├────────────────────────────────────────────────────────────────────────┤
│ PROPOSAL: Enable lz4 background compression on /dev/nvme0n1            │
│ EXECUTION PLAN:                                                        │
│ 1. Create backup: /etc/fstab.halbert.bak-20260823                      │
│ 2. Apply mount option: compress=lz4 in /etc/fstab                      │
│ 3. Remount filesystem live: mount -o remount,compress=lz4 /            │
│ 4. Verify I/O throughput with benchmark probe                          │
├────────────────────────────────────────────────────────────────────────┤
│ ROLLBACK SNAPSHOT: #SNAP-20260823-04 (1-Click Restore Guarantee)       │
├────────────────────────────────────────────────────────────────────────┤
│ [ Approve & Run (Polkit) ]         [ Dry-Run Test ]         [ Cancel ] │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Law of Four Whys Interaction Mechanics

Every piece of proactive advice or reactive diagnostic from Halbert incorporates a clickable **`WhyChip`**:

```
┌──────────────────────────────────────────────────┐
│ [ WhyChip: ⚠ Important | /etc/fstab | 3 Whys ]   │ ◄ Clickable Anchor
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────────────────────────┐
│ WHY CARD POPOVER                                                       │
├────────────────────────────────────────────────────────────────────────┤
│ 1. WHY NOW?   │ Scheduled 03:00 morning triage detected uncompressed   │
│               │ volume with >500GB text logs accumulating.             │
├───────────────┼────────────────────────────────────────────────────────┤
│ 2. WHY CARE?  │ Free space will exhaust in 14 days without compression.│
│               │ Enabling lz4 saves ~35% storage with 0% CPU penalty.   │
├───────────────┼────────────────────────────────────────────────────────┤
│ 3. WHY SO?    │ Compression was left at default "none" during initial  │
│               │ OS installation on 2026-06-01.                         │
├───────────────┼────────────────────────────────────────────────────────┤
│ 4. WHY TRUST? │ Grounded in /etc/fstab line 4 and bcachefs man page.   │
│               │ [ View Raw Evidence ]                                  │
└────────────────────────────────────────────────────────────────────────┘
```

### Data Contract for WhyCard (`WhyPayload`):

```typescript
interface WhyPayload {
  id: string;
  target: string;              // e.g. "/etc/fstab" or "sshd.service"
  severity: 'nominal' | 'attention' | 'critical' | 'info';
  whyNow: string;              // Trigger reason & timing context
  whyCare: string;             // Real-world consequence if ignored
  whySo: string;               // Historical context & past user intent
  whyTrust: {                  // Verifiable provenance
    filePath?: string;
    lineNumbers?: number[];
    logQuery?: string;
    docCitation?: string;
    sha256?: string;
  };
  actions?: Array<{
    id: string;
    label: string;
    variant: 'primary' | 'secondary' | 'destructive';
  }>;
}
```

---

## 4. Architectural Event Bus & Synchronization

To connect the conversational spine (left pane) and domain modules (right pane) smoothly without tight coupling:

```typescript
// Shared Event Bus Contract
type HalbertUIEvent = 
  | { type: 'MODULE_SUMMON'; moduleId: 'vitals' | 'config' | 'storage' | 'evidence' | 'approval'; payload: any }
  | { type: 'MODULE_DISMISS'; moduleId: string }
  | { type: 'MODULE_PIN'; moduleId: string }
  | { type: 'EXECUTE_APPROVAL'; proposalId: string; elevationToken?: string }
  | { type: 'TRIGGER_ROLLBACK'; snapshotId: string };
```

This guarantees that whenever the LLM agent streams a tool invocation or answers a query, the corresponding domain module is summoned with exact context and state synchronization.
