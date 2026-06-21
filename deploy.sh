#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
err()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

cd "$(dirname "$0")"
PROJECT_DIR="$(pwd)"

log "Updating system packages..."
sudo apt update && sudo apt upgrade -y

log "Installing Docker & Docker Compose..."
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

log "Installing Node.js & npm (for Hardhat)..."
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

log "Installing Python 3 + pip + venv..."
sudo apt install -y python3 python3-pip python3-venv

log "Setting up project..."
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

log "Creating .env from template..."
if [ ! -f .env ]; then
    cp .env.example .env
    log "Please edit .env with your config (Pinata API key, RPC URL, etc.)"
fi

log "DONE!"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Deploy contract: cd contracts && npm install && npx hardhat run scripts/deploy.js --network polygon_mumbai"
echo "  3. Start app: source venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000"
echo ""
echo "Or use Docker:"
echo "  docker-compose up -d"