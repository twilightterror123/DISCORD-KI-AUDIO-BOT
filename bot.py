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
        raise RuntimeError("FFmpeg fehlt. Installiere es mit: sudo apt install ffmpeg")
    result = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *map(str, args)], capture_output=True, text=True)
    if result.returncode and not allow_error:
        raise RuntimeError(result.stderr[-1800:] or "FFmpeg-Fehler")
    return result


def probe_duration(source):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(source)], capture_output=True, text=True)
    try:
        return max(1.0, float(result.stdout.strip()))
    except ValueError:
        return 180.0


def analyse(source):
    try:
        import librosa
        y, sr = librosa.load(str(source), sr=22050, mono=True, duration=180)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo = float(tempo[0] if hasattr(tempo, "__len__") else tempo)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
        return {"bpm": max(60.0, min(180.0, tempo or 120.0)), "key": int(chroma.argmax()), "rms": float(librosa.feature.rms(y=y).mean())}
    except Exception:
        return {"bpm": 120.0, "key": 0, "rms": 0.1}


def loudness_target(value):
    return {"leise": -18, "normal": -14, "laut": -11, "ultra laut": -9}[value]


def bass_gain(value):
    return {"wenig": 1.5, "mittel": 3.0, "viel": 5.0, "bass boost": 7.0}[value]


def master_filter(bass="mittel", loudness="laut"):
    return (
        "highpass=f=28,lowpass=f=19500,"
        f"equalizer=f=55:t=q:w=0.8:g={bass_gain(bass)},"
        "equalizer=f=110:t=q:w=0.9:g=2.0,"
        "equalizer=f=250:t=q:w=1:g=-2.0,"
        "equalizer=f=2500:t=q:w=1:g=1.5,"
        "equalizer=f=6500:t=q:w=1:g=1.2,"
        "acompressor=threshold=-23dB:ratio=2.5:attack=15:release=140:makeup=1,"
        "stereotools=mlev=1.03:slev=1.03,"
        "alimiter=limit=0.94:attack=5:release=90,"
        f"loudnorm=I={loudness_target(loudness)}:TP=-1.0:LRA=8"
    )


def render_master(source, output, bass, loudness):
    run_ffmpeg(["-i", source, "-vn", "-af", master_filter(bass, loudness), "-map_metadata", "0", "-c:a", "libmp3lame", "-b:a", "320k", output])


def render_remix(first, second, output, bass, loudness, mode):
    a = analyse(first)
    b = analyse(second)
    da, db = probe_duration(first), probe_duration(second)
    bpm = (a["bpm"] + b["bpm"]) / 2
    bar = max(1.0, 4 * 60 / bpm)
    phrase = max(8.0, min(32.0, bar * 4))
    fade = min(8.0, phrase / 2)
    if mode == "transition":
        al, bl = min(da, phrase * 8), min(db, phrase * 12)
        start = max(0.0, db - bl)
        fc = f"[0:a]atrim=0:{al},asetpts=PTS-STARTPTS[a];[1:a]atrim={start}:{start+bl},asetpts=PTS-STARTPTS[b];[a][b]acrossfade=d={fade}:c1=exp:c2=exp,{master_filter(bass,loudness)}[o]"
    elif mode == "beat":
        al, bl = min(da, phrase * 8), min(db, phrase * 8)
        start = max(0.0, db - bl)
        fc = f"[0:a]atrim=0:{al},asetpts=PTS-STARTPTS,volume=0.82[a];[1:a]atrim={start}:{start+bl},asetpts=PTS-STARTPTS,volume=0.82[b];[a][b]acrossfade=d={fade}:c1=tri:c2=tri,{master_filter(bass,loudness)}[o]"
    else:
        al, bl = min(da, phrase * 8), min(db, phrase * 16)
        start = max(0.0, db - bl)
        fc = f"[0:a]atrim=0:{al},asetpts=PTS-STARTPTS[a];[1:a]atrim={start}:{start+bl},asetpts=PTS-STARTPTS[b];[a][b]acrossfade=d={fade}:c1=tri:c2=tri,{master_filter(bass,loudness)}[o]"
    run_ffmpeg(["-i", first, "-i", second, "-filter_complex", fc, "-map", "[o]", "-c:a", "libmp3lame", "-b:a", "320k", output])


async def save_attachment(attachment, path):
    if attachment.size > MAX_FILE_SIZE:
        raise RuntimeError("Maximal 25 MB pro Datei.")
    if Path(attachment.filename).suffix.lower() not in AUDIO_EXTENSIONS:
        raise RuntimeError("Erlaubt: MP3, WAV, M4A, FLAC, OGG, AAC und OPUS.")
    await attachment.save(path)


def choices(values):
    return [app_commands.Choice(name=value.capitalize(), value=value) for value in values]


@bot.event
async def on_ready():
    print(f"Eingeloggt als {bot.user}")
    print("Audio-Bot ist bereit.")


@bot.tree.command(name="master", description="Song analysieren, Bass boosten und laut mastern")
@app_commands.describe(audio="Audiodatei", bass="Bass-Stärke", lautstaerke="Lautheitsstufe")
@app_commands.choices(
    bass=choices(["wenig", "mittel", "viel", "bass boost"]),
    lautstaerke=choices(["leise", "normal", "laut", "ultra laut"]),
)
async def master(interaction: discord.Interaction, audio: discord.Attachment, bass: app_commands.Choice[str], lautstaerke: app_commands.Choice[str]):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / ("input" + Path(audio.filename).suffix.lower())
            output = folder / "mastered.mp3"
            await save_attachment(audio, source)
            await asyncio.to_thread(render_master, source, output, bass.value, lautstaerke.value)
            await interaction.followup.send(f"✅ Master fertig | Bass: {bass.name} | Lautheit: {lautstaerke.name}", file=discord.File(output, "mastered.mp3"))
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.tree.command(name="remix", description="Analysierter Remix mit Beat-Phrasen, Übergang und lautem Mastering")
@app_commands.describe(first="Song 1", second="Song 2", bass="Bass-Stärke", lautstaerke="Lautheitsstufe", modus="Remix-Modus")
@app_commands.choices(
    bass=choices(["wenig", "mittel", "viel", "bass boost"]),
    lautstaerke=choices(["leise", "normal", "laut", "ultra laut"]),
    modus=choices(["mashup", "transition", "beat"]),
)
async def remix(interaction: discord.Interaction, first: discord.Attachment, second: discord.Attachment, bass: app_commands.Choice[str], lautstaerke: app_commands.Choice[str], modus: app_commands.Choice[str]):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            first_path = folder / ("first" + Path(first.filename).suffix.lower())
            second_path = folder / ("second" + Path(second.filename).suffix.lower())
            output = folder / "remix.mp3"
            await save_attachment(first, first_path)
            await save_attachment(second, second_path)
            await asyncio.to_thread(render_remix, first_path, second_path, output, bass.value, lautstaerke.value, modus.value)
            await interaction.followup.send(f"🔥 Remix fertig | Modus: {modus.name} | Bass: {bass.name} | Lautheit: {lautstaerke.name}", file=discord.File(output, "remix.mp3"))
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.command()
async def ping(ctx):
    await ctx.send("Pong! Audio-Bot ist online.")


if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt als Umgebungsvariable.")

bot.run(TOKEN)
