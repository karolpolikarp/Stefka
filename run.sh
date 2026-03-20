#!/bin/bash
set -e

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Activate venv
if [ ! -d ".venv" ]; then
    echo "Środowisko Python nie znalezione. Uruchom najpierw: ./setup.sh"
    exit 1
fi
source .venv/bin/activate

# Start Ollama if not running
if ! pgrep -x "ollama" > /dev/null 2>&1; then
    echo -e "${YELLOW}Uruchamiam Ollama...${NC}"
    ollama serve &
    sleep 2
fi

echo -e "${GREEN}Juliusz uruchomiony!${NC}"
echo "Otwórz w przeglądarce: http://localhost:8000"
echo ""

uvicorn app.main:app --host 127.0.0.1 --port 8000
