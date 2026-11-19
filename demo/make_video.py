"""Build the demo video: one screenshot per scene, narrated with Piper TTS, assembled with ffmpeg.

    uv run --no-project --python 3.12 --with piper-tts \
        python demo/make_video.py demo/narration.json docs/screenshots <voice.onnx> whygraph-demo.mp4

Get the voice with `python -m piper.download_voices en_US-joe-medium --data-dir <dir>`.
Each scene shows docs/screenshots/<scene>.png (render them first with demo/render_screens.py) for the
length of its narration plus a short pause. The contest allows at most 2 minutes, so the build fails,
and writes nothing, if the total would run over 120 seconds.
"""
import json
import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

from piper import PiperVoice

LIMIT_S = 120.0
PAUSE_S = 0.8
BG = "0x0f1419"


def run(*cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def main():
    narration, shots, voice_path, out = sys.argv[1:5]
    scenes = json.loads(Path(narration).read_text())
    voice = PiperVoice.load(voice_path)
    with tempfile.TemporaryDirectory() as tmp:
        segs, total = [], 0.0
        for i, s in enumerate(scenes):
            png = Path(shots) / f"{s['scene']}.png"
            if not png.exists():
                sys.exit(f"missing {png}: render the screens first (demo/render_screens.py)")
            wav = Path(tmp) / f"n{i:02d}.wav"
            with wave.open(str(wav), "wb") as w:
                voice.synthesize_wav(s.get("say", s["text"]), w)
            with wave.open(str(wav), "rb") as r:
                dur = r.getnframes() / r.getframerate() + PAUSE_S
            total += dur
            print(f"{s['scene']:<12} {dur:5.2f}s  total {total:6.2f}s")
            segs.append((png, wav, dur))
        if total > LIMIT_S:
            sys.exit(f"video would be {total:.1f}s, over the {LIMIT_S:.0f}s limit; shorten demo/narration.json")
        parts = []
        for i, (png, wav, dur) in enumerate(segs):
            mp4 = Path(tmp) / f"s{i:02d}.mp4"
            run("ffmpeg", "-y", "-loop", "1", "-framerate", "30", "-t", f"{dur:.3f}", "-i", str(png), "-i", str(wav),
                "-filter_complex",
                f"[0]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color={BG},"
                "format=yuv420p[v];[1]aresample=48000,apad[a]",
                "-map", "[v]", "-map", "[a]", "-t", f"{dur:.3f}", "-r", "30",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "128k", "-ac", "1", str(mp4))
            parts.append(mp4)
        listing = Path(tmp) / "list.txt"
        listing.write_text("".join(f"file '{p}'\n" for p in parts))
        tmp_out = Path(tmp) / "out.mp4"
        run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", "-movflags", "+faststart",
            str(tmp_out))
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(tmp_out)], check=True, capture_output=True, text=True)
        length = float(probe.stdout.strip())
        if length > LIMIT_S:
            sys.exit(f"encoded video is {length:.1f}s, over the {LIMIT_S:.0f}s limit")
        os.replace(tmp_out, out)
        print(f"wrote {out}: {length:.1f}s")


if __name__ == "__main__":
    main()
