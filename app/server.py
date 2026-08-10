"""Local-only metadata dashboard and guarded backup/restore API.

The browser can submit a project slug only. The server resolves all paths from
the local catalog and explicit runtime configuration; it never accepts or
returns environment values, key contents, or subprocess output.
"""

import json
import os
import re
import subprocess
import sys
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("ENVSHELF_DATA_DIR", str(ROOT / "data")))
CATALOG = DATA / "catalog.json"
WEB_ROOT = ROOT / "web" / "dist"
WEB = WEB_ROOT / "index.html"
WEB_FALLBACK = ROOT / "web" / "index.html"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
METADATA_FIELDS = (
    "slug", "name", "gitUrl", "path", "envFile", "envExample", "requiredKeys",
    "environmentCount", "backupFile", "backupExists", "lastBackup", "status",
)


class DashboardError(Exception):
    """Expected, non-secret error suitable for a local dashboard response."""


def _slug(value):
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise DashboardError("invalid project slug")
    return value


def _source_catalog():
    return CATALOG if CATALOG.exists() else ROOT / "data" / "catalog.example.json"


def _read_catalog(path=None):
    source = path or _source_catalog()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DashboardError("could not read the metadata catalog") from exc
    if not isinstance(value, dict) or not isinstance(value.get("projects", []), list):
        raise DashboardError("metadata catalog has an invalid shape")
    return value


