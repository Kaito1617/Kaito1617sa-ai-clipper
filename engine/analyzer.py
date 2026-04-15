"""
analyzer.py — Analyse et scoring des moments forts
Combine l'analyse audio (librosa) et l'analyse LLM (Ollama) pour scorer
chaque segment de la vidéo et détecter les moments les plus intéressants.
"""

import os
import json
import logging
import math
import subprocess
import tempfile
from typing import Optional, Callable, List

import numpy as np

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Analyse audio
# ─────────────────────────────────────────────

def analyser_audio(chemin_video: str, callback_progression: Optional[Callable] = None) -> dict:
    """
    Analyse l'audio de la vidéo et retourne les métriques d'énergie.

    Returns:
        dict avec 'energie_par_seconde', 'pics_energie', 'duree_totale'
    """
    logger.info("Analyse audio en cours...")
    if callback_progression:
        callback_progression("Extraction de l'audio...", 5)

    # Extraction de l'audio en WAV mono avec FFmpeg
    avec_fichier_temp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    chemin_audio_temp = avec_fichier_temp.name
    avec_fichier_temp.close()

    try:
        cmd = [
            "ffmpeg", "-y", "-i", chemin_video,
            "-ac", "1",        # Mono
            "-ar", "22050",    # 22kHz suffisant pour l'analyse
            "-vn",             # Pas de vidéo
            chemin_audio_temp
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        if callback_progression:
            callback_progression("Analyse des niveaux sonores...", 20)

        # Lecture et analyse avec librosa
        import librosa
        y, sr = librosa.load(chemin_audio_temp, sr=None)
        duree_totale = len(y) / sr

        # Calcul du RMS par frame (énergie)
        taille_frame = int(sr * 0.5)  # Fenêtres de 0.5 secondes
        hop_length = int(sr * 0.25)   # Décalage de 0.25 secondes

        rms = librosa.feature.rms(y=y, frame_length=taille_frame, hop_length=hop_length)[0]
        temps_frames = librosa.frames_to_time(
            np.arange(len(rms)), sr=sr, hop_length=hop_length
        )

        # Normalisation de l'énergie (0-100)
        rms_norm = rms / (np.max(rms) + 1e-8)
        energie_par_seconde = []
        for t, e in zip(temps_frames, rms_norm):
            energie_par_seconde.append({
                "temps": round(float(t), 3),
                "energie": round(float(e) * 100, 1)
            })

        # Détection des pics d'énergie (> 70% de l'énergie max)
        seuil_pic = 0.7
        pics = []
        en_pic = False
        debut_pic = 0.0

        for item in energie_par_seconde:
            if item["energie"] >= seuil_pic * 100 and not en_pic:
                en_pic = True
                debut_pic = item["temps"]
            elif item["energie"] < seuil_pic * 100 and en_pic:
                en_pic = False
                if item["temps"] - debut_pic >= 1.0:  # Pic d'au moins 1 seconde
                    pics.append({
                        "debut": debut_pic,
                        "fin": item["temps"],
                        "intensite": round(
                            max(e["energie"] for e in energie_par_seconde
                                if debut_pic <= e["temps"] <= item["temps"]),
                            1
                        )
                    })

        logger.info(f"Analyse audio : {len(pics)} pics détectés sur {duree_totale:.1f}s")

        if callback_progression:
            callback_progression("Analyse audio terminée", 100)

        return {
            "energie_par_seconde": energie_par_seconde,
            "pics_energie": pics,
            "duree_totale": duree_totale
        }

    finally:
        if os.path.exists(chemin_audio_temp):
            os.unlink(chemin_audio_temp)


# ─────────────────────────────────────────────
# Scoring des segments
# ─────────────────────────────────────────────

def scorer_segment_audio(segment: dict, analyse_audio: dict) -> float:
    """
    Calcule un score audio (0-100) pour un segment donné.
    """
    debut = segment["debut"]
    fin = segment["fin"]
    duree = fin - debut

    if duree <= 0:
        return 0.0

    # Énergie moyenne sur la durée du segment
    energies = [
        e["energie"] for e in analyse_audio["energie_par_seconde"]
        if debut <= e["temps"] <= fin
    ]

    if not energies:
        return 0.0

    energie_moyenne = sum(energies) / len(energies)
    energie_max = max(energies)

    # Score = 60% énergie moyenne + 40% pic d'énergie
    score = (energie_moyenne * 0.6) + (energie_max * 0.4)

    # Bonus si chevauchement avec un pic détecté
    for pic in analyse_audio["pics_energie"]:
        chevauchement = min(fin, pic["fin"]) - max(debut, pic["debut"])
        if chevauchement > 0:
            score = min(100, score + 15)
            break

    return round(score, 1)


# ─────────────────────────────────────────────
# Analyse LLM via Ollama
# ─────────────────────────────────────────────

def analyser_avec_llm(
    segments: List[dict],
    mode: str,
    config_mode: dict,
    callback_progression: Optional[Callable] = None
) -> List[dict]:
    """
    Envoie le transcript à Ollama (Mistral 7B ou LLaMA 3 8B) pour scorer
    les moments selon le mode choisi (football, anime, streamer).

    Returns:
        Liste des segments avec un champ 'score_llm' (0-100)
    """
    logger.info(f"Analyse LLM (mode: {mode})...")

    prompt_systeme = config_mode.get("llm_prompt_systeme", "")
    modele_ollama = config_mode.get("llm_modele", "mistral")

    # Construction du texte de transcript abrégé
    # (max 4000 tokens pour Ollama)
    lignes_transcript = []
    for i, seg in enumerate(segments):
        lignes_transcript.append(f"[{seg['debut']:.1f}s-{seg['fin']:.1f}s] {seg['texte']}")

    transcript_texte = "\n".join(lignes_transcript[:200])  # Limiter à 200 segments

    prompt_utilisateur = f"""Voici la transcription d'une vidéo (mode: {mode}).

{transcript_texte}

Pour chaque segment (identifié par son indice 0, 1, 2...), donne un score de 0 à 100 indiquant à quel point ce moment est intéressant pour créer un Short YouTube.
Score 100 = moment parfait (but, réaction épique, moment drôle...)
Score 0 = moment ennuyeux/inutile

Réponds UNIQUEMENT avec un JSON de la forme:
{{"scores": [score_0, score_1, score_2, ...]}}

Ne mets que les scores, dans l'ordre des segments."""

    try:
        import requests
        reponse = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": modele_ollama,
                "prompt": f"{prompt_systeme}\n\n{prompt_utilisateur}",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 1000}
            },
            timeout=120
        )
        reponse.raise_for_status()
        texte_reponse = reponse.json().get("response", "")

        # Extraction du JSON
        debut_json = texte_reponse.find("{")
        fin_json = texte_reponse.rfind("}") + 1
        if debut_json >= 0 and fin_json > debut_json:
            donnees = json.loads(texte_reponse[debut_json:fin_json])
            scores_llm = donnees.get("scores", [])

            # Assignation des scores aux segments
            for i, seg in enumerate(segments):
                if i < len(scores_llm):
                    seg["score_llm"] = float(scores_llm[i])
                else:
                    seg["score_llm"] = 0.0

            logger.info(f"LLM: {len(scores_llm)} scores reçus")
            return segments

    except Exception as e:
        logger.warning(f"Ollama non disponible ({e}). Utilisation du scoring audio uniquement.")

    # Fallback : score LLM à 0 (le score audio sera utilisé seul)
    for seg in segments:
        seg["score_llm"] = 0.0

    return segments


