# Composants tiers et licences

Montage Studio Video (MSV) est distribué sous **GPL-3.0-or-later** (voir `LICENSE`).
Ce choix est imposé par FFmpeg : le binaire fourni par `imageio-ffmpeg` est compilé avec
`--enable-gpl --enable-version3` (il inclut l'encodeur x264), il est donc sous GPL version 3.

## Deux éditions : libre et pro

MSV existe en deux éditions, choisies par la variable `MSV_EDITION` (ou le fichier `EDITION` écrit par
l'installateur) : `libre` par défaut, ou `pro`. Voir `core/edition.py`.

- **Libre** (GPL-3.0-or-later) : tout ce qui est décrit dans ce fichier.
- **Pro** : aucun composant GPL n'est fourni ni utilisé. MSV refuse de démarrer FFmpeg s'il est compilé avec
  `--enable-gpl` (il faut une build LGPL, indiquée par `MONTAGE_FFMPEG`), et refuse toute commande qui utiliserait
  un encodeur ou un filtre GPL (`core/ff.py`, `check_edition`).

| Fonction | Édition libre | Édition pro (sans GPL) |
|---|---|---|
| Encodage H.264 | x264 (GPL) | Carte graphique (NVENC, Quick Sync, AMF, VideoToolbox), sinon encodeur de Windows (Media Foundation) ou OpenH264 (BSD-2) |
| Stabilisation | vid.stab (GPL) | Mesure du tremblement par MSV (numpy, corrélation de phase) et recadrage par FFmpeg (`sendcmd` + `crop`, LGPL) ; corrige les déplacements, pas les rotations |
| Changer la hauteur de la voix off | Rubber Band (GPL), garde le timbre | Vocodeur WORLD (pyworld, MIT ; WORLD, BSD modifiée), garde le timbre |
| Effets micro « voix grave », « monstre »… | Rubber Band (GPL) | Rééchantillonnage + `atempo` (LGPL), le timbre suit la hauteur |
| Effacer un logo | Filtre `delogo` (GPL) | Zone reconstruite à partir de ses 4 bords (`blend`, LGPL) |
| Flou, luminosité, saturation | `avgblur`, `lutyuv`, `hue` (LGPL), dans les deux éditions | idem |
| Détourage IA | RobustVideoMatting (GPL-3.0), récurrent, carte graphique possible | MODNet (Apache-2.0) avec ONNX Runtime (MIT), sur le processeur ; personnes seulement, image par image avec lissage dans le temps |
| Voix Piper « Tom » | AGPL-3.0 | Non proposée |
| Voix Piper et Kokoro | sherpa-onnx (inclut espeak-ng, GPL-3.0) | Non installées : module à installer à part par l'utilisateur |

Installation de l'édition pro : `installer\MontageStudioVideo.iss` compilé avec `/DPro`. Il installe le fichier
`EDITION`, les paquets de `requirements-pro.lock` (sans imageio-ffmpeg ni sherpa-onnx, dans un environnement à part)
et un FFmpeg LGPL (build BtbN, préparé et vérifié par `outils/ffmpeg_lgpl.py`) avec sa licence et l'adresse de son
code source. Il faut fournir `installer\pro\LICENCE-PRO.txt` (conditions de licence de la version pro).

Points à vérifier avant de vendre : pykakasi (GPL-3.0), une dépendance de Chatterbox, est installé à la demande de
l'utilisateur dans `.venv_clonage` (clonage de voix) ; licences de brevets pour H.264, H.265 et AAC dans un produit
payant (OpenH264 de Cisco et l'encodeur de Windows couvrent H.264).

## Bibliothèques installées par `requirements.txt`

| Composant | Licence | Rôle |
|---|---|---|
| FFmpeg (binaire statique via imageio-ffmpeg) | GPL-3.0 | Décodage, filtres, encodage vidéo et audio |
| imageio-ffmpeg | BSD-2-Clause | Fournit le binaire FFmpeg |
| Gradio | Apache-2.0 | Interface dans le navigateur |
| FastAPI / Uvicorn | MIT / BSD-3-Clause | Serveur local de l'interface |
| Pillow | MIT-CMU (HPND) | Rendu du texte et des images |
| pandas, NumPy | BSD-3-Clause | Timeline, calculs audio |
| OpenCV (opencv-python-headless) | Apache-2.0 (inclut FFmpeg en LGPL) | Détection des visages (cadrage « suivre le visage ») |
| Modèle YuNet de détection des visages (Shiqi Yu, OpenCV Zoo), téléchargé au premier usage et vérifié par empreinte SHA-256 | MIT | Cadrage « suivre le visage », cadrage des miniatures |
| ONNX Runtime (Microsoft), avec flatbuffers (Apache-2.0) et protobuf (BSD-3-Clause) ; dans `requirements-pro.txt`, à installer à part dans l'édition libre | MIT | Exécute le modèle MODNet |
| Modèle MODNet de détourage des personnes (Zhanghan Ke et al., export ONNX de Xenova/modnet figé sur une révision), téléchargé au premier usage et vérifié par empreinte SHA-256 | Apache-2.0 | Détourage IA de l'édition pro, « Détourer la personne » des miniatures |
| sherpa-onnx | Apache-2.0 | Voix off Piper hors ligne |
| faster-whisper (optionnel dans l'édition libre, inclus dans la pro), CTranslate2, tokenizers ; modèles Whisper « faster-whisper » (Systran) téléchargés au premier usage | MIT / MIT / Apache-2.0 ; modèles MIT | Sous-titres automatiques, Long → Shorts. Édition pro : **sans PyAV** (son FFmpeg inclut x264 et x265, sous GPL) ; MSV donne à Whisper le son décodé par son FFmpeg LGPL et remplace « av » par un module vide (`core/subs.py`) |
| SDK MCP `mcp`, `mcp-types` (optionnel, `requirements-mcp.txt`) | MIT | Serveur MCP (`mcp_server.py`) : une IA pilote MSV |
| Dépendances du SDK MCP : attrs, jsonschema, PyJWT, referencing, rpds-py / cffi / cryptography / pycparser, sse-starlette / pywin32 (Windows) | MIT / MIT-0 / Apache-2.0 ou BSD-3-Clause / BSD-3-Clause / PSF | Protocole MCP |

## Fichiers fournis avec le logiciel

| Fichier | Licence | Utilisation commerciale |
|---|---|---|
| `fonts/Anton-Regular.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Anton.txt`) | Oui |
| `fonts/Montserrat.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Montserrat.txt`) | Oui |

## Application de bureau `MSV-Editeur.exe` (dossier `desktop/`, installateur de l'édition pro)

| Composant | Licence | Utilisation |
|---|---|---|
| Tauri 2 et ses bibliothèques Rust (tao, wry, serde…) | MIT ou Apache-2.0 | Fenêtre de l'application, qui affiche l'éditeur servi par MSV |
| Microsoft Edge WebView2 (déjà présent dans Windows 10 et 11, non fourni) | Licence Microsoft (composant du système) | Affichage de la page dans la fenêtre |

## Voix Piper (téléchargées au premier usage, non incluses dans le logiciel)

Seules les voix dont la licence autorise l'usage commercial sont proposées.

| Voix | Langue | Licence du modèle | Obligation |
|---|---|---|---|
| Pierre, Jessica (UPMC) | Français, homme / femme | CC BY-SA 4.0 | Créditer la voix |
| Siwis | Français, femme | CC BY 4.0 | Créditer la voix |
| Tom | Français, homme | AGPL-3.0 | Compatible avec la GPL du logiciel |
| LibriTTS-R (locuteur 36) | Anglais, homme | CC BY 4.0 | Créditer la voix |
| DaveFX | Espagnol, homme | CC0 | Aucune |
| Sharvard | Espagnol, homme / femme | CC BY 3.0 | Créditer la voix |

Voix écartées : `en_US-ryan` (CC BY-NC-SA, usage commercial interdit), `it_IT-riccardo` et `it_IT-paola`
(licence non précisée). Pour l'italien, utiliser les voix Kokoro ci-dessous ou ElevenLabs.

## Voix Kokoro ★ (téléchargées au premier usage, non incluses dans le logiciel)

Un seul fichier pour toutes les voix : `kokoro-int8-multi-lang-v1_0` (132 Mo), publié par le projet sherpa-onnx,
vérifié par son empreinte SHA-256 avant d'être utilisé.

| Composant | Licence | Voix proposées | Obligation |
|---|---|---|---|
| Kokoro-82M v1.0 (hexgrad), modèle et voix | Apache-2.0 | Siwis (français), Sara et Nicola (italien), Dora et Alex (espagnol), Heart et Michael (anglais US), Emma et George (anglais UK) | Aucune (crédit apprécié) |
| espeak-ng-data (phonétisation, dans la même archive) | GPL-3.0 | — | Compatible avec la GPL du logiciel |

Crédit conseillé dans la description d'une vidéo : « Voix : Piper (modèle Siwis, CC BY 4.0) ».

## Ma voix (clonage local, installé à la demande dans `.venv_clonage`)

| Composant | Licence | Rôle |
|---|---|---|
| Chatterbox Multilingual (Resemble AI) | MIT | Synthèse de la voix clonée |
| PyTorch, torchaudio | BSD-3-Clause | Calcul sur la carte graphique |
| Whisper small (OpenAI), via transformers | MIT / Apache-2.0 | Vérification des prises (transcription) |

## Doublage et détourage (installés à la demande dans le même `.venv_clonage`)

| Composant | Licence | Rôle |
|---|---|---|
| Demucs 4 et son modèle « htdemucs » (Meta) | MIT | Séparation de la voix et du fond (Audio → Doublage) ; en 4 pistes, sépare le chant des instruments |
| Modèle MVSEP-CDX23 « Cinematic » (Roman Solovyev / ZFTurbo), poids Demucs 4 téléchargés au premier usage depuis GitHub et vérifiés par empreinte SHA-256 | MIT (code et poids publiés ensemble) ; entraîné sur Divide and Remaster v2 (CC BY 4.0) | Séparation en 3 pistes : voix, musique, ambiance et bruitages |
| RobustVideoMatting (Peter Lin et al.), code et poids téléchargés au premier usage, figés sur un commit | GPL-3.0 (compatible avec la GPL du logiciel) | Détourage IA sans fond vert (Vidéo → Fond vert et détourage) |
| torchvision | BSD-3-Clause | Nécessaire à RobustVideoMatting |

## Services externes

| Service | Conditions |
|---|---|
| ElevenLabs | Chaque utilisateur utilise **sa propre clé API** et reste soumis aux conditions de son abonnement ElevenLabs |
