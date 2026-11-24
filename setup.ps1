# ViDub installer (ASCII only on purpose: Windows PowerShell 5.1 safe)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Step($n, $msg) { Write-Host ""; Write-Host "[$n/5] $msg" -ForegroundColor Cyan }
function Download($url, $out) {
    for ($i = 1; $i -le 3; $i++) {
        try { Invoke-WebRequest $url -OutFile $out -UseBasicParsing; return }
        catch { Write-Host "  Loi tai, thu lai lan $i..." -ForegroundColor Yellow; Start-Sleep 3 }
    }
    throw "Khong tai duoc $url - kiem tra mang roi chay lai Cai_dat.bat"
}

$env:UV_CACHE_DIR = "$Root\uv\cache"
$env:UV_PYTHON_INSTALL_DIR = "$Root\uv\python"
$env:HF_HOME = "$Root\models"
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

Step 1 "Tai cong cu cai dat (uv)"
if (-not (Test-Path "$Root\uv\uv.exe")) {
    New-Item -ItemType Directory -Force "$Root\uv" | Out-Null
    Download 'https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip' "$Root\uv\uv.zip"
    Expand-Archive "$Root\uv\uv.zip" -DestinationPath "$Root\uv" -Force
    Remove-Item "$Root\uv\uv.zip"
} else { Write-Host "  Da co, bo qua." }

Step 2 "Cai Python 3.12 rieng cho ViDub (khong anh huong may)"
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
    & "$Root\uv\uv.exe" venv "$Root\.venv" --python 3.12
    if ($LASTEXITCODE -ne 0) { throw "Tao moi truong Python that bai" }
} else { Write-Host "  Da co, bo qua." }

Step 3 "Cai thu vien (Whisper, Gemini, Edge TTS, VieNeu) - co the mat 5-15 phut"
& "$Root\uv\uv.exe" pip install --python "$Root\.venv\Scripts\python.exe" -r "$Root\requirements.txt"
if ($LASTEXITCODE -ne 0) { throw "Cai thu vien that bai" }

Step 4 "Tai ffmpeg (xu ly video)"
if (-not (Test-Path "$Root\tools\ffmpeg\bin\ffmpeg.exe")) {
    New-Item -ItemType Directory -Force "$Root\tools" | Out-Null
    Download 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' "$Root\tools\ffmpeg.zip"
    Expand-Archive "$Root\tools\ffmpeg.zip" -DestinationPath "$Root\tools\_ff" -Force
    $inner = Get-ChildItem "$Root\tools\_ff" -Directory | Select-Object -First 1
    if (Test-Path "$Root\tools\ffmpeg") { Remove-Item "$Root\tools\ffmpeg" -Recurse -Force }
    Move-Item $inner.FullName "$Root\tools\ffmpeg"
    Remove-Item "$Root\tools\_ff", "$Root\tools\ffmpeg.zip" -Recurse -Force
} else { Write-Host "  Da co, bo qua." }

Step 5 "Tai san model nhan giong (Whisper small) va giong doc VieNeu"
$env:PATH = "$Root\tools\ffmpeg\bin;$env:PATH"
& "$Root\.venv\Scripts\python.exe" -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8'); print('  Whisper OK')"
& "$Root\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0, r'$Root'); import engine_vieneu as e; print('  VieNeu OK -', len(e.list_voices()), 'giong')"

# Desktop shortcut (skip with VIDUB_NO_SHORTCUT=1, used for testing)
if (-not $env:VIDUB_NO_SHORTCUT) {
$desk = [Environment]::GetFolderPath('Desktop')
$ws = New-Object -ComObject WScript.Shell
$lnk = $ws.CreateShortcut("$desk\ViDub.lnk")
$lnk.TargetPath = "$Root\ViDub.bat"
$lnk.WorkingDirectory = $Root
$lnk.IconLocation = "$env:SystemRoot\System32\imageres.dll,18"
$lnk.Save()
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  CAI DAT XONG! Bam dup 'ViDub' tren Desktop." -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
