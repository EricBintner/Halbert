# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
"""The census: every route is authenticated, or it is listed and defended.

This is the test that makes SEC-1 hold. The defect it exists to prevent is not
"somebody wrote an insecure route" — it is that the previous design required 334
separate acts of remembering and got 19 of them. Registration through
``mount_router`` means a new route is authenticated by *omission*; this test is
what fails when someone reaches around it.

If this test fails on a route you added, the fix is almost never to add it to
the allowlist below. It is to register the router through ``mount_api``.
"""
from __future__ import annotations

import os
import tempfile

import pytest

pytest.importorskip("fastapi")

from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402
from starlette.routing import Mount, Route  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """The real app, built once.

    Note what this deliberately does *not* do: mutate ``HALBERT_API_TOKEN``.
    An earlier version popped it here and never put it back, which silently
    de-authenticated every suite that ran afterwards — the module-scoped
    equivalent of the fail-open this whole work item is about.
    """
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("XDG_STATE_HOME", tmp)
            from halbert_core.dashboard.app import create_app

            yield create_app()


@pytest.fixture
def anon(app):
    """A client presenting no credential at all.

    ``conftest`` gives every TestClient a default Authorization header so the
    rest of the suite can exercise business logic. These tests are about the
    door itself, so they take it back off.
    """
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.headers.pop("Authorization", None)
    return client


#: Routes served without a credential, each with the reason it is safe.
#: Adding to this set is a conscious act; the reason column is the point.
PUBLIC_ALLOWLIST = {
    "/": "the SPA shell; every datum it renders arrives over an authenticated fetch",
    "/auth/enter": "the ticket exchange — the only way a browser can get through the door",
    "/auth/status": "discloses one bit (authenticated or not) so the shell can route",
    "/auth/logout": "clears a session; needs no session to be safe",
    "/Halbert.png": "brand logo, static",
    "/favicon.ico": "static",
}

#: Client-side routes that serve index.html. Same reasoning as "/".
SPA_PATHS_ARE_PUBLIC = True


def _iter_routes(app):
    """Yield ``(route, inherited_dependencies)`` for every leaf route.

    This walk is load-bearing, and getting it wrong is silent. This FastAPI
    version does not flatten an included router into ``app.routes``: it appends
    an ``_IncludedRouter`` wrapper that keeps the real routes on
    ``original_router`` and the include-time ``dependencies=`` on
    ``include_context``. A census that only walked ``app.routes`` saw four
    routes and passed cheerfully while 334 sat unexamined beneath it — which is
    exactly the class of mistake this whole work item is about.

    Both shapes are handled so the test does not quietly stop checking anything
    the day FastAPI changes its mind.
    """
    stack = [(r, ()) for r in app.routes]
    while stack:
        route, inherited = stack.pop()
        if isinstance(route, Mount):
            continue

        if type(route).__name__ == "_IncludedRouter":
            ctx = getattr(route, "include_context", None)
            deps = tuple(getattr(ctx, "dependencies", ()) or ())
            original = getattr(route, "original_router", None)
            if original is not None:
                stack.extend((r, inherited + deps) for r in original.routes)
                continue

        children = getattr(route, "routes", None)
        if children and not isinstance(children, (str, bytes)):
            stack.extend((r, inherited) for r in children)
            continue

        yield route, inherited


def _recognised_guards():
    """The dependencies that count as a door.

    ``require_owner`` is the general one. ``require_peer_auth`` is the peer
    compute surface's own bearer scheme — a different principal, but a real
    credential, so a route carrying it is not open. Recognising the *dependency*
    rather than a tag matters: a tag is a label anyone can copy onto an
    unguarded router, and this test would then wave it through.
    """
    from halbert_core.dashboard.auth import require_owner
    from halbert_core.federation.peer_middleware import require_peer_auth

    return (require_owner, require_peer_auth)


def _guards(dep) -> bool:
    """Is this dependency one of the recognised doors, however FastAPI wrapped it?"""
    recognised = _recognised_guards()
    return (
        getattr(dep, "call", None) in recognised
        or getattr(dep, "dependency", None) in recognised
    )


def _has_owner_dependency(route, inherited=()) -> bool:
    """Is this route guarded, by inclusion or in its own signature?"""
    if any(_guards(d) for d in inherited):
        return True
    dependant = getattr(route, "dependant", None)
    if dependant is None:
        return False
    if any(_guards(d) for d in getattr(dependant, "dependencies", [])):
        return True
    # A signature dependency (`peer: PeerContext = Depends(require_peer_auth)`)
    # lands as a sub-dependant rather than in `.dependencies`.
    recognised = _recognised_guards()
    return any(
        getattr(sub, "call", None) in recognised
        for sub in getattr(dependant, "dependencies", [])
    ) or any(
        getattr(sub, "call", None) in recognised
        for sub in _walk_subdependants(dependant)
    )


def _walk_subdependants(dependant, depth: int = 0):
    if depth > 4:
        return
    for sub in getattr(dependant, "dependencies", []) or []:
        yield sub
        yield from _walk_subdependants(sub, depth + 1)


