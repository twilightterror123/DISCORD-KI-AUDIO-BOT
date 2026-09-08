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


class AudioBot(commands.Bot):
    async def setup_hook(self):
        synced = await self.tree.sync()
        print(f"{len(synced)} Slash-Commands synchronisiert.")


intents = discord.Intents.default()
intents.message_content = True
bot = AudioBot(command_prefix="!", intents=intents)


def process_audio(source: Path, output: Path) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg ist nicht installiert oder nicht im PATH.")

    # Deutlich hörbarer Beat-Boost: Kick/Bass und Präsenz werden angehoben,
    # Matsch reduziert, anschließend wird sauber komprimiert und begrenzt.
    filters = (
        "highpass=f=28,lowpass=f=19500,"
        "equalizer=f=75:t=q:w=0.9:g=5,"
        "equalizer=f=160:t=q:w=1:g=2,"
        "equalizer=f=280:t=q:w=1:g=-3,"
        "equalizer=f=2500:t=q:w=1:g=2.5,"
        "equalizer=f=9000:t=q:w=0.8:g=3,"
        "acompressor=threshold=-24dB:ratio=4:attack=8:release=100:makeup=3,"
        "stereotools=mlev=0.95,"
        "alimiter=limit=0.97:attack=5:release=50,"
        "loudnorm=I=-11:TP=-1.0:LRA=7"
    )

    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(source), "-vn", "-af", filters,
            "-map_metadata", "0", "-codec:a", "libmp3lame", "-b:a", "192k",
            str(output),
        ],
        capture_output=True,
        text=True,
    )

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
        return discord.File(output, filename="mastered.mp3")


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")
    print("Audio-Bot ist bereit.")


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
            "✅ Fertig — Beat wurde verstärkt und die MP3 gemastert:",
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
