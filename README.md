# AutoClipper

Post a Twitch clip in Discord to get a 1080 × 1920 MP4. AutoClipper uses YOLOv8 to locate the webcam, places it above the gameplay, and highlights each spoken word in yellow. Captions have a black outline and a transparent background.

## Windows setup

Install Python 3.11 and Git. Video export uses H.264 NVENC and requires a compatible NVIDIA GPU and driver. Run these commands in PowerShell.

```powershell
git clone https://github.com/rayanzouch/AutoClipper.git
cd AutoClipper
py -3.11 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt "moviepy==1.0.3" "opencv-python<4.12" "pillow<12"
$ffmpeg = .\venv\Scripts\python.exe -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())"
Copy-Item $ffmpeg .\venv\Scripts\ffmpeg.exe
```

## Configuration

Enable **Message Content Intent** in your Discord bot settings. Create a `.env` file in the project root with your bot token and the numeric IDs of the input and output channels.

```env
DISCORD_TOKEN=
CHANNEL_INPUT_ID=
CHANNEL_OUTPUT_ID=
STREAMABLE_USER=
STREAMABLE_PASS=
ASSEMBLYAI_API_KEY=
```

For Streamable uploads, set `STREAMABLE_USER` to your account email and `STREAMABLE_PASS` to your password. Leave `ASSEMBLYAI_API_KEY` empty to transcribe locally with Whisper. Set it to use AssemblyAI first.

## Run

Double-click `Demarrer-AutoClipper.cmd` and keep the window open. Post a link like `https://www.twitch.tv/channel/clip/slug` in the input channel. 👀 means the bot picked up the clip. ✅ means it delivered the video.

The bot uploads each clip to Streamable and posts the link in the output channel. If the upload fails or Streamable credentials are missing, it sends the MP4 directly when it fits the server's upload limit. If delivery fails, the bot keeps the finished MP4 and prints its path in the console.

## License

MIT
