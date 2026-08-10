"""Local-first project registry and age-backed environment backup CLI.

The CLI accepts paths and metadata only. It never accepts an environment value
as an argument and never prints command output from age, because tools should
not accidentally turn a secret into a log line.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit


class EnvShelfError(Exception):
    """An expected, user-facing failure that contains no secret material."""


def _slug(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,62}", value):
        raise EnvShelfError("slug must use lowercase letters, numbers, dots, hyphens, or underscores")
    return value


def _repo(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise EnvShelfError("repo must be a Git URL")
    if value.startswith(("https://", "http://")):
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password:
            raise EnvShelfError("repo URL cannot contain credentials")
    elif not value.startswith("git@"):
        raise EnvShelfError("repo must be an http(s) URL or an SSH Git URL")
    return value


def _path(value):
    return Path(value).expanduser()


def _catalog_path(value=None):
    if value:
        return _path(value)
    data_dir = os.environ.get("ENVSHELF_DATA_DIR")
    return _path(data_dir) / "catalog.json" if data_dir else Path("data/catalog.json")


def _read_catalog(path):
    if not path.exists():
        return {"projects": []}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EnvShelfError("Could not read the metadata catalog") from exc
    if not isinstance(value, dict) or not isinstance(value.get("projects", []), list):
        raise EnvShelfError("The metadata catalog has an invalid shape")
    return value


def _write_catalog(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".catalog.", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _project(catalog, slug):
    for project in catalog["projects"]:
        if project.get("slug", project.get("name")) == slug:
            return project
    raise EnvShelfError("Project is not registered")


def _age_binary():
    return os.environ.get("ENVSHELF_AGE_BIN", "age")


def _age_keygen_binary():
    return os.environ.get("ENVSHELF_AGE_KEYGEN_BIN", "age-keygen")


def _run(command):
    """Run age without forwarding stdout/stderr, which may contain sensitive data."""
    try:
        result = subprocess.run(command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise EnvShelfError("The age command is not available") from exc
    if result.returncode:
        raise EnvShelfError("The age operation failed; no output was written")
    return result


def _recipient(path):
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
    except (OSError, UnicodeDecodeError) as exc:
        raise EnvShelfError("Could not read the recipient file") from exc
    values = [line for line in lines if line and not line.startswith("#")]
    if len(values) != 1 or not values[0].startswith("age1"):
        raise EnvShelfError("Recipient file must contain one age recipient")
    return values[0]


def _new_output(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".envshelf.", dir=str(path.parent))
    os.close(fd)
    os.unlink(temporary)
    return Path(temporary)


def _selected_env(project):
    project_path = _path(project.get("path", "."))
    env_file = project.get("envFile", ".env")
    if not isinstance(env_file, str) or not env_file or Path(env_file).is_absolute():
        raise EnvShelfError("Registered envFile must be a relative filename")
    selected = project_path / env_file
    try:
        selected.resolve().relative_to(project_path.resolve())
    except ValueError as exc:
        raise EnvShelfError("Registered envFile must stay inside the project") from exc
    if selected.is_symlink():
        raise EnvShelfError("Refusing to read an env symlink")
    if not selected.is_file():
        raise EnvShelfError("Registered environment file was not found")
    return selected


def command_init(args):
    identity = _path(args.identity_file)
    recipient = _path(args.recipient_file or str(identity) + ".recipient")
    if identity.exists() or recipient.exists():
        raise EnvShelfError("Identity or recipient already exists; choose new paths")
    identity.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = _run([_age_keygen_binary(), "-o", str(identity)])
    except EnvShelfError:
        identity.unlink(missing_ok=True)
        raise
    text = (result.stdout + result.stderr).decode("utf-8", "replace")
    public_keys = [word for word in text.split() if word.startswith("age1")]
    if len(public_keys) != 1:
        identity.unlink(missing_ok=True)
        raise EnvShelfError("age-keygen did not return one recipient")
    try:
        recipient.write_text(public_keys[0] + "\n", encoding="utf-8")
        os.chmod(identity, 0o600)
        os.chmod(recipient, 0o600)
    except OSError as exc:
        identity.unlink(missing_ok=True)
        recipient.unlink(missing_ok=True)
        raise EnvShelfError("Could not save the age files") from exc
    print("Created age identity and recipient files.")


def command_register(args):
    _slug(args.slug)
    _repo(args.repo)
    if Path(args.env_file).is_absolute() or not args.env_file or "\x00" in args.env_file:
        raise EnvShelfError("envFile must be a relative filename")
    path = _catalog_path(args.catalog)
    catalog = _read_catalog(path)
    project = {
        "slug": args.slug,
        "name": args.name or args.slug,
        "gitUrl": args.repo,
        "path": str(_path(args.path)),
        "envFile": args.env_file,
        "environmentCount": 1,
        "lastBackup": None,
        "status": "registered",
    }
    existing = [p for p in catalog["projects"] if p.get("slug", p.get("name")) != args.slug]
    catalog["projects"] = existing + [project]
    _write_catalog(path, catalog)
    print("Registered project metadata.")


def command_encrypt(args):
    _slug(args.slug)
    catalog = _read_catalog(_catalog_path(args.catalog))
    project = _project(catalog, args.slug)
    env_path = _selected_env(project)
    recipient_path = _path(args.recipient_file)
    recipient = _recipient(recipient_path)
    output = _path(args.output or str(Path("backups") / (args.slug + ".env.age")))
    if output.resolve() == env_path.resolve():
        raise EnvShelfError("Encrypted output must differ from the environment file")
    temporary = _new_output(output)
    try:
        _run([_age_binary(), "-r", recipient, "-o", str(temporary), str(env_path)])
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    project["lastBackup"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    project["status"] = "encrypted backup ready"
    _write_catalog(_catalog_path(args.catalog), catalog)
    print("Encrypted backup created.")


def _preserve_existing(target):
    if not target.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = target.with_name(target.name + ".before-restore." + stamp)
    counter = 1
    while backup.exists():
        backup = target.with_name(target.name + ".before-restore." + stamp + "." + str(counter))
        counter += 1
    shutil.copy2(target, backup)
    os.chmod(backup, 0o600)
    return backup


def command_restore(args):
    _slug(args.slug)
    catalog = _read_catalog(_catalog_path(args.catalog))
    project = _project(catalog, args.slug)
    target = _path(args.output) if args.output else _selected_env(project)
    if target.is_symlink():
        raise EnvShelfError("Refusing to overwrite an env symlink")
    input_path = _path(args.input or str(Path("backups") / (args.slug + ".env.age")))
    if not input_path.is_file():
        raise EnvShelfError("Encrypted backup was not found")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = _new_output(target)
    try:
        _run([_age_binary(), "-d", "-i", str(_path(args.identity_file)), "-o", str(temporary), str(input_path)])
        os.chmod(temporary, 0o600)
        preserved = _preserve_existing(target)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    project["status"] = "restored"
    _write_catalog(_catalog_path(args.catalog), catalog)
    if preserved:
        print("Restored environment; previous file was preserved beside it.")
    else:
        print("Restored environment.")


def command_list(args):
    catalog = _read_catalog(_catalog_path(args.catalog))
    for project in catalog["projects"]:
        print("{}  {}".format(project.get("name", "unnamed"), project.get("gitUrl", "")))


def command_doctor(_args):
    print("Metadata and age backup workflows are ready; secret values are never displayed.")


def build_parser():
    parser = argparse.ArgumentParser(prog="envshelf")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create an age identity and recipient file")
    init.add_argument("--identity-file", required=True, help="path for the private age identity")
    init.add_argument("--recipient-file", help="path for the public recipient")
    init.set_defaults(function=command_init)

    register = commands.add_parser("register", help="save project metadata")
    register.add_argument("--slug", required=True)
    register.add_argument("--repo", required=True, help="Git URL")
    register.add_argument("--path", required=True, help="local project directory")
    register.add_argument("--env-file", default=".env", help="relative env filename")
    register.add_argument("--name")
    register.add_argument("--catalog")
    register.set_defaults(function=command_register)

    encrypt = commands.add_parser("encrypt", help="encrypt a registered env file")
    encrypt.add_argument("--slug", required=True)
    encrypt.add_argument("--recipient-file", required=True)
    encrypt.add_argument("--output")
    encrypt.add_argument("--catalog")
    encrypt.set_defaults(function=command_encrypt)

    restore = commands.add_parser("restore", help="restore an encrypted env file safely")
    restore.add_argument("--slug", required=True)
    restore.add_argument("--identity-file", required=True)
    restore.add_argument("--input")
    restore.add_argument("--output")
    restore.add_argument("--catalog")
    restore.set_defaults(function=command_restore)

    for name, function in (("list", command_list), ("doctor", command_doctor)):
        command = commands.add_parser(name)
        command.add_argument("--catalog")
        command.set_defaults(function=function)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.function(args)
    except EnvShelfError as exc:
        parser.exit(2, "envshelf: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
