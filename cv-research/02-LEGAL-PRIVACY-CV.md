# Legal & Privacy Research: Computer Vision Input for Halbert

**Document Type:** Legal Foundation / Privacy Architecture Reference  
**Date:** 2026-08-27  
**Author:** Halbert CV Research Phase  
**Status:** Research Complete -- Ready for Implementation Planning  

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Biometric Data & Privacy Laws](#2-biometric-data--privacy-laws)
3. [Screen Capture Legality](#3-screen-capture-legality)
4. [Webcam & Camera Access Legal Considerations](#4-webcam--camera-access-legal-considerations)
5. [Privacy Best Practices for CV-Enabled Apps](#5-privacy-best-practices-for-cv-enabled-apps)
6. [Existing Frameworks & Industry Guidelines](#6-existing-frameworks--industry-guidelines)
7. [Recommended Privacy Gates & Defaults for Halbert](#7-recommended-privacy-gates--defaults-for-halbert)
8. [Summary of Legal Risk Matrix](#8-summary-of-legal-risk-matrix)
9. [References](#9-references)

---

## 1. Executive Summary

Halbert is a local-first, GPL-3.0 licensed homelab sysadmin AI assistant that runs on macOS and Linux. It already maintains a zero-telemetry privacy posture documented in `PRIVACY.md` and has GDPR/CCPA compliance documentation. This document researches the legal landscape and best practices for adding **computer vision (CV) input** -- specifically screen capture and webcam/camera access -- to Halbert.

### Key Findings

1. **On-device processing is the strongest legal shield.** The Seventh Circuit's 2026 decision in *G.T. v. Samsung Electronics America* held that BIPA does not reach biometric data that remains on a user's own device, because the company never "possesses" or "collects" it. This is the single most important precedent for Halbert's local-first architecture.

2. **Photographs are NOT automatically biometric data under GDPR.** Per Recital 51, photographs only become special category biometric data when processed through "specific technical means allowing the unique identification or authentication of a natural person." Generic screen capture or webcam frames that are processed for non-identification purposes (e.g., reading a dashboard, OCR of terminal text) are personal data but not special category data.

3. **The EU AI Act prohibits emotion recognition in workplace and education contexts** (Article 5(1)(f), effective February 2, 2025). Halbert must avoid any feature that infers emotions from biometric data in these settings.

4. **Screen capture and camera access are gated by OS-level permission frameworks** (macOS TCC/ScreenCaptureKit, Linux xdg-desktop-portal/Wayland). These provide built-in consent flows that Halbert should leverage rather than circumvent.

5. **Cloud API mode fundamentally changes the legal posture.** Sending visual frames to a cloud LLM provider transforms Halbert from an on-device processor into a data transmitter, triggering biometric privacy laws, GDPR Article 9, and potentially wiretapping statutes. This mode requires explicit, granular, informed consent.

6. **Default-off, granular permissions, visual indicators, and zero-retention of raw frames** are the four pillars of a defensible CV privacy architecture.

---

## 2. Biometric Data & Privacy Laws

### 2.1 GDPR (EU) -- Article 9 Special Categories

#### What Qualifies as Biometric Data

Under GDPR Article 4(14), biometric data is "personal data resulting from specific technical processing relating to the physical, physiological or behavioural characteristics of a natural person, which allow or confirm the unique identification of that natural person, such as facial images or dactyloscopic data."

**Critical distinction (Recital 51):**

> "The processing of photographs should not systematically be considered to be processing of special categories of personal data as they are covered by the definition of biometric data only when processed through a specific technical means allowing the unique identification or authentication of a natural person."

This means:
- **A webcam frame or screenshot containing a person's face is NOT automatically biometric data** under GDPR.
- It becomes biometric data (and thus special category data under Article 9) only when processed through technical means that allow **unique identification or authentication** of a person -- e.g., creating a faceprint template and matching it against a database.
- The UK ICO confirms: "Although a digital image may allow for identification using physical characteristics, it only becomes biometric data if you carry out 'specific technical processing'. Usually this involves using the image data to create an individual digital template or profile."
- Source: https://gdpr-info.eu/recitals/no-51/
- Source: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-is-special-category-data/
- Source: https://verasafe.com/blog/gdpr-and-photographs-understanding-special-categories-of-personal-data/

#### Article 9 Processing Prohibition and Exceptions

Article 9(1) prohibits processing of biometric data for the purpose of uniquely identifying a natural person. Article 9(2) provides exceptions, the most relevant for Halbert being:

- **Article 9(2)(a) -- Explicit consent:** "The data subject has given explicit consent to the processing of those personal data for one or more specified purposes." This is the most likely lawful condition for Halbert's CV features. Explicit consent must be:
  - Freely given, specific, informed, and unambiguous
  - Not buried in a general terms-of-service agreement
  - Withdrawable at any time
- Source: https://www.legislation.gov.uk/eur/2016/679/article/9?view=plain
- Source: https://cy.ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/how-do-we-process-biometric-data-lawfully/

#### EDPB Guidelines on Video Devices

The European Data Protection Board's *Guidelines 3/2019 on processing of personal data through video devices* provide directly applicable guidance:

- **Purpose specification (Article 5(1)(b)):** Purposes must be specified in detail before use. "Safety" alone is not sufficiently specific.
- **Transparency (Article 12-13):** Data subjects must be informed that video surveillance is in operation, using a layered approach:
  - **First layer (warning sign):** Purpose, identity of controller, rights of the individual, where to find detailed information.
  - **Second layer (detailed information):** Complete Article 13 information available via QR code, website, or central location.
- **Data minimization (Article 5(1)(c)):** Real-time monitoring may be more intrusive than storing and auto-deleting. Black box solutions (auto-delete after a period) may be preferable.
- **Biometric data through video:** "The video footage of an individual cannot in itself be considered as biometric data under Article 9, if it has no [identification purpose]." (paragraph 74)
- **Raw data deletion:** Controllers should delete raw data (face images, speech signals, gait) and ensure effectiveness of deletion. If raw data must be kept, noise-additive methods (watermarking) should be explored.
- Source: https://www.edpb.europa.eu/documents/guideline/guidelines-32019-on-processing-of-personal-data-through-video-devices_en

#### Application to Halbert

| Halbert CV Feature | GDPR Classification | Article 9 Triggered? |
|---|---|---|
| Screen capture (no faces visible) | Personal data (if it reveals info about the user) | No |
| Screen capture (faces visible in video calls) | Personal data | Only if facial recognition/identification is performed |
| Webcam frame for OCR/dashboard reading | Personal data | No (not for identification) |
| Webcam frame for face recognition/login | Biometric data -- special category | Yes -- requires explicit consent |
| Webcam frame sent to cloud LLM | Personal data, potentially biometric | Depends on cloud provider's processing |

### 2.2 EU AI Act -- Biometric Identification & Visual Surveillance

The EU AI Act (Regulation 2024/1689) entered into force August 1, 2024, with prohibitions applicable from February 2, 2025.

#### Prohibited Practices (Article 5)

The following are directly relevant to CV features:

- **Article 5(1)(e):** Prohibits AI systems that create or expand facial recognition databases through untargeted scraping of facial images from the internet or CCTV footage.
- **Article 5(1)(f):** Prohibits AI systems that infer emotions of a natural person **in the areas of workplace and education institutions**, except where intended for medical or safety reasons. This is critical -- Halbert must not implement emotion recognition features if it could be used in workplace or educational contexts.
- **Article 5(1)(g):** Prohibits biometric categorisation systems that categorise individuals based on biometric data to deduce or infer race, political opinions, trade union membership, religious or philosophical beliefs, sex life, or sexual orientation.
- **Article 5(1)(h):** Prohibits real-time remote biometric identification in publicly accessible spaces for law enforcement (with narrow exceptions).

#### Key Definitions

- **"Biometric identification"** (Recital 15): "Automated recognition of physical, physiological and behavioural human features such as the face, eye movement, body shape, voice, prosody, gait, posture, heart rate, blood pressure, odour, keystrokes characteristics, for the purpose of establishing an individual's identity by comparing biometric data of that individual to stored biometric data of individuals in a reference database."
- **Exclusion of biometric verification:** "This excludes AI systems intended to be used for biometric verification, which includes authentication, whose sole purpose is to confirm that a specific natural person is the person he or she claims to be and to confirm the identity of a natural person for the sole purpose of having access to a service, unlocking a device or having security access to premises." (Recital 15)
- **"Emotion recognition system"** (Recital 18): AI systems for identifying or inferring emotions or intentions based on biometric data. Does NOT include physical states like pain or fatigue, or mere detection of readily apparent expressions (frown, smile) unless used for inferring emotions.

#### Application to Halbert

- Halbert's CV features must NOT include emotion recognition, especially if used in workplace or educational settings.
- Halbert must NOT include biometric categorisation that infers sensitive attributes.
- Biometric verification (e.g., confirming the user is who they claim to be for device unlock) is excluded from the biometric identification prohibition, but still requires GDPR Article 9 compliance.
- Source: https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-5
- Source: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?qid=1724745059760&uri=OJ%3AL_202401689
- Source: https://fpf.org/blog/red-lines-under-the-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/

### 2.3 Illinois BIPA (Biometric Information Privacy Act)

BIPA (740 ILCS 14/) is the most stringent US biometric privacy law, enacted in 2008. It is unique among US biometric laws for its **private right of action**, with damages of $1,000 per negligent violation and $5,000 per intentional or reckless violation.

#### Key Requirements

Before collecting biometric identifiers, a private entity must:

1. **Inform the subject in writing** that a biometric identifier or biometric information is being collected or stored.
2. **Inform the subject in writing** of the specific purpose and length of term for which the data is being collected, stored, and used.
3. **Receive a written release** executed by the subject (or their legally authorized representative).

Additional requirements:
- Develop a **written, publicly available retention schedule and destruction policy**.
- Destroy biometric data when the initial purpose is satisfied or within 3 years of the individual's last interaction, whichever occurs first.
- **Never sell, lease, trade, or otherwise profit from** biometric identifiers.
- Do not disclose biometric data except under narrow circumstances (warrant, financial transaction completion, identification in case of disappearance/death with consent).
- Use **reasonable care** to store, transmit, and protect biometric data.

#### BIPA Definitions

- **Biometric identifier:** "A retina or iris scan, fingerprint, voiceprint, or scan of hand or face geometry."
- **Biometric information:** "Any information based on an identifier used to identify an individual."

#### The On-Device Exception -- *G.T. v. Samsung Electronics America* (7th Cir. 2026)

**This is the most important case for Halbert's architecture.** The Seventh Circuit held that a company does not "possess" or "collect" biometric data merely by supplying software that creates or processes such data on a user's own device.

Key holdings:
- "Possessing, collecting, capturing, and obtaining biometric data under BIPA all require the defendant to have some degree of control over that data."
- Samsung did not violate BIPA by preinstalling a Gallery app that generated and stored face templates on users' phones, because the data remained on the user's device and Samsung never had access to it.
- This represents a significant development for device manufacturers, app developers, and other companies whose products generate biometric data on user hardware.

**Implication for Halbert:** As long as Halbert processes CV data entirely on-device and never transmits biometric data to Halbert's servers, BIPA's collection, consent, and retention requirements likely do not apply. However, this is a Seventh Circuit decision and may not be followed in Illinois state courts where most BIPA cases are filed. Caution is warranted.

- Source: https://law.justia.com/codes/illinois/chapter-740/act-740-ilcs-14/
- Source: https://regulome.io/regulations/illinois-bipa
- Source: https://www.mayerbrown.com/en/insights/publications/2026/08/seventh-circuit-holds-that-bipa-does-not-reach-biometric-data-that-remains-on-a-users-device
- Source: https://rsmus.com/insights/services/risk-fraud-cybersecurity/what-you-need-to-know-about-the-illinois-biometric-privacy-act--.html

#### BIPA Amendment (SB 2979, August 2024)

The 2024 amendment clarified that a single instance of collecting the same biometric identifier from the same person using the same method constitutes a single violation (not per-scan), significantly reducing potential damages in class actions. However, the core consent and disclosure requirements remain unchanged.
- Source: https://www.ilga.gov/Legislation/PublicActs/PrinterFriendly/103-0769

### 2.4 Texas CUBI (Capture or Use of Biometric Identifier Act)

Texas Business and Commerce Code Chapter 503 (CUBI) regulates biometric identifiers for commercial purposes.

#### Key Requirements

- **Inform the individual before capturing** a biometric identifier.
- **Obtain the individual's consent** prior to capture.
- **Do not sell, lease, or disclose** biometric identifiers except under narrow circumstances (law enforcement warrant, financial transaction completion, identification in disappearance/death with consent).
- **Protect** biometric identifiers using reasonable care.
- **Destroy** biometric identifiers within a reasonable time, no later than **1 year** after the purpose of collection has expired.

#### Key Differences from BIPA

- **No private right of action.** Only the Texas Attorney General can enforce CUBI, with civil penalties up to $25,000 per violation.
- **No publicly available retention policy requirement.**
- **Narrower disclosure rules** -- even with consent, disclosure is only permitted under four specific circumstances.
- **Definition is narrower:** "retina or iris scan, fingerprint, voiceprint, or record of hand or face geometry." Notably, CUBI was amended to include "artificial intelligence system" definitions.
- Source: https://statutes.capitol.texas.gov/?artSec=&chapter=BC.503&code=BC&tab=1
- Source: https://www.texasattorneygeneral.gov/consumer-protection/file-consumer-complaint/consumer-privacy-rights/biometric-identifier-act
- Source: https://www.biometricupdate.com/202208/beyond-bipa-mitigating-biometric-data-legal-risks-under-texas-and-washington-biometrics-laws

### 2.5 Washington State (RCW 19.375)

#### Key Requirements

- **Provide notice, obtain consent, or provide a mechanism to prevent subsequent use** before enrolling a biometric identifier in a database for a commercial purpose.
- **Do not sell, lease, or disclose** biometric identifiers for commercial purposes without consent, unless disclosure is necessary to provide a subscribed product/service, complete a financial transaction, or is required by law.
- **No specific retention timeline** (unlike BIPA's 3 years or CUBI's 1 year).

#### Key Differences

- **No private right of action.** Enforced by the Washington Attorney General under the Consumer Protection Act.
- **Definition excludes photographs:** "Biometric identifier does not include a physical or digital photograph, video or audio recording or data generated therefrom."
- **Notice can be non-consent-based:** Notice alone (without affirmative consent) can satisfy the requirement if a mechanism to prevent subsequent use is provided.
- Source: https://app.leg.wa.gov/RCW/default.aspx?cite=19.375&full=true
- Source: https://www.biometricupdate.com/202208/beyond-bipa-mitigating-biometric-data-legal-risks-under-texas-and-washington-biometrics-laws

### 2.6 California CCPA/CPRA

#### Biometric Information Definition

CCPA defines biometric information broadly: "an individual's physiological, biological, or behavioral characteristics... that is used or is intended to be used singly or in combination with each other or with other identifying data, to establish individual identity." This includes "imagery of the iris, retina, fingerprint, face, hand, palm, vein patterns, and voice recordings, from which an identifier template, such as a faceprint, a minutiae template, or a voiceprint, can be extracted."

#### Key Provisions

- Biometric information is classified as **personal information** under CCPA (Section 1798.140(v)(1)(E)).
- Under CPRA, biometric information used for the purpose of uniquely identifying a consumer is classified as **sensitive personal information**, giving consumers the right to limit its use.
- **"Publicly available" does not mean biometric information collected by a business about a consumer without the consumer's knowledge.** (Section 1798.140(v)(2)(ii))
- Businesses must provide notice of collection, allow deletion requests, and honor opt-out of sale/sharing.
- Source: https://cppa.ca.gov/pdf/20260101_ccpa_statute.pdf
- Source: https://law.justia.com/codes/california/code-civ/division-3/part-4/title-1-81-5/section-1798-140/

### 2.7 Other State Biometric Privacy Laws

As of 2026, only Illinois (BIPA), Texas (CUBI), and Washington have stand-alone biometric statutes. Approximately twenty additional states protect biometric data as sensitive data under broader consumer privacy laws (e.g., Colorado, Connecticut, Virginia, Utah). The remaining states cover biometric data only through data-breach notification rules. There is no federal biometric privacy law.
- Source: https://www.recordinglaw.com/us-laws/data-privacy-laws/biometric-privacy-laws/

### 2.8 How These Laws Apply to a Local, On-Device CV System

| Law | Applies to On-Device Processing? | Key Condition |
|---|---|---|
| GDPR Art. 9 | Potentially -- if biometric identification is performed | Requires explicit consent; on-device processing reduces but does not eliminate obligations |
| EU AI Act Art. 5 | Yes -- prohibits emotion recognition in workplace/education regardless of where processing occurs | Must avoid these features entirely |
| Illinois BIPA | Likely NOT (per *Samsung* 7th Cir. 2026) -- if data never leaves the user's device | On-device processing is the key defense; caution in Illinois state courts |
| Texas CUBI | Potentially -- if "commercial purpose" and "capture" occurs | On-device processing may not constitute "capture" by the developer |
| Washington RCW 19.375 | Potentially -- if "enrollment in a database for commercial purpose" | Excludes photographs/video recordings from definition |
| CCPA/CPRA | Yes -- if Halbert is a "business" collecting consumer data | On-device processing may not constitute "collection" by the business; but cloud mode changes this |

**The critical legal architecture principle:** Halbert, as the software developer, does not "possess," "collect," or "control" biometric data that is processed entirely on the user's device. The user is the data controller. This distinction is what makes local-first processing legally defensible. **Cloud API mode breaks this shield** -- when frames are transmitted to a cloud LLM, the cloud provider (and potentially Halbert as the intermediary) becomes a processor/controller subject to full biometric privacy law obligations.

---

## 3. Screen Capture Legality

### 3.1 Legal Considerations of Screen Recording/Capture for AI Assistants

Screen capture involves copying the visual contents of a display, which may contain:
- Personal data (user's files, messages, browsing history)
- Confidential business information
- Third-party copyrighted content
- Credentials, passwords, API keys (if visible)
- Other people's communications (if screen-sharing or video calls are visible)

#### Key Legal Frameworks

1. **Federal Wiretap Act (18 U.S.C. Section 2511):** Prohibits interception of electronic communications. Screen capture of visual-only content (no audio) generally falls outside the Wiretap Act. However, if screen capture includes audio (e.g., from a video call), wiretap laws may apply.

2. **Electronic Communications Privacy Act (ECPA, 1986):** Governs interception of electronic communications. Screen capture of one's own screen is generally permissible. Capturing others' screens without authorization may violate ECPA.

3. **State wiretapping/privacy laws:** Vary significantly. See Section 4.3 on one-party vs. all-party consent.

4. **Copyright law:** Screen capture of copyrighted content (e.g., streaming video, documents) for personal use is generally fair use, but redistribution may infringe.

### 3.2 Consent Requirements for Screen Capture

#### Capturing Your Own Screen

Capturing your own screen is generally legal. You are the owner/operator of the device and have authority over its display. This is the primary use case for Halbert -- the user captures their own screen for the AI assistant to analyze.

#### Capturing Others' Screens

Capturing someone else's screen without authorization may constitute:
- Unauthorized access under the Computer Fraud and Abuse Act (CFAA)
- Invasion of privacy (intrusion upon seclusion)
- Violation of state surveillance laws

**Halbert should only capture the user's own screen, never remote or shared screens without explicit authorization.**

### 3.3 Workplace Monitoring Laws

If Halbert is used in a professional setting, screen capture may implicate workplace monitoring laws:

#### Federal Law

- **ECPA business-purpose exception (18 U.S.C. Section 2511(2)(a)(i)):** Employers may monitor electronic communications on company-owned devices when monitoring serves a legitimate business purpose.
- **Consent exception (18 U.S.C. Section 2511(2)(d)):** Monitoring is permitted when at least one party consents. The employer, as device owner, satisfies this.
- Federal law does not require employers to notify employees before deploying screen monitoring.

#### State Law

- **Connecticut (Conn. Gen. Stat. Section 31-48d):** Requires employers to give employees prior written notice of electronic monitoring.
- **Delaware (Del. Code Title 19, Section 705):** Requires employee consent before monitoring.
- **New York (NY Labor Law Section 52-c):** Requires employers to notify employees of electronic monitoring, including by mail, email, or written acknowledgment.
- **California:** Employers must notify employees before tracking them.

#### Implications for Halbert

Halbert is a user-installed tool, not an employer-deployed monitoring system. However, if an employer installs Halbert on company devices and enables screen capture, the employer (not Halbert) is responsible for compliance with workplace monitoring notice laws. Halbert should:
- Include documentation noting that workplace use may require employer compliance with state monitoring notice laws.
- Not be marketed as an employee monitoring tool.
- Source: https://www.nelsonmullins.com/insights/blogs/the-hr-minute/employee-privacy/electronic-workplace-monitoring-privacy-compliance-and-risk-management-considerations-for-employers
- Source: https://www.employee-monitoring.net/compliance/is-screen-recording-employees-legal
- Source: https://www.worktime.com/blog/statistics/employee-monitoring-laws-by-state

### 3.4 macOS Screen Recording Permissions

#### TCC (Transparency, Consent, and Control) Framework

macOS uses the TCC framework to manage privacy-sensitive permissions, including screen recording (`kTCCServiceScreenCapture`).

Key characteristics:
- **First-grant requires app relaunch:** ScreenCaptureKit (`SCShareableContent`, `SCStream`, `SCScreenshotManager`) does NOT begin working in the same process that the user grants permission in. The OS only attaches the new TCC decision to the next process launch. The app must be quit and reopened.
- **Sandboxed apps are supported:** Unlike the Accessibility API, ScreenCaptureKit works in sandboxed apps once TCC is granted.
- **Info.plist:** Adding `NSScreenRecordingUsageDescription` does nothing -- the OS fills in the dialog from `CFBundleDisplayName`.
- **TCC database:** Stored at `~/Library/Application Support/com.apple.TCC/TCC.db` (user-level) and `/Library/Application Support/com.apple.TCC/TCC.db` (system-level). Protected by SIP.
- Source: https://apple-docs.everest.mt/docs/sample-code/screencapturekit/capturing-screen-content-in-macos/
- Source: https://www.screenify.studio/blog/2026-04-23-macos-screen-recording-permissions

#### macOS Sequoia (15.x) Changes

- **Monthly re-authorization:** macOS Sequoia prompts users to re-confirm screen recording permissions on a monthly basis, increasing user awareness of which apps have continuous screen access.
- **Code signing requirement:** `CGPreflightScreenCaptureAccess()` requires a binary signed with a valid Apple Developer ID certificate (with a Team ID). Ad-hoc signing (`codesign --sign "-"`) does not satisfy this requirement on Sequoia. This is a regression from earlier macOS versions.
- **Implication for Halbert:** Halbert's macOS distribution must be properly code-signed with an Apple Developer ID for screen recording to work on Sequoia and later.
- Source: https://github.com/CapSoftware/Cap/issues/1722
- Source: https://tryskilly.app/learn/enable-screen-recording-permissions-macos/

#### Permission Flow

1. App calls ScreenCaptureKit or CGWindowList API.
2. macOS checks the TCC database for an existing permission entry.
3. If no entry exists, macOS shows a permission dialog to the user.
4. The user's choice (Allow or Deny) is stored in the TCC database.
5. The app must be restarted for the permission to take effect.

### 3.5 Linux Screen Capture Permissions

#### X11

On X11, any application can capture the screen by default using the X11 protocol (e.g., `XGetImage`, `XShmGetImage`). There is no built-in permission prompt. This is a known security weakness of X11 -- any running application can see the entire screen contents.

**Implication for Halbert:** On X11, Halbert can capture the screen without OS-level permission prompts. Halbert should implement its own consent flow as a compensating control.

#### Wayland

Wayland's security architecture forbids unauthorized access to other windows. No capture API is provided by Wayland itself. Applications must explicitly request user authorization through:

- **xdg-desktop-portal:** A D-Bus API that provides standardized, desktop-environment-independent access to screen capture and other features.
  - **ScreenCast interface (`org.freedesktop.portal.ScreenCast`):** Returns a PipeWire stream handle for the selected screen or window.
  - **Screenshot interface (`org.freedesktop.portal.Screenshot`):** Takes a single screenshot with user-selected target (screen, window, area, active window).
  - The portal shows a native dialog where the user selects what to share (specific monitor, specific window, or specific region).
  - Permission can be remembered (stored in portal's permission store) to skip the dialog on subsequent requests.
  - GNOME Settings and KDE system settings both provide UI to manage these permissions.

- **Backends:** Different desktop environments provide different backends:
  - GNOME: `xdg-desktop-portal-gnome`
  - KDE: `xdg-desktop-portal-kde`
  - wlroots-based (Sway, Hyprland): `xdg-desktop-portal-wlr`
  - Deepin: `xdg-desktop-portal-deepin`

**Implication for Halbert:** On Wayland, Halbert should use the xdg-desktop-portal ScreenCast API, which provides a native, user-mediated consent flow. This is the privacy-correct approach and aligns with Wayland's security model.
- Source: https://wiki.archlinux.org/title/XDG_Desktop_Portal
- Source: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html
- Source: https://github.com/DafabHoid/libscreencapture-wayland

### 3.6 Differences: Capturing Your Own Screen vs. Others'

| Scenario | Legal Status | OS Permission Required |
|---|---|---|
| Capturing your own full screen | Legal (you control the device) | macOS: TCC; Wayland: portal; X11: none |
| Capturing a specific app window you own | Legal | macOS: TCC (per-app); Wayland: portal (window selection) |
| Capturing a screen-shared window from a video call | Depends on consent of other participants | OS-level permission covers technical access; legal consent is separate |
| Capturing a remote/other person's screen | Potentially illegal (CFAA, state laws) | N/A -- Halbert should not support this |
| Employer capturing employee screens | Legal with notice (varies by state) | OS-level permission; employer compliance separate |

---

## 4. Webcam & Camera Access Legal Considerations

### 4.1 Consent Requirements for Camera-Based CV

#### Self-Capture (User Points Camera at Themselves or Their Own Environment)

When the user is the only person captured, consent is implicit -- the user is both the captor and the subject. This is analogous to taking a selfie. However:

- If the webcam frame is processed for **biometric identification** (e.g., face recognition for login), GDPR Article 9 and state biometric laws apply.
- If the webcam frame is processed for **non-identification purposes** (e.g., reading a gauge, detecting if a person is present, OCR of text in view), it is personal data but not necessarily biometric data.

#### Capturing Others

When the webcam captures other people (family members, visitors, people in public), additional legal considerations arise:

- **Reasonable expectation of privacy:** People in private spaces (homes, bathrooms, bedrooms) have a reasonable expectation of privacy. Capturing them without consent may violate privacy laws.
- **Public spaces:** Recording video in public is generally legal, but audio recording is subject to one-party/all-party consent rules (see Section 4.3).
- **BIPA and state biometric laws:** If the camera captures faces and the system performs facial recognition, BIPA and similar laws apply to each captured individual, not just the user.

### 4.2 When Is Camera Processing Considered "Surveillance"?

Camera processing crosses into "surveillance" territory when:

1. **Continuous or always-on capture:** If the camera is continuously capturing without explicit user initiation for each capture session.
2. **Capture of non-consenting individuals:** If the camera captures people who are not aware of or have not consented to the capture.
3. **Purpose is monitoring:** If the primary purpose is to monitor, track, or observe individuals rather than to perform a specific, user-initiated task.
4. **Remote access:** If captured data is transmitted to a remote location for processing or storage.

**Halbert's design principle should be:** Camera access is **session-based, user-initiated, and task-specific.** The camera is only active when the user explicitly starts a CV session for a defined purpose (e.g., "read this gauge," "describe what's on my desk"). There is no always-on or ambient camera mode.

The EDPB Guidelines on video devices emphasize that "real-time monitoring may also be more intrusive than storing and automatically deleting material after a limited timeframe" (paragraph 29). This suggests that even if Halbert does not store frames, continuous real-time processing is more intrusive than periodic, user-initiated capture.

### 4.3 One-Party vs. Two-Party (All-Party) Consent for Audio/Visual Recording

#### Federal Baseline

The Federal Wiretap Act (18 U.S.C. Section 2511(2)(d)) establishes **one-party consent** as the national baseline: you can record any conversation you are a party to without notice to the other side.

#### State Variations

- **One-party consent (37 jurisdictions):** 36 states plus DC. Your own consent as a participant is sufficient. States include: Alabama, Alaska, Arizona, Arkansas, Colorado, Georgia, Idaho, Indiana, Iowa, Kansas, Kentucky, Louisiana, Maine, Michigan, Minnesota, Mississippi, Missouri, Nebraska, Nevada, New Jersey, New Mexico, New York, North Carolina, North Dakota, Ohio, Oklahoma, Rhode Island, South Carolina, South Dakota, Tennessee, Texas, Utah, Virginia, West Virginia, Wisconsin, Wyoming, plus DC.

- **All-party consent (9 states):** California, Florida, Illinois, Maryland, Massachusetts, Montana, New Hampshire, Pennsylvania, and Washington. Every person in the conversation must consent before recording.

- **Hybrid states (5):** Connecticut, Delaware, Hawaii, Maine, and Oregon. The rule flips depending on whether it is a phone call or in-person recording.

#### Application to Halbert

- **Video-only (no audio):** Video recording without audio is generally not governed by wiretap laws, which focus on "oral communications" and "electronic communications." However, some states have broader privacy statutes.
- **Video with audio:** If Halbert captures audio alongside video (e.g., for a multimodal AI assistant), all-party consent states require consent from everyone whose audio is captured.
- **Best practice:** Halbert should default to **video-only capture** (no audio) for CV features. If audio is needed, it should be a separate, explicitly enabled feature with appropriate consent warnings, especially in all-party consent states.
- Source: https://www.recordinglaw.com/united-states-recording-laws/
- Source: https://www.recordinglaw.com/us-laws/is-it-illegal-to-record-someone/
- Source: https://cctvinfo.com/guides/cctv-laws-usa

### 4.4 Local Processing vs. Transmitting Frames

| Factor | Local-Only Processing | Cloud API Transmission |
|---|---|---|
| GDPR Art. 9 | On-device biometric processing may not constitute "processing" by Halbert (user is controller) | Halbert becomes a processor/controller; full Article 9 compliance required |
| BIPA | Likely not applicable (per *Samsung* 7th Cir. 2026) -- data never leaves device | BIPA applies -- Halbert "collects" by transmitting to cloud |
| CCPA/CPRA | May not constitute "collection" by the business | Constitutes "collection" and "disclosure" -- full CCPA rights apply |
| Wiretap laws | User captures their own data; one-party consent satisfied | Transmission may constitute "interception" if not properly secured |
| Data breach risk | Minimal -- data never leaves device | High -- frames in transit and on cloud servers are potential breach targets |
| User trust | High -- aligns with "sovereign by design" principle | Lower -- requires trust in cloud provider's data practices |

### 4.5 Children's Privacy (COPPA)

The Children's Online Privacy Protection Act (COPPA, 15 U.S.C. 6501 et seq.) applies to operators of commercial websites or online services directed to children under 13 that collect personal information.

#### 2025 COPPA Rule Amendments

The FTC's 2025 amendments to the COPPA Rule added **biometric identifiers** to the definition of "personal information":
- "Personal information" now includes "government-issued identifiers and biometric identifiers that can be used for the automated or semi-automated recognition of an individual."
- A "photograph, video, or audio file, where such file contains a child's image or voice" remains personal information.
- Source: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions
- Source: https://www.govinfo.gov/content/pkg/FR-2025-04-22/html/2025-05904.htm

#### Application to Halbert

- Halbert is not directed to children under 13 and is not a "website or online service" in the traditional COPPA sense.
- However, if Halbert's webcam captures images of children (e.g., a user's family members), and those images are transmitted to a cloud service, COPPA-like concerns arise.
- **Best practice:** Halbert should include a warning in its CV consent flow: "If your camera may capture images of children, do not enable cloud transmission of visual data. Local-only processing is recommended."
- Halbert should not be marketed to or configured for use by children under 13.

---

## 5. Privacy Best Practices for CV-Enabled Apps

### 5.1 Privacy-by-Design Principles for CV Features

The seven foundational principles of Privacy-by-Design (developed by Ann Cavoukian, former Information and Privacy Commissioner of Ontario) apply directly to CV:

1. **Proactive not reactive; preventive not remedial:** Design CV features with privacy protections built in from the start, not added later.
2. **Privacy as the default setting:** CV features should be OFF by default. The user must explicitly opt in.
3. **Privacy embedded into design:** Privacy measures are integral to the CV system, not bolted on.
4. **Full functionality -- positive-sum, not zero-sum:** Privacy and functionality coexist; do not sacrifice privacy for CV capability.
5. **End-to-end security -- full lifecycle protection:** From capture to processing to deletion, data is protected at every stage.
6. **Visibility and transparency:** Users can see when CV is active, what is being captured, and how it is processed.
7. **Respect for user privacy:** Keep user interests front and center; empower users with control.

The NIST Privacy Framework reinforces these principles: "privacy protection should allow for individual choices, as long as effective privacy risk mitigations are already engineered into products and services."
- Source: https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.01162020.pdf

### 5.2 Default-Off vs. Default-On

**Recommendation: All CV features must be default-OFF.**

This is non-negotiable for legal compliance and user trust:

- **GDPR:** Consent must be "freely given, specific, informed, and unambiguous." Pre-ticked boxes and default-on settings do not constitute valid consent.
- **BIPA:** Requires informed written consent before collection. Default-on would violate this.
- **CCPA/CPRA:** Sensitive personal information (including biometric data) requires explicit opt-in.
- **EU AI Act:** While not explicitly requiring default-off, the risk-based approach strongly favors user control.
- **OS-level permission frameworks:** Both macOS TCC and Wayland portals default to "not granted" -- the user must explicitly approve.

### 5.3 Granular Permissions

**Recommendation: Separate permissions for each CV modality and scope.**

| Permission | Description | Granularity |
|---|---|---|
| Screen capture -- full display | Capture the entire screen | Per-display |
| Screen capture -- specific window | Capture a single application window | Per-window, per-session |
| Screen capture -- specific region | Capture a defined screen region | Per-region, per-session |
| Webcam -- front camera | Access the front-facing camera | Per-session |
| Webcam -- external camera | Access an external USB camera | Per-session |
| Cloud transmission -- visual data | Send visual frames to a cloud LLM | Per-session, per-provider |
| Cloud transmission -- screen data | Send screen captures to a cloud LLM | Per-session, per-provider |

Research supports this approach. The "Recognizer Abstraction" model from Columbia University proposes that applications request permissions at the granularity of semantic objects (e.g., "only detects faces") rather than raw sensor access. The Erebus access control framework for AR systems advocates for:
- **G1: Regulating direct access to sensors** -- apps should not access raw camera feeds directly.
- **G2: Minimizing function-level over-privilege** -- apps should only access APIs matching their functional requirement.
- **G3: Minimizing attribute-level over-privilege** -- users should be able to review and adjust accesses.
- Source: https://www.cs.columbia.edu/~suman/docs/suman_usenix13.pdf
- Source: http://amir.rahmati.com/dl/usenixsec23/erebus_usenixsec.pdf

### 5.4 Visual Indicators When CV Is Active

**Recommendation: Always show a clear, non-dismissable visual indicator when any CV modality is active.**

#### Platform-Provided Indicators

- **macOS:** Green dot in the status bar when the camera is active. Orange dot when the microphone is active. These are OS-level and cannot be suppressed.
- **Android 16:** Green icon in the status bar when camera or microphone is active; tapping shows which app is using the sensor.
- **iOS/macOS:** Green dot (camera) or orange dot (microphone) in the top right corner.

#### Halbert-Specific Indicators

In addition to OS-provided indicators, Halbert should implement:

1. **In-app recording indicator:** A persistent, non-dismissable banner or icon in the Halbert UI showing "Screen capture active" or "Camera active" with a red dot or similar visual cue.
2. **System tray/menu bar icon:** On macOS, a menu bar icon that changes appearance when CV is active. On Linux, a system tray icon or notification.
3. **Desktop notification on start/stop:** A system notification when CV capture begins and ends, so the user is always aware of the capture window.
4. **Audio cue (optional):** A subtle sound when CV capture starts and stops, for users who may not be looking at the screen.

#### Industry Precedent: Meta Ray-Ban AI Glasses

Meta's AI glasses use a **capture LED** -- a front-facing white light that blinks when content is being captured. Key design choices:
- The LED has no off switch.
- Blocking the LED disables the camera (hardware tamper detection).
- Second-generation glasses disable the camera when LED tampering or destruction is detected.
- Meta distinguishes between "Active Capture" (photos/videos saved for later) and "AI Features" (visual understanding for AI assistance, not saved). For AI features, Meta explored different signaling approaches since the data is not saved.
- Source: https://about.fb.com/wp-content/uploads/2026/07/Bystander-Privacy.pdf
- Source: https://truescho.com/en/blog/meta-ai-glasses-capture-led-2026

#### Microsoft HLK Requirements

Microsoft's Hardware Lab Kit (HLK) requires that a visible indicator LED be ON when the camera's image signal processor (ISP) is capturing sensor data. This is a hardware-level requirement for Windows-certified cameras.
- Source: https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-privacy-controls

### 5.5 Data Retention Policies for Visual Frames

**Recommendation: Zero-retention of raw visual frames. Process in memory, never write to disk.**

#### Architecture

1. **Process, don't store:** Visual frames go into the CV pipeline, semantic extraction happens, and frames are immediately discarded from memory. Nothing is written to disk.
2. **Ephemeral processing:** Processing happens in RAM only. No swap file usage for frame buffers (configure `mlock` or equivalent to prevent paging).
3. **No logging of frame content:** Logs should never contain raw pixel data, base64-encoded frames, or visual content. Logs may contain metadata (e.g., "CV session started at 14:32:01, ended at 14:32:15, 14 frames processed").
4. **Derived data only:** Only the semantic output of CV processing (e.g., "I see a terminal showing an error message about disk space") should be retained, and only if the user explicitly saves the conversation.

#### EDPB Guidance on Retention

The EDPB Guidelines on video devices state:
- "Data controllers should proceed to the deletion of raw data (face images, speech signals, the gait, etc.) and ensure the effectiveness of this deletion."
- "If there is no longer a lawful basis for the processing, the raw data has to be deleted."
- "In case the data controller would need to keep such data, noise-additive methods (such as watermarking) must be explored."
- Source: https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201903_video_devices_en.pdf

#### Zero-Retention Architecture (Industry Best Practice)

The enterprise video privacy guide recommends:
- "Process, don't store: Video goes in, enhanced video comes out, nothing is retained. Processing happens in memory, not on disk."
- "Ephemeral infrastructure: Processing containers are created for each job and destroyed immediately after."
- "Verifiable deletion: When deletion happens, you can prove it with cryptographic certificates."
- "When your system is architecturally incapable of retaining data, compliance becomes automatic."
- Source: https://bettervideo.io/knowledge-base/enterprise-video-privacy-compliance-guide

### 5.6 On-Device Processing as Privacy Protection

On-device processing is the single most effective privacy protection for CV features:

1. **Legal shield:** The *Samsung* 7th Cir. decision establishes that on-device biometric processing may not constitute "collection" or "possession" by the software developer.
2. **GDPR minimization:** On-device processing aligns with Article 5(1)(c) data minimization -- data is processed and immediately discarded, never transmitted.
3. **No data breach risk:** Data that never leaves the device cannot be intercepted in transit or stolen from a server.
4. **User sovereignty:** Aligns with Halbert's "Sovereign by Design" principle -- the user retains complete control over their data.
5. **Reduced regulatory burden:** On-device processing may exempt Halbert from biometric privacy law obligations that would apply if data were transmitted.

### 5.7 Differential Privacy and Fuzzing Approaches for Visual Data

Several approaches can enhance privacy for visual data processing:

#### Edge Anonymization

- Anonymize visual data at the edge (on-device) before any processing or storage.
- Detect and blur faces, license plates, and other PII before the data enters the processing pipeline.
- "The moment a camera snaps an image, it must be anonymized at the edge before it enters your network database." -- AdaptNXT
- Source: https://www.adaptnxt.com/blogs/privacy-first-video-analytics-gdpr-compliance

#### Protective Perturbation

- Inject noise into images to prevent visual privacy exposure while preserving machine vision capability.
- "Protective perturbation-based approaches inject noises to the private images in order to prevent the visual privacy exposure to human vision while preserving the capability of machine vision to complete the machine learning services."
- Source: https://ar5iv.labs.arxiv.org/html/2409.01710

#### Learned Visual Transformations

- Train models to obscure sensitive or task-irrelevant information while retaining features essential for task performance.
- "The approach employs learned visual transformations that obscure sensitive or task-irrelevant information while retaining features essential for task performance."
- Source: https://doi.org/10.48550/arxiv.2512.09463

#### Differential Privacy for Federated Learning

- If Halbert ever implements model improvement through user data, use federated learning with differential privacy to ensure personal data remains protected.
- "Share updates securely using differential privacy, ensuring personal data remains protected."
- Source: https://github.com/ngeeyonglim/TikTokTechJam2025

#### Recommendation for Halbert

For the initial CV implementation, Halbert should:
1. Process frames on-device only (no cloud transmission by default).
2. Optionally apply face blurring/anonymization before processing if the use case does not require facial information.
3. Never store raw frames -- extract semantic content and discard.
4. If cloud transmission is enabled by the user, apply on-device anonymization (blur faces, redact text containing credentials) before transmission.

---

## 6. Existing Frameworks & Industry Guidelines

### 6.1 NIST Privacy Framework

The NIST Privacy Framework (version 1.1, aligned with CSF 2.0) is a voluntary tool for managing privacy risk through enterprise risk management.

#### Core Structure

The framework consists of three components:
1. **Core:** A set of privacy protection activities and outcomes organized into five functions:
   - **GOVERN-P (GV-P):** Establish organizational privacy governance.
   - **MAP-P (ID-P):** Develop organizational privacy understanding (system, product, or service).
   - **IDENTIFY-P (ID-P):** Identify privacy risks.
   - **CONTROL-P (PR-P):** Develop and implement controls.
   - **COMMUNICATE-P (CO-P):** Communicate privacy practices.
2. **Profiles:** Organization-specific sets of activities and outcomes.
3. **Tiers:** Levels of maturity (1-4) for each function.

#### Application to Halbert CV

- **MAP-P:** Map what visual data is collected (screen frames, webcam frames), how it is processed (on-device CV models), and what privacy risks exist (biometric data exposure, bystander capture).
- **CONTROL-P:** Implement controls (default-off, granular permissions, visual indicators, zero-retention, on-device processing).
- **COMMUNICATE-P:** Communicate privacy practices through in-app consent dialogs, privacy policy updates, and visual indicators.
- Source: https://www.nist.gov/privacy-framework
- Source: https://csrc.nist.gov/pubs/cswp/40/nist-privacy-framework-11/ipd
- Source: https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.01162020.pdf

### 6.2 ISO/IEC 27701 (Privacy Information Management)

ISO/IEC 27701:2025 is the international standard for Privacy Information Management Systems (PIMS). Key features:

- **Standalone certification:** As of the 2025 update, ISO 27701 can be certified independently of ISO 27001.
- **Role-based controls:** Organized into three categories -- PII controllers, PII processors, and joint controllers -- aligning with GDPR roles.
- **Mandatory privacy risk management:** The 2025 update makes privacy risk management mandatory.
- **Broader coverage:** Addresses modern privacy challenges including AI and emerging technologies.
- **Alignment with global regulations:** Helps demonstrate compliance with GDPR and other privacy laws.

#### Application to Halbert

While Halbert as a GPL-3.0 open-source project may not seek formal ISO certification, the framework provides useful guidance:
- Adopt a structured approach to privacy risk management for CV features.
- Clearly define Halbert's role: in local-only mode, the user is the PII controller and Halbert is a tool; in cloud mode, Halbert may be a PII processor.
- Implement controls for data minimization, purpose limitation, and storage limitation.
- Source: https://www.iso.org/standard/27701
- Source: https://www.dpocentre.com/blog/iso-27701-2025-whats-changed/

### 6.3 Ambient/Always-On CV Device Guidelines

There is no single industry standard for ambient/always-on CV devices, but several sources provide guidance:

#### EDPB Guidelines on Video Devices

The EDPB guidelines (Section 2.1) are the most authoritative European guidance on video processing:
- Require specific purpose specification before deployment.
- Mandate layered transparency (warning signs + detailed information).
- Emphasize data minimization and storage limitation.
- Note that real-time monitoring may be more intrusive than black-box (auto-delete) approaches.
- Source: https://www.edpb.europa.eu/documents/guideline/guidelines-32019-on-processing-of-personal-data-through-video-devices_en

#### Meta Responsible Innovation Principles

Meta's approach to AI glasses bystander privacy:
- Capture LED as a hardware-level signal to bystanders.
- Distinction between "Active Capture" (saved photos/videos) and "AI Features" (ephemeral visual understanding).
- Tamper detection that disables capture if the LED is covered.
- Source: https://about.fb.com/wp-content/uploads/2026/07/Bystander-Privacy.pdf

#### Multi-Layered Privacy Permission Framework (XR Research)

Research on extended reality (XR) privacy provides applicable guidance:
- **OS-level mediation is preferred over app-level:** "Standalone XR systems tend to implement standardized OS-level permission dialogs for accessing sensors like cameras, microphones, or eye tracking, requiring explicit user consent per app."
- **Hardware kill switches:** "Meta Quest OS enforces privacy by physically cutting power to external cameras and microphones under certain conditions, effectively providing a reliable hardware-based kill switch."
- **Principle of Least Privilege:** "Every program and every user of the system should operate using the least set of privileges necessary to complete the job."
- Source: https://www.mmi.ifi.lmu.de/pubdb/publications/pub/mansour2025nspw/mansour2025nspw.pdf

### 6.4 How Existing Products Handle Privacy Disclosures

#### Apple Face ID

- **On-device only:** "Face ID data -- including mathematical representations of your face -- is encrypted and protected with a key available only to the Secure Enclave."
- **Never leaves device:** "Face ID data does not leave your device, and is never backed up to iCloud or anywhere else."
- **Immediate frame deletion:** "The Secure Enclave immediately discards face images captured during normal operation after it calculates the mathematical representation."
- **User control:** "If you choose to enroll in Face ID, you can control how it is used or disable it at any time."
- **App isolation:** "Apps are notified only as to whether the authentication is successful. Apps can't access Face ID data associated with the enrolled face."
- **California disclosure:** Apple publishes a California Privacy Disclosures page listing biometric information as a category of personal information it may collect.
- Source: https://www.apple.com/legal/privacy/data/en/face-id/
- Source: https://support.apple.com/guide/security/facial-matching-security-sece151358d1/web
- Source: https://www.apple.com/legal/privacy/california/ca-privacy-disclosures.html

#### Windows Hello

- **Enhanced Sign-in Security (ESS):** Biometric data is processed in a "Virtual Secure Mode" (VSM) isolated process.
- **Biometric framework logging:** Event logs track biometric sensor enumeration and ESS status.
- **Multi-user handling:** "On multi-user devices, the lowest Windows Hello security posture applies."
- Source: https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/windows-hello-enhanced-sign-in-security

#### Google Nest

- **Encrypted transmission:** "End-to-end encrypted transmission for the streamed images to protect against unauthorized access."
- **Device-level encryption:** "Combined secure encryption method for encrypted videos in transit and rest."
- **User-configurable storage:** Multiple storage methods (local SD card, cloud) with user control.
- Source: https://trust.mi.com/docs/iot-privacy-white-paper-global/3/5

### 6.5 Privacy Policies of Existing CV-Enabled AI Products

#### Google Gemini Live

- **Data collected:** "Transcripts and recordings of your interactions with Gemini Live (including audio, video and screens you share with Live)."
- **Camera auto-off behavior:** Camera automatically turns off when Live is put on hold, when the user leaves the app, or when the screen locks. It does not automatically turn back on.
- **Bystander consent:** "Respect others' privacy and ask permission before recording or including them in a Live chat."
- **Gemini Apps Activity:** If enabled, Google saves chats, uploads, and related data, which may be used for model training. Can be turned off, but at the cost of losing chat history.
- Source: https://support.google.com/gemini/answer/13594961?hl=en
- Source: https://support.google.com/gemini/answer/15274899

#### OpenAI ChatGPT (Advanced Voice / Camera)

- **Camera access:** Manual permission only -- user must tap the "+" icon and select "Camera" or "Take Photo."
- **Data retention:** "Audio clips from Live and Advanced Voice, along with video clips from Advanced Voice, are stored with the transcript in chat history and retained for 30 days under its ChatGPT Voice data controls."
- **API platform:** "As of March 1, 2023, data sent to the OpenAI API is not used to train or improve OpenAI models (unless you explicitly opt in)."
- **Enterprise:** "By default, we do not use data from ChatGPT Enterprise, ChatGPT Business, ChatGPT Edu, ChatGPT for Healthcare, ChatGPT for Teachers, or our API platform -- including inputs or outputs -- for training or improving our models."
- **Zero Data Retention:** Eligible enterprise customers can be approved for Zero Data Retention or Modified Abuse Monitoring controls.
- **Encryption:** AES-256 at rest, TLS 1.2+ in transit.
- Source: https://developers.openai.com/api/docs/guides/your-data
- Source: https://openai.com/enterprise-privacy/
- Source: https://openai.com/business-data/
- Source: https://help.openai.com/en/articles/7039943-chatgpt-data-usage-faq

#### Key Takeaways for Halbert

| Practice | Google Gemini | OpenAI ChatGPT | Halbert Recommendation |
|---|---|---|---|
| Camera access | Manual, per-session | Manual, per-action | Manual, per-session (default-off) |
| Camera auto-off | On hold, app leave, screen lock | N/A (manual only) | On session end, app lose focus, screen lock |
| Frame retention | Stored with transcript (if Activity on) | 30 days for voice/video clips | Zero retention -- process and discard |
| Cloud training | Yes (unless Activity off) | No for API/Enterprise | Never -- Halbert does not train on user data |
| Bystander notice | "Ask permission before recording" | N/A | Visual indicator + in-app warning |
| Encryption | Google infrastructure | AES-256 at rest, TLS 1.2+ | On-device only (no transit by default) |

---

## 7. Recommended Privacy Gates & Defaults for Halbert

### 7.1 What Should Be Opt-In vs. Opt-Out

| Feature | Default | Rationale |
|---|---|---|
| Screen capture (any) | **Opt-in** | GDPR consent, OS permission, user control |
| Webcam capture (any) | **Opt-in** | Biometric privacy laws, GDPR Art. 9, user trust |
| Cloud transmission of visual data | **Opt-in (double opt-in)** | Transforms legal posture; requires explicit informed consent |
| Face detection (non-identifying) | **Opt-in** | Privacy-by-design; user should know when faces are processed |
| Face recognition (identifying) | **Opt-in (triple gate)** | Triggers GDPR Art. 9, BIPA, CCPA sensitive PI; requires written consent |
| Emotion recognition | **PROHIBITED** | EU AI Act Art. 5(1)(f) prohibits in workplace/education |
| Biometric categorization (race, gender, etc.) | **PROHIBITED** | EU AI Act Art. 5(1)(g) prohibits |
| Always-on / ambient camera | **PROHIBITED** | Constitutes surveillance; excessive privacy risk |
| Audio capture alongside video | **Opt-in (separate from video)** | All-party consent states require separate consent |
| Frame storage / logging | **Disabled (zero-retention)** | Data minimization; EDPB guidance |
| Visual indicators | **Always on (cannot be disabled)** | Transparency; Meta/Apple/Microsoft precedent |

### 7.2 Consent Dialogs Needed

#### Dialog 1: Initial CV Feature Enablement

When the user first attempts to enable any CV feature:

```
[Halbert CV Permission Request]

Halbert is requesting access to: [Screen Capture] / [Webcam]

What Halbert will do:
- Capture [screen content / camera frames] only when you explicitly start a CV session
- Process frames locally on your device using on-device models
- Immediately discard raw frames after processing -- nothing is stored
- Show a visual indicator whenever capture is active

What Halbert will NOT do:
- Store or save any visual frames
- Transmit visual data to any external server (unless you separately enable cloud mode)
- Perform facial recognition or biometric identification
- Monitor continuously or in the background

You can revoke this permission at any time in Settings > Privacy > Computer Vision.

[Allow] [Deny] [Learn More]
```

#### Dialog 2: Cloud Transmission Enablement

When the user attempts to enable cloud LLM mode for CV features (a separate, additional gate):

```
[Cloud Visual Data Transmission Warning]

You are about to enable cloud processing of visual data.

IMPORTANT: This changes Halbert's privacy posture.

When cloud visual mode is enabled:
- Visual frames (screen captures or camera images) will be sent to [Cloud Provider Name]
- This data will be processed on [Cloud Provider]'s servers, not your device
- [Cloud Provider]'s privacy policy and data retention practices will apply
- This may constitute "collection" or "processing" of biometric data under privacy laws (GDPR, BIPA, CCPA)
- If frames contain faces of other people, you may need their consent (especially in all-party consent states)

Halbert will apply on-device anonymization (face blurring, credential redaction) before transmission.

Recommendation: Use local-only CV processing whenever possible. Only enable cloud mode if you need capabilities that require a large vision-language model.

[I understand -- Enable Cloud Visual Mode] [Cancel] [Use Local-Only Instead]
```

#### Dialog 3: Per-Session CV Start

Each time a CV session begins:

```
[CV Session Starting]

Halbert is starting a [screen capture / camera] session.

- Capture target: [Full screen / Window: Terminal / Webcam]
- Processing: [Local only / Cloud: OpenAI GPT-4V]
- Duration: Until you stop the session or 5 minutes (auto-stop)

A visual indicator will be shown while capture is active.

[Start Session] [Cancel]
```

#### Dialog 4: Bystander Warning (Webcam Only)

When webcam capture starts and other people may be visible:

```
[Bystander Privacy Notice]

Your webcam is now active. If other people are visible in the camera frame:
- They may not have consented to being recorded
- In some states/countries, you may need their consent (especially for audio)
- Consider informing anyone visible that camera capture is active

[Continue] [Pause Camera]
```

### 7.3 Visual Indicators to Show

| Indicator | When Active | Implementation |
|---|---|---|
| Red dot in Halbert UI | Any CV session active | In-app overlay, non-dismissable |
| Menu bar / system tray icon change | Any CV session active | macOS: NSStatusItem with red variant; Linux: AppIndicator |
| Desktop notification on start | CV session begins | `osascript` (macOS) / `notify-send` (Linux) |
| Desktop notification on stop | CV session ends | Same as above |
| OS-provided camera indicator | Webcam active | macOS green dot (automatic); Linux varies by DE |
| Auto-stop timer countdown | CV session running | Subtle countdown in UI (5-minute default) |
| Cloud mode badge | Cloud transmission active | Distinct visual (e.g., cloud icon) in UI |

### 7.4 What Data Should Never Be Stored

| Data Type | Storage Policy | Rationale |
|---|---|---|
| Raw video frames | **NEVER store** | Data minimization; zero-retention architecture |
| Raw webcam images | **NEVER store** | Biometric data risk; EDPB raw data deletion guidance |
| Raw screen captures | **NEVER store** | May contain credentials, PII, confidential info |
| Face templates / faceprints | **NEVER store** (unless user explicitly enrolls for login) | BIPA/CCPA biometric data; high-risk |
| Biometric identifiers (any) | **NEVER store** | All biometric privacy laws require retention limits |
| Audio accompanying video | **NEVER store** | Wiretap law compliance; all-party consent states |
| CV processing logs with visual content | **NEVER store** | Logs should contain metadata only, never pixel data |
| Cloud-transmitted frame copies | **NEVER store locally after transmission** | No caching of transmitted frames |

### 7.5 What the Privacy Policy Should Say About CV Features

The existing `PRIVACY.md` should be augmented with a new section (suggested Section 2.4):

```markdown
### 2.4 Computer Vision Input (Screen Capture & Camera)

Halbert can optionally use computer vision (CV) to process visual input from
your screen or webcam. All CV features are **disabled by default** and require
your explicit opt-in.

**Local-Only CV Mode (Default):**
- When you enable CV features, Halbert captures screen content or webcam frames
  only during active, user-initiated CV sessions.
- All processing occurs on your local device using on-device models.
- Raw visual frames are processed in memory and immediately discarded. Halbert
  never writes raw frames, images, or video to disk.
- Halbert does not perform facial recognition, biometric identification, emotion
  recognition, or biometric categorization.
- A visual indicator is shown whenever CV capture is active.
- CV sessions auto-terminate after a configurable timeout (default: 5 minutes).

**Optional Cloud CV Mode:**
- If you explicitly enable cloud CV mode, visual frames may be sent to your
  configured cloud LLM provider (e.g., OpenAI, Anthropic, Google) for processing.
- This is a separate, additional consent gate beyond the initial CV enablement.
- Halbert applies on-device anonymization (face blurring, credential redaction)
  before transmitting frames.
- Your data transfer to the cloud provider is governed by your direct agreement
  with that provider.
- Enabling cloud CV mode may constitute "collection" or "processing" of
  biometric data under GDPR, BIPA, CCPA, and other privacy laws.

**What Halbert Never Does:**
- Never stores raw visual frames, images, or video.
- Never performs facial recognition or biometric identification.
- Never performs emotion recognition (prohibited by EU AI Act in
  workplace/education contexts).
- Never performs biometric categorization based on race, gender, or other
  protected attributes.
- Never captures audio alongside video by default.
- Never operates the camera in always-on or ambient mode.
- Never trains models on your visual data.
- Never transmits visual data to Halbert servers.

**Your Rights:**
- You can disable all CV features at any time in Settings > Privacy >
  Computer Vision.
- You can revoke OS-level screen recording and camera permissions through
  your operating system's privacy settings.
- Because Halbert does not store visual data, there is no data to delete
  or export -- your visual data is ephemeral by design.
```

### 7.6 Cloud API Mode vs. Local-Only Mode

#### Architecture Decision Matrix

| Aspect | Local-Only Mode | Cloud API Mode |
|---|---|---|
| **Legal classification** | User is data controller; Halbert is a tool | Halbert may be processor; cloud provider is processor/sub-processor |
| **GDPR Art. 9** | On-device processing may not trigger Art. 9 (per Recital 51, if no biometric identification) | Full Art. 9 compliance required; explicit consent mandatory |
| **BIPA** | Likely not applicable (per *Samsung* 7th Cir. 2026) | Applicable -- transmission constitutes "collection" |
| **CCPA/CPRA** | May not constitute "collection" by Halbert | Constitutes "collection" and "disclosure" |
| **Data breach risk** | Minimal | High -- frames in transit and on cloud servers |
| **Consent required** | OS-level permission + in-app opt-in | OS-level + in-app opt-in + cloud-specific opt-in + provider ToS |
| **Anonymization** | Optional (not needed for non-identification tasks) | Required -- blur faces, redact credentials before transmission |
| **Retention** | Zero (process and discard) | Governed by cloud provider's retention policy |
| **Encryption** | N/A (no transit) | TLS 1.2+ required for transit |
| **Visual indicator** | Standard CV indicator | Standard CV indicator + cloud mode badge |
| **Auto-stop** | 5-minute default | 5-minute default (or shorter) |

#### Implementation Recommendations for Cloud CV Mode

1. **Double opt-in:** User must first enable CV features, then separately enable cloud CV mode. These are two distinct consent gates.
2. **Provider-specific disclosure:** Show the specific cloud provider's data retention and privacy practices in the consent dialog.
3. **Pre-transmission anonymization:** Before sending any frame to the cloud:
   - Detect and blur human faces.
   - Redact text matching patterns for credentials (API keys, passwords, tokens).
   - Optionally redact other PII (email addresses, phone numbers, SSNs).
4. **Frame size reduction:** Downscale frames to the minimum resolution needed for the task, reducing data volume and PII exposure.
5. **No frame caching:** Do not cache transmitted frames locally. If retransmission is needed, re-capture.
6. **Session-scoped:** Cloud CV mode is enabled per-session, not globally. Each session requires explicit re-confirmation.
7. **Provider comparison:** Show users a comparison of cloud providers' data practices:
   - OpenAI API: No training on API data (as of March 1, 2023); abuse monitoring logs retained 30 days; Zero Data Retention available for eligible enterprise customers.
   - Google Gemini: Gemini Apps Activity may save data for training if enabled; can be disabled.
   - Anthropic: Opt-out from training available.
   - Source: https://developers.openai.com/api/docs/guides/your-data
   - Source: https://openai.com/enterprise-privacy/
   - Source: https://support.google.com/gemini/answer/13594961?hl=en

---

## 8. Summary of Legal Risk Matrix

| Risk Factor | Local-Only Mode | Cloud API Mode | Mitigation |
|---|---|---|---|
| GDPR Art. 9 (biometric data) | Low -- on-device, no identification | High -- transmission triggers processing | Avoid biometric identification; explicit consent; anonymization before transmission |
| EU AI Act Art. 5(1)(f) (emotion recognition) | **Prohibited** in workplace/education | **Prohibited** in workplace/education | Do not implement emotion recognition features |
| EU AI Act Art. 5(1)(g) (biometric categorization) | **Prohibited** | **Prohibited** | Do not implement biometric categorization |
| Illinois BIPA | Low -- *Samsung* 7th Cir. defense | High -- transmission = collection | Local-only by default; if cloud, obtain written consent, publish retention policy |
| Texas CUBI | Low -- on-device may not be "capture" | Medium -- transmission may be "disclosure" | Local-only by default; if cloud, inform and consent before capture |
| Washington RCW 19.375 | Low -- excludes photographs/video | Medium -- enrollment in database | Local-only by default; provide opt-out mechanism |
| CCPA/CPRA | Low -- may not be "collection" | High -- collection and disclosure | Local-only by default; provide notice, opt-out, deletion rights |
| COPPA (children) | Low -- not directed to children | Medium -- if children visible in frames | Warn users about capturing minors; do not transmit to cloud |
| Wiretap laws (audio) | Low -- video-only by default | High if audio included | Default to video-only; separate audio consent |
| Workplace monitoring | Low -- user-installed tool | Medium -- if employer-deployed | Document employer compliance obligations; not marketed as monitoring |
| macOS TCC | Handled by OS | Handled by OS | Leverage OS permission flow; do not circumvent |
| Linux Wayland portal | Handled by DE | Handled by DE | Use xdg-desktop-portal; do not bypass |
| Linux X11 (no portal) | No OS gate | No OS gate | Implement in-app consent as compensating control |
| Data breach | Minimal | High | Zero-retention; encryption in transit; no local caching |

---

## 9. References

### Laws & Regulations

1. **GDPR (Regulation 2016/679)** -- Article 9 (special categories): https://www.legislation.gov.uk/eur/2016/679/article/9?view=plain
2. **GDPR Recital 51** (photographs and biometric data): https://gdpr-info.eu/recitals/no-51/
3. **EU AI Act (Regulation 2024/1689)** -- Article 5 (prohibited practices): https://ai-act-service-desk.ec.europa.eu/en/ai-act/article-5
4. **EU AI Act full text**: https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?qid=1724745059760&uri=OJ%3AL_202401689
5. **Illinois BIPA (740 ILCS 14/)**: https://law.justia.com/codes/illinois/chapter-740/act-740-ilcs-14/
6. **BIPA SB 2979 amendment (2024)**: https://www.ilga.gov/Legislation/PublicActs/PrinterFriendly/103-0769
7. **Texas CUBI (Bus. & Com. Code Ch. 503)**: https://statutes.capitol.texas.gov/?artSec=&chapter=BC.503&code=BC&tab=1
8. **Washington RCW 19.375**: https://app.leg.wa.gov/RCW/default.aspx?cite=19.375&full=true
9. **California CCPA/CPRA**: https://cppa.ca.gov/pdf/20260101_ccpa_statute.pdf
10. **California Civil Code Section 1798.140**: https://law.justia.com/codes/california/code-civ/division-3/part-4/title-1-81-5/section-1798-140/
11. **Federal Wiretap Act (18 U.S.C. Section 2511)**: https://www.recordinglaw.com/us-laws/is-it-illegal-to-record-someone/
12. **ECPA (Electronic Communications Privacy Act)**: https://www.employee-monitoring.net/compliance/is-screen-recording-employees-legal
13. **COPPA (15 U.S.C. 6501 et seq.)** -- FTC FAQ: https://www.ftc.gov/business-guidance/resources/complying-coppa-frequently-asked-questions
14. **COPPA Rule 2025 amendments**: https://www.govinfo.gov/content/pkg/FR-2025-04-22/html/2025-05904.htm

### Regulatory Guidance

15. **EDPB Guidelines 3/2019 on processing of personal data through video devices**: https://www.edpb.europa.eu/documents/guideline/guidelines-32019-on-processing-of-personal-data-through-video-devices_en
16. **EDPB Guidelines 3/2019 (PDF)**: https://www.edpb.europa.eu/sites/default/files/files/file1/edpb_guidelines_201903_video_devices_en.pdf
17. **ICO -- How do we process biometric data lawfully?**: https://cy.ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/biometric-data-guidance-biometric-recognition/how-do-we-process-biometric-data-lawfully/
18. **ICO -- What is special category data?**: https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/lawful-basis/special-category-data/what-is-special-category-data/
19. **NIST Privacy Framework**: https://www.nist.gov/privacy-framework
20. **NIST Privacy Framework 1.1 (CSWP 40)**: https://csrc.nist.gov/pubs/cswp/40/nist-privacy-framework-11/ipd
21. **NIST Privacy Framework 1.0 (PDF)**: https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.01162020.pdf
22. **ISO/IEC 27701:2025**: https://www.iso.org/standard/27701
23. **ISO 27701:2025 update analysis**: https://www.dpocentre.com/blog/iso-27701-2025-whats-changed/

### Case Law

24. **G.T. v. Samsung Electronics America, Inc. (7th Cir. 2026)** -- BIPA does not reach biometric data on user's device: https://www.mayerbrown.com/en/insights/publications/2026/08/seventh-circuit-holds-that-bipa-does-not-reach-biometric-data-that-remains-on-a-users-device

### Platform Documentation

25. **Apple -- Face ID & Privacy**: https://www.apple.com/legal/privacy/data/en/face-id/
26. **Apple -- Facial matching security**: https://support.apple.com/guide/security/facial-matching-security-sece151358d1/web
27. **Apple -- California Privacy Disclosures**: https://www.apple.com/legal/privacy/california/ca-privacy-disclosures.html
28. **Apple -- Capturing screen content in macOS (ScreenCaptureKit)**: https://apple-docs.everest.mt/docs/sample-code/screencapturekit/capturing-screen-content-in-macos/
29. **Microsoft -- Windows Hello Enhanced Sign-in Security**: https://learn.microsoft.com/en-us/windows-hardware/design/device-experiences/windows-hello-enhanced-sign-in-security
30. **Microsoft -- Camera privacy controls (LED requirements)**: https://learn.microsoft.com/en-us/windows-hardware/drivers/stream/camera-privacy-controls
31. **xdg-desktop-portal -- Screenshot interface**: https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.Screenshot.html
32. **xdg-desktop-portal -- ArchWiki**: https://wiki.archlinux.org/title/XDG_Desktop_Portal
33. **libscreencapture-wayland**: https://github.com/DafabHoid/libscreencapture-wayland

### Industry Privacy Practices

34. **Google -- Gemini Apps Privacy Hub**: https://support.google.com/gemini/answer/13594961?hl=en
35. **Google -- Gemini Live camera/screen sharing**: https://support.google.com/gemini/answer/15274899
36. **OpenAI -- Data controls in the platform**: https://developers.openai.com/api/docs/guides/your-data
37. **OpenAI -- Enterprise privacy**: https://openai.com/enterprise-privacy/
38. **OpenAI -- Business data privacy**: https://openai.com/business-data/
39. **OpenAI -- Consumer data usage FAQ**: https://help.openai.com/en/articles/7039943-chatgpt-data-usage-faq
40. **Meta -- Bystander Privacy (AI Glasses)**: https://about.fb.com/wp-content/uploads/2026/07/Bystander-Privacy.pdf
41. **Meta AI Glasses Capture LED analysis**: https://truescho.com/en/blog/meta-ai-glasses-capture-led-2026
42. **Xiaomi -- Mi Camera and Privacy**: https://trust.mi.com/docs/iot-privacy-white-paper-global/3/5

### Privacy-by-Design & CV Privacy Research

43. **VeraSafe -- GDPR, Photographs, and Special Categories**: https://verasafe.com/blog/gdpr-and-photographs-understanding-special-categories-of-personal-data/
44. **AdaptNXT -- Privacy-First Video Analytics**: https://www.adaptnxt.com/blogs/privacy-first-video-analytics-gdpr-compliance
45. **BetterVideo -- Enterprise Video Privacy & Compliance**: https://bettervideo.io/knowledge-base/enterprise-video-privacy-compliance-guide
46. **The Neural Base -- GDPR for image processing**: https://theneuralbase.com/opencv/learn/advanced/gdpr-for-image-processing/
47. **Aragorn -- Privacy-Enhancing System for Mobile Cameras**: https://arch.cs.ucdavis.edu/assets/papers/imwut24-aragorn.pdf
48. **Erebus -- Access Control for AR Systems**: http://amir.rahmati.com/dl/usenixsec23/erebus_usenixsec.pdf
49. **Recognizer Abstraction (Columbia University)**: https://www.cs.columbia.edu/~suman/docs/suman_usenix13.pdf
50. **Multi-Layered Privacy Permission Framework for XR**: https://www.mmi.ifi.lmu.de/pubdb/publications/pub/mansour2025nspw/mansour2025nspw.pdf
51. **Protective Perturbation for Multimedia**: https://ar5iv.labs.arxiv.org/html/2409.01710
52. **Privacy-Preserving CV for Industry**: https://doi.org/10.48550/arxiv.2512.09463

### State Law References

53. **Biometric Privacy Laws by State (2026)**: https://www.recordinglaw.com/us-laws/data-privacy-laws/biometric-privacy-laws/
54. **US Recording Laws by State (2026)**: https://www.recordinglaw.com/united-states-recording-laws/
55. **Employee Monitoring Laws by State**: https://www.worktime.com/blog/statistics/employee-monitoring-laws-by-state
56. **Texas AG -- Biometric Identifier Act**: https://www.texasattorneygeneral.gov/consumer-protection/file-consumer-complaint/consumer-privacy-rights/biometric-identifier-act
57. **Regulome -- Illinois BIPA Compliance Guide**: https://regulome.io/regulations/illinois-bipa
58. **RSM -- BIPA Overview**: https://rsmus.com/insights/services/risk-fraud-cybersecurity/what-you-need-to-know-about-the-illinois-biometric-privacy-act--.html
59. **Biometric Update -- Texas and Washington biometrics laws**: https://www.biometricupdate.com/202208/beyond-bipa-mitigating-biometric-data-legal-risks-under-texas-and-washington-biometrics-laws
60. **FPF -- EU AI Act Emotion Recognition Prohibition**: https://fpf.org/blog/red-lines-under-the-eu-ai-act-unpacking-the-prohibition-of-emotion-recognition-in-the-workplace-and-education-institutions/
61. **FPF -- EU AI Act Remote Biometric Identification**: https://fpf.org/blog/red-lines-under-the-eu-ai-act-restricting-real-time-remote-biometric-identification-systems-for-law-enforcement-purposes/

---

*This document is a research reference, not legal advice. Halbert's developers should consult with a qualified privacy attorney before deploying CV features, especially if offering cloud-based visual data processing. The legal landscape is evolving rapidly, particularly around biometric privacy and AI regulation.*
