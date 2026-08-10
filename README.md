# Démix · MP3 → Instruments séparés → MIDI

Site local qui découpe un morceau de musique (MP3, WAV, OGG, FLAC, M4A, AAC) en **6 pistes d'instruments isolées** (batterie, 808/basse, guitare, piano, autres, voix) grâce à l'IA, puis **transcrit chaque piste en fichier MIDI** propre et utilisable.

## Fonctionnalités

- 🔀 **Séparation IA (Demucs `htdemucs_6s`)** : 6 stems par instrument, volume normalisé (-14 LUFS) pour une écoute claire de chaque piste.
- 🎹 **Transcription professionnelle par instrument** :
  - Piano → modèle pro polyphonique **ByteDance Piano Transcription**
  - Guitare, basse, voix, autres → **Basic Pitch** (NASA ICASSP 2022)
  - Batterie → réécrite en **kit standard** (kick 36, snare 38, hats 42/46, toms) sur canal 10
- ✨ **Nettoyage MIDI automatique** : doublons fusionnés, notes parasites supprimées, notes trop courtes coupées.
- 🎧 **Écoute en ligne** : chaque piste isolée jouable depuis le site.
- ⬇️ **Téléchargements** : MP3 isolé + MIDI par instrument, ou tout en un ZIP.
- 🔒 **100 % local** : rien ne quitte ton ordinateur.

## Installation (macOS, Apple Silicon recommandé)

```bash
# 1. Outils de base (une seule fois)
curl -LsSf https://astral.sh/uv/install.sh | sh          # gestionnaire Python/venv
curl -L -o tools/ffmpeg https://github.com/eugeneware/ffmpeg-static/releases/download/b6.0/ffmpeg-darwin-arm64
chmod +x tools/ffmpeg

# 2. Environnement Python
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python setuptools==75.8.2
uv pip install --python .venv/bin/python -r requirements.txt

# 3. Lancement
./lancer.sh          # → http://127.0.0.1:5151
```

Au premier run, les modèles IA se téléchargent automatiquement (~300 Mo pour Demucs, ~170 Mo pour le piano).

## Utilisation API

| Méthode | Route | Description |
|---|---|---|
| POST | `/api/upload` | Envoie le fichier audio (multipart `file`) → `{ job }` |
| GET | `/api/status/{job}` | Progression de l'analyse |
| GET | `/api/file/{job}/{stem}.mp3` | Piste isolée |
| GET | `/api/file/{job}/{stem}.mid` | Transcription MIDI |
| GET | `/api/zip/{job}` | Tout télécharger en ZIP |

`stems` : `drums`, `bass`, `guitar`, `piano`, `other`, `vocals`.

## Structure

```
server.py       API FastAPI (upload, statut, fichiers, ZIP)
worker.py       Pipeline IA (Demucs → transcription → nettoyage)
nettoyage.py    Nettoyage MIDI + mapping batterie
static/         Frontend (HTML/CSS/JS francophone)
tools/ffmpeg    Binaire ffmpeg statique (non versionné)
data/jobs/      Analyses (non versionné)
```

## Limites

- Analyse lourde : prévoir quelques minutes (≈1 min par 30 s de musique sur Apple Silicon).
- Morceaux < 10 min conseillés (précision et mémoire).
- La qualité de transcription dépend de la clarté du mix : les 808 très sub-graves peuvent être partielles.