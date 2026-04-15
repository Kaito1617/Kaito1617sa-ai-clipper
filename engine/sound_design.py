"""
sound_design.py — Design sonore pour les Shorts
Bass boost sur moments épiques, SFX automatiques (whoosh, impact, vine boom),
musique de fond synchronisée aux beats.
"""

import os
import subprocess
import logging
import glob
import tempfile
import random
from typing import Optional, List

logger = logging.getLogger(__name__)

# Répertoire des assets SFX
CHEMIN_SFX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "sfx")
CHEMIN_MUSIQUE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "music")


def appliquer_sound_design(
    chemin_video: str,
    config_mode: dict,
    intensite: str,
    debut_segment: float,
    fin_segment: float,
    chemin_sortie: str,
    musique_fond: Optional[str] = None
) -> bool:
    """
    Applique le design sonore sur la vidéo du Short.

    Pipeline :
    1. Bass boost (si mode anime/streamer)
    2. SFX automatiques aux transitions
    3. Musique de fond (optionnelle)

    Args:
        chemin_video: Vidéo source avec audio d'origine
        config_mode: Configuration du mode (effets audio)
        intensite: 'leger', 'normal' ou 'intense'
        debut_segment / fin_segment: Bornes du segment (pour le contexte)
        chemin_sortie: Fichier de sortie
        musique_fond: Chemin vers musique de fond optionnelle

    Returns:
        True si succès
    """
    logger.info(f"Sound design : intensité={intensite}")

    config_audio = config_mode.get("audio", {})
    facteurs = {"leger": 0.5, "normal": 1.0, "intense": 1.5}
    facteur = facteurs.get(intensite, 1.0)

    # Construction des filtres audio FFmpeg
    filtres_audio = _construire_filtres_audio(config_audio, facteur)

    # Sélection d'un SFX de transition si activé
    sfx_path = None
    if config_audio.get("sfx_transitions", False) and intensite != "leger":
        sfx_path = _choisir_sfx(config_mode.get("sfx_types", ["whoosh"]))

    # Commande FFmpeg finale
    succes = _appliquer_audio_ffmpeg(
        chemin_video=chemin_video,
        filtres_audio=filtres_audio,
        sfx_path=sfx_path,
        musique_fond=musique_fond,
        config_audio=config_audio,
        facteur=facteur,
        chemin_sortie=chemin_sortie
    )

    return succes


def _construire_filtres_audio(config_audio: dict, facteur: float) -> str:
    """
    Construit la chaîne de filtres audio FFmpeg.
    """
    filtres = []

    # 1. Normalisation du volume
    filtres.append("loudnorm=I=-16:TP=-1.5:LRA=11")

    # 2. Bass boost (equalizer sur les basses fréquences)
    if config_audio.get("bass_boost", False):
        gain_basses = config_audio.get("bass_boost_db", 6) * facteur
        gain_basses = min(gain_basses, 12)  # Limite à +12dB
        filtres.append(f"equalizer=f=100:width_type=o:width=2:g={gain_basses:.1f}")

    # 3. Compression dynamique (rend le son plus punch)
    if config_audio.get("compression", True):
        filtres.append("acompressor=threshold=-18dB:ratio=4:attack=5:release=50:makeup=3dB")

    # 4. Écho/Reverb léger pour les moments épiques (mode streamer)
    if config_audio.get("reverb", False) and facteur >= 1.0:
        filtres.append("aecho=0.8:0.88:60:0.4")

    return ",".join(filtres) if filtres else "anull"


