#!/bin/sh
set -eu

demo_root=$(mktemp -d "${TMPDIR:-/tmp}/envshelf-demo.XXXXXX")
cleanup() {
  rm -rf "$demo_root"
}
trap cleanup EXIT INT TERM

mkdir -p "$demo_root/projects/starlight-api" "$demo_root/keys" "$demo_root/data"
cat > "$demo_root/projects/starlight-api/.env.example" <<'EOF'
APP_PORT=
DATABASE_URL=
SESSION_SECRET=
EOF
cat > "$demo_root/data/catalog.json" <<'EOF'
{"projects":[{"slug":"starlight-api","name":"Starlight API","gitUrl":"https://github.com/demo/starlight-api","path":"/workspace/starlight-api","envFile":".env","envExample":".env.example","backupFile":"backups/starlight-api.env.age","environmentCount":3,"status":"demo"}]}
EOF

docker build -t envshelf:demo .
export ENVSHELF_PROJECT_ROOT=/workspace
export ENVSHELF_CATALOG_ROOT=/workspace
export ENVSHELF_PORT="${ENVSHELF_PORT:-8787}"

echo "Synthetic demo fixture: $demo_root"
echo "Open http://localhost:8787"
echo "Press Ctrl-C to stop and remove the fixture."
docker run --rm --name envshelf-demo \
  -p "127.0.0.1:${ENVSHELF_PORT}:8787" \
  -e ENVSHELF_BIND=0.0.0.0 \
  -e ENVSHELF_PORT=8787 \
  -e ENVSHELF_DATA_DIR=/var/lib/envshelf \
  -e ENVSHELF_PROJECT_ROOT="$ENVSHELF_PROJECT_ROOT" \
  -e ENVSHELF_CATALOG_ROOT="$ENVSHELF_CATALOG_ROOT" \
  -v "$demo_root/data:/var/lib/envshelf" \
  -v "$demo_root/projects:/workspace:rw" \
  -v "$demo_root/keys:/keys:ro" \
  envshelf:demo
