"""
app.py — Serveur principal AI Clipper
FastAPI + WebSocket pour le traitement en temps réel des vidéos.
Interface web locale accessible sur http://localhost:8000
"""

import asyncio
import json
import logging
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# Configuration des logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Initialisation de l'application FastAPI
# ─────────────────────────────────────────────

app = FastAPI(
    title="AI Clipper",
    description="Transforme tes vidéos en YouTube Shorts automatiquement",
    version="1.0.0"
)

# Dossiers de travail
DOSSIER_UPLOADS = Path("uploads").resolve()
DOSSIER_OUTPUT = Path("output").resolve()
DOSSIER_UPLOADS.mkdir(exist_ok=True)
DOSSIER_OUTPUT.mkdir(exist_ok=True)

# Stockage des tâches en cours {task_id: {statut, progression, ...}}
taches_en_cours: Dict[str, dict] = {}

# Connexions WebSocket actives {task_id: WebSocket}
connexions_ws: Dict[str, WebSocket] = {}

# Expression régulière pour valider un task_id (8 caractères alphanumériques et tirets)
_RE_TASK_ID = re.compile(r'^[0-9a-f\-]{8,36}$')
# Expression régulière pour valider un nom de fichier MP4/ZIP sûr
_RE_NOM_FICHIER = re.compile(r'^[a-zA-Z0-9_\-]{1,80}\.(mp4|zip)$')


def _valider_task_id(task_id: str) -> bool:
    """Valide que le task_id ne contient que des caractères sûrs."""
    return bool(_RE_TASK_ID.match(task_id))


def _chemin_safe(base: Path, *parties) -> Path:
    """
    Résout un chemin et vérifie qu'il est bien dans le répertoire base.
    Lève ValueError si le chemin sort du répertoire autorisé (path traversal).
    """
    chemin = (base / Path(*parties)).resolve()
    if not str(chemin).startswith(str(base)):
        raise ValueError(f"Chemin non autorisé : {chemin}")
    return chemin


# ─────────────────────────────────────────────
# WebSocket — Progression en temps réel
# ─────────────────────────────────────────────

@app.websocket("/ws/progress/{task_id}")
async def websocket_progression(websocket: WebSocket, task_id: str):
    """WebSocket pour recevoir la progression d'une tâche en temps réel."""
    await websocket.accept()
    connexions_ws[task_id] = websocket
    logger.info(f"WebSocket connecté pour tâche {task_id}")

    try:
        while True:
            # Vérifier si la tâche est terminée
            tache = taches_en_cours.get(task_id, {})
            if tache.get("statut") in ("terminee", "erreur"):
                await websocket.send_json(tache)
                break

            # Attendre les messages du client (keep-alive)
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        logger.info(f"WebSocket déconnecté : {task_id}")
    finally:
        connexions_ws.pop(task_id, None)


async def envoyer_progression(task_id: str, etape: str, pourcentage: int, details: dict = None):
    """Envoie une mise à jour de progression via WebSocket."""
    message = {
        "task_id": task_id,
        "etape": etape,
        "pourcentage": pourcentage,
        "timestamp": time.time(),
        **(details or {})
    }

    # Mise à jour de l'état interne
    if task_id in taches_en_cours:
        taches_en_cours[task_id].update(message)

    # Envoi WebSocket si connecté
    ws = connexions_ws.get(task_id)
    if ws:
        try:
            await ws.send_json(message)
        except Exception:
            connexions_ws.pop(task_id, None)


# ─────────────────────────────────────────────
# API — Upload et lancement du traitement
# ─────────────────────────────────────────────

