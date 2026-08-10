#!/usr/bin/env python3
"""Launch the EnvShelf dashboard without Docker.

This is intentionally a small process launcher.  The dashboard and CLI keep
using the official ``age`` executable for cryptography; this file only sets a
native, allowlisted project root and a per-user app-data directory before
starting the loopback server.
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import webbrowser
from pathlib import Path


def default_data_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "EnvShelf"
    if system == "Windows":
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "EnvShelf"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "envshelf"


def absolute_directory(value: str, label: str, *, create: bool = False) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise SystemExit(f"envshelf: {label} must be an absolute path")
    if create:
        path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise SystemExit(f"envshelf: {label} is not a directory")
    return path.resolve()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run EnvShelf in native mode")
    result.add_argument("--projects-root", required=True, help="folder containing your projects")
    result.add_argument("--data-dir", help="local catalog directory (defaults to the OS app-data folder)")
    result.add_argument("--identity-file", help="optional age identity file for restore")
    result.add_argument("--recipient-file", help="optional age recipient file for backup")
    result.add_argument("--app-root", help="EnvShelf source/resource directory (defaults to this checkout)")
    result.add_argument("--port", type=int, default=8787)
    result.add_argument("--no-browser", action="store_true", help="do not open the local dashboard")
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    project_root = absolute_directory(args.projects_root, "projects root")
    data_dir = Path(args.data_dir).expanduser().resolve() if args.data_dir else default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    app_root = Path(args.app_root).expanduser().resolve() if args.app_root else Path(__file__).resolve().parents[1]
    if not (app_root / "app" / "server.py").is_file():
        raise SystemExit("envshelf: app root must contain app/server.py")

    environment = os.environ.copy()
    environment.update({
        "ENVSHELF_MODE": "standalone",
        "ENVSHELF_DATA_DIR": str(data_dir),
        "ENVSHELF_PROJECT_ROOT": str(project_root),
        "ENVSHELF_ALLOWED_PROJECT_ROOTS": str(project_root),
        "ENVSHELF_CATALOG_ROOT": str(project_root),
        "ENVSHELF_BIND": "127.0.0.1",
        "ENVSHELF_PORT": str(args.port),
        "PYTHONPATH": str(app_root) + os.pathsep + environment.get("PYTHONPATH", ""),
    })
    if args.identity_file:
        environment["ENVSHELF_IDENTITY_FILE"] = str(Path(args.identity_file).expanduser().resolve())
    if args.recipient_file:
        environment["ENVSHELF_RECIPIENT_FILE"] = str(Path(args.recipient_file).expanduser().resolve())

    # The server logs only request metadata. Keep the launcher quiet and do
    # not inherit a terminal that might be used to paste secret values.
    kwargs: dict[str, object] = {"cwd": str(app_root), "env": environment,
                                 "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                                 "stderr": subprocess.DEVNULL}
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen([sys.executable, "-m", "app.server"], **kwargs)
    url = f"http://127.0.0.1:{args.port}"
    if not args.no_browser:
        webbrowser.open(url)
    print(f"EnvShelf standalone dashboard: {url}")
    print(f"Native project root: {project_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
