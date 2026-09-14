# Deployment: Netlify + Cloudflare (halbert.computer)

**Status:** infrastructure prepared, first deploy pending your Netlify + Cloudflare setup (§2–§4).
**Owner:** Eric Bintner · **Site:** `marketing/web-v10` · **Domain:** `halbert.computer` (Cloudflare)

---

## 1. The deploy contract

**A plain `git push origin main` only syncs code — it can never deploy.**
Production deploys happen only through one script:

```bash
scripts/deploy.sh            # deploy local main
scripts/deploy.sh <commit>   # deploy a specific pushed commit
scripts/deploy.sh --status   # what is live / pending
```

How the gate works: Netlify is configured to watch a dedicated
**`deploy/main` branch**, not `main`. `deploy.sh` verifies the commit is
pushed and the tree is clean, then moves `deploy/main` to that commit
and pushes it. Netlify sees the ref move and builds. Code pushes to
`main` are invisible to Netlify by construction.

The script refuses to deploy if:

- the target commit is not on `origin/main` (Netlify builds the remote —
  an unpushed commit would deploy something invisible),
- the working tree has uncommitted changes under `marketing/`, `docs/`,
  `scripts/`, or the root `netlify.toml`.

## 2. One-time Netlify setup (~5 minutes)

1. **Create the site.** [app.netlify.com](https://app.netlify.com) →
   *Add new site* → *Import an existing project* → **GitHub** →
   `EricBintner/Halbert`. If the sandbox of the app you run Claude in
   can't reach github.com, do this from a normal browser.
2. **Branch to deploy: `deploy/main`** — this is the gate. Change it
   from the default `main` in the site's *Build & deploy* settings →
   *Branches* → *Production branch*. **Do not** add `main` as an
   additional deploy branch.
3. **Build settings** — the repo's root `netlify.toml` (copied to
   `marketing/web-v10/netlify.toml`, deployed copy wins) already
   defines everything; confirm Netlify shows:
   - Base directory: `.` (repo root)
   - Build command: `python3 scripts/sync_fonts.py && npm --prefix
     marketing/web-v10 install && npm --prefix marketing/web-v10 run build`
   - Publish directory: `marketing/web-v10/dist`
   - Node 22 / Python 3.11 (build environment)
4. **Note the site URL** (`<something>.netlify.app`) — needed for DNS in §3.

Why the build command looks like that: the typefaces are vendored
(`shared-tokens/fonts/`, licence: OFL) and copied into each app's
`public/fonts` **at build time** — those copies are gitignored, so the
deploy build must regenerate them or the site ships without its fonts.
CI already runs the same sync with `--check` on every PR.

## 3. Cloudflare DNS for halbert.computer (~5 minutes)

You own the domain on Cloudflare. Two records point it at Netlify, and
one Cloudflare setting must be changed or the domain will loop:

1. **In Netlify:** *Site settings* → *Domain management* → *Add custom
   domain* → `halbert.computer`, and add `www.halbert.computer` too.
   Netlify will show a pending-DNS warning until step 2 propagates.
2. **In Cloudflare** (domain → DNS):
   | Type | Name | Content | Proxy |
   |---|---|---|---|
   | `CNAME` | `@` (or `halbert.computer`) | `<your-site>.netlify.app` | **DNS only (grey cloud)** |
   | `CNAME` | `www` | `<your-site>.netlify.app` | **DNS only (grey cloud)** |
3. **Turn OFF the orange cloud for both records.** This is the step that
   silently breaks the setup if missed: Netlify terminates TLS itself and
   needs to see the ACME HTTP-01 challenge requests to issue the Let's
   Encrypt certificate for `halbert.computer`. With Cloudflare's proxy
   on, those challenges get answered by Cloudflare's edge certificate
   instead, and Netlify's certificate never issues — you get a redirect
   loop or an invalid-certificate error.
4. Wait for DNS propagation (minutes, occasionally up to an hour) and
   watch Netlify's domain page until both domains show
   *Netlify-managed certificate · active*.
5. **Optionally re-enable the orange cloud afterwards.** Once Netlify's
   certificate is live you may proxy `halbert.computer` through
   Cloudflare again (full SSL mode, not "flexible"). Keep it off for
   the first issuance; add it back only if you want Cloudflare's CDN/WAF
   in front of Netlify.

## 4. First deploy

After §2–§3 and after your pending `git push origin main` (the sandbox
in Claude app sessions currently can't reach github.com, so push from
your terminal):

```bash
git push origin main        # publish the commits (no deploy)
scripts/deploy.sh           # first production deploy of web-v10
scripts/deploy.sh --status  # confirm the deploy ref moved
```

Then watch the build at *app.netlify.com → Production deploys*, and
load **https://halbert.computer** when it finishes.

## 5. What is deployed from which commit

The deployed commit's copy of these files governs the build:

- `marketing/web-v10/netlify.toml` — build command, publish dir, headers,
  apex redirects (Netlify reads it from the deployed ref)
- `scripts/sync_fonts.py` and `shared-tokens/fonts/` — the typefaces
- `marketing/web-v10/src/**` — the site itself
- `packages/design-system/**` — consumed via a vite alias, so a
  design-system change deploys the site against it

## 6. Operations

- **Check what is live:** `scripts/deploy.sh --status`, or Netlify →
  *Production deploys* (the deploy commit hash matches `deploy/main`).
- **Roll back:** `scripts/deploy.sh <older-commit>` — moves the ref to
  any previously deployed commit and rebuilds. Netlify's UI also offers
  one-click *Publish a previous deploy*.
- **Never** push to `deploy/main` by hand; the script is the only writer.
- **Netlify free tier** covers this usage (100 GB bandwidth/mo); no
  build-minute limits apply (static Vite build, ~1 min).
- **Cloudflare proxy (optional):** if re-enabled in §3.5, set SSL/TLS
  mode to *Full (strict)* so Cloudflare validates Netlify's cert rather
  than accepting anything.

## 7. Security notes

- The site is fully static — no forms backend, no secrets, no env vars
  in the Netlify config. The early-access form is UI-only (client state).
- Headers (`netlify.toml`): `X-Frame-Options: DENY`, `nosniff`,
  `Referrer-Policy` on everything; HTML never cached so deploys land
  immediately; hashed `/assets/*` cached immutable; fonts cached a week.
- DNS-only mode during issuance means no Cloudflare WAF in front for
  those first minutes — acceptable for a static site.

## 8. Future work (not in this pass)

- Netlify UI deploys (`netlify deploy --prod`) bypass the ref gate —
  decide whether to disable the CLI token or leave it as a break-glass
  path.
- Preview deploys for pull requests (useful, free) — would watch a
  `preview/*` pattern, separate from the `deploy/main` production ref.
- Cloudflare Pages is the obvious alternative host; the gate design
  (deploy ref) transfers directly since Pages also builds on a branch.