import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import server

class CatalogTests(unittest.TestCase):
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
