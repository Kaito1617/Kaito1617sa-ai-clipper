# 🎬 AI Clipper — Machine à YouTube Shorts

**Transforme automatiquement tes vidéos longues en YouTube Shorts prêts à poster.**

Donne une vidéo (match de foot, épisode d'anime, VOD de streamer), l'IA détecte les meilleurs moments, les découpe, ajoute les effets, les sous-titres animés et exporte des Shorts 9:16 de qualité professionnelle — **100% en local, 0 cloud, 0 abonnement**.

---

## ✅ Prérequis

### Matériel recommandé

| Composant | Minimum | Recommandé |
|-----------|---------|------------|
| **GPU** | GTX 1060 (6 Go) | RTX 3070+ / RTX 5070 |
| **RAM** | 16 Go | 32 Go+ |
| **Stockage** | 50 Go libre | 100 Go+ SSD |

### Logiciels requis

#### 1. Python 3.10+
- **Windows** : https://www.python.org/downloads/ (cocher "Add Python to PATH")
- **Linux** : `sudo apt install python3.10 python3.10-venv python3-pip`

#### 2. FFmpeg
- **Windows** : `winget install ffmpeg`
- **Linux** : `sudo apt install ffmpeg`
- **macOS** : `brew install ffmpeg`

#### 3. Ollama (optionnel mais recommandé)
Pour l'analyse intelligente par LLM.
- **Téléchargement** : https://ollama.ai/download
- Après installation : `ollama pull mistral`

---

## 🚀 Installation

### Installation automatique (recommandé)

**Windows** : Double-clic sur `install.bat`

**Linux / macOS** :
```bash
chmod +x install.sh && ./install.sh
```

### Installation manuelle

```bash
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

---

## ▶️ Lancement

```bash
source venv/bin/activate
python app.py
```

Ouvre **http://localhost:8000** dans ton navigateur.

---

## 🎮 Utilisation

1. **Upload** : Glisse ta vidéo dans la zone ou clique pour sélectionner
2. **Mode** : Choisis ⚽ Football, 🎌 Anime ou 🎮 Streamer
3. **Paramètres** : Nombre de Shorts (1-15), durée (30/45/60s), intensité
4. **Générer** : Clique et regarde la progression en temps réel
5. **Télécharger** : Preview + téléchargement individuel ou ZIP

---

## 🎯 Les 3 modes

### ⚽ Football — Inspiration : AshStudio7
Détecte buts, dribbles, célébrations, réactions commentateurs, foule en délire.
Style : zoom rapide, texte accrocheur, transitions dynamiques, SFX d'impact.

### 🎌 Anime — Inspiration : ShonifyG
Détecte moments épiques, scènes drôles, répliques cultes, réactions exagérées.
Style : zoom visages, bass boost, sous-titres colorés, SFX boom.

### 🎮 Streamer — Inspiration : JynxziJ
Détecte cris, fous rires, rage, fails, réactions extrêmes.
Style : zoom face cam, shake effect, sous-titres mot par mot, SFX comiques.

---

## 🧠 Pipeline IA

```
📹 Vidéo source
  │
  ├→ 🎙️ faster-whisper : transcription GPU + timecodes mot par mot
  ├→ 🔊 librosa : analyse audio (pics d'énergie, cris, rires)
  ├→ 🧠 Ollama (Mistral 7B) : score LLM de chaque segment
  ├→ 👀 YOLOv8 : détection visuelle (personnes/visages)
  │
  ├→ ✂️ Sélection des top N moments (score combiné audio + LLM)
  ├→ 📐 Recadrage 9:16 intelligent (suit le sujet)
  ├→ 🔥 Effets (zoom, shake, transitions, fade)
  ├→ 📝 Sous-titres animés style CapCut
  ├→ 🔊 Sound design (bass boost, SFX, musique de fond)
  │
  └→ 📦 Export MP4 H.264 1080x1920 NVENC (RTX GPU)
```

---

## ⚙️ Configuration avancée

### Modifier un mode

Édite les fichiers `modes/football.json`, `modes/anime.json` ou `modes/streamer.json`.

```json
{
  "llm_modele": "mistral",
  "poids_llm": 0.5,
  "effets": { "zoom_max": 1.4, "shake": true },
  "audio": { "bass_boost": true, "bass_boost_db": 6 }
}
```

### Ajouter des SFX

Copie tes fichiers MP3/WAV dans `assets/sfx/`. Voir `assets/sfx/README.md`.

### Musique de fond

Copie tes fichiers MP3 dans `assets/music/`. Voir `assets/music/README.md`.

---

## 📁 Structure du projet

```
ai-clipper/
├── app.py                  # Serveur FastAPI + WebSocket
├── requirements.txt        # Dépendances Python
├── install.sh / install.bat# Installation one-click
├── frontend/               # Interface web (HTML/CSS/JS)
├── engine/                 # Moteur IA
│   ├── transcriber.py      # Whisper GPU
│   ├── analyzer.py         # Audio + LLM scoring
│   ├── detector.py         # YOLOv8 détection
│   ├── clipper.py          # Sélection moments
│   ├── effects.py          # Effets visuels 9:16
│   ├── subtitles.py        # Sous-titres animés
│   ├── sound_design.py     # Bass boost + SFX
│   └── exporter.py         # Export NVENC
├── modes/                  # Config par mode (JSON)
├── assets/                 # SFX, polices, musiques
├── uploads/                # Vidéos uploadées
└── output/                 # Shorts générés
```

---

## ❓ FAQ / Troubleshooting

**"FFmpeg n'est pas trouvé"**
```bash
# Windows : winget install ffmpeg (redémarre le terminal)
# Linux : sudo apt install ffmpeg
ffmpeg -version  # vérification
```

**"Ollama n'est pas disponible"**
Fonctionne sans — scoring audio uniquement. Pour activer le LLM :
```bash
ollama serve  # dans un terminal séparé
ollama pull mistral
```

**"Erreur CUDA / GPU non disponible"**
Bascule automatiquement sur CPU. Plus lent mais fonctionnel.

**"La vidéo est trop courte"**
La vidéo doit faire minimum 2 minutes.

**"Aucun moment détecté"**
- Vérifie que la vidéo a du son
- Lance Ollama : `ollama serve`
- Baisse les seuils dans `modes/{mode}.json`

**"Export trop lent"**
- Vérifie NVENC : `ffmpeg -encoders | grep nvenc`
- L'encodage CPU est un fallback automatique

**"Port 8000 déjà utilisé"**
Change le port dans `app.py` : `port=8001`

---

## 💪 Stack technique

| Composant | Technologie |
|-----------|-------------|
| Serveur | FastAPI + Uvicorn |
| Transcription | faster-whisper (Whisper GPU) |
| Analyse audio | librosa |
| LLM local | Ollama (Mistral 7B) |
| Détection visuelle | YOLOv8 (ultralytics) |
| Encodage vidéo | FFmpeg + NVENC |
| Frontend | HTML/CSS/JS pur |
| Temps réel | WebSocket |

---

*Fait avec ❤️ — 100% local, 100% privé, 0 abonnement*