@app.post("/api/upload")
async def upload_et_traiter(
    video: UploadFile = File(...),
    mode: str = Form("football"),
    nb_shorts: int = Form(5),
    duree_short: int = Form(45),
    intensite: str = Form("normal"),
    format_sortie: str = Form("portrait")
):
    """
    Endpoint principal : upload la vidéo et lance le pipeline de traitement.
    Retourne un task_id pour suivre la progression via WebSocket.
    """
    # Validation des paramètres
    if mode not in ("football", "anime", "streamer"):
        return JSONResponse({"erreur": "Mode invalide. Choisir : football, anime, streamer"}, status_code=400)
    if nb_shorts < 1 or nb_shorts > 20:
        return JSONResponse({"erreur": "Nombre de shorts invalide (1-20)"}, status_code=400)
    if duree_short not in (30, 45, 60):
        return JSONResponse({"erreur": "Durée invalide. Choisir : 30, 45 ou 60 secondes"}, status_code=400)
    if intensite not in ("leger", "normal", "intense"):
        return JSONResponse({"erreur": "Intensité invalide. Choisir : leger, normal, intense"}, status_code=400)
    if format_sortie not in ("portrait", "paysage"):
        return JSONResponse({"erreur": "Format invalide. Choisir : portrait, paysage"}, status_code=400)

    # Validation du format vidéo
    extensions_acceptees = {".mp4", ".avi", ".mkv", ".mov", ".webm", ".flv", ".ts"}
    extension = Path(video.filename).suffix.lower()
    if extension not in extensions_acceptees:
        return JSONResponse(
            {"erreur": f"Format non supporté. Acceptés : {', '.join(extensions_acceptees)}"},
            status_code=400
        )

    # Génération d'un ID unique pour cette tâche
    task_id = str(uuid.uuid4())[:8]

    # Sauvegarde du fichier uploadé
    dossier_tache = DOSSIER_UPLOADS / task_id
    dossier_tache.mkdir(exist_ok=True)
    chemin_video = dossier_tache / f"source{extension}"

    try:
        with open(chemin_video, "wb") as f:
            contenu = await video.read()
            if len(contenu) == 0:
                return JSONResponse({"erreur": "Fichier vide"}, status_code=400)
            f.write(contenu)
        logger.info(f"Vidéo uploadée : {video.filename} ({len(contenu) // 1024 // 1024} Mo) → {task_id}")
    except Exception as e:
        logger.error(f"Erreur sauvegarde vidéo : {e}")
        return JSONResponse({"erreur": "Erreur lors de la sauvegarde du fichier"}, status_code=500)

    # Initialisation de la tâche
    taches_en_cours[task_id] = {
        "task_id": task_id,
        "statut": "en_cours",
        "etape": "Démarrage...",
        "pourcentage": 0,
        "mode": mode,
        "nb_shorts": nb_shorts,
        "duree_short": duree_short,
        "intensite": intensite,
        "format_sortie": format_sortie,
        "nom_video": video.filename,
        "shorts": []
    }

    # Lancement du pipeline en arrière-plan
    asyncio.create_task(
        lancer_pipeline(
            task_id=task_id,
            chemin_video=str(chemin_video),
            mode=mode,
            nb_shorts=nb_shorts,
            duree_short=duree_short,
            intensite=intensite,
            format_sortie=format_sortie
        )
    )

    return JSONResponse({
        "task_id": task_id,
        "message": "Traitement lancé !",
        "ws_url": f"/ws/progress/{task_id}"
    })


# ─────────────────────────────────────────────
# Pipeline de traitement principal
# ─────────────────────────────────────────────

