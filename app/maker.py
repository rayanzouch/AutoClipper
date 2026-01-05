"""
MAKER.PY - Version 2.0 (Refonte Complète)
==========================================
Bot de conversion Twitch Clip → TikTok/Reels/Shorts

Améliorations majeures :
- Détection de visage multi-frame avec tracking
- Sous-titres style "Hormozi" avec animation mot par mot
- Rendu Pillow pur (sans dépendance ImageMagick)
- Compression adaptative intelligente
- Gestion d'erreurs robuste

Auteur: Refonte pour production commerciale
"""

import os
import sys
import tempfile
import traceback
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict
from collections import Counter

# ═══════════════════════════════════════════════════════════════════════════════
# IMPORTS ET CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

import numpy as np
import cv2
import requests
import time
from PIL import Image, ImageDraw, ImageFont
import yt_dlp
from ultralytics import YOLO
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()
ASSEMBLYAI_API_KEY = os.getenv('ASSEMBLYAI_API_KEY')

# MoviePy imports
from moviepy.editor import (
    VideoFileClip, AudioFileClip, CompositeVideoClip, 
    ColorClip, ImageClip, concatenate_videoclips
)

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION GLOBALE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Config:
    """Configuration centralisée du pipeline"""
    # Dimensions finales (TikTok/Reels/Shorts)
    FINAL_W: int = 1080
    FINAL_H: int = 1920
    
    # Ratio webcam/gameplay
    CAM_RATIO: float = 0.35  # 35% pour la webcam

    # Zoom du gameplay (plus le ratio est grand, moins c'est zoomé)
    # 9/16 = 0.5625 (très zoomé), 12/16 = 0.75 (plus large)
    GAMEPLAY_ASPECT: float = 0.70  # Bon compromis : moins zoomé que 9:16
    
    # Détection de visage
    FACE_SAMPLE_COUNT: int = 10       # Nombre de frames à analyser
    FACE_MIN_CONFIDENCE: float = 0.3  # Confiance minimale MediaPipe
    FACE_PADDING_W: float = 0.6       # Padding horizontal autour du visage
    FACE_PADDING_H: float = 0.9       # Padding vertical autour du visage
    
    # Sous-titres Hormozi
    SUBTITLE_FONT_SIZE: int = 75
    SUBTITLE_STROKE_WIDTH: int = 4
    SUBTITLE_Y_POSITION: float = 0.72  # Position Y (% de la hauteur)
    SUBTITLE_MAX_WORDS: int = 3        # Mots max par groupe
    SUBTITLE_MAX_CHARS: int = 20       # Caractères max par groupe
    
    # Couleurs des sous-titres
    SUBTITLE_DEFAULT_COLOR: str = "#FFFFFF"
    SUBTITLE_HIGHLIGHT_COLOR: str = "#FFFF00"  # Jaune pour le mot actif
    SUBTITLE_STROKE_COLOR: str = "#000000"
    SUBTITLE_BG_COLOR: Tuple[int, int, int, int] = (0, 0, 0, 180)  # Fond semi-transparent
    
    # Compression (optimisé pour Streamable - limite 250 Mo)
    TARGET_SIZE_MB: float = 100.0  # Qualité HD, Streamable gère les gros fichiers
    MIN_BITRATE: str = "2000k"     # Minimum plus élevé pour éviter les artefacts
    MAX_BITRATE: str = "10000k"    # Qualité maximale
    
    # Whisper
    WHISPER_MODEL: str = "large"  # Options: tiny, base, small, medium, large
    SUBTITLES_ENABLED: bool = True  # Sous-titres activés

    # YOLO (détection de personnes)
    YOLO_MODEL: str = "yolov8n.pt"  # nano = rapide, autres: yolov8s.pt, yolov8m.pt
    YOLO_CONFIDENCE: float = 0.3   # Confiance minimum pour la détection
    
    # Fallback webcam (coins classiques)
    FALLBACK_ZONES: List[Tuple[str, float, float, float, float]] = None
    
    def __post_init__(self):
        # Zones de fallback pour webcam (x%, y%, w%, h%)
        self.FALLBACK_ZONES = [
            ("top_left", 0.0, 0.0, 0.25, 0.30),
            ("top_right", 0.75, 0.0, 0.25, 0.30),
            ("bottom_left", 0.0, 0.70, 0.25, 0.30),
            ("bottom_right", 0.75, 0.70, 0.25, 0.30),
        ]

