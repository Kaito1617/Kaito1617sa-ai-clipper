"""
transcriber.py — Transcription audio avec faster-whisper
Utilise le GPU NVIDIA (CUDA) pour une transcription rapide.
Retourne le texte complet + les timecodes mot par mot.
"""

import os
import logging
from typing import Optional, Callable
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)


def transcrire_video(
    chemin_video: str,
    modele: str = "medium",
    langue: Optional[str] = None,
    callback_progression: Optional[Callable] = None
) -> dict:
    """
    Transcrit l'audio d'une vidéo et retourne le texte avec les timecodes.

    Args:
        chemin_video: Chemin vers le fichier vidéo
        modele: Taille du modèle Whisper ('tiny', 'base', 'small', 'medium', 'large-v3')
        langue: Langue forcée (ex: 'fr', 'en', 'ja'). None = détection auto
        callback_progression: Fonction appelée avec (étape, pourcentage)

    Returns:
        dict avec:
            - 'texte_complet': str (transcription entière)
            - 'segments': list de dicts {'debut', 'fin', 'texte', 'mots'}
            - 'mots': list de dicts {'mot', 'debut', 'fin', 'probabilite'}
            - 'langue': str (langue détectée)
    """
    if not os.path.exists(chemin_video):
        raise FileNotFoundError(f"Vidéo introuvable : {chemin_video}")

    logger.info(f"Chargement du modèle Whisper ({modele})...")
    if callback_progression:
        callback_progression("Chargement du modèle Whisper", 5)

    # Chargement du modèle — GPU CUDA en priorité, sinon CPU
    try:
        modele_whisper = WhisperModel(
            modele,
            device="cuda",
            compute_type="float16"  # Optimisé RTX 5070
        )
        logger.info("Modèle chargé sur GPU (CUDA)")
    except Exception as e:
        logger.warning(f"GPU non disponible ({e}), utilisation du CPU")
        modele_whisper = WhisperModel(
            modele,
            device="cpu",
            compute_type="int8"  # Plus rapide sur CPU
        )

    if callback_progression:
        callback_progression("Transcription en cours...", 10)

    logger.info(f"Transcription de : {chemin_video}")

    # Options de transcription
    options = {
        "word_timestamps": True,  # Timecodes mot par mot
        "vad_filter": True,       # Filtre silence (Voice Activity Detection)
        "vad_parameters": {
            "min_silence_duration_ms": 500
        }
    }
    if langue:
        options["language"] = langue

    # Lancement de la transcription
    segments_gen, infos = modele_whisper.transcribe(chemin_video, **options)

    # Conversion du générateur en liste (avec progression)
    segments = []
    tous_les_mots = []
    texte_complet_parts = []

    for i, segment in enumerate(segments_gen):
        # Données du segment
        donnees_segment = {
            "debut": round(segment.start, 3),
            "fin": round(segment.end, 3),
            "texte": segment.text.strip(),
            "mots": []
        }

        # Mots avec timecodes
        if segment.words:
            for mot in segment.words:
                donnees_mot = {
                    "mot": mot.word.strip(),
                    "debut": round(mot.start, 3),
                    "fin": round(mot.end, 3),
                    "probabilite": round(mot.probability, 3)
                }
                donnees_segment["mots"].append(donnees_mot)
                tous_les_mots.append(donnees_mot)

        segments.append(donnees_segment)
        texte_complet_parts.append(segment.text.strip())

        # Mise à jour progression (10% à 90%)
        if callback_progression and i % 10 == 0:
            callback_progression(f"Transcription segment {i+1}...", min(90, 10 + i * 2))

    texte_complet = " ".join(texte_complet_parts)
    langue_detectee = infos.language if hasattr(infos, 'language') else "unknown"

    logger.info(f"Transcription terminée. {len(segments)} segments, {len(tous_les_mots)} mots. Langue : {langue_detectee}")

    if callback_progression:
        callback_progression("Transcription terminée", 100)

    return {
        "texte_complet": texte_complet,
        "segments": segments,
        "mots": tous_les_mots,
        "langue": langue_detectee
    }
