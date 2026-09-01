#!/usr/bin/env python3
"""rich-render document server.

Serves rich HTML documents (markdown + KaTeX + Mermaid) over localhost.
Standard library only -- no pip, no uv, no third-party packages.
All JS/CSS/font assets are vendored under ../assets and served locally,
so the server works with no network access at all.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import shutil
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

APP = "rich-render"
VERSION = "1.0.0"

PLUGIN_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = PLUGIN_DIR / "assets"
SERVER_DIR = PLUGIN_DIR / "server"

DEFAULT_PORT = 3001
DEFAULT_HOST = "0.0.0.0"
PORT_SCAN_RANGE = 20
SESSION_REUSE_HOURS = 12
DEFAULT_PRUNE_DAYS = 30

mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/markdown", ".md")


# --------------------------------------------------------------------------
# paths / state
# --------------------------------------------------------------------------

def home_dir() -> Path:
    return Path(os.environ.get("RICH_RENDER_HOME", Path.home() / ".claude" / APP)).expanduser()


def sessions_dir() -> Path:
    return home_dir() / "sessions"


def state_file() -> Path:
    return home_dir() / "server.json"


def log_file() -> Path:
    return home_dir() / "server.log"


def default_port() -> int:
    raw = os.environ.get("RICH_RENDER_PORT", "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_PORT


def default_host() -> str:
    """Bind address. Defaults to all interfaces so a remote machine (VPN, LAN,
    a named server) can reach the documents. Set RICH_RENDER_HOST=127.0.0.1 to
    restrict it to this machine."""
    return os.environ.get("RICH_RENDER_HOST", "").strip() or DEFAULT_HOST


def local_ip() -> str | None:
    """Best-guess outward-facing IPv4, without sending any traffic."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # TEST-NET-1, never routed
            return sock.getsockname()[0]
    except OSError:
        return None


def public_urls(port: int, host: str) -> list[str]:
    """Reachable URLs, best first. A wildcard bind is advertised by hostname
    and LAN IP, because 127.0.0.1 is useless to a remote viewer."""
    if host not in ("0.0.0.0", "::", ""):
        return [f"http://{host}:{port}"]
    urls = []
    hostname = socket.gethostname()
    if hostname and hostname != "localhost":
        urls.append(f"http://{hostname}:{port}")
    ip = local_ip()
    if ip and f"http://{ip}:{port}" not in urls:
        urls.append(f"http://{ip}:{port}")
    urls.append(f"http://127.0.0.1:{port}")
    return urls


def read_state() -> dict:
    try:
        return json.loads(state_file().read_text())
    except (OSError, ValueError):
        return {}


def write_state(data: dict) -> None:
    home_dir().mkdir(parents=True, exist_ok=True)
    state_file().write_text(json.dumps(data, indent=2))


def slugify(text: str, fallback: str = "doc") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return (slug or fallback)[:60]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------

def read_session_meta(path: Path) -> dict:
    try:
        return json.loads((path / "session.json").read_text())
    except (OSError, ValueError):
        return {}


def list_sessions() -> list[Path]:
    root = sessions_dir()
    if not root.is_dir():
        return []
    dirs = [p for p in root.iterdir() if p.is_dir()]
    return sorted(dirs, key=lambda p: p.name, reverse=True)


def get_or_create_session(project: str | None, force_new: bool = False) -> Path:
    cwd = str(Path(project).resolve()) if project else os.getcwd()
    if not force_new:
        cutoff = time.time() - SESSION_REUSE_HOURS * 3600
        for path in list_sessions():
            meta = read_session_meta(path)
            if meta.get("cwd") == cwd and path.stat().st_mtime >= cutoff:
                return path
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{stamp}-{slugify(Path(cwd).name, 'session')}"
    path = sessions_dir() / name
    suffix = 2
    while path.exists():
        path = sessions_dir() / f"{name}-{suffix}"
        suffix += 1
    path.mkdir(parents=True)
    (path / "session.json").write_text(json.dumps({
        "cwd": cwd,
        "project": Path(cwd).name,
        "created": now_iso(),
    }, indent=2))
    return path


FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n", re.DOTALL)


