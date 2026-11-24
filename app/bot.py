#bot.py
"""
BOT DISCORD - MAnaty (AutoClipper)
==================================
Bot Discord qui convertit les clips Twitch en vidéos verticales (format TikTok/Reels).
Utilise Streamable en priorité.
"""

import discord
import os
import asyncio
import requests
from dotenv import load_dotenv
import maker as maker

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CHANNEL_INPUT = int(os.getenv('CHANNEL_INPUT_ID'))
CHANNEL_OUTPUT = int(os.getenv('CHANNEL_OUTPUT_ID'))

# Streamable (compte gratuit requis : https://streamable.com)
STREAMABLE_USER = os.getenv('STREAMABLE_USER')
STREAMABLE_PASS = os.getenv('STREAMABLE_PASS')

# ═══════════════════════════════════════════════════════════════════════════════
# FONCTION UPLOAD STREAMABLE
# ═══════════════════════════════════════════════════════════════════════════════

def upload_to_streamable(file_path):
    """
    Upload une vidéo sur Streamable et retourne l'URL.
    Nécessite un compte gratuit sur https://streamable.com
    """
    if not STREAMABLE_USER or not STREAMABLE_PASS:
        print("Credentials Streamable manquants dans .env")
        return None

    try:
        print(f"Upload Streamable en cours...")
        with open(file_path, 'rb') as f:
            response = requests.post(
                'https://api.streamable.com/upload',
                auth=(STREAMABLE_USER, STREAMABLE_PASS),
                files={'file': f},
                timeout=300  # 5 min max pour l'upload
            )

        if response.status_code == 200:
            data = response.json()
            shortcode = data.get('shortcode')
            if shortcode:
                url = f"https://streamable.com/{shortcode}"
                print(f"Upload Streamable reussi : {url}")
                return url

        print(f"Erreur Streamable : {response.status_code} - {response.text}")
        return None

    except Exception as e:
        print(f"Erreur upload Streamable : {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# ENVOI VIDÉO (Discord ou Streamable)
# ═══════════════════════════════════════════════════════════════════════════════

async def send_video(channel, file_path, message, twitch_url):
    msg_content = f"Vidéo de {message.author.mention} · Original <{twitch_url}>"
    url = await asyncio.to_thread(upload_to_streamable, file_path)
    if url:
        await channel.send(f"{msg_content}\n{url}")
        return True
    if os.path.getsize(file_path) <= channel.guild.filesize_limit:
        attachment = discord.File(file_path)
        try:
            await channel.send(content=msg_content, file=attachment)
        finally:
            attachment.close()
        return True
    await channel.send(f"Envoi Streamable impossible. Vidéo conservée sur le PC du bot : {os.path.basename(file_path)}")
    return False


# ═══════════════════════════════════════════════════════════════════════════════
# BOT DISCORD
# ═══════════════════════════════════════════════════════════════════════════════

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


@client.event
async def on_ready():
    print(f'Bot connecte en tant que {client.user} !')
    print(f'Surveillance du salon : {CHANNEL_INPUT}')
    if STREAMABLE_USER and STREAMABLE_PASS:
        print(f'Streamable : configure pour tous les clips')
    else:
        print(f'Streamable : non configure, envoi Discord selon la limite du serveur')


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    # On vérifie si on est dans le bon salon
    if message.channel.id == CHANNEL_INPUT:

        if "twitch.tv" in message.content and "/clip/" in message.content:
            words = message.content.split()
            twitch_url = next((w for w in words if "twitch.tv" in w and "/clip/" in w), None)

            if twitch_url:
                print(f"Clip detecte : {twitch_url}")
                await message.add_reaction("👀")

                temp_input = f"raw_{message.id}.mp4"
                temp_output = f"tiktok_{message.id}.mp4"

                montage_success = send_success = False
                try:
                    loop = asyncio.get_event_loop()

                    # 1. Téléchargement
                    download_success = await loop.run_in_executor(
                        None, maker.download_clip, twitch_url, temp_input
                    )

                    if download_success:
                        # 2. Montage (avec overlay Twitch)
                        montage_success = await loop.run_in_executor(
                            None,
                            lambda: maker.create_tiktok(temp_input, temp_output, twitch_url)
                        )

                        if montage_success:
                            # 3. Envoi (Discord ou Streamable)
                            output_channel = client.get_channel(CHANNEL_OUTPUT)
                            if output_channel:
                                send_success = await send_video(
                                    output_channel, temp_output, message, twitch_url
                                )

                                if send_success:
                                    await message.add_reaction("✅")
                                    print("Video envoyee !")
                                else:
                                    await message.add_reaction("⚠️")
                            else:
                                print("Erreur : Salon de sortie introuvable, ID incorrect dans .env")
                        else:
                            await message.add_reaction("⚠️")
                    else:
                        await message.add_reaction("❌")

                except Exception as e:
                    print(f"ERREUR CRITIQUE : {e}")
                    await message.add_reaction("💀")

                finally:
                    # Nettoyage des fichiers temporaires
                    if os.path.exists(temp_input):
                        os.remove(temp_input)
                    if montage_success and not send_success:
                        print(f"MP4 conservé : {os.path.abspath(temp_output)}")
                    elif os.path.exists(temp_output):
                        os.remove(temp_output)


if TOKEN:
    client.run(TOKEN)
else:
    print("ERREUR : Le Token est vide dans le fichier .env !")
