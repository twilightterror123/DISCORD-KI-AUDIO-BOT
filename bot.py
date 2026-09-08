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


def run_ffmpeg(args):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg ist nicht installiert oder nicht im PATH.")
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg-Fehler")


def process_audio(source, output, remix=False, second=None):
    filters = ("highpass=f=28,lowpass=f=19500,equalizer=f=60:t=q:w=0.8:g=5,equalizer=f=95:t=q:w=0.8:g=5,equalizer=f=180:t=q:w=1:g=2,equalizer=f=300:t=q:w=1:g=-3,equalizer=f=3000:t=q:w=1:g=2.5,equalizer=f=9000:t=q:w=0.8:g=3,acompressor=threshold=-25dB:ratio=4.5:attack=7:release=110:makeup=4,aecho=0.85:0.75:700:0.28,stereotools=mlev=1.15,alimiter=limit=0.95:attack=5:release=60,loudnorm=I=-11:TP=-1.0:LRA=7")
    if remix:
        args = ["-i", str(source), "-i", str(second), "-filter_complex", f"[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=3,{filters}[a]", "-map", "[a]"]
    else:
        args = ["-i", str(source), "-vn", "-af", filters, "-map_metadata", "0"]
    run_ffmpeg(args + ["-codec:a", "libmp3lame", "-b:a", "256k", str(output)])
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Keine fertige MP3 wurde erzeugt.")


async def save_attachment(attachment, path):
    if attachment.size > MAX_FILE_SIZE:
        raise RuntimeError("Eine Datei ist zu groß. Maximal 25 MB pro Datei.")
    if Path(attachment.filename).suffix.lower() not in AUDIO_EXTENSIONS:
        raise RuntimeError("Nur MP3, WAV, M4A, FLAC, OGG, AAC und OPUS werden unterstützt.")
    await attachment.save(path)


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")
    print("Audio-Bot ist bereit.")


@bot.event
async def setup_hook():
    synced = await bot.tree.sync()
    print(f"{len(synced)} Slash-Commands synchronisiert.")


@bot.tree.command(name="master", description="Starker Bass, klarer Sound und hörbarer Reverb")
@app_commands.describe(audio="Eine Audiodatei")
async def master(interaction: discord.Interaction, audio: discord.Attachment):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / ("input" + Path(audio.filename).suffix.lower())
            output = Path(folder) / "mastered.mp3"
            await save_attachment(audio, source)
            await asyncio.to_thread(process_audio, source, output)
            await interaction.followup.send("✅ Fertig: fetter Bass, klarer Sound und hörbarer Reverb.", file=discord.File(output, "mastered.mp3"))
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.tree.command(name="remix", description="Mischt zwei Songs zu einem Bass-Remix")
@app_commands.describe(first="Erster Song", second="Zweiter Song")
async def remix(interaction: discord.Interaction, first: discord.Attachment, second: discord.Attachment):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            first_path = folder / ("first" + Path(first.filename).suffix.lower())
            second_path = folder / ("second" + Path(second.filename).suffix.lower())
            output = folder / "remix.mp3"
            await save_attachment(first, first_path)
            await save_attachment(second, second_path)
            await asyncio.to_thread(process_audio, first_path, output, True, second_path)
            await interaction.followup.send("🔥 Remix fertig — zwei Songs, fetter Bass und hörbarer Reverb.", file=discord.File(output, "remix.mp3"))
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")
bot.run(TOKEN)
