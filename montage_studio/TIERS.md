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

## Fichiers fournis avec le logiciel

| Fichier | Licence | Utilisation commerciale |
|---|---|---|
| `fonts/Anton-Regular.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Anton.txt`) | Oui |
| `fonts/Montserrat.ttf` | SIL Open Font License 1.1 (`fonts/OFL-Montserrat.txt`) | Oui |

## Voix Piper (téléchargées au premier usage, non incluses dans le logiciel)

Seules les voix dont la licence autorise l'usage commercial sont proposées.

| Voix | Langue | Licence du modèle | Obligation |
|---|---|---|---|
| Gilles | Français, homme | CC0 | Aucune |
| Pierre, Jessica (UPMC) | Français, homme / femme | CC BY-SA 4.0 | Créditer la voix |
| Siwis | Français, femme | CC BY 4.0 | Créditer la voix |
| Tom | Français, homme | AGPL-3.0 | Compatible avec la GPL du logiciel |
| LibriTTS-R (locuteur 36) | Anglais, homme | CC BY 4.0 | Créditer la voix |
| DaveFX | Espagnol, homme | CC0 | Aucune |
| Sharvard | Espagnol, homme / femme | CC BY 3.0 | Créditer la voix |

Voix écartées : `en_US-ryan` (CC BY-NC-SA, usage commercial interdit), `it_IT-riccardo` et `it_IT-paola`
(licence non précisée). Pour l'italien, utiliser ElevenLabs.

Crédit conseillé dans la description d'une vidéo : « Voix : Piper (modèle Siwis, CC BY 4.0) ».

## Services externes

| Service | Conditions |
|---|---|
| ElevenLabs | Chaque utilisateur utilise **sa propre clé API** et reste soumis aux conditions de son abonnement ElevenLabs |
