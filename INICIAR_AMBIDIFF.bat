@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AmbiDiff - Comparador de Ambientes
if not exist ".venv\Scripts\python.exe" (
  echo Primeiro abra instalar.bat para preparar o programa.
  pause
  exit /b 1
)
echo Iniciando AmbiDiff em http://127.0.0.1:8765
echo Para encerrar, feche esta janela ou pressione Ctrl+C.
".venv\Scripts\python.exe" web\server.py
pause
