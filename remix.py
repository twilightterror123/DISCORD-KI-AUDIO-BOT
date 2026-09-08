import subprocess
from pathlib import Path


def create_remix(first: Path, second: Path, output: Path) -> None:
    """Mix two songs with strong bass, clean presence and audible reverb."""
    if subprocess.run(["which", "ffmpeg"], capture_output=True).returncode != 0:
        raise RuntimeError("FFmpeg ist nicht installiert.")

    effects = (
        "highpass=f=28,lowpass=f=19500,"
        "equalizer=f=55:t=q:w=0.8:g=6,"
        "equalizer=f=95:t=q:w=0.9:g=5,"
        "equalizer=f=170:t=q:w=1:g=2.5,"
        "equalizer=f=280:t=q:w=1:g=-3,"
        "equalizer=f=2500:t=q:w=1:g=2.5,"
        "equalizer=f=9000:t=q:w=0.8:g=3,"
        "acompressor=threshold=-23dB:ratio=4:attack=8:release=110:makeup=3,"
        "aecho=0.8:0.75:700:0.28,"
        "alimiter=limit=0.96:attack=5:release=50,"
        "loudnorm=I=-11:TP=-1.0:LRA=7"
    )

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(first), "-i", str(second),
        "-filter_complex",
        "[0:a][1:a]amix=inputs=2:duration=longest:dropout_transition=2," + effects,
        "-vn", "-codec:a", "libmp3lame", "-b:a", "256k", str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-1500:] or "Remix konnte nicht erstellt werden.")
