#!/bin/bash
set -e

echo "========================================="
echo "  Stefka — Instalacja"
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

# 6. llama.cpp (for GGUF conversion)
if ! brew list llama.cpp &>/dev/null; then
    echo -e "${YELLOW}Instaluję llama.cpp (konwersja modelu)...${NC}"
    brew install llama.cpp
fi
echo -e "${GREEN}[OK]${NC} llama.cpp"

# 7. Install conversion dependencies
pip install transformers sentencepiece gguf -q
echo -e "${GREEN}[OK]${NC} Zależności konwersji modelu"

# 8. Ollama — start & download + convert official PLLuM model
echo ""
echo "Uruchamiam Ollama i przygotowuję model PLLuM-12B..."
echo "(Pierwsze uruchomienie: pobranie ~24GB + konwersja — może potrwać kilkanaście minut)"

# Start Ollama in background if not running
if ! pgrep -x "ollama" > /dev/null; then
    ollama serve &
    sleep 3
fi

GGUF_PATH="$(dirname "$0")/models/pllum-12b-nc-instruct-q8_0.gguf"
MODELFILE="$(dirname "$0")/Modelfile.pllum"

if ! ollama list | grep -q "pllum-12b-instruct"; then
    echo "Pobieram oficjalny model CYFRAGOVPL/PLLuM-12B-nc-instruct..."
    mkdir -p "$(dirname "$0")/models"
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('CYFRAGOVPL/PLLuM-12B-nc-instruct', local_dir='$(dirname "$0")/models/PLLuM-12B-nc-instruct')
"
    echo "Konwertuję model do GGUF Q8_0..."
    CONVERT_SCRIPT="$(find /opt/homebrew/Cellar/llama.cpp -name 'convert_hf_to_gguf.py' | head -1)"
    python3 "$CONVERT_SCRIPT" "$(dirname "$0")/models/PLLuM-12B-nc-instruct" \
        --outtype q8_0 --outfile "$GGUF_PATH"

    echo "Importuję model do Ollama..."
    ollama create pllum-12b-instruct -f "$MODELFILE"

    # Clean up safetensors (keep only GGUF)
    rm -rf "$(dirname "$0")/models/PLLuM-12B-nc-instruct"
fi

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
