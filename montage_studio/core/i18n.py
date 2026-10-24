"""Traductions de l'interface et des messages (français, anglais, italien, espagnol).

Principe « gettext » : le texte français sert de clé. `_("Texte", x=1)` renvoie la traduction dans la langue
active (variable de contexte LANG), puis remplit les champs {x}. Un texte absent de la table reste en français.
"""
from __future__ import annotations

import contextvars

LANGS = {"fr": "Français", "en": "English", "it": "Italiano", "es": "Español"}
DEFAULT_LANG = "fr"
LANG: contextvars.ContextVar[str] = contextvars.ContextVar("lang", default=DEFAULT_LANG)

# (français, english, italiano, español)
_STRINGS: list[tuple[str, str, str, str]] = [
    # ---- en-tête, onglets, pied de page
    ("Montage vidéo local pour Shorts et vidéos YouTube, propulsé par FFmpeg.",
     "Local video editing for Shorts and YouTube videos, powered by FFmpeg.",
     "Montaggio video in locale per Shorts e video YouTube, basato su FFmpeg.",
     "Edición de vídeo local para Shorts y vídeos de YouTube, con FFmpeg."),
    ("100 % local", "100% local", "100% locale", "100 % local"),
    ("Langue de l'interface", "Interface language", "Lingua dell'interfaccia", "Idioma de la interfaz"),
    ("Montage Studio Video · tout est traité sur ton ordinateur, rien n'est envoyé sur Internet",
     "Montage Studio Video · everything is processed on your computer, nothing is sent to the Internet",
     "Montage Studio Video · tutto viene elaborato sul tuo computer, niente viene inviato su Internet",
     "Montage Studio Video · todo se procesa en tu ordenador, no se envía nada a Internet"),
    ("Montage", "Editor", "Montaggio", "Edición"),
    ("Shorts en série", "Batch Shorts", "Shorts in serie", "Shorts en serie"),
    ("Outils rapides", "Quick tools", "Strumenti rapidi", "Herramientas rápidas"),
    ("Aide", "Help", "Aiuto", "Ayuda"),

    # ---- sections
    ("Médiathèque", "Media library", "Libreria media", "Biblioteca de medios"),
    ("vidéos et images", "videos and images", "video e immagini", "vídeos e imágenes"),
    ("Inspecteur", "Inspector", "Ispettore", "Inspector"),
    ("choisis le début et la fin", "set the start and end", "scegli inizio e fine", "elige el inicio y el final"),
    ("Timeline", "Timeline", "Timeline", "Línea de tiempo"),
    ("les cellules sont modifiables", "cells are editable", "le celle sono modificabili",
     "las celdas son editables"),

    # ---- médiathèque, inspecteur, timeline
    ("Importer des fichiers", "Import files", "Importa file", "Importar archivos"),
    ("ou un dossier de ton PC", "or a folder on your PC", "o una cartella del tuo PC", "o una carpeta de tu PC"),
    ("Importer le dossier", "Import folder", "Importa cartella", "Importar carpeta"),
    ("Média", "Media", "Media", "Medio"),
    ("Image au curseur", "Frame at cursor", "Fotogramma al cursore", "Fotograma en el cursor"),
    ("Importe un média pour commencer.", "Import a media file to get started.", "Importa un file per iniziare.",
     "Importa un archivo para empezar."),
    ("Curseur (s)", "Cursor (s)", "Cursore (s)", "Cursor (s)"),
    ("Début", "Start", "Inizio", "Inicio"),
    ("Fin", "End", "Fine", "Fin"),
    ("Début = curseur", "Start = cursor", "Inizio = cursore", "Inicio = cursor"),
    ("Fin = curseur", "End = cursor", "Fine = cursore", "Fin = cursor"),
    ("Ajouter l'extrait à la timeline", "Add clip to timeline", "Aggiungi la clip alla timeline",
     "Añadir el fragmento a la línea de tiempo"),
    ("Ajouter toute la médiathèque", "Add entire library", "Aggiungi tutta la libreria", "Añadir toda la biblioteca"),
    ("Trier et renuméroter", "Sort and renumber", "Ordina e rinumera", "Ordenar y renumerar"),
    ("Retirer la dernière ligne", "Remove last row", "Rimuovi l'ultima riga", "Quitar la última fila"),
    ("Vider", "Clear", "Svuota", "Vaciar"),
    # colonnes de la timeline
    ("ordre", "order", "ordine", "orden"),
    ("fichier", "file", "file", "archivo"),
    ("début", "start", "inizio", "inicio"),
    ("fin", "end", "fine", "fin"),
    ("vitesse", "speed", "velocità", "velocidad"),
    ("volume", "volume", "volume", "volumen"),
    ("cadrage_x", "crop_x", "inquadratura_x", "encuadre_x"),
    ("durée_img", "img_duration", "durata_img", "duración_img"),

    # ---- format et rendu
    ("Nom du projet", "Project name", "Nome del progetto", "Nombre del proyecto"),
    ("Format et rendu", "Format and render", "Formato e rendering", "Formato y renderizado"),
    ("Format", "Format", "Formato", "Formato"),
    ("Cadrage", "Framing", "Inquadratura", "Encuadre"),
    ("flou = fond flouté, rogner = plein écran, bandes = barres noires",
     "blur = blurred background, crop = full screen, bars = black bars",
     "sfocato = sfondo sfocato, ritaglia = schermo intero, bande = barre nere",
     "desenfoque = fondo desenfocado, recortar = pantalla completa, bandas = barras negras"),
    ("flou", "blur", "sfocato", "desenfoque"),
    ("rogner", "crop", "ritaglia", "recortar"),
    ("bandes", "bars", "bande", "bandas"),
    ("Images/s", "Frames/s", "Fotogrammi/s", "Fotogramas/s"),
    ("Qualité export", "Export quality", "Qualità export", "Calidad de exportación"),
    ("aperçu", "preview", "anteprima", "vista previa"),
    ("standard", "standard", "standard", "estándar"),
    ("haute", "high", "alta", "alta"),
    ("Encodeur", "Encoder", "Encoder", "Codificador"),
    ("Transition", "Transition", "Transizione", "Transición"),
    ("aucune", "none", "nessuna", "ninguna"),
    ("fondu enchaîné", "crossfade", "dissolvenza incrociata", "fundido encadenado"),
    ("fondu au noir", "fade to black", "dissolvenza al nero", "fundido a negro"),
    ("dissolution", "dissolve", "dissolvenza", "disolución"),
    ("glissement gauche", "slide left", "scorrimento a sinistra", "deslizar a la izquierda"),
    ("glissement haut", "slide up", "scorrimento in alto", "deslizar hacia arriba"),
    ("balayage", "wipe", "tendina", "barrido"),
    ("zoom", "zoom", "zoom", "zoom"),
    ("cercle", "circle", "cerchio", "círculo"),
    ("Durée transition (s)", "Transition duration (s)", "Durata transizione (s)", "Duración de la transición (s)"),
    ("Ouverture au noir (s)", "Fade in from black (s)", "Apertura dal nero (s)", "Apertura desde negro (s)"),
    ("Fermeture au noir (s)", "Fade out to black (s)", "Chiusura al nero (s)", "Cierre a negro (s)"),

    # ---- audio
    ("Audio", "Audio", "Audio", "Audio"),
    ("Voix off", "Voice-over", "Voce fuori campo", "Voz en off"),
    ("Volume voix", "Voice volume", "Volume voce", "Volumen de voz"),
    ("Décalage voix (s)", "Voice offset (s)", "Ritardo voce (s)", "Desfase de voz (s)"),
    ("Musique de fond (bouclée)", "Background music (looped)", "Musica di sottofondo (in loop)",
     "Música de fondo (en bucle)"),
    ("Volume musique", "Music volume", "Volume musica", "Volumen de música"),
    ("Baisser la musique quand on parle", "Lower music during speech", "Abbassa la musica quando si parla",
     "Bajar la música cuando se habla"),
    ("Normaliser le volume (-14 LUFS, cible YouTube)", "Normalize loudness (-14 LUFS, YouTube target)",
     "Normalizza il volume (-14 LUFS, standard YouTube)", "Normalizar el volumen (-14 LUFS, objetivo de YouTube)"),
    ("Couper les silences automatiquement", "Cut silences automatically", "Taglia i silenzi automaticamente",
     "Cortar los silencios automáticamente"),
    ("Seuil de silence (dB)", "Silence threshold (dB)", "Soglia di silenzio (dB)", "Umbral de silencio (dB)"),
    ("Silence minimum (s)", "Minimum silence (s)", "Silenzio minimo (s)", "Silencio mínimo (s)"),

    # ---- images fixes
    ("Images fixes", "Still images", "Immagini fisse", "Imágenes fijas"),
    ("Durée par image (s)", "Duration per image (s)", "Durata per immagine (s)", "Duración por imagen (s)"),
    ("aucun", "none", "nessuno", "ninguno"),
    ("zoom avant", "zoom in", "zoom avanti", "acercar"),
    ("zoom arrière", "zoom out", "zoom indietro", "alejar"),
    ("Mouvement (effet Ken Burns)", "Motion (Ken Burns effect)", "Movimento (effetto Ken Burns)",
     "Movimiento (efecto Ken Burns)"),
    ("Répartir les images sur toute la durée de la voix off", "Spread images across the whole voice-over",
     "Distribuisci le immagini su tutta la durata della voce fuori campo",
     "Repartir las imágenes durante toda la voz en off"),

    # ---- titre
    ("Titre", "Title", "Titolo", "Título"),
    ("Texte du titre", "Title text", "Testo del titolo", "Texto del título"),
    ("Laisse vide pour aucun titre", "Leave empty for no title", "Lascia vuoto per nessun titolo",
     "Déjalo vacío para no poner título"),
    ("Apparaît à (s)", "Appears at (s)", "Appare a (s)", "Aparece en (s)"),
    ("Disparaît à (s)", "Disappears at (s)", "Scompare a (s)", "Desaparece en (s)"),
    ("Police", "Font", "Carattere", "Fuente"),
    ("Couleur", "Color", "Colore", "Color"),
    ("Taille", "Size", "Dimensione", "Tamaño"),
    ("Position verticale", "Vertical position", "Posizione verticale", "Posición vertical"),
    ("Fond derrière le titre", "Background behind title", "Sfondo dietro il titolo", "Fondo detrás del título"),

    # ---- sous-titres
    ("Sous-titres", "Subtitles", "Sottotitoli", "Subtítulos"),
    ("Source", "Source", "Origine", "Origen"),
    ("Script (mode « script »)", "Script (“script” mode)", "Script (modalità «script»)", "Guion (modo «script»)"),
    ("Colle ici le texte lu par la voix off.", "Paste the voice-over text here.",
     "Incolla qui il testo letto dalla voce fuori campo.", "Pega aquí el texto que lee la voz en off."),
    ("Fichier .srt (mode « srt »)", ".srt file (“srt” mode)", "File .srt (modalità «srt»)",
     "Archivo .srt (modo «srt»)"),
    ("Mots par sous-titre", "Words per subtitle", "Parole per sottotitolo", "Palabras por subtítulo"),
    ("Surligner le mot prononcé", "Highlight the spoken word", "Evidenzia la parola pronunciata",
     "Resaltar la palabra pronunciada"),
    ("Langue (Whisper)", "Language (Whisper)", "Lingua (Whisper)", "Idioma (Whisper)"),
    ("Modèle Whisper", "Whisper model", "Modello Whisper", "Modelo Whisper"),
    ("Texte", "Text", "Testo", "Texto"),
    ("Contour", "Outline", "Contorno", "Contorno"),
    ("Surlignage", "Highlight", "Evidenziazione", "Resaltado"),
    ("Épaisseur contour", "Outline width", "Spessore contorno", "Grosor del contorno"),
    ("couleur", "color", "colore", "color"),
    ("fond", "background", "sfondo", "fondo"),
    ("Style du surlignage", "Highlight style", "Stile evidenziazione", "Estilo de resaltado"),
    ("Bandeau", "Banner", "Fascia", "Franja"),
    ("Majuscules", "Uppercase", "Maiuscole", "Mayúsculas"),

    # ---- logo
    ("Logo / filigrane", "Logo / watermark", "Logo / filigrana", "Logo / marca de agua"),
    ("Logo (PNG transparent conseillé)", "Logo (transparent PNG recommended)", "Logo (consigliato PNG trasparente)",
     "Logo (se recomienda PNG transparente)"),
    ("Position", "Position", "Posizione", "Posición"),
    ("haut gauche", "top left", "in alto a sinistra", "arriba a la izquierda"),
    ("haut droite", "top right", "in alto a destra", "arriba a la derecha"),
    ("bas gauche", "bottom left", "in basso a sinistra", "abajo a la izquierda"),
    ("bas droite", "bottom right", "in basso a destra", "abajo a la derecha"),
    ("centre", "center", "centro", "centro"),
    ("Opacité", "Opacity", "Opacità", "Opacidad"),

    # ---- aperçu, rendu, projets
    ("Aperçu du texte (instantané)", "Text preview (instant)", "Anteprima del testo (istantanea)",
     "Vista previa del texto (instantánea)"),
    ("Aperçu du titre et des sous-titres", "Title and subtitle preview", "Anteprima di titolo e sottotitoli",
     "Vista previa del título y los subtítulos"),
    ("Aperçu rapide (demi-résolution)", "Quick preview (half resolution)", "Anteprima rapida (metà risoluzione)",
     "Vista previa rápida (media resolución)"),
    ("Exporter la vidéo", "Export video", "Esporta il video", "Exportar el vídeo"),
    ("Résultat", "Result", "Risultato", "Resultado"),
    ("Fichiers (vidéo + sous-titres .srt)", "Files (video + .srt subtitles)", "File (video + sottotitoli .srt)",
     "Archivos (vídeo + subtítulos .srt)"),
    ("Journal", "Log", "Registro", "Registro"),
    ("Projets et modèles", "Projects and templates", "Progetti e modelli", "Proyectos y plantillas"),
    ("Enregistrer le projet", "Save project", "Salva il progetto", "Guardar el proyecto"),
    ("Charger un projet (.json)", "Load a project (.json)", "Carica un progetto (.json)",
     "Cargar un proyecto (.json)"),
    ("Charger", "Load", "Carica", "Cargar"),
    ("Enregistrer les réglages comme modèle de série", "Save settings as batch template",
     "Salva le impostazioni come modello di serie", "Guardar los ajustes como plantilla de serie"),
    ("Modèle", "Template", "Modello", "Plantilla"),
    ("Appliquer ce modèle aux réglages", "Apply this template to settings", "Applica questo modello alle impostazioni",
     "Aplicar esta plantilla a los ajustes"),
    ("(réglages de l'onglet Montage)", "(settings from the Editor tab)", "(impostazioni della scheda Montaggio)",
     "(ajustes de la pestaña Edición)"),

    # ---- série
    ("Une ligne du tableau = une vidéo terminée. Le modèle fixe le style, le tableau fixe le contenu.",
     "One table row = one finished video. The template sets the style, the table sets the content.",
     "Una riga della tabella = un video finito. Il modello definisce lo stile, la tabella il contenuto.",
     "Una fila de la tabla = un vídeo terminado. La plantilla define el estilo, la tabla el contenido."),
    ("Actualiser la liste des modèles", "Refresh template list", "Aggiorna l'elenco dei modelli",
     "Actualizar la lista de plantillas"),
    ("Tableau CSV", "CSV table", "Tabella CSV", "Tabla CSV"),
    ("Dossier : une vidéo par fichier", "Folder: one video per file", "Cartella: un video per file",
     "Carpeta: un vídeo por archivo"),
    ("Dossier de base des chemins du CSV", "Base folder for CSV paths", "Cartella base dei percorsi del CSV",
     "Carpeta base de las rutas del CSV"),
    ("Dossier de vidéos (mode dossier)", "Video folder (folder mode)", "Cartella video (modalità cartella)",
     "Carpeta de vídeos (modo carpeta)"),
    ("Durée max par vidéo (s)", "Max duration per video (s)", "Durata massima per video (s)",
     "Duración máxima por vídeo (s)"),
    ("Titre = nom du fichier", "Title = file name", "Titolo = nome del file", "Título = nombre del archivo"),
    ("Nom du dossier de sortie", "Output folder name", "Nome della cartella di output",
     "Nombre de la carpeta de salida"),
    ("Qualité", "Quality", "Qualità", "Calidad"),
    ("Générer la série", "Generate batch", "Genera la serie", "Generar la serie"),
    ("Exemples de CSV", "CSV examples", "Esempi di CSV", "Ejemplos de CSV"),
    ("Vidéos produites", "Generated videos", "Video prodotti", "Vídeos generados"),
    ("Rapport", "Report", "Rapporto", "Informe"),

    # ---- outils rapides
    ("Miniature YouTube", "YouTube thumbnail", "Miniatura YouTube", "Miniatura de YouTube"),
    ("Vidéo ou image", "Video or image", "Video o immagine", "Vídeo o imagen"),
    ("Moment (s)", "Time (s)", "Istante (s)", "Momento (s)"),
    ("Il a disparu sans laisser de trace", "He vanished without a trace", "È sparito senza lasciare traccia",
     "Desapareció sin dejar rastro"),
    ("Créer la miniature", "Create thumbnail", "Crea la miniatura", "Crear la miniatura"),
    ("Miniature", "Thumbnail", "Miniatura", "Miniatura"),
    ("Télécharger", "Download", "Scarica", "Descargar"),
    ("Vidéo → Short 9:16 en un clic", "Video → 9:16 Short in one click", "Video → Short 9:16 in un clic",
     "Vídeo → Short 9:16 en un clic"),
    ("Vidéo", "Video", "Video", "Vídeo"),
    ("Durée max (s)", "Max duration (s)", "Durata massima (s)", "Duración máxima (s)"),
    ("Couper les silences", "Cut silences", "Taglia i silenzi", "Cortar los silencios"),
    ("Convertir", "Convert", "Converti", "Convertir"),
    ("Extraire l'audio en MP3", "Extract audio to MP3", "Estrai l'audio in MP3", "Extraer el audio en MP3"),
    ("Extraire", "Extract", "Estrai", "Extraer"),
    ("Transcrire en sous-titres .srt", "Transcribe to .srt subtitles", "Trascrivi in sottotitoli .srt",
     "Transcribir a subtítulos .srt"),
    ("Audio ou vidéo", "Audio or video", "Audio o video", "Audio o vídeo"),
    ("Langue", "Language", "Lingua", "Idioma"),
    ("Mots par ligne", "Words per line", "Parole per riga", "Palabras por línea"),
    ("Transcrire", "Transcribe", "Trascrivi", "Transcribir"),
    ("Fichier .srt", ".srt file", "File .srt", "Archivo .srt"),

    # ---- aide
    ("FFmpeg utilisé", "FFmpeg in use", "FFmpeg in uso", "FFmpeg en uso"),
    ("installé ✅", "installed ✅", "installato ✅", "instalado ✅"),
    ("non installé (optionnel)", "not installed (optional)", "non installato (opzionale)", "no instalado (opcional)"),

    # ---- messages de l'interface
    ("Dossier introuvable : {d}", "Folder not found: {d}", "Cartella non trovata: {d}", "Carpeta no encontrada: {d}"),
    ("Choisis un média.", "Choose a media file.", "Scegli un file.", "Elige un archivo."),
    ("Fichier audio ({dur:.1f} s) : utilise-le comme voix off ou musique.",
     "Audio file ({dur:.1f} s): use it as voice-over or music.",
     "File audio ({dur:.1f} s): usalo come voce fuori campo o musica.",
     "Archivo de audio ({dur:.1f} s): úsalo como voz en off o música."),
    ("avec son", "with sound", "con audio", "con sonido"),
    ("sans son", "no sound", "senza audio", "sin sonido"),
    ("image fixe", "still image", "immagine fissa", "imagen fija"),
    ("Choisis d'abord un média dans la médiathèque.", "First choose a media file from the library.",
     "Prima scegli un file dalla libreria.", "Primero elige un archivo de la biblioteca."),
    ("Un fichier audio va dans « Voix off » ou « Musique », pas dans la timeline.",
     "An audio file goes in “Voice-over” or “Music”, not in the timeline.",
     "Un file audio va in «Voce fuori campo» o «Musica», non nella timeline.",
     "Un archivo de audio va en «Voz en off» o «Música», no en la línea de tiempo."),
    ("La timeline est vide : ajoute au moins une vidéo ou une image.",
     "The timeline is empty: add at least one video or image.",
     "La timeline è vuota: aggiungi almeno un video o un'immagine.",
     "La línea de tiempo está vacía: añade al menos un vídeo o una imagen."),
    ("✅ {name} : {dur:.1f} s de vidéo, rendue en {sec:.0f} s",
     "✅ {name}: {dur:.1f} s of video, rendered in {sec:.0f} s",
     "✅ {name}: {dur:.1f} s di video, renderizzato in {sec:.0f} s",
     "✅ {name}: {dur:.1f} s de vídeo, renderizado en {sec:.0f} s"),
    ("Voici un exemple de sous-titres", "Here is a subtitle example", "Ecco un esempio di sottotitoli",
     "Este es un ejemplo de subtítulos"),
    ("Projet enregistré : projets/{name}", "Project saved: projets/{name}", "Progetto salvato: projets/{name}",
     "Proyecto guardado: projets/{name}"),
    ("Choisis un fichier de projet .json.", "Choose a .json project file.", "Scegli un file di progetto .json.",
     "Elige un archivo de proyecto .json."),
    ("Modèle enregistré : templates/{name}.json", "Template saved: templates/{name}.json",
     "Modello salvato: templates/{name}.json", "Plantilla guardada: templates/{name}.json"),
    ("Choisis un modèle enregistré.", "Choose a saved template.", "Scegli un modello salvato.",
     "Elige una plantilla guardada."),
    ("Les réglages actuels de l'onglet Montage serviront de modèle.",
     "The current settings of the Editor tab will be used as the template.",
     "Le impostazioni attuali della scheda Montaggio verranno usate come modello.",
     "Los ajustes actuales de la pestaña Edición se usarán como plantilla."),
    ("Modèle {name} ({fmt}).", "Template {name} ({fmt}).", "Modello {name} ({fmt}).", "Plantilla {name} ({fmt})."),
    ("Modèle illisible : {e}", "Unreadable template: {e}", "Modello illeggibile: {e}", "Plantilla ilegible: {e}"),
    ("Ajoute le fichier CSV de la série.", "Add the batch CSV file.", "Aggiungi il file CSV della serie.",
     "Añade el archivo CSV de la serie."),
    ("Aucune ligne à traiter.", "No rows to process.", "Nessuna riga da elaborare.", "No hay filas que procesar."),
    ("{ok}/{n} vidéos dans {out}", "{ok}/{n} videos in {out}", "{ok}/{n} video in {out}", "{ok}/{n} vídeos en {out}"),
    ("Ajoute une vidéo ou une image.", "Add a video or an image.", "Aggiungi un video o un'immagine.",
     "Añade un vídeo o una imagen."),
    ("Ajoute une vidéo.", "Add a video.", "Aggiungi un video.", "Añade un vídeo."),
    ("Whisper n'est pas installé. Lance : pip install faster-whisper",
     "Whisper is not installed. Run: pip install faster-whisper",
     "Whisper non è installato. Esegui: pip install faster-whisper",
     "Whisper no está instalado. Ejecuta: pip install faster-whisper"),
    ("Ajoute un fichier audio ou vidéo.", "Add an audio or video file.", "Aggiungi un file audio o video.",
     "Añade un archivo de audio o vídeo."),
    ("Transcription en cours (le premier lancement télécharge le modèle)",
     "Transcribing (the first run downloads the model)",
     "Trascrizione in corso (al primo avvio viene scaricato il modello)",
     "Transcribiendo (la primera vez se descarga el modelo)"),

    # ---- messages du moteur (core/)
    ("Analyse des médias", "Analyzing media", "Analisi dei file", "Analizando los archivos"),
    ("Préparation du segment {i}/{n}", "Preparing segment {i}/{n}", "Preparazione del segmento {i}/{n}",
     "Preparando el segmento {i}/{n}"),
    ("Assemblage", "Assembling", "Assemblaggio", "Montaje"),
    ("Rendu final", "Final render", "Rendering finale", "Renderizado final"),
    ("Terminé", "Done", "Fatto", "Terminado"),
    ("⚠ Segment ignoré (durée nulle) : {name}", "⚠ Segment skipped (zero length): {name}",
     "⚠ Segmento ignorato (durata nulla): {name}", "⚠ Segmento omitido (duración nula): {name}"),
    ("✂ {name} : {n} morceaux, {gain:.1f} s de silence retirés",
     "✂ {name}: {n} pieces, {gain:.1f} s of silence removed",
     "✂ {name}: {n} parti, {gain:.1f} s di silenzio rimossi",
     "✂ {name}: {n} fragmentos, {gain:.1f} s de silencio eliminados"),
    ("⚠ Fichier ignoré dans la timeline (audio ou inconnu) : {name}",
     "⚠ File skipped in the timeline (audio or unknown): {name}",
     "⚠ File ignorato nella timeline (audio o sconosciuto): {name}",
     "⚠ Archivo omitido en la línea de tiempo (audio o desconocido): {name}"),
    ("🖼 {n} images calées sur la voix off : {per:.2f} s chacune",
     "🖼 {n} images synced to the voice-over: {per:.2f} s each",
     "🖼 {n} immagini sincronizzate sulla voce fuori campo: {per:.2f} s ciascuna",
     "🖼 {n} imágenes ajustadas a la voz en off: {per:.2f} s cada una"),
    ("⚠ Whisper non installé (pip install faster-whisper) : sous-titres ignorés",
     "⚠ Whisper not installed (pip install faster-whisper): subtitles skipped",
     "⚠ Whisper non installato (pip install faster-whisper): sottotitoli ignorati",
     "⚠ Whisper no instalado (pip install faster-whisper): subtítulos omitidos"),
    ("⚠ Encodeur GPU indisponible, nouvel essai avec le CPU (x264)",
     "⚠ GPU encoder unavailable, retrying with the CPU (x264)",
     "⚠ Encoder GPU non disponibile, nuovo tentativo con la CPU (x264)",
     "⚠ Codificador GPU no disponible, reintentando con la CPU (x264)"),
    ("Média introuvable : {q}", "Media not found: {q}", "File non trovato: {q}", "Archivo no encontrado: {q}"),
    ("✅ {name}.mp4  ({dur:.1f} s, rendu en {sec:.0f} s)", "✅ {name}.mp4  ({dur:.1f} s, rendered in {sec:.0f} s)",
     "✅ {name}.mp4  ({dur:.1f} s, renderizzato in {sec:.0f} s)",
     "✅ {name}.mp4  ({dur:.1f} s, renderizado en {sec:.0f} s)"),
    ("FFmpeg introuvable. Lance : pip install imageio-ffmpeg", "FFmpeg not found. Run: pip install imageio-ffmpeg",
     "FFmpeg non trovato. Esegui: pip install imageio-ffmpeg",
     "FFmpeg no encontrado. Ejecuta: pip install imageio-ffmpeg"),
    ("Fichier introuvable : {path}", "File not found: {path}", "File non trovato: {path}",
     "Archivo no encontrado: {path}"),
    ("FFmpeg a échoué (code {code}) :\n{msg}", "FFmpeg failed (code {code}):\n{msg}",
     "FFmpeg non è riuscito (codice {code}):\n{msg}", "FFmpeg ha fallado (código {code}):\n{msg}"),
    # ---- voix off (ElevenLabs / Piper)
    ("Piper (gratuit, local)", "Piper (free, local)", "Piper (gratuito, locale)", "Piper (gratis, local)"),
    ("ElevenLabs (API)", "ElevenLabs (API)", "ElevenLabs (API)", "ElevenLabs (API)"),
    ("Pierre — homme, français", "Pierre — male, French", "Pierre — uomo, francese", "Pierre — hombre, francés"),
    ("Tom — homme, français", "Tom — male, French", "Tom — uomo, francese", "Tom — hombre, francés"),
    ("Gilles — homme, français (grave)", "Gilles — male, French (deep)", "Gilles — uomo, francese (grave)",
     "Gilles — hombre, francés (grave)"),
    ("Jessica — femme, français", "Jessica — female, French", "Jessica — donna, francese", "Jessica — mujer, francés"),
    ("Siwis — femme, français", "Siwis — female, French", "Siwis — donna, francese", "Siwis — mujer, francés"),
    ("LibriTTS — homme, anglais", "LibriTTS — male, English", "LibriTTS — uomo, inglese", "LibriTTS — hombre, inglés"),
    ("DaveFX — homme, espagnol", "DaveFX — male, Spanish", "DaveFX — uomo, spagnolo", "DaveFX — hombre, español"),
    ("Sharvard — homme, espagnol", "Sharvard — male, Spanish", "Sharvard — uomo, spagnolo", "Sharvard — hombre, español"),
    ("Sharvard — femme, espagnol", "Sharvard — female, Spanish", "Sharvard — donna, spagnolo", "Sharvard — mujer, español"),
    ("Choisis une voix ElevenLabs (bouton « Charger mes voix »).",
     "Choose an ElevenLabs voice (“Load my voices” button).",
     "Scegli una voce ElevenLabs (pulsante «Carica le mie voci»).",
     "Elige una voz de ElevenLabs (botón «Cargar mis voces»)."),
    ("{n} voix trouvées sur ton compte ElevenLabs.", "{n} voices found on your ElevenLabs account.",
     "{n} voci trovate sul tuo account ElevenLabs.", "{n} voces encontradas en tu cuenta de ElevenLabs."),
    ("Licence du modèle : {lic} (détails dans TIERS.md)", "Model licence: {lic} (details in TIERS.md)",
     "Licenza del modello: {lic} (dettagli in TIERS.md)", "Licencia del modelo: {lic} (detalles en TIERS.md)"),
    ("Écris le texte de la voix off.", "Write the voice-over text.", "Scrivi il testo della voce fuori campo.",
     "Escribe el texto de la voz en off."),
    ("Création de la voix ({n} scène(s))", "Creating the voice ({n} scene(s))", "Creazione della voce ({n} scena/e)",
     "Creando la voz ({n} escena(s))"),
    ("le premier usage télécharge la voix", "first use downloads the voice", "il primo utilizzo scarica la voce",
     "el primer uso descarga la voz"),
    ("✅ Voix créée : {dur:.1f} s, {n} scène(s)", "✅ Voice created: {dur:.1f} s, {n} scene(s)",
     "✅ Voce creata: {dur:.1f} s, {n} scena/e", "✅ Voz creada: {dur:.1f} s, {n} escena(s)"),
    ("   scène {i} : {dur:.2f} s", "   scene {i}: {dur:.2f} s", "   scena {i}: {dur:.2f} s", "   escena {i}: {dur:.2f} s"),
    ("Sous-titres : minutage exact (ElevenLabs)", "Subtitles: exact timing (ElevenLabs)",
     "Sottotitoli: tempi esatti (ElevenLabs)", "Subtítulos: tiempos exactos (ElevenLabs)"),
    ("Sous-titres : minutage estimé", "Subtitles: estimated timing", "Sottotitoli: tempi stimati",
     "Subtítulos: tiempos estimados"),
    ("Génère d'abord une voix.", "Generate a voice first.", "Genera prima una voce.", "Genera primero una voz."),
    ("Voix off et sous-titres envoyés dans l'onglet Montage.", "Voice-over and subtitles sent to the Editor tab.",
     "Voce fuori campo e sottotitoli inviati alla scheda Montaggio.",
     "Voz en off y subtítulos enviados a la pestaña Edición."),
    ("Ajoute la vidéo et la nouvelle voix (ou génère-en une au-dessus).",
     "Add the video and the new voice (or generate one above).",
     "Aggiungi il video e la nuova voce (o generane una qui sopra).",
     "Añade el vídeo y la nueva voz (o genera una arriba)."),
    ("Écris le texte, choisis une voix, génère. Sépare les scènes par une ligne `---` : une piste par scène + une piste "
     "complète + les sous-titres `.srt`.",
     "Write the text, choose a voice, generate. Separate scenes with a `---` line: one track per scene + a full track "
     "+ the `.srt` subtitles.",
     "Scrivi il testo, scegli una voce, genera. Separa le scene con una riga `---`: una traccia per scena + una "
     "traccia completa + i sottotitoli `.srt`.",
     "Escribe el texto, elige una voz y genera. Separa las escenas con una línea `---`: una pista por escena + una "
     "pista completa + los subtítulos `.srt`."),
    ("Texte de la voix off", "Voice-over text", "Testo della voce fuori campo", "Texto de la voz en off"),
    ("15 janvier 1919. Boston.\n---\nDans le quartier du North End, une cuve géante domine le port.",
     "January 15, 1919. Boston.\n---\nIn the North End, a giant tank towers over the harbour.",
     "15 gennaio 1919. Boston.\n---\nNel quartiere del North End, un enorme serbatoio domina il porto.",
     "15 de enero de 1919. Boston.\n---\nEn el barrio del North End, un tanque gigante domina el puerto."),
    ("Nom", "Name", "Nome", "Nombre"),
    ("Pause entre scènes (s)", "Pause between scenes (s)", "Pausa tra le scene (s)", "Pausa entre escenas (s)"),
    ("Générer la voix", "Generate the voice", "Genera la voce", "Generar la voz"),
    ("Écoute", "Listen", "Ascolto", "Escuchar"),
    ("Utiliser dans l'onglet Montage (voix + sous-titres)", "Use in the Editor tab (voice + subtitles)",
     "Usa nella scheda Montaggio (voce + sottotitoli)", "Usar en la pestaña Edición (voz + subtítulos)"),
    ("Fichiers (piste complète, .srt, une piste par scène)", "Files (full track, .srt, one track per scene)",
     "File (traccia completa, .srt, una traccia per scena)", "Archivos (pista completa, .srt, una pista por escena)"),
    ("Moteur", "Engine", "Motore", "Motor"),
    ("Vitesse", "Speed", "Velocità", "Velocidad"),
    ("**Piper** : gratuit, hors ligne. La voix est téléchargée au premier usage.",
     "**Piper**: free, offline. The voice is downloaded on first use.",
     "**Piper**: gratuito, offline. La voce viene scaricata al primo utilizzo.",
     "**Piper**: gratis, sin conexión. La voz se descarga en el primer uso."),
    ("Voix", "Voice", "Voce", "Voz"),
    ("Hauteur (demi-tons, négatif = plus grave)", "Pitch (semitones, negative = deeper)",
     "Tono (semitoni, negativo = più grave)", "Tono (semitonos, negativo = más grave)"),
    ("**ElevenLabs** : voix très naturelles et voix clonées. Payant, consomme tes crédits. "
     "Clé : elevenlabs.io → Profile → API Keys.",
     "**ElevenLabs**: very natural voices and cloned voices. Paid, uses your credits. "
     "Key: elevenlabs.io → Profile → API Keys.",
     "**ElevenLabs**: voci molto naturali e voci clonate. A pagamento, consuma i tuoi crediti. "
     "Chiave: elevenlabs.io → Profile → API Keys.",
     "**ElevenLabs**: voces muy naturales y voces clonadas. De pago, consume tus créditos. "
     "Clave: elevenlabs.io → Profile → API Keys."),
    ("Clé API", "API key", "Chiave API", "Clave API"),
    ("Mémoriser la clé sur ce PC (voix_config.json)", "Remember the key on this PC (voix_config.json)",
     "Memorizza la chiave su questo PC (voix_config.json)", "Recordar la clave en este PC (voix_config.json)"),
    ("Charger mes voix", "Load my voices", "Carica le mie voci", "Cargar mis voces"),
    ("Stabilité (bas = plus expressif)", "Stability (low = more expressive)", "Stabilità (basso = più espressivo)",
     "Estabilidad (bajo = más expresivo)"),
    ("Fidélité à la voix", "Voice similarity", "Fedeltà alla voce", "Fidelidad a la voz"),
    ("Style / exagération", "Style / exaggeration", "Stile / enfasi", "Estilo / exageración"),
    ("Remplacer la voix d'un clip existant", "Replace the voice of an existing clip",
     "Sostituisci la voce di una clip esistente", "Reemplazar la voz de un clip existente"),
    ("Pour une scène générée avec la mauvaise voix : la voix d'origine est retirée et la nouvelle est posée au moment "
     "choisi, au même volume qu'un clip de référence.",
     "For a scene generated with the wrong voice: the original voice is removed and the new one is placed at the "
     "chosen time, at the same volume as a reference clip.",
     "Per una scena generata con la voce sbagliata: la voce originale viene rimossa e la nuova viene inserita al "
     "momento scelto, allo stesso volume di una clip di riferimento.",
     "Para una escena generada con la voz equivocada: se quita la voz original y se coloca la nueva en el momento "
     "elegido, al mismo volumen que un clip de referencia."),
    ("Clip vidéo", "Video clip", "Clip video", "Clip de vídeo"),
    ("Nouvelle voix (vide = dernière voix générée)", "New voice (empty = last generated voice)",
     "Nuova voce (vuoto = ultima voce generata)", "Nueva voz (vacío = última voz generada)"),
    ("Clip de référence pour le volume (optionnel)", "Reference clip for volume (optional)",
     "Clip di riferimento per il volume (facoltativa)", "Clip de referencia para el volumen (opcional)"),
    ("Début de la voix (s)", "Voice start (s)", "Inizio della voce (s)", "Inicio de la voz (s)"),
    ("Garder le son d'origine (ambiance)", "Keep the original sound (ambience)", "Mantieni il suono originale (ambiente)",
     "Conservar el sonido original (ambiente)"),
    ("Remplacer", "Replace", "Sostituisci", "Reemplazar"),
    ("Créer la voix off à partir de la colonne « texte » (réglages de l'onglet Voix off)",
     "Create the voice-over from the “texte” column (Voice-over tab settings)",
     "Crea la voce fuori campo dalla colonna «texte» (impostazioni della scheda Voce fuori campo)",
     "Crear la voz en off a partir de la columna «texte» (ajustes de la pestaña Voz en off)"),
    ("création de la voix off", "creating the voice-over", "creazione della voce fuori campo", "creando la voz en off"),
    ("🎙 {name} : voix off générée ({dur:.1f} s)", "🎙 {name}: voice-over generated ({dur:.1f} s)",
     "🎙 {name}: voce fuori campo generata ({dur:.1f} s)", "🎙 {name}: voz en off generada ({dur:.1f} s)"),
    ("Clé API ElevenLabs manquante (onglet Voix off, ou variable ELEVENLABS_API_KEY).",
     "ElevenLabs API key missing (Voice-over tab, or ELEVENLABS_API_KEY variable).",
     "Chiave API ElevenLabs mancante (scheda Voce fuori campo, o variabile ELEVENLABS_API_KEY).",
     "Falta la clave API de ElevenLabs (pestaña Voz en off, o variable ELEVENLABS_API_KEY)."),
    ("clé API invalide", "invalid API key", "chiave API non valida", "clave API no válida"),
    ("crédits insuffisants", "insufficient credits", "crediti insufficienti", "créditos insuficientes"),
    ("trop de requêtes, réessaie dans un instant", "too many requests, try again in a moment",
     "troppe richieste, riprova tra poco", "demasiadas solicitudes, inténtalo de nuevo en un momento"),
    ("ElevenLabs a refusé la requête ({code}) : {detail}", "ElevenLabs refused the request ({code}): {detail}",
     "ElevenLabs ha rifiutato la richiesta ({code}): {detail}", "ElevenLabs rechazó la solicitud ({code}): {detail}"),
    ("Impossible de joindre ElevenLabs : {reason}", "Cannot reach ElevenLabs: {reason}",
     "Impossibile raggiungere ElevenLabs: {reason}", "No se puede conectar con ElevenLabs: {reason}"),
    ("Le texte est vide.", "The text is empty.", "Il testo è vuoto.", "El texto está vacío."),
    # ---- recadrage de l'image et sous-titres intégrés à la vidéo
    ("recadrage_%", "crop_%", "ritaglio_%", "recorte_%"),
    ("Recadrer l'image", "Crop the frame", "Ritaglia l'inquadratura", "Recortar el encuadre"),
    ("Retire des bords de l'image (en %). Le recadrage est enregistré avec l'extrait quand tu l'ajoutes à la "
     "timeline (colonne recadrage_% : gauche/haut/droite/bas, modifiable).",
     "Removes edges of the frame (in %). The crop is saved with the clip when you add it to the timeline "
     "(crop_% column: left/top/right/bottom, editable).",
     "Rimuove i bordi dell'immagine (in %). Il ritaglio viene salvato con la clip quando la aggiungi alla "
     "timeline (colonna ritaglio_%: sinistra/alto/destra/basso, modificabile).",
     "Quita bordes de la imagen (en %). El recorte se guarda con el fragmento al añadirlo a la línea de tiempo "
     "(columna recorte_%: izquierda/arriba/derecha/abajo, editable)."),
    ("Gauche (%)", "Left (%)", "Sinistra (%)", "Izquierda (%)"),
    ("Haut (%)", "Top (%)", "Alto (%)", "Arriba (%)"),
    ("Droite (%)", "Right (%)", "Destra (%)", "Derecha (%)"),
    ("Bas (%)", "Bottom (%)", "Basso (%)", "Abajo (%)"),
    ("Proportions", "Aspect ratio", "Proporzioni", "Proporciones"),
    ("libre", "free", "libero", "libre"),
    ("Réinitialiser", "Reset", "Reimposta", "Restablecer"),
    ("vidéo", "video track", "traccia del video", "pista del vídeo"),
    ("Langue (Whisper, piste de la vidéo)", "Language (Whisper, video track)", "Lingua (Whisper, traccia del video)",
     "Idioma (Whisper, pista del vídeo)"),
    ("sous-titres : {langs}", "subtitles: {langs}", "sottotitoli: {langs}", "subtítulos: {langs}"),
    ("Recadrage invalide : « {v} » (attendu : gauche/haut/droite/bas en %, ex. 10/0/10/0)",
     "Invalid crop: “{v}” (expected: left/top/right/bottom in %, e.g. 10/0/10/0)",
     "Ritaglio non valido: «{v}» (atteso: sinistra/alto/destra/basso in %, es. 10/0/10/0)",
     "Recorte no válido: «{v}» (se espera: izquierda/arriba/derecha/abajo en %, p. ej. 10/0/10/0)"),
    ("⚠ Aucune piste de sous-titres dans {name}", "⚠ No subtitle track in {name}",
     "⚠ Nessuna traccia di sottotitoli in {name}", "⚠ No hay pista de subtítulos en {name}"),
    ("⚠ Sous-titres en image dans {name} : non pris en charge, utilise Whisper",
     "⚠ Image-based subtitles in {name}: not supported, use Whisper",
     "⚠ Sottotitoli in formato immagine in {name}: non supportati, usa Whisper",
     "⚠ Subtítulos en imagen en {name}: no compatibles, usa Whisper"),
    ("💬 {n} sous-titres repris de {name} (piste {lang})", "💬 {n} subtitles taken from {name} ({lang} track)",
     "💬 {n} sottotitoli presi da {name} (traccia {lang})", "💬 {n} subtítulos tomados de {name} (pista {lang})"),
    # ---- convertisseur de temps, effacement de logo, logo MSV
    ("Convertisseur de temps", "Time converter", "Convertitore di tempo", "Conversor de tiempo"),
    ("Durée à convertir", "Duration to convert", "Durata da convertire", "Duración a convertir"),
    ("Secondes", "Seconds", "Secondi", "Segundos"),
    ("Minutes", "Minutes", "Minuti", "Minutos"),
    ("Heures", "Hours", "Ore", "Horas"),
    ("→ Début", "→ Start", "→ Inizio", "→ Inicio"),
    ("→ Fin", "→ End", "→ Fine", "→ Fin"),
    ("Format non reconnu. Exemples : 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2,5 min",
     "Unrecognized format. Examples: 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2.5 min",
     "Formato non riconosciuto. Esempi: 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2,5 min",
     "Formato no reconocido. Ejemplos: 90 · 1:30 · 1:02:03 · 1h 2m 3s · 2,5 min"),
    ("Effacer un logo", "Remove a logo", "Rimuovi un logo", "Quitar un logo"),
    ("logo, filigrane, texte", "logo, watermark, text", "logo, filigrana, testo", "logo, marca de agua, texto"),
    ("Utilise cet outil uniquement sur des vidéos dont tu détiens les droits (par exemple pour retirer ton ancien logo).",
     "Only use this tool on videos you own the rights to (for example to remove your old logo).",
     "Usa questo strumento solo su video di cui possiedi i diritti (per esempio per togliere il tuo vecchio logo).",
     "Usa esta herramienta solo con vídeos de los que tengas los derechos (por ejemplo, para quitar tu antiguo logo)."),
    ("Zone rapide", "Quick area", "Zona rapida", "Zona rápida"),
    ("Méthode", "Method", "Metodo", "Método"),
    ("effacer", "erase", "cancella", "borrar"),
    ("flouter", "blur", "sfoca", "desenfocar"),
    ("Largeur (%)", "Width (%)", "Larghezza (%)", "Ancho (%)"),
    ("Hauteur (%)", "Height (%)", "Altezza (%)", "Alto (%)"),
    ("Aperçu", "Preview", "Anteprima", "Vista previa"),
    ("Zone choisie", "Selected area", "Zona scelta", "Zona elegida"),
    ("Après effacement", "After removal", "Dopo la rimozione", "Tras borrar"),
    ("Effacer sur toute la vidéo", "Remove from the whole video", "Rimuovi da tutto il video",
     "Quitar de todo el vídeo"),
    ("Logo MSV", "MSV logo", "Logo MSV", "Logo MSV"),
    ("ajouter ou enlever ton logo", "add or remove your logo", "aggiungi o togli il tuo logo",
     "añade o quita tu logo"),
    ("Action", "Action", "Azione", "Acción"),
    ("ajouter", "add", "aggiungi", "añadir"),
    ("enlever", "remove", "togli", "quitar"),
    ("Modèle de logo", "Logo style", "Tipo di logo", "Tipo de logo"),
    ("icône", "icon", "icona", "icono"),
    ("logo complet", "full logo", "logo completo", "logo completo"),
    ("Méthode (pour enlever)", "Method (to remove)", "Metodo (per togliere)", "Método (para quitar)"),
    ("Appliquer", "Apply", "Applica", "Aplicar"),
    ("Traitement de la vidéo", "Processing the video", "Elaborazione del video", "Procesando el vídeo"),
    ("Ce fichier n'est pas une vidéo : {name}", "This file is not a video: {name}", "Questo file non è un video: {name}",
     "Este archivo no es un vídeo: {name}"),
    ("✅ Logo MSV ajouté : sa position est mémorisée dans la vidéo pour pouvoir l'enlever plus tard.",
     "✅ MSV logo added: its position is stored in the video so it can be removed later.",
     "✅ Logo MSV aggiunto: la sua posizione è memorizzata nel video per poterlo togliere in seguito.",
     "✅ Logo MSV añadido: su posición se guarda en el vídeo para poder quitarlo más tarde."),
    ("✅ Logo MSV enlevé (position exacte retrouvée dans la vidéo).",
     "✅ MSV logo removed (exact position found in the video).",
     "✅ Logo MSV tolto (posizione esatta ritrovata nel video).",
     "✅ Logo MSV quitado (posición exacta encontrada en el vídeo)."),
    ("✅ Logo enlevé à la position choisie (cette vidéo ne contenait pas la position mémorisée : "
     "vérifie que position et taille correspondent).",
     "✅ Logo removed at the chosen position (this video had no stored position: check that position and size match).",
     "✅ Logo tolto nella posizione scelta (questo video non conteneva la posizione memorizzata: "
     "controlla che posizione e dimensione corrispondano).",
     "✅ Logo quitado en la posición elegida (este vídeo no tenía la posición guardada: "
     "comprueba que la posición y el tamaño coinciden)."),

    # ---- calques (incrustations, textes animés) et mouvement des images
    ("Calques", "Layers", "Livelli", "Capas"),
    ("incrustations et textes animés", "overlays and animated text", "sovrapposizioni e testi animati",
     "superposiciones y textos animados"),
    ("Par-dessus le montage, sous le titre et les sous-titres. Les heures sont celles de la vidéo finale ; "
     "« disparaît à » vide ou 0 = jusqu'à la fin.",
     "On top of the edit, below the title and subtitles. Times refer to the final video; "
     "empty or 0 “disappears at” = until the end.",
     "Sopra il montaggio, sotto il titolo e i sottotitoli. I tempi sono quelli del video finale; "
     "« scompare a » vuoto o 0 = fino alla fine.",
     "Encima del montaje, debajo del título y los subtítulos. Los tiempos son los del vídeo final; "
     "«desaparece en» vacío o 0 = hasta el final."),
    ("Image ou vidéo incrustée", "Image or video overlay", "Immagine o video sovrapposto",
     "Imagen o vídeo superpuesto"),
    ("Texte animé", "Animated text", "Testo animato", "Texto animado"),
    ("capture d'écran, sticker, photo ou vidéo (picture-in-picture, sans son)",
     "screenshot, sticker, photo or video (picture-in-picture, muted)",
     "screenshot, sticker, foto o video (picture-in-picture, senza audio)",
     "captura de pantalla, sticker, foto o vídeo (picture-in-picture, sin sonido)"),
    ("Entrée animée", "Entrance animation", "Entrata animata", "Entrada animada"),
    ("Position rapide", "Quick position", "Posizione rapida", "Posición rápida"),
    ("Centre X (%)", "Center X (%)", "Centro X (%)", "Centro X (%)"),
    ("Centre Y (%)", "Center Y (%)", "Centro Y (%)", "Centro Y (%)"),
    ("Ajouter l'incrustation", "Add overlay", "Aggiungi la sovrapposizione", "Añadir la superposición"),
    ("Ajouter le texte", "Add text", "Aggiungi il testo", "Añadir el texto"),
    ("Fond derrière le texte", "Background behind text", "Sfondo dietro il testo", "Fondo detrás del texto"),
    ("Abonne-toi !", "Subscribe!", "Iscriviti!", "¡Suscríbete!"),
    ("Une incrustation doit être une image ou une vidéo.", "An overlay must be an image or a video.",
     "Una sovrapposizione deve essere un'immagine o un video.", "Una superposición debe ser una imagen o un vídeo."),
    ("Écris le texte à afficher.", "Type the text to display.", "Scrivi il testo da mostrare.",
     "Escribe el texto que se mostrará."),
    ("⚠ Calque ignoré (hors de la vidéo ou durée nulle) : {name}",
     "⚠ Layer skipped (outside the video or zero duration): {name}",
     "⚠ Livello ignorato (fuori dal video o durata nulla): {name}",
     "⚠ Capa ignorada (fuera del vídeo o duración nula): {name}"),
    ("⚠ Calque ignoré (ni image ni vidéo) : {name}", "⚠ Layer skipped (neither image nor video): {name}",
     "⚠ Livello ignorato (né immagine né video): {name}", "⚠ Capa ignorada (ni imagen ni vídeo): {name}"),
    ("Aperçu du texte et des calques (instantané)", "Text and layers preview (instant)",
     "Anteprima di testi e livelli (istantanea)", "Vista previa de textos y capas (instantánea)"),
    ("Aperçu du titre, des sous-titres et des calques", "Title, subtitles and layers preview",
     "Anteprima di titolo, sottotitoli e livelli", "Vista previa del título, los subtítulos y las capas"),
    ("pour une seule image : colonne « mouvement » de la timeline",
     "for a single image: “motion” column of the timeline",
     "per una sola immagine: colonna « movimento » della timeline",
     "para una sola imagen: columna «movimiento» de la línea de tiempo"),
    ("Calque ajouté : visible de {s} s à {e} s.", "Layer added: visible from {s} s to {e} s.",
     "Livello aggiunto: visibile da {s} s a {e} s.", "Capa añadida: visible de {s} s a {e} s."),
    ("Calque ajouté : visible de {s} s jusqu'à la fin.", "Layer added: visible from {s} s until the end.",
     "Livello aggiunto: visibile da {s} s fino alla fine.", "Capa añadida: visible desde {s} s hasta el final."),
    ("Les champs servent à ajouter un nouveau calque. Pour changer un calque déjà ajouté (heures, position, "
     "couleur…), modifie sa ligne dans le tableau.",
     "The fields add a new layer. To change a layer already added (times, position, color…), edit its row in the "
     "table.",
     "I campi servono ad aggiungere un nuovo livello. Per cambiare un livello già aggiunto (tempi, posizione, "
     "colore…), modifica la sua riga nella tabella.",
     "Los campos sirven para añadir una capa nueva. Para cambiar una capa ya añadida (tiempos, posición, "
     "color…), modifica su fila en la tabla."),
    ("Couleur du texte", "Text color", "Colore del testo", "Color del texto"),
    ("clique sur le carré de couleur", "click the color square", "clicca sul quadrato colorato",
     "haz clic en el cuadrado de color"),
    ("Moment de l'aperçu (s)", "Preview time (s)", "Momento dell'anteprima (s)", "Momento de la vista previa (s)"),
    # ---- messages d'erreur : problème + que faire (core/errors.py)
    ("Un problème est survenu", "Something went wrong", "Si è verificato un problema", "Se ha producido un problema"),
    ("Que faire : ", "What to do: ", "Cosa fare: ", "Qué hacer: "),
    ("Détail technique : ", "Technical detail: ", "Dettaglio tecnico: ", "Detalle técnico: "),
    ("Journal complet : {path}", "Full log: {path}", "Registro completo: {path}", "Registro completo: {path}"),
    ("Le fichier de projet n'est pas un JSON valide (ligne {l}, colonne {c}).",
     "The project file is not valid JSON (line {l}, column {c}).",
     "Il file di progetto non è un JSON valido (riga {l}, colonna {c}).",
     "El archivo de proyecto no es un JSON válido (línea {l}, columna {c})."),
    ("Charge un projet enregistré par MSV, ou corrige le fichier dans un éditeur de texte (virgule ou guillemet "
     "manquant à l'endroit indiqué).",
     "Load a project saved by MSV, or fix the file in a text editor (missing comma or quote at the position shown).",
     "Carica un progetto salvato da MSV, oppure correggi il file in un editor di testo (virgola o virgolette "
     "mancanti nel punto indicato).",
     "Carga un proyecto guardado por MSV, o corrige el archivo en un editor de texto (falta una coma o unas "
     "comillas en el lugar indicado)."),
    ("Le fichier (CSV ou texte) n'est pas lisible.", "The file (CSV or text) cannot be read.",
     "Il file (CSV o testo) non è leggibile.", "El archivo (CSV o texto) no se puede leer."),
    ("Enregistre-le en « CSV UTF-8 » (Excel : Fichier → Enregistrer sous → CSV UTF-8), avec « ; » ou « , » comme "
     "séparateur et une ligne d'en-tête (voir les exemples de CSV).",
     "Save it as “CSV UTF-8” (Excel: File → Save As → CSV UTF-8), with “;” or “,” as separator and a header row "
     "(see the CSV examples).",
     "Salvalo come « CSV UTF-8 » (Excel: File → Salva con nome → CSV UTF-8), con « ; » o « , » come separatore e "
     "una riga di intestazione (vedi gli esempi di CSV).",
     "Guárdalo como «CSV UTF-8» (Excel: Archivo → Guardar como → CSV UTF-8), con «;» o «,» como separador y una "
     "fila de encabezado (mira los ejemplos de CSV)."),
    ("Un fichier vidéo ou audio est abîmé ou incomplet.", "A video or audio file is damaged or incomplete.",
     "Un file video o audio è danneggiato o incompleto.", "Un archivo de vídeo o audio está dañado o incompleto."),
    ("S'il est encore en cours de téléchargement ou de copie, attends la fin. Sinon, ouvre-le dans un lecteur vidéo "
     "pour vérifier, puis re-télécharge-le ou réexporte-le en MP4 (H.264).",
     "If it is still downloading or copying, wait until it finishes. Otherwise, open it in a video player to check, "
     "then download it again or re-export it as MP4 (H.264).",
     "Se è ancora in download o in copia, aspetta che finisca. Altrimenti aprilo in un lettore video per "
     "controllarlo, poi scaricalo di nuovo o riesportalo in MP4 (H.264).",
     "Si todavía se está descargando o copiando, espera a que termine. Si no, ábrelo en un reproductor para "
     "comprobarlo y vuelve a descargarlo o a exportarlo en MP4 (H.264)."),
    ("FFmpeg ne trouve pas un des fichiers du projet.", "FFmpeg cannot find one of the project files.",
     "FFmpeg non trova uno dei file del progetto.", "FFmpeg no encuentra uno de los archivos del proyecto."),
    ("Vérifie qu'aucun fichier n'a été déplacé ou renommé : réimporte-le dans la médiathèque et remplace-le dans la "
     "timeline, la voix off, la musique ou les calques.",
     "Check that no file was moved or renamed: import it again into the library and replace it in the timeline, "
     "voice-over, music or layers.",
     "Controlla che nessun file sia stato spostato o rinominato: reimportalo nella libreria e sostituiscilo nella "
     "timeline, nella voce fuori campo, nella musica o nei livelli.",
     "Comprueba que ningún archivo se haya movido o renombrado: vuelve a importarlo en la biblioteca y sustitúyelo "
     "en la línea de tiempo, la voz en off, la música o las capas."),
    ("Un fichier est verrouillé par un autre programme.", "A file is locked by another program.",
     "Un file è bloccato da un altro programma.", "Un archivo está bloqueado por otro programa."),
    ("Ferme le lecteur vidéo, l'explorateur ou le logiciel qui utilise le fichier, puis relance.",
     "Close the video player, file explorer or software using the file, then try again.",
     "Chiudi il lettore video, Esplora file o il programma che usa il file, poi riprova.",
     "Cierra el reproductor, el explorador o el programa que usa el archivo y vuelve a intentarlo."),
    ("Le disque est plein.", "The disk is full.", "Il disco è pieno.", "El disco está lleno."),
    ("Libère de l'espace (anciens rendus du dossier sorties, corbeille), puis relance.",
     "Free up space (old renders in the sorties folder, recycle bin), then try again.",
     "Libera spazio (vecchi render nella cartella sorties, cestino), poi riprova.",
     "Libera espacio (renders antiguos de la carpeta sorties, papelera) y vuelve a intentarlo."),
    ("L'encodeur de la carte graphique n'est pas disponible sur cet ordinateur.",
     "The graphics card encoder is not available on this computer.",
     "L'encoder della scheda grafica non è disponibile su questo computer.",
     "El codificador de la tarjeta gráfica no está disponible en este ordenador."),
    ("Dans « Format et rendu », choisis l'encodeur « cpu (x264) ».",
     "In “Format and render”, choose the “cpu (x264)” encoder.",
     "In « Formato e rendering », scegli l'encoder « cpu (x264) ».",
     "En «Formato y renderizado», elige el codificador «cpu (x264)»."),
    ("L'ordinateur manque de mémoire.", "The computer is out of memory.", "Il computer non ha abbastanza memoria.",
     "El ordenador no tiene suficiente memoria."),
    ("Ferme d'autres programmes, utilise l'aperçu rapide ou une qualité plus basse, ou découpe la vidéo.",
     "Close other programs, use the quick preview or a lower quality, or split the video.",
     "Chiudi altri programmi, usa l'anteprima rapida o una qualità più bassa, oppure dividi il video.",
     "Cierra otros programas, usa la vista previa rápida o una calidad más baja, o divide el vídeo."),
    ("FFmpeg n'a pas pu fabriquer la vidéo.", "FFmpeg could not build the video.", "FFmpeg non è riuscito a creare il video.",
     "FFmpeg no ha podido crear el vídeo."),
    ("Lance un aperçu rapide avec un seul extrait à la fois pour trouver le fichier en cause, vérifie ses heures de "
     "début et de fin, puis relance.",
     "Run a quick preview with one clip at a time to find the faulty file, check its start and end times, then try "
     "again.",
     "Fai un'anteprima rapida con una clip alla volta per trovare il file che dà problemi, controlla inizio e fine, "
     "poi riprova.",
     "Haz una vista previa rápida con un solo fragmento cada vez para encontrar el archivo que falla, comprueba su "
     "inicio y su fin y vuelve a intentarlo."),
    ("La voix Piper n'a produit aucun son.", "The Piper voice produced no sound.", "La voce Piper non ha prodotto alcun suono.",
     "La voz Piper no ha producido ningún sonido."),
    ("La voix Piper n'a produit aucun son pour « {text} ».", "The Piper voice produced no sound for “{text}”.",
     "La voce Piper non ha prodotto alcun suono per « {text} ».", "La voz Piper no ha producido ningún sonido para «{text}»."),
    ("Vérifie que le texte contient des mots (pas seulement des chiffres ou des symboles). Si l'erreur touche "
     "toutes les phrases, réinstalle le moteur de voix compatible : {cmd}",
     "Check that the text contains words (not only numbers or symbols). If every sentence fails, reinstall the "
     "compatible voice engine: {cmd}",
     "Controlla che il testo contenga parole (non solo numeri o simboli). Se l'errore riguarda tutte le frasi, "
     "reinstalla il motore vocale compatibile: {cmd}",
     "Comprueba que el texto contiene palabras (no solo números o símbolos). Si falla con todas las frases, "
     "reinstala el motor de voz compatible: {cmd}"),
    ("Piper n'est pas installé. Dans le dossier de l'application, lance : {cmd}",
     "Piper is not installed. In the application folder, run: {cmd}",
     "Piper non è installato. Nella cartella dell'applicazione, esegui: {cmd}",
     "Piper no está instalado. En la carpeta de la aplicación, ejecuta: {cmd}"),
    ("La version {v} de sherpa-onnx ne sait plus faire parler les voix Piper. Remets la version compatible : {cmd}",
     "sherpa-onnx version {v} can no longer speak with Piper voices. Reinstall the compatible version: {cmd}",
     "La versione {v} di sherpa-onnx non sa più far parlare le voci Piper. Reinstalla la versione compatibile: {cmd}",
     "La versión {v} de sherpa-onnx ya no puede hacer hablar a las voces Piper. Vuelve a instalar la versión "
     "compatible: {cmd}"),
    ("Un module Python manque : {mod}.", "A Python module is missing: {mod}.", "Manca un modulo Python: {mod}.",
     "Falta un módulo de Python: {mod}."),
    ("Dans le dossier de l'application, lance : {cmd}", "In the application folder, run: {cmd}",
     "Nella cartella dell'applicazione, esegui: {cmd}", "En la carpeta de la aplicación, ejecuta: {cmd}"),
    ("Fichier introuvable : {name}", "File not found: {name}", "File non trovato: {name}",
     "Archivo no encontrado: {name}"),
    ("Il a été déplacé, renommé ou supprimé. Réimporte-le dans la médiathèque et remets-le à sa place (timeline, "
     "calques, voix off ou musique).",
     "It was moved, renamed or deleted. Import it again into the library and put it back in place (timeline, "
     "layers, voice-over or music).",
     "È stato spostato, rinominato o eliminato. Reimportalo nella libreria e rimettilo al suo posto (timeline, "
     "livelli, voce fuori campo o musica).",
     "Se ha movido, renombrado o eliminado. Vuelve a importarlo en la biblioteca y ponlo en su sitio (línea de "
     "tiempo, capas, voz en off o música)."),
    ("Accès refusé au fichier {name}.", "Access denied to the file {name}.", "Accesso negato al file {name}.",
     "Acceso denegado al archivo {name}."),
    ("Ferme le programme qui l'utilise (lecteur vidéo, Excel…) ou choisis un autre dossier, puis relance.",
     "Close the program using it (video player, Excel…) or choose another folder, then try again.",
     "Chiudi il programma che lo usa (lettore video, Excel…) o scegli un'altra cartella, poi riprova.",
     "Cierra el programa que lo usa (reproductor, Excel…) o elige otra carpeta y vuelve a intentarlo."),
    ("Pas de connexion à Internet (ou le service ne répond pas).", "No Internet connection (or the service is not "
     "responding).", "Nessuna connessione a Internet (o il servizio non risponde).",
     "No hay conexión a Internet (o el servicio no responde)."),
    ("Vérifie ta connexion : elle est nécessaire pour ElevenLabs et pour le premier téléchargement d'une voix Piper "
     "ou d'un modèle Whisper. Le montage, lui, fonctionne hors ligne.",
     "Check your connection: it is needed for ElevenLabs and for the first download of a Piper voice or a Whisper "
     "model. Editing itself works offline.",
     "Controlla la connessione: serve per ElevenLabs e per il primo download di una voce Piper o di un modello "
     "Whisper. Il montaggio invece funziona offline.",
     "Comprueba tu conexión: hace falta para ElevenLabs y para la primera descarga de una voz Piper o de un modelo "
     "Whisper. La edición funciona sin conexión."),
    ("Cette image n'est pas lisible.", "This image cannot be read.", "Questa immagine non è leggibile.",
     "Esta imagen no se puede leer."),
    ("Convertis-la en PNG ou en JPG, puis réimporte-la.", "Convert it to PNG or JPG, then import it again.",
     "Convertila in PNG o JPG, poi reimportala.", "Conviértela a PNG o JPG y vuelve a importarla."),
    ("Corrige la valeur indiquée puis relance.", "Fix the value shown, then try again.",
     "Correggi il valore indicato, poi riprova.", "Corrige el valor indicado y vuelve a intentarlo."),
    ("Erreur interne de MSV ({kind}).", "MSV internal error ({kind}).", "Errore interno di MSV ({kind}).",
     "Error interno de MSV ({kind})."),
    ("Ce n'est pas de ta faute. Réessaie une fois ; si l'erreur revient, envoie le fichier journal_erreurs.log au "
     "développeur (GitHub → Issues) en expliquant ce que tu faisais.",
     "It's not your fault. Try once more; if the error comes back, send the journal_erreurs.log file to the "
     "developer (GitHub → Issues) and explain what you were doing.",
     "Non è colpa tua. Riprova una volta; se l'errore ritorna, invia il file journal_erreurs.log allo sviluppatore "
     "(GitHub → Issues) spiegando cosa stavi facendo.",
     "No es culpa tuya. Vuelve a intentarlo una vez; si el error se repite, envía el archivo journal_erreurs.log al "
     "desarrollador (GitHub → Issues) explicando lo que estabas haciendo."),
    # erreurs de sens dans la timeline et les calques
    ("Ligne {n} de la timeline : ", "Timeline row {n}: ", "Riga {n} della timeline: ", "Fila {n} de la línea de tiempo: "),
    ("fichier introuvable ({name}).", "file not found ({name}).", "file non trovato ({name}).",
     "archivo no encontrado ({name})."),
    ("Le fichier a été déplacé, renommé ou supprimé : réimporte-le puis corrige la colonne « fichier » (ou retire la "
     "ligne).",
     "The file was moved, renamed or deleted: import it again and fix the “file” column (or remove the row).",
     "Il file è stato spostato, rinominato o eliminato: reimportalo e correggi la colonna « file » (o togli la riga).",
     "El archivo se ha movido, renombrado o eliminado: vuelve a importarlo y corrige la columna «archivo» (o quita "
     "la fila)."),
    ("ce fichier n'est ni une vidéo ni une image ({name}).", "this file is neither a video nor an image ({name}).",
     "questo file non è né un video né un'immagine ({name}).", "este archivo no es ni un vídeo ni una imagen ({name})."),
    ("Un fichier audio va dans « Audio » (voix off ou musique), pas dans la timeline.",
     "An audio file goes in “Audio” (voice-over or music), not in the timeline.",
     "Un file audio va in « Audio » (voce fuori campo o musica), non nella timeline.",
     "Un archivo de audio va en «Audio» (voz en off o música), no en la línea de tiempo."),
    ("vitesse {v:g} impossible.", "speed {v:g} is not possible.", "velocità {v:g} impossibile.",
     "velocidad {v:g} imposible."),
    ("Écris une vitesse entre 0,1 et 4 (1 = normale, 2 = deux fois plus rapide).",
     "Enter a speed between 0.1 and 4 (1 = normal, 2 = twice as fast).",
     "Scrivi una velocità tra 0,1 e 4 (1 = normale, 2 = due volte più veloce).",
     "Escribe una velocidad entre 0,1 y 4 (1 = normal, 2 = el doble de rápido)."),
    ("volume négatif.", "negative volume.", "volume negativo.", "volumen negativo."),
    ("Écris un volume entre 0 (muet) et 2 (double).", "Enter a volume between 0 (muted) and 2 (double).",
     "Scrivi un volume tra 0 (muto) e 2 (doppio).", "Escribe un volumen entre 0 (silencio) y 2 (doble)."),
    ("le début ({s:g} s) est après la fin du fichier ({d:.1f} s).",
     "the start ({s:g} s) is after the end of the file ({d:.1f} s).",
     "l'inizio ({s:g} s) è dopo la fine del file ({d:.1f} s).",
     "el inicio ({s:g} s) está después del final del archivo ({d:.1f} s)."),
    ("Écris un début plus petit que {d:.1f} s (colonne « début »).",
     "Enter a start smaller than {d:.1f} s (“start” column).",
     "Scrivi un inizio più piccolo di {d:.1f} s (colonna « inizio »).",
     "Escribe un inicio menor que {d:.1f} s (columna «inicio»)."),
    ("la fin ({e:g} s) est avant le début ({s:g} s).", "the end ({e:g} s) is before the start ({s:g} s).",
     "la fine ({e:g} s) è prima dell'inizio ({s:g} s).", "el fin ({e:g} s) está antes del inicio ({s:g} s)."),
    ("Corrige les colonnes « début » et « fin » : la fin doit être plus grande que le début (laisse « fin » vide pour "
     "aller jusqu'au bout du fichier).",
     "Fix the “start” and “end” columns: the end must be greater than the start (leave “end” empty to go to the end "
     "of the file).",
     "Correggi le colonne « inizio » e « fine »: la fine deve essere più grande dell'inizio (lascia « fine » vuota "
     "per arrivare alla fine del file).",
     "Corrige las columnas «inicio» y «fin»: el fin debe ser mayor que el inicio (deja «fin» vacío para llegar al "
     "final del archivo)."),
    ("Écris le recadrage en % retirés de chaque bord, dans l'ordre gauche/haut/droite/bas, par exemple 10/0/10/0 "
     "(ou laisse la case vide).",
     "Enter the crop as % removed from each edge, in the order left/top/right/bottom, e.g. 10/0/10/0 (or leave the "
     "cell empty).",
     "Scrivi il ritaglio in % tolti da ogni bordo, nell'ordine sinistra/alto/destra/basso, per esempio 10/0/10/0 "
     "(o lascia la cella vuota).",
     "Escribe el recorte en % quitado de cada borde, en el orden izquierda/arriba/derecha/abajo, por ejemplo "
     "10/0/10/0 (o deja la celda vacía)."),
    ("L'heure d'apparition ne peut pas être négative.", "The appearance time cannot be negative.",
     "Il momento di comparsa non può essere negativo.", "El momento de aparición no puede ser negativo."),
    ("Écris 0 ou plus dans « Apparaît à ».", "Enter 0 or more in “Appears at”.", "Scrivi 0 o più in « Appare a ».",
     "Escribe 0 o más en «Aparece en»."),
    ("Le calque disparaîtrait ({e:g} s) avant d'apparaître ({s:g} s).",
     "The layer would disappear ({e:g} s) before appearing ({s:g} s).",
     "Il livello scomparirebbe ({e:g} s) prima di apparire ({s:g} s).",
     "La capa desaparecería ({e:g} s) antes de aparecer ({s:g} s)."),
    ("Mets dans « Disparaît à » une heure plus grande que « Apparaît à », ou 0 pour garder le calque jusqu'à la fin.",
     "Put a time greater than “Appears at” in “Disappears at”, or 0 to keep the layer until the end.",
     "Metti in « Scompare a » un tempo più grande di « Appare a », oppure 0 per tenere il livello fino alla fine.",
     "Pon en «Desaparece en» un tiempo mayor que «Aparece en», o 0 para mantener la capa hasta el final."),
    # animations et positions des calques
    ("fondu", "fade", "dissolvenza", "fundido"),
    ("montée", "rise", "salita", "subida"),
    ("haut", "top", "in alto", "arriba"),
    ("bas", "bottom", "in basso", "abajo"),
    # mouvements des images fixes
    ("panoramique vers la droite", "pan right", "panoramica a destra", "paneo a la derecha"),
    ("panoramique vers la gauche", "pan left", "panoramica a sinistra", "paneo a la izquierda"),
    ("Ken Burns", "Ken Burns", "Ken Burns", "Ken Burns"),
    # colonnes des tableaux
    ("mouvement", "motion", "movimento", "movimiento"),
    ("largeur_%", "width_%", "larghezza_%", "ancho_%"),
    ("opacité", "opacity", "opacità", "opacidad"),
    ("animation", "animation", "animazione", "animación"),
    ("texte", "text", "testo", "texto"),
    ("taille", "size", "dimensione", "tamaño"),
]

