import os
import socket
import subprocess
import sys
import time

import socketio


def _start_socketio_server() -> tuple[int, subprocess.Popen]:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=os.environ,
    )

    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("Socket.IO server process exited prematurely")
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.settimeout(0.25)
                probe.connect(("127.0.0.1", port))
            break
        except OSError:
            time.sleep(0.25)
    else:
        process.terminate()
        process.wait(timeout=2)
        raise RuntimeError("Socket.IO server failed to start")

    return port, process


class SocketRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def record_bot_response(self, data):
        self.events.append(("bot_response", data))

    def record_salon_cards(self, data):
        self.events.append(("salon_cards", data))


def _build_client(recorder: SocketRecorder) -> socketio.Client:
    client = socketio.Client(logger=False, engineio_logger=False)
    client.on("bot_response", recorder.record_bot_response)
    client.on("salon_cards", recorder.record_salon_cards)
    return client


def _wait_for_event(recorder: SocketRecorder, event_name: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if any(name == event_name for name, _ in recorder.events):
            return True
        time.sleep(0.1)
    return False


def _shutdown_server(client: socketio.Client, process: subprocess.Popen) -> None:
    try:
        client.disconnect()
    except Exception:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


def test_greeting_and_simple_faq():
    port, process = _start_socketio_server()
    recorder = SocketRecorder()
    client = _build_client(recorder)

    try:
        client.connect(f"http://127.0.0.1:{port}", transports=["polling"], socketio_path="/socket.io")
        time.sleep(0.25)

        assert any(name == "bot_response" for name, _ in recorder.events), "Expected greeting bot_response on connect"

        client.emit("user_message", {"session_id": "s1", "message": "What is Bookly?"})
        assert _wait_for_event(recorder, "bot_response", timeout=5.0), "Expected bot_response after FAQ message"
    finally:
        _shutdown_server(client, process)


def test_booking_flow_returns_salon_cards():
    port, process = _start_socketio_server()
    recorder = SocketRecorder()
    client = _build_client(recorder)

    try:
        client.connect(f"http://127.0.0.1:{port}", transports=["polling"], socketio_path="/socket.io")
        time.sleep(0.25)

        client.emit("user_message", {"session_id": "s2", "message": "I want to book an appointment"})
        assert _wait_for_event(recorder, "bot_response", timeout=5.0), "Expected bot_response after booking intent"

        client.emit("user_message", {"session_id": "s2", "message": "Hair Smoothing"})
        assert _wait_for_event(recorder, "bot_response", timeout=5.0), "Expected bot_response after service follow-up"

        client.emit("user_message", {"session_id": "s2", "message": "Dubai"})
        assert _wait_for_event(recorder, "salon_cards", timeout=10.0), f"Expected salon_cards in events, got {recorder.events}"
    finally:
        _shutdown_server(client, process)