CONFIG = Config()

# ═══════════════════════════════════════════════════════════════════════════════
# LAZY LOADERS (Économie de mémoire)
# ═══════════════════════════════════════════════════════════════════════════════

_whisper_model = None
_yolo_model = None
_font_cache = {}

def get_whisper_model():
    """Charge le modèle Whisper à la demande"""
    global _whisper_model
    if _whisper_model is None:
        import whisper
        print(f"🧠 Chargement Whisper ({CONFIG.WHISPER_MODEL})...")
        _whisper_model = whisper.load_model(CONFIG.WHISPER_MODEL)
    return _whisper_model

def get_yolo_model():
    """Charge le modèle YOLO à la demande"""
    global _yolo_model
    if _yolo_model is None:
        print(f"🧠 Chargement YOLO ({CONFIG.YOLO_MODEL})...")
        _yolo_model = YOLO(CONFIG.YOLO_MODEL)
    return _yolo_model

def get_font(size: int) -> ImageFont.FreeTypeFont:
    """Charge la police Obelix Pro avec cache"""
    if size not in _font_cache:
        # Chemin vers la police Obelix Pro (priorité)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(script_dir)

        font_paths = [
            # Obelix Pro Bold (prioritaire)
            os.path.join(project_dir, "obelix-pro", "ObelixProB-cyr.ttf"),
            os.path.join(project_dir, "obelix-pro", "ObelixPro-cyr.ttf"),
            # Fallbacks Windows
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/impact.ttf",
        ]

        font = None
        for path in font_paths:
            if os.path.exists(path):
                try:
                    font = ImageFont.truetype(path, size)
                    print(f"✅ Police chargée : {os.path.basename(path)}")
                    break
                except Exception as e:
                    print(f"⚠️ Erreur police {path}: {e}")
                    continue

        if font is None:
            print("⚠️ Police par défaut utilisée")
            font = ImageFont.load_default()

        _font_cache[size] = font

    return _font_cache[size]

# ═══════════════════════════════════════════════════════════════════════════════
# TÉLÉCHARGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

