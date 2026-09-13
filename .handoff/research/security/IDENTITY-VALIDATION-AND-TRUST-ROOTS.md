# Research Brief: Identity Validation and Decentralized Trust Roots

**Date**: 2026-09-12  
**Assigned To**: Security Research Subagent / Next Session  
**Subject**: Decentralized identity, root of trust, and authentication architecture for Halbert State Vault and multi-device federation.

---

## 1. Problem Statement

Consumer ecosystems like Apple, Google, and Microsoft anchor device identity, backup encryption, and cross-device migration in **centralized cloud identity accounts** (Apple ID / iCloud Keychain / Secure Enclave remote attestation servers).

When an Apple user sets up a new iPhone or restores from backup:
1. Apple's servers authenticate the user's credentials (email/password + 2FA push to trusted devices).
2. Apple's hardware Security Escrow recovers the Cloud Key Vault using the user's passcode.
3. Apple's servers vouch for the identity and cryptographic legitimacy of both devices during Quick Start.

### The Halbert Reality:
Halbert operates under non-negotiable architectural directives:
- **Zero Company Cloud Backend**: Halbert maintains no user account databases, no authentication brokers, and no cloud KMS ($0 infrastructure bill, zero privacy/compliance liability).
- **Local-First & Offline Capable**: A user's home server and workstation must pair, back up, and restore seamlessly even if the internet is completely severed.
- **Heterogeneous Hardware**: Halbert runs across Apple Silicon (Secure Enclave), Linux x86 (TPM 2.0 or headless with no TPM), Raspberry Pis, and N150 mini-PCs. We cannot assume hardware-bound enclave support on every node.
- **Subtractive Contract**: Haloysius maintains exactly two hard dependencies (`pyyaml`, `requests`). All cryptographic tooling must live in `halbert_core` using standard library primitives or established packages (`cryptography`), avoiding exotic C/Rust extensions unless deferred behind optional seams.

**The Question for Research**:  
*Without Apple ID or a central server, how does Halbert establish identity, validate authenticity, and securely orchestrate State Vault backup, restore, and LAN device migration?*

---

## 2. Threat Models & Attack Scenarios to Address

Any proposed architecture must be evaluated against these 5 specific threat vectors:

1. **The Stolen Backup Archive**: An attacker gains access to the user's Google Drive, iCloud Drive, or external USB drive containing `.halbert-backup` files.  
   *Requirement*: Zero-knowledge client-side encryption. The cloud provider or drive thief must not be able to read persona memories, Tier 2 secrets, or identity keys.
2. **The Rogue LAN Device**: A compromised IoT device or guest on the home Wi-Fi network attempts to forge a pairing request, spoof a canonical host, or replay a State Vault restore to exfiltrate identity.  
   *Requirement*: Mutual authentication with out-of-band operator verification.
3. **The Malicious / Tampered Archive Injection**: An attacker crafts a malicious `.halbert-backup` containing poisoned instructions or modified SQLite files to gain root execution or overwrite system prompts upon restore.  
   *Requirement*: Cryptographic signature verification over the archive manifest prior to decompression or database execution.
4. **The Hardware Disposal / Motherboard Burnout**: The physical machine hosting Halbert suffers catastrophic motherboard failure.  
   *Requirement*: Keys must not be permanently trapped in a deceased motherboard's TPM without an offline escrow mechanism (avoiding "Hardware-Bound Entanglement").
5. **Split-Brain / Replay on Restore**: Restoring an older backup archive must not silently fork the entity's history or overwrite newer live state on other paired satellites without operator acknowledgment.

---

## 3. Five Trust Architectures to Investigate

The incoming AI should research and evaluate the following 5 models, comparing trade-offs in cryptographic strength, implementation complexity, and user friction:

### Model A: Deterministic Mnemonic Seed (BIP-39 / Web3 Paradigm)
- **Mechanism**: During initial setup, the user is presented with a 12- or 24-word recovery phrase.
- **Derivation Path**: Using a deterministic KDF (e.g. PBKDF2/Argon2id + HKDF), the seed derives:
  - Master Backup Encryption Key (AES-256-GCM)
  - Entity Identity Key Pair (`Ed25519` $\rightarrow$ `did:key:...`)
  - Inter-device Root Certificate / PSK
