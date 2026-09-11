# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""One door: the authentication boundary for every dashboard listener.

Before this module, ~315 of 334 routes carried no authentication of any kind and
loopback was treated as an authorization boundary. It is not one. Every other
process running as this user is already on loopback, and so is a web page that
has rebound its own hostname to 127.0.0.1 — which is why the Host allowlist here
is not optional decoration (SEC-1; findings F0, F1, F4).

**What this establishes, and what it does not.**

  It does     stop another user account on this machine, anything on the LAN, and
              any web page the owner visits in a browser.
  It does not stop code already executing as the owner's own uid. That code can
              read the token file, exactly as it can read the owner's ssh key.
              Raising *that* bar needs OS-level app sandboxing, not a secret, and
              it is out of scope here. Say so plainly rather than implying the
              token is doing more work than it is.

**Three credentials, checked in this order.**

  1. ``Authorization: Bearer <token>``  peers, the CLI, MCP.
  2. ``X-Halbert-Token: <token>``       the Tauri webview, which is cross-origin
                                        to its own sidecar and therefore cannot
                                        use a cookie at all.
  3. ``halbert_session`` cookie         a browser, after redeeming a ticket.

**Tickets.** A browser cannot be handed a header, so ``halbert dashboard`` mints
a short-lived single-use ticket and opens a URL carrying it; redeeming it sets
the session cookie. Tickets are an HMAC over the token, so the CLI can mint one
in a *different process* with no shared state beyond the token file — which is
what lets ``scripts/halbert-kiosk.service`` keep working.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import time
from pathlib import Path
from typing import Iterable, Optional, Set

logger = logging.getLogger("halbert.dashboard.auth")

#: Cookie the browser session lands in. HttpOnly + SameSite=Strict: a session
#: cookie readable from JS would hand every same-origin script the door key,
#: and Lax would still ride along on a top-level cross-site GET.
SESSION_COOKIE = "halbert_session"

#: Header the Tauri webview uses. It is cross-origin to the sidecar over plain
#: http, where SameSite=None;Secure cookies cannot be set, so a header is the
#: only credential available to it.
TOKEN_HEADER = "X-Halbert-Token"

#: Env var that hands the token to a child process (the Tauri shell sets it on
#: the sidecar). Never logged.
TOKEN_ENV = "HALBERT_API_TOKEN"

#: Paths served without a credential. Deliberately tiny, and every entry is
#: either static, a liveness probe, or the ticket exchange itself. Anything
#: added here needs a reason in review — ``tests/test_route_auth_census.py``
#: exists to make that a conscious act rather than an accident.
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/api/health",
    "/auth/enter",
    "/auth/status",
    "/favicon.ico",
    "/Halbert.png",
})

#: Prefixes served without a credential: the built SPA and its assets. The shell
#: itself discloses nothing — every datum it renders arrives over an
#: authenticated fetch — so serving it openly costs nothing and keeps the
#: ticket-redemption redirect able to land somewhere.
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/assets/",
    "/fonts/",
)

#: Routers that authenticate themselves rather than through ``require_owner``:
#: the peer/compute surface carries its own bearer scheme, and the WebSocket
#: router checks inside each handler because a dependency that raises
#: HTTPException on a handshake produces a 500, not a clean refusal.
SELF_AUTHENTICATING = ("compute-peer", "websocket")

_TICKET_TTL_SECONDS = 300
_SESSION_TTL_SECONDS = 12 * 60 * 60


# ---------------------------------------------------------------------------
# The token
# ---------------------------------------------------------------------------

def token_path() -> Path:
    """Where the API token lives: ``<state_dir>/api-token``."""
    from ..utils.paths import state_dir

    return Path(state_dir()) / "api-token"


def load_or_create_token() -> str:
    """The token for this installation, creating it on first call.

    ``0600`` in a ``0700`` directory, and the mode is repaired on every read —
    the audit found every other store in the tree created world-readable because
    it relied on umask, and a credential is the last place to inherit that.
    """
    env = os.environ.get(TOKEN_ENV, "").strip()
    if env:
        return env

    path = token_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    except OSError as exc:  # pragma: no cover - filesystem-dependent
        logger.warning("could not secure %s: %s", path.parent, exc)

    if path.exists():
        try:
            os.chmod(path, 0o600)
        except OSError:  # pragma: no cover
            pass
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing

    token = secrets.token_urlsafe(32)
    # Create with the right mode from the start rather than chmod-after-write:
    # between the two there is a window where the credential is world-readable.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    logger.info("minted a new dashboard API token at %s", path)
    return token


