"""Integration tests for PTYSession (B1a).

These fork real child processes via os.openpty/os.fork, so they are
Unix-only (skipped elsewhere) and use timeouts to avoid hanging on a
misbehaving child.
"""

import asyncio
import sys
import pytest

from halbert_core.streaming.pty import PTYSession

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="PTY is Unix-only (os.fork)"
)


async def _collect_until(session, predicate, timeout=5.0):
    """Read chunks until predicate(output_bytes) is true or timeout.

    Always aclose()s the read_chunk generator so the loop reader is removed
    and the event loop can shut down cleanly (B1a).
    """
    output = bytearray()
    gen = session.read_chunk()

    async def read_all():
        async for chunk in gen:
            output.extend(chunk)
            if predicate(bytes(output)):
                return

    try:
        try:
            await asyncio.wait_for(read_all(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
    finally:
        await gen.aclose()
    return bytes(output)


@pytest.mark.asyncio
async def test_spawn_echo_hello():
    session = PTYSession("printf 'hello world\\n'")
    pid = await session.spawn()
    assert pid > 0

    output = await _collect_until(session, lambda o: b"hello world" in o)
    assert b"hello world" in output

    # Allow the child to be reaped
    await asyncio.sleep(0.2)
    assert not session.is_alive()
    assert session.exit_code == 0
    session.kill()  # idempotent


@pytest.mark.asyncio
async def test_exit_code_propagates():
    session = PTYSession("exit 7")
    await session.spawn()
    # No output; read_chunk ends on EOF and reaps the child
    chunks = []
    async for chunk in session.read_chunk():
        chunks.append(chunk)
    await asyncio.sleep(0.1)
    assert session.exit_code == 7
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_buffer_trims_to_bound():
    # Produce ~200k bytes; cap the scrollback to 4096
    session = PTYSession("yes | head -c 200000", buffer_bytes=4096)
    await session.spawn()
    await _collect_until(session, lambda o: len(o) > 1000, timeout=5.0)
    # let it finish
    await asyncio.sleep(0.3)
    buf = session.get_buffer()
    assert len(buf) <= 4096
    session.kill()


@pytest.mark.asyncio
async def test_resize_does_not_raise():
    session = PTYSession("sleep 2")
    await session.spawn()
    # Should not raise
    session.resize(120, 40)
    assert session._cols == 120
    assert session._rows == 40
    session.kill()
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_kill_terminates_long_running():
    session = PTYSession("sleep 30")
    await session.spawn()
    assert session.is_alive()
    session.kill()
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_write_stdin_to_cat():
    # cat echoes stdin through the PTY (line discipline echo + cat output)
    session = PTYSession("cat")
    await session.spawn()
    await asyncio.sleep(0.2)  # let cat start

    # Write stdin then read one chunk, always closing the generator
    await session.write_stdin("hi\n")
    gen = session.read_chunk()
    try:
        try:
            chunk = await asyncio.wait_for(gen.__anext__(), timeout=3.0)
        except (StopAsyncIteration, asyncio.TimeoutError):
            chunk = b""
    finally:
        await gen.aclose()
    assert b"hi" in chunk
    session.kill()
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_get_buffer_empty_before_spawn():
    session = PTYSession("echo hi")
    assert session.get_buffer() == b""
    assert session.is_alive()  # not exited yet -> "alive" by current contract


@pytest.mark.asyncio
async def test_double_kill_is_safe():
    session = PTYSession("echo hi")
    await session.spawn()
    session.kill()
    session.kill()  # must not raise
    assert not session.is_alive()


@pytest.mark.asyncio
async def test_kill_wakes_in_flight_read_chunk():
    """kill() mid-iteration must terminate a consumer suspended at queue.get().

    Regression: kill() removed the reader but never pushed the EOF sentinel,
    so an SSE/WS consumer awaiting chunks froze forever.
    """
    session = PTYSession("exec sleep 30")
    await session.spawn()
    await asyncio.sleep(0.2)  # let the child start producing-silently

    chunks = []

    async def consume():
        async for chunk in session.read_chunk():
            chunks.append(chunk)

    # Must complete within a couple of seconds even though sleep 30 is silent
    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.2)  # consumer is now suspended at queue.get()
    session.kill()
    await asyncio.wait_for(task, timeout=3.0)
    assert not session.is_alive()
    session.kill()  # still idempotent after the consumer finished

    # Second kill with a fresh consumer attached also terminates promptly
    # (fd already closed path)
    async def consume_again():
        async for _chunk in session.read_chunk():
            pass

    await asyncio.wait_for(consume_again(), timeout=3.0)


@pytest.mark.asyncio
async def test_child_has_controlling_terminal():
    """The child must be able to open /dev/tty (controlling terminal).

    Regression: child did setsid()+dup2 but never TIOCSCTTY, so /dev/tty
    (sudo password prompts, job control) failed with ENXIO.
    """
    session = PTYSession("exec 3</dev/tty && echo ctty-ok")
    await session.spawn()
    output = await _collect_until(session, lambda o: b"ctty-ok" in o, timeout=5.0)
    assert b"ctty-ok" in output
    session.kill()