- **Questions for Research**:
  - What is the UX friction for non-technical users?
  - Should the 24-word phrase be mandatory or an opt-in "Disaster Recovery Key"?
  - How does wordlist localization work if the user's primary language changes?

### Model B: WebAuthn / FIDO2 Passkeys (The Hardware Token Paradigm)
- **Mechanism**: Use the user's existing smartphone or laptop biometric authenticator (Touch ID, Face ID, YubiKey) as the root of trust via WebAuthn.
- **Questions for Research**:
  - Can WebAuthn be used over local HTTP/IP connections (e.g. `http://192.168.1.50:8000` or `.local` mDNS)?
  - How do origin-binding constraints in WebAuthn behave when a home server's IP changes?
  - Does WebAuthn allow extracting or wrapping symmetric backup keys (via the PRF / `hmac-secret` WebAuthn extension)?

### Model C: Short Authentication Strings (SAS) & Out-of-Band Physical Proximity (The Signal / Matrix Model)
- **Mechanism**: Ephemeral Diffie-Hellman key exchange over LAN, authenticated by a human comparing a visual SAS (6-digit PIN, 4 matching words, emoji sequence, or dynamic visual QR/constellation on screen).
- **Questions for Research**:
  - How closely does this map to Halbert's existing 4-digit PIN pairing in `routes/peers.py`?
  - Can SAS be upgraded to generate a persistent mutual trust anchor between devices?
  - How does this work when one of the devices is completely headless (e.g. smart speaker with no screen)?

### Model D: Decentralized Identifiers (DIDs) & Merkle Audit Chains (The Git / SSH Model)
- **Mechanism**: Trust-On-First-Use (TOFU) with public key pinning. Each node generates a `did:key:ed25519:...`. Archives are signed by the canonical node's private key.
- **Questions for Research**:
  - Halbert already uses `did:key` in `haloysius.seam.SigningBackend` and `HalbertSigner` (`crypto/storage.py`). How do we extend this to sign the State Vault manifest?
  - How does a new, blank replacement machine verify that a signed archive is authentic if it has never met the old machine? (The bootstrapping problem).

### Model E: Threshold Cryptography / Shamir's Secret Sharing (The Fleet Mesh Model)
- **Mechanism**: The master backup key is split into shards (e.g. 2-of-3 threshold) distributed across paired fleet devices (e.g. Home Server + Workstation + User's Laptop).
- **Questions for Research**:
  - Can a restored canonical node be re-authorized simply by having 2 other paired devices on the LAN approve it, without the user ever typing a master password?
  - What happens if 2 out of 3 devices die simultaneously?

---

## 4. Specific Deliverables Requested from the Next AI

1. **Comparative Trade-off Matrix**:
   - Compare the 5 models across: Security, Offline Reliability, Implementation Complexity, User Friction, and Suitability for Halbert.
2. **Recommended Hybrid Architecture**:
   - Propose a layered security stack (e.g., Daily Convenience Layer vs Disaster Recovery Root).
3. **Protocol Specifications**:
   - **Protocol 1: State Vault Cryptographic Envelope**: Exact algorithms (Argon2id parameters, AES-256-GCM vs ChaCha20-Poly1305, HKDF salt/info, signature scheme).
   - **Protocol 2: Zero-Trust LAN Migration Handshake**: Step-by-step cryptographic protocol for streaming state directly between two Halbert appliances on an untrusted LAN.
   - **Protocol 3: Operator Authentication from Desktop Dashboard**: How the desktop UI proves administrative authority to the headless home server without hardcoded cleartext API tokens.
4. **Codebase Integration Map**:
   - Identify which files in `halbert_core/crypto/`, `halbert_core/federation/`, and `halbert_core/dashboard/` will implement the proposed protocols.
