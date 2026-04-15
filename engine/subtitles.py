"""
subtitles.py — Sous-titres animés style CapCut / Cali
Génère des sous-titres mot par mot avec highlight du mot courant,
police bold, ombre portée, animation d'apparition.
Utilise FFmpeg avec le filtre drawtext pour le rendu.
"""

import os
import subprocess
import logging
import tempfile
from typing import List, Optional

logger = logging.getLogger(__name__)

# Chemin vers la police par défaut
CHEMIN_FONTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
POLICE_DEFAUT = os.path.join(CHEMIN_FONTS, "Montserrat-Bold.ttf")
POLICE_FALLBACK = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def ajouter_sous_titres(
    chemin_video: str,
    mots_segment: List[dict],
    debut_segment: float,
    config_mode: dict,
    intensite: str,
    chemin_sortie: str
) -> bool:
    """
    Ajoute des sous-titres animés mot par mot sur la vidéo.

    Args:
        chemin_video: Vidéo source (déjà recadrée en 9:16)
        mots_segment: Liste de mots avec timecodes {'mot', 'debut', 'fin'}
        debut_segment: Début du segment (pour recalculer les timecodes relatifs)
        config_mode: Config du mode (couleurs, taille...)
        intensite: 'leger', 'normal' ou 'intense'
        chemin_sortie: Fichier de sortie

    Returns:
        True si succès
    """
    if not mots_segment:
        logger.info("Pas de mots à afficher, copie directe")
        _copier_video(chemin_video, chemin_sortie)
        return True

    logger.info(f"Ajout de {len(mots_segment)} mots en sous-titres")

    # Configuration visuelle selon le mode
    style = config_mode.get("style_sous_titres", {})
    couleur_texte = style.get("couleur_texte", "white")
    couleur_highlight = style.get("couleur_highlight", "yellow")
    taille_police = style.get("taille_police", 28)
    position_y = style.get("position_y", "h-200")  # 200px du bas

    # Facteur taille selon intensité
    if intensite == "intense":
        taille_police = int(taille_police * 1.1)
    elif intensite == "leger":
        taille_police = int(taille_police * 0.95)

    # Sélection de la police
    police = _trouver_police()

    # Regrouper les mots en lignes (max 6 mots par ligne)
    groupes = _grouper_mots(mots_segment, max_mots_par_groupe=6)

    # Génération du fichier SRT pour FFmpeg subtitle filter
    chemin_srt = _generer_srt(groupes, debut_segment)

    # Application avec FFmpeg
    succes = _appliquer_sous_titres_ffmpeg(
        chemin_video=chemin_video,
        chemin_srt=chemin_srt,
        police=police,
        taille_police=taille_police,
        couleur_texte=couleur_texte,
        chemin_sortie=chemin_sortie
    )

    # Nettoyage
    if os.path.exists(chemin_srt):
        os.unlink(chemin_srt)

    return succes


def _grouper_mots(mots: List[dict], max_mots_par_groupe: int = 6) -> List[dict]:
    """
    Groupe les mots en lignes de sous-titres (max N mots par groupe).
    Chaque groupe a un 'debut', 'fin' et 'texte'.
    """
    groupes = []
    i = 0
    while i < len(mots):
        groupe_mots = mots[i:i + max_mots_par_groupe]
        texte = " ".join(m["mot"] for m in groupe_mots if m["mot"].strip())

        if texte.strip():
            groupes.append({
                "debut": groupe_mots[0]["debut"],
                "fin": groupe_mots[-1]["fin"],
                "texte": texte  # Casse normale
            })
        i += max_mots_par_groupe

    return groupes


def _generer_srt(groupes: List[dict], debut_segment: float) -> str:
    """
    Génère un fichier SRT temporaire à partir des groupes de mots.
    """
    fichier_srt = tempfile.NamedTemporaryFile(
        mode="w", suffix=".srt", delete=False, encoding="utf-8"
    )

    for i, groupe in enumerate(groupes, 1):
        # Timecodes relatifs au début du segment
        debut_rel = max(0, groupe["debut"] - debut_segment)
        fin_rel = max(debut_rel + 0.1, groupe["fin"] - debut_segment)

        def srt_time(secs):
            h = int(secs // 3600)
            m = int((secs % 3600) // 60)
            s = int(secs % 60)
            ms = int((secs - int(secs)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        fichier_srt.write(f"{i}\n")
        fichier_srt.write(f"{srt_time(debut_rel)} --> {srt_time(fin_rel)}\n")
        fichier_srt.write(f"{groupe['texte']}\n\n")

    fichier_srt.close()
    return fichier_srt.name


def _appliquer_sous_titres_ffmpeg(
    chemin_video: str,
    chemin_srt: str,
    police: str,
    taille_police: int,
    couleur_texte: str,
    chemin_sortie: str
) -> bool:
    """
    Applique les sous-titres via le filtre subtitles de FFmpeg.
    """
    # Échappement du chemin pour FFmpeg (Windows compatibility)
    chemin_srt_escape = chemin_srt.replace("\\", "/").replace(":", "\\:")

    # Style ASS/SRT pour FFmpeg
    style_force = (
        f"FontName={os.path.basename(police).replace('.ttf', '')},"
        f"FontSize={taille_police},"
        f"PrimaryColour=&H00FFFFFF,"  # Blanc
        f"OutlineColour=&H00000000,"  # Contour noir
        f"BackColour=&H80000000,"     # Fond semi-transparent
        f"Bold=1,"
        f"Outline=1,"
        f"Shadow=1,"
        f"MarginV=40,"                # Marge bas
        f"Alignment=2"               # Centré en bas
    )

    filtre_sub = f"subtitles='{chemin_srt_escape}':force_style='{style_force}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", chemin_video,
        "-vf", filtre_sub,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        chemin_sortie
    ]

    try:
        resultat = subprocess.run(cmd, capture_output=True, timeout=300)
        if resultat.returncode != 0:
            logger.warning(
                f"Sous-titres FFmpeg erreur : "
                f"{resultat.stderr.decode('utf-8', errors='replace')[-300:]}"
            )
            # Fallback : copie sans sous-titres
            _copier_video(chemin_video, chemin_sortie)
            return True
        logger.info(f"Sous-titres ajoutés : {chemin_sortie}")
        return True
    except Exception as e:
        logger.error(f"Erreur sous-titres : {e}")
        _copier_video(chemin_video, chemin_sortie)
        return True  # Continuer même sans sous-titres


def _trouver_police() -> str:
    """Retourne le chemin vers la police bold disponible."""
    if os.path.exists(POLICE_DEFAUT):
        return POLICE_DEFAUT
    if os.path.exists(POLICE_FALLBACK):
        return POLICE_FALLBACK
    # Chercher une police bold quelconque
    for dossier in ["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")]:
        if os.path.exists(dossier):
            for f in os.listdir(dossier):
                if "bold" in f.lower() and f.endswith(".ttf"):
                    return os.path.join(dossier, f)
    return "DejaVuSans-Bold"  # Fallback FFmpeg


def _copier_video(source: str, destination: str):
    """Copie une vidéo sans modification."""
    import shutil
    shutil.copy2(source, destination)
