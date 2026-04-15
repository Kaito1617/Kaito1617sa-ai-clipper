"""
clipper.py — Sélection et découpe intelligente des meilleurs moments
Sélectionne les top N moments selon le score, évite les doublons,
et découpe les segments avec une marge avant/après.
"""

import logging
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)


def selectionner_meilleurs_moments(
    segments_scores: List[dict],
    nb_shorts: int,
    duree_short: int,
    config_mode: dict
) -> List[dict]:
    """
    Sélectionne les meilleurs moments pour créer des Shorts.

    Args:
        segments_scores: Liste de segments avec scores (de analyzer.py)
        nb_shorts: Nombre de Shorts voulus
        duree_short: Durée cible en secondes (30, 45 ou 60)
        config_mode: Configuration du mode

    Returns:
        Liste des moments sélectionnés avec 'debut_final' et 'fin_final'
    """
    logger.info(f"Sélection des {nb_shorts} meilleurs moments ({duree_short}s chacun)")

    distance_minimale = config_mode.get("distance_minimale_segments", 30)  # secondes
    marge_avant = config_mode.get("marge_avant", 2.0)   # secondes avant le moment
    marge_apres = config_mode.get("marge_apres", 2.0)   # secondes après le moment

    moments_selectionnes = []

    for candidat in segments_scores:
        if len(moments_selectionnes) >= nb_shorts:
            break

        # Vérification : pas trop proche d'un moment déjà sélectionné
        trop_proche = False
        for moment in moments_selectionnes:
            # Chevauchement ou proximité trop grande
            if (abs(candidat["debut"] - moment["debut"]) < distance_minimale or
                    _segments_se_chevauchent(candidat, moment)):
                trop_proche = True
                break

        if trop_proche:
            continue

        # Calcul des bornes du short avec marge
        debut_moment = max(0, candidat["debut"] - marge_avant)
        fin_moment = candidat["fin"] + marge_apres

        # Ajustement pour atteindre la durée cible
        duree_actuelle = fin_moment - debut_moment
        if duree_actuelle < duree_short:
            # Étendre symétriquement
            manque = duree_short - duree_actuelle
            debut_moment = max(0, debut_moment - manque / 2)
            fin_moment = fin_moment + manque / 2

        # Limiter à la durée cible (centré sur le moment fort)
        if fin_moment - debut_moment > duree_short:
            centre = (candidat["debut"] + candidat["fin"]) / 2
            debut_moment = max(0, centre - duree_short / 2)
            fin_moment = debut_moment + duree_short

        moment_final = candidat.copy()
        moment_final["debut_final"] = round(debut_moment, 3)
        moment_final["fin_final"] = round(fin_moment, 3)
        moment_final["duree_finale"] = round(fin_moment - debut_moment, 3)

        moments_selectionnes.append(moment_final)
        logger.info(
            f"  ✓ Moment {len(moments_selectionnes)}: "
            f"[{debut_moment:.1f}s - {fin_moment:.1f}s] "
            f"score={candidat.get('score_final', 0):.0f}/100"
        )

    logger.info(f"{len(moments_selectionnes)} moments sélectionnés")
    return moments_selectionnes


def _segments_se_chevauchent(seg1: dict, seg2: dict) -> bool:
    """Vérifie si deux segments se chevauchent."""
    debut1 = seg1.get("debut_final", seg1["debut"])
    fin1 = seg1.get("fin_final", seg1["fin"])
    debut2 = seg2.get("debut_final", seg2["debut"])
    fin2 = seg2.get("fin_final", seg2["fin"])
    return not (fin1 <= debut2 or fin2 <= debut1)


def extraire_segment_ffmpeg(
    chemin_video: str,
    debut: float,
    fin: float,
    chemin_sortie: str
) -> bool:
    """
    Extrait un segment de la vidéo avec FFmpeg (sans ré-encodage = rapide).

    Returns:
        True si succès, False sinon
    """
    import subprocess
    duree = fin - debut

    cmd = [
        "ffmpeg", "-y",
        "-ss", str(debut),
        "-i", chemin_video,
        "-t", str(duree),
        "-c", "copy",           # Pas de ré-encodage (rapide)
        "-avoid_negative_ts", "make_zero",
        chemin_sortie
    ]

    try:
        subprocess.run(cmd, capture_output=True, check=True)
        logger.info(f"Segment extrait : {chemin_sortie}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Erreur extraction segment : {e.stderr.decode()}")
        return False
