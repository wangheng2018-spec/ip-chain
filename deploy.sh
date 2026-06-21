#!/bin/bash
set -e
echo "=============================="
echo "  IP-Chain Server Setup"
echo "=============================="

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

echo "[1/5] Installing system packages..."
apt update && apt install -y docker.io docker-compose git curl wget

echo "[2/5] Installing IPFS node..."
if ! command -v ipfs &>/dev/null; then
    wget -q https://dist.ipfs.tech/kubo/v0.27.0/kubo_v0.27.0_linux-amd64.tar.gz
    tar -xzf kubo_v0.27.0_linux-amd64.tar.gz
    cd kubo && bash install.sh
    cd "$PROJECT_DIR"
    rm -rf kubo kubo_v0.27.0_linux-amd64.tar.gz
    ipfs init
    echo "IPFS installed"
fi

echo "[3/5] Configuring environment..."
if [ ! -f .env ]; then
    cp .env.example .env
    JWT_SECRET=$(openssl rand -hex 32)
    sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" .env
fi

echo "[4/5] Starting IPFS daemon..."
nohup ipfs daemon --enable-gateway > /tmp/ipfs.log 2>&1 &
echo "IPFS daemon started (API: 5001, Gateway: 8080)"

echo "[5/5] Starting application..."
docker-compose up -d

echo ""
echo "=============================="
echo "  Setup Complete!"
echo "=============================="
echo ""
echo "  Open in browser: http://$(curl -s ifconfig.me):8000"
echo ""