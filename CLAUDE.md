# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MAnaty (AutoClipper) is a Discord bot that converts Twitch clips into TikTok-optimized vertical videos (1080x1920). It detects Twitch clip URLs, downloads them, intelligently crops webcam and gameplay, generates Hormozi-style animated subtitles, and uploads the result.

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

```env
DISCORD_TOKEN=           # Discord bot token (required)
CHANNEL_INPUT_ID=        # Channel ID to monitor for clips (required)
CHANNEL_OUTPUT_ID=       # Channel ID for output videos (required)
STREAMABLE_USER=         # Streamable credentials (optional, for large files)
STREAMABLE_PASS=
ASSEMBLYAI_API_KEY=      # AssemblyAI API key (optional, falls back to Whisper)
```

## Architecture

### Entry Point
- `app/bot.py` - Discord bot that listens for Twitch clip URLs in the input channel

### Video Processing Pipeline (`app/maker.py`)
1. **Download** - `download_clip()` uses yt-dlp to fetch Twitch clips
2. **Person Detection** - `detect_person_multiframe()` uses YOLO v8 to locate webcam position via multi-frame analysis with zone voting
3. **Video Assembly** - Crops webcam (35% height) and gameplay (65% height), assembles vertically
4. **Transcription** - Uses AssemblyAI (if API key provided) or Whisper locally
5. **Subtitles** - `render_hormozi_subtitle()` creates word-by-word animated subtitles with Pillow
6. **Export** - Adaptive bitrate compression targeting ~100MB output

### Key Configuration (`Config` class in maker.py)
- `FINAL_W/H`: 1080x1920 (TikTok format)
- `CAM_RATIO`: 0.35 (webcam takes 35% of height)
- `GAMEPLAY_ASPECT`: 0.70 (gameplay zoom factor)
- `WHISPER_MODEL`: "large" (transcription quality)
- `YOLO_MODEL`: "yolov8n.pt" (fast person detection)

### External Dependencies
- FFmpeg must be installed and in PATH
- YOLO model file `app/yolov8n.pt` is required
- Custom fonts in `obelix-pro/` directory (falls back to system fonts)

## Key Functions

- `maker.download_clip(url, output_path)` - Downloads a Twitch clip
- `maker.create_tiktok(input_path, output_path)` - Full video processing pipeline
- `maker.detect_person_multiframe(video_path)` - YOLO-based webcam detection
- `maker.transcribe_video(video_path)` - Audio transcription with word timing
