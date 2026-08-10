import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from app import cli


FAKE_AGE = r'''#!/usr/bin/env python3
import pathlib
import sys

args = sys.argv[1:]
if args and args[0] == "-o" and "-r" not in args and "-d" not in args:
    pathlib.Path(args[args.index("-o") + 1]).write_text("# fake identity\n", encoding="utf-8")
    print("Public key: age1fakepublicrecipient")
    raise SystemExit(0)
output = pathlib.Path(args[args.index("-o") + 1])
source = pathlib.Path(args[-1])
payload = source.read_bytes()
output.write_bytes(payload[4:] if "-d" in args else b"AGE:" + payload)
'''


class CliWorkflowTests(unittest.TestCase):
    def test_encrypt_restore_preserves_previous_env_and_registry_has_metadata_only(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "project"
            project.mkdir()
            env_file = project / ".env"
            env_file.write_text("TEST_FIXTURE_VALUE=fixture-only\n", encoding="utf-8")
            fake_age = root / "fake-age"
            fake_age.write_text(FAKE_AGE, encoding="utf-8")
            fake_age.chmod(fake_age.stat().st_mode | stat.S_IXUSR)
            catalog = root / "catalog.json"
            identity = root / "identity.txt"
            recipient = root / "recipient.txt"
            backup = root / "backup.age"
            environment = {
                "ENVSHELF_AGE_BIN": str(fake_age),
                "ENVSHELF_AGE_KEYGEN_BIN": str(fake_age),
            }
            with patch.dict(os.environ, environment, clear=False):
                cli.main(["init", "--identity-file", str(identity), "--recipient-file", str(recipient)])
                cli.main(["register", "--slug", "demo", "--repo", "https://example.test/demo", "--path", str(project), "--catalog", str(catalog)])
                cli.main(["encrypt", "--slug", "demo", "--recipient-file", str(recipient), "--output", str(backup), "--catalog", str(catalog)])
                env_file.write_text("TEST_FIXTURE_VALUE=old-only\n", encoding="utf-8")
                cli.main(["restore", "--slug", "demo", "--identity-file", str(identity), "--input", str(backup), "--catalog", str(catalog)])

            self.assertEqual(env_file.read_text(encoding="utf-8"), "TEST_FIXTURE_VALUE=fixture-only\n")
            preserved = list(project.glob(".env.before-restore.*"))
            self.assertEqual(len(preserved), 1)
            self.assertEqual(preserved[0].read_text(encoding="utf-8"), "TEST_FIXTURE_VALUE=old-only\n")
            metadata = json.loads(catalog.read_text(encoding="utf-8"))
            self.assertNotIn("TEST_FIXTURE_VALUE", catalog.read_text(encoding="utf-8"))
            self.assertEqual(metadata["projects"][0]["slug"], "demo")

    def test_cli_output_does_not_include_age_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            fake_age = root / "fake-age"
            fake_age.write_text(FAKE_AGE, encoding="utf-8")
            fake_age.chmod(fake_age.stat().st_mode | stat.S_IXUSR)
            output = StringIO()
            with patch.dict(os.environ, {"ENVSHELF_AGE_KEYGEN_BIN": str(fake_age)}, clear=False), redirect_stdout(output):
                cli.main(["init", "--identity-file", str(root / "identity")])
            self.assertNotIn("age1fakepublicrecipient", output.getvalue())


if __name__ == "__main__":
    unittest.main()
