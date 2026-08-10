import json
import os
import re
import shutil
import subprocess
import sys
import time

from nettoyage import nettoyer

BASE = os.path.dirname(os.path.abspath(__file__))
FFMPEG = os.path.join(BASE, "tools", "ffmpeg")
JOBS = os.path.join(BASE, "data", "jobs")
LOCK = os.path.join(BASE, "data", "worker.lock")
PY = sys.executable

STEMS = [
    ("drums", "Batterie", "🥁"),
    ("bass", "808 - Basse", "🔊"),
    ("guitar", "Guitare", "🎸"),
    ("piano", "Piano", "🎹"),
    ("other", "Autres instruments", "🎻"),
    ("vocals", "Voix", "🎤"),
]

os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("PYTHONUNBUFFERED", "1")


def status(job_id, **fields):
    path = os.path.join(JOBS, job_id, "status.json")
    data = {"status": "queued", "step": "file", "progress": 0, "message": "", "stems": [], "error": None}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    data.update(fields)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def run(cmd, job_id=None, progress_from=None, progress_to=None, parse_pct=False, cwd=None):
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, text=True, cwd=cwd
    )
    last = -1
    for line in proc.stdout:
        if job_id and parse_pct:
            m = re.search(r"(\d+)%", line)
            if m:
                v = int(m.group(1))
                if v != last:
                    last = v
                    pct = progress_from + (progress_to - progress_from) * v / 100.0
                    status(job_id, progress=round(pct))
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"commande en échec: {' '.join(cmd[:5])}...")


def acquire_lock():
    while True:
        if not os.path.exists(LOCK):
            break
        try:
            with open(LOCK) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            time.sleep(3)
        except (OSError, ValueError):
            os.remove(LOCK)
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))


def release_lock():
    try:
        os.remove(LOCK)
    except OSError:
        pass


def find_job_dir(job_id):
    jdir = os.path.join(JOBS, job_id)
    for name in os.listdir(jdir):
        if name.startswith("input."):
            return jdir, name
    return jdir, "input.mp3"


def process(job_id):
    jdir, input_name = find_job_dir(job_id)
    input_path = os.path.join(jdir, input_name)
    status(job_id, status="separating", step="decode", progress=2, message="Lecture du fichier audio…")

    wav_path = os.path.join(jdir, "input.wav")
    if not os.path.splitext(input_path)[1].lower() == ".wav":
        run([FFMPEG, "-y", "-i", input_path, "-ar", "44100", "-ac", "2", wav_path], job_id, 2, 5)
    else:
        run([FFMPEG, "-y", "-i", input_path, "-ar", "44100", "-ac", "2", wav_path], job_id, 2, 5)

    try:
        import torch
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    except Exception:
        device = "cpu"

    status(job_id, status="separating", step="demucs", progress=5, message="Séparation des instruments par l'IA (Demucs)…")
    stems_dir = os.path.join(jdir, "stems")
    acquire_lock()
    try:
        run(
            [PY, "-m", "demucs.separate", "-n", "htdemucs_6s", "--device", device,
             "--shifts", "2", "--overlap", "0.4", "-o", stems_dir, wav_path],
            job_id, 5, 55, parse_pct=True,
        )
    finally:
        release_lock()

    stem_wavs = {}
    if not os.path.exists(stems_dir):
        raise RuntimeError("Demucs n'a produit aucun fichier")
    for root, _dirs, files in os.walk(stems_dir):
        for name in files:
            if name.endswith((".wav", ".mp3")):
                stem_wavs[name.split(".")[0]] = os.path.join(root, name)

    done = []
    onnx_model = os.path.join(BASE, ".venv", "lib", "python3.11", "site-packages", "basic_pitch", "saved_models", "icassp_2022", "nmp.onnx")
    total = len(STEMS)
    for i, (key, label, emoji) in enumerate(STEMS):
        base = 55 + int(i * 40 / total)
        nxt = 55 + int((i + 1) * 40 / total)
        status(job_id, status="transcribing", step=key, progress=base, message=f"Transcription MIDI : {label}…")
        src = stem_wavs.get(key)
        if not src:
            continue
        mono = os.path.join(jdir, f"{key}_22050.wav")
        run([FFMPEG, "-y", "-i", src, "-ar", "22050", "-ac", "1", mono], job_id, base, base + 20)
        mid_dir = os.path.join(jdir, "midi")
        os.makedirs(mid_dir, exist_ok=True)
        mid_path = os.path.join(jdir, f"{key}.mid")

        if key == "piano":
            try:
                import torch
                from piano_transcription_inference import PianoTranscription, sample_rate, load_audio
                piano16 = os.path.join(jdir, f"{key}_16000.wav")
                run([FFMPEG, "-y", "-i", src, "-ar", str(sample_rate), "-ac", "1", piano16])
                audio, _ = load_audio(piano16, sr=sample_rate, mono=True)
                tdev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
                transcriber = PianoTranscription(device=tdev, checkpoint_path=None)
                transcriber.transcribe(audio, mid_path)
                os.remove(piano16)
            except Exception:
                run([PY, "-m", "basic_pitch.predict", "--model-path", onnx_model, "--save-midi", mid_dir, mono])
                midis = [n for n in os.listdir(mid_dir) if n.endswith(".mid")]
                if midis:
                    shutil.move(os.path.join(mid_dir, midis[0]), mid_path)
        else:
            run([PY, "-m", "basic_pitch.predict", "--model-path", onnx_model, "--save-midi", mid_dir, mono])
            midis = [n for n in os.listdir(mid_dir) if n.endswith(".mid")]
            if midis:
                shutil.move(os.path.join(mid_dir, midis[0]), mid_path)

        if os.path.exists(mid_path):
            nettoyer(mid_path, key)

        mp3_path = os.path.join(jdir, f"{key}.mp3")
        run([FFMPEG, "-y", "-i", src, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ac", "2",
             "-codec:a", "libmp3lame", "-b:a", "160k", mp3_path])
        os.remove(mono)
        size = os.path.getsize(mp3_path) if os.path.exists(mp3_path) else 0
        has_midi = os.path.exists(mid_path)
        done.append({"key": key, "label": label, "emoji": emoji, "size": size, "midi": has_midi})
        status(job_id, progress=nxt)

    for path in [wav_path]:
        try:
            os.remove(path)
        except OSError:
            pass
    try:
        shutil.rmtree(stems_dir)
    except OSError:
        pass

    status(job_id, status="done", step="done", progress=100, message="Terminé !", stems=done)


def main():
    job_id = sys.argv[1]
    try:
        status(job_id, status="separating", progress=1, message="Démarrage…")
        process(job_id)
    except Exception as exc:
        status(job_id, status="error", error=str(exc))


if __name__ == "__main__":
    main()