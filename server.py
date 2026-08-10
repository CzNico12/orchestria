import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from io import BytesIO

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

BASE = os.path.dirname(os.path.abspath(__file__))
JOBS = os.path.join(BASE, "data", "jobs")
STATIC = os.path.join(BASE, "static")
ALLOWED = {"mp3", "wav", "ogg", "flac", "m4a", "aac"}
MAX_BYTES = 200 * 1024 * 1024
KEEP_HOURS = 24


def cleanup_old_jobs():
    if not os.path.isdir(JOBS):
        return
    now = time.time()
    for name in os.listdir(JOBS):
        path = os.path.join(JOBS, name)
        try:
            if now - os.path.getmtime(path) > KEEP_HOURS * 3600:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


@asynccontextmanager
async def lifespan(_app):
    cleanup_old_jobs()
    yield


app = FastAPI(lifespan=lifespan)


def job_dir(job_id):
    path = os.path.join(JOBS, job_id)
    if not os.path.isdir(path) or not job_id.isalnum():
        raise HTTPException(404, "Analyse introuvable")
    return path


def read_status(job_id):
    path = os.path.join(job_dir(job_id), "status.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    name = file.filename or "audio"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED:
        raise HTTPException(400, "Format non supporté. Utilise un fichier MP3, WAV, OGG, FLAC, M4A ou AAC.")

    job_id = uuid.uuid4().hex[:12]
    path = os.path.join(JOBS, job_id, f"input.{ext}")
    os.makedirs(os.path.dirname(path), exist_ok=True)

    total = 0
    with open(path, "wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_BYTES:
                raise HTTPException(413, "Fichier trop lourd (max 200 Mo).")
            out.write(chunk)

    status_path = os.path.join(os.path.dirname(path), "status.json")
    with open(status_path, "w", encoding="utf-8") as f:
        json.dump({"status": "queued", "step": "file", "progress": 0, "message": "Fichier reçu, démarrage…", "stems": [], "error": None}, f)

    subprocess.Popen(
        [sys.executable, os.path.join(BASE, "worker.py"), job_id],
        start_new_session=True,
    )
    return {"job": job_id, "name": name}


@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    data = read_status(job_id)
    if data is None:
        raise HTTPException(404, "Analyse introuvable")
    return data


@app.get("/api/file/{job_id}/{stem}.{fmt}")
def get_file(job_id: str, stem: str, fmt: str):
    job_dir(job_id)
    if fmt == "mp3":
        path = os.path.join(JOBS, job_id, f"{stem}.mp3")
        media = "audio/mpeg"
    elif fmt == "mid" or fmt == "midi":
        path = os.path.join(JOBS, job_id, f"{stem}.mid")
        media = "audio/midi"
    else:
        raise HTTPException(400, "Format inconnu")
    if not os.path.exists(path):
        raise HTTPException(404, "Fichier pas encore prêt")
    return FileResponse(path, media_type=media, filename=f"{stem}.{fmt}")


@app.get("/api/zip/{job_id}")
def get_zip(job_id: str):
    jdir = job_dir(job_id)
    data = read_status(job_id)
    if data is None or data.get("status") != "done":
        raise HTTPException(400, "Analyse pas encore terminée")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for stem in data.get("stems", []):
            key = stem["key"]
            for fmt in ("mp3", "mid"):
                path = os.path.join(jdir, f"{key}.{fmt}")
                if os.path.exists(path):
                    zf.write(path, f"{key}.{fmt}")
    buffer.seek(0)
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="separation-{job_id}.zip"'},
    )


app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")