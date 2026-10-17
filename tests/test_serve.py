"""scripts/serve.py: the dev server for web/ says Cache-Control: no-store on every response, and queues a
burst of connections instead of resetting them."""
import functools
import http.client
import http.server
import importlib.util
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SERVE = ROOT / "scripts" / "serve.py"


def load_serve():
    spec = importlib.util.spec_from_file_location("hfh_serve", SERVE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        res = conn.getresponse()
        return res.status, res.getheader("Cache-Control"), res.read()
    finally:
        conn.close()


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_handler_sends_no_store():
    """The same handler and folder as main() builds, on a free port (never 8642, which is the preview server)."""
    serve = load_serve()
    assert serve.WEB == ROOT / "web"
    handler = functools.partial(serve.NoStore, directory=str(serve.WEB))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        port = httpd.server_address[1]
        status, cache, body = get(port, "/index.html")
        assert status == 200 and cache == "no-store" and b"<title>Hus f" in body
        status, cache, body = get(port, "/fonts/inter/OFL.txt")  # a self-hosted font folder
        assert status == 200 and cache == "no-store" and body
        status, cache, _ = get(port, "/no-such-file")
        assert status == 404 and cache == "no-store"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)


def test_command_line_serves_web_on_the_given_port():
    port = free_port()
    proc = subprocess.Popen([sys.executable, str(SERVE), str(port)], stdout=subprocess.PIPE, text=True)
    try:
        assert f"http://127.0.0.1:{port}/" in proc.stdout.readline()  # printed once the socket is bound
        deadline = time.time() + 10
        while True:
            try:
                status, cache, _ = get(port, "/index.html")
                break
            except OSError:
                assert time.time() < deadline, "the server did not answer"
                time.sleep(0.1)
        assert status == 200 and cache == "no-store"
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        proc.stdout.close()


def test_server_keeps_a_deep_listen_queue():
    """The page asks for about 15 modules at once. socketserver's default listen backlog of 5 lets macOS reset the
    connections beyond it, and the e2e tests then hang at "Building the city 0%"."""
    serve = load_serve()
    assert issubclass(serve.Server, http.server.ThreadingHTTPServer)
    assert serve.Server.request_queue_size == 128


def test_main_serves_with_the_deep_queue(monkeypatch):
    serve = load_serve()
    made = []

    class Made(Exception):
        pass

    class Recorder:
        def __init__(self, address, handler):
            made.append((address, handler.func))
            raise Made

    monkeypatch.setattr(serve, "Server", Recorder)
    with pytest.raises(Made):
        serve.main(["8999"])
    assert made == [(("127.0.0.1", 8999), serve.NoStore)]


def test_a_burst_of_connections_waits_in_the_queue():
    """40 clients connect before the server accepts any: all are queued and answered, none is reset."""
    serve = load_serve()
    httpd = serve.Server(("127.0.0.1", 0), functools.partial(serve.NoStore, directory=str(serve.WEB)))
    port = httpd.server_address[1]
    socks, thread = [], threading.Thread(target=httpd.serve_forever, daemon=True)
    try:
        for _ in range(40):
            socks.append(socket.create_connection(("127.0.0.1", port), timeout=10))
        thread.start()
        for s in socks:
            s.sendall(b"GET /index.html HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
        for s in socks:
            assert s.makefile("rb").readline().split()[1] == b"200"
    finally:
        for s in socks:
            s.close()
        if thread.is_alive():
            httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)
