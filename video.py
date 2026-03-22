# -*- coding: cp1252 -*-
import os
import time
import subprocess
import psutil
from datetime import datetime
import json
import re

# -------------------- Basis-Konfiguration --------------------
BASE_DIR = r"C:\media-automation"

INPUT_DIR = os.path.join(BASE_DIR, "input")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")

# Optional: direkte Pfade oder einfach "ffmpeg" / "ffprobe", wenn im PATH vorhanden
FFMPEG_EXE = r"ffmpeg"
FFPROBE_EXE = r"ffprobe"

CHECK_INTERVAL = 60  # Sekunden
TARGET_WIDTH = 1920

# -------------------- Encoding Optionen --------------------
NUM_THREADS = 0      # 0 = ffmpeg entscheidet automatisch
CRF = "25"           # Videoqualität / Dateigröße
PRESET = "slow"      # slow / medium / fast
AUDIO_BITRATE = "160k"
LOUDNORM_PARAMS = "I=-23:TP=-2:LRA=11"

# -------------------- Hilfsfunktionen --------------------
def ensure_dirs():
    for d in [INPUT_DIR, TEMP_DIR, OUTPUT_DIR, LOG_DIR]:
        os.makedirs(d, exist_ok=True)


def info(message):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] INFO - {message}"
    print(line)
    logfile = os.path.join(LOG_DIR, f"{datetime.now():%Y-%m-%d}.log")
    with open(logfile, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def ffmpeg_running():
    for p in psutil.process_iter(["name"]):
        try:
            name = p.info["name"]
            if name and "ffmpeg" in name.lower():
                return True
        except Exception:
            continue
    return False


def file_is_free(path):
    try:
        with open(path, "rb"):
            return True
    except IOError:
        return False


def get_video_info(file_path):
    cmd = [
        FFPROBE_EXE,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,field_order",
        "-of", "json",
        file_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="cp1252",
    )
    streams = json.loads(result.stdout).get("streams", [])
    return streams[0] if streams else None


def get_audio_streams(file_path):
    cmd = [
        FFPROBE_EXE,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index,codec_name,bit_rate",
        "-of", "json",
        file_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="cp1252",
    )
    return json.loads(result.stdout).get("streams", [])


def get_duration(file_path):
    cmd = [
        FFPROBE_EXE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1",
        file_path,
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="cp1252",
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def build_ffmpeg_command(input_file, output_file, video_stream, audio_streams):
    vf_filters = []

    field_order = (video_stream.get("field_order") or "").lower()
    if field_order in ["tt", "bb", "tb", "bt"]:
        vf_filters.append("yadif")
        info("Interlaced video erkannt -> Deinterlacing aktiviert.")

    width = int(video_stream.get("width", 0))
    if width < TARGET_WIDTH:
        vf_filters.append(f"scale={TARGET_WIDTH}:-2:flags=lanczos")

    vf_option = ",".join(vf_filters) if vf_filters else None

    audio_cmds = []
    for i, aud in enumerate(audio_streams):
        codec_name = (aud.get("codec_name") or "").lower()

        if codec_name == "ac3":
            audio_cmds.extend([f"-c:a:{i}", "copy"])
        else:
            audio_cmds.extend([
                f"-c:a:{i}", "ac3",
                f"-b:a:{i}", AUDIO_BITRATE,
                f"-filter:a:{i}", f"loudnorm={LOUDNORM_PARAMS}",
            ])

    cmd = [
        FFMPEG_EXE,
        "-i", input_file,
        "-c:v", "libx264",
        "-crf", CRF,
        "-preset", PRESET,
        "-movflags", "+faststart",
        "-threads", str(NUM_THREADS),
    ]

    if vf_option:
        cmd += ["-vf", vf_option]

    cmd += audio_cmds
    cmd.append(output_file)
    return cmd


def set_low_priority(pid):
    try:
        p = psutil.Process(pid)
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    except Exception as e:
        info(f"Fehler beim Setzen der Priorität: {e}")


def cleanup_temp_dir():
    for f in os.listdir(TEMP_DIR):
        path = os.path.join(TEMP_DIR, f)
        if os.path.isfile(path):
            try:
                os.remove(path)
            except Exception as e:
                info(f"Temp-Datei konnte nicht gelöscht werden: {path} ({e})")


# -------------------- Hauptschleife --------------------
def main():
    ensure_dirs()
    info(f"Verarbeitung gestartet: {INPUT_DIR}")

    while True:
        try:
            if ffmpeg_running():
                info("ffmpeg läuft bereits -> warten.")
                time.sleep(CHECK_INTERVAL)
                continue

            files = [
                os.path.join(INPUT_DIR, f)
                for f in os.listdir(INPUT_DIR)
                if os.path.isfile(os.path.join(INPUT_DIR, f))
            ]
            files.sort(key=lambda x: os.path.getmtime(x))

            next_file = None
            for f in files:
                if file_is_free(f):
                    next_file = f
                    break

            if not next_file:
                time.sleep(CHECK_INTERVAL)
                continue

            info(f"Verarbeite Datei: {os.path.basename(next_file)}")

            temp_file = os.path.join(TEMP_DIR, os.path.basename(next_file))
            os.rename(next_file, temp_file)

            video_stream = get_video_info(temp_file)
            if not video_stream:
                info("Kein Videostream gefunden. Datei wird übersprungen.")
                cleanup_temp_dir()
                time.sleep(CHECK_INTERVAL)
                continue

            audio_streams = get_audio_streams(temp_file)
            duration = get_duration(temp_file)

            width = int(video_stream.get("width", 0))
            vcodec = (video_stream.get("codec_name") or "").lower()
            field_order = (video_stream.get("field_order") or "progressive").lower()

            info(f"Video-Codec: {vcodec}, Breite: {width}, Field Order: {field_order}")
            info(f"Audio-Spuren: {len(audio_streams)}, {[a.get('codec_name', 'unknown') for a in audio_streams]}")

            all_audio_copy = all((a.get("codec_name") or "").lower() == "ac3" for a in audio_streams)

            if width >= TARGET_WIDTH and vcodec == "h264" and all_audio_copy and field_order == "progressive":
                info("Alle Streams kompatibel -> verschiebe in Output ohne Konvertierung.")
                final_output = os.path.join(OUTPUT_DIR, os.path.basename(temp_file))
                os.rename(temp_file, final_output)
                time.sleep(CHECK_INTERVAL)
                continue

            output_name = os.path.splitext(os.path.basename(temp_file))[0] + ".mp4"
            final_output = os.path.join(OUTPUT_DIR, output_name)
            temp_output = os.path.join(TEMP_DIR, output_name)

            cmd = build_ffmpeg_command(temp_file, temp_output, video_stream, audio_streams)
            info("Starte Konvertierung...")

            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="cp1252",
                bufsize=1,
            )
            set_low_priority(proc.pid)

            for line in proc.stdout:
                m = re.search(r'time=(\d+):(\d+):(\d+)\.(\d+)', line)
                if m:
                    hours, minutes, seconds, ms = map(int, m.groups())
                    elapsed_sec = hours * 3600 + minutes * 60 + seconds + ms / 100
                    percent = min((elapsed_sec / duration) * 100, 100) if duration > 0 else 0
                    eta = ((elapsed_sec / (percent / 100)) - elapsed_sec) / 60 if percent > 0 else 0
                    print(f"\r{percent:.1f}% fertig, ETA: {eta:.1f} min", end="")

            proc.wait()
            print()

            if proc.returncode != 0:
                info(f"ffmpeg beendet mit Fehlercode {proc.returncode}")
                cleanup_temp_dir()
                time.sleep(CHECK_INTERVAL)
                continue

            os.rename(temp_output, final_output)
            info(f"Konvertierung abgeschlossen: {os.path.basename(final_output)}")

            cleanup_temp_dir()

        except Exception as e:
            info(f"Fehler: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
