@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Prefere le lanceur "py" (choisit la version de Python la plus recente installee)
set "PY=python"
py -3 -c "" >nul 2>&1 && set "PY=py -3"
if not exist ".venv\Scripts\python.exe" (
  echo Premiere installation, cela prend quelques minutes...
  %PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) and sys.version_info.releaselevel == 'final' else 1)"
  if errorlevel 1 (
    echo Python 3.11 ou plus recent ^(version finale^) est introuvable.
    echo Installe Python depuis python.org en cochant "Add python.exe to PATH", puis relance ce fichier.
    pause
    exit /b 1
  )
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Impossible de creer l'environnement .venv
    pause
    exit /b 1
  )
)
rem Installe les dependances tant qu'une installation n'a pas reussi (marqueur .venv\installed.ok)
if not exist ".venv\installed.ok" (
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt && ".venv\Scripts\python.exe" -m pip install --no-deps -r overrides.txt
  if errorlevel 1 (
    echo L'installation des dependances a echoue. Verifie ta connexion puis relance ce fichier.
    pause
    exit /b 1
  )
  echo ok> ".venv\installed.ok"
)
".venv\Scripts\python.exe" app.py
pause
