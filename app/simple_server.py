from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from app import config
from app.models import TeachingRequest
from app.pipeline import generate_teaching_assets


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/health"}:
            self._json({"status": "ok", "endpoint": "/generate"})
            return
        if parsed.path.startswith("/static/"):
            self._file(parsed.path.removeprefix("/static/"))
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._json({"status": "ok", "endpoint": "/generate"})
            return
        if parsed.path not in {"/generate", "/api/generate"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        try:
            req = TeachingRequest.model_validate_json(body)
            assets = generate_teaching_assets(req)
            base = config.PUBLIC_BASE_URL or f"http://{self.headers.get('Host', '127.0.0.1:8000')}"
            response = {
                "video_url": _url_for(base, assets["video"]),
                "subtitle_url": _url_for(base, assets["subtitle"]),
                "supplementary_url": [_url_for(base, path) for path in assets["supplementary"]],
            }
            self._json(response)
        except Exception as exc:
            self._json({"error": str(exc)}, status=500)

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _file(self, rel_path: str) -> None:
        target = (config.OUTPUT_DIR / unquote(rel_path)).resolve()
        if not str(target).startswith(str(config.OUTPUT_DIR.resolve())) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = "application/octet-stream"
        if target.suffix == ".mp4":
            content_type = "video/mp4"
        elif target.suffix == ".vtt":
            content_type = "text/vtt"
        elif target.suffix == ".pdf":
            content_type = "application/pdf"
        data = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _url_for(base: str, path: Path | str) -> str:
    rel = Path(path).resolve().relative_to(config.OUTPUT_DIR)
    return f"{base.rstrip('/')}/static/{rel.as_posix()}"


def main() -> None:
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    print("Serving on http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
