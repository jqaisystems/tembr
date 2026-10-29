# Tembr / Windows and GPU setup

Install Tembr's API and web interface on Windows, the project's primary development platform, with an NVIDIA GPU of about 12 GB VRAM. The commands follow the repository's documented PyTorch 2.6 / CUDA 12.4 baseline. Use the checks below to verify readiness on your PC.

## 1. Check prerequisites

- Python **3.11** for the environments below. Confirm with `py -3.11 --version`; if you use another Python launcher, select the Python 3.11 executable explicitly.
- A supported Node.js LTS version. Use **22.12+** or a later supported LTS release compatible with the web app. Next.js 16's technical minimum is Node 20.9, but Node 20 is end-of-life. See [Next.js requirements](https://nextjs.org/docs/app/getting-started/installation) and [Node release status](https://nodejs.org/en/about/previous-releases).
- An NVIDIA GPU and a driver compatible with the CUDA-enabled PyTorch wheel. `nvidia-smi` should recognise the card. The decisive application check is `torch.cuda.is_available()` below.
- [ffmpeg](https://ffmpeg.org/download.html) on PATH: confirm with `ffmpeg -version`.
- Space for two Python environments, dependencies, about 10 GB of model weights, and your generated audio.

Run the following commands from the repository root in PowerShell. The examples use explicit environment Python paths, so activation is not required.

## 2. Install the main voice environment

```powershell
py -3.11 -m venv server/.venv
.\server\.venv\Scripts\python.exe -m pip install --upgrade pip
.\server\.venv\Scripts\python.exe -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.\server\.venv\Scripts\python.exe -m pip install -r server/requirements.txt "torch==2.6.0" "torchaudio==2.6.0"
.\server\.venv\Scripts\python.exe -m pip check
```

The CUDA wheel command follows the [official PyTorch 2.6 installation matrix](https://pytorch.org/get-started/previous-versions/#v260). Keep torch and torchaudio on matching versions. The final install retains this baseline while resolving the remaining repository requirements.

Confirm that this environment can see the GPU:

```powershell
.\server\.venv\Scripts\python.exe -c "import torch; print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'not available')"
```

Expected: a CUDA-enabled torch version, `CUDA available: True`, and your GPU name. If this is false, stop and check the driver, selected Python environment and wheel before launching. A successful pip install alone does not establish GPU readiness. If dependency resolution fails, retain the error and review upstream compatibility rather than forcing incompatible packages into the environment.

## 3. Install the web interface

```powershell
cd web
npm install
cd ..
```

## 4. Optional: a separate Qwen environment

Skip this section for the default Chatterbox workflow. Qwen runs in `server/.venv-qwen` because its dependency requirements can differ from Chatterbox. Do not combine them in one environment.

```powershell
py -3.11 -m venv server/.venv-qwen
.\server\.venv-qwen\Scripts\python.exe -m pip install --upgrade pip
.\server\.venv-qwen\Scripts\python.exe -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
.\server\.venv-qwen\Scripts\python.exe -m pip install qwen-tts fastapi uvicorn "torch==2.6.0" "torchaudio==2.6.0"
.\server\.venv-qwen\Scripts\python.exe -m pip check
.\server\.venv-qwen\Scripts\python.exe -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

Confirm CUDA is available here too. The main API manages the optional worker when that engine is selected. See [qwen_worker.py](server/qwen_worker.py) for its model and environment paths. Model downloads can take additional disk space and time.

## 5. Check that the studio is ready

```powershell
.\start-studio.ps1
```

The launcher starts the API on port 8100 and the web interface on port 3000 in separate windows. Leave them open while using the studio. In another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health | Select-Object status, torch, cuda_available
```

Expected: `status` is `ok`, torch is present, and `cuda_available` is `True`. This health response confirms API/GPU access; model loading continues in the background. Open `http://localhost:3000`, wait for the engine to load, then generate a short neutral sentence with a voice you have permission to use. Listen to and download the result before attempting a batch.

If the browser opens before the servers are ready, wait for their startup messages and reload. For first-run model downloads, keep the API window open and read its progress or error. Do not assume a blank UI means generation has completed.

## Troubleshooting

| Symptom | Check |
|---|---|
| No matching torch wheel | Confirm Python 3.11 and the documented wheel index; do not substitute the newest Python blindly. |
| CUDA unavailable | Confirm the environment path, NVIDIA driver and CUDA wheel, then repeat the GPU check. |
| Import or dependency error | Run that environment's `python -m pip check`; keep Qwen isolated from Chatterbox. |
| Studio cannot reach the API | Check both launcher windows and the port 8100 health response. |
| First generation is slow | Inspect model-download/loading progress in the API window and allow free disk space. |

When asking for help, share the operating system, Python/Node versions, GPU/driver, engine and a redacted error. The health endpoint also returns local path details; do not paste its entire response into a public issue. Keep voice recordings, models and recipient data out of attachments.

[Back to the project](README.md) · [Voice reference script](voice-reference-script.md) · [Roadmap](ROADMAP.md)