def download_clip(url: str, output_path: str = "input_clip.mp4") -> bool:
    """
    Télécharge un clip Twitch en haute qualité
    
    Args:
        url: URL du clip Twitch
        output_path: Chemin de sortie
    
    Returns:
        bool: True si succès
    """
    print(f"⬇️ Téléchargement : {url}")
    
    # Supprimer le fichier existant si présent
    if os.path.exists(output_path):
        os.remove(output_path)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if os.path.exists(output_path):
            size_mb = os.path.getsize(output_path) / (1024 * 1024)
            print(f"✅ Téléchargé : {size_mb:.1f} Mo")
            return True
        else:
            print("❌ Fichier non créé après téléchargement")
            return False
            
    except Exception as e:
        print(f"❌ Erreur téléchargement : {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# DÉTECTION DE VISAGE (MULTI-FRAME ROBUSTE)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class FaceBox:
    """Représente une zone de visage détectée"""
    x: int
    y: int
    w: int
    h: int
    confidence: float
    zone: str = "unknown"

def detect_person_multiframe(video_path: str) -> Optional[FaceBox]:
    """
    Détection de personne robuste avec YOLO et échantillonnage multi-frame

    YOLO détecte des personnes entières (pas juste les visages),
    ce qui est beaucoup plus fiable pour les petites webcams de stream.

    Stratégie :
    1. Échantillonne N frames réparties dans la vidéo
    2. Détecte les personnes avec YOLO
    3. Vote majoritaire sur la zone (coin de l'écran)
    4. Retourne la zone la plus stable
    """
    print("🔍 Analyse YOLO multi-frame pour détection de personne...")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("❌ Impossible d'ouvrir la vidéo")
        return None

    # Infos vidéo
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = total_frames / fps

    print(f"📹 Vidéo : {vid_w}x{vid_h}, {duration:.1f}s, {fps:.0f}fps")

    # Calcul des frames à échantillonner (évite début/fin)
    start_frame = int(fps * 2)  # Skip les 2 premières secondes
    end_frame = int(total_frames - fps * 2)  # Skip les 2 dernières

    if end_frame <= start_frame:
        start_frame = 0
        end_frame = total_frames

    sample_frames = np.linspace(start_frame, end_frame, CONFIG.FACE_SAMPLE_COUNT, dtype=int)

    model = get_yolo_model()
    detections = []

    for frame_idx in sample_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue

        # Détection YOLO (classe 0 = personne)
        results = model(frame, verbose=False, conf=CONFIG.YOLO_CONFIDENCE)

        for result in results:
            boxes = result.boxes
            for box in boxes:
                # Classe 0 = personne dans COCO
                if int(box.cls[0]) == 0:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0])

                    fx = int(x1)
                    fy = int(y1)
                    fw = int(x2 - x1)
                    fh = int(y2 - y1)

                    # Déterminer dans quel coin se trouve la personne
                    center_x = fx + fw / 2
                    center_y = fy + fh / 2
                    zone = classify_zone(center_x, center_y, vid_w, vid_h)

                    detections.append(FaceBox(fx, fy, fw, fh, confidence, zone))

    cap.release()

    if not detections:
        print("⚠️ Aucune personne détectée sur tous les frames")
        return None

    # Vote majoritaire sur la zone
    zone_counts = Counter(d.zone for d in detections)
    best_zone, count = zone_counts.most_common(1)[0]

    print(f"📊 Détections YOLO : {len(detections)} personnes, zone dominante : {best_zone} ({count}/{len(detections)})")

    # Filtrer les détections de la zone majoritaire
    zone_detections = [d for d in detections if d.zone == best_zone]

    # Moyenne des positions pour cette zone
    avg_x = int(np.mean([d.x for d in zone_detections]))
    avg_y = int(np.mean([d.y for d in zone_detections]))
    avg_w = int(np.mean([d.w for d in zone_detections]))
    avg_h = int(np.mean([d.h for d in zone_detections]))
    avg_conf = np.mean([d.confidence for d in zone_detections])

    # Padding plus généreux pour YOLO (on veut voir toute la personne)
    pad_w = int(avg_w * 0.2)  # 20% de padding horizontal
    pad_h = int(avg_h * 0.1)  # 10% de padding vertical

    final_x = max(0, avg_x - pad_w)
    final_y = max(0, avg_y - pad_h)
    final_w = min(vid_w - final_x, avg_w + pad_w * 2)
    final_h = min(vid_h - final_y, avg_h + pad_h * 2)

    print(f"✅ Webcam détectée : zone={best_zone}, pos=({final_x},{final_y}), taille={final_w}x{final_h}")

    return FaceBox(final_x, final_y, final_w, final_h, avg_conf, best_zone)

def classify_zone(x: float, y: float, w: int, h: int) -> str:
    """Classifie une position dans l'un des 4 coins ou le centre"""
    rel_x = x / w
    rel_y = y / h
    
    if rel_x < 0.35:
        return "top_left" if rel_y < 0.5 else "bottom_left"
    elif rel_x > 0.65:
        return "top_right" if rel_y < 0.5 else "bottom_right"
    else:
        return "center"

def get_fallback_webcam_zone(video_path: str) -> FaceBox:
    """
    Fallback intelligent : analyse les coins pour trouver une zone "webcam-like"
    
    Heuristique : la webcam a souvent une luminosité/contraste différent du gameplay
    """
    print("🔄 Fallback : recherche de zone webcam par analyse visuelle...")
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return FaceBox(0, 0, 400, 300, 0.0, "fallback_default")
    
    vid_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    vid_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    
    # Lire un frame au milieu
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(fps * 5))
    ret, frame = cap.read()
    cap.release()
    
    if not ret:
        return FaceBox(0, 0, 400, 300, 0.0, "fallback_default")
    
    # Analyser chaque coin
    best_score = -1
    best_zone = None
    
    for name, rx, ry, rw, rh in CONFIG.FALLBACK_ZONES:
        x1 = int(rx * vid_w)
        y1 = int(ry * vid_h)
        x2 = int((rx + rw) * vid_w)
        y2 = int((ry + rh) * vid_h)
        
        roi = frame[y1:y2, x1:x2]
        
        # Score basé sur la variance (une webcam a souvent plus de détails qu'un fond uni)
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        variance = np.var(gray)
        
        # Bonus si beaucoup de tons chair (heuristique simple)
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        skin_mask = cv2.inRange(hsv, (0, 20, 70), (20, 255, 255))
        skin_ratio = np.sum(skin_mask > 0) / skin_mask.size
        
        score = variance * (1 + skin_ratio * 2)
        
        if score > best_score:
            best_score = score
            best_zone = (name, x1, y1, x2 - x1, y2 - y1)
    
    if best_zone:
        name, x, y, w, h = best_zone
        print(f"📍 Zone fallback sélectionnée : {name}")
        return FaceBox(x, y, w, h, 0.5, f"fallback_{name}")
    
    return FaceBox(0, 0, int(vid_w * 0.25), int(vid_h * 0.3), 0.0, "fallback_default")

