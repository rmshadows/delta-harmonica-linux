from __future__ import annotations

import json
from http.server import SimpleHTTPRequestHandler
from pathlib import Path


class PreviewRequestHandler(SimpleHTTPRequestHandler):
    """Static files + POST /api/save-score to write under scores/."""

    # Set by factory
    project_root: Path

    def log_message(self, fmt: str, *args: object) -> None:
        # quieter than default
        if args and str(args[0]).startswith("POST"):
            super().log_message(fmt, *args)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/api/list-scores":
            scores_dir = self.project_root / "scores"
            items = []
            if scores_dir.is_dir():
                for p in sorted(scores_dir.glob("*.txt")):
                    title = p.stem
                    try:
                        for line in p.read_text(encoding="utf-8").splitlines()[:12]:
                            if line.lower().startswith("title:"):
                                title = line.split(":", 1)[1].strip() or title
                                break
                    except OSError:
                        pass
                    items.append({"id": p.stem, "path": f"scores/{p.name}", "title": title})
            body = json.dumps({"ok": True, "scores": items}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/save-score":
            self.send_error(404, "not found")
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
            rel = str(data.get("path", "")).strip().lstrip("/")
            content = data.get("content")
            if not isinstance(content, str):
                raise ValueError("content must be a string")
            if not rel.startswith("scores/") or ".." in rel or rel.endswith("/"):
                raise ValueError("path must be under scores/, e.g. scores/tonghua.txt")
            if not rel.endswith(".txt"):
                raise ValueError("only .txt scores can be saved")
            dest = (self.project_root / rel).resolve()
            scores = (self.project_root / "scores").resolve()
            if not str(dest).startswith(str(scores) + "/") and dest != scores:
                raise ValueError("refusing to write outside scores/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            body = json.dumps({"ok": False, "error": str(exc)}).encode("utf-8")
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        body = json.dumps({"ok": True, "path": rel}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_handler(root: Path) -> type[PreviewRequestHandler]:
    class Bound(PreviewRequestHandler):
        def __init__(self, *args, **kwargs):
            self.project_root = root
            super().__init__(*args, directory=str(root), **kwargs)

    return Bound
