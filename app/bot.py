#bot.py
"""
BOT DISCORD - MAnaty (AutoClipper)
==================================
Bot Discord qui convertit les clips Twitch en vidéos verticales (format TikTok/Reels).
Utilise Streamable pour les fichiers > 25 Mo.
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

# Seuil pour utiliser Streamable (Discord limite à 25 Mo)
DISCORD_FILE_LIMIT_MB = 25


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
    """
    Envoie la vidéo sur Discord.
    Si le fichier est > 25 Mo, utilise Streamable.
    """
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    msg_content = f"**Video prete !**\nSource : {message.author.mention}\nOriginal : <{twitch_url}>"

    # Fichier volumineux → Streamable
    if file_size_mb > DISCORD_FILE_LIMIT_MB:
        print(f"Fichier volumineux ({file_size_mb:.1f} Mo), utilisation de Streamable...")

        loop = asyncio.get_event_loop()
        streamable_url = await loop.run_in_executor(None, upload_to_streamable, file_path)

        if streamable_url:
            await channel.send(f"{msg_content}\n\n**Video HD** : {streamable_url}")
            return True
        else:
            # Fallback : essayer Discord quand même (échouera si serveur non boosté)
            print("Streamable echoue, tentative Discord...")

    # Fichier petit ou fallback → Discord direct
    print(f"Envoi Discord ({file_size_mb:.1f} Mo)...")

    try:
        await channel.send(
            content=msg_content,
            file=discord.File(file_path)
        )
        return True

    except discord.HTTPException as e:
        if e.status == 413:  # Fichier trop gros
            print(f"Fichier trop volumineux pour Discord ({file_size_mb:.1f} Mo)")
            await channel.send(
                f"{msg_content}\n\n⚠️ Fichier trop volumineux ({file_size_mb:.1f} Mo).\n"
                f"Configure Streamable dans .env pour les gros fichiers."
            )
        else:
            print(f"Erreur Discord: {e}")
            await channel.send(f"{msg_content}\n\n⚠️ Erreur lors de l'envoi")
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
        print(f'Streamable : configure (fichiers > {DISCORD_FILE_LIMIT_MB} Mo)')
    else:
        print(f'Streamable : non configure (limite Discord {DISCORD_FILE_LIMIT_MB} Mo)')


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
                    if os.path.exists(temp_output):
                        os.remove(temp_output)


if TOKEN:
    client.run(TOKEN)
else:
    print("ERREUR : Le Token est vide dans le fichier .env !")
