# Tembr launcher: starts the API and the web UI in their own windows,
# then opens the studio in your browser. Every cache stays inside this folder.
$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-ExecutionPolicy", "Bypass", "-File", "$root\server\start.ps1"

Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:npm_config_cache='$root\.cache\npm'; `$env:TMP='$root\.cache\tmp'; `$env:TEMP='$root\.cache\tmp'; Set-Location '$root\web'; npm run dev"

Start-Sleep -Seconds 8
Start-Process "http://localhost:3000"
