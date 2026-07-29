# Start the Tembr API (localhost only, all caches inside the project folder)
$root = Split-Path $PSScriptRoot -Parent
$env:PIP_CACHE_DIR = "$root\.cache\pip"
$env:HF_HOME = "$root\models"
$env:TORCH_HOME = "$root\models\torch"
$env:TMP = "$root\.cache\tmp"
$env:TEMP = "$root\.cache\tmp"
Set-Location "$root\server"
& "$root\server\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100
