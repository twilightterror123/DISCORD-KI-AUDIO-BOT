import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
MAX_FILE_SIZE = 25 * 1024 * 1024
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".opus"}

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def process_audio(source: Path, output: Path) -> None:
    """Mastert die Audiodatei lokal mit FFmpeg und erstellt eine MP3."""
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

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(source), "-vn", "-af", filters,
        "-map_metadata", "0", "-codec:a", "libmp3lame", "-b:a", "192k",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or "FFmpeg konnte die Datei nicht verarbeiten.")
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("FFmpeg hat keine fertige MP3 erzeugt.")


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")
    print("Audio-Bot ist bereit. MP3 hochladen, dann kommt die fertige MP3 zurück.")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    audio = next(
        (a for a in message.attachments
         if Path(a.filename).suffix.lower() in AUDIO_EXTENSIONS),
        None,
    )

    if audio:
        if audio.size > MAX_FILE_SIZE:
            await message.reply("❌ Die Datei ist zu groß. Maximal 25 MB.")
            return

        async with message.channel.typing():
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    temp = Path(temp_dir)
                    suffix = Path(audio.filename).suffix.lower()
                    source = temp / f"input{suffix}"
                    output = temp / "mastered.mp3"

                    await audio.save(source)
                    await asyncio.to_thread(process_audio, source, output)

                    await message.reply(
                        "✅ Fertig — hier ist deine automatisch bearbeitete MP3:",
                        file=discord.File(output, filename="mastered.mp3"),
                    )
            except Exception as error:
                print(f"Audio-Fehler: {error}")
                await message.reply(f"❌ Verarbeitung fehlgeschlagen: `{error}`")

    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")

bot.run(TOKEN)
