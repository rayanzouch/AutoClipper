import discord
import os
from dotenv import load_dotenv
import maker as maker
import asyncio

# --- CONFIGURATION ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
# On s'assure que les IDs sont bien des entiers (int)
CHANNEL_INPUT = int(os.getenv('CHANNEL_INPUT_ID'))
CHANNEL_OUTPUT = int(os.getenv('CHANNEL_OUTPUT_ID'))
HISTORY_FILE = "history.txt" # Le fichier mémoire

# --- FONCTIONS UTILITAIRES POUR LA MÉMOIRE ---
def load_history():
    """Charge les liens déjà traités au démarrage"""
    if not os.path.exists(HISTORY_FILE):
        # Crée le fichier s'il n'existe pas
        open(HISTORY_FILE, 'w').close() 
        return set()
    with open(HISTORY_FILE, 'r') as f:
        # On utilise un 'set' pour une recherche ultra-rapide
        return set(line.strip() for line in f if line.strip())

def save_to_history(link):
    """Ajoute un nouveau lien dans la mémoire"""
    with open(HISTORY_FILE, 'a') as f:
        f.write(f"{link}\n")
    # On met aussi à jour la mémoire vive du bot
    processed_links.add(link)

# --- INITALISATION DU BOT ---
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Chargement de la mémoire au démarrage
processed_links = load_history()

@client.event
async def on_ready():
    print(f'🤖 Bot connecté en tant que {client.user} !')
    print(f'🧠 Mémoire chargée : {len(processed_links)} clips déjà traités.')
    print(f'👀 Surveillance du salon : {CHANNEL_INPUT}')

@client.event
async def on_message(message):
    if message.author == client.user: return

    # On vérifie si on est dans le bon salon
    if message.channel.id == CHANNEL_INPUT:
        
        if "twitch.tv" in message.content and "/clip/" in message.content:
            # Extraction propre du lien pour vérifier les doublons
            words = message.content.split()
            twitch_url = next((w for w in words if "twitch.tv" in w and "/clip/" in w), None)
            
            if twitch_url:
                # --- VÉRIFICATION ANTI-DOUBLON ---
                # On nettoie le lien (parfois il y a des ?referrer=... à la fin) pour comparer
                clean_link = twitch_url.split('?')[0]
                
                if clean_link in processed_links:
                    print(f"♻️ Doublon détecté et ignoré : {clean_link}")
                    await message.add_reaction("♻️") # Feedback visuel pour le viewer
                    return # ON ARRÊTE TOUT ICI
                # ----------------------------------

                print(f"✨ Nouveau clip détecté : {twitch_url}")
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
                            # 3. Envoi
                            output_channel = client.get_channel(CHANNEL_OUTPUT)
                            if output_channel:
                                msg = f"🎬 **TikTok Prêt !**\n👤 Source : {message.author.mention}\n🔗 Original : <{twitch_url}>"
                                file = discord.File(temp_output)
                                await output_channel.send(content=msg, file=file)
                                
                                await message.add_reaction("✅")
                                print("✅ Vidéo envoyée !")
                                
                                # --- SAUVEGARDE DANS LA MÉMOIRE ---
                                save_to_history(clean_link)
                                # ----------------------------------
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