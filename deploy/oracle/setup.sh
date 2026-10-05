#!/usr/bin/env bash
# Set up (or update) the backend on an Oracle Cloud Ubuntu VM.
#
#   bash setup.sh https://your-site.vercel.app
#
# The argument is the frontend's origin, allowed to call the API (CORS).
# Re-run it any time to pull the latest code and rebuild.
set -euo pipefail

ORIGINS="${1:-}"
REPO_URL="https://github.com/imsky1812/GeM-Filter-Optimizer.git"
DIR="$HOME/GeM-Filter-Optimizer"

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
fi

# Oracle's Ubuntu images reject inbound traffic other than SSH in iptables,
# even when the cloud firewall (security list) allows it.
for port in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport "$port" -m state --state NEW -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 6 -p tcp --dport "$port" -m state --state NEW -j ACCEPT
  fi
done
sudo netfilter-persistent save 2>/dev/null || true

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only
else
  git clone "$REPO_URL" "$DIR"
fi

# A free hostname that resolves to this VM, so Caddy can get a real HTTPS
# certificate without buying a domain: 1.2.3.4 -> 1-2-3-4.sslip.io
IP="$(curl -fsS https://api.ipify.org)"
DOMAIN="${IP//./-}.sslip.io"

cd "$DIR/deploy/oracle"
printf 'DOMAIN=%s\nALLOWED_ORIGINS=%s\n' "$DOMAIN" "$ORIGINS" > .env
sudo docker compose up -d --build

echo
echo "Backend origin:  https://$DOMAIN"
echo "Health check:    https://$DOMAIN/api/health"
echo "Allowed origins: ${ORIGINS:-<none set>}"
