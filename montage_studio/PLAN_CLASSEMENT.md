# Plan de développement : mode « Classement » pour Montage Studio Video

Document de travail destiné à Claude Code. À déposer à la racine du dépôt `MontageStudioVideo`
(par exemple `docs/PLAN_CLASSEMENT.md`), puis à exécuter **une phase à la fois**.

---

## 0. Comment utiliser ce document

1. Dépose ce fichier dans le dépôt.
2. Ouvre Claude Code à la racine du dépôt.
3. Pour chaque phase, copie le bloc **« Prompt à donner à Code »** tel quel.
4. À la fin de chaque phase, Code s'arrête et résume. Relis, teste, puis lance la phase suivante.
5. Ne saute pas la phase 0 : elle sert à vérifier que ce plan colle au code réel avant d'écrire quoi que ce soit.

---

## 1. Objectif du mode

Produire des Shorts 9:16 de type « Top N » : un titre en haut, une liste numérotée qui se remplit clip après clip,
le clip en cours dans un cadre avec un badge de rang.

```
┌──────────────────────────────┐
│     RANKING BEST             │  titre, mots-clés surlignés au choix
│     FOOTBALL MOMENTS         │
│ 1. Instant Karma  ┌────────┐ │  liste : rang en cours rempli et coloré
│ 2.                │   #1   │ │
│ 3.                │  clip  │ │  clip dans un cadre + badge du rang
│ 4.                │        │ │
│ 5.                └────────┘ │
│                   @créateur  │  crédit de la source (optionnel)
└──────────────────────────────┘
```

---

## 2. Décisions produit (à modifier ici avant de lancer Code si besoin)

| # | Décision | Valeur retenue |
|---|---|---|
| D1 | Ordre de passage par défaut | `décroissant` (compte à rebours, le n° 1 passe en dernier) ; `croissant` disponible |
| D2 | Mises en page de la v1 | `liste à gauche`, `liste en haut`, `plein écran` |
| D3 | Champ « crédit » par clip | Oui, optionnel, affiché sous le cadre |
| D4 | Préréglage par défaut | `néon sombre` (fond noir, surlignage bleu ciel, badge rose) |
| D5 | Nombre de clips | 2 à 10 |
| D6 | Durée max par clip par défaut | 8 s ; alerte (non bloquante) si la durée totale dépasse 60 s |
| D7 | Format | 9:16 uniquement en v1 |

---

## 3. Règles valables pour toutes les phases

Code doit respecter ces règles sans qu'on les répète.

| Règle | Détail |
|---|---|
| Langue | Code, commentaires, messages de commit et documentation **en français**, comme le reste du dépôt |
| Aucune nouvelle dépendance | Ne modifier ni `requirements.txt`, ni `requirements.lock`, ni `overrides.txt`, ni `securite.json` |
| Ne pas toucher | `installer/`, `.github/`, `outils/`, `promo/`, `LICENSE`, `TIERS.md` |
| Traductions | Tout texte affiché passe par `_()` et reçoit ses 4 traductions (FR, EN, IT, ES) dans `core/i18n.py`. Un test du dépôt vérifie que rien ne manque : il doit rester vert |
| Compatibilité | Aucun comportement existant ne doit changer. Les nouveaux paramètres ont une valeur par défaut qui reproduit l'existant |
| Réutiliser avant d'écrire | Le mode Classement **traduit sa description en projet standard** rendu par `render_project`. Pas de second moteur de rendu |
| Tests | Chaque phase ajoute ses tests dans `montage_studio/tests/`. Lancer **toute** la suite avant chaque commit : `cd montage_studio && python -m pytest tests -q` |
| Médias de test | Générés à la volée avec FFmpeg (`testsrc`, `sine`), comme dans les tests existants. Aucun fichier binaire ajouté au dépôt |
| Commits | Un commit par phase, message clair en français. **Ne pas pousser, ne pas créer de tag** |
| Chemins | Utiliser `core/paths.py` pour tout dossier de données. Ne jamais écrire dans le dossier de l'application |
| Fin de phase | S'arrêter, lister les fichiers modifiés, le résultat des tests, et tout écart par rapport au plan |
| En cas de doute | Si le code réel contredit ce plan, **s'arrêter et expliquer** plutôt que d'improviser |

