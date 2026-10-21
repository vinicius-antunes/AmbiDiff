@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AmbiDiff - Instalacao
echo ==============================================
echo       AMBIDIFF - PRIMEIRA INSTALACAO
echo ==============================================
where py >nul 2>&1
if %errorlevel%==0 (set "PY=py -3") else (set "PY=python")
%PY% --version
if errorlevel 1 (
  echo Instale Python em python.org e marque Add Python to PATH.
  pause
  exit /b 1
)
%PY% -m venv .venv
if errorlevel 1 goto :erro
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :erro
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 goto :erro
echo.
echo Instalacao concluida! Abra INICIAR_AMBIDIFF.bat.
pause
exit /b 0
:erro
echo Houve uma falha. Confira sua conexao ou permissoes do computador.
pause
exit /b 1
