"""Exercise the real HTTPS gateway when Caddy is installed."""
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import shutil
import socket
import subprocess
from threading import Thread
import time

import httpx
import pytest


@pytest.mark.skipif(not shutil.which("caddy"), reason="Caddy executable required for gateway acceptance")
def test_gateway_protects_ui_and_api(tmp_path):
    class Echo(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            if self.headers.get("Authorization"):
                self.wfile.write(b"leaked")
            elif self.headers.get("X-EGX-Gateway") == gateway and self.path.startswith("/api/"):
                self.wfile.write(b"owner")
            else:
                self.wfile.write(b"ok")

        do_POST = do_GET

        def log_message(self, *args):
            pass

    gateway = secrets.token_urlsafe(32)
    caddy = shutil.which("caddy")
    password = secrets.token_urlsafe(24)
    hashed = subprocess.run([caddy, "hash-password"], input=password, text=True, check=True,
                            capture_output=True).stdout.strip()
    with socket.socket() as unused:
        unused.bind(("127.0.0.1", 0))
        port = unused.getsockname()[1]
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Echo)
    Thread(target=upstream.serve_forever, daemon=True).start()
    address = f"127.0.0.1:{upstream.server_port}"
    host = f"localhost:{port}"
    origin = f"https://{host}"
    env = {**os.environ, "APP_HOST": host, "OWNER_PASSWORD_HASH": hashed,
           "XDG_DATA_HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path),
           "BACKEND_UPSTREAM": address, "FRONTEND_UPSTREAM": address,
           "INTEGRATIONS_GATEWAY_SECRET": gateway}
    source = Path(__file__).resolve().parents[2] / "deploy" / "Caddyfile"
    config = tmp_path / "Caddyfile"
    config.write_text("{\n admin off\n auto_https disable_redirects\n skip_install_trust\n}\n" + source.read_text())
    process = subprocess.Popen([caddy, "run", "--config", str(config)], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        cert = tmp_path / "caddy/pki/authorities/local/root.crt"
        for _ in range(100):
            assert process.poll() is None
            if cert.exists():
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.1):
                        break
                except OSError:
                    pass
            time.sleep(.05)
        import ssl
        with httpx.Client(base_url=origin, verify=ssl.create_default_context(cafile=str(cert)),
                          trust_env=False) as client:
            for path in ("/", "/api/v1/egx/stocks"):
                assert client.get(path).status_code == 401
                assert client.get(path, auth=("owner", "incorrect")).status_code == 401
                response = client.get(path, auth=("owner", password))
                assert response.text == ("owner" if path.startswith("/api/") else "ok")
                assert "no-store" in response.headers["Cache-Control"]
            headers = {"X-EGX-Gateway": "from-browser"}
            assert client.get("/portfolio", auth=("owner", password), headers=headers).text == "ok"
            assert client.get("/api/v1/integrations/thndr/status", auth=("owner", password), headers=headers).text == "owner"
            url = "/api/v1/egx/live-analysis/manual-eod"
            for headers in ({}, {"Origin": "https://untrusted.example"}):
                assert client.post(url, auth=("owner", password), headers=headers).status_code == 403
            assert client.post(url, auth=("owner", password), headers={"Origin": origin}).text == "owner"
    finally:
        process.terminate()
        process.wait(timeout=10)
        upstream.shutdown()
        upstream.server_close()
