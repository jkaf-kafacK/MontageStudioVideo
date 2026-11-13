<p align="center"><img src="assets/logo.svg" alt="Montage Studio Video" width="380"></p>

# Tutoriel : prendre en main Montage Studio Video

Ce tutoriel est fait pour toi si tu ouvres Montage Studio Video (MSV) pour la première fois. Il présente les sept
onglets de l'application, dans l'ordre de l'écran. Chaque onglet a son petit exercice guidé : tu cliques en même
temps que tu lis.

Compte environ 1 heure pour tout faire. Tu peux aussi aller directement à l'onglet qui t'intéresse.

> Les noms entre « guillemets » sont écrits exactement comme sur les boutons et les champs de l'application
> (interface en français).

## Sommaire

0. [Avant de commencer](#0-avant-de-commencer)
1. [Onglet Montage : ta première vidéo](#1-onglet-montage--ta-première-vidéo)
2. [Onglet Scènes animées : une intro et un écran final](#2-onglet-scènes-animées--une-intro-et-un-écran-final)
3. [Onglet Classement : un Short « Top 5 »](#3-onglet-classement--un-short--top-5-)
4. [Onglet Voix off : transformer un texte en voix](#4-onglet-voix-off--transformer-un-texte-en-voix)
5. [Onglet Shorts en série : plusieurs vidéos d'un coup](#5-onglet-shorts-en-série--plusieurs-vidéos-dun-coup)
6. [Onglet Outils rapides : les petites tâches en un clic](#6-onglet-outils-rapides--les-petites-tâches-en-un-clic)
7. [Onglet Aide](#7-onglet-aide)
8. [Problèmes fréquents](#8-problèmes-fréquents)
9. [Petit lexique](#9-petit-lexique)

---

## 0. Avant de commencer

### Lancer l'application

| Si tu as… | Fais ceci |
|---|---|
| la version installée (Windows) | Menu Démarrer → **Montage Studio Video** |
| le dossier du logiciel (Windows) | Double-clic sur `lancer_windows.bat` |
| macOS ou Linux | Dans un terminal : `./lancer_mac_linux.sh` |

Le premier lancement télécharge les composants une seule fois (quelques minutes, Internet nécessaire). Ensuite,
l'application s'ouvre **dans ton navigateur**, à l'adresse `http://127.0.0.1:7860`.

C'est une page web, mais tout est fait **sur ton ordinateur** : tes vidéos ne sont envoyées nulle part. Une fenêtre
noire reste ouverte dans la barre des tâches. C'est le moteur de l'application : si tu la fermes, l'application
s'arrête.

### Ce que tu vois à l'écran

- **En haut** : le nom du logiciel et le sélecteur de langue **FR · EN · IT · ES**.
- **Juste en dessous** : les sept onglets.

| Onglet | En une phrase |
|---|---|
| **Montage** | Tu assembles toi-même une vidéo à partir de tes clips et de tes photos. |
| **Scènes animées** | Tu crées une animation toute prête : intro, écran « Abonne-toi », liste, chiffres… |
| **Classement** | Tu fabriques un Short « Top N » : une liste numérotée qui se remplit clip après clip. |
| **Voix off** | Tu écris un texte, l'application le lit avec une voix et crée les sous-titres. |
| **Shorts en série** | Tu produis des dizaines de vidéos au même style à partir d'un tableau. |
| **Outils rapides** | Tu fais une miniature, une conversion en Short, une extraction du son, etc. |
| **Aide** | Le résumé du mode d'emploi, toujours disponible. |

### Par où commencer ?

| Tu veux… | Va à |
|---|---|
| monter une vidéo avec tes propres clips | [Montage](#1-onglet-montage--ta-première-vidéo) |
| un Short « Top 5 des… » | [Classement](#3-onglet-classement--un-short--top-5-) |
| une vidéo racontée sur des images (storytelling) | [Voix off](#4-onglet-voix-off--transformer-un-texte-en-voix) puis [Montage](#1-onglet-montage--ta-première-vidéo) |
| publier tous les jours au même format | [Shorts en série](#5-onglet-shorts-en-série--plusieurs-vidéos-dun-coup) |
| transformer vite une vidéo YouTube en Short | [Outils rapides](#6-onglet-outils-rapides--les-petites-tâches-en-un-clic), outil B |

### Trois réflexes à prendre

1. **Aperçu d'abord, export à la fin.** Les boutons « Aperçu rapide » donnent une vidéo légère en quelques secondes.
   Tu n'exportes en pleine qualité que quand tout est bon.
2. **Lis le « Journal ».** Sous chaque résultat, ce cadre dit ce qui s'est passé. En cas de problème, il explique
   ce qui ne va pas et **ce qu'il faut faire**.
3. **Enregistre ton travail.** Un projet ou un classement s'enregistre en fichier `.json` et se recharge plus tard.

### Où vont tes fichiers ?

| Version | Dossier |
|---|---|
| Installée (Windows) | `Documents\Montage Studio Video` |
| Lancée depuis le dossier du logiciel | Le dossier `montage_studio` lui-même |

Dans ce dossier :

| Sous-dossier | Contenu |
|---|---|
| `medias` | Copies des fichiers que tu importes |
| `sorties` | Tes vidéos terminées, et leurs sous-titres `.srt` |
| `sorties/scenes` | Les scènes animées |
| `sorties/classements` | Les Shorts « Top N » |
| `sorties/voix` | Les voix off générées |
| `projets` | Tes projets enregistrés |

---

## 1. Onglet Montage : ta première vidéo

**À quoi il sert :** assembler une vidéo à la main. Tu choisis les morceaux de tes vidéos, tu les mets dans l'ordre,
puis tu ajoutes du texte, du son et un logo.

L'écran a deux colonnes :

- **à gauche**, ton matériel, en 4 sections numérotées : **1 · Médiathèque**, **2 · Inspecteur**, **3 · Timeline**,
  **4 · Calques** ;
- **à droite**, les réglages du projet, rangés dans des volets qui s'ouvrent d'un clic (Format et rendu, Audio,
  Titre…) ;
- **en bas**, les boutons pour fabriquer la vidéo.

### Exercice : un Short de 15 secondes avec un titre

**Prépare** 2 ou 3 petites vidéos de ton téléphone et, si tu veux, une photo.

#### Étape 1 : importer (section « 1 · Médiathèque »)

Glisse tes fichiers dans la zone « Importer des fichiers ».

Autre possibilité : colle le chemin d'un dossier de ton PC dans « ou un dossier de ton PC », puis clique sur
« Importer le dossier ».

Les fichiers apparaissent dans la liste « Média » de l'inspecteur.

#### Étape 2 : choisir le bon morceau (section « 2 · Inspecteur »)

1. Dans « Média », choisis ta première vidéo. Une image s'affiche.
2. Déplace le « Curseur (s) » jusqu'au moment où l'extrait doit commencer, puis clique sur « Début = curseur ».
3. Déplace le curseur jusqu'à la fin voulue, puis clique sur « Fin = curseur ».
4. Clique sur **« Ajouter l'extrait à la timeline »**.
5. Recommence avec tes autres vidéos.

Deux aides sous l'inspecteur :

- **Recadrer l'image** : retire des bords (en %), ou garde d'un clic une zone au format 9:16, 1:1, 4:5 ou 16:9.
- **Convertisseur de temps** : tape `1:30`, `90`, ou `1h 2m 3s`, puis « → Début » ou « → Fin ».

> Pour mettre **tout** un fichier sans le couper, clique directement sur « Ajouter toute la médiathèque » (section 3).

#### Étape 3 : vérifier l'ordre (section « 3 · Timeline »)

La timeline est un **tableau** : une ligne par extrait. Clique dans une case pour la modifier.

| Colonne | Ce qu'elle règle |
|---|---|
| `ordre` | La position de l'extrait dans la vidéo |
| `début`, `fin` | Le morceau gardé, en secondes |
| `vitesse` | 0,5 = ralenti, 2 = deux fois plus vite |
| `volume` | 0 = muet, 1 = normal, 2 = deux fois plus fort |
| `cadrage_x` | Quelle partie de l'image garder en vertical : 0 = gauche, 0,5 = centre, 1 = droite |
| `durée_img` | Combien de secondes une photo reste affichée |
| `mouvement` | Le mouvement d'une photo (zoom, panoramique, Ken Burns) |

Si tu as changé des numéros d'ordre, clique sur « Trier et renuméroter ».

#### Étape 4 : le format (volet « Format et rendu », à droite)

1. **Format** : `9:16` pour un Short, TikTok ou Reels ; `16:9` pour YouTube classique.
2. **Cadrage**, quand une vidéo n'a pas la bonne forme :

   | Choix | Résultat |
   |---|---|
   | `flou` | Toute l'image, sur un fond flouté |
   | `rogner` | Plein écran, les côtés sont coupés |
   | `bandes` | Toute l'image, avec des barres noires |

3. **Transition** : par exemple `fondu enchaîné` entre les extraits.

#### Étape 5 : un titre (volet « Titre »)

1. Écris ton texte dans « Texte du titre ».
2. Choisis quand il apparaît et disparaît (en secondes), puis sa police, sa couleur, sa taille et sa position.
3. Clique sur **« Aperçu du texte et des calques (instantané) »** : une image montre le résultat immédiatement, sans
   fabriquer la vidéo.

#### Étape 6 : fabriquer la vidéo (en bas)

1. **« Aperçu rapide (demi-résolution) »** : en quelques secondes, la vidéo apparaît dans « Résultat ». Regarde-la.
2. Corrige si besoin, puis clique sur **« Exporter la vidéo »** pour la version finale.

La vidéo (MP4) et ses sous-titres (`.srt`) apparaissent dans « Fichiers ». Ils sont aussi enregistrés dans
`sorties`.

#### Étape 7 : enregistrer (volet « Projets et modèles », tout en bas)

Donne un nom au projet (champ « Nom du projet », en haut à droite), puis clique sur « Enregistrer le projet ». Pour
reprendre plus tard : « Charger un projet (.json) » puis « Charger ».

### Aller plus loin dans l'onglet Montage

**Le son (volet « Audio »)**

- **Voix off** : ton fichier audio, son volume et son décalage.
- **Musique de fond** : ton fichier, joué en boucle. Sans fichier, choisis une **musique générée** libre de droits
  (calme, inspirant, énergique, suspense), composée à la durée exacte de ta vidéo. « Écouter 12 s » te fait entendre
  un extrait.
- **Baisser la musique quand on parle** : la musique se fait discrète pendant la voix.
- **Normaliser le volume** : met le son au niveau conseillé par YouTube. Laisse la case cochée.
- **Couper les silences automatiquement** : retire les blancs d'une vidéo où tu parles face caméra.

**Les sous-titres (volet « Sous-titres »)** : choisis une source.

| Source | Quand l'utiliser |
|---|---|
| `script` | Tu colles le texte lu ; l'application le découpe et le minute toute seule |
| `srt` | Tu as déjà un fichier de sous-titres (par exemple celui de l'onglet Voix off) |
| `whisper` | L'application écoute la vidéo et écrit ce qui est dit, au mot près (module à installer une fois) |
| `vidéo` | Ta vidéo contient déjà des sous-titres |

Coche « Surligner le mot prononcé » pour l'effet karaoké : le mot dit change de couleur.

**Les photos (volet « Images fixes »)** : durée de chaque photo et mouvement (zoom, panoramique, Ken Burns). Avec une
voix off, coche « Répartir les images sur toute la durée de la voix off ».

**Le logo (volet « Logo / filigrane »)** : un PNG transparent dans un coin, avec sa taille et son opacité.

**Les calques (section « 4 · Calques »)** : des éléments posés **par-dessus** la vidéo, chacun avec son heure
d'apparition et de disparition.

- **Image ou vidéo incrustée** : un sticker, une capture d'écran, ou une vidéo dans un coin. Choisis le média,
  la position, la largeur et l'entrée animée (`fondu`, `montée`, `zoom`), puis « Ajouter l'incrustation ».
- **Texte animé** : par exemple « Abonne-toi ! » qui monte en bas de l'écran à la 10ᵉ seconde. Écris le texte,
  règle-le, puis « Ajouter le texte ».

Pour modifier un calque déjà ajouté, change directement sa ligne dans le tableau sous les champs.

> « Moment de l'aperçu (s) », à côté du bouton d'aperçu instantané, choisit l'instant affiché. Tu vois ainsi les
> calques qui apparaissent plus tard.

---

## 2. Onglet Scènes animées : une intro et un écran final

**À quoi il sert :** fabriquer de courtes animations « comme à la télé », sans logiciel d'animation. Tu remplis des
textes, l'application crée un petit clip vidéo.

| Scène | Ce qu'elle montre |
|---|---|
| **carte titre** | Ton logo qui arrive avec un rebond, une étiquette et un grand titre. Pour ouvrir une vidéo. |
| **téléphone** | Ta vidéo ou ton image dans un téléphone, avec un titre |
| **écran final** | Un bouton « S'abonner » qui se fait cliquer, et « Lien en bio » |
| **liste** | Des points qui apparaissent un à un avec une coche |
| **chiffres clés** | De grands nombres qui défilent jusqu'à leur valeur |
| **avant / après** | Deux images : la seconde remplace la première par un balayage |
| **question choc** | Une grande question qui tombe mot par mot |

### Exercice : une intro pour ta vidéo

1. **Section « 1 · Scène »** : choisis `carte titre`, le format `9:16` et une durée de 3 à 4 secondes.
2. **Section « 2 · Textes et média »** :
   - « Étiquette » : `Épisode 1` ;
   - « Titre » : `Le *secret* du lac`. Le mot entre étoiles prend la couleur d'accent ;
   - « Sous-titre » : une phrase courte ;
   - « Logo, image ou vidéo » : ton logo, si tu en as un.
3. Change les couleurs si tu veux : « Fond », « Lumières du fond », « Accent ».
4. **Section « 3 · Aperçu et création »** : déplace « Moment de l'aperçu (s) » pour voir l'animation à différents
   instants.
5. Clique sur **« Créer la scène (vidéo) »** (quelques secondes).

Ensuite, deux possibilités :

| Bouton | Effet |
|---|---|
| « Ajouter à la timeline » | La scène devient un extrait de plus, à la fin de la timeline de l'onglet Montage |
| « Utiliser comme intro du projet » / « Utiliser comme fin du projet » | La scène est ajoutée **automatiquement** au début ou à la fin de chaque vidéo du projet, au bon format. Elle s'applique aussi aux séries. |

Pour retirer une intro ou une fin automatique : onglet Montage, volet « Intro et fin (scènes animées) ».

> Si ton texte est long, la scène réduit la taille des lettres d'elle-même pour que rien ne sorte de l'écran.

---

## 3. Onglet Classement : un Short « Top 5 »

**À quoi il sert :** créer un Short vertical « Top N » en quelques minutes.

- En haut : un titre.
- Au milieu : une liste numérotée qui se remplit au fil des clips.
- Le clip en cours est affiché avec son rang.

Il faut de 2 à 10 clips.

> **Droits :** n'utilise que des clips que tu as filmés, ou dont tu as l'autorisation, et crédite toujours la source.

### Exercice : « Le top 5 des plus beaux buts »

#### Étape 1 : les clips (section « 1 · Clips »)

1. Glisse 5 vidéos (ou images) dans « Importer des clips ». Tu peux en ajouter d'autres plus tard : elles
   s'ajoutent à la suite.
2. Un tableau apparaît, une ligne par clip. **La première ligne est le n° 1.**
3. La colonne `titre` reprend d'abord le nom du fichier. Remplace-le par le nom de chaque rang (par exemple
   `Le retourné de la dernière minute`).
   La colonne `crédit` reçoit le nom de l'auteur du clip (par exemple `@createur1`).
4. Facultatif : `début` et `fin` (en secondes) pour ne garder qu'un morceau du clip.

Pour changer l'ordre :

1. Clique sur une ligne : son numéro s'affiche dans « Rang sélectionné ».
2. Utilise « ▲ Monter », « ▼ Descendre » ou « Supprimer ».

« Mélanger » met les clips dans un ordre au hasard.

#### Étape 2 : le titre et le style (section « 3 · Titre et style »)

1. **Titre** : écris `Le top 5` puis appuie sur **Entrée** et écris `des plus beaux buts`. La touche Entrée met le
   titre sur deux lignes.
2. **Mots à surligner** : coche les mots à mettre en couleur, par exemple `beaux` et `buts`.
3. **Préréglage** : un style complet en un clic.

   | Préréglage | Style |
   |---|---|
   | Néon sombre | Fond noir, couleurs vives |
   | Clair | Fond clair, sobre |
   | Brut rouge | Contrasté, rouge |
   | Podium | Titre dans une bande noire, vidéo plein écran, numéros or, argent et bronze |

4. **Mise en page** :

   | Mise en page | Disposition |
   |---|---|
   | liste à gauche | La liste à gauche, le clip à droite |
   | liste en haut | La liste sous le titre, le clip en dessous |
   | plein écran | Le clip occupe tout l'écran, la liste est posée dessus |
   | bandeau | Le titre sur une bande en haut, le clip remplit le reste de l'écran |

5. **Ordre de passage** :
   - `décroissant` : compte à rebours, du n° 5 au n° 1, le plus attendu à la fin ;
   - `croissant` : du n° 1 au n° 5.
6. **Durée max par clip (s)** : coupe les clips trop longs.

#### Étape 3 : vérifier (section « 2 · Aperçu »)

Fais glisser « Rang affiché » : l'image montre l'écran à chaque étape du classement. Clique sur « Actualiser
l'aperçu » après une modification du tableau.

#### Étape 4 : fabriquer (section « 4 · Vidéo »)

1. **« Aperçu rapide (vidéo) »** fait une vidéo légère pour vérifier le rythme.
2. **« Exporter »** fait la version finale en 1080 × 1920, enregistrée dans `sorties/classements`.
3. **« Enregistrer le classement »** garde tout ton travail dans un fichier `.json`. « Charger un classement » le
   rouvre plus tard.

### Réglages fins (volet « Police, tailles et couleurs »)

| Réglage | Effet |
|---|---|
| Police, tailles, couleurs | Le texte, les rangs à venir (en gris), le surlignage, le badge, le fond, le contour |
| Surlignage 2 | Un mot surligné sur deux prend cette deuxième couleur (par exemple rouge puis jaune) |
| Position du badge | Le « #3 » : dans le coin du clip, à côté du titre, ou caché |
| Panneau derrière la liste | Un fond sombre derrière la liste, pour la lire sur une vidéo claire |
| Numéros colorés | 1 en or, 2 en argent, 3 en bronze |
| Taille des libellés | Les noms plus petits que les numéros |
| Libellés en majuscules / en italique | Le style « podium » |

« Musique (facultatif) » ajoute un fond sonore, avec son volume.

> **Conseil :** pour les mises en page « plein écran » et « bandeau », utilise des clips **verticaux** : un clip
> horizontal est rogné sur les côtés.

---

## 4. Onglet Voix off : transformer un texte en voix

**À quoi il sert :** écrire un texte et obtenir une narration audio, avec les sous-titres synchronisés.

### Les trois voix possibles (section « 2 · Voix », à droite)

| Moteur | Prix | Qualité | Internet |
|---|---|---|---|
| **Piper** | Gratuit | Correcte | Seulement pour télécharger la voix la première fois |
| **ElevenLabs** | Ton abonnement ElevenLabs | Très naturelle | Obligatoire (clé API) |
| **Ma voix** | Gratuit | Ta propre voix | Non (installation d'environ 5 Go une seule fois) |

### Exercice : une narration en deux scènes avec Piper

1. **Section « 1 · Texte »**, écris :

   ```
   15 janvier 1919. Boston.
   ---
   Dans le quartier du North End, une cuve géante domine le port.
   ```

   La ligne `---` sépare deux **scènes** : tu obtiendras une piste audio par scène, plus une piste complète.
2. À droite, choisis le moteur **Piper** et une voix dans la liste (par exemple *Pierre* ou *Siwis*). Sous la liste,
   un texte rappelle la licence de la voix.
3. Règle si besoin la « Vitesse » et la « Hauteur ». Laisse « Son studio » coché : la voix sonne plus naturelle.
4. Clique sur **« Générer la voix »**. La première fois, la voix est téléchargée.
5. Écoute le résultat dans « Écoute ».
6. Clique sur **« Utiliser dans l'onglet Montage (voix + sous-titres) »**. Dans l'onglet Montage, la voix off et les
   sous-titres sont réglés d'un coup. Il ne te reste qu'à ajouter des images.

Les fichiers créés (piste complète, `.srt`, une piste par scène) sont aussi dans `sorties/voix`.

### Pour une voix plus naturelle

Ouvre le volet « Pauses et prononciation » :

- **Pauses** : chaque phrase est lue séparément, avec une pause adaptée à la ponctuation. Pour une pause précise,
  écris `[pause 1s]` ou `[pause 500ms]` dans le texte.
- **Prononciation** : les nombres, heures et prix sont lus en toutes lettres. Si un mot est mal prononcé, ajoute une
  ligne dans le « Dictionnaire de prononciation », par exemple `YouTube = you-tioube`.

Écris pour l'oreille : des phrases courtes, avec une ponctuation soignée.

### Avec ElevenLabs

1. Sur le site elevenlabs.io, crée une clé (*Profile → API Keys*).
2. Colle-la dans « Clé API », puis clique sur « Charger mes voix ».
3. Choisis une voix, puis génère comme avec Piper. Chaque génération consomme tes crédits ElevenLabs.

La clé est mémorisée sur ton PC uniquement. Ne la partage jamais.

### Avec ta propre voix (« Ma voix »)

1. Enregistre **30 à 60 secondes** de ta voix, dans une pièce calme, avec le ton de tes vidéos.
2. Choisis le moteur « Ma voix ». La première fois, clique sur « Installer le clonage de voix » (environ 5 Go, une
   seule fois).
3. Dans « Créer une nouvelle voix » :
   - ajoute l'enregistrement ;
   - donne un nom ;
   - coche la case de consentement ;
   - clique sur « Créer la voix ».
4. Choisis ensuite :
   - ta voix dans « Mes voix » ;
   - un « Style de lecture » (Narration calme, Conversation, Promo énergique) ;
   - le nombre de « Prises par phrase ». Avec 2 ou 3, chaque phrase est vérifiée et refaite si un mot manque.

Tout reste sur ton PC.

> **Règle importante :** ne clone que **ta** voix, ou celle d'une personne qui t'a donné son accord.

### Corriger une scène déjà montée

Le volet « Remplacer la voix d'un clip existant » sert quand une vidéo a été faite avec la mauvaise voix :

1. Donne le clip.
2. Donne la nouvelle voix (vide = la dernière voix générée).
3. Si tu veux, ajoute un clip de référence pour garder le même volume.
4. Clique sur « Remplacer ».

---

## 5. Onglet Shorts en série : plusieurs vidéos d'un coup

**À quoi il sert :** produire automatiquement beaucoup de vidéos qui se ressemblent (une série d'histoires, des
extraits de podcast…).

**Le principe :** le **modèle** fixe le style (format, police, couleurs, musique…) et le **tableau** fixe le contenu.
**Une ligne du tableau = une vidéo terminée.**

### Exercice : deux vidéos à partir d'un tableau

#### 1. Choisis un modèle

Dans la liste « Modèle » :

- `(réglages de l'onglet Montage)` reprend exactement ce que tu as réglé dans l'onglet Montage ;
- ou un modèle fourni :

  | Modèle | Pour quoi |
  |---|---|
  | `short_storytelling` | Histoires narrées sur des images |
  | `short_clip_parle` | Vidéos filmées, interviews, vlogs |
  | `short_enfants` | Contenus pour les tout-petits |
  | `video_youtube_16x9` | Vidéos YouTube classiques |

Pour créer ton propre modèle : règle tout dans l'onglet Montage, puis, dans « Projets et modèles », clique sur
« Enregistrer les réglages comme modèle de série ».

#### 2. Prépare le tableau

Prépare-le dans Excel, Google Sheets ou un simple éditeur de texte, puis enregistre-le en **CSV** :

```
id;medias;titre;texte;musique
histoire_01;histoires/01/*.jpg;Le lac gelé;Ce soir, je vous raconte une histoire vraie.;auto:suspense
histoire_02;histoires/02;La cuve de Boston;Le 15 janvier 1919, à Boston...;auto:suspense
```

| Colonne | Contenu |
|---|---|
| `id` | Le nom de la vidéo produite |
| `medias` | Les fichiers (séparés par `\|`), un dossier entier, ou un motif comme `images/*.jpg` |
| `titre` | Le titre affiché au début |
| `texte` | Le texte des sous-titres (et de la voix off, si tu coches l'option plus bas) |
| `musique` | Un fichier audio, ou `auto` / `auto:suspense` pour une musique générée |
| `voix_off`, `srt` | Un fichier de narration, un fichier de sous-titres |
| `debut`, `fin` | La portion des vidéos à garder (en secondes) |
| `intro`, `outro` | `Titre \| sous-titre` d'une scène animée d'ouverture et de fin |

Deux exemples prêts à l'emploi sont téléchargeables en bas de l'onglet (« Exemples de CSV »).

#### 3. Lance la série

1. Source : « Tableau CSV ». Dépose ton fichier dans « Tableau CSV ».
2. « Dossier de base des chemins du CSV » : le dossier d'où partent les chemins de la colonne `medias`.
3. Coche « Créer la voix off à partir de la colonne « texte » » si tu veux une narration automatique. Elle utilise
   les réglages de l'onglet Voix off.
4. Donne un « Nom du dossier de sortie », puis clique sur **« Générer la série »**.

Le « Rapport » indique chaque vidéo réussie ou en erreur. Une ligne en erreur **n'arrête pas** les autres.

**Mode dossier :** choisis « Dossier : une vidéo par fichier » et indique un dossier de vidéos. Chaque vidéo devient
un Short. Règle la durée maximale, et coche « Titre = nom du fichier » si tu veux que le nom du fichier serve de titre.

---

## 6. Onglet Outils rapides : les petites tâches en un clic

Six outils indépendants. Chacun : tu déposes un fichier, tu règles, tu cliques, tu télécharges.

| Outil | À quoi il sert | Comment |
|---|---|---|
| **A · Miniature YouTube** | L'image de couverture de ta vidéo | Dépose la vidéo, choisis le « Moment (s) » de l'image, écris un texte court et accrocheur, puis « Créer la miniature ». Format 16:9 (YouTube) ou 9:16. |
| **B · Vidéo → Short 9:16** | Transformer une vidéo horizontale en Short | Dépose la vidéo, choisis le cadrage (`flou` conseillé), la durée max, puis « Convertir ». Les silences sont coupés si la case est cochée. |
| **C · Extraire l'audio en MP3** | Récupérer le son d'une vidéo | Dépose la vidéo, puis « Extraire ». |
| **D · Transcrire en sous-titres .srt** | Obtenir le texte de ce qui est dit | Dépose un audio ou une vidéo, choisis la langue, puis « Transcrire ». Demande le module Whisper (voir [Problèmes fréquents](#8-problèmes-fréquents)). |
| **E · Effacer un logo** | Retirer ton ancien logo ou un texte incrusté | Choisis la zone (coin rapide, puis curseurs X, Y, largeur, hauteur), vérifie avec « Aperçu », puis « Effacer sur toute la vidéo ». |
| **F · Logo MSV** | Ajouter ton logo, ou l'enlever proprement plus tard | « ajouter » : choisis la position, la taille et l'opacité. La position est mémorisée dans la vidéo, ce qui permet ensuite de l'« enlever » exactement. |

> L'outil E est réservé aux vidéos dont **tu détiens les droits**.

Les résultats sont enregistrés dans `sorties`.

---

## 7. Onglet Aide

Le résumé du mode d'emploi, dans la langue choisie : les étapes du montage, le format du tableau CSV, les sources de
sous-titres, les scènes, le classement, la voix off et des conseils de vitesse.

Tout en bas, deux informations utiles en cas de problème :

- l'emplacement de FFmpeg, le moteur vidéo ;
- si le module Whisper est installé ou non.

---

## 8. Problèmes fréquents

| Problème | Solution |
|---|---|
| La page ne s'ouvre pas | Vérifie que la fenêtre noire est toujours ouverte, puis va sur `http://127.0.0.1:7860` |
| Un message rouge s'affiche | Lis-le jusqu'au bout : il dit ce qui ne va pas et **que faire** (par exemple « la fin est avant le début ») |
| Le rendu est long | Utilise les aperçus rapides. Avec une carte NVIDIA, choisis l'encodeur `nvidia (nvenc)` dans « Format et rendu » |
| « Encodeur GPU indisponible » dans le journal | Normal sans carte graphique compatible : le rendu continue sur le processeur |
| Les sous-titres « script » sont un peu décalés | Le minutage est estimé. Pour une synchronisation parfaite : un `.srt` (onglet Voix off) ou Whisper |
| Whisper n'est pas installé | Version du dossier : `.venv\Scripts\python -m pip install faster-whisper`, puis relance l'application |
| Une police manque | Dépose un fichier `.ttf` ou `.otf` dans le dossier `fonts`, puis relance |
| Windows affiche « Windows a protégé votre ordinateur » | *Informations complémentaires* → *Exécuter quand même* (l'installateur n'est pas encore signé) |

---

## 9. Petit lexique

| Mot | Signification |
|---|---|
| **Extrait** | Un morceau d'une vidéo, entre un début et une fin |
| **Timeline** | La liste des extraits, dans l'ordre où ils passent |
| **Calque** | Un élément posé par-dessus la vidéo (image, texte) |
| **9:16 / 16:9** | Vertical (téléphone) / horizontal (télévision, YouTube) |
| **Cadrage** | Comment une image de la mauvaise forme est adaptée au format |
| **Transition** | L'effet de passage d'un extrait au suivant |
| **Ducking** | La musique qui baisse automatiquement quand quelqu'un parle |
| **Karaoké** | Le mot prononcé qui change de couleur dans les sous-titres |
| **`.srt`** | Un fichier de sous-titres, accepté par YouTube |
| **Modèle** | Un ensemble de réglages de style réutilisable |
| **Aperçu rapide** | Une version légère de la vidéo, faite en quelques secondes pour vérifier |
| **Export** | La fabrication de la vidéo finale, en pleine qualité |

Pour tous les détails techniques (architecture, format des fichiers, ligne de commande), voir
[DOCUMENTATION.md](DOCUMENTATION.md).
