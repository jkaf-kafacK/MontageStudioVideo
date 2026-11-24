# Composants tiers et licences

Montage Studio Video (MSV) est distribué sous **GPL-3.0-or-later** (voir `LICENSE`).
Ce choix est imposé par FFmpeg : le binaire fourni par `imageio-ffmpeg` est compilé avec
`--enable-gpl --enable-version3` (il inclut l'encodeur x264), il est donc sous GPL version 3.

## Bibliothèques installées par `requirements.txt`

| Composant | Licence | Rôle |
|---|---|---|
| FFmpeg (binaire statique via imageio-ffmpeg) | GPL-3.0 | Décodage, filtres, encodage vidéo et audio |
| imageio-ffmpeg | BSD-2-Clause | Fournit le binaire FFmpeg |
| Gradio | Apache-2.0 | Interface dans le navigateur |
| FastAPI / Uvicorn | MIT / BSD-3-Clause | Serveur local de l'interface |
| Pillow | MIT-CMU (HPND) | Rendu du texte et des images |
| pandas, NumPy | BSD-3-Clause | Timeline, calculs audio |
| sherpa-onnx | Apache-2.0 | Voix off Piper hors ligne |
| faster-whisper (optionnel) | MIT | Transcription automatique |
| SDK MCP `mcp`, `mcp-types` (optionnel, `requirements-mcp.txt`) | MIT | Serveur MCP (`mcp_server.py`) : une IA pilote MSV |
| Dépendances du SDK MCP : attrs, jsonschema, PyJWT, referencing, rpds-py / cffi / cryptography / pycparser, sse-starlette / pywin32 (Windows) | MIT / MIT-0 / Apache-2.0 ou BSD-3-Clause / BSD-3-Clause / PSF | Protocole MCP |

## Fichiers fournis avec le logiciel

| Fichier | Licence | Utilisation commerciale |
|---|---|---|
| `fonts/Anton-Regular.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Anton.txt`) | Oui |
| `fonts/Montserrat.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Montserrat.txt`) | Oui |

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
