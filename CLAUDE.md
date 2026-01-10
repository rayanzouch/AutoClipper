# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAnaty (AutoClipper) is a Discord bot that converts Twitch clips into TikTok-optimized vertical videos (1080x1920). It detects Twitch clip URLs, downloads them, intelligently crops webcam and gameplay, adds Twitch branding overlay, generates Hormozi-style animated subtitles, and uploads the result.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the bot
python app/bot.py

# Test video processing directly (requires test_clip.mp4)
python app/maker.py
```

## Required Environment Variables (.env)

Copy `.env.example` to `.env` and fill in the values:

```env
DISCORD_TOKEN=           # Discord bot token (required)
CHANNEL_INPUT_ID=        # Channel ID to monitor for clips (required)
CHANNEL_OUTPUT_ID=       # Channel ID for output videos (required)
STREAMABLE_USER=         # Streamable credentials (optional, for files > 25 Mo)
STREAMABLE_PASS=
ASSEMBLYAI_API_KEY=      # AssemblyAI API key (optional, falls back to Whisper if not set or on error)
```

## Architecture

### Entry Point
- `app/bot.py` - Discord bot that listens for Twitch clip URLs in the input channel, uses Streamable for files > 25 Mo

### Video Processing Pipeline (`app/maker.py`)
1. **Download** - `download_clip()` uses yt-dlp to fetch Twitch clips
2. **Person Detection** - `detect_person_multiframe()` uses YOLO v8 to locate webcam position via multi-frame analysis with zone voting
3. **Video Assembly** - Crops webcam (35% height) and gameplay (65% height), assembles vertically
4. **Twitch Overlay** - `render_twitch_overlay()` adds Twitch logo + @username badge on the webcam zone
5. **Transcription** - `transcribe_video()` uses AssemblyAI (falls back to Whisper on error or if no API key)
6. **Subtitles** - `render_hormozi_subtitle()` creates word-by-word animated subtitles with Pillow (can be disabled via `SUBTITLES_ENABLED`)
7. **Export** - Adaptive bitrate compression targeting ~100 Mo output

### Key Configuration (`Config` class in maker.py)
- `FINAL_W/H`: 1080x1920 (TikTok format)
- `CAM_RATIO`: 0.35 (webcam takes 35% of height)
- `GAMEPLAY_ASPECT`: 0.70 (gameplay zoom factor)
- `WHISPER_MODEL`: "large" (fallback transcription quality)
- `YOLO_MODEL`: "yolov8n.pt" (fast person detection)
- `SUBTITLES_ENABLED`: True (toggle subtitles on/off)
- `TARGET_SIZE_MB`: 100.0 (target file size for compression)

### External Dependencies
- FFmpeg (fourni automatiquement par `imageio-ffmpeg`, pas d'installation manuelle requise)
- YOLO model `yolov8n.pt` (auto-downloaded by ultralytics on first run)
- Custom fonts in `obelix-pro/` directory (falls back to Arial Bold, Impact)

## Key Functions

- `maker.download_clip(url, output_path)` - Downloads a Twitch clip
- `maker.create_tiktok(input_path, output_path, twitch_url)` - Full video processing pipeline
- `maker.detect_person_multiframe(video_path)` - YOLO-based webcam detection with zone voting
- `maker.transcribe_video(video_path)` - Audio transcription via AssemblyAI (fallback: Whisper)
- `maker.extract_twitch_username(url)` - Extracts username from Twitch clip URL
- `maker.render_twitch_overlay(username, cam_width, cam_height)` - Creates Twitch branding overlay
