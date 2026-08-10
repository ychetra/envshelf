"""Local-only metadata dashboard and guarded backup/restore API.

The browser can submit a project slug only. The server resolves all paths from
the local catalog and explicit runtime configuration; it never accepts or
returns environment values, key contents, or subprocess output.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import mimetypes
import tempfile
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
    "pinned",
)


def _standalone_mode():
    """Return whether the dashboard is running against native host paths.

    Docker remains the default for backwards compatibility.  The standalone
    launcher sets this explicitly and supplies an allowlisted project root;
    the browser still receives only metadata in either mode.
    """
    return os.environ.get("ENVSHELF_MODE", "docker").strip().lower() == "standalone"


class DashboardError(Exception):
    """Expected, non-secret error suitable for a local dashboard response."""


def _slug(value):
    if not isinstance(value, str) or not SLUG_RE.fullmatch(value):
        raise DashboardError("invalid project slug")
    return value


def _source_catalog():
    # The Docker image uses the checked-in fixture for a first-run preview.
    # Native mode must start with an empty, user-local catalog instead of
    # displaying the fixture as if it were a real project.
    return CATALOG if CATALOG.exists() or _standalone_mode() else ROOT / "data" / "catalog.example.json"


def _read_catalog(path=None):
    source = path or _source_catalog()
    if _standalone_mode() and source == CATALOG and not source.exists():
        return {"projects": []}
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DashboardError("could not read the metadata catalog") from exc
    if not isinstance(value, dict) or not isinstance(value.get("projects", []), list):
        raise DashboardError("metadata catalog has an invalid shape")
    return value


def _write_catalog(value):
    """Atomically persist local metadata; the catalog never contains secrets."""
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".catalog.", dir=str(CATALOG.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, CATALOG)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _path(value):
    if isinstance(value, Path):
        return value.expanduser()
    if not isinstance(value, str) or not value or "\x00" in value:
        raise DashboardError("project metadata contains an invalid path")
    return Path(value).expanduser()


def _assert_no_symlink_path(path):
    """Reject symlinks in a user-selected path, including a symlinked leaf."""
    if not path.is_absolute():
        raise DashboardError("project paths must be absolute")
    # macOS exposes /var and /tmp as stable system aliases to /private/*;
    # accepting those aliases does not widen the configured root, while user
    # supplied symlink components below them remain rejected.
    system_aliases = {Path("/var"), Path("/tmp")}
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink() and cursor not in system_aliases:
            raise DashboardError("project paths cannot contain symlinks")


def _allowed_project_roots():
    """Return explicit container-side roots available to dashboard actions."""
    configured = os.environ.get("ENVSHELF_ALLOWED_PROJECT_ROOTS", "")
    values = [item.strip() for item in configured.split(",") if item.strip()]
    if not values:
        legacy = os.environ.get("ENVSHELF_PROJECT_ROOT")
        if legacy:
            values = [legacy]
    if not values:
        raise DashboardError("allowed project roots are not configured")
    roots = []
    for value in values:
        root = _path(value)
        if not root.is_absolute() or "\x00" in value:
            raise DashboardError("allowed project roots must be absolute")
        resolved = root.resolve(strict=False)
        if not root.exists() or not root.is_dir() or root.is_symlink():
            raise DashboardError("an allowed project root is unavailable")
        if resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


def _inside_allowed_root(path, require_directory=False):
    """Resolve a path only when it is inside an explicitly mounted root."""
    candidate = _path(path)
    _assert_no_symlink_path(candidate)
    resolved = candidate.resolve(strict=False)
    for root in _allowed_project_roots():
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        if require_directory and not candidate.is_dir():
            raise DashboardError("project directory is unavailable")
        return resolved
    raise DashboardError("project path is outside the configured allowed roots")


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
    return _allowed_project_roots()[0]


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


def _host_path_to_runtime(path):
    """Translate a helper's host path into the explicit container mount.

    The native helper may know `/Users/me/Projects/app`, while the dashboard
    sees that same directory as `/workspace/app`. Translation is allowed only
    below the configured catalog root and only after rejecting symlinked path
    components. No arbitrary host path becomes a container action target.
    """
    candidate = _path(path)
    configured = os.environ.get("ENVSHELF_CATALOG_ROOT") or os.environ.get(
        "ENVSHELF_PROJECTS_HOST_PATH"
    )
    lexical_root = _path(configured) if configured else _project_root()
    if lexical_root.is_symlink():
        raise DashboardError("configured catalog root cannot be a symlink")
    catalog_root = lexical_root.resolve()
    if not catalog_root.is_absolute() or not catalog_root.exists() or not catalog_root.is_dir():
        raise DashboardError("configured catalog root is unavailable")
    # System prefixes such as macOS `/var` may themselves be symlinks. Check
    # only the user-controlled path below the configured root, while resolving
    # the complete path for the containment check.
    try:
        lexical_relative = candidate.relative_to(lexical_root)
    except ValueError:
        lexical_relative = None
    if lexical_relative is not None:
        cursor = catalog_root
        for part in lexical_relative.parts:
            cursor /= part
            if cursor.is_symlink():
                raise DashboardError("project paths cannot contain symlinks")
    resolved = candidate.resolve(strict=False)
    try:
        relative = resolved.relative_to(catalog_root)
    except ValueError as exc:
        raise DashboardError("project path is outside the configured catalog root") from exc
    return _inside_allowed_root(_project_root() / relative, require_directory=True)


def _runtime_project_path(catalog_path):
    # New entries are stored using container-side paths, so they can be used
    # directly even when the catalog was created by the dashboard.
    raw_catalog_path = _path(catalog_path)
    resolved_catalog_path = raw_catalog_path.resolve(strict=False)
    for root in _allowed_project_roots():
        try:
            resolved_catalog_path.relative_to(root)
        except ValueError:
            continue
        return _inside_allowed_root(raw_catalog_path)
    catalog_root = _catalog_root()
    try:
        relative = resolved_catalog_path.relative_to(catalog_root)
    except ValueError as exc:
        raise DashboardError("project is outside the configured catalog root") from exc
    return _inside_allowed_root(_project_root() / relative)


def _guard_project_path(project):
    project_path = _runtime_project_path(_path(project.get("path", ".")))
    if not project_path.is_dir():
        raise DashboardError("project directory is unavailable")
    return _inside_allowed_root(project_path, require_directory=True)


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


def _key_metadata(example_path, env_path, backup_exists):
    """Return key names and presence booleans without retaining env values."""
    expected = _env_keys(example_path)
    configured = set(_env_keys(env_path))
    return [{"name": key, "configured": key in configured, "backup": bool(backup_exists)}
            for key in expected]


def _summary(project):
    slug = _slug(project.get("slug", project.get("name")))
    display_path = _path(project.get("path", "."))
    try:
        project_path = _runtime_project_path(display_path)
    except DashboardError:
        project_path = display_path
    env_file = project.get("envFile", ".env")
    env_example = project.get("envExample", ".env.example")
    env_path = _relative_file(project_path, env_file, ".env")
    example_path = _relative_file(project_path, env_example, ".env.example")
    backup_name = project.get("backupFile", "backups/" + slug + ".env.age")
    backup_path = _relative_file(project_path, backup_name, "backups/" + slug + ".env.age")
    required = _env_keys(example_path)
    backup_exists = backup_path.is_file()
    return {"slug": slug, "name": project.get("name", slug),
            "gitUrl": project.get("gitUrl"), "path": str(display_path),
            "envFile": env_file, "envExample": env_example,
            "requiredKeys": required,
            "environmentCount": project.get("environmentCount", len(required)),
            "backupFile": str(backup_path), "backupExists": backup_exists,
            "keyMetadata": _key_metadata(example_path, env_path, backup_exists),
            "lastBackup": project.get("lastBackup"), "status": project.get("status", "registered"),
            "pinned": bool(project.get("pinned", False)),
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


def _repo_url(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise DashboardError("Git URL is required")
    if value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password:
            raise DashboardError("Git URL cannot contain credentials")
        return value
    if value.startswith("git@") and ":" in value:
        return value
    raise DashboardError("Git URL must be an http(s) or SSH Git URL")


def _safe_env_filename(value):
    filename = value if value is not None else ".env"
    if not isinstance(filename, str) or not filename or "\x00" in filename:
        raise DashboardError("environment filename is invalid")
    candidate = Path(filename)
    if candidate.is_absolute() or any(part in ("", ".", "..") for part in candidate.parts):
        raise DashboardError("environment filename must stay inside the project")
    return filename


def _new_slug(path, projects):
    base = re.sub(r"[^a-z0-9._-]+", "-", path.name.lower()).strip("-._") or "project"
    base = base[:63]
    used = {item.get("slug") for item in projects if isinstance(item, dict)}
    slug = base
    index = 2
    while slug in used:
        suffix = "-" + str(index)
        slug = base[: 63 - len(suffix)] + suffix
        index += 1
    return _slug(slug)


def _detected_environment_files(project_path):
    """Detect environment filenames from directory metadata, never values."""
    try:
        names = sorted(
            item.name for item in project_path.iterdir()
            if item.is_file() and not item.is_symlink() and item.name.startswith(".env")
        )
    except OSError:
        names = []
    env_file = ".env" if ".env" in names else next(
        (name for name in names if name != ".env.example"), ".env"
    )
    env_example = ".env.example" if ".env.example" in names else ".env.example"
    return env_file, env_example


def _detected_git_url(project_path):
    """Read a safe origin URL from local Git metadata, if one exists."""
    git_config = project_path / ".git" / "config"
    if not git_config.is_file() or git_config.is_symlink():
        return None
    try:
        text = git_config.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    match = re.search(r"^\s*url\s*=\s*(\S+)\s*$", text, re.MULTILINE)
    if not match:
        return None
    candidate = match.group(1)
    try:
        return _repo_url(candidate)
    except DashboardError:
        return None


def register_existing_project(payload):
    """Register a mounted folder using metadata only; do not upload its files."""
    if not isinstance(payload, dict):
        raise DashboardError("register request must be an object")
    requested_path = payload.get("path")
    if not isinstance(requested_path, str) or not requested_path:
        raise DashboardError("local path is required")
    target = _path(requested_path)
    if not target.is_absolute():
        raise DashboardError("local path must be absolute")
    try:
        runtime_target = _inside_allowed_root(target, require_directory=True)
    except DashboardError:
        # Native Finder helper sends the host path; browser requests normally
        # send the already-mounted container path. Both remain root-guarded.
        runtime_target = _host_path_to_runtime(target)
    if runtime_target == runtime_target.parent:
        raise DashboardError("the mounted root itself cannot be registered")
    env_file, env_example = _detected_environment_files(runtime_target)
    supplied_env_file = payload.get("envFile")
    supplied_env_example = payload.get("envExample")
    if supplied_env_file:
        env_file = _safe_env_filename(supplied_env_file)
    if supplied_env_example:
        env_example = _safe_env_filename(supplied_env_example)
    display_name = payload.get("name") or runtime_target.name
    if not isinstance(display_name, str) or not display_name.strip() or len(display_name.strip()) > 120:
        raise DashboardError("project name is invalid")
    repo = payload.get("gitUrl") or _detected_git_url(runtime_target)
    if repo:
        repo = _repo_url(repo)
    catalog = _read_catalog(CATALOG if CATALOG.exists() else None)
    resolved_target = runtime_target.resolve()
    for existing in catalog["projects"]:
        try:
            if _runtime_project_path(existing.get("path", ".")).resolve() == resolved_target:
                raise DashboardError("this folder is already registered")
        except (AttributeError, DashboardError):
            if isinstance(existing, dict) and existing.get("path") == str(runtime_target):
                raise DashboardError("this folder is already registered")
    slug = _new_slug(runtime_target, catalog["projects"])
    project = {
        "slug": slug,
        "name": display_name.strip(),
        "gitUrl": repo,
        "path": str(runtime_target),
        "envFile": env_file,
        "envExample": env_example,
        "environmentCount": 0,
        "lastBackup": None,
        "status": "registered",
        "pinned": False,
    }
    catalog["projects"] = [*catalog["projects"], project]
    try:
        _write_catalog(catalog)
    except (OSError, TypeError, ValueError) as exc:
        raise DashboardError("project metadata could not be saved") from exc
    return {"message": "Folder registered; only metadata was inspected.", "project": _summary(project)}


def initialize_project(payload):
    """Clone a repository into an explicit root, then register metadata."""
    if not isinstance(payload, dict):
        raise DashboardError("initialize request must be an object")
    repo = _repo_url(payload.get("gitUrl"))
    display_name = payload.get("name") or ""
    if not isinstance(display_name, str) or len(display_name.strip()) > 120:
        raise DashboardError("project name is invalid")
    requested_path = payload.get("path")
    if not isinstance(requested_path, str) or not requested_path:
        raise DashboardError("local path is required")
    target = _path(requested_path)
    runtime_target = _inside_allowed_root(target)
    if not target.is_absolute():
        raise DashboardError("local path must be absolute")
    if target.exists() or runtime_target.exists():
        raise DashboardError("local path already exists")
    parent = target.parent
    _inside_allowed_root(parent, require_directory=True)
    env_file = _safe_env_filename(payload.get("envFile", payload.get("envFilename", ".env")))
    catalog = _read_catalog(CATALOG if CATALOG.exists() else None)
    slug = _new_slug(runtime_target, catalog["projects"])
    try:
        result = subprocess.run(
            ["git", "clone", "--quiet", "--", repo, str(runtime_target)],
            cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        shutil.rmtree(runtime_target, ignore_errors=True)
        raise DashboardError("Git clone did not complete") from exc
    if result.returncode:
        shutil.rmtree(runtime_target, ignore_errors=True)
        raise DashboardError("Git clone failed; no project was registered")
    project = {
        "slug": slug,
        "name": display_name.strip() or runtime_target.name,
        "gitUrl": repo,
        "path": str(runtime_target),
        "envFile": env_file,
        "environmentCount": 0,
        "lastBackup": None,
        "status": "initialized",
        "pinned": False,
    }
    catalog["projects"] = [*catalog["projects"], project]
    try:
        _write_catalog(catalog)
    except (OSError, TypeError, ValueError) as exc:
        raise DashboardError("project cloned but metadata could not be saved") from exc
    return {"message": "Project initialized and registered.", "project": _summary(project)}


def update_pin(slug, pinned):
    catalog_value = _read_catalog(CATALOG)
    project = _project(catalog_value, _slug(slug))
    if not isinstance(pinned, bool):
        raise DashboardError("pinned must be boolean")
    project["pinned"] = pinned
    _write_catalog(catalog_value)
    return {"message": "Project pin updated.", "projects": catalog()["projects"]}


def reorder_projects(slugs):
    if not isinstance(slugs, list) or not all(isinstance(slug, str) for slug in slugs):
        raise DashboardError("order must be a list of project slugs")
    catalog_value = _read_catalog(CATALOG)
    current = [project.get("slug", project.get("name")) for project in catalog_value["projects"]]
    if len(slugs) != len(set(slugs)) or set(slugs) != set(current):
        raise DashboardError("order must contain every registered project once")
    by_slug = {project.get("slug", project.get("name")): project for project in catalog_value["projects"]}
    catalog_value["projects"] = [by_slug[slug] for slug in slugs]
    _write_catalog(catalog_value)
    return {"message": "Project order saved.", "projects": catalog()["projects"]}


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

    def read_json(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise DashboardError("request body is invalid")
        if content_length <= 0 or content_length > 32768:
            raise DashboardError("request body is invalid")
        try:
            value = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DashboardError("request body is invalid") from exc
        return value

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
            elif route == "/api/config":
                roots = _allowed_project_roots()
                host_root = os.environ.get("ENVSHELF_PROJECTS_HOST_PATH", "").strip()
                # Only expose connection state, never host path or environment
                # contents. A relative/default mount is the empty starter
                # directory and is not useful for a user's real projects.
                host_root_configured = bool(host_root and not host_root.startswith("./"))
                self.send_json({
                    "allowedRoots": [str(root) for root in roots],
                    "docker": not _standalone_mode(),
                    "standalone": _standalone_mode(),
                    "hostRootConfigured": host_root_configured,
                    "nativeHelperSupported": not _standalone_mode(),
                })
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
        if route == "/api/projects/init":
            try:
                result = initialize_project(self.read_json())
                self.send_json(result, status=201)
            except DashboardError as exc:
                self.send_json({"error": str(exc)}, status=409)
            return
        if route == "/api/projects/register":
            try:
                result = register_existing_project(self.read_json())
                self.send_json(result, status=201)
            except DashboardError as exc:
                self.send_json({"error": str(exc)}, status=409)
            return
        pin_match = re.fullmatch(r"/api/projects/([a-z0-9][a-z0-9._-]{0,62})/pin", route)
        if pin_match:
            try:
                body = self.read_json()
                result = update_pin(pin_match.group(1), body.get("pinned") if isinstance(body, dict) else None)
                self.send_json(result)
            except DashboardError as exc:
                self.send_json({"error": str(exc)}, status=409)
            return
        if route == "/api/projects/reorder":
            try:
                body = self.read_json()
                result = reorder_projects(body.get("slugs") if isinstance(body, dict) else None)
                self.send_json(result)
            except DashboardError as exc:
                self.send_json({"error": str(exc)}, status=409)
            return
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
