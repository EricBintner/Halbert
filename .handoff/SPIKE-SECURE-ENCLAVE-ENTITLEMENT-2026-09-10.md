# Spike — can the shipped app carry a Secure Enclave re-auth key?

Run 2026-09-10 on this machine (macOS 26.5.1, Xcode Swift 6.3.2, Touch ID
enrolled, `Developer ID Application: Eric Bintner (FU96NT58N5)`). Measured,
not reasoned: every line below is an observed result, and the binaries are
in the session scratchpad.

**The question**, as `.handoff/STATE-OF-WORK-2026-09-10.md` §2 posed it: if a
Tauri-bundled, Developer-ID-signed `.app` cannot carry a
`keychain-access-groups` entitlement, the sound design for A11-G12's
`os_reauth` leg dies and the fallback is a biometry-gated HMAC.

**The verdict: the route lives, and it costs one provisioning profile the
founder has to create.** Not an afternoon of engineering — an account
action. Until it exists the app cannot store *any* access-controlled
keychain item, Secure Enclave or otherwise, and an app signed with the
entitlement but without the profile does not run at all.

## What was measured

| # | Binary | Signature | Entitlements | Result |
|---|---|---|---|---|
| A | bare | ad-hoc | none | SE key refused, `-34018` |
| B | `.app` | Developer ID, hardened runtime | none | SE key refused, `-34018` |
| C | `.app` | Developer ID, hardened runtime | `keychain-access-groups` | **killed at exec, SIGKILL** |
| D | `.app` | Developer ID, hardened runtime | none | user-presence *file* keychain item refused, `-34018` |
| E | `.app` | Developer ID, hardened runtime | `com.apple.security.application-groups` | runs, still refused `-34018` |

`LAContext` was available in every one of them, including the unsigned bare
binary: `canEvaluatePolicy(.deviceOwnerAuthenticationWithBiometrics)` and
`.deviceOwnerAuthentication` both returned true, and `coreauthd` resolved
the bundle identity. Nothing here evaluated a policy, so no Touch ID prompt
was raised to get these numbers.

### What the OS said, in its own words

`securityd` on the refusals (run B):

> Client has neither `com.apple.application-identifier` nor
> `com.apple.security.application-groups` nor `keychain-access-groups`
> entitlements

AMFI on run C, which is the finding:

> Restricted entitlements not validated, bailing out. Error … Code=-413
> "No matching profile found"
>
> Code has restricted entitlements, but the validation of its code signature
> failed.

That is a fatal signature check — `mac_vnode_check_signature: … failed
fatally` — not a permission denial at the point of use. **Shipping the
entitlement without the profile does not degrade, it fails to launch.**

## Three conclusions that change the design

**1. The Enclave is not the gate. The keychain is.** `-34018` is
`errSecMissingEntitlement`, and it arrived identically for a Secure Enclave
key (A, B) and for a plain generic-password item with a `.userPresence` ACL
(D). Any `kSecAttrAccessControl` item lives in the data-protection keychain,
and the data-protection keychain wants one of the three entitlements
`securityd` names. So **"fall back to a biometry-gated HMAC" is not a
fallback** — it needs exactly the same entitlement the Enclave route needs.
The fallback named in the state-of-work document does not exist as an
independent option, and planning around it would have cost a cycle to
discover.

**2. `application-groups` is not a way around it.** Run E signs and launches
cleanly — so it is not a restricted entitlement in the way
`keychain-access-groups` is — and still refuses the item, because on macOS
that entitlement only takes effect for a sandboxed app. App Sandbox is
closed to Halbert on product shape, not on OS grounds: a machine that runs
shell commands, reads `/etc` and manages services is not a sandboxable app.

**3. The route is ordinary and shipped daily.** Six Developer-ID-signed apps
in `/Applications` on this machine ship `Contents/embedded.provisionprofile`
carrying `keychain-access-groups` — Brave, ChatGPT, Claude, CodexBar,
Discord, Docker. The shape of the one Halbert needs, read out of one of
them:

```
Name                  "Claude - Developer ID - 20260410"
Platform              OSX
ProvisionsAllDevices  true
IsXcodeManaged        false
keychain-access-groups  ["<TeamID>.*"]
ExpirationDate        2044   (TimeToLive 6570 days)
```

`ProvisionsAllDevices: true` and an 18-year life are what make this viable
for outside-the-store distribution: the profile is not per-device and does
not need renewing on a release cadence.

## What has to happen, in order

1. **Founder, in the Apple Developer account.** An explicit App ID for the
   bundle identifier with the Keychain Sharing capability, then a **macOS
   "Developer ID" provisioning profile** for it. One action, expires far
   out, not per-device. Nothing else in this list can start first.
2. **Packaging.** The profile lands at `Contents/embedded.provisionprofile`
   in the Tauri bundle, and the `keychain-access-groups` entitlement joins
   the entitlements file the app is already signed with. This needs a
   `.app`-bundle build to verify — checking it against a bare binary proves
   nothing, since AMFI reads the profile from the bundle.
3. **Only then, the re-auth handler** (A11-G12's residual). Its shape is
   now decided by the measurements above rather than assumed: a Secure
   Enclave P-256 key with
   `SecAccessControlCreateWithFlags(.privateKeyUsage, .biometryCurrentSet)`,
   whose signature over the grant payload is what
   `SurfaceReceipt.for_session` records instead of today's hardcoded
   `os_reauth=False`. `.biometryCurrentSet` is the right flag rather than
   `.biometryAny`: the key invalidates when the enrolment set changes, so a
   finger added after a grant cannot use the key that grant was bound to.

## What is still not decided, and is not a code question

`LAContext.evaluatePolicy(.deviceOwnerAuthentication)` works today, with no
entitlement and no profile, in any binary — and it is what
`documentation/design/PERMISSION-AND-CONSENT-SYSTEM-2026-09-06.md:624`
actually specifies. It returns a boolean in-process. The Enclave adds one
thing to that: a signature a compromised in-process caller cannot forge,
which is the difference between "this process says a re-auth happened" and
"a re-auth happened". **That difference is the whole reason the grant record
carries `authn` at all**, and R-08's STOP condition already forbids
accepting a caller-supplied `authn` string as an interim — so the boolean
route is not a shippable half-step, it is the thing the packet refused.

Which leaves the founder one question the measurements cannot answer: is the
step-1 account action worth doing now, or does first-run acceptance wait?
Nothing regresses while it waits — `accept_profile` still has no route
caller, so no grant is being recorded on a promise the code cannot keep.

## Reproducing

`spike.swift` (Secure Enclave key create / find / delete) and
`fallback.swift` (user-presence generic-password item) are in this session's
scratchpad, with the four entitlement plists and a minimal `.app` skeleton.
Both are creation-and-lookup only and raise no biometric prompt. Rebuild:

```bash
swiftc -O spike.swift -o spike && codesign --force --options runtime \
  -s "Developer ID Application: …" --entitlements ents-kag.plist Spike.app
```

Read the refusal reason from the OS rather than from the exit code —
`log show --last 2m --predicate 'process == "amfid" OR process == "secd"'`
is where both the `-413` and the `-34018` explanations are written, and the
process that is SIGKILLed prints nothing at all.
