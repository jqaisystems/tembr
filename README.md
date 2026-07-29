<p align="center">
  <img src="brand/logo_tembr-01.svg" width="360" alt="Tembr">
</p>

# Tembr

**Your voice, everywhere you can't be.** Tembr is a local, private voice
cloning studio for outreach that gets heard. It clones your voice on your own
GPU, speaks any text with it, renders a personal voice note for every lead on
a list, and builds each lead a branded player page you can host from any
folder. Nothing about your voice ever touches a cloud.

Product site: [ai.joaoqueiros.com/tembr](https://www.ai.joaoqueiros.com/tembr)

## The privacy stance

- Your voice is biometric data. Recording, cloning and rendering all run
  locally. There is no telemetry, no account, no upload anywhere.
- There are **no API keys in this system**. The optional AI drafting feature
  shells out to CLI tools you already have installed and logged in (`codex`,
  `claude`); their auth stays theirs, and only the drafting text leaves the
  machine. Everything voice stays home.
- The player pages Tembr builds are plain static files. Host them on your own
  server or any static host; the lead needs no account and nothing expires.

## What it does

- **Record** a reference (about ninety seconds, guided by a script written to
  cover the language's full range). The studio measures the take and tells
  you in plain language if your microphone or your room is holding it back,
  and offers an optional cleanup that never overwrites the original.
- **Clone** locally. The engine conditions on the strongest ten seconds of
  your take, found automatically (see "How cloning works" below). Voices get
  quality badges, favorites, collections, and portable `.voice` export.
- **Generate** any text in your voice. Takes are named from their own words,
  starred, filtered by project, and downloads carry readable filenames.
- **Outreach**: paste or upload a lead list (or raw notes an assistant
  untangles into rows), write one template with `{name}` and `{business}`
  variables, and render a personal note per lead. Every note is quality
  checked automatically: long pauses, repeated words and mangled endings are
  flagged before anything reaches a lead, with one-click re-render.
- **Build pages**: a branded player page per lead, their name on it, your
  voice inside it, a reply one tap away. Download the site as a folder and
  host it anywhere.

## How cloning works (and why length matters)

The zero-shot engine conditions its decoder on roughly the **first ten
seconds** of whatever reference file it is handed, and its accent-carrying
token prompt on the first six; the rest of a recording feeds only a weak
averaged embedding. Tembr therefore scans your whole take for its strongest
ten seconds (the most voiced, most pitch-alive stretch, snapped to a speech
onset) and conditions on that window instead of whatever happened to be the
stiff first line of your read. The full recording still earns its length: it
is the pool the window is found in, it stays with the voice for playback and
quality checks, and it becomes training data if you ever fine-tune. Record as
long as you comfortably can in one consistent sitting.

## Requirements

- Windows (developed there; the server is plain FastAPI + PyTorch, other
  platforms should work with adjusted launch scripts)
- An NVIDIA GPU with about 12 GB VRAM (developed on an RTX 3060 class card)
- Python 3.11+, Node 20+, [ffmpeg](https://ffmpeg.org) on PATH
- Roughly 10 GB of disk for model weights, downloaded on first run

## Quickstart

```powershell
# 1. server: two virtual environments (the Qwen engine is isolated on purpose)
cd server
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
# optional, for European Portuguese (isolated venv, see server/qwen_worker.py)
python -m venv .venv-qwen
.venv-qwen\Scripts\pip install qwen-tts fastapi uvicorn

# 2. web
cd ..\web
npm install

# 3. run everything (API on :8100, studio on :3000)
cd ..
.\start-studio.ps1
```

Model weights download automatically on first use into `models/`. First
generation takes a few minutes while the engine loads.

## Engines and credits

- [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI (MIT)
  is the default engine and covers most languages.
- [Qwen3-TTS](https://github.com/QwenLM) by the Qwen team (Apache 2.0) serves
  European Portuguese, where its accent is truer.

Tembr's own code is MIT licensed (see LICENSE). Voice cloning requires
consent: the studio asks for it at every voice creation, and the reference
script includes a spoken consent line. Clone only voices you have the right
to clone.

## Documentation

- `voice-reference-script.md`: how to record a reference that clones well,
  with the measurements behind every recommendation.
- The in-app help panels on every screen document the workflow they sit on.
- `ROADMAP.md`: where this is going.