def _eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


# ---------------------------------------------------------------------------
# Tickets — the browser handoff
# ---------------------------------------------------------------------------

def _sign(token: str, payload: str) -> str:
    mac = hmac.new(token.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest()).decode("ascii").rstrip("=")


def mint_ticket(token: Optional[str] = None, ttl: int = _TICKET_TTL_SECONDS) -> str:
    """A single-use, short-lived credential a browser can carry in a URL.

    Stateless by construction: the signature is an HMAC over the API token, so
    the CLI can mint one without talking to the running server.
    """
    tok = token or load_or_create_token()
    expiry = int(time.time()) + ttl
    nonce = secrets.token_urlsafe(12)
    payload = f"{expiry}.{nonce}"
    return f"{payload}.{_sign(tok, payload)}"


def verify_ticket(ticket: str, token: Optional[str] = None, *, seen: Optional[Set[str]] = None) -> bool:
    """True when ``ticket`` is well-formed, unexpired, correctly signed and unused."""
    tok = token or load_or_create_token()
    parts = ticket.split(".")
    if len(parts) != 3:
        return False
    expiry_raw, nonce, sig = parts
    try:
        expiry = int(expiry_raw)
    except ValueError:
        return False
    if expiry < time.time():
        return False
    if not _eq(_sign(tok, f"{expiry_raw}.{nonce}"), sig):
        return False
    if seen is not None:
        if nonce in seen:
            return False
        seen.add(nonce)
    return True


class SessionStore:
    """Browser sessions, in memory and per server run.

    Not persisted on purpose: a restart should not silently re-admit a browser
    the owner has since walked away from, and re-redeeming a ticket is cheap.
    """

    def __init__(self, ttl: int = _SESSION_TTL_SECONDS) -> None:
        self._ttl = ttl
        self._sessions: dict[str, float] = {}
        self._spent_tickets: Set[str] = set()

    @property
    def spent_tickets(self) -> Set[str]:
        return self._spent_tickets

    def create(self) -> str:
        self._reap()
        sid = secrets.token_urlsafe(32)
        self._sessions[sid] = time.time() + self._ttl
        return sid

    def valid(self, sid: str) -> bool:
        self._reap()
        expiry = self._sessions.get(sid)
        return expiry is not None and expiry > time.time()

    def revoke_all(self) -> None:
        self._sessions.clear()

    def _reap(self) -> None:
        now = time.time()
        for sid in [s for s, exp in self._sessions.items() if exp <= now]:
            self._sessions.pop(sid, None)


# ---------------------------------------------------------------------------
# Host and Origin
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTNAMES = {"localhost", "tauri.localhost", "testserver", "testclient"}


def _hostname_of(header: str) -> str:
    """The host part of a Host header, with the port and any brackets removed."""
    value = header.strip()
    if value.startswith("["):  # [::1]:8000
        end = value.find("]")
        return value[1:end] if end != -1 else value[1:]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def host_allowed(header: Optional[str], extra: Iterable[str] = ()) -> bool:
    """Is this Host header one we answer to?

    The DNS-rebinding defence. An attacker's page resolves ``evil.example`` to
    127.0.0.1 and the browser then treats the dashboard as same-origin — CORS
    never enters into it. What that page cannot do is change the Host header it
    sends, so refusing an unrecognised Host is what actually closes it (F1).
    """
    if not header:
        # HTTP/1.1 requires Host; a request without one is not a browser.
        return True
    name = _hostname_of(header).lower()
    if name in _LOOPBACK_HOSTNAMES or name in {e.lower() for e in extra}:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def allowed_hosts_from_env() -> tuple[str, ...]:
    raw = os.environ.get("HALBERT_ALLOWED_HOSTS", "")
    return tuple(h.strip() for h in raw.split(",") if h.strip())


def origin_allowed(origin: Optional[str], extra: Iterable[str] = ()) -> bool:
    """Is this Origin one of ours?

    Used on the WebSocket handshake, which CORS never sees — the browser sends
    Origin but the server is free to ignore it, and every one of the four
    handlers did (F125).
    """
    if not origin:
        # No Origin means no browser. Such a caller still needs a token.
        return True
    value = origin.strip().lower()
    if value in {"tauri://localhost", "http://tauri.localhost", "null"}:
        return value != "null"
    for candidate in extra:
        if value == candidate.strip().lower():
            return True
    scheme, _, rest = value.partition("://")
    if scheme not in ("http", "https"):
        return False
    return host_allowed(rest, extra)