async def lancer_pipeline(
    task_id: str,
    chemin_video: str,
    mode: str,
    nb_shorts: int,
    duree_short: int,
    intensite: str,
    format_sortie: str = "portrait"
):
    """
    Pipeline complet de traitement :
    Transcription → Analyse → Sélection → Effets → Sous-titres → Sound → Export
    """
    dossier_sortie = str(DOSSIER_OUTPUT / task_id)
    os.makedirs(dossier_sortie, exist_ok=True)

    def cb_progression(etape: str, pourcentage: int):
        """Callback synchrone pour les modules engine (appelé depuis thread)."""
        asyncio.create_task(envoyer_progression(task_id, etape, pourcentage))

    try:
        # ─── Chargement config mode ───
        config_mode = _charger_config_mode(mode)

        # ─── Étape 1 : Transcription ───
        await envoyer_progression(task_id, "🎙️ Transcription...", 5)
        logger.info(f"[{task_id}] Étape 1 : Transcription")

        from engine.transcriber import transcrire_video
        transcription = await asyncio.to_thread(
            transcrire_video,
            chemin_video,
            "medium",
            None,
            None  # Pas de callback dans le thread pour éviter les conflits asyncio
        )

        await envoyer_progression(task_id, "✅ Transcription terminée", 20)

        # ─── Étape 2 : Analyse et scoring ───
        await envoyer_progression(task_id, "🧠 Analyse des moments forts...", 22)
        logger.info(f"[{task_id}] Étape 2 : Analyse")

        from engine.analyzer import analyser_et_scorer
        segments_scores = await asyncio.to_thread(
            analyser_et_scorer,
            chemin_video,
            transcription,
            mode,
            config_mode,
            None
        )

        await envoyer_progression(task_id, "✅ Analyse terminée", 40)

        # ─── Étape 3 : Sélection des meilleurs moments ───
        await envoyer_progression(task_id, "✂️ Sélection des meilleurs moments...", 42)
        logger.info(f"[{task_id}] Étape 3 : Sélection")

        from engine.clipper import selectionner_meilleurs_moments
        moments = selectionner_meilleurs_moments(
            segments_scores=segments_scores,
            nb_shorts=nb_shorts,
            duree_short=duree_short,
            config_mode=config_mode
        )

        if not moments:
            raise ValueError("Aucun moment intéressant détecté dans cette vidéo.")

        await envoyer_progression(
            task_id, f"✅ {len(moments)} moments sélectionnés", 45,
            {"moments_trouves": len(moments)}
        )

        # ─── Étapes 4-7 : Export de chaque Short ───
        await envoyer_progression(task_id, "🎬 Génération des Shorts...", 47)
        logger.info(f"[{task_id}] Étape 4 : Export des Shorts")

        from engine.exporter import exporter_shorts
        shorts = await asyncio.to_thread(
            exporter_shorts,
            chemin_video,
            moments,
            transcription,
            mode,
            config_mode,
            intensite,
            dossier_sortie,
            task_id,
            None,
            format_sortie
        )

        if not shorts:
            raise ValueError("Aucun Short n'a pu être généré.")

        await envoyer_progression(
            task_id, f"📦 Création de l'archive ZIP...", 95
        )

        # ─── Étape 8 : Création du ZIP ───
        from engine.exporter import creer_archive_zip
        chemin_zip = os.path.join(dossier_sortie, f"shorts_{task_id}.zip")
        creer_archive_zip(shorts, chemin_zip)

        # ─── Terminé ! ───
        taches_en_cours[task_id]["statut"] = "terminee"
        taches_en_cours[task_id]["shorts"] = [
            {
                "numero": s["numero"],
                "nom_fichier": s["nom_fichier"],
                "duree": s["duree"],
                "score": s["score"],
                "url": f"/api/shorts/{task_id}/{s['nom_fichier']}",
                "taille_mo": round(s.get("taille_octets", 0) / 1024 / 1024, 1)
            }
            for s in shorts
        ]
        taches_en_cours[task_id]["zip_url"] = f"/api/download/{task_id}"

        await envoyer_progression(
            task_id, f"🎉 {len(shorts)} Shorts prêts !", 100,
            {
                "statut": "terminee",
                "shorts": taches_en_cours[task_id]["shorts"],
                "zip_url": taches_en_cours[task_id]["zip_url"]
            }
        )
        logger.info(f"[{task_id}] ✓ Pipeline terminé ! {len(shorts)} Shorts générés.")

    except Exception as e:
        logger.error(f"[{task_id}] ✗ Erreur pipeline : {e}", exc_info=True)
        taches_en_cours[task_id]["statut"] = "erreur"
        taches_en_cours[task_id]["erreur"] = str(e)
        await envoyer_progression(
            task_id, f"❌ Erreur : {str(e)}", 0,
            {"statut": "erreur", "erreur": str(e)}
        )


