import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import server

class CatalogTests(unittest.TestCase):
    def test_catalog_allowlists_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"catalog.json"
            path.write_text(json.dumps({"projects":[{"name":"demo","token":"never-return","gitUrl":"https://example.test/x"}]}))
            with patch.object(server,"CATALOG",path): value=server.catalog()
        self.assertEqual(value["projects"][0]["name"],"demo")
        self.assertNotIn("token",value["projects"][0])

if __name__=="__main__": unittest.main()

