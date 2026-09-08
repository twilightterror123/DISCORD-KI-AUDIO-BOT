import os
import subprocess
import tempfile
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
MAX_FILE_SIZE = 25 * 1024 * 1024

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)


def process_audio(source: Path, output: Path) -> None:
    filters = (
        "highpass=f=25,lowpass=f=19000,"
        "equalizer=f=90:t=q:w=1:g=2,equalizer=f=250:t=q:w=1:g=-1.5,"
        "equalizer=f=3500:t=q:w=1:g=1.2,"
        "acompressor=threshold=-18dB:ratio=2.2:attack=15:release=120:makeup=1,"
        "stereotools=mlev=0.9,alimiter=limit=0.95:attack=5:release=50,"
        "loudnorm=I=-14:TP=-1.5:LRA=11"
    )
    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(source), "-af", filters,
        "-codec:a", "libmp3lame", "-b:a", "192k", str(output)
    ], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    audio = next((a for a in message.attachments if Path(a.filename).suffix.lower() in
                  {".mp3", ".wav", ".m4a", ".flac", ".ogg"}), None)
    if audio:
        if audio.size > MAX_FILE_SIZE:
            await message.reply("Die Datei ist zu groß. Maximal 25 MB.")
            return
        async with message.channel.typing():
            try:
                with tempfile.TemporaryDirectory() as temp:
                    temp = Path(temp)
                    source = temp / f"input{Path(audio.filename).suffix.lower()}"
                    output = temp / "mastered.mp3"
                    await audio.save(source)
                    process_audio(source, output)
                    await message.reply("✅ Fertig — automatisch bearbeitet.",
                                        file=discord.File(output, filename="mastered.mp3"))
            except Exception as error:
                await message.reply(f"❌ Fehler: `{error}`")
    await bot.process_commands(message)


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")
bot.run(TOKEN)
