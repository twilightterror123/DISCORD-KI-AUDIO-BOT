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
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg-Fehler")


# Kräftiges, aber kontrolliertes Mastering: Sub-Bass, Kick, Präsenz,
# Saturation, Chorus, Reverb, Stereo-Breite, Kompression und Limiter.
MASTER_FILTERS = (
    "highpass=f=25,"
    "lowpass=f=19500,"
    "equalizer=f=45:t=q:w=0.8:g=4,"
    "equalizer=f=65:t=q:w=0.8:g=6,"
    "equalizer=f=95:t=q:w=0.9:g=5,"
    "equalizer=f=160:t=q:w=1:g=2.5,"
    "equalizer=f=280:t=q:w=1:g=-4,"
    "equalizer=f=650:t=q:w=1:g=-2,"
    "equalizer=f=2200:t=q:w=1:g=2.5,"
    "equalizer=f=4200:t=q:w=1:g=3,"
    "equalizer=f=9000:t=q:w=0.8:g=4,"
    "acompressor=threshold=-25dB:ratio=4.5:attack=6:release=100:makeup=4,"
    "acompressor=threshold=-18dB:ratio=2:attack=20:release=180:makeup=2,"
    "acrusher=bits=16:mix=0.08,"
    "aecho=0.85:0.72:650:0.30,"
    "chorus=0.5:0.9:50:0.35:0.25:2,"
    "stereotools=mlev=1.12:slev=1.08,"
    "alimiter=limit=0.96:attack=5:release=65,"
    "loudnorm=I=-11:TP=-1.0:LRA=7"
)


def process_audio(source, output, remix=False, second=None):
    if remix:
        # Zwei Songs werden parallel gemischt und danach gemeinsam gemastert.
        args = [
            "-i", str(source),
            "-i", str(second),
            "-filter_complex",
            f"[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=3,{MASTER_FILTERS}[a]",
            "-map", "[a]",
        ]
    else:
        args = [
            "-i", str(source),
            "-vn",
            "-af", MASTER_FILTERS,
            "-map_metadata", "0",
        ]

    run_ffmpeg(args + [
        "-codec:a", "libmp3lame",
        "-b:a", "320k",
        str(output),
    ])

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


@bot.tree.command(name="master", description="Extremes Bass- und Sound-Mastering mit Reverb")
@app_commands.describe(audio="Eine Audiodatei")
async def master(interaction: discord.Interaction, audio: discord.Attachment):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / ("input" + Path(audio.filename).suffix.lower())
            output = Path(folder) / "mastered.mp3"
            await save_attachment(audio, source)
            await asyncio.to_thread(process_audio, source, output)
            await interaction.followup.send(
                "✅ Fertig: Sub-Bass, Kick, Klarheit, Saturation, Chorus, Reverb und lautes Mastering.",
                file=discord.File(output, "mastered.mp3"),
            )
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.tree.command(name="remix", description="Mischt zwei Songs zu einem kräftigen Bass-Remix")
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
            await interaction.followup.send(
                "🔥 Remix fertig: zwei Songs, fetter Bass, Kick, Reverb, Chorus und Stereo-Sound.",
                file=discord.File(output, "remix.mp3"),
            )
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")

bot.run(TOKEN)
