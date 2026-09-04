# License

**Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors**

Halbert is free software: you can redistribute it and/or modify it under the
terms of the **GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version** — SPDX identifier `GPL-3.0-or-later`.

Halbert is distributed in the hope that it will be useful, but **WITHOUT ANY
WARRANTY**; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
A PARTICULAR PURPOSE. See the GNU General Public License for more details.

## Mac App Store additional permission

Builds conveyed through the Apple Mac App Store carry one additional permission
under GPLv3 §7. The operative text is
[`LICENSE-EXCEPTION-APPSTORE`](../../LICENSE-EXCEPTION-APPSTORE) at the repository
root — that file, and only that file, is the grant.

It is scope-limited to conveyance through the Mac App Store, does not extend to
third-party code whose holders have not granted an equivalent permission, and a
downstream fork may drop it. Every other build — the direct macOS download and
every Linux package — is plain `GPL-3.0-or-later` with no exception.

Why the exception is needed at all (the GPLv3 §6 and §10 conflict with Apple's
terms, and the VLC/GNU Go precedent) is set out in
[`APP-STORE-DISTRIBUTION-STRATEGY.md`](APP-STORE-DISTRIBUTION-STRATEGY.md).

## Summary

**You are free to:**

- **Use** — Run the software for any purpose
- **Study** — Examine and modify the source code
- **Share** — Copy and distribute the software
- **Improve** — Modify and distribute your modifications

**Under the following conditions:**

- **Disclose source** — Corresponding source code must be made available when you distribute the software
- **Same license** — Distributed modifications must be licensed under GPL-3.0-or-later
- **State changes** — Document the changes you made to the code
- **License notice** — Include the license and copyright notices in distributions
- **No further restrictions** — You may not impose additional legal or technical restrictions on recipients

This summary is not a substitute for the license. The license text governs.

## Full License

- The verbatim GPLv3 text ships in the repository root as [`LICENSE`](../../LICENSE)
  and is printed by `halbert license --full`.
- Online: https://www.gnu.org/licenses/gpl-3.0.html
- SPDX: [`GPL-3.0-or-later`](https://spdx.org/licenses/GPL-3.0-or-later.html)
  (the bare identifier `GPL-3.0` is deprecated; where older files or docs say
  "GPL-3.0" they mean this license)

## Source File Headers

Every first-party `.py`, `.rs`, `.ts`, `.tsx` and `.sh` file carries:

```
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
```

`python scripts/add_spdx_headers.py --check` verifies this (it runs in the test
suite). A handful of files derived from third-party code keep their upstream
license identifier instead — see
[`THIRD-PARTY-LICENSES.md` §3.5](./THIRD-PARTY-LICENSES.md).

## Legal Notices in the Program

As GPLv3 §5(d) asks of interactive programs, `halbert --version`, `halbert info`
and the dashboard server print the copyright notice, the no-warranty statement,
and how to view the license (`halbert license`, `halbert license --full`,
`halbert license --third-party`).

## For Contributors

Contributions are accepted under `GPL-3.0-or-later` with a Developer
Certificate of Origin sign-off on every commit (`git commit -s`). See
[`CONTRIBUTING.md` § Contributor Licensing](../contributing/CONTRIBUTING.md#contributor-licensing--intellectual-property-agreement).

## Third-Party Content

The RAG knowledge corpus, software dependencies, and foundation models each
carry their own licenses and attribution requirements. They are listed in
[`THIRD-PARTY-LICENSES.md`](./THIRD-PARTY-LICENSES.md).

## Why GPL-3.0-or-later?

1. The software remains free and open source
2. Improvements benefit the community
3. Users have the right to study and modify the code
4. Anyone who distributes the software — commercially or not — must make the
   corresponding source available under the same terms
5. "or later" lets the project adopt future FSF license versions without
   contacting every contributor

This aligns with the project's goal of building a community around Linux and
macOS system management.
