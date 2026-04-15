"""
exporter.py — Assemblage final et export des Shorts
Combine tous les éléments (effets visuels + sous-titres + sound design)
et exporte en MP4 H.264 1080x1920 (9:16) prêt pour YouTube Shorts.
"""

import os
import logging
import shutil
import tempfile
import zipfile
from typing import List, Optional, Callable

from engine.effects import appliquer_effets
from engine.subtitles import ajouter_sous_titres
from engine.sound_design import appliquer_sound_design, choisir_musique_fond
from engine.detector import detecter_zones_interet, obtenir_dimensions_video

logger = logging.getLogger(__name__)


def exporter_shorts(
    chemin_video: str,
    moments: List[dict],
    transcription: dict,
    mode: str,
    config_mode: dict,
    intensite: str,
    dossier_sortie: str,
    task_id: str,
    callback_progression: Optional[Callable] = None,
    format_sortie: str = "portrait"
) -> List[dict]:
    """
    Pipeline d'export complet pour tous les Shorts sélectionnés.

    Args:
        chemin_video: Vidéo source
        moments: Liste des moments sélectionnés (de clipper.py)
        transcription: Données de transcription (de transcriber.py)
        mode: Mode actif ('football', 'anime', 'streamer')
        config_mode: Config du mode
        intensite: 'leger', 'normal' ou 'intense'
        dossier_sortie: Dossier où sauvegarder les Shorts
        task_id: Identifiant de la tâche (pour le nommage)
        callback_progression: Callback de progression

    Returns:
        Liste de dicts {'numero', 'chemin', 'nom_fichier', 'duree'}
    """
    os.makedirs(dossier_sortie, exist_ok=True)
    shorts_generes = []
    musique_fond = choisir_musique_fond(mode)

    if musique_fond:
        logger.info(f"Musique de fond : {musique_fond}")

    for i, moment in enumerate(moments):
        numero = i + 1
        logger.info(f"\n=== Export Short {numero}/{len(moments)} ===")

        if callback_progression:
            pourcentage = int((i / len(moments)) * 100)
            callback_progression(f"Export Short {numero}/{len(moments)}...", pourcentage)

        nom_fichier = f"{mode}_short_{numero}.mp4"
        chemin_final = os.path.join(dossier_sortie, nom_fichier)

        # Répertoire temporaire pour ce short
        dossier_temp = tempfile.mkdtemp(prefix=f"short_{task_id}_{numero}_")

        try:
            succes = _exporter_un_short(
                chemin_video=chemin_video,
                moment=moment,
                transcription=transcription,
                mode=mode,
                config_mode=config_mode,
                intensite=intensite,
                musique_fond=musique_fond,
                chemin_sortie=chemin_final,
                dossier_temp=dossier_temp,
                numero=numero,
                format_sortie=format_sortie
            )

            if succes and os.path.exists(chemin_final):
                taille = os.path.getsize(chemin_final)
                shorts_generes.append({
                    "numero": numero,
                    "chemin": chemin_final,
                    "nom_fichier": nom_fichier,
                    "duree": round(moment.get("duree_finale", moment["fin_final"] - moment["debut_final"]), 1),
                    "score": round(moment.get("score_final", 0), 1),
                    "taille_octets": taille
                })
                logger.info(f"✓ Short {numero} généré : {nom_fichier} ({taille // 1024} Ko)")
            else:
                logger.error(f"✗ Échec export Short {numero}")

        except Exception as e:
            logger.error(f"Erreur export Short {numero} : {e}", exc_info=True)
        finally:
            # Nettoyage des fichiers temporaires
            if os.path.exists(dossier_temp):
                shutil.rmtree(dossier_temp, ignore_errors=True)

    logger.info(f"\n=== {len(shorts_generes)}/{len(moments)} Shorts exportés ===")

    if callback_progression:
        callback_progression("Export terminé !", 100)

    return shorts_generes


def _exporter_un_short(
    chemin_video: str,
    moment: dict,
    transcription: dict,
    mode: str,
    config_mode: dict,
    intensite: str,
    musique_fond: Optional[str],
    chemin_sortie: str,
    dossier_temp: str,
    numero: int,
    format_sortie: str = "portrait"
) -> bool:
    """
    Exporte un seul Short en appliquant le pipeline complet :
    1. Effets visuels (recadrage 9:16, zoom, shake)
    2. Sous-titres animés
    3. Sound design (bass boost, SFX, musique)
    """
    debut = moment["debut_final"]
    fin = moment["fin_final"]

    # ─── Étape 1 : Détection YOLO du sujet ───
    logger.info(f"  → Détection visuelle...")
    largeur, hauteur, fps = obtenir_dimensions_video(chemin_video)
    zones_detection = detecter_zones_interet(chemin_video, debut, fin, config_mode)

    # ─── Étape 2 : Effets visuels + recadrage 9:16 ───
    logger.info(f"  → Effets visuels (recadrage 9:16, zoom, transitions)...")
    chemin_avec_effets = os.path.join(dossier_temp, "step1_effets.mp4")
    succes = appliquer_effets(
        chemin_video=chemin_video,
        debut=debut,
        fin=fin,
        zones_detection=zones_detection,
        config_mode=config_mode,
        intensite=intensite,
        chemin_sortie=chemin_avec_effets,
        format_sortie=format_sortie
    )

    if not succes or not os.path.exists(chemin_avec_effets):
        logger.error("  ✗ Échec effets visuels")
        return False

    # ─── Étape 3 : Sous-titres animés ───
    logger.info(f"  → Sous-titres animés...")
    # Extraire les mots du segment
    mots_segment = _extraire_mots_segment(transcription, debut, fin)
    chemin_avec_subs = os.path.join(dossier_temp, "step2_subs.mp4")
    ajouter_sous_titres(
        chemin_video=chemin_avec_effets,
        mots_segment=mots_segment,
        debut_segment=debut,
        config_mode=config_mode,
        intensite=intensite,
        chemin_sortie=chemin_avec_subs,
        format_sortie=format_sortie
    )

    source_pour_audio = chemin_avec_subs if os.path.exists(chemin_avec_subs) else chemin_avec_effets

    # ─── Étape 4 : Sound design ───
    logger.info(f"  → Sound design...")
    appliquer_sound_design(
        chemin_video=source_pour_audio,
        config_mode=config_mode,
        intensite=intensite,
        debut_segment=debut,
        fin_segment=fin,
        chemin_sortie=chemin_sortie,
        musique_fond=musique_fond
    )

    return os.path.exists(chemin_sortie) and os.path.getsize(chemin_sortie) > 0


def _extraire_mots_segment(transcription: dict, debut: float, fin: float) -> list:
    """
    Extrait les mots du transcript qui appartiennent à ce segment.
    """
    mots = transcription.get("mots", [])
    return [
        m for m in mots
        if debut <= m.get("debut", 0) <= fin
    ]


def creer_archive_zip(shorts: List[dict], chemin_zip: str) -> bool:
    """
    Crée un ZIP contenant tous les Shorts générés.

    Args:
        shorts: Liste des Shorts générés (de exporter_shorts)
        chemin_zip: Chemin du fichier ZIP de sortie

    Returns:
        True si succès
    """
    try:
        with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for short in shorts:
                if os.path.exists(short["chemin"]):
                    zf.write(short["chemin"], short["nom_fichier"])
                    logger.info(f"Ajouté au ZIP : {short['nom_fichier']}")
        logger.info(f"Archive ZIP créée : {chemin_zip}")
        return True
    except Exception as e:
        logger.error(f"Erreur création ZIP : {e}")
        return False
