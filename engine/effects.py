"""
effects.py — Effets visuels pour les Shorts
Recadrage dynamique 9:16, zoom progressif, shake effect, transitions.
Utilise FFmpeg pour le rendu final haute performance.
"""

import os
import subprocess
import logging
import json
import math
import tempfile
from typing import List, Optional, Callable

logger = logging.getLogger(__name__)

# Résolution cible YouTube Shorts (9:16)
LARGEUR_SHORT = 1080
HAUTEUR_SHORT = 1920

# Résolution cible paysage (16:9)
LARGEUR_PAYSAGE = 1920
HAUTEUR_PAYSAGE = 1080


def appliquer_effets(
    chemin_video: str,
    debut: float,
    fin: float,
    zones_detection: list,
    config_mode: dict,
    intensite: str,
    chemin_sortie: str,
    callback_progression: Optional[Callable] = None,
    format_sortie: str = "portrait"
) -> bool:
    """
    Applique tous les effets visuels sur un segment et l'exporte.

    Args:
        chemin_video: Vidéo source
        debut: Début du segment (secondes)
        fin: Fin du segment (secondes)
        zones_detection: Données de détection YOLO
        config_mode: Config du mode actif
        intensite: 'leger', 'normal' ou 'intense'
        chemin_sortie: Fichier de sortie (sans sous-titres)
        format_sortie: 'portrait' (9:16) ou 'paysage' (16:9)

    Returns:
        True si succès
    """
    duree = fin - debut
    logger.info(f"Application des effets [{debut:.1f}s - {fin:.1f}s] intensité={intensite} format={format_sortie}")

    # Facteurs d'intensité réduits pour un rendu plus pro
    facteurs = {"leger": 0.3, "normal": 0.7, "intense": 1.0}
    facteur = facteurs.get(intensite, 0.7)

    # Config effets du mode
    config_effets = config_mode.get("effets", {})

    if format_sortie == "paysage":
        # Mode 16:9 : effets très subtils, pas de crop agressif
        zoom_max = config_effets.get("zoom_max", 1.05) * min(facteur, 1.0)
        zoom_max = min(zoom_max, 1.05)  # Jamais plus de 1.05x en paysage
        activer_shake = config_effets.get("shake", True) and intensite == "intense"
        amplitude_shake = config_effets.get("amplitude_shake", 8) * facteur / 4
    else:
        # Mode portrait 9:16 : zoom réduit par rapport à l'ancienne valeur
        zoom_max = config_effets.get("zoom_max", 1.15) * facteur
        zoom_max = min(zoom_max, 1.5)  # Limite plus basse qu'avant
        activer_shake = config_effets.get("shake", True) and intensite != "leger"
        amplitude_shake = config_effets.get("amplitude_shake", 4) * facteur

    # Calcul du centre de recadrage (utilisé uniquement en portrait)
    cx_ratio, cy_ratio = _calculer_centre_optimal(zones_detection, config_mode)

    # Filtres FFmpeg
    filtres = _construire_filtres_ffmpeg(
        debut=debut,
        duree=duree,
        cx_ratio=cx_ratio,
        cy_ratio=cy_ratio,
        zoom_max=zoom_max,
        activer_shake=activer_shake,
        amplitude_shake=amplitude_shake,
        config_mode=config_mode,
        intensite=intensite,
        format_sortie=format_sortie
    )

    # Commande FFmpeg avec accélération NVENC si disponible
    cmd = _construire_commande_ffmpeg(
        chemin_video=chemin_video,
        debut=debut,
        duree=duree,
        filtres=filtres,
        chemin_sortie=chemin_sortie,
        format_sortie=format_sortie
    )

    try:
        resultat = subprocess.run(cmd, capture_output=True, timeout=300)
        if resultat.returncode != 0:
            logger.error(f"FFmpeg erreur: {resultat.stderr.decode('utf-8', errors='replace')[-500:]}")
            # Retry sans accélération GPU
            cmd_cpu = _construire_commande_ffmpeg(
                chemin_video=chemin_video,
                debut=debut,
                duree=duree,
                filtres=filtres,
                chemin_sortie=chemin_sortie,
                force_cpu=True,
                format_sortie=format_sortie
            )
            resultat2 = subprocess.run(cmd_cpu, capture_output=True, timeout=300)
            if resultat2.returncode != 0:
                logger.error(f"FFmpeg CPU erreur: {resultat2.stderr.decode('utf-8', errors='replace')[-500:]}")
                return False
        logger.info(f"Effets appliqués : {chemin_sortie}")
        return True
    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout (> 5 minutes)")
        return False
    except Exception as e:
        logger.error(f"Erreur effets : {e}")
        return False


