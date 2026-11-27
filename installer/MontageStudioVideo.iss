; Installateur Windows de Montage Studio Video (Inno Setup 6).
; Compilé automatiquement par GitHub Actions :  ISCC.exe /DAppVersion=1.2.0 installer\MontageStudioVideo.iss
; Avant compilation, le workflow place uv.exe dans ce dossier et écrit montage_studio\VERSION.
;
; Édition pro (aucun composant GPL, voir montage_studio\TIERS.md) :  ISCC.exe /DPro /DAppVersion=1.2.0 ...
; Il faut en plus : installer\pro\LICENCE-PRO.txt (tes conditions de licence), installer\pro\ffmpeg\
; (FFmpeg LGPL, préparé par : python outils\ffmpeg_lgpl.py) et l'application de bureau MSV-Editeur.exe
; (compilée par : cd desktop, puis npm install et npm run build ; voir desktop\README.md).

#ifdef Pro
  #define AppName "Montage Studio Video Pro"
  #define Suffix "-Pro"
  #if !FileExists(AddBackslash(SourcePath) + "pro\LICENCE-PRO.txt")
    #error Édition pro : il manque installer\pro\LICENCE-PRO.txt (conditions de licence de la version pro)
  #endif
  #if !FileExists(AddBackslash(SourcePath) + "pro\ffmpeg\ffmpeg.exe")
    #error Édition pro : il manque installer\pro\ffmpeg\ffmpeg.exe (lance : python outils\ffmpeg_lgpl.py)
  #endif
  #define DesktopExe AddBackslash(SourcePath) + "..\desktop\src-tauri\target\release\MSV-Editeur.exe"
  #if !FileExists(DesktopExe)
    #error Édition pro : il manque MSV-Editeur.exe (lance : cd desktop, puis npm install et npm run build)
  #endif
#else
  #define AppName "Montage Studio Video"
  #define Suffix ""
#endif
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppUrl "https://github.com/jkaf-kafacK/MontageStudioVideo"

[Setup]
; Identifiant unique et définitif : ne jamais le changer (il permet les mises à jour par-dessus).
; L'édition pro a le sien : elle s'installe à côté de l'édition libre, sans la remplacer.
#ifdef Pro
AppId={{4F484AB6-BB3B-455C-812C-F5BDACDEEABE}
#else
AppId={{8F3C2A51-6B7E-4D2A-9C1F-3E5B7A9D0C42}
#endif
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Jacques Kafack
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
; Installation pour l'utilisateur courant : aucune fenêtre « Autoriser les modifications ».
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
#ifdef Pro
LicenseFile=pro\LICENCE-PRO.txt
#else
LicenseFile=..\LICENSE
#endif
SetupIconFile=..\montage_studio\assets\montage_studio.ico
#ifdef Sign
; Signature numérique (outils\signer.py, certificat dans les variables MSV_SIGN_…) :
;   ISCC.exe /DPro /DSign "/Smsvsign=python outils\signer.py $f" installer\MontageStudioVideo.iss
SignTool=msvsign
SignedUninstaller=yes
#endif
UninstallDisplayIcon={app}\app\assets\montage_studio.ico
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=MontageStudioVideo{#Suffix}-{#AppVersion}-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
ShowLanguageDialog=auto

[Languages]
Name: "french";  MessagesFile: "compiler:Languages\French.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "italian"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
french.FirstRun=Au premier lancement, Montage Studio Video télécharge Python et ses composants (environ 400 Mo, une seule fois). Une connexion Internet est nécessaire.
english.FirstRun=On first launch, Montage Studio Video downloads Python and its components (about 400 MB, only once). An Internet connection is required.
italian.FirstRun=Al primo avvio, Montage Studio Video scarica Python e i suoi componenti (circa 400 MB, una sola volta). È necessaria una connessione Internet.
spanish.FirstRun=En el primer inicio, Montage Studio Video descarga Python y sus componentes (unos 400 MB, una sola vez). Se necesita conexión a Internet.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; Le code de l'application, sans les tests, les anciens lanceurs ni aucun fichier personnel.
; Les dossiers sont exclus par leur nom (« \tests ») : tout leur contenu est ignoré et le dossier n'est pas créé.
; Pas de « createallsubdirs » : il créerait les dossiers exclus, vides, dans l'installation.
Source: "..\montage_studio\*"; DestDir: "{app}\app"; \
  Excludes: "\tests,\.venv,\.venv_clonage,\.venv_pro,\lancer_windows_pro.bat,\EDITION,__pycache__,*.pyc,.pytest_cache,\medias,\sorties,\projets,\cache,\modeles_voix,voix_config.json,licence_pro.txt,*.patch,.gitignore,\lancer_windows.bat,\lancer_mac_linux.sh"; \
  Flags: recursesubdirs ignoreversion
Source: "uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "lancer_msv.bat"; DestDir: "{app}"; Flags: ignoreversion
#ifdef Pro
; Édition pro : fichier EDITION (lu par core/edition.py et par le lanceur), FFmpeg LGPL avec sa licence et
; l'adresse de son code source (obligations de la LGPL), conditions de licence de la version pro
Source: "pro\EDITION"; DestDir: "{app}\app"; Flags: ignoreversion
Source: "pro\ffmpeg\*"; DestDir: "{app}\ffmpeg"; Flags: recursesubdirs ignoreversion
Source: "pro\LICENCE-PRO.txt"; DestDir: "{app}"; Flags: ignoreversion
; Application de bureau (Tauri) : l'éditeur dans sa propre fenêtre ; elle lance lancer_msv.bat sans fenêtre noire
#ifdef Sign
Source: "{#DesktopExe}"; DestDir: "{app}"; Flags: ignoreversion sign
#else
Source: "{#DesktopExe}"; DestDir: "{app}"; Flags: ignoreversion
#endif
#else
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\lancer_msv.bat"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\montage_studio.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\lancer_msv.bat"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\montage_studio.ico"; Tasks: desktopicon
#ifdef Pro
Name: "{group}\MSV Éditeur"; Filename: "{app}\MSV-Editeur.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\MSV Éditeur"; Filename: "{app}\MSV-Editeur.exe"; WorkingDir: "{app}"; Tasks: desktopicon
#endif

[Run]
Filename: "{app}\lancer_msv.bat"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Supprime Python, les composants, le cache, les voix téléchargées et la clé API mémorisée.
; Les vidéos, médias et projets de Documents\Montage Studio Video sont conservés.
#ifdef Pro
; Édition pro : seulement son environnement (le reste peut servir à l'édition libre installée à côté)
Type: filesandordirs; Name: "{localappdata}\MontageStudioVideo\venv-pro"
Type: filesandordirs; Name: "{app}\ffmpeg"
#else
Type: filesandordirs; Name: "{localappdata}\MontageStudioVideo"
#endif
Type: filesandordirs; Name: "{app}\app"

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + CustomMessage('FirstRun');
end;