HELP = {
    "fr": """
### Démarrage rapide
1. **Médiathèque** : importe tes vidéos et images (ou indique un dossier de ton PC).
2. **Inspecteur** : choisis un média, déplace le curseur, fixe le début et la fin, puis ajoute l'extrait à la timeline.
   « Recadrer l'image » retire des bords (en %) ou garde une zone au format 9:16, 1:1, 4:5 ou 16:9.
3. **Timeline** : modifie directement les cellules (ordre, vitesse 0,5 à 4, volume 0 à 2, cadrage_x 0 = gauche, 1 = droite).
4. **Réglages** à droite, puis **Aperçu rapide** (demi-résolution, très rapide) et **Exporter la vidéo**.

### Shorts en série
Prépare un modèle (onglet Montage → « Enregistrer comme modèle », ou un des modèles fournis), puis un tableau CSV
où **une ligne = une vidéo**. Colonnes : `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage`.
Dans `medias`, sépare les fichiers par `|`, indique un dossier entier, ou un motif comme `images/*.jpg`.
Si la ligne contient des images et une voix off, les images sont réparties automatiquement sur la durée de la voix.

### Sous-titres
- **script** : colle le texte, il est découpé et minuté automatiquement (sur la durée de la voix off s'il y en a une).
- **srt** : fichier de sous-titres existant (par exemple exporté de ton générateur de voix).
- **whisper** : transcription automatique au mot près, après `pip install faster-whisper`.
- **vidéo** : active les sous-titres déjà intégrés au fichier vidéo (MP4, MKV), dans la langue choisie ;
  ils restent synchronisés même après coupe, changement de vitesse ou suppression des silences.
Un fichier `.srt` est toujours créé à côté de la vidéo : tu peux l'envoyer sur YouTube.

### Calques et photos animées
- **Image ou vidéo incrustée** (section 4) : capture d'écran, sticker, logo ou vidéo par-dessus le montage
  (picture-in-picture). Choisis le média dans la médiathèque, les heures d'apparition, la position (centre en %),
  la largeur et l'entrée animée : **fondu**, **montée** ou **zoom** (avec un léger rebond). Les images opaques et les
  vidéos ont des coins arrondis ; la vidéo incrustée est muette et bouclée si elle est trop courte.
- **Texte animé** : autant de textes que tu veux, chacun avec ses heures, sa position, sa taille, sa couleur et son
  entrée. Les tableaux restent modifiables (animation en toutes lettres, « fin » vide = jusqu'à la fin).
- **Mouvement des photos** (Réglages → Images fixes) : zoom avant ou arrière, panoramique, ou **Ken Burns** (zoom lent
  et déplacement, avec un trajet différent à chaque photo). La colonne « mouvement » de la timeline règle une photo
  précise.

### Voix off
Onglet **Voix off** : écris le texte (scènes séparées par `---`), choisis **Piper** (gratuit, hors ligne) ou
**ElevenLabs** (ta clé API, voix très naturelles et minutage exact des sous-titres), puis « Utiliser dans l'onglet Montage ».
En série, coche « Créer la voix off à partir de la colonne texte ». Une scène générée avec la mauvaise voix se corrige
avec « Remplacer la voix d'un clip existant ».

### Outils rapides
- **Convertisseur de temps** (Inspecteur) : tape `90`, `1:30`, `1h 2m 3s` ou `2,5 min`, puis « → Début » / « → Fin ».
- **Effacer un logo** : choisis la zone (coin rapide + curseurs), vérifie avec « Aperçu », puis efface sur toute la vidéo.
- **Logo MSV** : ajoute ton logo [ ▶ ] ; sa position est mémorisée dans la vidéo pour l'enlever ensuite exactement.

### Conseils de performance
Les rendus « aperçu » sont 3 à 5 fois plus rapides. Si tu as une carte NVIDIA, choisis l'encodeur « nvidia (nvenc) ».
En cas d'échec de l'encodeur GPU, le logiciel repasse automatiquement sur le CPU.
""",
    "en": """
### Quick start
1. **Media library**: import your videos and images (or enter a folder on your PC).
2. **Inspector**: choose a file, move the cursor, set the start and end, then add the clip to the timeline.
   “Crop the frame” removes edges (in %) or keeps a 9:16, 1:1, 4:5 or 16:9 area.
3. **Timeline**: edit the cells directly (order, speed 0.5 to 4, volume 0 to 2, crop_x 0 = left, 1 = right).
4. **Settings** on the right, then **Quick preview** (half resolution, very fast) and **Export video**.

### Batch Shorts
Prepare a template (Editor tab → “Save settings as batch template”, or one of the bundled templates), then a CSV table
where **one row = one video**. Columns: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage`
(column names stay in French). In `medias`, separate files with `|`, give a whole folder, or a pattern like `images/*.jpg`.
If a row contains images and a voice-over, the images are spread automatically over the length of the voice.

### Subtitles
- **script**: paste the text; it is split and timed automatically (over the voice-over length if there is one).
- **srt**: an existing subtitle file (for example exported from your voice generator).
- **whisper**: automatic word-level transcription, after `pip install faster-whisper`.
- **video track**: turns on the subtitles already embedded in the video file (MP4, MKV), in the chosen language;
  they stay in sync even after trimming, speed changes or silence removal.
A `.srt` file is always created next to the video: you can upload it to YouTube.

### Layers and animated photos
- **Image or video overlay** (section 4): screenshot, sticker, logo or video on top of the edit (picture-in-picture).
  Pick the media from the library, when it appears, its position (center in %), width and entrance animation:
  **fade**, **rise** or **zoom** (with a slight bounce). Opaque images and videos get rounded corners; the overlay
  video is muted and looped if it is too short.
- **Animated text**: as many texts as you like, each with its own times, position, size, color and entrance.
  The tables stay editable (animation written out in full, empty “end” = until the end).
- **Photo motion** (Settings → Still images): zoom in or out, pan, or **Ken Burns** (slow zoom and drift, with a
  different path for each photo). The timeline's “motion” column sets the motion of a single photo.

### Voice-over
**Voice-over** tab: write the text (scenes separated by `---`), choose **Piper** (free, offline) or
**ElevenLabs** (your API key, very natural voices and exact subtitle timing), then “Use in the Editor tab”.
In batch mode, tick “Create the voice-over from the texte column”. A scene generated with the wrong voice can be fixed
with “Replace the voice of an existing clip”.

### Quick tools
- **Time converter** (Inspector): type `90`, `1:30`, `1h 2m 3s` or `2.5 min`, then “→ Start” / “→ End”.
- **Remove a logo**: choose the area (quick corner + sliders), check with “Preview”, then remove it from the whole video.
- **MSV logo**: add your [ ▶ ] logo; its position is stored in the video so it can be removed exactly later.

### Performance tips
“Preview” renders are 3 to 5 times faster. If you have an NVIDIA card, choose the “nvidia (nvenc)” encoder.
If the GPU encoder fails, the software automatically falls back to the CPU.
""",
    "it": """
### Avvio rapido
1. **Libreria media**: importa i tuoi video e immagini (oppure indica una cartella del tuo PC).
2. **Ispettore**: scegli un file, sposta il cursore, imposta inizio e fine, poi aggiungi la clip alla timeline.
   «Ritaglia l'inquadratura» rimuove i bordi (in %) o tiene una zona in formato 9:16, 1:1, 4:5 o 16:9.
3. **Timeline**: modifica direttamente le celle (ordine, velocità da 0,5 a 4, volume da 0 a 2, inquadratura_x 0 = sinistra, 1 = destra).
4. **Impostazioni** a destra, poi **Anteprima rapida** (metà risoluzione, molto veloce) ed **Esporta il video**.

### Shorts in serie
Prepara un modello (scheda Montaggio → «Salva le impostazioni come modello di serie», oppure uno dei modelli forniti),
poi una tabella CSV in cui **una riga = un video**. Colonne: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage`
(i nomi delle colonne restano in francese). In `medias`, separa i file con `|`, indica un'intera cartella o un motivo come `images/*.jpg`.
Se la riga contiene immagini e una voce fuori campo, le immagini vengono distribuite automaticamente sulla durata della voce.

### Sottotitoli
- **script**: incolla il testo, viene diviso e sincronizzato automaticamente (sulla durata della voce fuori campo, se presente).
- **srt**: un file di sottotitoli esistente (ad esempio esportato dal tuo generatore di voce).
- **whisper**: trascrizione automatica parola per parola, dopo `pip install faster-whisper`.
- **traccia del video**: attiva i sottotitoli già presenti nel file video (MP4, MKV), nella lingua scelta;
  restano sincronizzati anche dopo taglio, cambio di velocità o rimozione dei silenzi.
Accanto al video viene sempre creato un file `.srt`: puoi caricarlo su YouTube.

### Livelli e foto animate
- **Immagine o video sovrapposto** (sezione 4): screenshot, sticker, logo o video sopra il montaggio
  (picture-in-picture). Scegli il media dalla libreria, quando appare, la posizione (centro in %), la larghezza e
  l'entrata animata: **dissolvenza**, **salita** o **zoom** (con un leggero rimbalzo). Le immagini opache e i video
  hanno gli angoli arrotondati; il video sovrapposto è muto e va in loop se è troppo corto.
- **Testo animato**: tutti i testi che vuoi, ognuno con i suoi tempi, posizione, dimensione, colore ed entrata.
  Le tabelle restano modificabili (animazione scritta per esteso, « fine » vuota = fino alla fine).
- **Movimento delle foto** (Impostazioni → Immagini fisse): zoom avanti o indietro, panoramica, oppure **Ken Burns**
  (zoom lento e spostamento, con un percorso diverso per ogni foto). La colonna « movimento » della timeline regola
  una sola foto.

### Voce fuori campo
Scheda **Voce fuori campo**: scrivi il testo (scene separate da `---`), scegli **Piper** (gratuito, offline) o
**ElevenLabs** (la tua chiave API, voci molto naturali e sottotitoli con tempi esatti), poi «Usa nella scheda Montaggio».
In serie, spunta «Crea la voce fuori campo dalla colonna texte». Una scena generata con la voce sbagliata si corregge
con «Sostituisci la voce di una clip esistente».

### Strumenti rapidi
- **Convertitore di tempo** (Ispettore): scrivi `90`, `1:30`, `1h 2m 3s` o `2,5 min`, poi «→ Inizio» / «→ Fine».
- **Rimuovi un logo**: scegli la zona (angolo rapido + cursori), controlla con «Anteprima», poi rimuovilo da tutto il video.
- **Logo MSV**: aggiungi il tuo logo [ ▶ ]; la posizione resta memorizzata nel video per poterlo togliere con precisione.

### Consigli sulle prestazioni
I rendering «anteprima» sono da 3 a 5 volte più veloci. Se hai una scheda NVIDIA, scegli l'encoder «nvidia (nvenc)».
Se l'encoder GPU non funziona, il programma torna automaticamente alla CPU.
""",
    "es": """
### Inicio rápido
1. **Biblioteca de medios**: importa tus vídeos e imágenes (o indica una carpeta de tu PC).
2. **Inspector**: elige un archivo, mueve el cursor, fija el inicio y el final, y añade el fragmento a la línea de tiempo.
   «Recortar el encuadre» quita bordes (en %) o conserva una zona en formato 9:16, 1:1, 4:5 o 16:9.
3. **Línea de tiempo**: edita las celdas directamente (orden, velocidad de 0,5 a 4, volumen de 0 a 2, encuadre_x 0 = izquierda, 1 = derecha).
4. **Ajustes** a la derecha, luego **Vista previa rápida** (media resolución, muy rápida) y **Exportar el vídeo**.

### Shorts en serie
Prepara una plantilla (pestaña Edición → «Guardar los ajustes como plantilla de serie», o una de las plantillas incluidas),
y luego una tabla CSV donde **una fila = un vídeo**. Columnas: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage`
(los nombres de las columnas se quedan en francés). En `medias`, separa los archivos con `|`, indica una carpeta entera o un patrón como `images/*.jpg`.
Si la fila contiene imágenes y una voz en off, las imágenes se reparten automáticamente durante la voz.

### Subtítulos
- **script**: pega el texto; se divide y se sincroniza automáticamente (con la duración de la voz en off, si la hay).
- **srt**: un archivo de subtítulos existente (por ejemplo, exportado de tu generador de voz).
- **whisper**: transcripción automática palabra por palabra, tras `pip install faster-whisper`.
- **pista del vídeo**: activa los subtítulos ya incluidos en el archivo de vídeo (MP4, MKV), en el idioma elegido;
  se mantienen sincronizados incluso tras cortar, cambiar la velocidad o quitar los silencios.
Siempre se crea un archivo `.srt` junto al vídeo: puedes subirlo a YouTube.

### Capas y fotos animadas
- **Imagen o vídeo superpuesto** (sección 4): captura de pantalla, sticker, logo o vídeo encima del montaje
  (picture-in-picture). Elige el medio en la biblioteca, cuándo aparece, la posición (centro en %), el ancho y la
  entrada animada: **fundido**, **subida** o **zoom** (con un ligero rebote). Las imágenes opacas y los vídeos tienen
  esquinas redondeadas; el vídeo superpuesto va sin sonido y en bucle si es demasiado corto.
- **Texto animado**: todos los textos que quieras, cada uno con sus tiempos, posición, tamaño, color y entrada.
  Las tablas siguen siendo editables (animación escrita completa, «fin» vacío = hasta el final).
- **Movimiento de las fotos** (Ajustes → Imágenes fijas): acercar o alejar, paneo, o **Ken Burns** (zoom lento y
  desplazamiento, con un recorrido distinto para cada foto). La columna «movimiento» de la línea de tiempo ajusta
  una sola foto.

### Voz en off
Pestaña **Voz en off**: escribe el texto (escenas separadas por `---`), elige **Piper** (gratis, sin conexión) o
**ElevenLabs** (tu clave API, voces muy naturales y subtítulos con tiempos exactos), y luego «Usar en la pestaña Edición».
En serie, marca «Crear la voz en off a partir de la columna texte». Una escena generada con la voz equivocada se corrige
con «Reemplazar la voz de un clip existente».

### Herramientas rápidas
- **Conversor de tiempo** (Inspector): escribe `90`, `1:30`, `1h 2m 3s` o `2,5 min`, y luego «→ Inicio» / «→ Fin».
- **Quitar un logo**: elige la zona (esquina rápida + controles), compruébalo con «Vista previa» y quítalo de todo el vídeo.
- **Logo MSV**: añade tu logo [ ▶ ]; su posición se guarda en el vídeo para poder quitarlo con precisión.

### Consejos de rendimiento
Los renderizados de «vista previa» son de 3 a 5 veces más rápidos. Si tienes una tarjeta NVIDIA, elige el codificador «nvidia (nvenc)».
Si el codificador GPU falla, el programa vuelve automáticamente a la CPU.
""",
}

_TABLES: dict[str, dict[str, str]] = {code: {} for code in LANGS if code != DEFAULT_LANG}
for _fr, *_others in _STRINGS:
    for _code, _txt in zip(("en", "it", "es"), _others):
        _TABLES[_code][_fr] = _txt


def _(text: str, **kw) -> str:
    """Traduit `text` (français) dans la langue active, puis remplit les champs {nom}."""
    lang = LANG.get()
    out = _TABLES.get(lang, {}).get(text, text)
    return out.format(**kw) if kw else out


def translations(text: str) -> list[str]:
    """Toutes les traductions d'un texte français (pour relire une valeur saisie dans n'importe quelle langue)."""
    return [t[text] for t in _TABLES.values() if text in t]


def opts(values) -> list[tuple[str, str]]:
    """Choix traduits pour Radio/Dropdown : on affiche la traduction, la valeur reste en français."""
    return [(_(v), v) for v in values]


def help_text() -> str:
    return HELP.get(LANG.get(), HELP[DEFAULT_LANG])


def pick_lang(accept_language: str | None) -> str:
    """Choisit la langue d'après l'en-tête Accept-Language du navigateur."""
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "en"
