import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
MAX_FILE_SIZE = 25 * 1024 * 1024
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus"}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def process_audio(source: Path, output: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg ist nicht installiert oder nicht im PATH.")

    filters = (
        "highpass=f=25,lowpass=f=19000,"
        "equalizer=f=90:t=q:w=1:g=2,"
        "equalizer=f=250:t=q:w=1:g=-1.5,"
        "equalizer=f=3500:t=q:w=1:g=1.2,"
        "acompressor=threshold=-18dB:ratio=2.2:attack=15:release=120:makeup=1,"
        "stereotools=mlev=0.9,"
        "alimiter=limit=0.95:attack=5:release=50,"
        "loudnorm=I=-14:TP=-1.5:LRA=11"
    )

    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-vn", "-af", filters,
        "-map_metadata", "0", "-codec:a", "libmp3lame", "-b:a", "192k",
        str(output),
    ], capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg konnte die Datei nicht verarbeiten.")
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Keine fertige MP3 wurde erzeugt.")


async def make_mp3(attachment: discord.Attachment) -> discord.File:
    if attachment.size > MAX_FILE_SIZE:
        raise RuntimeError("Die Datei ist zu groß. Maximal 25 MB.")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp = Path(temp_dir)
        source = temp / f"input{Path(attachment.filename).suffix.lower()}"
        output = temp / "mastered.mp3"
        await attachment.save(source)
        await asyncio.to_thread(process_audio, source, output)

        # Discord.File muss vor dem Löschen des temporären Ordners erstellt werden.
        return discord.File(output, filename="mastered.mp3")


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")
    print("Audio-Bot ist bereit.")


@bot.event
async def setup_hook():
    synced = await bot.tree.sync()
    print(f"{len(synced)} Slash-Commands synchronisiert.")


@bot.tree.command(name="master", description="Bearbeitet eine Audiodatei und sendet eine fertige MP3 zurück.")
@app_commands.describe(audio="Die MP3 oder andere Audiodatei")
async def master(interaction: discord.Interaction, audio: discord.Attachment):
    suffix = Path(audio.filename).suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        await interaction.response.send_message(
            "❌ Unterstützte Formate: MP3, WAV, M4A, FLAC, OGG, AAC und OPUS.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()
    try:
        file = await make_mp3(audio)
        await interaction.followup.send(
            "✅ Fertig — hier ist deine bearbeitete MP3:",
            file=file,
        )
    except Exception as error:
        print(f"Audio-Fehler: {error}")
        await interaction.followup.send(f"❌ Verarbeitung fehlgeschlagen: `{error}`")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")

bot.run(TOKEN)