def parse_front_matter(text: str) -> dict:
    """Minimal `key: value` front matter reader. Not a YAML parser."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip("\"'")
    return meta


def describe_doc(path: Path) -> dict:
    try:
        head = path.read_text(errors="replace")[:4000]
    except OSError:
        head = ""
    meta = parse_front_matter(head)
    title = meta.get("title")
    if not title:
        heading = re.search(r"^#\s+(.+)$", head, re.MULTILINE)
        title = heading.group(1).strip() if heading else path.stem
    stat = path.stat()
    return {
        "slug": path.stem,
        "title": title,
        "kind": meta.get("kind", "doc"),
        "summary": meta.get("summary", ""),
        "mtime": stat.st_mtime,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "bytes": stat.st_size,
    }


def index_payload() -> dict:
    out = []
    for session in list_sessions():
        docs = sorted(session.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not docs:
            continue
        meta = read_session_meta(session)
        out.append({
            "id": session.name,
            "project": meta.get("project", session.name),
            "cwd": meta.get("cwd", ""),
            "created": meta.get("created", ""),
            "docs": [describe_doc(d) for d in docs],
        })
    return {"app": APP, "version": VERSION, "home": str(home_dir()), "sessions": out}


def prune(days: int) -> list[str]:
    cutoff = time.time() - days * 86400
    removed = []
    for session in list_sessions():
        docs = list(session.glob("*.md"))
        newest = max((d.stat().st_mtime for d in docs), default=session.stat().st_mtime)
        if newest < cutoff:
            shutil.rmtree(session, ignore_errors=True)
            removed.append(session.name)
    return removed


# --------------------------------------------------------------------------
# http
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = f"{APP}/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter log
        sys.stderr.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))

    # -- helpers ---------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data: dict, code: int = 200):
        self._send(code, json.dumps(data).encode(), "application/json; charset=utf-8")

    def _text(self, code: int, message: str):
        self._send(code, message.encode(), "text/plain; charset=utf-8")

    def _file(self, path: Path, cache: str = "no-store"):
        try:
            body = path.read_bytes()
        except OSError:
            return self._text(404, "not found")
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, body, ctype, cache)

    @staticmethod
    def _safe_join(root: Path, relative: str) -> Path | None:
        candidate = (root / relative.lstrip("/")).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return None
        return candidate

    # -- routes ----------------------------------------------------------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)

        if path == "/health" or path == "/__rich_render/health":
            return self._json({
                "app": APP, "version": VERSION, "pid": os.getpid(),
                "home": str(home_dir()), "port": self.server.server_address[1],
                "host": self.server.server_address[0],
            })

        if path == "/__rich_render/index.json":
            return self._json(index_payload())

        if path == "/__rich_render/poll":
            doc = (query.get("doc") or [""])[0]
            known = float((query.get("mtime") or ["0"])[0] or 0)
            target = self._safe_join(sessions_dir(), doc + ".md") if doc else None
            if not target or not target.is_file():
                return self._json({"exists": False, "changed": False, "mtime": 0})
            mtime = target.stat().st_mtime
            return self._json({"exists": True, "changed": mtime > known + 1e-6, "mtime": mtime})

        if path == "/" or path == "/index.html":
            return self._file(SERVER_DIR / "index.html")

        if path.startswith("/doc/"):
            return self._file(SERVER_DIR / "template.html")

        if path.startswith("/raw/"):
            target = self._safe_join(sessions_dir(), path[len("/raw/"):])
            if not target or not target.is_file():
                return self._text(404, "document not found")
            return self._file(target)

        if path.startswith("/assets/"):
            rel = path[len("/assets/"):]
            local = self._safe_join(SERVER_DIR, rel)
            if local and local.is_file() and local.suffix in (".css", ".js"):
                return self._file(local, cache="no-cache")
            target = self._safe_join(ASSETS_DIR, rel)
            if not target or not target.is_file():
                return self._text(404, "asset not found")
            return self._file(target, cache="public, max-age=604800")

        if path == "/favicon.ico":
            return self._send(200, FAVICON, "image/svg+xml", "public, max-age=86400")

        return self._text(404, "not found")


FAVICON = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    b'<rect width="32" height="32" rx="7" fill="#4f46e5"/>'
    b'<text x="16" y="23" font-size="19" font-family="Georgia,serif" font-style="italic"'
    b' fill="#fff" text-anchor="middle">f</text></svg>'
)


# --------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------

def probe(port: int) -> dict | None:
    """Return health payload if a rich-render server owns this port.

    Always checked over loopback: a wildcard-bound server answers there too,
    and a host-restricted one is reachable from this machine by definition."""
    host = default_host()
    check = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    try:
        with urllib.request.urlopen(f"http://{check}:{port}/health", timeout=0.6) as resp:
            data = json.loads(resp.read().decode())
        return data if data.get("app") == APP else None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError):
        return None


def port_is_free(port: int, host: str | None = None) -> bool:
    """Test-bind the address we will actually serve on -- a port free on
    loopback can still be taken on 0.0.0.0, and vice versa."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host or default_host(), port))
            return True
        except OSError:
            return False


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def resolve_port(preferred: int, host: str | None = None) -> tuple[int, dict | None, list[int]]:
    """(port_to_use, existing_server_health, ports_skipped)."""
    skipped = []
    for candidate in range(preferred, preferred + PORT_SCAN_RANGE):
        health = probe(candidate)
        if health and health.get("home") == str(home_dir()):
            return candidate, health, skipped
        if port_is_free(candidate, host):
            return candidate, None, skipped
        skipped.append(candidate)
    raise SystemExit(f"no free port in {preferred}-{preferred + PORT_SCAN_RANGE - 1}")


