"""
Script de debugging pour analyser la détection de visage
"""
import sys
sys.path.insert(0, 'app')

import maker
import cv2
import numpy as np
from PIL import Image, ImageDraw

# URL du clip à tester
CLIP_URL = "https://www.twitch.tv/manatylol/clip/DirtyPlayfulLeopardDBstyle-DF8_uugba3zN-mBG"
INPUT_FILE = "debug_clip.mp4"
DEBUG_IMAGE = "debug_detection.jpg"

print("=" * 60)
print("🔍 SCRIPT DE DEBUGGING - DÉTECTION DE VISAGE")
print("=" * 60)

# Étape 1 : Téléchargement
print("\n1️⃣ Téléchargement du clip...")
success = maker.download_clip(CLIP_URL, INPUT_FILE)

if not success:
    print("❌ Échec du téléchargement")
    sys.exit(1)

print("✅ Téléchargement réussi")

# Étape 2 : Détection de visage avec logs détaillés
print("\n2️⃣ Détection de visage...")
face_box = maker.detect_face_multiframe(INPUT_FILE)

if face_box:
    print(f"\n📍 RÉSULTAT DE LA DÉTECTION :")
    print(f"   Zone : {face_box.zone}")
    print(f"   Position : ({face_box.x}, {face_box.y})")
    print(f"   Taille : {face_box.w}x{face_box.h}")
    print(f"   Confiance : {face_box.confidence:.2f}")
else:
    print("\n⚠️ Aucun visage détecté, utilisation du fallback...")
    face_box = maker.get_fallback_webcam_zone(INPUT_FILE)
    print(f"\n📍 RÉSULTAT FALLBACK :")
    print(f"   Zone : {face_box.zone}")
    print(f"   Position : ({face_box.x}, {face_box.y})")
    print(f"   Taille : {face_box.w}x{face_box.h}")

# Étape 3 : Visualisation
print(f"\n3️⃣ Création d'une image de preview...")

cap = cv2.VideoCapture(INPUT_FILE)
if cap.isOpened():
    # Lire une frame au milieu de la vidéo
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)

    ret, frame = cap.read()
    if ret:
        # Dessiner le rectangle de détection
        cv2.rectangle(
            frame,
            (face_box.x, face_box.y),
            (face_box.x + face_box.w, face_box.y + face_box.h),
            (0, 255, 0),  # Vert
            3
        )

        # Ajouter un label
        label = f"Zone: {face_box.zone}"
        cv2.putText(
            frame,
            label,
            (face_box.x, face_box.y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 0),
            2
        )

        # Sauvegarder
        cv2.imwrite(DEBUG_IMAGE, frame)
        print(f"✅ Image de debug sauvegardée : {DEBUG_IMAGE}")
        print(f"   Ouvrez cette image pour voir la zone détectée !")

    cap.release()

print("\n" + "=" * 60)
print("✅ ANALYSE TERMINÉE")
print("=" * 60)
print(f"\nActions suggérées :")
print(f"1. Ouvrez '{DEBUG_IMAGE}' pour voir la zone détectée")
print(f"2. Vérifiez si le rectangle vert englobe bien la webcam")
print(f"3. Si la zone est incorrecte, on ajustera les paramètres")
