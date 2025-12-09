import os

# 🔧 Indiquer à MoviePy où se trouve ImageMagick (AVANT d'importer moviepy)
os.environ["IMAGEMAGICK_BINARY"] = r"C:\Program Files\ImageMagick-7.1.2-Q16\magick.exe"

import PIL.Image
# FIX pour la compatibilité Pillow récent et MoviePy
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

import yt_dlp
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip, clips_array

import cv2
import numpy as np
import whisper

# --- CONFIGURATION GLOBALE ---

FALLBACK_X, FALLBACK_Y = 0, 0
FALLBACK_W, FALLBACK_H = 450, 340

FINAL_W = 1080
FINAL_H = 1920
CAM_RATIO = 0.35  # 35% caméra en haut, 65% jeu en bas

# Palette de couleurs pour les sous-titres (style TikTok)
CAPTION_COLORS = [
    "white",
    "yellow",
    "deepskyblue",
    "lime",
    "violet"
]

_whisper_model = None  # cache modèle whisper


# ------------------ WHISPER ------------------ #

def get_whisper_model():
    """Charge le modèle Whisper une seule fois (lazy load)."""
    global _whisper_model
    if _whisper_model is None:
        print("🧠 Chargement du modèle Whisper (small)...")
        _whisper_model = whisper.load_model("small")  # "tiny", "base", "small", ...
    return _whisper_model


def transcribe_with_whisper(video_path):
    """
    Utilise Whisper pour générer des segments avec liste de mots (timestamps précis).
    Retourne une liste de segments :
    {
      "start": float,
      "end": float,
      "text": str,
      "words": [ {"start": float, "end": float, "word": str}, ... ]
    }
    """
    print("🧠 Whisper : Transcription en cours...")
    model = get_whisper_model()

    result = model.transcribe(
        video_path,
        language=None,          # auto FR/EN
        word_timestamps=True    # IMPORTANT pour les timings précis
    )

    segments = []
    for seg in result["segments"]:
        words = []
        for w in seg.get("words", []):
            word_text = w["word"].strip()
            if not word_text:
                continue
            words.append({
                "start": float(w["start"]),
                "end": float(w["end"]),
                "word": word_text
            })

        segments.append({
            "start": float(seg["start"]),
            "end": float(seg["end"]),
            "text": seg["text"].strip(),
            "words": words
        })

    print(f"✅ Whisper : {len(segments)} segments générés.")
    return segments


def build_captions_from_segments(segments, max_words=4, max_chars=25):
    """
    Construit des petits blocs de sous-titres (~3-4 mots)
    parfaitement calés sur les timestamps des mots.
    """
    captions = []

    for seg in segments:
        words = seg["words"]
        if not words:
            continue

        current_words = []
        current_start = None

        for w in words:
            if current_start is None:
                current_start = w["start"]
            current_words.append(w)

            text = " ".join(x["word"] for x in current_words)

            # On coupe si on dépasse le seuil de mots ou de caractères
            if len(current_words) >= max_words or len(text) >= max_chars:
                captions.append({
                    "start": current_start,
                    "end": current_words[-1]["end"],
                    "text": text
                })
                current_words = []
                current_start = None

        # Reste éventuel
        if current_words:
            captions.append({
                "start": current_start,
                "end": current_words[-1]["end"],
                "text": " ".join(x["word"] for x in current_words)
            })

    print(f"📝 {len(captions)} sous-titres générés.")
    return captions


def choose_style_for_caption(idx, text):
    """
    Choisit une couleur en fonction de l'index ou du contenu.
    Tu peux complexifier avec des mots-clés.
    """
    keywords_color = {
        "blue": "deepskyblue",
        "ward": "lime",
        "ult": "yellow",
        "one shot": "red",
        "oneshot": "red",
        "clutch": "violet"
    }

    lower = text.lower()
    for k, col in keywords_color.items():
        if k in lower:
            return col

    return CAPTION_COLORS[idx % len(CAPTION_COLORS)]


def make_subtitle_clips(captions, video_size):
    """
    Sous-titres stylés sans fond noir :
      - texte en majuscules, police arrondie
      - outline noir épais
      - couleur flashy par bloc
    """
    W, H = video_size
    clips = []

    for i, cap in enumerate(captions):
        txt = cap["text"].upper()
        color = choose_style_for_caption(i, txt)

        # léger offset pour coller à la voix
        start = max(0, cap["start"] - 0.05)
        end = cap["end"] + 0.05

        y_pos = int(H * 0.70)

        # 1) outline noir (texte légèrement plus gros)
        outline_clip = (
            TextClip(
                txt,
                fontsize=80,
                font="Arial Rounded MT Bold",   # police arrondie
                color="black",
                stroke_color="black",
                stroke_width=6,
                method="caption",
                size=(int(W * 0.9), None),
                align="center"
            )
            .set_start(start)
            .set_end(end)
            .set_position(("center", y_pos))
        )

        # 2) texte coloré par-dessus (léger stroke blanc pour la netteté)
        fg_clip = (
            TextClip(
                txt,
                fontsize=80,
                font="Arial Rounded MT Bold",
                color=color,
                stroke_color="white",
                stroke_width=1,
                method="caption",
                size=(int(W * 0.9), None),
                align="center"
            )
            .set_start(start)
            .set_end(end)
            .set_position(("center", y_pos))
        )

        clips.extend([outline_clip, fg_clip])

    return clips



