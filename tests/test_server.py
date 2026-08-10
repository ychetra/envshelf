import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import server

class CatalogTests(unittest.TestCase):
    def test_standalone_starts_with_empty_local_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Path(folder) / "catalog.json"
            projects = Path(folder) / "projects"
            projects.mkdir()
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ,
                {
                    "ENVSHELF_MODE": "standalone",
                    "ENVSHELF_ALLOWED_PROJECT_ROOTS": str(projects),
                },
                clear=False,
            ):
                self.assertEqual(server.catalog(), {"projects": []})

    def test_docker_catalog_paths_are_mapped_from_host_root(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host_root = root / "host-projects"
            container_root = root / "container-projects"
            (host_root / "demo").mkdir(parents=True)
            (container_root / "demo").mkdir(parents=True)
            project = {"slug": "demo", "path": str(host_root / "demo")}
            with patch.dict(os.environ, {
                "ENVSHELF_CATALOG_ROOT": str(host_root),
                "ENVSHELF_PROJECT_ROOT": str(container_root),
            }, clear=False):
                self.assertEqual(server._guard_project_path(project), (container_root / "demo").resolve())

    def test_docker_catalog_path_outside_host_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host_root = root / "host-projects"
            outside = root / "outside"
            host_root.mkdir()
            outside.mkdir()
            project = {"slug": "demo", "path": str(outside)}
            with patch.dict(os.environ, {
                "ENVSHELF_CATALOG_ROOT": str(host_root),
                "ENVSHELF_PROJECT_ROOT": str(root / "container-projects"),
            }, clear=False):
                with self.assertRaises(server.DashboardError):
                    server._guard_project_path(project)

    def test_catalog_allowlists_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"catalog.json"
            path.write_text(json.dumps({"projects":[{"name":"demo","token":"never-return","gitUrl":"https://example.test/x"}]}))
            with patch.object(server,"CATALOG",path): value=server.catalog()
        self.assertEqual(value["projects"][0]["name"],"demo")
        self.assertNotIn("token",value["projects"][0])

    def test_catalog_exposes_key_names_but_never_example_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "demo"
            project.mkdir()
            (project / ".env.example").write_text(
                "PUBLIC_NAME=not-a-secret-value\n# ignored\nexport PORT=8080\n", encoding="utf-8"
            )
            path = root / "catalog.json"
            path.write_text(json.dumps({"projects": [{
                "slug": "demo", "name": "Demo", "path": str(project),
                "gitUrl": "https://example.test/demo"
            }]}), encoding="utf-8")
            with patch.object(server, "CATALOG", path):
                value = server.catalog()
            serialized = json.dumps(value)
        self.assertEqual(value["projects"][0]["requiredKeys"], ["PUBLIC_NAME", "PORT"])
        self.assertNotIn("not-a-secret-value", serialized)
        self.assertNotIn("8080", serialized)

    def test_key_metadata_has_statuses_without_secret_values(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "demo"
            project.mkdir()
            (project / ".env.example").write_text("APP_URL=example\nDATABASE_URL=example\n", encoding="utf-8")
            (project / ".env").write_text("APP_URL=https://private.example\n", encoding="utf-8")
            path = root / "catalog.json"
            path.write_text(json.dumps({"projects": [{
                "slug": "demo", "name": "Demo", "path": str(project),
                "gitUrl": "https://example.test/demo"
            }]}), encoding="utf-8")
            with patch.object(server, "CATALOG", path), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(root)}, clear=False
            ):
                value = server.catalog()
            serialized = json.dumps(value)
        self.assertEqual(value["projects"][0]["keyMetadata"], [
            {"name": "APP_URL", "configured": True, "backup": False},
            {"name": "DATABASE_URL", "configured": False, "backup": False},
        ])
        self.assertNotIn("private.example", serialized)
        self.assertNotIn("private.example", serialized)

    def test_pin_and_reorder_persist_in_local_catalog(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("one", "two"):
                (root / name).mkdir()
            path = root / "catalog.json"
            path.write_text(json.dumps({"projects": [
                {"slug": "one", "name": "One", "path": str(root / "one")},
                {"slug": "two", "name": "Two", "path": str(root / "two")},
            ]}), encoding="utf-8")
            with patch.object(server, "CATALOG", path), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(root)}, clear=False
            ):
                server.update_pin("two", True)
                server.reorder_projects(["two", "one"])
            saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual([project["slug"] for project in saved["projects"]], ["two", "one"])
        self.assertTrue(saved["projects"][0]["pinned"])

    def test_initialize_rejects_outside_and_symlink_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            allowed = root / "allowed"
            outside = root / "outside"
            allowed.mkdir()
            outside.mkdir()
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            payload = {"gitUrl": "https://example.test/repo", "path": str(outside / "repo")}
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(allowed)}, clear=False
            ), patch.object(server.subprocess, "run") as run:
                with self.assertRaises(server.DashboardError):
                    server.initialize_project(payload)
                run.assert_not_called()
            (allowed / "link").symlink_to(outside, target_is_directory=True)
            payload["path"] = str(allowed / "link" / "repo")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(allowed)}, clear=False
            ), patch.object(server.subprocess, "run") as run:
                with self.assertRaises(server.DashboardError):
                    server.initialize_project(payload)
                run.assert_not_called()

    def test_register_existing_folder_detects_names_only_and_remote(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "existing-app"
            (project / ".git").mkdir(parents=True)
            (project / ".git" / "config").write_text(
                "[remote \"origin\"]\n\turl = https://github.com/example/existing-app.git\n",
                encoding="utf-8",
            )
            (project / ".env").write_text("APP_URL=https://secret.invalid\n", encoding="utf-8")
            (project / ".env.example").write_text("APP_URL=https://example.invalid\nDB_URL=postgres\n", encoding="utf-8")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(root)}, clear=False
            ):
                result = server.register_existing_project({"path": str(project.resolve())})
                serialized = json.dumps(result)
            self.assertEqual(result["project"]["gitUrl"], "https://github.com/example/existing-app.git")
            self.assertEqual(result["project"]["envFile"], ".env")
            self.assertEqual(result["project"]["envExample"], ".env.example")
            self.assertIn("APP_URL", serialized)
            self.assertNotIn("secret.invalid", serialized)

    def test_register_existing_folder_rejects_unmounted_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            allowed = root / "allowed"
            outside = root / "outside"
            allowed.mkdir()
            outside.mkdir()
            (outside / "app").mkdir()
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {"ENVSHELF_ALLOWED_PROJECT_ROOTS": str(allowed)}, clear=False
            ):
                with self.assertRaises(server.DashboardError):
                    server.register_existing_project({"path": str(outside / "app")})

    def test_register_existing_folder_maps_native_helper_host_path(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host_root = root / "host-projects"
            container_root = root / "container-projects"
            host_project = host_root / "drop-app"
            container_project = container_root / "drop-app"
            host_project.mkdir(parents=True)
            container_project.mkdir(parents=True)
            (container_project / ".env.example").write_text("APP_URL=example\n", encoding="utf-8")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {
                    "ENVSHELF_CATALOG_ROOT": str(host_root),
                    "ENVSHELF_PROJECT_ROOT": str(container_root),
                    "ENVSHELF_ALLOWED_PROJECT_ROOTS": str(container_root),
                }, clear=False
            ):
                result = server.register_existing_project({"path": str(host_project)})
            saved = json.loads(catalog.read_text(encoding="utf-8"))
        self.assertEqual(result["project"]["path"], str(container_project.resolve()))
        self.assertEqual(saved["projects"][0]["path"], str(container_project.resolve()))
        self.assertEqual(result["project"]["requiredKeys"], ["APP_URL"])

    def test_native_helper_host_path_outside_catalog_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host_root = root / "host-projects"
            container_root = root / "container-projects"
            outside = root / "outside"
            host_root.mkdir()
            container_root.mkdir()
            outside.mkdir()
            (outside / "drop-app").mkdir()
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {
                    "ENVSHELF_CATALOG_ROOT": str(host_root),
                    "ENVSHELF_PROJECT_ROOT": str(container_root),
                    "ENVSHELF_ALLOWED_PROJECT_ROOTS": str(container_root),
                }, clear=False
            ):
                with self.assertRaises(server.DashboardError):
                    server.register_existing_project({"path": str(outside / "drop-app")})

    def test_native_helper_host_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            host_root = root / "host-projects"
            container_root = root / "container-projects"
            outside = root / "outside"
            host_root.mkdir()
            container_root.mkdir()
            outside.mkdir()
            (outside / "real-app").mkdir()
            (host_root / "linked-app").symlink_to(outside / "real-app", target_is_directory=True)
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": []}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {
                    "ENVSHELF_CATALOG_ROOT": str(host_root),
                    "ENVSHELF_PROJECT_ROOT": str(container_root),
                    "ENVSHELF_ALLOWED_PROJECT_ROOTS": str(container_root),
                }, clear=False
            ):
                with self.assertRaises(server.DashboardError):
                    server.register_existing_project({"path": str(host_root / "linked-app")})
    def test_action_rejects_project_outside_configured_root_before_age(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root / "outside"
            outside.mkdir()
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"projects": [{
                "slug": "demo", "name": "Demo", "path": str(outside),
                "gitUrl": "https://example.test/demo"
            }]}), encoding="utf-8")
            with patch.object(server, "CATALOG", catalog), patch.dict(
                os.environ, {"ENVSHELF_PROJECT_ROOT": str(root / "allowed")}, clear=False
            ), patch.object(server, "_run_cli") as run_cli:
                with self.assertRaises(server.DashboardError):
                    server.perform_action("demo", "backup")
                run_cli.assert_not_called()

    def test_asset_resolution_supports_built_tree_and_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as folder:
            dist = Path(folder) / "dist"
            (dist / "assets").mkdir(parents=True)
            (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
            with patch.object(server, "WEB_ROOT", dist):
                self.assertEqual(server.Handler._asset("/assets/app.js"), (dist / "assets" / "app.js").resolve())
                with self.assertRaises(server.DashboardError):
                    server.Handler._asset("/assets/%2e%2e/%2e%2e/secret")

if __name__=="__main__": unittest.main()