def _path(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise DashboardError("project metadata contains an invalid path")
    return Path(value).expanduser()


def _relative_file(project_path, value, default):
    filename = value if value is not None else default
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise DashboardError("project metadata contains an invalid filename")
    candidate = Path(filename)
    if candidate.is_absolute():
        raise DashboardError("project filenames must be relative")
    resolved_project = project_path.resolve()
    resolved = (project_path / candidate).resolve(strict=False)
    try:
        resolved.relative_to(resolved_project)
    except ValueError as exc:
        raise DashboardError("project filename must stay inside the project") from exc
    if (project_path / candidate).is_symlink() or resolved.is_symlink():
        raise DashboardError("refusing to use a symlinked project file")
    return resolved


def _project(catalog_value, slug):
    for project in catalog_value["projects"]:
        if isinstance(project, dict) and project.get("slug", project.get("name")) == slug:
            return project
    raise DashboardError("project is not registered")


def _project_root():
    configured = os.environ.get("ENVSHELF_PROJECT_ROOT")
    if not configured:
        raise DashboardError("project root is not configured")
    return Path(configured).expanduser().resolve()


def _catalog_root():
    """Root represented by paths in catalog.json.

    In Docker, the catalog is commonly authored on the host while the same
    directory is mounted at /workspace. Keeping this separate from the
    container root lets us translate paths without widening the mount.
    """
    configured = os.environ.get("ENVSHELF_CATALOG_ROOT") or os.environ.get(
        "ENVSHELF_PROJECTS_HOST_PATH"
    )
    if not configured:
        return _project_root()
    return Path(configured).expanduser().resolve()


def _runtime_project_path(catalog_path):
    catalog_root = _catalog_root()
    try:
        relative = catalog_path.relative_to(catalog_root)
    except ValueError as exc:
        raise DashboardError("project is outside the configured catalog root") from exc
    project_path = (_project_root() / relative).resolve()
    try:
        project_path.relative_to(_project_root())
    except ValueError as exc:
        raise DashboardError("project is outside the configured project root") from exc
    return project_path


def _guard_project_path(project):
    project_path = _runtime_project_path(_path(project.get("path", ".")).resolve())
    if not project_path.is_dir():
        raise DashboardError("project directory is unavailable")
    return project_path


def _env_keys(path):
    """Return names from .env.example only; never retain the right-hand side."""
    if not path.is_file() or path.is_symlink():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    keys = []
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        if candidate.startswith("export "):
            candidate = candidate[7:].lstrip()
        key = candidate.split("=", 1)[0].split(":", 1)[0].strip()
        if ENV_KEY_RE.fullmatch(key) and key not in keys:
            keys.append(key)
    return keys


def _summary(project):
    slug = _slug(project.get("slug", project.get("name")))
    display_path = _path(project.get("path", "."))
    try:
        project_path = _runtime_project_path(display_path.resolve())
    except DashboardError:
        project_path = display_path
    env_file = project.get("envFile", ".env")
    env_example = project.get("envExample", ".env.example")
    env_path = _relative_file(project_path, env_file, ".env")
    example_path = _relative_file(project_path, env_example, ".env.example")
    backup_name = project.get("backupFile", "backups/" + slug + ".env.age")
    backup_path = _relative_file(project_path, backup_name, "backups/" + slug + ".env.age")
    required = _env_keys(example_path)
    return {"slug": slug, "name": project.get("name", slug),
            "gitUrl": project.get("gitUrl"), "path": str(display_path),
            "envFile": env_file, "envExample": env_example,
            "requiredKeys": required,
            "environmentCount": project.get("environmentCount", len(required)),
            "backupFile": str(backup_path), "backupExists": backup_path.is_file(),
            "lastBackup": project.get("lastBackup"), "status": project.get("status", "registered"),
            "envExists": env_path.is_file()}


def catalog():
    value = _read_catalog()
    projects = []
    for project in value.get("projects", []):
        if not isinstance(project, dict):
            continue
        try:
            item = _summary(project)
        except DashboardError:
            # A malformed local entry is shown as unavailable metadata; it is
            # never allowed to become an action target.
            item = {k: project.get(k) for k in METADATA_FIELDS if k in project}
            item.update({"requiredKeys": [], "backupExists": False, "status": "invalid metadata"})
        projects.append(item)
    return {"projects": projects}


def _action_context(slug):
    source = _source_catalog()
    value = _read_catalog(source)
    project = _project(value, _slug(slug))
    project_path = _guard_project_path(project)
    backup_path = _relative_file(project_path, project.get("backupFile"), "backups/" + slug + ".env.age")
    if not CATALOG.exists():
        raise DashboardError("a writable local catalog is required for actions")
    return source, project_path, backup_path


def _configured_key(name, default):
    value = os.environ.get(name, default)
    path = Path(value).expanduser()
    if not path.is_file() or path.is_symlink():
        raise DashboardError("configured age key file is unavailable")
    return path


def _run_cli(arguments):
    command = [sys.executable, "-m", "app.cli", *arguments]
    try:
        result = subprocess.run(command, cwd=str(ROOT), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=False, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DashboardError("the age operation did not complete") from exc
    if result.returncode:
        raise DashboardError("the age operation failed; no output was written")


def perform_action(slug, action):
    source, project_path, backup_path = _action_context(slug)
    catalog_path = str(source)
    if action == "backup":
        recipient = _configured_key("ENVSHELF_RECIPIENT_FILE", "/keys/recipient.txt")
        _run_cli(["encrypt", "--slug", slug, "--recipient-file", str(recipient),
                  "--output", str(backup_path), "--catalog", catalog_path])
        return {"message": "Encrypted backup created.", "project": _summary(_project(_read_catalog(source), slug))}
    if action == "restore":
        identity = _configured_key("ENVSHELF_IDENTITY_FILE", "/keys/identity.txt")
        if not backup_path.is_file():
            raise DashboardError("encrypted backup was not found")
        _run_cli(["restore", "--slug", slug, "--identity-file", str(identity),
                  "--input", str(backup_path), "--catalog", catalog_path])
        return {"message": "Environment restored; any previous file was preserved.",
                "project": _summary(_project(_read_catalog(source), slug))}
    raise DashboardError("unsupported action")


def _json_bytes(value):
    return json.dumps(value, separators=(",", ":")).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type="application/json", status=200):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, value, status=200):
        self.send_bytes(_json_bytes(value), status=status)

    @staticmethod
    def _asset(path):
        """Resolve a dist asset without allowing traversal or symlinks."""
        raw = unquote(path)
        if "\x00" in raw or "\\" in raw:
            raise DashboardError("invalid asset path")
        relative = raw.removeprefix("/")
        if not relative or Path(relative).is_absolute():
            raise DashboardError("invalid asset path")
        lexical = WEB_ROOT / relative
        cursor = WEB_ROOT
        for part in Path(relative).parts:
            cursor = cursor / part
            if cursor.is_symlink():
                raise DashboardError("refusing to serve a symlinked dashboard asset")
        candidate = lexical.resolve(strict=False)
        try:
            candidate.relative_to(WEB_ROOT.resolve())
        except ValueError as exc:
            raise DashboardError("asset path is outside the dashboard") from exc
        if not candidate.is_file():
            raise DashboardError("dashboard asset was not found")
        return candidate

    def do_GET(self):
        route = urlsplit(self.path).path
        try:
            if route == "/api/health":
                self.send_json({"ok": True, "secretValues": "never exposed"})
            elif route == "/api/projects":
                self.send_json(catalog())
            elif route in ("/", "/index.html"):
                page = WEB if WEB.is_file() else WEB_FALLBACK
                self.send_bytes(page.read_bytes(), "text/html; charset=utf-8")
            elif route.startswith("/assets/"):
                asset = self._asset(route)
                content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                self.send_bytes(asset.read_bytes(), content_type)
            else:
                self.send_error(404)
        except DashboardError as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self):
        route = urlsplit(self.path).path
        match = re.fullmatch(r"/api/projects/([a-z0-9][a-z0-9._-]{0,62})/(backup|restore)", route)
        if not match:
            self.send_error(404)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > 0:
            if content_length > 0:
                self.rfile.read(content_length)
            self.send_json({"error": "action requests must have an empty body"}, status=400)
            return
        try:
            result = perform_action(match.group(1), match.group(2))
            self.send_json(result)
        except DashboardError as exc:
            self.send_json({"error": str(exc)}, status=409)

    def log_message(self, fmt, *args):
        print("envshelf", self.command, self.path.split("?", 1)[0])


if __name__ == "__main__":
    ThreadingHTTPServer((os.environ.get("ENVSHELF_BIND", "127.0.0.1"),
                         int(os.environ.get("ENVSHELF_PORT", "8787"))), Handler).serve_forever()
