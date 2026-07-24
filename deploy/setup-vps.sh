#!/usr/bin/env bash
# One-shot bootstrap for SaveVid AI on a fresh Ubuntu 24.04 VPS.
# Run as root (or with sudo) on the box:
#
#   curl -fsSL https://raw.githubusercontent.com/OxIsrafil/savevidai/main/deploy/setup-vps.sh | bash
#
# or clone the repo and run it directly. Idempotent: safe to re-run to update.
set -euo pipefail

REPO="https://github.com/OxIsrafil/savevidai.git"
DIR="/opt/savevidai"

echo "==> Installing prerequisites (git, curl)"
apt-get update -y
apt-get install -y git curl

echo "==> Installing Docker (skips if already present)"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

echo "==> Fetching the repo into $DIR"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch --depth 1 origin main
  git -C "$DIR" reset --hard origin/main
else
  git clone --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

if [ ! -f deploy/app.env ]; then
  cp deploy/app.env.example deploy/app.env
  echo ""
  echo "==> Created deploy/app.env from the template."
  echo "    Fill in the 4 analytics vars (same values as Render), then re-run:"
  echo "      nano $DIR/deploy/app.env"
  echo "      bash $DIR/deploy/setup-vps.sh"
  exit 1
fi

echo "==> Building and starting (first build takes a few minutes)"
docker compose -f compose.prod.yaml up -d --build

echo ""
echo "==> Running. Status:"
docker compose -f compose.prod.yaml ps
echo ""
echo "Once DNS for savevidai.israfill.dev points at this box, Caddy will fetch"
echo "a Let's Encrypt cert automatically (ports 80 and 443 must be open)."
echo "Verify locally:  curl -sic http://localhost:80/api/health  (via Caddy once DNS is live)"
echo "App logs:        docker compose -f compose.prod.yaml logs -f app"
