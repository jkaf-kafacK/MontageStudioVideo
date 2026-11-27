# MSV Éditeur : l'application de bureau (Tauri)

L'éditeur de Montage Studio Video s'ouvre dans sa propre fenêtre, sans navigateur. Quand on lance `MSV-Editeur.exe` :

1. l'application démarre MSV avec son lanceur habituel, sans fenêtre noire ni navigateur ;
2. elle attend que MSV réponde (la première fois, sa configuration prend quelques minutes) ;
3. elle affiche l'éditeur dans la fenêtre ;
4. quand on ferme la fenêtre, elle arrête MSV et tout ce qu'il a lancé.

Si MSV Pro est déjà ouvert (port 7870), la fenêtre l'utilise directement et ne l'arrête pas à la fermeture.

## Quel MSV est lancé

Le programme cherche un lanceur dans son propre dossier, puis dans les dossiers parents :

| Lanceur trouvé | Cas |
|---|---|
| `lancer_msv.bat` | version installée ; l'édition dépend du fichier `app\EDITION` |
| `lancer_windows_pro.bat` | dossier du projet, édition pro (choix par défaut) |
| `lancer_windows.bat` | dossier du projet, édition libre (option `--libre`) |

La variable `MSV_APP_DIR` permet d'indiquer un autre dossier.

Le journal du démarrage se trouve dans `%LOCALAPPDATA%\MontageStudioVideo\editeur-bureau.log`.

## Compiler

Il faut Rust (rustup) et Visual Studio Build Tools, avec la charge de travail « Développement Desktop en C++ ». WebView2 est déjà présent sur Windows 10 et 11.

```
cd desktop
npm install
npm run build
```

Le programme est créé ici : `desktop\src-tauri\target\release\MSV-Editeur.exe`.

L'installateur de l'édition pro l'inclut (`ISCC.exe /DPro …`) et ajoute un raccourci « MSV Éditeur ».

Tauri est sous licences MIT et Apache 2.0 : il convient aux deux éditions.
