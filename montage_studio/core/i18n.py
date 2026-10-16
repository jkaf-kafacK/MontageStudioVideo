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
    ("Piper n'est pas installé : pip install sherpa-onnx", "Piper is not installed: pip install sherpa-onnx",
     "Piper non è installato: pip install sherpa-onnx", "Piper no está instalado: pip install sherpa-onnx"),
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
]

HELP = {
    "fr": """
### Démarrage rapide
1. **Médiathèque** : importe tes vidéos et images (ou indique un dossier de ton PC).
2. **Inspecteur** : choisis un média, déplace le curseur, fixe le début et la fin, puis ajoute l'extrait à la timeline.
3. **Timeline** : modifie directement les cellules (ordre, vitesse 0,5 à 4, volume 0 à 2, cadrage_x 0 = gauche, 1 = droite).
4. **Réglages** à droite, puis **Aperçu rapide** (demi-résolution, très rapide) et **Exporter la vidéo**.

### Shorts en série
Prépare un modèle (onglet Montage → « Enregistrer comme modèle », ou un des modèles fournis), puis un tableau CSV
où **une ligne = une vidéo**. Colonnes : `id; medias; titre; texte; srt; voix_off; musique; debut; fin`.
Dans `medias`, sépare les fichiers par `|`, indique un dossier entier, ou un motif comme `images/*.jpg`.
Si la ligne contient des images et une voix off, les images sont réparties automatiquement sur la durée de la voix.

### Sous-titres
- **script** : colle le texte, il est découpé et minuté automatiquement (sur la durée de la voix off s'il y en a une).
- **srt** : fichier de sous-titres existant (par exemple exporté de ton générateur de voix).
- **whisper** : transcription automatique au mot près, après `pip install faster-whisper`.
Un fichier `.srt` est toujours créé à côté de la vidéo : tu peux l'envoyer sur YouTube.

### Voix off
Onglet **Voix off** : écris le texte (scènes séparées par `---`), choisis **Piper** (gratuit, hors ligne) ou
**ElevenLabs** (ta clé API, voix très naturelles et minutage exact des sous-titres), puis « Utiliser dans l'onglet Montage ».
En série, coche « Créer la voix off à partir de la colonne texte ». Une scène générée avec la mauvaise voix se corrige
avec « Remplacer la voix d'un clip existant ».

### Conseils de performance
Les rendus « aperçu » sont 3 à 5 fois plus rapides. Si tu as une carte NVIDIA, choisis l'encodeur « nvidia (nvenc) ».
En cas d'échec de l'encodeur GPU, le logiciel repasse automatiquement sur le CPU.
""",
    "en": """
### Quick start
1. **Media library**: import your videos and images (or enter a folder on your PC).
2. **Inspector**: choose a file, move the cursor, set the start and end, then add the clip to the timeline.
3. **Timeline**: edit the cells directly (order, speed 0.5 to 4, volume 0 to 2, crop_x 0 = left, 1 = right).
4. **Settings** on the right, then **Quick preview** (half resolution, very fast) and **Export video**.

### Batch Shorts
Prepare a template (Editor tab → “Save settings as batch template”, or one of the bundled templates), then a CSV table
where **one row = one video**. Columns: `id; medias; titre; texte; srt; voix_off; musique; debut; fin`
(column names stay in French). In `medias`, separate files with `|`, give a whole folder, or a pattern like `images/*.jpg`.
If a row contains images and a voice-over, the images are spread automatically over the length of the voice.

### Subtitles
- **script**: paste the text; it is split and timed automatically (over the voice-over length if there is one).
- **srt**: an existing subtitle file (for example exported from your voice generator).
- **whisper**: automatic word-level transcription, after `pip install faster-whisper`.
A `.srt` file is always created next to the video: you can upload it to YouTube.

### Voice-over
**Voice-over** tab: write the text (scenes separated by `---`), choose **Piper** (free, offline) or
**ElevenLabs** (your API key, very natural voices and exact subtitle timing), then “Use in the Editor tab”.
In batch mode, tick “Create the voice-over from the texte column”. A scene generated with the wrong voice can be fixed
with “Replace the voice of an existing clip”.

### Performance tips
“Preview” renders are 3 to 5 times faster. If you have an NVIDIA card, choose the “nvidia (nvenc)” encoder.
If the GPU encoder fails, the software automatically falls back to the CPU.
""",
    "it": """
### Avvio rapido
1. **Libreria media**: importa i tuoi video e immagini (oppure indica una cartella del tuo PC).
2. **Ispettore**: scegli un file, sposta il cursore, imposta inizio e fine, poi aggiungi la clip alla timeline.
3. **Timeline**: modifica direttamente le celle (ordine, velocità da 0,5 a 4, volume da 0 a 2, inquadratura_x 0 = sinistra, 1 = destra).
4. **Impostazioni** a destra, poi **Anteprima rapida** (metà risoluzione, molto veloce) ed **Esporta il video**.

### Shorts in serie
Prepara un modello (scheda Montaggio → «Salva le impostazioni come modello di serie», oppure uno dei modelli forniti),
poi una tabella CSV in cui **una riga = un video**. Colonne: `id; medias; titre; texte; srt; voix_off; musique; debut; fin`
(i nomi delle colonne restano in francese). In `medias`, separa i file con `|`, indica un'intera cartella o un motivo come `images/*.jpg`.
Se la riga contiene immagini e una voce fuori campo, le immagini vengono distribuite automaticamente sulla durata della voce.

### Sottotitoli
- **script**: incolla il testo, viene diviso e sincronizzato automaticamente (sulla durata della voce fuori campo, se presente).
- **srt**: un file di sottotitoli esistente (ad esempio esportato dal tuo generatore di voce).
- **whisper**: trascrizione automatica parola per parola, dopo `pip install faster-whisper`.
Accanto al video viene sempre creato un file `.srt`: puoi caricarlo su YouTube.

### Voce fuori campo
Scheda **Voce fuori campo**: scrivi il testo (scene separate da `---`), scegli **Piper** (gratuito, offline) o
**ElevenLabs** (la tua chiave API, voci molto naturali e sottotitoli con tempi esatti), poi «Usa nella scheda Montaggio».
In serie, spunta «Crea la voce fuori campo dalla colonna texte». Una scena generata con la voce sbagliata si corregge
con «Sostituisci la voce di una clip esistente».

### Consigli sulle prestazioni
I rendering «anteprima» sono da 3 a 5 volte più veloci. Se hai una scheda NVIDIA, scegli l'encoder «nvidia (nvenc)».
Se l'encoder GPU non funziona, il programma torna automaticamente alla CPU.
""",
    "es": """
### Inicio rápido
1. **Biblioteca de medios**: importa tus vídeos e imágenes (o indica una carpeta de tu PC).
2. **Inspector**: elige un archivo, mueve el cursor, fija el inicio y el final, y añade el fragmento a la línea de tiempo.
3. **Línea de tiempo**: edita las celdas directamente (orden, velocidad de 0,5 a 4, volumen de 0 a 2, encuadre_x 0 = izquierda, 1 = derecha).
4. **Ajustes** a la derecha, luego **Vista previa rápida** (media resolución, muy rápida) y **Exportar el vídeo**.

### Shorts en serie
Prepara una plantilla (pestaña Edición → «Guardar los ajustes como plantilla de serie», o una de las plantillas incluidas),
y luego una tabla CSV donde **una fila = un vídeo**. Columnas: `id; medias; titre; texte; srt; voix_off; musique; debut; fin`
(los nombres de las columnas se quedan en francés). En `medias`, separa los archivos con `|`, indica una carpeta entera o un patrón como `images/*.jpg`.
Si la fila contiene imágenes y una voz en off, las imágenes se reparten automáticamente durante la voz.

### Subtítulos
- **script**: pega el texto; se divide y se sincroniza automáticamente (con la duración de la voz en off, si la hay).
- **srt**: un archivo de subtítulos existente (por ejemplo, exportado de tu generador de voz).
- **whisper**: transcripción automática palabra por palabra, tras `pip install faster-whisper`.
Siempre se crea un archivo `.srt` junto al vídeo: puedes subirlo a YouTube.

### Voz en off
Pestaña **Voz en off**: escribe el texto (escenas separadas por `---`), elige **Piper** (gratis, sin conexión) o
**ElevenLabs** (tu clave API, voces muy naturales y subtítulos con tiempos exactos), y luego «Usar en la pestaña Edición».
En serie, marca «Crear la voz en off a partir de la columna texte». Una escena generada con la voz equivocada se corrige
con «Reemplazar la voz de un clip existente».

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