def daemonize() -> None:
    if os.fork() > 0:
        os._exit(0)
    os.setsid()
    if os.fork() > 0:
        os._exit(0)
    home_dir().mkdir(parents=True, exist_ok=True)
    sys.stdout.flush()
    sys.stderr.flush()
    devnull = os.open(os.devnull, os.O_RDONLY)
    logfd = os.open(str(log_file()), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.dup2(devnull, 0)
    os.dup2(logfd, 1)
    os.dup2(logfd, 2)


def run_server(port: int, host: str | None = None) -> None:
    host = host or default_host()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    write_state({
        "pid": os.getpid(), "port": port, "host": host, "home": str(home_dir()),
        "plugin": str(PLUGIN_DIR), "started": now_iso(), "version": VERSION,
    })

    def shutdown(*_):
        try:
            state_file().unlink(missing_ok=True)
        finally:
            os._exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    sys.stderr.write(f"[{now_iso()}] {APP} {VERSION} listening on {host}:{port}\n")
    sys.stderr.flush()
    httpd.serve_forever()


def wait_until_up(port: int, timeout: float = 6.0) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        health = probe(port)
        if health:
            return health
        time.sleep(0.12)
    return None


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def find_running() -> tuple[int, dict] | tuple[None, None]:
    """Locate a live server owning this home: recorded state first, then a port scan."""
    recorded = read_state().get("port")
    candidates = ([recorded] if recorded else []) + \
        [p for p in range(default_port(), default_port() + PORT_SCAN_RANGE) if p != recorded]
    for port in candidates:
        health = probe(port)
        if health and health.get("home") == str(home_dir()):
            return port, health
    return None, None


def cmd_start(args) -> int:
    home_dir().mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    preferred = args.port or default_port()
    host = args.host or default_host()

    # Reuse whatever is already serving this home, so a port bump can never
    # leave a second server orphaned. An explicit --port that disagrees is a
    # deliberate move: retire the old server first.
    live_port, live_health = find_running()
    if live_port is not None and args.port and args.port != live_port:
        pid = live_health.get("pid")
        if pid and pid_alive(pid):
            os.kill(pid, signal.SIGTERM)
            for _ in range(40):
                if not pid_alive(pid):
                    break
                time.sleep(0.05)
        live_port, live_health = None, None

    # A host change also needs a restart -- the bind address is fixed at listen.
    if live_port is not None and live_health.get("host") not in (None, host):
        if terminate(live_health.get("pid")):
            live_port, live_health = None, None

    if live_port is not None:
        port, existing, skipped = live_port, live_health, []
    else:
        port, existing, skipped = resolve_port(preferred, host)
    reused = existing is not None

    if not reused:
        pruned = prune(args.prune_days)
        if os.fork() == 0:
            daemonize()
            run_server(port, host)
            os._exit(0)
        os.wait()  # reap the intermediate child
        if not wait_until_up(port):
            print(json.dumps({"ok": False, "error": f"server did not come up on port {port}",
                              "log": str(log_file())}))
            return 1
    else:
        pruned = []

    session = get_or_create_session(args.project, force_new=args.new_session)
    urls = public_urls(port, host)
    base = urls[0]
    print(json.dumps({
        "ok": True,
        "url": base,
        "urls": urls,
        "port": port,
        "host": host,
        "reused_server": reused,
        "requested_port": preferred,
        "ports_busy": skipped,
        "session_id": session.name,
        "session_dir": str(session),
        "doc_url_base": f"{base}/doc/{session.name}",
        "pruned_sessions": pruned,
        "log": str(log_file()),
    }, indent=2))
    return 0


def cmd_status(args) -> int:
    state = read_state()
    port = state.get("port") or default_port()
    health = probe(port)
    host = (health or {}).get("host") or state.get("host") or default_host()
    payload = {
        "running": bool(health),
        "port": port if health else None,
        "host": host if health else None,
        "pid": state.get("pid") if health else None,
        "url": public_urls(port, host)[0] if health else None,
        "urls": public_urls(port, host) if health else [],
        "home": str(home_dir()),
        "state_file": str(state_file()),
        "log": str(log_file()),
        "documents": index_payload()["sessions"],
    }
    print(json.dumps(payload, indent=2))
    return 0 if health else 1


def terminate(pid: int) -> bool:
    if not pid or not pid_alive(pid):
        return False
    os.kill(pid, signal.SIGTERM)
    for _ in range(40):
        if not pid_alive(pid):
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        pass
    return True


def cmd_stop(args) -> int:
    """Sweep the scan range so a port-bumped server can never be left behind."""
    stopped = []
    recorded = read_state()
    ports = {recorded.get("port")} | set(range(default_port(), default_port() + PORT_SCAN_RANGE))
    for port in sorted(p for p in ports if p):
        health = probe(port)
        if health and health.get("home") == str(home_dir()):
            if terminate(health.get("pid")):
                stopped.append({"pid": health.get("pid"), "port": port})
    state_file().unlink(missing_ok=True)
    message = ("stopped " + ", ".join(f"pid {s['pid']} on port {s['port']}" for s in stopped)
               if stopped else "no server running")
    print(json.dumps({"ok": True, "stopped": stopped, "message": message}))
    return 0


def cmd_session(args) -> int:
    sessions_dir().mkdir(parents=True, exist_ok=True)
    session = get_or_create_session(args.project, force_new=args.new_session)
    state = read_state()
    port = state.get("port") or default_port()
    host = state.get("host") or default_host()
    print(json.dumps({
        "session_id": session.name,
        "session_dir": str(session),
        "doc_url_base": f"{public_urls(port, host)[0]}/doc/{session.name}",
    }, indent=2))
    return 0


def cmd_prune(args) -> int:
    removed = prune(args.days)
    print(json.dumps({"ok": True, "days": args.days, "removed": removed}, indent=2))
    return 0


def cmd_run(args) -> int:
    """Run in the foreground (debugging / manual use)."""
    home_dir().mkdir(parents=True, exist_ok=True)
    sessions_dir().mkdir(parents=True, exist_ok=True)
    host = args.host or default_host()
    port, existing, _ = resolve_port(args.port or default_port(), host)
    if existing:
        print(f"already running on {port}", file=sys.stderr)
        return 1
    run_server(port, host)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="serve.py", description=f"{APP} document server")
    sub = parser.add_subparsers(dest="command")

    start = sub.add_parser("start", help="start (or reuse) the server and return a session")
    start.add_argument("--port", type=int, default=None)
    start.add_argument("--host", default=None,
                       help="bind address (default 0.0.0.0 = reachable from other machines)")
    start.add_argument("--project", default=None, help="project directory the docs belong to")
    start.add_argument("--new-session", action="store_true", help="force a fresh session")
    start.add_argument("--prune-days", type=int,
                       default=int(os.environ.get("RICH_RENDER_PRUNE_DAYS", DEFAULT_PRUNE_DAYS)))
    start.set_defaults(func=cmd_start)

    status = sub.add_parser("status", help="report server state and known documents")
    status.set_defaults(func=cmd_status)

    stop = sub.add_parser("stop", help="stop the running server")
    stop.set_defaults(func=cmd_stop)

    session = sub.add_parser("session", help="get or create the session directory")
    session.add_argument("--project", default=None)
    session.add_argument("--new-session", action="store_true")
    session.set_defaults(func=cmd_session)

    pr = sub.add_parser("prune", help="delete sessions older than N days")
    pr.add_argument("--days", type=int, default=DEFAULT_PRUNE_DAYS)
    pr.set_defaults(func=cmd_prune)

    run = sub.add_parser("run", help="run in the foreground")
    run.add_argument("--port", type=int, default=None)
    run.add_argument("--host", default=None)
    run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