---

## 4. Format de description d'un classement

Fichier JSON (aussi produit par l'interface). La position dans `items` donne le rang : le premier est le n° 1.

```json
{
  "title": "Ranking best football moments",
  "highlight_words": ["football", "moments"],
  "order": "décroissant",
  "layout": "liste à gauche",
  "max_clip_duration": 8,
  "items": [
    {"path": "clips/karma.mp4", "label": "Instant Karma", "start": 2.0, "end": 9.5, "credit": "@createur1"},
    {"path": "clips/dad.mp4", "label": "Proud dad"}
  ],
  "style": {
    "font": "Anton-Regular.ttf",
    "title_size": 96,
    "list_size": 44,
    "text_color": "#FFFFFF",
    "dim_color": "#6B7280",
    "highlight_color": "#38BDF8",
    "badge_color": "#F43F5E",
    "background": "#000000",
    "stroke_width": 4,
    "stroke_color": "#000000"
  },
  "music": {"path": "", "volume": 0.15, "ducking": true},
  "normalize_audio": true
}
```

| Champ | Règle |
|---|---|
| `items[].start` / `end` | Optionnels. Sans eux : début du clip, durée limitée par `max_clip_duration` |
| `highlight_words` | Comparaison insensible à la casse et à la ponctuation |
| `order` | `décroissant` ou `croissant` |
| `layout` | Une des 3 valeurs de D2 |
| Image fixe dans `items` | Acceptée, durée = `max_clip_duration` |

---

## Phase 0 : reconnaissance (lecture seule)

**Objectif** : vérifier que ce plan correspond au code réel. Aucun fichier modifié.

### Prompt à donner à Code

```
Lis docs/PLAN_CLASSEMENT.md en entier. Exécute UNIQUEMENT la phase 0 : ne modifie aucun fichier.

Lis ces fichiers : montage_studio/core/render.py, core/layers.py, core/textimg.py, core/scenes.py,
core/paths.py, core/i18n.py (structure seulement), montage_studio/app.py (structure des onglets,
fonctions section(), L(), reg(), collect()), montage_studio/cli.py, montage_studio/tests/.

Puis réponds à ces questions, avec le nom des fonctions et les numéros de ligne :
1. Comment un clip est-il cadré aujourd'hui (modes flou / rogner / bandes) ? Le mode est-il global au
   projet ou réglable par clip ? Quelle est la plus petite modification pour ajouter un mode « cadre »
   (rectangle x, y, largeur, hauteur sur un fond de couleur) réglable par clip ?
2. Comment textimg dessine-t-il un mot surligné ? Que faut-il changer pour en surligner plusieurs ?
3. Quel est le format exact des incrustations minutées dans layers.py (clés, unités, animations) ?
   Peut-on y passer une image PNG pleine largeur avec un début et une fin ?
4. Existe-t-il déjà une fonction pour dessiner une pastille (badge) ? Laquelle ?
5. Le projet accepte-t-il une couleur de fond ? Sinon, où l'ajouter ?
6. Comment les onglets existants (ex. « Scènes animées ») construisent-ils un aperçu instantané ?
7. Quels tests existants couvrent ces zones ?

Termine par : la liste des écarts entre le plan et le code réel, et pour chacun l'ajustement que tu
proposes. N'écris aucun code. Attends ma validation.
```

**Critère de fin** : un rapport écrit, zéro fichier modifié (`git status` propre).

---

## Phase 1 : titre avec plusieurs mots surlignés

**Objectif** : `core/textimg.py` sait surligner plusieurs mots.

| Élément | Détail |
|---|---|
| Fichiers | `core/textimg.py`, `tests/test_classement.py` (nouveau) |
| Tâche | Ajouter un paramètre acceptant un ensemble d'indices de mots à surligner. L'ancien paramètre à indice unique continue de fonctionner à l'identique |
| Aide | Ajouter une fonction qui convertit une liste de mots (`["football", "moments"]`) en indices, sans tenir compte de la casse ni de la ponctuation |

**Critères d'acceptation**

- [ ] Un appel avec l'ancien paramètre donne une image **identique au pixel près** à celle d'avant.
- [ ] Avec deux mots surlignés, les deux sont dans la couleur de surlignage, les autres dans la couleur de texte.
- [ ] Un mot demandé mais absent du titre est ignoré sans erreur.
- [ ] Toute la suite de tests passe.

### Prompt à donner à Code

```
Exécute la phase 1 de docs/PLAN_CLASSEMENT.md, en tenant compte des ajustements validés en phase 0.
Respecte les règles de la section 3. Écris les tests d'abord (ils doivent échouer), puis le code.
Lance seulement la suite de tests neccessaire,
```

---

## Phase 2 : clip dans un cadre, sur fond de couleur

**Objectif** : le moteur sait placer un clip dans un rectangle libre de l'image.

| Élément | Détail |
|---|---|
| Fichiers | `core/render.py`, `tests/test_classement.py` |
| Tâche 1 | Nouveau mode de cadrage `cadre`, **réglable par clip**, avec un rectangle exprimé en pourcentages de l'image (`x`, `y`, `largeur`, `hauteur`). Le clip est mis à l'échelle pour tenir dans le rectangle sans déformation, centré dedans |
| Tâche 2 | Couleur de fond du projet (défaut : noir, donc aucun changement pour l'existant) |
| Tâche 3 | Le mode `cadre` fonctionne pour les vidéos **et** les images fixes |

**Critères d'acceptation**

- [ ] Un projet sans les nouveaux champs produit le même résultat qu'avant.
- [ ] Avec un cadre de 60 % de large à droite : un pixel pris à gauche a la couleur de fond, un pixel au centre du cadre vient du clip (test sur une image extraite du rendu).
- [ ] Les dimensions envoyées à FFmpeg sont toujours paires.
- [ ] Deux clips du même projet peuvent avoir des cadres différents.
- [ ] Toute la suite de tests passe.

### Prompt à donner à Code

```
Exécute la phase 2 de docs/PLAN_CLASSEMENT.md, en tenant compte des ajustements validés en phase 0.
Respecte les règles de la section 3. Tests d'abord, rendu en qualité « aperçu » dans les tests pour
rester rapide si c'est necessaire.
```

---

## Phase 3 : le cœur, `core/ranking.py`

**Objectif** : traduire une description de classement en projet standard, et fournir un aperçu instantané.

| Fonction à écrire | Rôle |
|---|---|
| `normaliser(spec)` | Complète les valeurs par défaut, valide (2 à 10 clips, fichiers existants, valeurs de `order` et `layout`), messages d'erreur traduits |
| `ordre_de_passage(spec)` | Liste des rangs dans l'ordre d'apparition selon `order` |
| `durees(spec)` | Durée de chaque clip (coupe, durée max, image fixe) et horaires de début et de fin |
| `dessiner_titre(spec, W, H)` | Image du titre avec mots surlignés (phase 1) |
| `dessiner_liste(spec, reveles, courant, W, H)` | Image de la liste pour un état donné : rangs révélés remplis, rang en cours mis en avant, autres rangs : numéro seul, atténué |
| `dessiner_badge(spec, rang)` | Pastille `#N` (réutiliser la fonction existante repérée en phase 0) |
| `dessiner_credit(spec, texte)` | Petit texte sous le cadre, seulement si renseigné |
| `construire_projet(spec, dossier_travail)` | Assemble clips (mode `cadre`, phase 2), incrustations minutées, musique. Renvoie un projet standard |
| `apercu(spec, rang)` | Image fixe de l'état « rang N en cours », sans passer par FFmpeg pour le texte |
| `rendre(spec, sortie, progression, qualite)` | Appelle `render_project` sur le projet construit |
| `melanger(spec, graine=None)` | Mélange l'ordre des clips (graine pour des tests reproductibles) |

**Géométrie des 3 mises en page** : une table de constantes (zone du titre, zone de la liste, cadre du clip, position
du badge et du crédit), en pourcentages. Les zones ne doivent jamais se chevaucher.

**Critères d'acceptation**

- [ ] Ordre `décroissant` avec 5 clips : passage 5, 4, 3, 2, 1. Ordre `croissant` : 1, 2, 3, 4, 5.
- [ ] À l'état k, exactement k libellés sont visibles dans la liste, et le rang en cours est le seul mis en avant.
- [ ] Les horaires des incrustations se suivent sans trou ni chevauchement, et la dernière finit à la durée totale.
- [ ] Un libellé trop long est réduit ou tronqué avec « … » : il ne déborde jamais sur le cadre du clip.
- [ ] `apercu()` renvoie une image 9:16 en moins d'une seconde pour 6 clips.
- [ ] Rendu complet de 3 clips de 1 s en qualité « aperçu » : fichier MP4 valide, durée attendue à 0,2 s près.
- [ ] Les erreurs de saisie (0 clip, fichier manquant, `layout` inconnu) lèvent un message clair et traduit.
- [ ] Le dossier de travail utilise `core/paths.py` et est nettoyé après le rendu.
- [ ] Toute la suite de tests passe, y compris le test de couverture des traductions.

### Prompt à donner à Code

```
Exécute la phase 3 de docs/PLAN_CLASSEMENT.md, en tenant compte des ajustements validés en phase 0.
Respecte les règles de la section 3 et le format de la section 4. Écris d'abord les tests des
fonctions pures (ordre, durées, horaires), puis le dessin, puis le rendu complet.
Ne touche pas à app.py dans cette phase. 
Joins au résumé le chemin de 3 images d'aperçu (une par mise en page) pour que je les regarde.
```

---

## Phase 4 : ligne de commande et préréglages

| Élément | Détail |
|---|---|
| Fichiers | `cli.py`, `templates/classement_neon_sombre.json`, `classement_clair.json`, `classement_verifable_brut.json`, `exemples/classement_exemple.json`, tests |
| Commande | `python cli.py classement fichier.json -o sortie.mp4 [--qualite aperçu\|standard\|haute] [--melanger]` |
| Préréglages | Chaque fichier ne contient que `style`, `layout`, `order`. `verifable_brut` : fond noir, surlignage rouge `#C8102E`, police Anton |
| Chemins relatifs | Les chemins des clips dans le JSON sont résolus par rapport au dossier du fichier JSON |

**Critères d'acceptation**

- [ ] La commande rend un fichier à partir de l'exemple (clips générés dans le test).
- [ ] Les 3 préréglages sont des JSON valides, chargés et fusionnés avec les valeurs par défaut.
- [ ] `python cli.py classement --help` décrit les options en français.
- [ ] Les préréglages n'apparaissent **pas** dans la liste des modèles de « Shorts en série ».

### Prompt à donner à Code

```
Exécute la phase 4 de docs/PLAN_CLASSEMENT.md. Respecte les règles de la section 3.
Vérifie en particulier que les fichiers classement_*.json ne polluent pas la liste des modèles
existante (paths.template_names) : si c'est le cas, range-les dans un sous-dossier dédié et adapte.
```

---

## Phase 5 : onglet « Classement » dans l'interface

| Zone | Contenu |
|---|---|
| Emplacement | Nouvel onglet entre « Scènes animées » et « Voix off » |
| Colonne gauche | Import de plusieurs clips, tableau (rang, fichier, titre, début, fin, crédit), boutons Mélanger, Monter, Descendre, Supprimer. Durée totale affichée, avertissement au-delà de 60 s |
| Colonne centrale | Aperçu instantané + curseur « rang affiché » |
| Colonne droite | Titre, **cases à cocher des mots à surligner** (régénérées quand le titre change), préréglage, mise en page, ordre, durée max par clip, police, tailles, couleurs, musique |
| Bas | Aperçu rapide, Exporter, Enregistrer le classement, Charger un classement |

**Contraintes**

- Suivre les conventions de l'onglet le plus proche (repéré en phase 0) : `section()`, `L()`, `_()`, `opts()`.
- Les fichiers importés passent par la fonction de persistance existante (dossier `medias`).
- Les sorties vont dans le dossier `sorties` de `core/paths.py`.
- Environ 60 nouveaux textes, chacun avec ses 4 traductions.
- Ajouter une courte section « Classement » dans l'aide intégrée, dans les 4 langues, avec un rappel sur les droits :
  n'utiliser que des clips dont on a les droits ou l'autorisation, et créditer la source.

**Critères d'acceptation**

- [ ] L'application démarre dans les 4 langues, l'onglet est traduit.
- [ ] Changer le titre met à jour les cases des mots à surligner.
- [ ] Mélanger, Monter et Descendre modifient l'ordre et l'aperçu.
- [ ] L'aperçu rapide et l'export produisent une vidéo dans `sorties`.
- [ ] Enregistrer puis Charger restitue le même classement.
- [ ] Les fonctions de l'onglet sont testées sans navigateur (appels directs), comme dans `tests/test_app.py`.
- [ ] Toute la suite de tests passe.

### Prompt à donner à Code

```
Exécute la phase 5 de docs/PLAN_CLASSEMENT.md. Respecte les règles de la section 3.
Avant d'écrire l'onglet, relis l'onglet « Scènes animées » de app.py et imite sa structure.
Écris des tests qui appellent directement les fonctions de l'onglet (sans navigateur).
Lance l'application une fois (python app.py --no-browser) pour vérifier qu'elle démarre sans erreur
dans les 4 langues.
```

---

## Phase 6 : documentation et vérification finale

| Élément | Détail |
|---|---|
| Fichiers | `montage_studio/README.md`, `DOCUMENTATION.md`, `README.md` (racine) |
| README | Ligne dans le tableau des fonctions + section « Classement » : format JSON, 3 mises en page, commande CLI |
| Vérifications | Suite complète, `python outils/maj_securite.py --audit`, démarrage de l'app, rendu d'un classement d'exemple en qualité « haute » |

### Prompt à donner à Code

```
Exécute la phase 6 de docs/PLAN_CLASSEMENT.md. Mets à jour la documentation, puis fais la
vérification finale : suite de tests complète, audit de sécurité en lecture seule
(python outils/maj_securite.py --audit), démarrage de l'application, et rendu en qualité « haute »
d'un classement de 5 clips générés.
```

---

## 5. Ce que tu fais toi-même après la phase 6

| # | Action |
|---|---|
| 1 | Tester à la main avec **tes propres clips** : les 3 mises en page, les 2 ordres, un titre long, un libellé long, 2 puis 10 clips |
| 2 | Regarder la vidéo **sur un téléphone** : la liste et le clip sont-ils lisibles ? |
| 3 | `git push`, puis attendre les 3 jobs verts dans l'onglet Actions |

---

## 6. Hors périmètre de cette version (à garder pour une v2)

| Idée | Remarque |
|---|---|
| Voix qui annonce « Numéro 5… » | Via `core/voice.py` (Piper ou ElevenLabs) |
| Texte qui s'écrit lettre par lettre dans la liste | Effet visuel |
| Miniature automatique (image du n° 1 + titre) | Réutilise l'outil miniature existant |
| Classements en série depuis un CSV | Même logique que « Shorts en série » |
| Formats 16:9 et 1:1 | Demande d'autres géométries |
