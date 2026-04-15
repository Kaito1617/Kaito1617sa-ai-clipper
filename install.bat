@echo off
REM ============================================================
REM  AI Clipper — Script d'installation (Windows)
REM ============================================================

chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo ============================================================
echo    ^🎬  AI Clipper — Installation Windows
echo ============================================================
echo.

REM ── Vérification Python ──────────────────────────────────────
echo [1/5] Verification Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo          Telecharger : https://www.python.org/downloads/
    echo          IMPORTANT : Cocher "Add Python to PATH" lors de l'installation !
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python !PYVER!

REM ── Vérification FFmpeg ──────────────────────────────────────
echo.
echo [2/5] Verification FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [ATTENTION] FFmpeg n'est pas installe.
    echo.
    echo    Installation de FFmpeg :
    echo    1. Telecharger : https://www.gyan.dev/ffmpeg/builds/
    echo       (ffmpeg-release-essentials.zip)
    echo    2. Extraire dans C:\ffmpeg\
    echo    3. Ajouter C:\ffmpeg\bin au PATH Windows
    echo       (Panneau de config - Systeme - Variables d'environnement)
    echo.
    echo    Ou via winget : winget install ffmpeg
    echo    Ou via Chocolatey : choco install ffmpeg
    echo.
    set /p choix="Continuer sans FFmpeg ? (non recommande) [o/N] "
    if /i "!choix!" neq "o" (
        exit /b 1
    )
) else (
    echo [OK] FFmpeg installe
)

REM ── Vérification Ollama ──────────────────────────────────────
echo.
echo [3/5] Verification Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo [INFO] Ollama n'est pas installe.
    echo        L'analyse LLM sera desactivee (scoring audio uniquement).
    echo.
    echo        Pour installer Ollama :
    echo        https://ollama.ai/download/windows
    echo.
    echo        Puis telecharger le modele :
    echo        ollama pull mistral
    echo.
) else (
    echo [OK] Ollama installe
    REM Vérifier si le modèle est disponible
    ollama list 2>nul | findstr /i "mistral" >nul
    if errorlevel 1 (
        echo     Telechargement du modele Mistral 7B...
        ollama pull mistral
    ) else (
        echo [OK] Modele Mistral disponible
    )
)

REM ── Environnement virtuel Python ─────────────────────────────
echo.
echo [4/5] Creation de l'environnement virtuel...
if not exist "venv" (
    python -m venv venv
    echo [OK] Environnement virtuel cree
) else (
    echo [OK] Environnement virtuel existant
)

REM Activation
call venv\Scripts\activate.bat

REM ── Installation des dépendances ─────────────────────────────
echo.
echo [5/5] Installation des dependances Python...
pip install --quiet --upgrade pip
pip install -r requirements.txt

echo.
echo ============================================================
echo    OK  Installation terminee !
echo ============================================================
echo.
echo   Pour lancer AI Clipper :
echo   1. Double-cliquer sur "lancer.bat"
echo   OU
echo   2. Dans un terminal :
echo      venv\Scripts\activate
echo      python app.py
echo.
echo   Puis ouvrir dans ton navigateur :
echo   http://localhost:8000
echo.

REM Créer le script de lancement
echo @echo off > lancer.bat
echo call venv\Scripts\activate.bat >> lancer.bat
echo python app.py >> lancer.bat

echo   Script de lancement cree : lancer.bat
echo.
pause