def _calculer_centre_optimal(zones_detection: list, config_mode: dict) -> tuple:
    """
    Calcule le ratio cx/cy optimal pour le recadrage selon les détections YOLO.
    Retourne (cx_ratio, cy_ratio) entre 0 et 1.
    """
    if not zones_detection:
        return 0.5, 0.4  # Légèrement vers le haut par défaut

    # Filtrer les détections fiables
    bonnes_detections = [z for z in zones_detection if z.get("confiance", 0) > 0.4]
    if not bonnes_detections:
        return 0.5, 0.4

    # Prendre la détection avec la meilleure confiance
    meilleure = max(bonnes_detections, key=lambda z: z.get("confiance", 0))
    centre = meilleure.get("centre", (0.5, 0.5))

    # Si le centre est une paire de coordonnées normalisées
    if isinstance(centre, tuple) and len(centre) == 2:
        cx, cy = centre
        # Si valeurs > 1, c'est en pixels — normaliser approximativement
        if cx > 1 or cy > 1:
            return 0.5, 0.4
        return cx, cy

    return 0.5, 0.4


def _construire_filtres_ffmpeg(
    debut: float,
    duree: float,
    cx_ratio: float,
    cy_ratio: float,
    zoom_max: float,
    activer_shake: bool,
    amplitude_shake: float,
    config_mode: dict,
    intensite: str,
    format_sortie: str = "portrait"
) -> str:
    """
    Construit la chaîne de filtres FFmpeg pour le recadrage et les effets.
    """
    filtres = []

    if format_sortie == "paysage":
        # Mode 16:9 : pas de crop, juste redimensionner en 1920x1080 max
        filtres.append(f"scale={LARGEUR_PAYSAGE}:{HAUTEUR_PAYSAGE}:force_original_aspect_ratio=decrease:flags=lanczos")
        filtres.append(f"pad={LARGEUR_PAYSAGE}:{HAUTEUR_PAYSAGE}:(ow-iw)/2:(oh-ih)/2")
    else:
        # Mode portrait 9:16 : recadrage avec suivi du sujet
        crop_largeur = "min(iw\\,ih*9/16)"
        crop_hauteur = "min(ih\\,iw*16/9)"
        crop_filter = (
            f"crop="
            f"{crop_largeur}:"             # largeur = hauteur * 9/16
            f"{crop_hauteur}:"             # hauteur = largeur * 16/9
            f"(iw-{crop_largeur})*{cx_ratio:.3f}:"   # position X selon cx_ratio
            f"(ih-{crop_hauteur})*{cy_ratio:.3f}"    # position Y selon cy_ratio
        )
        filtres.append(crop_filter)

        # Redimensionnement vers 1080x1920
        filtres.append(f"scale={LARGEUR_SHORT}:{HAUTEUR_SHORT}:flags=lanczos")

    # Résolution de sortie selon le format
    largeur_out = LARGEUR_PAYSAGE if format_sortie == "paysage" else LARGEUR_SHORT
    hauteur_out = HAUTEUR_PAYSAGE if format_sortie == "paysage" else HAUTEUR_SHORT

    # Zoom progressif sur les moments intenses
    if zoom_max > 1.05:
        duree_zoom = min(duree, 3.0)  # Max 3 secondes de zoom
        zoom_expr = (
            f"zoompan="
            f"z='if(lte(on\\,{duree_zoom*25:.0f})"
            f"\\,1+({zoom_max-1:.3f}*on/{duree_zoom*25:.0f})"
            f"\\,{zoom_max:.3f})':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:fps=25:s={largeur_out}x{hauteur_out}"
        )
        filtres.append(zoom_expr)

    # Shake effect sur les moments intenses
    if activer_shake and amplitude_shake > 0:
        amp = int(amplitude_shake)
        shake_expr = (
            f"crop={largeur_out-amp*2}:{hauteur_out-amp*2}:"
            f"'random(1)*{amp}':"
            f"'random(2)*{amp}',"
            f"scale={largeur_out}:{hauteur_out}"
        )
        filtres.append(shake_expr)

    # Transition fade in/out
    fade_duree = 0.3
    filtres.append(
        f"fade=t=in:st=0:d={fade_duree},"
        f"fade=t=out:st={max(0, duree-fade_duree):.3f}:d={fade_duree}"
    )

    return ",".join(filtres)


def _construire_commande_ffmpeg(
    chemin_video: str,
    debut: float,
    duree: float,
    filtres: str,
    chemin_sortie: str,
    force_cpu: bool = False,
    format_sortie: str = "portrait"
) -> list:
    """
    Construit la commande FFmpeg complète avec accélération NVENC si disponible.
    """
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(debut),
        "-i", chemin_video,
        "-t", str(duree),
        "-vf", filtres,
    ]

    if not force_cpu:
        # Accélération GPU NVENC (RTX 5070)
        cmd += [
            "-c:v", "h264_nvenc",
            "-preset", "p4",          # Équilibre qualité/vitesse
            "-rc", "vbr",
            "-cq", "23",
            "-b:v", "8M",
            "-maxrate", "16M",
            "-bufsize", "32M",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
        ]
    else:
        # Encodage CPU libx264
        cmd += [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
        ]

    cmd += [
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",
        chemin_sortie
    ]

    return cmd