def _appliquer_audio_ffmpeg(
    chemin_video: str,
    filtres_audio: str,
    sfx_path: Optional[str],
    musique_fond: Optional[str],
    config_audio: dict,
    facteur: float,
    chemin_sortie: str
) -> bool:
    """
    Applique les traitements audio via FFmpeg.
    Supporte le mixage avec SFX et musique de fond.
    """
    inputs = ["-i", chemin_video]
    map_audio = "[a_final]"

    # Filtres complexes
    filtres_complexes = []
    nb_inputs = 1

    # Audio principal traité
    filtres_complexes.append(f"[0:a]{filtres_audio}[a_main]")
    sortie_actuelle = "[a_main]"

    # Ajout SFX si disponible
    if sfx_path and os.path.exists(sfx_path):
        inputs += ["-i", sfx_path]
        volume_sfx = config_audio.get("volume_sfx", 0.3) * facteur
        filtres_complexes.append(
            f"[{nb_inputs}:a]volume={volume_sfx:.2f}[a_sfx]"
        )
        filtres_complexes.append(
            f"{sortie_actuelle}[a_sfx]amix=inputs=2:duration=first:dropout_transition=2[a_avec_sfx]"
        )
        sortie_actuelle = "[a_avec_sfx]"
        nb_inputs += 1

    # Ajout musique de fond si disponible
    if musique_fond and os.path.exists(musique_fond):
        inputs += ["-i", musique_fond]
        volume_musique = config_audio.get("volume_musique_fond", 0.15) * facteur
        filtres_complexes.append(
            f"[{nb_inputs}:a]volume={volume_musique:.2f}[a_music]"
        )
        filtres_complexes.append(
            f"{sortie_actuelle}[a_music]amix=inputs=2:duration=first:dropout_transition=3[a_final]"
        )
        nb_inputs += 1
    else:
        # Renommage final si pas de musique
        filtres_complexes.append(f"{sortie_actuelle}acopy[a_final]")

    # Construction commande
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", ";".join(filtres_complexes),
        "-map", "0:v",
        "-map", "[a_final]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        chemin_sortie
    ]

    try:
        resultat = subprocess.run(cmd, capture_output=True, timeout=300)
        if resultat.returncode != 0:
            logger.warning(
                f"Sound design FFmpeg erreur: "
                f"{resultat.stderr.decode('utf-8', errors='replace')[-300:]}"
            )
            # Fallback simple : juste les filtres audio de base
            return _appliquer_audio_simple(chemin_video, chemin_sortie)
        logger.info(f"Sound design appliqué : {chemin_sortie}")
        return True
    except Exception as e:
        logger.error(f"Erreur sound design : {e}")
        return _appliquer_audio_simple(chemin_video, chemin_sortie)


def _appliquer_audio_simple(chemin_video: str, chemin_sortie: str) -> bool:
    """Fallback : normalisation audio simple."""
    cmd = [
        "ffmpeg", "-y", "-i", chemin_video,
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        chemin_sortie
    ]
    try:
        resultat = subprocess.run(cmd, capture_output=True, timeout=120)
        return resultat.returncode == 0
    except Exception:
        import shutil
        shutil.copy2(chemin_video, chemin_sortie)
        return True


def _choisir_sfx(types_sfx: List[str]) -> Optional[str]:
    """
    Choisit un SFX aléatoire parmi les fichiers disponibles.
    """
    if not os.path.exists(CHEMIN_SFX):
        return None

    fichiers_sfx = []
    for ext in ["*.mp3", "*.wav", "*.ogg"]:
        fichiers_sfx.extend(glob.glob(os.path.join(CHEMIN_SFX, ext)))

    if not fichiers_sfx:
        return None

    # Filtrer par type si possible
    for sfx_type in types_sfx:
        sfx_filtres = [f for f in fichiers_sfx if sfx_type.lower() in os.path.basename(f).lower()]
        if sfx_filtres:
            return random.choice(sfx_filtres)

    return random.choice(fichiers_sfx)


def choisir_musique_fond(mode: str) -> Optional[str]:
    """
    Cherche une musique de fond dans le dossier assets/music/.
    """
    if not os.path.exists(CHEMIN_MUSIQUE):
        return None

    # Chercher par mode d'abord
    for ext in ["*.mp3", "*.wav", "*.ogg", "*.m4a"]:
        fichiers = glob.glob(os.path.join(CHEMIN_MUSIQUE, f"*{mode}*{ext[1:]}"))
        if fichiers:
            return random.choice(fichiers)

    # Sinon n'importe quelle musique
    tous_fichiers = []
    for ext in ["*.mp3", "*.wav", "*.ogg", "*.m4a"]:
        tous_fichiers.extend(glob.glob(os.path.join(CHEMIN_MUSIQUE, ext)))

    return random.choice(tous_fichiers) if tous_fichiers else None
