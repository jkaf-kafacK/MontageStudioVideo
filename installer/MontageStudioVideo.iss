; Installateur Windows de Montage Studio Video (Inno Setup 6).
; Compilé automatiquement par GitHub Actions :  ISCC.exe /DAppVersion=1.2.0 installer\MontageStudioVideo.iss
; Avant compilation, le workflow place uv.exe dans ce dossier et écrit montage_studio\VERSION.

#define AppName "Montage Studio Video"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppUrl "https://github.com/jkaf-kafacK/MontageStudioVideo"

[Setup]
; Identifiant unique et définitif : ne jamais le changer (il permet les mises à jour par-dessus).
AppId={{8F3C2A51-6B7E-4D2A-9C1F-3E5B7A9D0C42}
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
LicenseFile=..\LICENSE
SetupIconFile=..\montage_studio\assets\montage_studio.ico
UninstallDisplayIcon={app}\app\assets\montage_studio.ico
UninstallDisplayName={#AppName}
OutputDir=..\dist
OutputBaseFilename=MontageStudioVideo-{#AppVersion}-Setup
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
  Excludes: "\tests,\.venv,__pycache__,*.pyc,.pytest_cache,\medias,\sorties,\projets,\cache,\modeles_voix,voix_config.json,*.patch,.gitignore,\lancer_windows.bat,\lancer_mac_linux.sh"; \
  Flags: recursesubdirs ignoreversion
Source: "uv.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "lancer_msv.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\lancer_msv.bat"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\montage_studio.ico"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{userdesktop}\{#AppName}"; Filename: "{app}\lancer_msv.bat"; WorkingDir: "{app}"; IconFilename: "{app}\app\assets\montage_studio.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\lancer_msv.bat"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Supprime Python, les composants, le cache, les voix téléchargées et la clé API mémorisée.
; Les vidéos, médias et projets de Documents\Montage Studio Video sont conservés.
Type: filesandordirs; Name: "{localappdata}\MontageStudioVideo"
Type: filesandordirs; Name: "{app}\app"

[Code]
procedure InitializeWizard;
begin
  WizardForm.WelcomeLabel2.Caption := WizardForm.WelcomeLabel2.Caption + #13#10#13#10 + CustomMessage('FirstRun');
end;
