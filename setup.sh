#!/bin/bash
set -e

echo "========================================="
echo "  Juliusz — Instalacja"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

check() { command -v "$1" >/dev/null 2>&1; }

# 1. Homebrew
if ! check brew; then
    echo -e "${RED}Homebrew nie jest zainstalowany.${NC}"
    echo "Zainstaluj: https://brew.sh"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Homebrew"

# 2. Python 3.11+
if ! check python3; then
    echo -e "${YELLOW}Instaluję Python 3...${NC}"
    brew install python@3.12
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}[OK]${NC} Python $PYTHON_VERSION"

# 3. ffmpeg
if ! check ffmpeg; then
    echo -e "${YELLOW}Instaluję ffmpeg...${NC}"
    brew install ffmpeg
fi
echo -e "${GREEN}[OK]${NC} ffmpeg"

# 4. pango (wymagane przez WeasyPrint do eksportu PDF)
if ! brew list pango &>/dev/null; then
    echo -e "${YELLOW}Instaluję pango (dla eksportu PDF)...${NC}"
    brew install pango
fi
echo -e "${GREEN}[OK]${NC} pango"

# 5. Ollama
if ! check ollama; then
    echo -e "${YELLOW}Instaluję Ollama...${NC}"
    brew install ollama
fi
echo -e "${GREEN}[OK]${NC} Ollama"

# 5. Python venv
echo ""
echo "Tworzę środowisko Python..."
cd "$(dirname "$0")"
python3 -m venv .venv
source .venv/bin/activate

echo "Instaluję zależności Python..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo -e "${GREEN}[OK]${NC} Zależności Python zainstalowane"

# 6. Ollama — start & pull model
echo ""
echo "Uruchamiam Ollama i pobieram model PLLuM-12B..."
echo "(To może potrwać kilka minut przy pierwszym uruchomieniu)"

# Start Ollama in background if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 3
fi

ollama pull PRIHLOP/PLLuM:12b

echo -e "${GREEN}[OK]${NC} Model PLLuM-12B gotowy"

# 7. Summary
echo ""
echo "========================================="
echo -e "${GREEN}  Instalacja zakończona!${NC}"
echo "========================================="
echo ""
echo "Aby uruchomić aplikację:"
echo "  ./run.sh"
echo ""
echo "Lub ręcznie:"
echo "  source .venv/bin/activate"
echo "  ollama serve  (w osobnym terminalu, jeśli nie działa)"
echo "  uvicorn app.main:app --host 127.0.0.1 --port 8000"
echo ""
echo "Aplikacja będzie dostępna pod: http://localhost:8000"
