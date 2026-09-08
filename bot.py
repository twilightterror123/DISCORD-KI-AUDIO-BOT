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


class AudioBot(commands.Bot):
    async def setup_hook(self):
        synced = await self.tree.sync()
        print(f"{len(synced)} Slash-Commands synchronisiert.")


bot = AudioBot(command_prefix="!", intents=intents)


def run_ffmpeg(args, allow_error=False):
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg ist nicht installiert oder nicht im PATH.")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not allow_error:
        raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg-Fehler")
    return result


def detect_peak(source):
    result = run_ffmpeg(["-i", str(source), "-af", "volumedetect", "-f", "null", "-"], allow_error=True)
    text = result.stderr
    for line in text.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:", 1)[1].split("dB", 1)[0].strip())
            except ValueError:
                pass
    return -12.0


def choose_master_filters(source):
    peak = detect_peak(source)
    # Leiseres Material bekommt etwas mehr Kompression; bereits lautes Material
    # wird nicht unnötig weiter überfahren.
    compression = "acompressor=threshold=-24dB:ratio=2.4:attack=18:release=160:makeup=2"
    if peak > -3:
        compression = "acompressor=threshold=-20dB:ratio=1.8:attack=25:release=180:makeup=1"
    return (
        "highpass=f=28,"
        "lowpass=f=19000,"
        "equalizer=f=55:t=q:w=0.8:g=2.5,"
        "equalizer=f=95:t=q:w=0.9:g=2,"
        "equalizer=f=250:t=q:w=1:g=-2.5,"
        "equalizer=f=700:t=q:w=1:g=-1.5,"
        "equalizer=f=2200:t=q:w=1:g=1.5,"
        "equalizer=f=4500:t=q:w=1:g=1.8,"
        "equalizer=f=10000:t=q:w=0.8:g=1.5,"
        f"{compression},"
        "acrusher=bits=16:mix=0.025,"
        "aecho=0.82:0.18:420:0.08,"
        "chorus=0.35:0.7:35:0.18:0.12:2,"
        "stereotools=mlev=1.04:slev=1.03,"
        "alimiter=limit=0.96:attack=5:release=80,"
        "loudnorm=I=-14:TP=-1.2:LRA=8"
    )


def process_audio(source, output, remix=False, second=None):
    filters = choose_master_filters(source)
    if remix:
        args = [
            "-i", str(source), "-i", str(second),
            "-filter_complex",
            f"[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=3,{filters}[a]",
            "-map", "[a]",
        ]
    else:
        args = ["-i", str(source), "-vn", "-af", filters, "-map_metadata", "0"]
    run_ffmpeg(args + ["-codec:a", "libmp3lame", "-b:a", "320k", str(output)])
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


@bot.tree.command(name="master", description="Automatisches Mastering für den ganzen Song")
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
                "✅ Ganzer Song gemastert: Bass, Klarheit, Dynamik, Stereo und Lautheit automatisch angepasst.",
                file=discord.File(output, "mastered.mp3"),
            )
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.tree.command(name="remix", description="Mischt zwei Songs und mastert das Ergebnis")
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
                "🔥 Remix fertig: beide Songs gemischt und gemeinsam gemastert.",
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