# ------------------ DÉTECTION VISAGE ------------------ #

def detect_face_box(video_path):
    """Détecte le visage et retourne un cadre SERRÉ."""
    print("🤖 IA (OpenCV) : Recherche du visage...")

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
    )

    video_capture = cv2.VideoCapture(video_path)
    fps = video_capture.get(cv2.CAP_PROP_FPS) or 25

    # Taille vidéo (avant release)
    video_w = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    video_h = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080

    # On regarde à 5 secondes pour éviter les intros
    frame_to_check = int(fps * 5)
    video_capture.set(cv2.CAP_PROP_POS_FRAMES, frame_to_check)

    success, frame = video_capture.read()
    video_capture.release()

    if not success:
        print("⚠️ IA : Erreur lecture vidéo. Fallback.")
        return FALLBACK_X, FALLBACK_Y, FALLBACK_W, FALLBACK_H

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(30, 30)
    )

    if len(faces) == 0:
        print("⚠️ IA : Aucun visage. Fallback.")
        return FALLBACK_X, FALLBACK_Y, FALLBACK_W, FALLBACK_H

    largest_face = max(faces, key=lambda rect: rect[2] * rect[3])
    x, y, w, h = largest_face
    print(f"✅ IA : Visage trouvé ! (X:{x}, Y:{y})")

    padding_w = int(w * 0.15)  # +15% largeur
    padding_h = int(h * 0.30)  # +30% hauteur

    final_x = max(0, x - padding_w // 2)
    final_y = max(0, y - padding_h // 3)
    final_w = min(video_w - final_x, w + padding_w)
    final_h = min(video_h - final_y, h + padding_h)

    print(f"📐 Cadrage optimisé : X={final_x}, Y={final_y}, W={final_w}, H={final_h}")
    return final_x, final_y, final_w, final_h


# ------------------ DOWNLOAD CLIP ------------------ #

def download_clip(url, filename="input_clip.mp4"):
    print(f"⬇️ Téléchargement : {url}")
    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'outtmpl': filename,
        'quiet': True,
        'no_warnings': True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"❌ Erreur download : {e}")
        return False


# ------------------ PIPELINE PRINCIPAL : CREATE TIKTOK ------------------ #

def create_tiktok(input_file, output_file):
    print("✂️ Démarrage du processus (Mode Sous-titres TikTok)...")
    clip = None
    base_clip = None
    final_clip = None

    try:
        # 1. DÉTECTION IA (cadrage caméra)
        cam_x, cam_y, cam_w, cam_h = detect_face_box(input_file)

        # 2. CLIP SOURCE
        clip = VideoFileClip(input_file)
        W, H = clip.size

        # 3. CALCUL DES HAUTEURS
        cam_final_h = int(FINAL_H * CAM_RATIO)
        game_final_h = FINAL_H - cam_final_h

        # 4. MONTAGE VIDÉO
        # Caméra (haut)
        cam_clip = clip.crop(x1=cam_x, y1=cam_y, width=cam_w, height=cam_h)
        cam_clip = cam_clip.resize(newsize=(FINAL_W, cam_final_h))

        # Jeu (bas) centré
        x1_game = max(0, W / 2 - FINAL_W / 2)
        if x1_game + FINAL_W > W:
            x1_game = max(0, W - FINAL_W)

        game_clip = clip.crop(
            x1=x1_game,
            y1=0,
            width=min(FINAL_W, W),
            height=H
        )
        game_clip = game_clip.resize(newsize=(FINAL_W, game_final_h))

        base_clip = clips_array([[cam_clip], [game_clip]])  # 1080x1920

        # 5. TRANSCRIPTION AUDIO + CAPTIONS
        segments = transcribe_with_whisper(input_file)
        captions = build_captions_from_segments(
            segments,
            max_words=4,
            max_chars=25
        )
        subtitle_clips = make_subtitle_clips(captions, base_clip.size)

        # 6. COMPOSITION FINALE (vidéo + sous-titres)
        final_clip = CompositeVideoClip([base_clip, *subtitle_clips])

        # 7. EXPORT OPTIMISÉ (Pour Discord < 25Mo)
        print("💾 Exportation optimisée avec sous-titres...")
        final_clip.write_videofile(
            output_file,
            codec='libx264',
            audio_codec='aac',
            audio_bitrate="128k",
            fps=30,
            bitrate="2000k",
            preset="medium",
            verbose=False,
            logger=None
        )
        print(f"✨ Vidéo prête : {output_file}")
        return True

    except Exception as e:
        print(f"❌ Erreur montage : {e}")
        return False

    finally:
        # Nettoyage MoviePy
        try:
            if clip is not None:
                clip.close()
        except Exception:
            pass
        try:
            if base_clip is not None and base_clip is not final_clip:
                base_clip.close()
        except Exception:
            pass
        try:
            if final_clip is not None:
                final_clip.close()
        except Exception:
            pass
