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
        raise RuntimeError("FFmpeg ist nicht installiert. Installiere es mit: sudo apt install ffmpeg")
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not allow_error:
        raise RuntimeError(result.stderr.strip()[-1800:] or "FFmpeg-Fehler")
    return result


def probe_duration(source):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(source),
        ], capture_output=True, text=True,
    )
    try:
        return max(1.0, float(result.stdout.strip()))
    except ValueError:
        return 180.0


def detect_peak(source):
    result = run_ffmpeg(
        ["-i", str(source), "-af", "volumedetect", "-f", "null", "-"],
        allow_error=True,
    )
    for line in result.stderr.splitlines():
        if "max_volume:" in line:
            try:
                return float(line.split("max_volume:", 1)[1].split("dB", 1)[0].strip())
            except ValueError:
                pass
    return -12.0


def bass_gain(value):
    return {"wenig": -1.0, "mittel": 1.5, "viel": 4.0}[value]


def loudness_target(value):
    return {"leise": -18, "normal": -14, "laut": -10}[value]


def master_filter(bass="mittel", loudness="normal", vocal="klar"):
    bass_db = bass_gain(bass)
    target = loudness_target(loudness)
    vocal_db = 1.8 if vocal == "klar" else 0.0
    return (
        "highpass=f=28,lowpass=f=19500,"
        f"equalizer=f=55:t=q:w=0.8:g={bass_db},"
        "equalizer=f=110:t=q:w=0.9:g=1.0,"
        "equalizer=f=250:t=q:w=1:g=-2.0,"
        "equalizer=f=650:t=q:w=1:g=-1.0,"
        f"equalizer=f=2500:t=q:w=1:g={vocal_db},"
        "equalizer=f=5000:t=q:w=1:g=1.2,"
        "equalizer=f=10500:t=q:w=0.8:g=1.0,"
        "acompressor=threshold=-24dB:ratio=2.2:attack=18:release=160:makeup=1,"
        "stereotools=mlev=1.02:slev=1.02,"
        "alimiter=limit=0.96:attack=5:release=90,"
        f"loudnorm=I={target}:TP=-1.2:LRA=9"
    )


def render_master(source, output, bass, loudness, vocal):
    run_ffmpeg([
        "-i", str(source), "-vn", "-af", master_filter(bass, loudness, vocal),
        "-map_metadata", "0", "-codec:a", "libmp3lame", "-b:a", "320k", str(output),
    ])


def render_remix(first, second, output, bass, loudness, mode):
    duration_a = probe_duration(first)
    duration_b = probe_duration(second)
    target = loudness_target(loudness)
    bass_db = bass_gain(bass)

    # Struktur statt stumpfem Vollsong-Overlay:
    # intro A -> Übergang A/B -> Hauptteil B -> kurzer gemeinsamer Outro-Mix.
    if mode == "mashup":
        a_end = min(35.0, duration_a * 0.28)
        b_start = min(20.0, max(0.0, duration_b * 0.08))
        b_end = min(duration_b, b_start + max(45.0, duration_a * 0.45))
        fade = 5.0
        filter_complex = (
            f"[0:a]atrim=start=0:end={a_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[a];"
            f"[1:a]atrim=start={b_start}:end={b_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[b];"
            f"[a][b]acrossfade=d={fade}:c1=tri:c2=tri,"
            f"{master_filter(bass, loudness, 'klar')}[out]"
        )
    elif mode == "transition":
        a_end = min(60.0, duration_a)
        b_start = min(30.0, duration_b * 0.15)
        b_end = min(duration_b, b_start + 90.0)
        filter_complex = (
            f"[0:a]atrim=0:{a_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[a];"
            f"[1:a]atrim={b_start}:{b_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[b];"
            "[a][b]acrossfade=d=8:c1=exp:c2=exp,"
            f"{master_filter(bass, loudness, 'klar')}[out]"
        )
    else:
        # Beat mode: rhythmisch wirkender, kurzer Wechsel mit Sidechain-artiger Ducking-Kurve.
        a_end = min(32.0, duration_a)
        b_start = min(16.0, duration_b * 0.1)
        b_end = min(duration_b, b_start + 64.0)
        filter_complex = (
            f"[0:a]atrim=0:{a_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[a];"
            f"[1:a]atrim={b_start}:{b_end},asetpts=PTS-STARTPTS,"
            f"loudnorm=I={target}:TP=-2:LRA=11[b];"
            "[a]volume='if(lt(mod(t,4),0.5),0.55,1)':eval=frame[ad];"
            "[b]volume='if(lt(mod(t,4),0.5),1,0.72)':eval=frame[bd];"
            "[ad][bd]amix=inputs=2:duration=longest:dropout_transition=2:normalize=1,"
            f"{master_filter(bass, loudness, 'klar')}[out]"
        )

    run_ffmpeg([
        "-i", str(first), "-i", str(second),
        "-filter_complex", filter_complex, "-map", "[out]",
        "-codec:a", "libmp3lame", "-b:a", "320k", str(output),
    ])


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


@bot.tree.command(name="master", description="Song sauber mastern mit Bass-, Lautstärke- und Vocal-Auswahl")
@app_commands.describe(audio="Eine Audiodatei", bass="Bass-Stärke", lautstaerke="Ausgabe-Lautstärke", vocals="Vocal-Klang")
@app_commands.choices(
    bass=choices(["wenig", "mittel", "viel"]),
    lautstaerke=choices(["leise", "normal", "laut"]),
    vocals=choices(["klar", "neutral"]),
)
async def master(interaction: discord.Interaction, audio: discord.Attachment, bass: app_commands.Choice[str], lautstaerke: app_commands.Choice[str], vocals: app_commands.Choice[str]):
    await interaction.response.defer()
    try:
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / ("input" + Path(audio.filename).suffix.lower())
            output = folder / "mastered.mp3"
            await save_attachment(audio, source)
            await asyncio.to_thread(render_master, source, output, bass.value, lautstaerke.value, vocals.value)
            await interaction.followup.send(
                f"✅ Master fertig | Bass: {bass.name} | Lautstärke: {lautstaerke.name} | Vocals: {vocals.name}",
                file=discord.File(output, "mastered.mp3"),
            )
    except Exception as error:
        await interaction.followup.send(f"❌ Fehler: `{error}`")


@bot.tree.command(name="remix", description="Erzeugt einen strukturierten Remix statt beide Songs stumpf zu stapeln")
@app_commands.describe(first="Song 1", second="Song 2", bass="Bass-Stärke", lautstaerke="Ausgabe-Lautstärke", modus="Remix-Modus")
@app_commands.choices(
    bass=choices(["wenig", "mittel", "viel"]),
    lautstaerke=choices(["leise", "normal", "laut"]),
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
            await interaction.followup.send(
                f"🔥 Remix fertig | Modus: {modus.name} | Bass: {bass.name} | Lautstärke: {lautstaerke.name}",
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