# ---------------------------------------------------------------------------
# Credential extraction
# ---------------------------------------------------------------------------

def credential_from_headers(headers, cookies=None) -> tuple[str, Optional[str]]:
    """Pull a credential out of a request. Returns ``(kind, value)``."""
    auth = headers.get("authorization") or ""
    if auth[:7].lower() == "bearer ":
        return "bearer", auth[7:].strip()
    direct = headers.get(TOKEN_HEADER.lower()) or headers.get(TOKEN_HEADER)
    if direct:
        return "header", direct.strip()
    if cookies:
        sid = cookies.get(SESSION_COOKIE)
        if sid:
            return "session", sid
    return "none", None


# ---------------------------------------------------------------------------
# FastAPI wiring
#
# Guarded the way ``app.py`` guards it: halbert_core is installed without the
# dashboard extra in several deployments, and importing this module must not be
# what breaks them. Everything above is pure and unit-testable without FastAPI.
# ---------------------------------------------------------------------------

try:
    from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
    from fastapi.responses import RedirectResponse
    from starlette.middleware.base import BaseHTTPMiddleware
    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only on a dashboard-less install
    FASTAPI_AVAILABLE = False


def is_public_path(path: str) -> bool:
    """Is this path served without a credential?"""
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def _state(app) -> "AuthState":
    """The auth state hung off the app, created on first use."""
    existing = getattr(app.state, "auth", None)
    if existing is None:
        existing = AuthState()
        app.state.auth = existing
    return existing


class AuthState:
    """Everything the door needs, in one place on ``app.state.auth``."""

    def __init__(self, token: Optional[str] = None) -> None:
        self.token = token or load_or_create_token()
        self.sessions = SessionStore()
        self.allowed_hosts = allowed_hosts_from_env()

    def check(self, kind: str, value: Optional[str]) -> bool:
        if not value:
            return False
        if kind == "session":
            return self.sessions.valid(value)
        return _eq(value, self.token)


