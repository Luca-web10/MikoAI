@echo off
chcp 65001 >nul
title USB AI Assistant
cd /d "%~dp0"

if not exist "bin\llama-server.exe" (
  echo [Loi] Khong tim thay bin\llama-server.exe
  pause
  exit /b
)
if not exist "models\model.gguf" (
  echo [Loi] Khong tim thay models\model.gguf
  pause
  exit /b
)

echo Dang khoi dong tro ly AI cua ban...
echo (Cua so nay mat di = tro ly tat. Giu cua so mo de tiep tuc tro chuyen.)
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8765"
bin\llama-server.exe -m models\model.gguf -c 4096 -t %NUMBER_OF_PROCESSORS% --port 8765 --path ui