def _charger_config_mode(mode: str) -> dict:
    """Charge le fichier JSON de configuration du mode."""
    chemin_config = Path("modes") / f"{mode}.json"
    if not chemin_config.exists():
        raise FileNotFoundError(f"Config mode introuvable : {chemin_config}")
    with open(chemin_config, "r", encoding="utf-8") as f:
        return json.load(f)


# ─────────────────────────────────────────────
# API — Récupération des résultats
# ─────────────────────────────────────────────

@app.get("/api/status/{task_id}")
async def statut_tache(task_id: str):
    """Retourne le statut actuel d'une tâche."""
    if not _valider_task_id(task_id):
        return JSONResponse({"erreur": "Identifiant de tâche invalide"}, status_code=400)
    tache = taches_en_cours.get(task_id)
    if not tache:
        return JSONResponse({"erreur": "Tâche introuvable"}, status_code=404)
    return JSONResponse(tache)


@app.get("/api/shorts/{task_id}/{nom_fichier}")
async def telecharger_short(task_id: str, nom_fichier: str):
    """Sert un Short généré pour lecture/téléchargement."""
    # Validation stricte des paramètres pour éviter le path traversal
    if not _valider_task_id(task_id):
        return JSONResponse({"erreur": "Identifiant de tâche invalide"}, status_code=400)
    nom_fichier = Path(nom_fichier).name
    if not _RE_NOM_FICHIER.match(nom_fichier):
        return JSONResponse({"erreur": "Nom de fichier invalide"}, status_code=400)

    try:
        chemin = _chemin_safe(DOSSIER_OUTPUT, task_id, nom_fichier)
    except ValueError:
        return JSONResponse({"erreur": "Accès refusé"}, status_code=403)

    if not chemin.exists():
        return JSONResponse({"erreur": "Fichier introuvable"}, status_code=404)

    return FileResponse(
        str(chemin),
        media_type="video/mp4",
        headers={"Content-Disposition": f"inline; filename={nom_fichier}"}
    )


@app.get("/api/download/{task_id}")
async def telecharger_zip(task_id: str):
    """Télécharge le ZIP contenant tous les Shorts d'une tâche."""
    if not _valider_task_id(task_id):
        return JSONResponse({"erreur": "Identifiant de tâche invalide"}, status_code=400)

    nom_zip = f"shorts_{task_id}.zip"
    try:
        chemin_zip = _chemin_safe(DOSSIER_OUTPUT, task_id, nom_zip)
    except ValueError:
        return JSONResponse({"erreur": "Accès refusé"}, status_code=403)

    if not chemin_zip.exists():
        return JSONResponse({"erreur": "Archive ZIP introuvable"}, status_code=404)

    return FileResponse(
        str(chemin_zip),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={nom_zip}"}
    )


@app.delete("/api/tache/{task_id}")
async def supprimer_tache(task_id: str):
    """Supprime les fichiers d'une tâche terminée pour libérer de l'espace."""
    if not _valider_task_id(task_id):
        return JSONResponse({"erreur": "Identifiant de tâche invalide"}, status_code=400)

    # Nettoyage dossiers (chemins vérifiés)
    for base in [DOSSIER_UPLOADS, DOSSIER_OUTPUT]:
        try:
            dossier = _chemin_safe(base, task_id)
            if dossier.exists():
                shutil.rmtree(dossier, ignore_errors=True)
        except ValueError:
            pass  # Chemin non autorisé, on ignore

    taches_en_cours.pop(task_id, None)
    return JSONResponse({"message": f"Tâche supprimée"})


# ─────────────────────────────────────────────
# Fichiers statiques (interface web)
# ─────────────────────────────────────────────

# Servir le frontend
app.mount("/", StaticFiles(directory="frontend", html=True), name="frontend")


# ─────────────────────────────────────────────
# Lancement du serveur
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  🎬  AI CLIPPER — Machine à YouTube Shorts")
    print("="*60)
    print("  Interface web : http://localhost:8000")
    print("  Docs API      : http://localhost:8000/docs")
    print("="*60 + "\n")

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1  # 1 worker car on utilise le GPU (pas thread-safe avec plusieurs workers)
    )