# ═══════════════════════════════════════════════════════════════════════════════
# TRANSCRIPTION WHISPER
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class WordTiming:
    """Un mot avec son timing précis"""
    word: str
    start: float
    end: float

@dataclass
class Caption:
    """Un groupe de mots à afficher ensemble"""
    words: List[WordTiming]
    start: float
    end: float
    
    @property
    def text(self) -> str:
        return " ".join(w.word for w in self.words)

def transcribe_with_assemblyai(video_path: str) -> List[WordTiming]:
    """
    Transcrit avec AssemblyAI (haute précision)
    """
    headers = {"authorization": ASSEMBLYAI_API_KEY}
    base_url = "https://api.assemblyai.com/v2"

    # 1. Upload du fichier
    print("   📤 Upload vers AssemblyAI...")
    with open(video_path, "rb") as f:
        upload_response = requests.post(
            f"{base_url}/upload",
            headers=headers,
            data=f
        )
    upload_url = upload_response.json()["upload_url"]

    # 2. Créer la transcription
    print("   🔄 Transcription en cours...")
    transcript_response = requests.post(
        f"{base_url}/transcript",
        headers=headers,
        json={
            "audio_url": upload_url,
            "language_code": "fr",  # Français
        }
    )
    transcript_id = transcript_response.json()["id"]

    # 3. Polling jusqu'à completion
    while True:
        result = requests.get(
            f"{base_url}/transcript/{transcript_id}",
            headers=headers
        ).json()

        status = result["status"]
        if status == "completed":
            break
        elif status == "error":
            raise Exception(f"AssemblyAI error: {result.get('error')}")

        time.sleep(2)

    # 4. Extraire les mots avec timestamps
    words = []
    for word_data in result.get("words", []):
        word = WordTiming(
            word=word_data["text"],
            start=word_data["start"] / 1000.0,  # ms → secondes
            end=word_data["end"] / 1000.0
        )
        words.append(word)

    return words


def transcribe_with_whisper(video_path: str) -> List[WordTiming]:
    """
    Transcrit avec Whisper (fallback local)
    """
    model = get_whisper_model()
    result = model.transcribe(video_path, word_timestamps=True)

    words = []
    for segment in result.get("segments", []):
        for word_data in segment.get("words", []):
            word = WordTiming(
                word=word_data["word"].strip(),
                start=float(word_data["start"]),
                end=float(word_data["end"])
            )
            if word.word:
                words.append(word)

    return words


def transcribe_video(video_path: str) -> List[Caption]:
    """
    Transcrit la vidéo et retourne des captions groupées.
    Utilise AssemblyAI si disponible, sinon Whisper.
    """
    all_words = []

    if ASSEMBLYAI_API_KEY:
        print("🎤 Transcription AssemblyAI (haute précision)...")
        try:
            all_words = transcribe_with_assemblyai(video_path)
            print(f"✅ AssemblyAI : {len(all_words)} mots transcrits")
        except Exception as e:
            print(f"⚠️ Erreur AssemblyAI : {e}")
            print("   Fallback sur Whisper...")
            all_words = transcribe_with_whisper(video_path)
    else:
        print("🎤 Transcription Whisper (pas de clé AssemblyAI)...")
        all_words = transcribe_with_whisper(video_path)

    print(f"📝 {len(all_words)} mots transcrits")

    # Grouper les mots en captions
    captions = group_words_into_captions(all_words)
    print(f"📑 {len(captions)} groupes de sous-titres créés")

    return captions