if FASTAPI_AVAILABLE:

    async def require_owner(request: Request) -> None:
        """The door. Every route gets this unless it is explicitly public.

        Applied by ``mount_router`` at registration time rather than by each
        route author remembering, so a new route is authenticated by *omission*.
        That inversion is the whole point: the previous design required 334
        separate acts of remembering and got 19 of them.
        """
        state = _state(request.app)
        if not host_allowed(request.headers.get("host"), state.allowed_hosts):
            raise HTTPException(
                status_code=status.HTTP_421_MISDIRECTED_REQUEST,
                detail="Unrecognised Host header.",
            )
        kind, value = credential_from_headers(request.headers, request.cookies)
        if state.check(kind, value):
            request.state.principal = "owner"
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "This machine does not answer to callers it cannot identify. "
                "Run `halbert dashboard` to open an authenticated window."
            ),
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def require_owner_stream(request: Request) -> None:
        """``require_owner``, plus a ``?token=`` query parameter.

        For ``EventSource`` only. The browser's SSE client cannot set a header,
        and in the Tauri webview it cannot use a cookie either — the webview is
        cross-origin to its own sidecar, where a ``SameSite`` cookie will not be
        sent. So the credential has nowhere to ride except the URL.

        That is a real cost: a URL lands in access logs and in ``Referer``. It is
        accepted here and nowhere else, on one route that streams events the UI
        already displays, and it is the same mechanism the WebSocket door
        already uses. If the token in a URL becomes unacceptable, the fix for
        both is a short-lived stream ticket rather than a different exception.
        """
        state = _state(request.app)
        if not host_allowed(request.headers.get("host"), state.allowed_hosts):
            raise HTTPException(
                status_code=status.HTTP_421_MISDIRECTED_REQUEST,
                detail="Unrecognised Host header.",
            )
        if not origin_allowed(request.headers.get("origin"), state.allowed_hosts):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unrecognised Origin.",
            )
        kind, value = credential_from_headers(request.headers, request.cookies)
        if state.check(kind, value):
            request.state.principal = "owner"
            return
        qp = request.query_params.get("token")
        if qp and state.check("bearer", qp):
            request.state.principal = "owner"
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This machine does not answer to callers it cannot identify.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    class HostHeaderMiddleware(BaseHTTPMiddleware):
        """Refuse a Host we do not answer to, before routing.

        ``require_owner`` checks this too, but public paths do not run it — and
        the SPA shell is a public path. Without this middleware a rebound page
        could still load the shell from our origin, which is most of the way to
        looking legitimate.
        """

        async def dispatch(self, request: Request, call_next):
            state = _state(request.app)
            if not host_allowed(request.headers.get("host"), state.allowed_hosts):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    status_code=status.HTTP_421_MISDIRECTED_REQUEST,
                    content={"detail": "Unrecognised Host header."},
                )
            return await call_next(request)

    def mount_router(app, router, *, prefix: str = "", tags=None, public: bool = False) -> None:
        """Register a router behind the door.

        ``public=True`` is the only way past it and every use is listed in
        ``SELF_AUTHENTICATING`` or defended in review.
        """
        self_auth = bool(tags) and any(t in SELF_AUTHENTICATING for t in tags)
        deps = [] if (public or self_auth) else [Depends(require_owner)]
        app.include_router(router, prefix=prefix, tags=tags, dependencies=deps)

    async def websocket_authenticated(websocket) -> bool:
        """Check a WebSocket handshake before accepting it.

        CORS never sees a handshake, so the four handlers were reachable by any
        web page the owner visited (F125). Origin is checked *and* a credential
        is required: Origin stops the browser case, the token stops everything
        else. A WebSocket cannot carry an Authorization header from a browser,
        so the session cookie or a ``?token=`` query parameter is what a real
        client uses here.
        """
        state = _state(websocket.app)
        if not host_allowed(websocket.headers.get("host"), state.allowed_hosts):
            return False
        if not origin_allowed(websocket.headers.get("origin"), state.allowed_hosts):
            return False
        kind, value = credential_from_headers(websocket.headers, websocket.cookies)
        if state.check(kind, value):
            return True
        qp = websocket.query_params.get("token")
        return bool(qp) and state.check("bearer", qp)

    async def reject_websocket(websocket) -> None:
        """Close an unauthenticated handshake with a policy-violation code."""
        await websocket.close(code=1008, reason="unauthenticated")

    def build_auth_router() -> "APIRouter":
        """The ticket exchange, and a status probe the shell can read."""
        router = APIRouter()

        @router.get("/auth/enter")
        async def enter(request: Request, ticket: str = "", next: str = "/"):
            """Redeem a one-time ticket for a session cookie.

            This is how a browser — which cannot be handed a header — gets
            through the door, and how ``scripts/halbert-kiosk.service`` keeps
            working after the door closed.
            """
            state = _state(request.app)
            if not verify_ticket(ticket, state.token, seen=state.sessions.spent_tickets):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="That link has expired or has already been used.",
                )
            # Only ever redirect within this origin: an open redirect here would
            # hand the ticket to whatever the query string named.
            target = next if next.startswith("/") and not next.startswith("//") else "/"
            response = RedirectResponse(url=target, status_code=303)
            response.set_cookie(
                SESSION_COOKIE,
                state.sessions.create(),
                httponly=True,
                samesite="strict",
                max_age=_SESSION_TTL_SECONDS,
                path="/",
            )
            return response

        @router.get("/auth/status")
        async def auth_status(request: Request):
            """Whether this caller is already through the door.

            Public on purpose, and it discloses one bit: authenticated or not.
            The shell uses it to decide whether to render or to send the user to
            fetch a link.
            """
            state = _state(request.app)
            kind, value = credential_from_headers(request.headers, request.cookies)
            return {"authenticated": state.check(kind, value), "credential": kind}

        @router.post("/auth/logout")
        async def logout(request: Request, response: Response):
            _state(request.app).sessions.revoke_all()
            response.delete_cookie(SESSION_COOKIE, path="/")
            return {"ok": True}

        return router


def guard_bind(host: str, token_present: bool = True) -> None:
    """Refuse to serve a non-loopback address without a credential.

    The shipped units set ``HALBERT_HOST=0.0.0.0`` (F2, F6), which put an
    unauthenticated PTY and arbitrary file write on the LAN. Binding wide is a
    legitimate thing to want; doing it with no door is not, so this raises
    rather than warning.
    """
    try:
        wide = not ipaddress.ip_address(host).is_loopback
    except ValueError:
        wide = host not in _LOOPBACK_HOSTNAMES
    if wide and not token_present:
        raise RuntimeError(
            f"Refusing to bind {host}: a non-loopback address needs a token. "
            f"Set {TOKEN_ENV}, or bind 127.0.0.1."
        )

