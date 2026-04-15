"""
detector.py — Détection visuelle avec YOLO
Détecte les visages et personnes dans la vidéo pour un recadrage 9:16 intelligent.
Suit le sujet principal à travers les frames.
"""

import cv2
import logging
import os
from typing import Optional, Callable, List, Tuple

logger = logging.getLogger(__name__)


def detecter_zones_interet(
    chemin_video: str,
    debut: float,
    fin: float,
    config_mode: dict,
    callback_progression: Optional[Callable] = None
) -> List[dict]:
    """
    Détecte les zones d'intérêt (visages, personnes, action) dans un segment.

    Args:
        chemin_video: Chemin vers le fichier vidéo
        debut: Début du segment (secondes)
        fin: Fin du segment (secondes)
        config_mode: Configuration du mode (seuils, priorités...)
        callback_progression: Callback de progression

    Returns:
        Liste de dicts {'temps', 'bbox': (x, y, w, h), 'type', 'confiance', 'centre'}
    """
    logger.info(f"Détection visuelle [{debut:.1f}s - {fin:.1f}s]")

    # Chargement du modèle YOLO
    try:
        from ultralytics import YOLO
        modele_yolo = YOLO("yolov8n.pt")  # Nano — rapide et léger
        logger.info("Modèle YOLO chargé")
    except ImportError:
        logger.warning("ultralytics non installé, détection visuelle désactivée")
        return _zones_par_defaut(debut, fin)
    except Exception as e:
        logger.warning(f"Erreur chargement YOLO : {e}")
        return _zones_par_defaut(debut, fin)

    cap = cv2.VideoCapture(chemin_video)
    if not cap.isOpened():
        logger.error(f"Impossible d'ouvrir la vidéo : {chemin_video}")
        return _zones_par_defaut(debut, fin)

    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        fps = 25.0

    # Échantillonnage : 1 frame par seconde (suffisant pour la détection)
    frame_debut = int(debut * fps)
    frame_fin = int(fin * fps)
    interval_frames = max(1, int(fps))  # 1 frame/seconde

    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_debut)

    zones = []
    frame_num = frame_debut
    # Classes YOLO : 0=personne, 1=vélo, 2=voiture... On s'intéresse aux personnes (0)
    classes_interet = {0: "personne"}  # Classe personne dans COCO

    while frame_num < frame_fin:
        ret, frame = cap.read()
        if not ret:
            break

        temps = frame_num / fps

        if frame_num % interval_frames == 0:
            # Détection sur la frame
            try:
                resultats = modele_yolo(frame, verbose=False, classes=[0])
                for r in resultats:
                    for box in r.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        confiance = float(box.conf[0])
                        if confiance > 0.4:
                            cx = (x1 + x2) // 2
                            cy = (y1 + y2) // 2
                            zones.append({
                                "temps": round(temps, 3),
                                "bbox": (x1, y1, x2 - x1, y2 - y1),
                                "type": "personne",
                                "confiance": round(confiance, 3),
                                "centre": (cx, cy)
                            })
            except Exception as e:
                logger.debug(f"Erreur détection frame {frame_num}: {e}")

        frame_num += 1

    cap.release()
    logger.info(f"Détection terminée : {len(zones)} détections")
    return zones


def calculer_centre_recadrage(
    zones: List[dict],
    largeur_source: int,
    hauteur_source: int,
    debut: float,
    fin: float
) -> List[dict]:
    """
    Calcule le centre optimal de recadrage 9:16 pour chaque moment.
    Utilise un lissage temporel pour éviter les sauts brusques.

    Returns:
        Liste de dicts {'temps', 'cx_norm', 'cy_norm'} — coordonnées normalisées (0-1)
    """
    if not zones:
        # Centre par défaut = milieu de l'image
        return [{"temps": debut, "cx_norm": 0.5, "cy_norm": 0.5}]

    # Grouper les détections par seconde
    centres_par_temps = {}
    for zone in zones:
        t = round(zone["temps"])
        if t not in centres_par_temps:
            centres_par_temps[t] = []
        centres_par_temps[t].append(zone["centre"])

    # Calculer le centre moyen pondéré par seconde
    series_centres = []
    for t in sorted(centres_par_temps.keys()):
        cx_moyen = sum(c[0] for c in centres_par_temps[t]) / len(centres_par_temps[t])
        cy_moyen = sum(c[1] for c in centres_par_temps[t]) / len(centres_par_temps[t])
        series_centres.append({
            "temps": float(t),
            "cx_norm": cx_moyen / largeur_source,
            "cy_norm": cy_moyen / hauteur_source
        })

    # Lissage de la trajectoire (moyenne glissante sur 3 points)
    if len(series_centres) >= 3:
        for i in range(1, len(series_centres) - 1):
            series_centres[i]["cx_norm"] = (
                series_centres[i-1]["cx_norm"] +
                series_centres[i]["cx_norm"] +
                series_centres[i+1]["cx_norm"]
            ) / 3
            series_centres[i]["cy_norm"] = (
                series_centres[i-1]["cy_norm"] +
                series_centres[i]["cy_norm"] +
                series_centres[i+1]["cy_norm"]
            ) / 3

    return series_centres


def obtenir_dimensions_video(chemin_video: str) -> Tuple[int, int, float]:
    """
    Retourne (largeur, hauteur, fps) d'une vidéo.
    """
    cap = cv2.VideoCapture(chemin_video)
    if not cap.isOpened():
        return 1920, 1080, 25.0
    largeur = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    hauteur = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return largeur, hauteur, fps if fps > 0 else 25.0


def _zones_par_defaut(debut: float, fin: float) -> List[dict]:
    """Retourne une zone par défaut (centre de l'image) si la détection échoue."""
    return [{"temps": debut, "bbox": None, "type": "defaut", "confiance": 1.0, "centre": (0.5, 0.5)}]