def group_words_into_captions(words: List[WordTiming]) -> List[Caption]:
    """
    Groupe les mots en captions de taille optimale pour la lisibilité
    """
    captions = []
    current_words = []
    
    for word in words:
        current_words.append(word)
        
        # Vérifier si on doit créer un nouveau groupe
        current_text = " ".join(w.word for w in current_words)
        should_break = (
            len(current_words) >= CONFIG.SUBTITLE_MAX_WORDS or
            len(current_text) >= CONFIG.SUBTITLE_MAX_CHARS
        )
        
        if should_break:
            caption = Caption(
                words=current_words.copy(),
                start=current_words[0].start,
                end=current_words[-1].end
            )
            captions.append(caption)
            current_words = []
    
    # Dernier groupe
    if current_words:
        caption = Caption(
            words=current_words,
            start=current_words[0].start,
            end=current_words[-1].end
        )
        captions.append(caption)
    
    return captions

# ═══════════════════════════════════════════════════════════════════════════════
# RENDU SOUS-TITRES HORMOZI (PILLOW PUR)
# ═══════════════════════════════════════════════════════════════════════════════

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """Convertit un code hex en tuple RGB"""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def render_hormozi_subtitle(
    text: str,
    highlight_word_idx: int,
    width: int,
    height: int
) -> np.ndarray:
    """
    Rend un sous-titre style Hormozi avec highlight du mot actif
    
    Style :
    - Texte en majuscules
    - Mot actif en jaune, autres en blanc
    - Contour noir épais
    - Fond semi-transparent optionnel
    """
    # Créer image RGBA
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    font = get_font(CONFIG.SUBTITLE_FONT_SIZE)
    words = text.upper().split()
    
    if not words:
        return np.array(img)
    
    # Calculer la position de chaque mot
    word_positions = []
    total_width = 0
    space_width = draw.textlength(" ", font=font)
    
    for word in words:
        word_width = draw.textlength(word, font=font)
        word_positions.append((word, word_width))
        total_width += word_width
    
    total_width += space_width * (len(words) - 1)
    
    # Position Y centrée verticalement dans la zone prévue
    y_pos = int(height * CONFIG.SUBTITLE_Y_POSITION)
    
    # Position X de départ (centré)
    x_pos = (width - total_width) // 2
    
    # Dessiner le fond semi-transparent (optionnel, améliore lisibilité)
    bbox = font.getbbox("Ay")  # Hauteur typique
    text_height = bbox[3] - bbox[1]
    padding = 15
    
    bg_rect = [
        x_pos - padding,
        y_pos - padding,
        x_pos + total_width + padding,
        y_pos + text_height + padding
    ]
    draw.rounded_rectangle(bg_rect, radius=10, fill=CONFIG.SUBTITLE_BG_COLOR)
    
    # Dessiner chaque mot
    stroke_color = hex_to_rgb(CONFIG.SUBTITLE_STROKE_COLOR)
    default_color = hex_to_rgb(CONFIG.SUBTITLE_DEFAULT_COLOR)
    highlight_color = hex_to_rgb(CONFIG.SUBTITLE_HIGHLIGHT_COLOR)
    
    for i, (word, word_width) in enumerate(word_positions):
        # Couleur : highlight si c'est le mot actif
        color = highlight_color if i == highlight_word_idx else default_color
        
        # Dessiner le contour (stroke)
        for dx in range(-CONFIG.SUBTITLE_STROKE_WIDTH, CONFIG.SUBTITLE_STROKE_WIDTH + 1):
            for dy in range(-CONFIG.SUBTITLE_STROKE_WIDTH, CONFIG.SUBTITLE_STROKE_WIDTH + 1):
                if dx != 0 or dy != 0:
                    draw.text((x_pos + dx, y_pos + dy), word, font=font, fill=stroke_color)
        
        # Dessiner le texte principal
        draw.text((x_pos, y_pos), word, font=font, fill=color)
        
        x_pos += word_width + space_width
    
    return np.array(img)

def create_subtitle_clips(captions: List[Caption], video_size: Tuple[int, int], duration: float):
    """
    Crée les clips de sous-titres avec animation mot par mot
    
    Chaque caption est divisée en sous-clips où le mot actif change
    """
    clips = []
    width, height = video_size
    
    for caption in captions:
        words = caption.words
        if not words:
            continue
        
        # Pour chaque mot, créer un clip avec ce mot highlighté
        for word_idx, word in enumerate(words):
            # Timing de ce mot
            start = word.start
            end = word.end
            clip_duration = end - start
            
            if clip_duration < 0.05:
                clip_duration = 0.05
            
            # Rendre le frame avec highlight
            frame = render_hormozi_subtitle(
                caption.text,
                highlight_word_idx=word_idx,
                width=width,
                height=height
            )
            
            # Créer le clip
            clip = ImageClip(frame, ismask=False, transparent=True)
            clip = clip.set_duration(clip_duration)
            clip = clip.set_start(start)
            clip = clip.set_position((0, 0))
            
            clips.append(clip)
    
    return clips

# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE DE MONTAGE
# ═══════════════════════════════════════════════════════════════════════════════

def calculate_adaptive_bitrate(duration: float, target_mb: float = CONFIG.TARGET_SIZE_MB) -> str:
    """
    Calcule le bitrate optimal pour atteindre une taille cible
    """
    target_bits = target_mb * 8 * 1024 * 1024
    # Réserve 192kbps pour l'audio haute qualité
    audio_bits = 192 * 1000 * duration
    video_bits = target_bits - audio_bits
    bitrate = int(video_bits / duration)

    # Clamp entre min et max
    min_br = int(CONFIG.MIN_BITRATE.replace('k', '000'))
    max_br = int(CONFIG.MAX_BITRATE.replace('k', '000'))
    bitrate = max(min_br, min(max_br, bitrate))

    return f"{bitrate // 1000}k"

def create_tiktok(input_path: str, output_path: str) -> bool:
    """
    Pipeline complet de création de vidéo TikTok
    
    Étapes :
    1. Détection de visage (multi-frame)
    2. Crop et assemblage webcam + gameplay
    3. Transcription Whisper
    4. Rendu sous-titres Hormozi
    5. Export avec compression adaptative
    """
    print("\n" + "═" * 60)
    print("🎬 DÉMARRAGE DU MONTAGE TIKTOK")
    print("═" * 60)
    
    clip = None
    final_clip = None
    
    try:
        # ─────────────────────────────────────────────────────────────
        # ÉTAPE 1 : Détection de la webcam (YOLO)
        # ─────────────────────────────────────────────────────────────
        face_box = detect_person_multiframe(input_path)

        if face_box is None or face_box.confidence < 0.3:
            print("⚠️ Détection YOLO faible, utilisation du fallback...")
            face_box = get_fallback_webcam_zone(input_path)
        
        # ─────────────────────────────────────────────────────────────
        # ÉTAPE 2 : Chargement et crop de la vidéo
        # ─────────────────────────────────────────────────────────────
        print("\n📹 Chargement de la vidéo source...")
        clip = VideoFileClip(input_path)
        src_w, src_h = clip.size
        duration = clip.duration
        
        print(f"   Source : {src_w}x{src_h}, {duration:.1f}s")
        
        # Dimensions cibles
        target_cam_h = int(CONFIG.FINAL_H * CONFIG.CAM_RATIO)
        target_game_h = CONFIG.FINAL_H - target_cam_h
        
        # ── WEBCAM ──
        print("📷 Traitement de la webcam...")
        cam_clip = clip.crop(
            x1=face_box.x,
            y1=face_box.y,
            width=face_box.w,
            height=face_box.h
        )
        
        # Resize pour remplir la largeur, puis crop vertical si nécessaire
        cam_aspect = face_box.w / face_box.h
        target_cam_aspect = CONFIG.FINAL_W / target_cam_h
        
        if cam_aspect > target_cam_aspect:
            # Trop large : resize par hauteur, crop largeur
            new_h = target_cam_h
            new_w = int(new_h * cam_aspect)
            cam_clip = cam_clip.resize(height=new_h)
            excess = new_w - CONFIG.FINAL_W
            cam_clip = cam_clip.crop(x1=excess//2, width=CONFIG.FINAL_W)
        else:
            # Trop haut : resize par largeur, crop hauteur
            new_w = CONFIG.FINAL_W
            new_h = int(new_w / cam_aspect)
            cam_clip = cam_clip.resize(width=new_w)
            excess = new_h - target_cam_h
            cam_clip = cam_clip.crop(y1=excess//2, height=target_cam_h)
        
        # Assurer la taille exacte
        cam_clip = cam_clip.resize(newsize=(CONFIG.FINAL_W, target_cam_h))
        
        # ── GAMEPLAY ──
        print("🎮 Traitement du gameplay...")

        # Stratégie : prendre le centre du jeu avec ratio configurable
        # CONFIG.GAMEPLAY_ASPECT contrôle le zoom (0.70 = moins zoomé que 9:16)
        target_game_w = int(src_h * CONFIG.GAMEPLAY_ASPECT)

        if target_game_w > src_w:
            # Vidéo plus étroite que le ratio demandé, on prend tout en largeur
            target_game_w = src_w

        game_x1 = (src_w - target_game_w) // 2
        game_clip = clip.crop(x1=game_x1, width=target_game_w, height=src_h)
        game_clip = game_clip.resize(newsize=(CONFIG.FINAL_W, target_game_h))

        print(f"   Gameplay : ratio={CONFIG.GAMEPLAY_ASPECT:.2f}, crop={target_game_w}px de large")
        
        # ── ASSEMBLAGE ──
        print("🔧 Assemblage webcam + gameplay...")
        
        # Positionner les clips
        cam_clip = cam_clip.set_position((0, 0))
        game_clip = game_clip.set_position((0, target_cam_h))
        
        # Fond noir de sécurité
        background = ColorClip(
            size=(CONFIG.FINAL_W, CONFIG.FINAL_H),
            color=(0, 0, 0)
        ).set_duration(duration)
        
        base_video = CompositeVideoClip(
            [background, cam_clip, game_clip],
            size=(CONFIG.FINAL_W, CONFIG.FINAL_H)
        )
        
        # ─────────────────────────────────────────────────────────────
        # ÉTAPE 3 : Transcription et sous-titres (optionnel)
        # ─────────────────────────────────────────────────────────────
        subtitle_clips = []

        if CONFIG.SUBTITLES_ENABLED:
            print("\n🎤 Transcription audio...")
            captions = transcribe_video(input_path)

            print("✨ Génération des sous-titres Hormozi...")
            subtitle_clips = create_subtitle_clips(
                captions,
                (CONFIG.FINAL_W, CONFIG.FINAL_H),
                duration
            )
        else:
            print("\n⏭️ Sous-titres désactivés (CONFIG.SUBTITLES_ENABLED = False)")

        # ─────────────────────────────────────────────────────────────
        # ÉTAPE 4 : Composition finale
        # ─────────────────────────────────────────────────────────────
        print("\n🎨 Composition finale...")

        all_clips = [base_video] + subtitle_clips
        final_clip = CompositeVideoClip(all_clips, size=(CONFIG.FINAL_W, CONFIG.FINAL_H))
        final_clip = final_clip.set_audio(clip.audio)
        
        # ─────────────────────────────────────────────────────────────
        # ÉTAPE 5 : Export
        # ─────────────────────────────────────────────────────────────
        print("\n💾 Export en cours...")
        
        bitrate = calculate_adaptive_bitrate(duration)
        print(f"   Bitrate adaptatif : {bitrate}")
        
        final_clip.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            audio_bitrate='192k',  # Audio haute qualité
            bitrate=bitrate,
            preset='slow',         # Meilleure compression = meilleure qualité
            fps=clip.fps or 30,    # Conserve le FPS original
            verbose=False,
            logger=None
        )
        
        # Vérification taille finale
        if os.path.exists(output_path):
            final_size = os.path.getsize(output_path) / (1024 * 1024)
            print(f"\n✅ SUCCÈS ! Taille finale : {final_size:.1f} Mo")

            if final_size > 250:
                print("⚠️ Attention : fichier > 250 Mo (limite Streamable)")
            elif final_size > 25:
                print("📤 Fichier HD : sera uploadé via Streamable si serveur non boosté")

            return True
        else:
            print("❌ Fichier de sortie non créé")
            return False
    
    except Exception as e:
        print(f"\n❌ ERREUR CRITIQUE : {e}")
        traceback.print_exc()
        return False
    
    finally:
        # Nettoyage mémoire
        if clip:
            try:
                clip.close()
            except:
                pass
        if final_clip:
            try:
                final_clip.close()
            except:
                pass

# ═══════════════════════════════════════════════════════════════════════════════
# POINT D'ENTRÉE (TEST)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("🧪 Mode test du maker")
    
    # Test avec un fichier local
    test_input = "test_clip.mp4"
    test_output = "test_tiktok.mp4"
    
    if os.path.exists(test_input):
        success = create_tiktok(test_input, test_output)
        print(f"\nRésultat : {'✅ Succès' if success else '❌ Échec'}")
    else:
        print(f"⚠️ Fichier de test '{test_input}' non trouvé")
        print("   Place un fichier vidéo nommé 'test_clip.mp4' pour tester")