def test_every_http_route_is_authenticated_or_allowlisted(app):
    from halbert_core.dashboard.app import SPA_ROUTES
    from halbert_core.dashboard.auth import SELF_AUTHENTICATING

    spa = set(SPA_ROUTES) if SPA_PATHS_ARE_PUBLIC else set()
    offenders = []

    walked = list(_iter_routes(app))
    assert len(walked) > 100, (
        f"The census walked only {len(walked)} routes, so it is not checking "
        "anything meaningful. The route tree shape changed — fix _iter_routes "
        "rather than letting this pass."
    )

    for route, inherited in walked:
        if not isinstance(route, (APIRoute, Route)):
            continue
        path = getattr(route, "path", "")
        if path in PUBLIC_ALLOWLIST or path in spa:
            continue
        tags = set(getattr(route, "tags", []) or [])
        if tags & set(SELF_AUTHENTICATING):
            continue
        if _has_owner_dependency(route, inherited):
            continue
        methods = ",".join(sorted(getattr(route, "methods", []) or []))
        offenders.append(f"{methods or 'GET'} {path}")

    assert not offenders, (
        "These routes are reachable with no credential. Register the router "
        "through `mount_api` in create_app rather than adding them here:\n  "
        + "\n  ".join(sorted(offenders))
    )


def test_websocket_routes_check_the_handshake(app):
    """Every WebSocket handler calls ``websocket_authenticated`` before accepting.

    Router-level dependencies cannot do this job: raising HTTPException during a
    handshake produces a 500 rather than a clean refusal, so the WebSocket
    router is self-authenticating and each handler checks for itself. This test
    reads the source to prove each one actually does.
    """
    import inspect

    from halbert_core.dashboard.routes import websocket as ws_module

    ws_routes = [
        r for r, _ in _iter_routes(app)
        if isinstance(r, APIWebSocketRoute) or "WebSocket" in type(r).__name__
    ]
    assert ws_routes, "expected the dashboard to expose WebSocket routes"

    missing = []
    for route in ws_routes:
        endpoint = getattr(route, "endpoint", None)
        if endpoint is None:
            missing.append(route.path)
            continue
        try:
            source = inspect.getsource(endpoint)
        except (OSError, TypeError):  # pragma: no cover
            missing.append(route.path)
            continue
        if "websocket_authenticated" not in source:
            missing.append(route.path)

    assert not missing, (
        "These WebSocket handlers accept a handshake without checking it. CORS "
        "never sees a handshake, so an unchecked one is reachable by any web "
        "page the owner visits:\n  " + "\n  ".join(sorted(missing))
    )
    assert hasattr(ws_module, "websocket_authenticated")


def test_the_named_criticals_refuse_an_anonymous_caller(anon):
    """The five routes SEC-1 names by hand, driven end to end.

    `/api/terminal/exec` spawns a PTY; `/api/editor/file` writes any absolute
    path; `/api/vision/config` flips the consent flags that gate capture;
    `/api/state/forget` destroys audit payloads; `/api/settings/policy` rewrites
    the tool policy. Each was reachable by any local process and, via DNS
    rebinding, by any web page.
    """
    cases = [
        ("post", "/api/terminal/exec", {"command": "id"}),
        ("post", "/api/editor/file", {"path": "/tmp/x", "content": "x"}),
        ("put", "/api/vision/config", {"screen_capture_enabled": True}),
        ("post", "/api/state/forget", {"request_id": "x"}),
        ("post", "/api/settings/policy", {"default_allow": True}),
    ]
    for method, path, body in cases:
        res = getattr(anon, method)(path, json=body)
        assert res.status_code in (401, 403, 404, 405), (
            f"{method.upper()} {path} answered {res.status_code} to an "
            f"anonymous caller; expected a refusal"
        )


def test_a_rebound_host_header_is_refused(anon):
    """DNS rebinding: the page cannot change the Host header it sends."""
    res = anon.get("/auth/status", headers={"Host": "evil.example"})
    assert res.status_code == 421, (
        "An unrecognised Host must be refused with 421 — this is the only "
        "control that closes DNS rebinding, since CORS never enters into it."
    )


def test_a_valid_token_gets_through(app, anon):
    """The door opens for the owner. A boundary that refuses everyone is not one."""
    token = app.state.auth.token
    res = anon.get("/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["authenticated"] is True

    assert anon.get("/auth/status").json()["authenticated"] is False


def test_a_ticket_is_single_use_and_opens_a_browser_session(app, anon):
    """The browser handoff: a ticket redeems once, for a cookie.

    This is what keeps a browser and the kiosk unit working now that the door
    is shut, so it has to actually work — and a ticket that could be replayed
    would be a URL-shaped credential sitting in shell history and server logs.
    """
    from halbert_core.dashboard.auth import SESSION_COOKIE, mint_ticket

    ticket = mint_ticket(app.state.auth.token)
    res = anon.get(f"/auth/enter?ticket={ticket}", follow_redirects=False)
    assert res.status_code == 303
    assert SESSION_COOKIE in res.cookies

    assert anon.get("/auth/status").json()["authenticated"] is True

    replay = _fresh_anon_client(app)
    assert replay.get(f"/auth/enter?ticket={ticket}", follow_redirects=False).status_code == 403


def _fresh_anon_client(app):
    """A second unauthenticated client, for asserting a ticket cannot be replayed."""
    from fastapi.testclient import TestClient

    client = TestClient(app)
    client.headers.pop("Authorization", None)
    return client
