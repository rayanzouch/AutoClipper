#bot.py
import discord
import os
import requests
from dotenv import load_dotenv
import maker as maker
import asyncio

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
# On s'assure que les IDs sont bien des entiers (int)
CHANNEL_INPUT = int(os.getenv('CHANNEL_INPUT_ID'))
CHANNEL_OUTPUT = int(os.getenv('CHANNEL_OUTPUT_ID'))
# Streamable (compte gratuit requis : https://streamable.com)
STREAMABLE_USER = os.getenv('STREAMABLE_USER')
STREAMABLE_PASS = os.getenv('STREAMABLE_PASS')

# --- FONCTION UPLOAD STREAMABLE ---
def upload_to_streamable(file_path):
    """
    Upload une vidéo sur Streamable et retourne l'URL.
    Nécessite un compte gratuit sur https://streamable.com
    """
    if not STREAMABLE_USER or not STREAMABLE_PASS:
        print("⚠️ Credentials Streamable manquants dans .env")
        return None

    try:
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
                return f"https://streamable.com/{shortcode}"

        print(f"❌ Erreur Streamable : {response.status_code} - {response.text}")
        return None

    except Exception as e:
        print(f"❌ Erreur upload Streamable : {e}")
        return None

async def send_video(channel, file_path, message, twitch_url):
    """
    Envoie la vidéo sur Streamable (toujours, pour la qualité HD).
    """
    file_size = os.path.getsize(file_path)
    msg_base = f"🎬 **TikTok Prêt !**\n👤 Source : {message.author.mention}\n🔗 Original : <{twitch_url}>"

    print(f"📤 Upload Streamable ({file_size / 1024 / 1024:.1f} Mo)...")

    loop = asyncio.get_event_loop()
    streamable_url = await loop.run_in_executor(None, upload_to_streamable, file_path)

    if streamable_url:
        msg = f"{msg_base}\n\n🎥 **Vidéo HD** : {streamable_url}"
        await channel.send(content=msg)
        return True
    else:
        # Fallback Discord si Streamable échoue
        print("⚠️ Streamable échoué, tentative Discord...")
        try:
            await channel.send(content=msg_base, file=discord.File(file_path))
            return True
        except discord.HTTPException as e:
            print(f"❌ Upload impossible : {e}")
            await channel.send(f"{msg_base}\n\n❌ Erreur upload. Vérifie les credentials Streamable dans .env")
            return False

# --- INITALISATION DU BOT ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
    print(f'🤖 Bot connecté en tant que {client.user} !')
    print(f'👀 Surveillance du salon : {CHANNEL_INPUT}')

@client.event
async def on_message(message):
    if message.author == client.user: return

    # On vérifie si on est dans le bon salon
    if message.channel.id == CHANNEL_INPUT:
        
        if "twitch.tv" in message.content and "/clip/" in message.content:
            words = message.content.split()
            twitch_url = next((w for w in words if "twitch.tv" in w and "/clip/" in w), None)

            if twitch_url:
                print(f"✨ Clip détecté : {twitch_url}")
                await message.add_reaction("👀")
                
                temp_input = f"raw_{message.id}.mp4"
                temp_output = f"tiktok_{message.id}.mp4"

                try:
                    loop = asyncio.get_event_loop()
                    
                    # 1. Téléchargement
                    download_success = await loop.run_in_executor(None, maker.download_clip, twitch_url, temp_input)
                    
                    if download_success:
                        # 2. Montage
                        montage_success = await loop.run_in_executor(None, maker.create_tiktok, temp_input, temp_output)
                        
                        if montage_success:
                            # 3. Envoi (Discord ou Streamable selon la taille)
                            output_channel = client.get_channel(CHANNEL_OUTPUT)
                            if output_channel:
                                send_success = await send_video(output_channel, temp_output, message, twitch_url)

                                if send_success:
                                    await message.add_reaction("✅")
                                    print("✅ Vidéo envoyée !")
                                else:
                                    await message.add_reaction("⚠️")
                            else:
                                print("❌ Erreur : Salon de sortie introuvable ID incorrect dans .env")
                        else:
                            await message.add_reaction("⚠️")
                    else:
                        await message.add_reaction("❌")

                except Exception as e:
                    print(f"❌ ERREUR CRITIQUE : {e}\n(Vérifie que ton bot a la permission d'envoyer des fichiers dans le salon de sortie !)")
                    await message.add_reaction("💀")
                
                finally:
                    if os.path.exists(temp_input): os.remove(temp_input)
                    if os.path.exists(temp_output): os.remove(temp_output)

if TOKEN:
    client.run(TOKEN)
else:
    print("❌ ERREUR : Le Token est vide dans le fichier .env !")