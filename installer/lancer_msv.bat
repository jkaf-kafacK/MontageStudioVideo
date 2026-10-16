@echo off
rem Lanceur de Montage Studio Video (version installée).
rem 1er lancement : uv télécharge Python 3.12 et les composants (versions figées et vérifiées), une seule fois.
rem Lancements suivants : démarrage direct.
setlocal
chcp 65001 >nul
title Montage Studio Video

set "APP=%~dp0app"
set "UV=%~dp0uv.exe"
set "DATA=%LOCALAPPDATA%\MontageStudioVideo"
set "VENV=%DATA%\venv"
set "UV_CACHE_DIR=%DATA%\uv-cache"
set "UV_PYTHON_INSTALL_DIR=%DATA%\python"
set "UV_PYTHON_PREFERENCE=only-managed"
set "MSV_INSTALLED=1"
set "PYTHONIOENCODING=utf-8"

if not exist "%VENV%\Scripts\python.exe" goto preparer
fc /b "%APP%\requirements.lock" "%VENV%\requirements.lock" >nul 2>&1
if errorlevel 1 goto preparer
goto lancer

:preparer
echo.
echo  Montage Studio Video : premiere configuration (une seule fois, 2 a 5 minutes).
echo  Telechargement de Python et des composants... Laisse cette fenetre ouverte.
echo.
if exist "%VENV%" rmdir /s /q "%VENV%"
"%UV%" venv --python 3.12 "%VENV%" || goto erreur
"%UV%" pip install --python "%VENV%\Scripts\python.exe" -r "%APP%\requirements.lock" || goto erreur
copy /y "%APP%\requirements.lock" "%VENV%\requirements.lock" >nul

:lancer
if "%MSV_PREPARER_SEULEMENT%"=="1" exit /b 0
echo.
echo  Montage Studio Video demarre dans ton navigateur.
echo  Garde cette fenetre ouverte pendant l'utilisation ; ferme-la pour quitter.
echo.
"%VENV%\Scripts\python.exe" "%APP%\app.py"
exit /b %errorlevel%

:erreur
echo.
echo  La configuration a echoue. Verifie ta connexion Internet puis relance Montage Studio Video.
echo  Si le probleme continue : https://github.com/jkaf-kafacK/MontageStudioVideo/issues
echo.
pause
exit /b 1
