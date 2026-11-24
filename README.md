# AutoClipper - Twitch to TikTok Bot

Bot Discord qui convertit automatiquement les clips Twitch en videos verticales optimisees pour TikTok/Reels/Shorts.

## Fonctionnalites

- Detecte les liens de clips Twitch dans un salon Discord
- Telecharge le clip en haute qualite
- Detecte intelligemment la position de la webcam (YOLO v8)
- Recadre la video au format 1080x1920 (webcam + gameplay)
- Genere des sous-titres animes style "Hormozi" (mot par mot)
- Envoie la version finale sur Discord ou Streamable

## Technologies

| Composant | Technologie |
|-----------|-------------|
| Bot | Discord.py |
| Telechargement | yt-dlp |
| Montage video | MoviePy + OpenCV |
| Detection webcam | YOLO v8 (ultralytics) |
| Transcription | AssemblyAI / OpenAI Whisper |
| Sous-titres | Pillow (rendu pur Python) |
| Export | FFmpeg |

## Installation sous Windows

La configuration testée utilise Python 3.11 et une carte NVIDIA avec un pilote compatible NVENC. Le montage exporte en H.264 avec cet encodeur. Dans PowerShell, exécuter ces commandes lors de la première installation.

```powershell
git clone https://github.com/rayanzouch/AutoClipper.git
cd AutoClipper
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt "moviepy==1.0.3" "opencv-python<4.12" "pillow<12"
$ffmpeg = .\venv\Scripts\python.exe -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
Copy-Item $ffmpeg .\venv\Scripts\ffmpeg.exe
```

## Configuration

Créer un fichier `.env` à la racine du projet. Renseigner le token du bot et les identifiants numériques des deux salons. Activer **Message Content Intent** dans les réglages Discord du bot pour qu’il puisse lire les liens.

```env
DISCORD_TOKEN=
CHANNEL_INPUT_ID=
CHANNEL_OUTPUT_ID=
STREAMABLE_USER=
STREAMABLE_PASS=
ASSEMBLYAI_API_KEY=
```

- Pour publier sur Streamable, renseigner l’e-mail du compte dans `STREAMABLE_USER` et son mot de passe dans `STREAMABLE_PASS`.
- Pour transcrire en local avec Whisper, laisser `ASSEMBLYAI_API_KEY` vide. Si une clé est renseignée, le bot essaie AssemblyAI en premier.

## Utilisation

Double-cliquer sur `Demarrer-AutoClipper.cmd` et laisser la fenêtre ouverte. Une fois le bot connecté, poster un lien de la forme `https://www.twitch.tv/nom/clip/identifiant` dans le salon d’entrée.

1. Le bot réagit avec 👀, télécharge le clip et produit une vidéo verticale.
2. Il tente d’envoyer chaque vidéo sur Streamable et publie le lien dans le salon de sortie.
3. Si Streamable est indisponible ou non configuré, le bot joint le MP4 lorsque sa taille respecte la limite du serveur Discord.
4. Après une livraison réussie, le bot réagit avec ✅. Si la livraison échoue après le montage, le MP4 reste sur le PC. La console indique son chemin.

## Architecture

```
AutoClipper/
├── app/
│   ├── bot.py          # Bot Discord (point d'entree)
│   ├── maker.py        # Pipeline de traitement video
│   └── yolov8n.pt      # Modele YOLO pour detection
├── obelix-pro/         # Polices pour sous-titres
├── Demarrer-AutoClipper.cmd  # Lanceur Windows
├── requirements.txt
├── .env                # Configuration (a creer)
└── CLAUDE.md           # Documentation technique
```

## Pipeline de traitement

1. **Telechargement** - yt-dlp recupere le clip Twitch
2. **Detection webcam** - YOLO analyse plusieurs frames et vote sur la position
3. **Montage** - Webcam (35%) + Gameplay (65%) assembles verticalement
4. **Transcription** - AssemblyAI ou Whisper genere les timestamps des mots
5. **Sous-titres** - Texte blanc à contour noir sur fond transparent. Le mot prononcé apparaît en jaune.
6. **Export** - Compression adaptative ciblant ~100 Mo

## Licence

MIT
