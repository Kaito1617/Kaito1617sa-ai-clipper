#!/bin/bash
# ============================================================
#  AI Clipper — Script d'installation (Linux / macOS)
# ============================================================

set -e

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================================"
echo -e "   🎬  AI Clipper — Installation"
echo -e "============================================================${NC}"
echo ""

# ── Vérification Python ──────────────────────────────────────
echo -e "${CYAN}[1/5] Vérification Python...${NC}"
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}❌ Python 3 n'est pas installé."
    echo "   → https://www.python.org/downloads/"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo -e "${RED}❌ Python 3.10+ requis. Version actuelle : $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python $PYTHON_VERSION${NC}"

# ── Vérification FFmpeg ──────────────────────────────────────
echo -e "${CYAN}[2/5] Vérification FFmpeg...${NC}"
if ! command -v ffmpeg &>/dev/null; then
    echo -e "${YELLOW}⚠️  FFmpeg n'est pas installé."
    echo ""
    echo "   Installation :"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "     brew install ffmpeg"
    else
        echo "     Ubuntu/Debian : sudo apt install ffmpeg"
        echo "     Fedora         : sudo dnf install ffmpeg"
        echo "     Arch           : sudo pacman -S ffmpeg"
    fi
    echo ""
    read -p "Continuer sans FFmpeg ? (non recommandé) [o/N] " choix
    if [[ "$choix" != "o" && "$choix" != "O" ]]; then
        exit 1
    fi
else
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    echo -e "${GREEN}✓ FFmpeg $FFMPEG_VERSION${NC}"
fi

# ── Vérification Ollama ──────────────────────────────────────
echo -e "${CYAN}[3/5] Vérification Ollama...${NC}"
if ! command -v ollama &>/dev/null; then
    echo -e "${YELLOW}⚠️  Ollama n'est pas installé."
    echo "   L'analyse LLM sera désactivée (scoring audio uniquement)."
    echo ""
    echo "   Pour installer Ollama :"
    echo "     curl -fsSL https://ollama.ai/install.sh | sh"
    echo "   Puis télécharger le modèle :"
    echo "     ollama pull mistral"
    echo ""
else
    echo -e "${GREEN}✓ Ollama installé${NC}"
    # Vérifier si Ollama est lancé
    if curl -s http://localhost:11434/api/version &>/dev/null; then
        echo -e "${GREEN}✓ Ollama est lancé${NC}"
        # Télécharger le modèle Mistral si nécessaire
        echo "   Vérification du modèle Mistral..."
        if ! ollama list 2>/dev/null | grep -q "mistral"; then
            echo "   Téléchargement de Mistral 7B (peut prendre quelques minutes)..."
            ollama pull mistral
        else
            echo -e "${GREEN}✓ Modèle Mistral disponible${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  Ollama n'est pas lancé. Lance-le avec : ollama serve${NC}"
    fi
fi

# ── Environnement virtuel Python ─────────────────────────────
echo -e "${CYAN}[4/5] Création de l'environnement virtuel...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Environnement virtuel créé${NC}"
else
    echo -e "${GREEN}✓ Environnement virtuel existant${NC}"
fi

# Activation
source venv/bin/activate

# ── Installation des dépendances ─────────────────────────────
echo -e "${CYAN}[5/5] Installation des dépendances Python...${NC}"
pip install --quiet --upgrade pip
pip install -r requirements.txt

echo ""
echo -e "${GREEN}============================================================"
echo -e "   ✅  Installation terminée !"
echo -e "============================================================${NC}"
echo ""
echo "  Pour lancer AI Clipper :"
echo -e "  ${CYAN}source venv/bin/activate${NC}"
echo -e "  ${CYAN}python app.py${NC}"
echo ""
echo "  Puis ouvre dans ton navigateur :"
echo -e "  ${CYAN}http://localhost:8000${NC}"
echo ""

# Créer le script de lancement
cat > lancer.sh << 'EOF'
#!/bin/bash
source venv/bin/activate
python app.py
EOF
chmod +x lancer.sh

echo -e "  Ou utilise directement : ${CYAN}./lancer.sh${NC}"
echo ""