# ─────────────────────────────────────────────
# Scoring final combiné
# ─────────────────────────────────────────────

def analyser_et_scorer(
    chemin_video: str,
    transcription: dict,
    mode: str,
    config_mode: dict,
    callback_progression: Optional[Callable] = None
) -> List[dict]:
    """
    Pipeline complet d'analyse : audio + LLM + score final.

    Returns:
        Liste de segments triés par score décroissant, avec:
            - 'score_audio': float (0-100)
            - 'score_llm': float (0-100)
            - 'score_final': float (0-100)
    """
    logger.info("=== Début de l'analyse ===")

    # 1. Analyse audio
    if callback_progression:
        callback_progression("Analyse audio...", 10)
    analyse_audio = analyser_audio(chemin_video)

    # 2. Regrouper les segments Whisper en fenêtres de 30-60 secondes
    duree_fenetre = config_mode.get("duree_fenetre_analyse", 30)  # secondes
    fenetres = _creer_fenetres(transcription["segments"], duree_fenetre)

    # 3. Score audio pour chaque fenêtre
    if callback_progression:
        callback_progression("Scoring audio des segments...", 30)
    for fenetre in fenetres:
        fenetre["score_audio"] = scorer_segment_audio(fenetre, analyse_audio)

    # 4. Analyse LLM
    if callback_progression:
        callback_progression("Analyse par IA (LLM)...", 50)
    fenetres = analyser_avec_llm(fenetres, mode, config_mode)

    # 5. Score final = combinaison audio + LLM
    poids_llm = config_mode.get("poids_llm", 0.5)
    poids_audio = 1.0 - poids_llm

    for fenetre in fenetres:
        score_audio = fenetre.get("score_audio", 0)
        score_llm = fenetre.get("score_llm", 0)

        # Si LLM n'a pas répondu, utiliser uniquement l'audio
        if score_llm == 0.0:
            fenetre["score_final"] = score_audio
        else:
            fenetre["score_final"] = round(
                score_audio * poids_audio + score_llm * poids_llm, 1
            )

    # Tri par score décroissant
    fenetres_triees = sorted(fenetres, key=lambda x: x["score_final"], reverse=True)

    logger.info(f"Analyse terminée : {len(fenetres_triees)} segments scorés")

    if callback_progression:
        callback_progression("Analyse terminée", 100)

    return fenetres_triees


def _creer_fenetres(segments_whisper: list, duree_fenetre: float) -> List[dict]:
    """
    Regroupe les segments Whisper en fenêtres de durée approximative.
    """
    if not segments_whisper:
        return []

    fenetres = []
    debut_fenetre = segments_whisper[0]["debut"]
    texte_fenetre = []
    mots_fenetre = []
    segments_fenetre = []

    for seg in segments_whisper:
        segments_fenetre.append(seg)
        texte_fenetre.append(seg["texte"])
        mots_fenetre.extend(seg.get("mots", []))

        duree_actuelle = seg["fin"] - debut_fenetre
        if duree_actuelle >= duree_fenetre:
            fenetres.append({
                "debut": debut_fenetre,
                "fin": seg["fin"],
                "texte": " ".join(texte_fenetre),
                "mots": mots_fenetre.copy(),
                "segments_source": segments_fenetre.copy()
            })
            # Nouvelle fenêtre
            debut_fenetre = seg["fin"]
            texte_fenetre = []
            mots_fenetre = []
            segments_fenetre = []

    # Dernière fenêtre (si assez longue)
    if texte_fenetre and segments_fenetre:
        derniere_fin = segments_fenetre[-1]["fin"]
        if derniere_fin - debut_fenetre >= 5:  # Au moins 5 secondes
            fenetres.append({
                "debut": debut_fenetre,
                "fin": derniere_fin,
                "texte": " ".join(texte_fenetre),
                "mots": mots_fenetre,
                "segments_source": segments_fenetre
            })

    return fenetres
