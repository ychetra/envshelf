"""Dependency-free metadata dashboard; secret values are never read or returned."""
import json, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
DATA=Path(os.environ.get("ENVSHELF_DATA_DIR", str(ROOT/"data")))
CATALOG=DATA/"catalog.json"
WEB=ROOT/"web"/"index.html"
FIELDS=("slug","name","gitUrl","environmentCount","lastBackup","status")

def catalog():
    source=CATALOG if CATALOG.exists() else ROOT/"data"/"catalog.example.json"
    try:
        value=json.loads(source.read_text())
        return {"projects":[{k:p.get(k) for k in FIELDS} for p in value.get("projects",[])]}
    except (OSError,json.JSONDecodeError,AttributeError):
        return {"projects":[]}

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, body, content_type):
        self.send_response(200); self.send_header("Content-Type",content_type); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path=="/api/health": self.send_bytes(b'{"ok":true,"secretValues":"never exposed"}',"application/json")
        elif self.path=="/api/projects": self.send_bytes(json.dumps(catalog()).encode(),"application/json")
        elif self.path in ("/","/index.html"): self.send_bytes(WEB.read_bytes(),"text/html; charset=utf-8")
        else: self.send_error(404)
    def log_message(self, fmt, *args): print("envshelf",self.command,self.path.split("?",1)[0])

if __name__=="__main__": ThreadingHTTPServer(("0.0.0.0",int(os.environ.get("ENVSHELF_PORT","8787"))),Handler).serve_forever()
