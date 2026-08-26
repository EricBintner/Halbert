# Halbert Privacy Policy

**Effective Date:** 2026-08-25  
**Last Updated:** 2026-08-25  
**Scope:** Halbert Software (Core CLI, Desktop Application, Background Daemons) and the Halbert Project Website (`halbert.net` / marketing web).

---

## 1. Core Commitment: Sovereign by Design

Halbert is built on an uncompromising principle: **your computer's data belongs to you.**

Unlike traditional cloud-based AI tools, Halbert operates **100% local-first by default**. We do not harvest, monetize, train on, or transmit your logs, telemetry, configuration files, terminal commands, or conversational prompts.

---

## 2. The Halbert Software Application

### 2.1 What Halbert Accesses Locally
To function as a host custodian, Halbert reads local machine state on your system:
- Hardware sensor telemetry (`hwmon`, CPU/GPU temperatures, memory and disk utilization).
- Operating system logs (`systemd-journald`, `syslog`, `/var/log`).
- Configuration files (`/etc`, dotfiles in `$HOME`, `launchd` plists, systemd service units).
- Shell history and environment variables (`$PATH`, shell profiles).

**All of this data remains strictly on your local machine.** It is stored in standard local directories adhering to the XDG Base Directory Specification:
- Configuration: `~/.config/halbert/`
- Data & Vector Indices: `~/.local/share/halbert/`
- State & Local Logs: `~/.local/state/halbert/`

### 2.2 Zero Telemetry, Analytics, or Crash Reporting
- Halbert **does not collect telemetry**, event pings, or usage analytics.
- Halbert **does not phone home** on startup, execution, or shutdown.
- There are no background beacon scripts, tracking SDKs, or third-party diagnostic collectors embedded in Halbert.

### 2.3 Optional Cloud Model Connections
Halbert runs on local models (via Ollama or Apple Silicon MLX) by default. 

If you **explicitly choose** to configure external cloud API keys (e.g., Anthropic Claude, OpenAI GPT, Google Gemini):
- Only the specific prompt and relevant retrieved context snippets required to answer your query are sent to the designated cloud provider.
- Your data transfer is governed strictly by your personal direct agreement with that cloud provider (e.g., Anthropic Commercial Terms of Service, OpenAI API Data Usage Policies).
- Halbert never proxies your cloud requests through intermediate Halbert servers.

---

## 3. The Halbert Project Website

### 3.1 Early Access Email Collection
On our website, we offer an early access signup form.
- **What We Collect**: Your email address (if voluntarily submitted).
- **Purpose**: To notify you when new release builds (Linux, macOS) or beta invitations become available.
- **Storage & Retention**: We do not sell, rent, trade, or share your email address with third parties or data brokers. You may unsubscribe or request permanent deletion at any time by contacting `privacy@halbert.net`.

### 3.2 Hosting & Infrastructure Server Logs
Our website is statically served via modern content delivery networks (e.g., Netlify / Cloudflare).
- Like all web servers, standard non-identifying request metadata (IP address, browser user-agent, referring URL, timestamp) is temporarily logged by the CDN infrastructure for network security, DDoS mitigation, and reliable asset delivery.
- These logs are standard operational technical logs maintained pursuant to the CDN provider's security practices and are purged on standard operational rotation.

### 3.3 Cookies & Tracking Technologies
- **No Advertising Cookies**: The Halbert website does not use advertising cookies, retargeting pixels, or behavioral cross-site trackers.
- **No Third-Party Analytics**: We do not use Google Analytics or invasive tracking scripts. Any performance metrics are cookieless, aggregate, and privacy-preserving.

---

## 4. Commercial Purchases (Halbert Pro via LemonSqueezy)

For paid software tiers (Halbert Pro for macOS):
- Payments and order fulfillment are processed by our Merchant of Record, **LemonSqueezy** (Lemon Squeezy LLC).
- LemonSqueezy handles payment processing, global VAT/sales tax compliance, and order delivery.
- Financial data (such as full credit card numbers) is handled directly by LemonSqueezy and its payment processors (Stripe/PayPal) and is never seen, stored, or processed by Halbert servers.
- LemonSqueezy's privacy practices are governed by the [Lemon Squeezy Privacy Policy](https://www.lemonsqueezy.com/privacy).

---

## 5. Your Data Protection Rights (GDPR & CCPA/CPRA)

Whether you reside in the European Economic Area (EEA), the United Kingdom, California, or elsewhere, you possess the right to:
1. **Access & Portability**: Request confirmation of any personal data we hold (e.g. early access email list).
2. **Erasure / Deletion**: Request that your email address be permanently deleted from our communication lists.
3. **No Sale of Personal Information**: Halbert does not sell personal information and has never done so.

To exercise any of these rights, email: `privacy@halbert.net`.

---

## 6. Changes to this Policy

If we update this Privacy Policy, we will post the updated document with a revised "Last Updated" date. Because our core architecture is strictly local-first, changes will only reflect updates to external services (such as distribution platforms or website infrastructure).

---

## 7. Contact Information

For inquiries regarding this Privacy Policy or Halbert's privacy practices:
- **Email**: `privacy@halbert.net`
- **Project Repository**: `https://github.com/EricBintner/Halbert`
