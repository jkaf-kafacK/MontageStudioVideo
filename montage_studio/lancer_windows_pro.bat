@echo off
rem Test local de l'edition pro (aucun composant GPL) : environnement separe .venv_pro installe depuis
rem requirements-pro.lock (sans imageio-ffmpeg ni sherpa-onnx), FFmpeg LGPL de installer\pro\ffmpeg.
rem L'edition libre (lancer_windows.bat, .venv) n'est pas touchee.
chcp 65001 >nul
cd /d "%~dp0"
set "FFPRO=%~dp0..\installer\pro\ffmpeg\ffmpeg.exe"
if not exist "%FFPRO%" (
  echo FFmpeg LGPL introuvable : %FFPRO%
  echo Prepare-le d'abord, depuis le dossier du depot :  python outils\ffmpeg_lgpl.py
  pause
  exit /b 1
)
set "PY=python"
py -3.12 -c "" >nul 2>&1 && set "PY=py -3.12"
if not exist ".venv_pro\Scripts\python.exe" (
  echo Premiere installation de l'edition pro, cela prend quelques minutes...
  %PY% -m venv .venv_pro
  if errorlevel 1 (
    echo Impossible de creer l'environnement .venv_pro ^(Python 3.12 conseille^)
    pause
    exit /b 1
  )
)
rem Reinstalle si requirements-pro.lock a change depuis la derniere installation reussie
fc /b "requirements-pro.lock" ".venv_pro\requirements-pro.lock" >nul 2>&1
if errorlevel 1 (
  ".venv_pro\Scripts\python.exe" -m pip install --upgrade pip
  ".venv_pro\Scripts\python.exe" -m pip install --no-deps --require-hashes -r requirements-pro.lock
  if errorlevel 1 (
    echo L'installation de l'edition pro a echoue. Verifie ta connexion puis relance ce fichier.
    pause
    exit /b 1
  )
  copy /y "requirements-pro.lock" ".venv_pro\requirements-pro.lock" >nul
)
set "MSV_EDITION=pro"
set "MONTAGE_FFMPEG=%FFPRO%"
if "%MSV_PREPARER_SEULEMENT%"=="1" exit /b 0
echo.
echo  Montage Studio Video - EDITION PRO (test local) : http://127.0.0.1:7870/
echo  Port 7870 : l'edition libre (port 7860) peut rester ouverte a cote.
echo.
".venv_pro\Scripts\python.exe" app.py --port 7870
pause
