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
    ("Sombre", "Dark", "Scuro", "Oscuro"),
    ("Passer au thème sombre", "Switch to dark theme", "Passa al tema scuro", "Cambiar al tema oscuro"),
    ("Passer au thème clair", "Switch to light theme", "Passa al tema chiaro", "Cambiar al tema claro"),
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
    # ---- onglet Classement (app.py)
    ("Classement", "Ranking", "Classifica", "Clasificación"),
    ("Un Short « Top N » : un titre, une liste numérotée qui se remplit clip après clip, le clip en cours dans un cadre "
     "avec son rang. N'utilise que des clips dont tu as les droits ou l'autorisation, et crédite la source.",
     "A “Top N” Short: a title, a numbered list that fills up clip after clip, and the current clip in a frame with "
     "its rank. Only use clips you have the rights or permission to use, and credit the source.",
     "Uno Short «Top N»: un titolo, una lista numerata che si riempie clip dopo clip, la clip in corso in una cornice "
     "con la sua posizione. Usa solo clip di cui hai i diritti o l'autorizzazione, e cita la fonte.",
     "Un Short «Top N»: un título, una lista numerada que se llena clip tras clip y el clip actual en un marco con su "
     "puesto. Usa solo clips de los que tengas los derechos o la autorización, y cita la fuente."),
    ("Clips", "Clips", "Clip", "Clips"),
    ("Importer des clips (vidéos ou images)", "Import clips (videos or images)", "Importa clip (video o immagini)",
     "Importar clips (vídeos o imágenes)"),
    ("rang", "rank", "posizione", "puesto"),
    ("titre", "title", "titolo", "título"),
    ("crédit", "credit", "crediti", "crédito"),
    ("Le n° 1 est la première ligne. Début et fin (s) sont facultatifs ; clique sur une ligne pour la sélectionner.",
     "No. 1 is the first row. Start and end (s) are optional; click a row to select it.",
     "Il n. 1 è la prima riga. Inizio e fine (s) sono facoltativi; clicca una riga per selezionarla.",
     "El n.º 1 es la primera fila. Inicio y fin (s) son opcionales; haz clic en una fila para seleccionarla."),
    ("Rang sélectionné", "Selected rank", "Posizione selezionata", "Puesto seleccionado"),
    ("Monter", "Move up", "Sposta su", "Subir"),
    ("Descendre", "Move down", "Sposta giù", "Bajar"),
    ("Supprimer", "Delete", "Elimina", "Eliminar"),
    ("Mélanger", "Shuffle", "Mescola", "Mezclar"),
    ("Importe de 2 à 10 clips, puis donne un titre à chaque rang.", "Import 2 to 10 clips, then give each rank a title.",
     "Importa da 2 a 10 clip, poi dai un titolo a ogni posizione.",
     "Importa de 2 a 10 clips y luego da un título a cada puesto."),
    ("Rang affiché", "Rank shown", "Posizione mostrata", "Puesto mostrado"),
    ("Titre et style", "Title and style", "Titolo e stile", "Título y estilo"),
    ("Le top 5 des plus beaux buts", "Top 5 most beautiful goals", "I 5 gol più belli", "Los 5 goles más bonitos"),
    ("Entrée : passer à la ligne (titre sur deux lignes).", "Enter: new line (two-line title).",
     "Invio: va a capo (titolo su due righe).", "Intro: salto de línea (título en dos líneas)."),
    ("Mots à surligner", "Words to highlight", "Parole da evidenziare", "Palabras a resaltar"),
    ("Préréglage", "Preset", "Preimpostazione", "Preajuste"),
    ("Néon sombre", "Dark neon", "Neon scuro", "Neón oscuro"),
    ("Clair", "Light", "Chiaro", "Claro"),
    ("Brut rouge", "Raw red", "Rosso crudo", "Rojo crudo"),
    ("Podium", "Podium", "Podio", "Podio"),
    ("Surlignage 2", "Highlight 2", "Evidenziazione 2", "Resaltado 2"),
    ("Un mot surligné sur deux (même couleur : désactivé).", "Every other highlighted word (same colour: off).",
     "Una parola evidenziata su due (stesso colore: disattivato).",
     "Una de cada dos palabras resaltadas (mismo color: desactivado)."),
    ("Position du badge", "Badge position", "Posizione del badge", "Posición de la insignia"),
    ("Panneau derrière la liste", "Panel behind the list", "Pannello dietro la lista", "Panel detrás de la lista"),
    ("Quand la liste est posée sur la vidéo.", "When the list sits on top of the video.",
     "Quando la lista è sopra il video.", "Cuando la lista está sobre el vídeo."),
    ("Numéros colorés (or, argent, bronze)", "Coloured numbers (gold, silver, bronze)",
     "Numeri colorati (oro, argento, bronzo)", "Números de colores (oro, plata, bronce)"),
    ("Taille des libellés (× numéros)", "Label size (× numbers)", "Dimensione delle etichette (× numeri)",
     "Tamaño de las etiquetas (× números)"),
    ("Libellés en majuscules", "Labels in capitals", "Etichette in maiuscolo", "Etiquetas en mayúsculas"),
    ("Libellés en italique", "Labels in italics", "Etichette in corsivo", "Etiquetas en cursiva"),
    ("Mise en page", "Layout", "Impaginazione", "Diseño"),
    ("Ordre de passage", "Playing order", "Ordine di passaggio", "Orden de aparición"),
    ("décroissant : compte à rebours, le n° 1 passe en dernier", "descending: countdown, No. 1 comes last",
     "decrescente: conto alla rovescia, il n. 1 arriva per ultimo",
     "descendente: cuenta atrás, el n.º 1 sale el último"),
    ("Durée max par clip (s)", "Max length per clip (s)", "Durata massima per clip (s)", "Duración máx. por clip (s)"),
    ("Police, tailles et couleurs", "Font, sizes and colours", "Carattere, dimensioni e colori",
     "Fuente, tamaños y colores"),
    ("Taille du titre", "Title size", "Dimensione del titolo", "Tamaño del título"),
    ("Taille de la liste", "List size", "Dimensione della lista", "Tamaño de la lista"),
    ("Rangs à venir", "Upcoming ranks", "Posizioni in arrivo", "Puestos por venir"),
    ("Badge", "Badge", "Badge", "Insignia"),
    ("Épaisseur du contour", "Outline thickness", "Spessore del contorno", "Grosor del contorno"),
    ("Musique (facultatif)", "Music (optional)", "Musica (facoltativa)", "Música (opcional)"),
    ("Volume de la musique", "Music volume", "Volume della musica", "Volumen de la música"),
    ("Aperçu rapide (vidéo)", "Quick preview (video)", "Anteprima rapida (video)", "Vista previa rápida (vídeo)"),
    ("Exporter", "Export", "Esporta", "Exportar"),
    ("Enregistrer le classement", "Save ranking", "Salva la classifica", "Guardar la clasificación"),
    ("Charger un classement", "Load a ranking", "Carica una classifica", "Cargar una clasificación"),
    ("Classement enregistré (.json)", "Saved ranking (.json)", "Classifica salvata (.json)",
     "Clasificación guardada (.json)"),
    ("Un classement contient au plus {max} clips : les clips en trop sont ignorés.",
     "A ranking contains at most {max} clips: the extra clips are ignored.",
     "Una classifica contiene al massimo {max} clip: quelle in più vengono ignorate.",
     "Una clasificación contiene como máximo {max} clips: los que sobran se ignoran."),
    ("**{n} clips · {d:.1f} s au total**", "**{n} clips · {d:.1f} s in total**", "**{n} clip · {d:.1f} s in totale**",
     "**{n} clips · {d:.1f} s en total**"),
    ("Rendu du classement", "Rendering the ranking", "Rendering della classifica", "Renderizando la clasificación"),
    ("Classement créé : {name}", "Ranking created: {name}", "Classifica creata: {name}",
     "Clasificación creada: {name}"),
    ("Classement enregistré : {name}", "Ranking saved: {name}", "Classifica salvata: {name}",
     "Clasificación guardada: {name}"),
    ("Choisis un fichier de classement .json.", "Choose a ranking .json file.", "Scegli un file di classifica .json.",
     "Elige un archivo de clasificación .json."),
    # ---- mode Classement (core/ranking.py)
    ("décroissant", "descending", "decrescente", "descendente"),
    ("croissant", "ascending", "crescente", "ascendente"),
    ("liste à gauche", "list on the left", "lista a sinistra", "lista a la izquierda"),
    ("liste en haut", "list at the top", "lista in alto", "lista arriba"),
    ("plein écran", "full screen", "schermo intero", "pantalla completa"),
    ("bandeau", "banner", "banda", "banda superior"),
    ("coin du clip", "clip corner", "angolo della clip", "esquina del clip"),
    ("à côté du titre", "next to the title", "accanto al titolo", "junto al título"),
    ("Position du badge inconnue : « {v} » (choix : {choix}).", "Unknown badge position: “{v}” (choices: {choix}).",
     "Posizione del badge sconosciuta: «{v}» (scelte: {choix}).",
     "Posición de la insignia desconocida: «{v}» (opciones: {choix})."),
    ("Ordre inconnu : « {v} » (choix : {choix}).", "Unknown order: “{v}” (choices: {choix}).",
     "Ordine sconosciuto: «{v}» (scelte: {choix}).", "Orden desconocido: «{v}» (opciones: {choix})."),
    ("Mise en page inconnue : « {v} » (choix : {choix}).", "Unknown layout: “{v}” (choices: {choix}).",
     "Impaginazione sconosciuta: «{v}» (scelte: {choix}).", "Diseño desconocido: «{v}» (opciones: {choix})."),
    ("Un classement contient de {min} à {max} clips (ici : {n}).",
     "A ranking contains from {min} to {max} clips (here: {n}).",
     "Una classifica contiene da {min} a {max} clip (qui: {n}).",
     "Una clasificación contiene de {min} a {max} clips (aquí: {n})."),
    ("Rang {n} : fichier introuvable ({path}).", "Rank {n}: file not found ({path}).",
     "Posizione {n}: file non trovato ({path}).", "Puesto {n}: archivo no encontrado ({path})."),
    ("Rang {n} : « {name} » n'est ni une vidéo ni une image.", "Rank {n}: “{name}” is neither a video nor an image.",
     "Posizione {n}: «{name}» non è né un video né un'immagine.",
     "Puesto {n}: «{name}» no es ni un vídeo ni una imagen."),
    ("Rang {n} : extrait trop court ({d:.2f} s). Vérifie le début et la fin.",
     "Rank {n}: excerpt too short ({d:.2f} s). Check the start and end.",
     "Posizione {n}: estratto troppo corto ({d:.2f} s). Controlla inizio e fine.",
     "Puesto {n}: fragmento demasiado corto ({d:.2f} s). Revisa el inicio y el final."),
    ("Musique introuvable : {path}", "Music not found: {path}", "Musica non trovata: {path}",
     "Música no encontrada: {path}"),
    ("Préréglage inconnu : « {nom} » (choix : {choix}).", "Unknown preset: “{nom}” (choices: {choix}).",
     "Preimpostazione sconosciuta: «{nom}» (scelte: {choix}).", "Preajuste desconocido: «{nom}» (opciones: {choix})."),
    ("⚠ Durée totale : {d:.0f} s. Au-delà de 60 s, la vidéo risque de ne plus être considérée comme un Short.",
     "⚠ Total length: {d:.0f} s. Beyond 60 s, the video may no longer count as a Short.",
     "⚠ Durata totale: {d:.0f} s. Oltre 60 s, il video potrebbe non essere più considerato uno Short.",
     "⚠ Duración total: {d:.0f} s. Más allá de 60 s, el vídeo podría dejar de considerarse un Short."),
    ("Cadre invalide : « {v} » (attendu : x/y/largeur/hauteur en %, ex. 40/20/60/60)",
     "Invalid frame: “{v}” (expected: x/y/width/height in %, e.g. 40/20/60/60)",
     "Cornice non valida: «{v}» (atteso: x/y/larghezza/altezza in %, es. 40/20/60/60)",
     "Marco no válido: «{v}» (se espera: x/y/ancho/alto en %, p. ej. 40/20/60/60)"),
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
    # ---- scènes animées (core/scenes.py)
    ("Scènes animées", "Animated scenes", "Scene animate", "Escenas animadas"),
    ("Des scènes animées prêtes à l'emploi : remplis les textes, regarde l'aperçu, crée la vidéo puis ajoute-la à "
     "la timeline. Mets un mot entre *étoiles* pour le colorer.",
     "Ready-made animated scenes: fill in the texts, check the preview, create the video, then add it to the "
     "timeline. Put a word between *asterisks* to color it.",
     "Scene animate pronte all'uso: compila i testi, guarda l'anteprima, crea il video e poi aggiungilo alla "
     "timeline. Metti una parola tra *asterischi* per colorarla.",
     "Escenas animadas listas para usar: rellena los textos, mira la vista previa, crea el vídeo y añádelo a la "
     "línea de tiempo. Pon una palabra entre *asteriscos* para colorearla."),
    ("Scène", "Scene", "Scena", "Escena"),
    ("Textes et média", "Texts and media", "Testi e media", "Textos y medio"),
    ("Aperçu et création", "Preview and creation", "Anteprima e creazione", "Vista previa y creación"),
    ("Type de scène", "Scene type", "Tipo di scena", "Tipo de escena"),
    ("carte titre", "title card", "scheda titolo", "tarjeta de título"),
    ("téléphone", "phone", "telefono", "teléfono"),
    ("écran final", "end screen", "schermata finale", "pantalla final"),
    ("Logo ou image qui arrive avec un rebond, étiquette, grand titre et trait de couleur. Idéal pour ouvrir une "
     "vidéo.",
     "Logo or image that bounces in, label, big title and a color line. Ideal to open a video.",
     "Logo o immagine che entra con un rimbalzo, etichetta, titolo grande e una linea colorata. Ideale per aprire "
     "un video.",
     "Logo o imagen que entra con un rebote, etiqueta, título grande y una línea de color. Ideal para abrir un vídeo."),
    ("Ta vidéo ou ton image dans un téléphone, avec un titre. Idéal pour montrer un extrait ou une appli.",
     "Your video or image inside a phone, with a title. Ideal to show a clip or an app.",
     "Il tuo video o la tua immagine dentro un telefono, con un titolo. Ideale per mostrare un estratto o un'app.",
     "Tu vídeo o tu imagen dentro de un teléfono, con un título. Ideal para mostrar un fragmento o una app."),
    ("Appel à l'action : titre, bouton qui se fait cliquer (« S'abonner » → « Abonné ») et badge « Lien en bio ».",
     "Call to action: title, a button that gets clicked (“Subscribe” → “Subscribed”) and a “Link in bio” badge.",
     "Invito all'azione: titolo, pulsante che viene cliccato (« Iscriviti » → « Iscritto ») e badge « Link in bio ».",
     "Llamada a la acción: título, botón que se pulsa («Suscribirse» → «Suscrito») y distintivo «Link en la bio»."),
    ("Durée (s)", "Duration (s)", "Durata (s)", "Duración (s)"),
    ("Étiquette (petit texte au-dessus du titre)", "Label (small text above the title)",
     "Etichetta (piccolo testo sopra il titolo)", "Etiqueta (texto pequeño encima del título)"),
    ("Épisode 1", "Episode 1", "Episodio 1", "Episodio 1"),
    ("Le *titre* de ta vidéo", "Your video *title*", "Il *titolo* del tuo video", "El *título* de tu vídeo"),
    ("Sous-titre", "Subtitle", "Sottotitolo", "Subtítulo"),
    ("Une phrase qui donne envie de regarder", "A line that makes people want to watch",
     "Una frase che fa venire voglia di guardare", "Una frase que dé ganas de mirar"),
    ("Logo, image ou vidéo", "Logo, image or video", "Logo, immagine o video", "Logo, imagen o vídeo"),
    ("Carte titre et écran final : ton logo ou une image. Téléphone : la vidéo ou l'image affichée dans l'écran. "
     "Avant / après : l'image « avant ».",
     "Title card and end screen: your logo or an image. Phone: the video or image shown on the screen. "
     "Before / after: the “before” image.",
     "Scheda titolo e schermata finale: il tuo logo o un'immagine. Telefono: il video o l'immagine mostrati "
     "sullo schermo. Prima / dopo: l'immagine « prima ».",
     "Tarjeta de título y pantalla final: tu logo o una imagen. Teléfono: el vídeo o la imagen que se ve en la "
     "pantalla. Antes / después: la imagen «antes»."),
    ("liste", "list", "elenco", "lista"),
    ("chiffres clés", "key figures", "numeri chiave", "cifras clave"),
    ("avant / après", "before / after", "prima / dopo", "antes / después"),
    ("question choc", "hook question", "domanda shock", "pregunta impactante"),
    ("Titre puis une liste de points qui apparaissent un à un avec une coche.",
     "A title, then a list of points that appear one by one with a check mark.",
     "Un titolo, poi un elenco di punti che appaiono uno alla volta con una spunta.",
     "Un título y luego una lista de puntos que aparecen uno a uno con una marca."),
    ("Tuiles « grand chiffre + légende » ; les nombres défilent jusqu'à leur valeur.",
     "“Big number + caption” tiles; the numbers count up to their value.",
     "Riquadri « numero grande + didascalia »; i numeri scorrono fino al loro valore.",
     "Recuadros «cifra grande + leyenda»; los números van contando hasta su valor."),
    ("Deux images ou vidéos : la seconde remplace la première par un balayage.",
     "Two images or videos: the second one replaces the first with a wipe.",
     "Due immagini o video: il secondo sostituisce il primo con una tendina.",
     "Dos imágenes o vídeos: la segunda sustituye a la primera con un barrido."),
    ("Une grande question qui tombe mot par mot, puis une phrase (« Dis-le en commentaire »).",
     "A big question that drops in word by word, then a line (“Tell me in the comments”).",
     "Una grande domanda che cade parola per parola, poi una frase (« Dimmelo nei commenti »).",
     "Una gran pregunta que cae palabra por palabra y luego una frase («Dímelo en los comentarios»)."),
    ("Premier point\nDeuxième point\nTroisième point", "First point\nSecond point\nThird point",
     "Primo punto\nSecondo punto\nTerzo punto", "Primer punto\nSegundo punto\nTercer punto"),
    ("120 000 | vues\n98 % | de satisfaction\n3 | minutes", "120,000 | views\n98% | satisfaction\n3 | minutes",
     "120.000 | visualizzazioni\n98% | di soddisfazione\n3 | minuti", "120.000 | visitas\n98 % | de satisfacción\n3 | minutos"),
    ("Avant\nAprès", "Before\nAfter", "Prima\nDopo", "Antes\nDespués"),
    ("un point par ligne", "one point per line", "un punto per riga", "un punto por línea"),
    ("« chiffre | légende », un par ligne : les nombres défilent jusqu'à leur valeur",
     "“number | caption”, one per line: the numbers count up to their value",
     "« numero | didascalia », uno per riga: i numeri scorrono fino al loro valore",
     "«cifra | leyenda», una por línea: los números van contando hasta su valor"),
    ("ligne 1 : étiquette de l'image « avant », ligne 2 : de l'image « après »",
     "line 1: label of the “before” image, line 2: of the “after” image",
     "riga 1: etichetta dell'immagine « prima », riga 2: dell'immagine « dopo »",
     "línea 1: etiqueta de la imagen «antes», línea 2: de la imagen «después»"),
    ("Lignes", "Lines", "Righe", "Líneas"),
    ("Image ou vidéo « après »", "“After” image or video", "Immagine o video « dopo »", "Imagen o vídeo «después»"),
    ("Intro et fin automatiques", "Automatic intro and ending", "Intro e finale automatici",
     "Intro y final automáticos"),
    ("Ou bien ajoute cette scène à chaque rendu du projet (et de la série), au format du projet :",
     "Or add this scene to every render of the project (and of the batch), in the project format:",
     "Oppure aggiungi questa scena a ogni render del progetto (e della serie), nel formato del progetto:",
     "O añade esta escena a cada renderizado del proyecto (y de la serie), en el formato del proyecto:"),
    ("Utiliser comme intro du projet", "Use as project intro", "Usa come intro del progetto",
     "Usar como intro del proyecto"),
    ("Utiliser comme fin du projet", "Use as project ending", "Usa come finale del progetto",
     "Usar como final del proyecto"),
    ("Intro du projet : {kind}", "Project intro: {kind}", "Intro del progetto: {kind}", "Intro del proyecto: {kind}"),
    ("Fin du projet : {kind}", "Project ending: {kind}", "Finale del progetto: {kind}", "Final del proyecto: {kind}"),
    ("Intro", "Intro", "Intro", "Intro"),
    ("Intro et fin (scènes animées)", "Intro and ending (animated scenes)", "Intro e finale (scene animate)",
     "Intro y final (escenas animadas)"),
    ("Choisis-les dans l'onglet « Scènes animées » (boutons « Utiliser comme intro / fin du projet ») : elles sont "
     "ajoutées à chaque rendu, au format du projet, et passent aussi dans les modèles de série.",
     "Pick them in the “Animated scenes” tab (“Use as project intro / ending” buttons): they are added to every "
     "render, in the project format, and are also saved in batch templates.",
     "Sceglile nella scheda « Scene animate » (pulsanti « Usa come intro / finale del progetto »): vengono "
     "aggiunte a ogni render, nel formato del progetto, e finiscono anche nei modelli di serie.",
     "Elígelas en la pestaña «Escenas animadas» (botones «Usar como intro / final del proyecto»): se añaden a "
     "cada renderizado, en el formato del proyecto, y también se guardan en las plantillas de serie."),
    ("Retirer l'intro", "Remove intro", "Togli l'intro", "Quitar la intro"),
    ("Retirer la fin", "Remove ending", "Togli il finale", "Quitar el final"),
    ("Scène animée : {kind}", "Animated scene: {kind}", "Scena animata: {kind}", "Escena animada: {kind}"),
    ("🎬 {what} : {kind} ({dur:g} s)", "🎬 {what}: {kind} ({dur:g} s)", "🎬 {what}: {kind} ({dur:g} s)",
     "🎬 {what}: {kind} ({dur:g} s)"),
    # ---- ma voix : clonage local (core/voice.py, voice_clone_worker.py)
    ("Ma voix (clonage local)", "My voice (local cloning)", "La mia voce (clonazione locale)",
     "Mi voz (clonación local)"),
    ("**Ma voix** : ta propre voix, recréée sur ton PC à partir d'un enregistrement de 10 à 60 s. Rien n'est envoyé "
     "sur Internet. Ne clone que ta voix, ou celle d'une personne qui t'a donné son accord.",
     "**My voice**: your own voice, recreated on your PC from a 10–60 s recording. Nothing is sent to the Internet. "
     "Only clone your own voice, or that of someone who gave you their consent.",
     "**La mia voce**: la tua voce, ricreata sul tuo PC da una registrazione di 10–60 s. Niente viene inviato su "
     "Internet. Clona solo la tua voce, o quella di una persona che ti ha dato il suo consenso.",
     "**Mi voz**: tu propia voz, recreada en tu PC a partir de una grabación de 10 a 60 s. No se envía nada a "
     "Internet. Clona solo tu voz, o la de una persona que te haya dado su consentimiento."),
    ("Mes voix", "My voices", "Le mie voci", "Mis voces"),
    ("Ma voix", "My voice", "La mia voce", "Mi voz"),
    ("Expressivité", "Expressiveness", "Espressività", "Expresividad"),
    ("Sous-titres .srt et texte .txt", "Subtitles .srt and text .txt", "Sottotitoli .srt e testo .txt",
     "Subtítulos .srt y texto .txt"),
    # ---- voix plus naturelles (pauses, prononciation, son studio, prises vérifiées)
    ("Style de lecture", "Reading style", "Stile di lettura", "Estilo de lectura"),
    ("Narration calme", "Calm narration", "Narrazione calma", "Narración tranquila"),
    ("Conversation", "Conversation", "Conversazione", "Conversación"),
    ("Promo énergique", "Energetic promo", "Promo energica", "Promo enérgica"),
    ("Personnalisé", "Custom", "Personalizzato", "Personalizado"),
    ("Prises par phrase", "Takes per sentence", "Riprese per frase", "Tomas por frase"),
    ("2 ou 3 : chaque phrase est vérifiée (transcription) et refaite si un mot manque ; le premier usage télécharge "
     "le vérificateur (≈ 1 Go)",
     "2 or 3: each sentence is checked (transcription) and redone if a word is missing; first use downloads the "
     "checker (≈ 1 GB)",
     "2 o 3: ogni frase viene verificata (trascrizione) e rifatta se manca una parola; al primo uso scarica il "
     "verificatore (≈ 1 GB)",
     "2 o 3: cada frase se verifica (transcripción) y se rehace si falta una palabra; el primer uso descarga el "
     "verificador (≈ 1 GB)"),
    ("Son studio", "Studio sound", "Suono da studio", "Sonido de estudio"),
    ("égaliseur, « s » adoucis, compression et très légère ambiance de pièce : la voix sonne moins « synthèse »",
     "equalizer, softened \"s\" sounds, compression and a very light room tone: the voice sounds less synthetic",
     "equalizzatore, « s » addolcite, compressione e leggerissimo effetto stanza: la voce suona meno sintetica",
     "ecualizador, « s » suavizadas, compresión y un ligerísimo ambiente de sala: la voz suena menos sintética"),
    ("Pauses et prononciation", "Pauses and pronunciation", "Pause e pronuncia", "Pausas y pronunciación"),
    ("**Pauses** : chaque phrase est lue séparément, avec une pause plus longue après un point, un point "
     "d'exclamation, des points de suspension ou une ligne vide. Pour une pause précise, écris `[pause 1s]` ou "
     "`[pause 500ms]`.\n\n**Prononciation** (Piper et Ma voix) : nombres, heures, prix, pourcentages et sigles sont "
     "lus en toutes lettres. Si un mot est mal prononcé, ajoute une ligne `mot = prononciation` ci-dessous.",
     "**Pauses**: each sentence is read separately, with a longer pause after a full stop, an exclamation mark, an "
     "ellipsis or a blank line. For an exact pause, write `[pause 1s]` or `[pause 500ms]`.\n\n**Pronunciation** "
     "(Piper and My voice): numbers, times, prices, percentages and acronyms are read out in full. If a word is "
     "mispronounced, add a line `word = pronunciation` below.",
     "**Pause**: ogni frase viene letta separatamente, con una pausa più lunga dopo un punto, un punto esclamativo, "
     "dei puntini di sospensione o una riga vuota. Per una pausa precisa, scrivi `[pause 1s]` o `[pause 500ms]`.\n\n"
     "**Pronuncia** (Piper e La mia voce): numeri, orari, prezzi, percentuali e sigle vengono letti per esteso. Se "
     "una parola è pronunciata male, aggiungi una riga `parola = pronuncia` qui sotto.",
     "**Pausas**: cada frase se lee por separado, con una pausa más larga tras un punto, un signo de exclamación, "
     "puntos suspensivos o una línea vacía. Para una pausa exacta, escribe `[pause 1s]` o `[pause 500ms]`.\n\n"
     "**Pronunciación** (Piper y Mi voz): números, horas, precios, porcentajes y siglas se leen en letras. Si una "
     "palabra se pronuncia mal, añade una línea `palabra = pronunciación` abajo."),
    ("Dictionnaire de prononciation", "Pronunciation dictionary", "Dizionario di pronuncia",
     "Diccionario de pronunciación"),
    ("MSV = èm-èss-vé\nYouTube = you-tioube", "MSV = em-ess-vee\nGIF = jif", "MSV = emme-esse-vu\nYouTube = iutiub",
     "MSV = eme-ese-uve\nYouTube = yutub"),
    ("Vérification : {summary}", "Check: {summary}", "Verifica: {summary}", "Verificación: {summary}"),
    ("{n} phrase(s), {redone} refaite(s) après vérification, {doubtful} douteuse(s) (à réécouter)",
     "{n} sentence(s), {redone} redone after checking, {doubtful} doubtful (listen again)",
     "{n} frase/i, {redone} rifatta/e dopo la verifica, {doubtful} dubbia/e (da riascoltare)",
     "{n} frase(s), {redone} rehecha(s) tras la verificación, {doubtful} dudosa(s) (volver a escuchar)"),
    ("0,5 = naturel ; plus haut = plus d'émotion (et plus rapide)", "0.5 = natural; higher = more emotion (and faster)",
     "0,5 = naturale; più alto = più emozione (e più veloce)", "0,5 = natural; más alto = más emoción (y más rápido)"),
    ("Rythme", "Pace", "Ritmo", "Ritmo"),
    ("plus bas = plus posé, conseillé si la voix parle trop vite", "lower = calmer, useful if the voice speaks too fast",
     "più basso = più pacato, utile se la voce parla troppo veloce",
     "más bajo = más pausado, útil si la voz habla demasiado rápido"),
    ("Créer une nouvelle voix", "Create a new voice", "Crea una nuova voce", "Crear una voz nueva"),
    ("Enregistrement de la voix (WAV ou MP3, 10 à 60 s)", "Voice recording (WAV or MP3, 10 to 60 s)",
     "Registrazione della voce (WAV o MP3, da 10 a 60 s)", "Grabación de la voz (WAV o MP3, de 10 a 60 s)"),
    ("Nom de la voix", "Voice name", "Nome della voce", "Nombre de la voz"),
    ("C'est ma voix, ou j'ai l'accord de la personne enregistrée", "It's my voice, or I have the recorded person's consent",
     "È la mia voce, o ho il consenso della persona registrata", "Es mi voz, o tengo el consentimiento de la persona grabada"),
    ("Créer la voix", "Create the voice", "Crea la voce", "Crear la voz"),
    ("Voix « {name} » créée.", "Voice “{name}” created.", "Voce « {name} » creata.", "Voz «{name}» creada."),
    ("Coche la case : on ne clone que sa propre voix, ou celle d'une personne qui a donné son accord.",
     "Tick the box: only clone your own voice, or that of someone who gave their consent.",
     "Spunta la casella: si clona solo la propria voce, o quella di una persona che ha dato il consenso.",
     "Marca la casilla: solo se clona la propia voz, o la de una persona que haya dado su consentimiento."),
    ("Crée d'abord ta voix (« Créer une nouvelle voix »), puis choisis-la dans la liste.",
     "First create your voice (“Create a new voice”), then pick it in the list.",
     "Crea prima la tua voce (« Crea una nuova voce »), poi sceglila nell'elenco.",
     "Crea primero tu voz («Crear una voz nueva») y luego elígela en la lista."),
    ("Donne un nom à la voix.", "Give the voice a name.", "Dai un nome alla voce.", "Ponle un nombre a la voz."),
    ("Ajoute un enregistrement audio de ta voix (WAV ou MP3, 10 à 60 s).",
     "Add an audio recording of your voice (WAV or MP3, 10 to 60 s).",
     "Aggiungi una registrazione audio della tua voce (WAV o MP3, da 10 a 60 s).",
     "Añade una grabación de audio de tu voz (WAV o MP3, de 10 a 60 s)."),
    ("L'enregistrement est trop court : il faut au moins 10 secondes de voix.",
     "The recording is too short: at least 10 seconds of voice are needed.",
     "La registrazione è troppo corta: servono almeno 10 secondi di voce.",
     "La grabación es demasiado corta: hacen falta al menos 10 segundos de voz."),
    ("Le clonage de voix n'est pas encore installé : clique sur « Installer le clonage de voix » (environ 5 Go à "
     "télécharger, une seule fois).",
     "Voice cloning is not installed yet: click “Install voice cloning” (about 5 GB to download, only once).",
     "La clonazione della voce non è ancora installata: clicca su « Installa la clonazione della voce » (circa 5 GB "
     "da scaricare, una sola volta).",
     "La clonación de voz todavía no está instalada: haz clic en «Instalar la clonación de voz» (unos 5 GB que "
     "descargar, una sola vez)."),
    ("Installer le clonage de voix (≈ 5 Go, une seule fois)", "Install voice cloning (≈ 5 GB, only once)",
     "Installa la clonazione della voce (≈ 5 GB, una sola volta)", "Instalar la clonación de voz (≈ 5 GB, una sola vez)"),
    ("Installation du clonage de voix (plusieurs minutes)", "Installing voice cloning (several minutes)",
     "Installazione della clonazione della voce (alcuni minuti)", "Instalando la clonación de voz (varios minutos)"),
    ("Installation du clonage impossible : {err}", "Voice cloning could not be installed: {err}",
     "Impossibile installare la clonazione: {err}", "No se ha podido instalar la clonación: {err}"),
    ("Clonage de voix installé.", "Voice cloning installed.", "Clonazione della voce installata.",
     "Clonación de voz instalada."),
    ("La voix clonée n'a pas pu être générée : {err}", "The cloned voice could not be generated: {err}",
     "Non è stato possibile generare la voce clonata: {err}", "No se ha podido generar la voz clonada: {err}"),
    ("Voix introuvable : {name}", "Voice not found: {name}", "Voce non trovata: {name}", "Voz no encontrada: {name}"),
    ("le premier usage télécharge le modèle (environ 3 Go)", "first use downloads the model (about 3 GB)",
     "il primo utilizzo scarica il modello (circa 3 GB)", "el primer uso descarga el modelo (unos 3 GB)"),
    # ---- musique générée (core/music.py)
    ("calme", "calm", "calma", "tranquila"),
    ("inspirant", "inspiring", "ispirante", "inspiradora"),
    ("énergique", "energetic", "energica", "enérgica"),
    ("suspense", "suspense", "suspense", "suspense"),
    ("Musique générée (libre de droits)", "Generated music (royalty-free)", "Musica generata (senza diritti)",
     "Música generada (libre de derechos)"),
    ("utilisée s'il n'y a pas de fichier de musique ; composée à la durée exacte de la vidéo",
     "used when there is no music file; composed to the exact length of the video",
     "usata se non c'è un file di musica; composta alla durata esatta del video",
     "se usa si no hay archivo de música; compuesta a la duración exacta del vídeo"),
    ("Écouter 12 s", "Listen 12 s", "Ascolta 12 s", "Escuchar 12 s"),
    ("Extrait", "Sample", "Estratto", "Fragmento"),
    ("Choisis une ambiance de musique.", "Choose a music mood.", "Scegli un'atmosfera musicale.",
     "Elige un ambiente musical."),
    ("🎵 Musique générée : {mood}, {dur:.0f} s", "🎵 Generated music: {mood}, {dur:.0f} s",
     "🎵 Musica generata: {mood}, {dur:.0f} s", "🎵 Música generada: {mood}, {dur:.0f} s"),
    ("Texte du bouton", "Button text", "Testo del pulsante", "Texto del botón"),
    ("S'abonner", "Subscribe", "Iscriviti", "Suscribirse"),
    ("Texte après le clic (vide = pas de clic)", "Text after the click (empty = no click)",
     "Testo dopo il clic (vuoto = nessun clic)", "Texto después del clic (vacío = sin clic)"),
    ("Abonné", "Subscribed", "Iscritto", "Suscrito"),
    ("Badge en bas", "Bottom badge", "Badge in basso", "Distintivo abajo"),
    ("Lien en bio", "Link in bio", "Link in bio", "Link en la bio"),
    ("Fond", "Background", "Sfondo", "Fondo"),
    ("Lumières du fond", "Background lights", "Luci dello sfondo", "Luces del fondo"),
    ("Accent (*mots*, bouton)", "Accent (*words*, button)", "Accento (*parole*, pulsante)",
     "Acento (*palabras*, botón)"),
    ("Actualiser l'aperçu", "Refresh preview", "Aggiorna l'anteprima", "Actualizar la vista previa"),
    ("Créer la scène (vidéo)", "Create the scene (video)", "Crea la scena (video)", "Crear la escena (vídeo)"),
    ("Ajouter à la timeline", "Add to timeline", "Aggiungi alla timeline", "Añadir a la línea de tiempo"),
    ("Création de la scène", "Creating the scene", "Creazione della scena", "Creando la escena"),
    ("Scène créée : {name}", "Scene created: {name}", "Scena creata: {name}", "Escena creada: {name}"),
    ("Scène ajoutée à la fin de la timeline (onglet Montage).", "Scene added at the end of the timeline (Editor tab).",
     "Scena aggiunta alla fine della timeline (scheda Montaggio).",
     "Escena añadida al final de la línea de tiempo (pestaña Edición)."),
    ("Crée d'abord la scène (bouton « Créer la scène »).", "Create the scene first (“Create the scene” button).",
     "Crea prima la scena (pulsante « Crea la scena »).", "Crea primero la escena (botón «Crear la escena»)."),
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
    ("effet", "effect", "effetto", "efecto"),
    ("intensité", "intensity", "intensità", "intensidad"),

    # ---- stickers
    ("pulsation", "pulse", "pulsazione", "pulsación"),
    ("rebond", "bounce", "rimbalzo", "rebote"),
    ("balancement", "swing", "oscillazione", "balanceo"),
    ("Sticker", "Sticker", "Sticker", "Sticker"),
    ("Clique sur un sticker (ou choisis un emoji), règle son animation puis « Ajouter le sticker ». Il rejoint le "
     "tableau des incrustations, où tu peux encore le modifier.",
     "Click a sticker (or pick an emoji), set its animation, then “Add sticker”. It joins the overlay table, where "
     "you can still edit it.",
     "Clicca su uno sticker (o scegli un'emoji), regola l'animazione e poi « Aggiungi lo sticker ». Finisce nella "
     "tabella delle sovrapposizioni, dove puoi ancora modificarlo.",
     "Haz clic en un sticker (o elige un emoji), ajusta su animación y luego «Añadir el sticker». Pasa a la tabla "
     "de superposiciones, donde aún puedes modificarlo."),
    ("Emoji", "Emoji", "Emoji", "Emoji"),
    ("ou colle le tien (Windows + point)", "or paste your own (Windows + period)", "o incolla la tua (Windows + punto)",
     "o pega el tuyo (Windows + punto)"),
    ("Utiliser cet emoji", "Use this emoji", "Usa questa emoji", "Usar este emoji"),
    ("Importer un sticker", "Import a sticker", "Importa uno sticker", "Importar un sticker"),
    ("Sticker choisi", "Chosen sticker", "Sticker scelto", "Sticker elegido"),
    ("Sticker choisi : {name}", "Chosen sticker: {name}", "Sticker scelto: {name}", "Sticker elegido: {name}"),
    ("PNG, GIF, WebP animé ou WebM transparent : ton propre sticker passe par « Importer un sticker ».",
     "PNG, GIF, animated WebP or transparent WebM: add your own sticker with “Import a sticker”.",
     "PNG, GIF, WebP animato o WebM trasparente: il tuo sticker passa da « Importa uno sticker ».",
     "PNG, GIF, WebP animado o WebM transparente: tu propio sticker se añade con «Importar un sticker»."),
    ("Animation", "Animation", "Animazione", "Animación"),
    ("pulsation, rebond et balancement bougent tant que le sticker est à l'écran",
     "pulse, bounce and swing keep moving while the sticker is on screen",
     "pulsazione, rimbalzo e oscillazione si muovono finché lo sticker è sullo schermo",
     "pulsación, rebote y balanceo se mueven mientras el sticker está en pantalla"),
    ("Ajouter le sticker", "Add sticker", "Aggiungi lo sticker", "Añadir el sticker"),
    ("Un sticker doit être une image (PNG, GIF, WebP) ou une vidéo transparente (WebM).",
     "A sticker must be an image (PNG, GIF, WebP) or a transparent video (WebM).",
     "Uno sticker deve essere un'immagine (PNG, GIF, WebP) o un video trasparente (WebM).",
     "Un sticker debe ser una imagen (PNG, GIF, WebP) o un vídeo transparente (WebM)."),
    ("⚠ cette vidéo n'est pas transparente : elle s'affichera comme une carte.",
     "⚠ this video is not transparent: it will be shown as a card.",
     "⚠ questo video non è trasparente: verrà mostrato come una scheda.",
     "⚠ este vídeo no es transparente: se mostrará como una tarjeta."),
    ("Choisis un fichier.", "Choose a file.", "Scegli un file.", "Elige un archivo."),
    ("Clique d'abord sur un sticker (ou choisis un emoji).", "First click a sticker (or pick an emoji).",
     "Prima clicca su uno sticker (o scegli un'emoji).", "Primero haz clic en un sticker (o elige un emoji)."),
    ("Choisis ou colle un emoji (un seul).", "Pick or paste one emoji.", "Scegli o incolla un'emoji (una sola).",
     "Elige o pega un emoji (solo uno)."),
    ("Exemple : 🔥 😂 👀 — copie-le depuis le clavier emoji (Windows + point).",
     "Example: 🔥 😂 👀 — copy it from the emoji keyboard (Windows + period).",
     "Esempio: 🔥 😂 👀 — copiala dalla tastiera emoji (Windows + punto).",
     "Ejemplo: 🔥 😂 👀 — cópialo desde el teclado de emojis (Windows + punto)."),
    ("Aucune police d'emoji en couleur sur cet ordinateur.", "No color emoji font on this computer.",
     "Nessun font di emoji a colori su questo computer.", "No hay ninguna fuente de emojis en color en este ordenador."),
    ("Importe plutôt une image PNG transparente comme sticker.", "Import a transparent PNG image as a sticker instead.",
     "Importa invece un'immagine PNG trasparente come sticker.",
     "Importa en su lugar una imagen PNG transparente como sticker."),
    ("Cet emoji n'existe pas dans la police du système.", "This emoji is not in the system font.",
     "Questa emoji non esiste nel font di sistema.", "Este emoji no existe en la fuente del sistema."),
    ("Essaie un autre emoji.", "Try another emoji.", "Prova un'altra emoji.", "Prueba otro emoji."),
    # stickers intégrés (noms affichés et textes dessinés)
    ("bouton S'abonner", "Subscribe button", "pulsante Iscriviti", "botón Suscribirse"),
    ("cœur", "heart", "cuore", "corazón"),
    ("étoile", "star", "stella", "estrella"),
    ("flèche droite", "right arrow", "freccia a destra", "flecha derecha"),
    ("flèche gauche", "left arrow", "freccia a sinistra", "flecha izquierda"),
    ("flèche haut", "up arrow", "freccia in alto", "flecha arriba"),
    ("flèche bas", "down arrow", "freccia in basso", "flecha abajo"),
    ("cercle rouge", "red circle", "cerchio rosso", "círculo rojo"),
    ("éclair", "lightning", "fulmine", "rayo"),
    ("coche", "check mark", "spunta", "marca de verificación"),
    ("croix", "cross", "croce", "cruz"),
    ("badge Nouveau", "New badge", "badge Nuovo", "insignia Nuevo"),
    ("Nouveau", "New", "Nuovo", "Nuevo"),
    ("WOW !", "WOW!", "WOW!", "¡WOW!"),

    # ---- effets spéciaux
    ("Effets spéciaux", "Special effects", "Effetti speciali", "Efectos especiales"),
    ("secousse, zoom, flash, filtres", "shake, zoom, flash, filters", "scossa, zoom, flash, filtri",
     "sacudida, zoom, flash, filtros"),
    ("Sur un passage de la vidéo finale, sous les calques : stickers, textes et sous-titres restent nets par-dessus. "
     "« Fin » vide ou 0 = jusqu'à la fin.",
     "On a part of the final video, below the layers: stickers, text and subtitles stay sharp on top. "
     "Empty or 0 “End” = until the end.",
     "Su un passaggio del video finale, sotto i livelli: sticker, testi e sottotitoli restano nitidi sopra. "
     "« Fine » vuoto o 0 = fino alla fine.",
     "En un tramo del vídeo final, debajo de las capas: stickers, textos y subtítulos quedan nítidos encima. "
     "«Fin» vacío o 0 = hasta el final."),
    ("Effet", "Effect", "Effetto", "Efecto"),
    ("secousse, zoom et flash : moments forts · filtres : ambiance",
     "shake, zoom and flash: key moments · filters: mood",
     "scossa, zoom e flash: momenti forti · filtri: atmosfera",
     "sacudida, zoom y flash: momentos clave · filtros: ambiente"),
    ("Début (s)", "Start (s)", "Inizio (s)", "Inicio (s)"),
    ("Fin (s)", "End (s)", "Fine (s)", "Fin (s)"),
    ("Intensité", "Intensity", "Intensità", "Intensidad"),
    ("Ajouter l'effet", "Add effect", "Aggiungi l'effetto", "Añadir el efecto"),
    ("secousse", "shake", "scossa", "sacudida"),
    ("zoom punch", "punch zoom", "zoom punch", "zoom punch"),
    ("zoom progressif", "slow zoom", "zoom progressivo", "zoom progresivo"),
    ("flash blanc", "white flash", "flash bianco", "destello blanco"),
    ("flash noir", "black flash", "flash nero", "destello negro"),
    ("noir et blanc", "black and white", "bianco e nero", "blanco y negro"),
    ("vintage", "vintage", "vintage", "vintage"),
    ("couleurs vives", "vivid colors", "colori vivaci", "colores vivos"),
    ("cinéma", "cinematic", "cinema", "cine"),
    ("chaud", "warm", "caldo", "cálido"),
    ("froid", "cool", "freddo", "frío"),
    ("vignette", "vignette", "vignettatura", "viñeta"),
    ("glitch", "glitch", "glitch", "glitch"),
    ("négatif", "negative", "negativo", "negativo"),
    ("Le début ne peut pas être négatif.", "The start cannot be negative.", "L'inizio non può essere negativo.",
     "El inicio no puede ser negativo."),
    ("Écris 0 ou plus dans « Début ».", "Enter 0 or more in “Start”.", "Scrivi 0 o più in « Inizio ».",
     "Escribe 0 o más en «Inicio»."),
    ("L'effet finirait ({e:g} s) avant de commencer ({s:g} s).",
     "The effect would end ({e:g} s) before it starts ({s:g} s).",
     "L'effetto finirebbe ({e:g} s) prima di iniziare ({s:g} s).",
     "El efecto terminaría ({e:g} s) antes de empezar ({s:g} s)."),
    ("Mets dans « Fin » une heure plus grande que « Début », ou 0 pour aller jusqu'à la fin.",
     "Put a time greater than “Start” in “End”, or 0 to go until the end.",
     "Metti in « Fine » un tempo più grande di « Inizio », oppure 0 per arrivare fino alla fine.",
     "Pon en «Fin» un tiempo mayor que «Inicio», o 0 para llegar hasta el final."),
    ("Effet ajouté : {name}, de {s} s à {e} s.", "Effect added: {name}, from {s} s to {e} s.",
     "Effetto aggiunto: {name}, da {s} s a {e} s.", "Efecto añadido: {name}, de {s} s a {e} s."),
    ("Effet ajouté : {name}, de {s} s jusqu'à la fin.", "Effect added: {name}, from {s} s until the end.",
     "Effetto aggiunto: {name}, da {s} s fino alla fine.", "Efecto añadido: {name}, desde {s} s hasta el final."),
    ("⚠ Effet ignoré (hors de la vidéo ou durée nulle) : {name}",
     "⚠ Effect skipped (outside the video or zero duration): {name}",
     "⚠ Effetto ignorato (fuori dal video o durata nulla): {name}",
     "⚠ Efecto ignorado (fuera del vídeo o duración nula): {name}"),
    ("✨ Effets spéciaux : {names}", "✨ Special effects: {names}", "✨ Effetti speciali: {names}",
     "✨ Efectos especiales: {names}"),
    ("zoom fixe", "fixed zoom", "zoom fisso", "zoom fijo"),

    # ---- rythme et effets sonores
    ("Rythme et effets sonores", "Rhythm and sound effects", "Ritmo ed effetti sonori", "Ritmo y efectos de sonido"),
    ("le montage suit la musique", "the edit follows the music", "il montaggio segue la musica",
     "el montaje sigue la música"),
    ("Analyser le rythme de la musique", "Analyze the music's rhythm", "Analizza il ritmo della musica",
     "Analizar el ritmo de la música"),
    ("La musique est celle des réglages Audio (fichier ou générée).",
     "The music is the one in the Audio settings (file or generated).",
     "La musica è quella delle impostazioni Audio (file o generata).",
     "La música es la de los ajustes de Audio (archivo o generada)."),
    ("Effet sur les temps", "Effect on the beats", "Effetto sui battiti", "Efecto en los tiempos"),
    ("Fréquence", "Frequency", "Frequenza", "Frecuencia"),
    ("tous les temps", "every beat", "ogni battito", "cada tiempo"),
    ("tous les 2 temps", "every 2 beats", "ogni 2 battiti", "cada 2 tiempos"),
    ("tous les 4 temps (1 mesure)", "every 4 beats (1 bar)", "ogni 4 battiti (1 battuta)",
     "cada 4 tiempos (1 compás)"),
    ("tous les 8 temps", "every 8 beats", "ogni 8 battiti", "cada 8 tiempos"),
    ("Images fixes calées sur le rythme (chaque coupe tombe sur un temps)",
     "Still images synced to the rhythm (every cut lands on a beat)",
     "Immagini fisse a tempo (ogni taglio cade su un battito)",
     "Imágenes fijas al ritmo (cada corte cae en un tiempo)"),
    ("À chaque coupe : effet", "On every cut: effect", "A ogni taglio: effetto", "En cada corte: efecto"),
    ("zoom alterné = un plan sur deux resserré (jump cut)", "alternating zoom = every other shot tighter (jump cut)",
     "zoom alternato = un'inquadratura su due più stretta (jump cut)",
     "zoom alterno = un plano de cada dos más cerrado (jump cut)"),
    ("À chaque coupe : son", "On every cut: sound", "A ogni taglio: suono", "En cada corte: sonido"),
    ("Intensité de l'effet", "Effect intensity", "Intensità dell'effetto", "Intensidad del efecto"),
    ("Volume du son", "Sound volume", "Volume del suono", "Volumen del sonido"),
    ("Effet sonore à un moment précis", "Sound effect at a given moment", "Effetto sonoro in un momento preciso",
     "Efecto de sonido en un momento preciso"),
    ("Écouter", "Listen", "Ascolta", "Escuchar"),
    ("Importer un son", "Import a sound", "Importa un suono", "Importar un sonido"),
    ("Au moment (s)", "At (s)", "Al momento (s)", "En el momento (s)"),
    ("Volume", "Volume", "Volume", "Volumen"),
    ("Ajouter le son", "Add sound", "Aggiungi il suono", "Añadir el sonido"),
    ("zoom alterné", "alternating zoom", "zoom alternato", "zoom alterno"),
    ("swipe", "swipe", "swipe", "swipe"),
    ("succès", "success", "successo", "éxito"),
    ("clic", "click", "clic", "clic"),
    ("bip censure", "censor beep", "bip censura", "pitido de censura"),
    ("déclic photo", "camera shutter", "scatto foto", "obturador de foto"),
    ("Un effet sonore doit être un fichier audio (MP3, WAV…).", "A sound effect must be an audio file (MP3, WAV…).",
     "Un effetto sonoro deve essere un file audio (MP3, WAV…).",
     "Un efecto de sonido debe ser un archivo de audio (MP3, WAV…)."),
    ("Choisis d'abord un son.", "First choose a sound.", "Prima scegli un suono.", "Primero elige un sonido."),
    ("Écris 0 ou plus dans « Au moment (s) ».", "Enter 0 or more in “At (s)”.", "Scrivi 0 o più in « Al momento (s) ».",
     "Escribe 0 o más en «En el momento (s)»."),
    ("Son ajouté à {s} s.", "Sound added at {s} s.", "Suono aggiunto a {s} s.", "Sonido añadido en {s} s."),
    ("⚠ Aucun rythme net dans cette musique : les effets sur les temps ne seront pas ajoutés.",
     "⚠ No clear rhythm in this music: no effects will be added on the beats.",
     "⚠ Nessun ritmo netto in questa musica: gli effetti sui battiti non verranno aggiunti.",
     "⚠ No hay un ritmo claro en esta música: no se añadirán efectos en los tiempos."),
    ("🥁 ≈ {bpm:.0f} BPM · {n} temps sur {dur:.0f} s · un temps toutes les {p:.2f} s",
     "🥁 ≈ {bpm:.0f} BPM · {n} beats in {dur:.0f} s · one beat every {p:.2f} s",
     "🥁 ≈ {bpm:.0f} BPM · {n} battiti in {dur:.0f} s · un battito ogni {p:.2f} s",
     "🥁 ≈ {bpm:.0f} BPM · {n} tiempos en {dur:.0f} s · un tiempo cada {p:.2f} s"),
    ("🥁 Musique générée « {mood} » : {bpm} BPM exacts", "🥁 Generated music “{mood}”: exactly {bpm} BPM",
     "🥁 Musica generata « {mood} »: {bpm} BPM esatti", "🥁 Música generada «{mood}»: {bpm} BPM exactos"),
    ("Ajoute d'abord une musique (réglages Audio → Musique) ou choisis une musique générée.",
     "First add music (Audio settings → Music) or choose generated music.",
     "Prima aggiungi una musica (impostazioni Audio → Musica) o scegli una musica generata.",
     "Primero añade una música (ajustes de Audio → Música) o elige una música generada."),
    ("⚠ Rythme de la musique introuvable : {err}", "⚠ Could not find the music's rhythm: {err}",
     "⚠ Ritmo della musica non trovato: {err}", "⚠ No se encontró el ritmo de la música: {err}"),
    ("⚠ Images sur le rythme : ajoute une musique (fichier ou générée).",
     "⚠ Images on the rhythm: add music (file or generated).",
     "⚠ Immagini a tempo: aggiungi una musica (file o generata).",
     "⚠ Imágenes al ritmo: añade una música (archivo o generada)."),
    ("🥁 {n} images calées sur le rythme ({bpm:.0f} BPM)", "🥁 {n} images synced to the rhythm ({bpm:.0f} BPM)",
     "🥁 {n} immagini a tempo ({bpm:.0f} BPM)", "🥁 {n} imágenes al ritmo ({bpm:.0f} BPM)"),
    ("⚠ Effets sur le rythme : ajoute une musique (fichier ou générée).",
     "⚠ Effects on the rhythm: add music (file or generated).",
     "⚠ Effetti a tempo: aggiungi una musica (file o generata).",
     "⚠ Efectos al ritmo: añade una música (archivo o generada)."),
    ("🥁 Rythme : {bpm:.0f} BPM, {n} effets « {fx} » sur les temps",
     "🥁 Rhythm: {bpm:.0f} BPM, {n} “{fx}” effects on the beats",
     "🥁 Ritmo: {bpm:.0f} BPM, {n} effetti « {fx} » sui battiti",
     "🥁 Ritmo: {bpm:.0f} BPM, {n} efectos «{fx}» en los tiempos"),
    ("✂ {n} coupes : {fx} · {snd}", "✂ {n} cuts: {fx} · {snd}", "✂ {n} tagli: {fx} · {snd}",
     "✂ {n} cortes: {fx} · {snd}"),
    ("🔊 Effets sonores : {n}", "🔊 Sound effects: {n}", "🔊 Effetti sonori: {n}", "🔊 Efectos de sonido: {n}"),

    # ---- studio audio
    ("Studio audio", "Audio studio", "Studio audio", "Estudio de audio"),
    ("Enchaîne tes musiques, superpose voix et ambiances, transforme ta voix. Chaque outil range ses fichiers dans "
     "son propre dossier.",
     "Chain your music, layer voices and ambiences, transform your voice. Each tool stores its files in its own "
     "folder.",
     "Concatena le tue musiche, sovrapponi voci e ambienti, trasforma la tua voce. Ogni strumento salva i suoi file "
     "nella propria cartella.",
     "Encadena tus músicas, superpón voces y ambientes, transforma tu voz. Cada herramienta guarda sus archivos en "
     "su propia carpeta."),
    ("enchaînement", "chain", "concatenazione", "encadenado"),
    ("superposition", "layering", "sovrapposizione", "superposición"),
    ("effets micro", "mic effects", "effetti microfono", "efectos de micro"),
    ("Enchaînement", "Chaining", "Concatenazione", "Encadenado"),
    ("Superposition", "Layering", "Sovrapposizione", "Superposición"),
    ("Effets micro", "Mic effects", "Effetti microfono", "Efectos de micro"),
    ("Enchaîner", "Chain", "Concatena", "Encadenar"),
    ("Superposer", "Layer", "Sovrapponi", "Superponer"),
    ("Effets micro et mixage", "Mic effects and mixing", "Effetti microfono e mixaggio", "Efectos de micro y mezcla"),
    ("Sorties", "Outputs", "File creati", "Salidas"),
    ("Morceaux", "Tracks", "Brani", "Pistas"),
    ("Durée du fondu enchaîné (s)", "Crossfade length (s)", "Durata della dissolvenza incrociata (s)",
     "Duración del fundido cruzado (s)"),
    ("Courbe du fondu", "Fade curve", "Curva della dissolvenza", "Curva del fundido"),
    ("équilibré", "balanced", "bilanciata", "equilibrada"),
    ("linéaire", "linear", "lineare", "lineal"),
    ("rapide", "fast", "rapida", "rápida"),
    ("Finition", "Finishing", "Rifinitura", "Acabado"),
    ("Fondu d'entrée (s)", "Fade in (s)", "Dissolvenza in entrata (s)", "Fundido de entrada (s)"),
    ("Fondu de sortie (s)", "Fade out (s)", "Dissolvenza in uscita (s)", "Fundido de salida (s)"),
    ("Volume normalisé (-14 LUFS)", "Normalized volume (-14 LUFS)", "Volume normalizzato (-14 LUFS)",
     "Volumen normalizado (-14 LUFS)"),
    ("Enchaîner les morceaux", "Chain the tracks", "Concatena i brani", "Encadenar las pistas"),
    ("Forme d'onde", "Waveform", "Forma d'onda", "Forma de onda"),
    ("Utiliser comme musique du projet", "Use as project music", "Usa come musica del progetto",
     "Usar como música del proyecto"),
    ("Pistes", "Tracks", "Tracce", "Pistas"),
    ("Rôle", "Role", "Ruolo", "Función"),
    ("musique", "music", "musica", "música"),
    ("voix", "voice", "voce", "voz"),
    ("ambiance", "ambience", "ambiente", "ambiente"),
    ("Mélange", "Mix", "Mix", "Mezcla"),
    ("Durée du résultat", "Result length", "Durata del risultato", "Duración del resultado"),
    ("la voix", "the voice", "la voce", "la voz"),
    ("« la voix » : le mélange s'arrête quand la voix finit", "“the voice”: the mix stops when the voice ends",
     "« la voce »: il mix si ferma quando finisce la voce", "«la voz»: la mezcla se detiene cuando termina la voz"),
    ("Ducking : la musique baisse quand la voix parle", "Ducking: the music dips when the voice speaks",
     "Ducking: la musica si abbassa quando parla la voce", "Ducking: la música baja cuando habla la voz"),
    ("Superposer les pistes", "Layer the tracks", "Sovrapponi le tracce", "Superponer las pistas"),
    ("Ta voix", "Your voice", "La tua voce", "Tu voz"),
    ("enregistre-la ici ou importe un fichier", "record it here or import a file", "registrala qui o importa un file",
     "grábala aquí o importa un archivo"),
    ("Micro ou fichier", "Microphone or file", "Microfono o file", "Micrófono o archivo"),
    ("Effet de voix", "Voice effect", "Effetto voce", "Efecto de voz"),
    ("Console de mixage", "Mixing console", "Mixer", "Mesa de mezclas"),
    ("Graves (dB)", "Bass (dB)", "Bassi (dB)", "Graves (dB)"),
    ("Médiums (dB)", "Mids (dB)", "Medi (dB)", "Medios (dB)"),
    ("Aigus (dB)", "Treble (dB)", "Acuti (dB)", "Agudos (dB)"),
    ("Compresseur", "Compressor", "Compressore", "Compresor"),
    ("égalise le volume : les passages faibles remontent", "evens out the volume: quiet parts come up",
     "uniforma il volume: i passaggi deboli salgono", "iguala el volumen: los pasajes suaves suben"),
    ("Gain (dB)", "Gain (dB)", "Guadagno (dB)", "Ganancia (dB)"),
    ("sans changer la hauteur de la voix", "without changing the pitch", "senza cambiare l'altezza della voce",
     "sin cambiar el tono de la voz"),
    ("Remettre la console à zéro", "Reset the console", "Azzera il mixer", "Reiniciar la mesa"),
    ("Appliquer les effets", "Apply effects", "Applica gli effetti", "Aplicar los efectos"),
    ("Utiliser comme voix off du projet", "Use as project voice-over", "Usa come voce fuori campo del progetto",
     "Usar como voz en off del proyecto"),
    ("Chaque outil a son dossier : retrouve, écoute et réutilise tes fichiers.",
     "Each tool has its own folder: find, play and reuse your files.",
     "Ogni strumento ha la sua cartella: ritrova, ascolta e riusa i tuoi file.",
     "Cada herramienta tiene su carpeta: encuentra, escucha y reutiliza tus archivos."),
    ("Fichiers", "Files", "File", "Archivos"),
    ("Actualiser", "Refresh", "Aggiorna", "Actualizar"),
    ("Ouvrir", "Open", "Apri", "Abrir"),
    ("Sorties rangées dans", "Outputs saved in", "File salvati in", "Salidas guardadas en"),
    ("Fichier créé", "File created", "File creato", "Archivo creado"),
    ("{n} fichier(s) dans « {kind} »", "{n} file(s) in “{kind}”", "{n} file in « {kind} »",
     "{n} archivo(s) en «{kind}»"),
    ("Aucune sortie « {kind} » pour l'instant.", "No “{kind}” output yet.", "Ancora nessun file « {kind} ».",
     "Todavía no hay salidas «{kind}»."),
    ("Crée ou choisis d'abord un fichier audio.", "First create or choose an audio file.",
     "Prima crea o scegli un file audio.", "Primero crea o elige un archivo de audio."),
    ("✅ Utilisé comme musique du projet (onglet Montage → Audio).",
     "✅ Used as project music (Editor tab → Audio).",
     "✅ Usato come musica del progetto (scheda Montaggio → Audio).",
     "✅ Usado como música del proyecto (pestaña Edición → Audio)."),
    ("✅ Utilisé comme voix off du projet (onglet Montage → Audio).",
     "✅ Used as project voice-over (Editor tab → Audio).",
     "✅ Usato come voce fuori campo del progetto (scheda Montaggio → Audio).",
     "✅ Usado como voz en off del proyecto (pestaña Edición → Audio)."),
    ("voix studio", "studio voice", "voce da studio", "voz de estudio"),
    ("radio", "radio", "radio", "radio"),
    ("mégaphone", "megaphone", "megafono", "megáfono"),
    ("robot", "robot", "robot", "robot"),
    ("écho", "echo", "eco", "eco"),
    ("grande salle", "large hall", "grande sala", "sala grande"),
    ("voix grave", "deep voice", "voce grave", "voz grave"),
    ("voix aiguë", "high voice", "voce acuta", "voz aguda"),
    ("monstre", "monster", "mostro", "monstruo"),
    ("chorale", "choir", "coro", "coro"),
    ("alien", "alien", "alieno", "alienígena"),
    ("Morceau trop court après la coupe : {name}", "Track too short after trimming: {name}",
     "Brano troppo corto dopo il taglio: {name}", "Pista demasiado corta tras el recorte: {name}"),
    ("⚠ Rythme introuvable ({err}) : fondu normal", "⚠ Rhythm not found ({err}): normal fade",
     "⚠ Ritmo non trovato ({err}): dissolvenza normale", "⚠ Ritmo no encontrado ({err}): fundido normal"),
    ("🥁 Transition {k} → {k2} : sur le temps ({bpm:.0f} BPM), fondu de {d:.2f} s",
     "🥁 Transition {k} → {k2}: on the beat ({bpm:.0f} BPM), {d:.2f} s fade",
     "🥁 Transizione {k} → {k2}: a tempo ({bpm:.0f} BPM), dissolvenza di {d:.2f} s",
     "🥁 Transición {k} → {k2}: al ritmo ({bpm:.0f} BPM), fundido de {d:.2f} s"),
    ("⚠ Transition {k} → {k2} : pas de rythme net, fondu normal",
     "⚠ Transition {k} → {k2}: no clear rhythm, normal fade",
     "⚠ Transizione {k} → {k2}: ritmo poco chiaro, dissolvenza normale",
     "⚠ Transición {k} → {k2}: sin ritmo claro, fundido normal"),
    ("Ajoute au moins 2 fichiers audio à enchaîner.", "Add at least 2 audio files to chain.",
     "Aggiungi almeno 2 file audio da concatenare.", "Añade al menos 2 archivos de audio para encadenar."),
    ("🔗 {n} morceaux enchaînés : {dur:.1f} s", "🔗 {n} tracks chained: {dur:.1f} s",
     "🔗 {n} brani concatenati: {dur:.1f} s", "🔗 {n} pistas encadenadas: {dur:.1f} s"),
    ("Ajoute au moins 2 fichiers audio à superposer.", "Add at least 2 audio files to layer.",
     "Aggiungi almeno 2 file audio da sovrapporre.", "Añade al menos 2 archivos de audio para superponer."),
    ("🎚 Ducking : la musique baisse quand la voix parle", "🎚 Ducking: the music dips when the voice speaks",
     "🎚 Ducking: la musica si abbassa quando parla la voce", "🎚 Ducking: la música baja cuando habla la voz"),
    ("🎛 {n} pistes superposées : {dur:.1f} s", "🎛 {n} tracks layered: {dur:.1f} s",
     "🎛 {n} tracce sovrapposte: {dur:.1f} s", "🎛 {n} pistas superpuestas: {dur:.1f} s"),
    ("Enregistre ta voix ou importe un fichier audio.", "Record your voice or import an audio file.",
     "Registra la tua voce o importa un file audio.", "Graba tu voz o importa un archivo de audio."),
    ("🎙 Effet « {preset} » appliqué : {dur:.1f} s", "🎙 “{preset}” effect applied: {dur:.1f} s",
     "🎙 Effetto « {preset} » applicato: {dur:.1f} s", "🎙 Efecto «{preset}» aplicado: {dur:.1f} s"),

    # ---- menu principal
    ("Menu principal", "Main menu", "Menu principale", "Menú principal"),

    # ---- studio audio : pistes illimitées, transitions de DJ, isolateur tactile
    ("transition", "transition", "transizione", "transición"),
    ("rôle", "role", "ruolo", "función"),
    ("commence à", "starts at", "inizia a", "empieza en"),
    ("boucle", "loop", "loop", "bucle"),
    ("coupe sèche", "hard cut", "taglio netto", "corte seco"),
    ("isolateur (bass swap)", "isolator (bass swap)", "isolatore (bass swap)", "aislador (bass swap)"),
    ("back spin", "back spin", "back spin", "back spin"),
    ("freinage", "vinyl brake", "frenata vinile", "frenado de vinilo"),
    ("graves", "bass", "bassi", "graves"),
    ("médiums", "mids", "medi", "medios"),
    ("aigus", "treble", "acuti", "agudos"),
    ("Graves", "Bass", "Bassi", "Graves"),
    ("Médiums", "Mids", "Medi", "Medios"),
    ("Aigus", "Treble", "Acuti", "Agudos"),
    ("coupés", "cut", "tagliati", "cortados"),
    ("Isolateur", "Isolator", "Isolatore", "Aislador"),
    ("Isolateur 3 bandes", "3-band isolator", "Isolatore a 3 bande", "Aislador de 3 bandas"),
    ("tout le résultat", "the whole result", "tutto il risultato", "todo el resultado"),
    ("Glisse avec le doigt ou la souris · double-tap = 0 dB · KILL coupe la bande",
     "Slide with your finger or mouse · double-tap = 0 dB · KILL cuts the band",
     "Scorri con il dito o il mouse · doppio tocco = 0 dB · KILL taglia la banda",
     "Desliza con el dedo o el ratón · doble toque = 0 dB · KILL corta la banda"),
    ("Tout à 0", "All to 0", "Tutto a 0", "Todo a 0"),
    ("🎚 Transitions : {list}", "🎚 Transitions: {list}", "🎚 Transizioni: {list}", "🎚 Transiciones: {list}"),
    ("⚠ {n} morceaux : seuls les {max} premiers sont gardés.", "⚠ {n} tracks: only the first {max} are kept.",
     "⚠ {n} brani: vengono tenuti solo i primi {max}.", "⚠ {n} pistas: solo se conservan las {max} primeras."),
    ("🥁 Transition {k} → {k2} : {fx} sur le temps ({bpm:.0f} BPM)",
     "🥁 Transition {k} → {k2}: {fx} on the beat ({bpm:.0f} BPM)",
     "🥁 Transizione {k} → {k2}: {fx} a tempo ({bpm:.0f} BPM)",
     "🥁 Transición {k} → {k2}: {fx} al ritmo ({bpm:.0f} BPM)"),
    ("Ignoré (ni audio ni vidéo) : {name}", "Skipped (neither audio nor video): {name}",
     "Ignorato (né audio né video): {name}", "Ignorado (ni audio ni vídeo): {name}"),
    ("{n} piste(s) ajoutée(s) : {total} au total.", "{n} track(s) added: {total} in total.",
     "{n} traccia/e aggiunta/e: {total} in totale.", "{n} pista(s) añadida(s): {total} en total."),
    ("Aucun fichier audio dans la médiathèque de l'onglet Montage.", "No audio file in the Editor tab's media library.",
     "Nessun file audio nella libreria della scheda Montaggio.",
     "No hay ningún archivo de audio en la biblioteca de la pestaña Edición."),
    ("Transition « {t} » appliquée à toutes les pistes.", "“{t}” transition applied to every track.",
     "Transizione « {t} » applicata a tutte le tracce.", "Transición «{t}» aplicada a todas las pistas."),
    ("autant que tu veux, joués dans l'ordre", "as many as you like, played in order",
     "quanti vuoi, suonati in ordine", "tantas como quieras, en orden"),
    ("autant que tu veux, jouées en même temps", "as many as you like, played at the same time",
     "quante vuoi, suonate insieme", "tantas como quieras, sonando a la vez"),
    ("Ajouter des morceaux", "Add tracks", "Aggiungi brani", "Añadir pistas"),
    ("Ajouter des pistes", "Add tracks", "Aggiungi tracce", "Añadir pistas"),
    ("Sons de la médiathèque", "Sounds from the media library", "Suoni della libreria", "Sonidos de la biblioteca"),
    ("Rôle des pistes ajoutées", "Role of added tracks", "Ruolo delle tracce aggiunte", "Función de las pistas añadidas"),
    ("Choisis plusieurs fichiers d'un coup (Ctrl ou Maj). Début et fin se remplissent tout seuls avec le morceau "
     "entier : modifie-les pour couper. Volume et transition vers le morceau suivant se règlent aussi. Clique sur une "
     "ligne pour l'écouter.",
     "Pick several files at once (Ctrl or Shift). Start and end are filled in automatically with the whole track: "
     "edit them to trim. Volume and transition to the next track can be set too. Click a row to listen to it.",
     "Scegli più file insieme (Ctrl o Maiusc). Inizio e fine si compilano da soli con il brano intero: modificali "
     "per tagliare. Si regolano anche il volume e la transizione verso il brano successivo. Clicca su una riga per "
     "ascoltarla.",
     "Elige varios archivos a la vez (Ctrl o Mayús). Inicio y fin se rellenan solos con la pista entera: cámbialos "
     "para recortar. También se ajustan el volumen y la transición a la pista siguiente. Haz clic en una fila para "
     "escucharla."),

    # ---- platine DJ
    ("Platine DJ", "DJ deck", "Console DJ", "Mesa de DJ"),
    ("platine dj", "DJ deck", "console DJ", "mesa de DJ"),
    ("corne de stade", "stadium horn", "tromba da stadio", "bocina de estadio"),
    ("sirène", "siren", "sirena", "sirena"),
    ("scratch", "scratch", "scratch", "scratch"),
    ("laser", "laser", "laser", "láser"),
    ("grosse caisse", "kick drum", "cassa", "bombo"),
    ("clap", "clap", "clap", "palmada"),
    ("roulement", "snare roll", "rullata", "redoble"),
    ("impact", "impact", "impatto", "impacto"),
    ("filtre grave", "low filter", "filtro bassi", "filtro de graves"),
    ("filtre aigu", "high filter", "filtro acuti", "filtro de agudos"),
    ("flanger", "flanger", "flanger", "flanger"),
    ("roll", "roll", "roll", "roll"),
    ("hachoir", "chopper", "trancia", "cortador"),
    ("moment", "time", "momento", "momento"),
    ("instrument", "instrument", "strumento", "instrumento"),
    ("Instruments", "Instruments", "Strumenti", "Instrumentos"),
    ("Effets de platine", "Deck effects", "Effetti della console", "Efectos de la mesa"),
    ("touche pendant l’écoute (ou touches 1 à 9)", "tap while it plays (or keys 1 to 9)",
     "tocca durante l'ascolto (o tasti da 1 a 9)", "toca mientras suena (o teclas 1 a 9)"),
    ("maintiens appuyé (ou touches Q W E R T Y)", "hold down (or keys Q W E R T Y)",
     "tieni premuto (o tasti Q W E R T Y)", "mantén pulsado (o teclas Q W E R T Y)"),
    ("Chaque coup s’inscrit dans les tableaux au moment de la lecture. Espace = lecture/pause.",
     "Every hit is written into the tables at the playback time. Space = play/pause.",
     "Ogni colpo si scrive nelle tabelle al momento della riproduzione. Spazio = play/pausa.",
     "Cada golpe se anota en las tablas en el momento de la reproducción. Espacio = reproducir/pausa."),
    ("Choisis une musique ci-dessus : elle se jouera ici.", "Pick a song above: it will play here.",
     "Scegli una musica qui sopra: suonerà qui.", "Elige una canción arriba: sonará aquí."),
    ("Choisis un fichier audio (ou une vidéo avec du son).", "Pick an audio file (or a video with sound).",
     "Scegli un file audio (o un video con audio).", "Elige un archivo de audio (o un vídeo con sonido)."),
    ("Ta musique", "Your song", "La tua musica", "Tu canción"),
    ("celle sur laquelle tu joues", "the one you play over", "quella su cui suoni", "sobre la que tocas"),
    ("Choisir une musique", "Choose a song", "Scegli una musica", "Elegir una canción"),
    ("Résultat d'Enchaîner", "Chain result", "Risultato di Concatena", "Resultado de Encadenar"),
    ("Résultat de Superposer", "Layer result", "Risultato di Sovrapponi", "Resultado de Superponer"),
    ("Joue en direct", "Play live", "Suona dal vivo", "Toca en directo"),
    ("comme un DJ", "like a DJ", "come un DJ", "como un DJ"),
    ("Tes coups", "Your hits", "I tuoi colpi", "Tus golpes"),
    ("modifiables : moment, volume, durée, intensité", "editable: time, volume, length, intensity",
     "modificabili: momento, volume, durata, intensità", "editables: momento, volumen, duración, intensidad"),
    ("Instruments : le moment est la seconde de la musique où tombe le coup. Effets : début, fin et intensité (0 à 1). "
     "Tu peux tout corriger à la main.",
     "Instruments: the time is the second of the song where the hit lands. Effects: start, end and intensity (0 to 1). "
     "You can fix everything by hand.",
     "Strumenti: il momento è il secondo della musica in cui cade il colpo. Effetti: inizio, fine e intensità (da 0 a "
     "1). Puoi correggere tutto a mano.",
     "Instrumentos: el momento es el segundo de la canción en el que cae el golpe. Efectos: inicio, fin e intensidad "
     "(0 a 1). Puedes corregirlo todo a mano."),
    ("Mixage", "Mixing", "Mixaggio", "Mezcla"),
    ("Caler sur le temps", "Snap to the beat", "Aggancia al battito", "Ajustar al tiempo"),
    ("chaque coup et chaque effet tombent pile sur le temps le plus proche",
     "every hit and every effect lands right on the nearest beat",
     "ogni colpo e ogni effetto cadono esattamente sul battito più vicino",
     "cada golpe y cada efecto caen justo en el tiempo más cercano"),
    ("Volume des instruments", "Instrument volume", "Volume degli strumenti", "Volumen de los instrumentos"),
    ("Mixer la platine", "Mix the deck", "Mixa la console", "Mezclar la mesa"),
    ("Choisis d'abord une musique pour la platine.", "Pick a song for the deck first.",
     "Scegli prima una musica per la console.", "Elige primero una canción para la mesa."),
    ("Musique trop courte pour la platine (1 s au moins).", "Song too short for the deck (1 s minimum).",
     "Musica troppo corta per la console (almeno 1 s).", "Canción demasiado corta para la mesa (1 s como mínimo)."),
    ("Touche au moins un pad (instrument ou effet) pendant l'écoute.",
     "Hit at least one pad (instrument or effect) while it plays.",
     "Tocca almeno un pad (strumento o effetto) durante l'ascolto.",
     "Toca al menos un pad (instrumento o efecto) mientras suena."),
    ("🥁 Rythme : {bpm:.0f} BPM", "🥁 Tempo: {bpm:.0f} BPM", "🥁 Ritmo: {bpm:.0f} BPM", "🥁 Ritmo: {bpm:.0f} BPM"),
    ("⚠ Rythme introuvable ({err}) : moments gardés tels quels", "⚠ No beat found ({err}): times kept as played",
     "⚠ Ritmo non trovato ({err}): momenti lasciati come suonati",
     "⚠ Ritmo no encontrado ({err}): momentos tal como se tocaron"),
    ("🎯 Coups et effets calés sur le temps", "🎯 Hits and effects snapped to the beat",
     "🎯 Colpi ed effetti agganciati al battito", "🎯 Golpes y efectos ajustados al tiempo"),
    # ---- platine DJ : textures et bus d'effets
    ("espace", "space", "spazio", "espacio"),
    ("shimmer", "shimmer", "shimmer", "shimmer"),
    ("dub", "dub", "dub", "dub"),
    ("crush", "crush", "crush", "crush"),
    ("gel", "freeze", "congela", "congelar"),
    ("vinyle", "vinyl", "vinile", "vinilo"),
    ("vent", "wind", "vento", "viento"),
    ("pluie", "rain", "pioggia", "lluvia"),
    ("bruit montant", "noise riser", "rumore in salita", "ruido ascendente"),
    ("Textures sonores", "Sound textures", "Texture sonore", "Texturas sonoras"),
    ("maintiens appuyé (ou touches A à L)", "hold down (or keys A to L)", "tieni premuto (o tasti da A a L)",
     "mantén pulsado (o teclas A a L)"),
    ("Volume des textures", "Texture volume", "Volume delle texture", "Volumen de las texturas"),
    ("vinyle, vent, pluie, bruit montant", "vinyl, wind, rain, noise riser", "vinile, vento, pioggia, rumore in salita",
     "vinilo, viento, lluvia, ruido ascendente"),
    ("Bus d'effets", "Effects bus", "Bus degli effetti", "Bus de efectos"),
    ("Send/Return ou Master", "Send/Return or Master", "Send/Return o Master", "Send/Return o Master"),
    ("Routage des effets", "Effects routing", "Instradamento degli effetti", "Enrutamiento de efectos"),
    ("auto", "auto", "auto", "auto"),
    ("Send/Return : le son d'origine reste intact, l'effet s'ajoute et sa queue continue de résonner (idéal : écho, "
     "espace, shimmer, dub). Master : l'effet traite tout le mix et s'arrête au relâchement (idéal : filtres, "
     "hachoir, crush). Auto : chaque effet sur son bus.",
     "Send/Return: the original sound stays intact, the effect is added and its tail keeps ringing (best for: echo, "
     "space, shimmer, dub). Master: the effect processes the whole mix and stops on release (best for: filters, "
     "chopper, crush). Auto: each effect on its own bus.",
     "Send/Return: il suono originale resta intatto, l'effetto si aggiunge e la sua coda continua a risuonare "
     "(ideale: eco, spazio, shimmer, dub). Master: l'effetto tratta tutto il mix e si ferma al rilascio (ideale: "
     "filtri, trancia, crush). Auto: ogni effetto sul suo bus.",
     "Send/Return: el sonido original queda intacto, el efecto se suma y su cola sigue sonando (ideal: eco, espacio, "
     "shimmer, dub). Master: el efecto procesa toda la mezcla y se detiene al soltar (ideal: filtros, cortador, "
     "crush). Auto: cada efecto en su bus."),
    ("quantité envoyée dans l'effet", "amount sent into the effect", "quantità inviata all'effetto",
     "cantidad enviada al efecto"),
    ("niveau de l'effet rendu au mix", "level of the effect returned to the mix", "livello dell'effetto reso al mix",
     "nivel del efecto devuelto a la mezcla"),
    ("0 = son d'origine, 1 = tout traité", "0 = original sound, 1 = fully processed", "0 = suono originale, 1 = tutto trattato",
     "0 = sonido original, 1 = todo procesado"),
    ("Fondu des effets (s)", "Effect fade (s)", "Dissolvenza degli effetti (s)", "Fundido de los efectos (s)"),
    ("intégration fluide : chaque effet entre et sort en douceur", "smooth blending: each effect fades in and out",
     "integrazione fluida: ogni effetto entra ed esce dolcemente", "integración fluida: cada efecto entra y sale suavemente"),
    ("🔀 Bus : {list} · fondu {fade:.2f} s", "🔀 Bus: {list} · fade {fade:.2f} s", "🔀 Bus: {list} · dissolvenza {fade:.2f} s",
     "🔀 Bus: {list} · fundido {fade:.2f} s"),

    # ---- découper
    ("Découper", "Cut", "Taglia", "Cortar"),
    ("découpe", "cuts", "tagli", "cortes"),
    ("Découpe", "Cutting", "Taglio", "Corte"),
    ("garder la sélection", "keep the selection", "tieni la selezione", "conservar la selección"),
    ("couper aux repères", "split at markers", "taglia ai segnaposto", "cortar en las marcas"),
    ("enlever la sélection", "remove the selection", "togli la selezione", "quitar la selección"),
    ("celle que tu veux couper", "the one you want to cut", "quella che vuoi tagliare", "la que quieres cortar"),
    ("Dernier fichier du Studio", "Latest Studio file", "Ultimo file dello Studio", "Último archivo del Estudio"),
    ("Choisis le passage", "Choose the part", "Scegli il passaggio", "Elige el fragmento"),
    ("au doigt, à la souris ou au clavier", "with your finger, mouse or keyboard", "con il dito, il mouse o la tastiera",
     "con el dedo, el ratón o el teclado"),
    ("Que faire ?", "What to do?", "Cosa fare?", "¿Qué hacer?"),
    ("couper aux repères = un fichier par morceau · enlever = le passage choisi disparaît, le reste est recollé",
     "split at markers = one file per piece · remove = the chosen part disappears, the rest is joined back",
     "taglia ai segnaposto = un file per pezzo · togli = il passaggio scelto sparisce, il resto viene riunito",
     "cortar en las marcas = un archivo por trozo · quitar = el fragmento elegido desaparece, el resto se vuelve a unir"),
    ("Couper", "Cut", "Taglia", "Cortar"),
    ("Morceaux créés", "Pieces created", "Pezzi creati", "Trozos creados"),
    ("Envoyer dans Enchaîner", "Send to Chain", "Invia a Concatena", "Enviar a Encadenar"),
    ("Choisis une musique ci-dessus : sa forme d’onde s’affichera ici.", "Pick a song above: its waveform will show here.",
     "Scegli una musica qui sopra: la sua forma d'onda apparirà qui.",
     "Elige una canción arriba: su forma de onda aparecerá aquí."),
    ("Écouter la sélection", "Play the selection", "Ascolta la selezione", "Escuchar la selección"),
    ("Début ici", "Start here", "Inizio qui", "Inicio aquí"),
    ("Fin ici", "End here", "Fine qui", "Fin aquí"),
    ("Repère ici", "Marker here", "Segnaposto qui", "Marca aquí"),
    ("Retirer le repère", "Remove marker", "Togli il segnaposto", "Quitar la marca"),
    ("Tout sélectionner", "Select all", "Seleziona tutto", "Seleccionar todo"),
    ("Aimant sur le temps", "Snap to the beat", "Calamita sul battito", "Imán en el tiempo"),
    ("Boucle", "Loop", "Loop", "Bucle"),
    ("Glisse sur la forme d’onde pour choisir un passage, touche-la pour y placer la lecture. Clavier : I = début, "
     "O = fin, M = repère, Suppr = retirer, flèches = ajuster (Maj = 1 s), Espace = lecture.",
     "Drag across the waveform to choose a part, tap it to move playback there. Keyboard: I = start, O = end, "
     "M = marker, Delete = remove, arrows = adjust (Shift = 1 s), Space = play.",
     "Trascina sulla forma d'onda per scegliere un passaggio, toccala per spostare lì la riproduzione. Tastiera: "
     "I = inizio, O = fine, M = segnaposto, Canc = togli, frecce = regola (Maiusc = 1 s), Spazio = play.",
     "Arrastra sobre la forma de onda para elegir un fragmento, tócala para llevar ahí la reproducción. Teclado: "
     "I = inicio, O = fin, M = marca, Supr = quitar, flechas = ajustar (Mayús = 1 s), Espacio = reproducir."),
    ("Aucune musique chargée.", "No song loaded.", "Nessuna musica caricata.", "Ninguna canción cargada."),
    ("Sélection : {a} → {b} ({d:.1f} s)", "Selection: {a} → {b} ({d:.1f} s)", "Selezione: {a} → {b} ({d:.1f} s)",
     "Selección: {a} → {b} ({d:.1f} s)"),
    ("{n} repère(s) → {p} morceaux", "{n} marker(s) → {p} pieces", "{n} segnaposto → {p} pezzi",
     "{n} marca(s) → {p} trozos"),
    ("Aucun fichier créé dans le Studio audio pour l'instant.", "No file created in the Audio studio yet.",
     "Nessun file creato nello Studio audio per ora.", "Todavía no hay archivos creados en el Estudio de audio."),
    ("{n} fichier(s) créé(s)", "{n} file(s) created", "{n} file creati", "{n} archivo(s) creado(s)"),
    ("Coupe d'abord la musique.", "Cut the song first.", "Prima taglia la musica.", "Corta primero la canción."),
    ("Choisis d'abord une musique à découper.", "Pick a song to cut first.", "Scegli prima una musica da tagliare.",
     "Elige primero una canción para cortar."),
    ("Sélection trop courte : choisis un début et une fin plus écartés.",
     "Selection too short: pick a start and an end further apart.",
     "Selezione troppo corta: scegli un inizio e una fine più distanti.",
     "Selección demasiado corta: elige un inicio y un fin más separados."),
    ("La sélection couvre tout le morceau : il ne resterait rien.",
     "The selection covers the whole track: nothing would be left.",
     "La selezione copre tutto il brano: non resterebbe niente.",
     "La selección cubre toda la pista: no quedaría nada."),
    ("✂️ Passage enlevé ({a} → {b}) : il reste {dur:.1f} s", "✂️ Part removed ({a} → {b}): {dur:.1f} s left",
     "✂️ Passaggio tolto ({a} → {b}): restano {dur:.1f} s", "✂️ Fragmento quitado ({a} → {b}): quedan {dur:.1f} s"),
    ("⚠ Aucun repère : la sélection est gardée en un seul morceau.", "⚠ No marker: the selection is kept as one piece.",
     "⚠ Nessun segnaposto: la selezione resta un unico pezzo.",
     "⚠ Ninguna marca: la selección se conserva en un solo trozo."),
    ("✂️ Sélection gardée ({a} → {b}) : {dur:.1f} s", "✂️ Selection kept ({a} → {b}): {dur:.1f} s",
     "✂️ Selezione tenuta ({a} → {b}): {dur:.1f} s", "✂️ Selección conservada ({a} → {b}): {dur:.1f} s"),
    ("✂️ {n} morceaux coupés aux repères", "✂️ {n} pieces split at the markers", "✂️ {n} pezzi tagliati ai segnaposto",
     "✂️ {n} trozos cortados en las marcas"),
    ("🎧 Platine DJ : {n} instrument(s), {m} effet(s), {dur:.1f} s", "🎧 DJ deck: {n} instrument(s), {m} effect(s), {dur:.1f} s",
     "🎧 Console DJ: {n} strumento/i, {m} effetto/i, {dur:.1f} s",
     "🎧 Mesa de DJ: {n} instrumento(s), {m} efecto(s), {dur:.1f} s"),
    ("Chaque ligne se modifie : rôle, volume, moment où la piste commence, boucle. Clique sur une ligne pour l'écouter.",
     "Every row is editable: role, volume, when the track starts, loop. Click a row to listen to it.",
     "Ogni riga si modifica: ruolo, volume, momento in cui la traccia inizia, loop. Clicca su una riga per ascoltarla.",
     "Cada fila se puede editar: función, volumen, momento en que empieza la pista, bucle. Haz clic en una fila para "
     "escucharla."),
    ("Écoute de la piste choisie", "Listen to the chosen track", "Ascolto della traccia scelta",
     "Escucha de la pista elegida"),
    ("Transitions", "Transitions", "Transizioni", "Transiciones"),
    ("touche un pad", "tap a pad", "tocca un pad", "toca un pad"),
    ("transition donnée aux nouveaux morceaux · écho, back spin et freinage = effets de relâchement du morceau qui se "
     "termine",
     "transition given to new tracks · echo, back spin and brake = release effects on the track that ends",
     "transizione data ai nuovi brani · eco, back spin e frenata = effetti di rilascio del brano che finisce",
     "transición para las pistas nuevas · eco, back spin y frenado = efectos de salida de la pista que termina"),
    ("Appliquer ce pad à toutes les pistes", "Apply this pad to every track", "Applica questo pad a tutte le tracce",
     "Aplicar este pad a todas las pistas"),
    ("fondu et isolateur ; 0 = coupe sèche", "fade and isolator; 0 = hard cut", "dissolvenza e isolatore; 0 = taglio netto",
     "fundido y aislador; 0 = corte seco"),
    ("Transitions sur le rythme", "Beat-matched transitions", "Transizioni a tempo", "Transiciones al ritmo"),
    ("fondus en mesures entières, échos et spins pile sur un temps, et le morceau suivant démarre sur son temps",
     "fades in whole bars, echoes and spins right on a beat, and the next track starts on its own beat",
     "dissolvenze in battute intere, eco e spin esattamente su un battito, e il brano successivo parte sul suo battito",
     "fundidos en compases enteros, ecos y spins justo en un tiempo, y la pista siguiente arranca en su tiempo"),

    # ---- mode viral
    ("Mode viral (en un clic)", "Viral mode (one click)", "Modalità virale (in un clic)", "Modo viral (en un clic)"),
    ("Règle tout le projet façon Short viral. Ensuite, chaque réglage reste modifiable à la main.",
     "Sets up the whole project like a viral Short. Every setting stays editable by hand afterwards.",
     "Imposta tutto il progetto in stile Short virale. Poi ogni impostazione resta modificabile a mano.",
     "Ajusta todo el proyecto al estilo Short viral. Después, cada ajuste sigue siendo editable a mano."),
    ("Accroche (2 premières secondes)", "Hook (first 2 seconds)", "Gancio (primi 2 secondi)",
     "Gancho (primeros 2 segundos)"),
    ("Attends la fin… 😱", "Wait for the end… 😱", "Aspetta la fine… 😱", "Espera al final… 😱"),
    ("Inclure", "Include", "Includi", "Incluir"),
    ("Appliquer le mode viral", "Apply viral mode", "Applica la modalità virale", "Aplicar el modo viral"),
    ("format vertical 9:16", "vertical 9:16 format", "formato verticale 9:16", "formato vertical 9:16"),
    ("sous-titres karaoké", "karaoke subtitles", "sottotitoli karaoke", "subtítulos karaoke"),
    ("couper les silences", "cut silences", "taglia i silenzi", "cortar los silencios"),
    ("zoom alterné + whoosh", "alternating zoom + whoosh", "zoom alternato + whoosh", "zoom alterno + whoosh"),
    ("musique énergique au rythme", "energetic music on the beat", "musica energica a tempo",
     "música enérgica al ritmo"),
    ("sticker S'abonner à la fin", "Subscribe sticker at the end", "sticker Iscriviti alla fine",
     "sticker Suscribirse al final"),
    ("format 9:16", "9:16 format", "formato 9:16", "formato 9:16"),
    ("accroche animée", "animated hook", "gancio animato", "gancho animado"),
    ("sous-titres : installe Whisper (pip install faster-whisper) ou écris le texte dans « Sous-titres → Texte »",
     "subtitles: install Whisper (pip install faster-whisper) or write the text in “Subtitles → Text”",
     "sottotitoli: installa Whisper (pip install faster-whisper) o scrivi il testo in « Sottotitoli → Testo »",
     "subtítulos: instala Whisper (pip install faster-whisper) o escribe el texto en «Subtítulos → Texto»"),
    ("silences coupés", "silences cut", "silenzi tagliati", "silencios cortados"),
    ("zoom alterné + whoosh à chaque coupe", "alternating zoom + whoosh on every cut",
     "zoom alternato + whoosh a ogni taglio", "zoom alterno + whoosh en cada corte"),
    ("musique au rythme", "music on the beat", "musica a tempo", "música al ritmo"),
    ("sticker S'abonner (3 dernières secondes)", "Subscribe sticker (last 3 seconds)",
     "sticker Iscriviti (ultimi 3 secondi)", "sticker Suscribirse (últimos 3 segundos)"),
    ("⚡ Mode viral appliqué : {done}.", "⚡ Viral mode applied: {done}.", "⚡ Modalità virale applicata: {done}.",
     "⚡ Modo viral aplicado: {done}."),
    ("Lance l'aperçu rapide pour voir le résultat.", "Run the quick preview to see the result.",
     "Avvia l'anteprima rapida per vedere il risultato.", "Lanza la vista previa rápida para ver el resultado."),

    # ---- Screen Record (enregistrement d'écran)
    ("Enregistrer l'écran", "Screen Record", "Registra schermo", "Grabar pantalla"),
    ("Screen Record est un enregistreur d'écran gratuit qui capture ton écran, ta voix, ton visage et le son "
     "de l'ordinateur — pour partager tout de suite après chaque enregistrement.",
     "Screen Record is a free screen recorder that captures your screen, voice, face and system audio — "
     "so you can share instantly after every recording.",
     "Screen Record è un registratore dello schermo gratuito che cattura schermo, voce, volto e audio del "
     "computer, così puoi condividere subito dopo ogni registrazione.",
     "Screen Record es un grabador de pantalla gratuito que captura tu pantalla, tu voz, tu cara y el audio del "
     "ordenador, para que compartas al instante después de cada grabación."),
    ("Gratuit · 100 % local · sans filigrane", "Free · 100% local · no watermark",
     "Gratis · 100% locale · senza filigrana", "Gratis · 100 % local · sin marca de agua"),
    ("Enregistrement d'écran rapide et simple", "Fast and easy screen recording",
     "Registrazione dello schermo facile e veloce", "Grabación de pantalla rápida y sencilla"),
    ("Un écran entier ou une seule fenêtre, en un clic.", "A whole screen or a single window, in one click.",
     "Uno schermo intero o una sola finestra, con un clic.", "Una pantalla completa o una sola ventana, con un clic."),
    ("Ta voix au micro", "Record your voice from the microphone", "Registra la tua voce dal microfono",
     "Graba tu voz con el micrófono"),
    ("Commente pendant que tu enregistres.", "Narrate while you record.", "Commenta mentre registri.",
     "Comenta mientras grabas."),
    ("Le son de l'ordinateur", "Capture computer system audio", "Cattura l'audio del computer",
     "Captura el audio del ordenador"),
    ("Vidéos, musique, sons des applications : sans câble virtuel ni réglage.",
     "Videos, music, app sounds: no virtual cable, no setup.",
     "Video, musica, suoni delle app: senza cavo virtuale né configurazione.",
     "Vídeos, música, sonidos de las apps: sin cable virtual ni configuración."),
    ("Ta webcam", "Record from your webcam", "Registra dalla webcam", "Graba con tu webcam"),
    ("Ton visage dans un médaillon rond, dans le coin de ton choix.",
     "Your face in a round bubble, in the corner you choose.",
     "Il tuo volto in un riquadro rotondo, nell'angolo che preferisci.",
     "Tu cara en un círculo, en la esquina que elijas."),
    ("Sans filigrane ni limite de durée", "No watermark and no time limit",
     "Nessuna filigrana e nessun limite di tempo", "Sin marca de agua ni límite de tiempo"),
    ("Tes vidéos t'appartiennent : enregistre aussi longtemps que tu veux.",
     "Your videos are yours: record as long as you want.",
     "I video sono tuoi: registra per tutto il tempo che vuoi.",
     "Tus vídeos son tuyos: graba todo el tiempo que quieras."),
    ("Léger, sans ralentissement", "Lightweight app (no lag)", "App leggera (nessun rallentamento)",
     "App ligera (sin retrasos)"),
    ("Encodage par la carte graphique quand elle le permet.", "Hardware encoding on your graphics card when available.",
     "Codifica con la scheda video quando è disponibile.", "Codificación con la tarjeta gráfica cuando está disponible."),
    ("Partage instantané par lien", "Instant sharing via link", "Condivisione immediata tramite link",
     "Compartir al instante con un enlace"),
    ("Un lien à ouvrir sur un téléphone ou un autre ordinateur de ton réseau Wi-Fi.",
     "A link to open on a phone or another computer on your Wi-Fi network.",
     "Un link da aprire su un telefono o un altro computer della tua rete Wi-Fi.",
     "Un enlace para abrir en un móvil u otro ordenador de tu red Wi-Fi."),
    ("Zoom automatique sur les clics", "Automatic zoom on clicks", "Zoom automatico sui clic",
     "Zoom automático en los clics"),
    ("L'image s'approche de chaque clic, suit le curseur, puis revient.",
     "The view zooms in on every click, follows the cursor, then zooms back out.",
     "L'inquadratura si avvicina a ogni clic, segue il cursore, poi torna indietro.",
     "La imagen se acerca a cada clic, sigue el cursor y luego vuelve."),
    ("Coupe automatique", "Automatic trimming", "Taglio automatico", "Recorte automático"),
    ("Le début, la fin et les longues pauses sont retirés tout seuls.",
     "The start, the end and long pauses are removed for you.",
     "L'inizio, la fine e le pause lunghe vengono tolti in automatico.",
     "El inicio, el final y las pausas largas se eliminan solos."),
    ("Version Short 9:16", "9:16 Short version", "Versione Short 9:16", "Versión Short 9:16"),
    ("Cadre qui suit le curseur, écran entier sur fond flou, ou écran en haut et webcam en bas : prête pour Shorts, "
     "Reels et TikTok.",
     "A frame that follows the cursor, the full screen on a blurred background, or the screen on top and the webcam "
     "below: ready for Shorts, Reels and TikTok.",
     "Inquadratura che segue il cursore, schermo intero su sfondo sfocato, oppure schermo sopra e webcam sotto: pronta "
     "per Shorts, Reels e TikTok.",
     "Encuadre que sigue el cursor, pantalla completa sobre fondo desenfocado, o pantalla arriba y webcam abajo: lista "
     "para Shorts, Reels y TikTok."),
    ("Que veux-tu enregistrer ?", "What do you want to record?", "Cosa vuoi registrare?", "¿Qué quieres grabar?"),
    ("Son et webcam", "Sound and webcam", "Audio e webcam", "Sonido y webcam"),
    ("Montage automatique", "Automatic editing", "Montaggio automatico", "Edición automática"),
    ("Montage automatique…", "Automatic editing…", "Montaggio automatico…", "Edición automática…"),
    ("Montage automatique… {pct} %", "Automatic editing… {pct}%", "Montaggio automatico… {pct}%",
     "Edición automática… {pct} %"),
    ("Ta vidéo", "Your video", "Il tuo video", "Tu vídeo"),
    ("dossier sorties/screen_record", "sorties/screen_record folder", "cartella sorties/screen_record",
     "carpeta sorties/screen_record"),
    ("Partager par lien", "Share via link", "Condividi tramite link", "Compartir con un enlace"),
    ("Micro", "Microphone", "Microfono", "Micrófono"),
    ("Son de l'ordinateur", "Computer audio", "Audio del computer", "Audio del ordenador"),
    ("Webcam", "Webcam", "Webcam", "Webcam"),
    ("Position de la webcam", "Webcam position", "Posizione della webcam", "Posición de la webcam"),
    ("Aucun", "None", "Nessuno", "Ninguno"),
    ("Aucune", "None", "Nessuna", "Ninguna"),
    ("Actualiser les listes", "Refresh lists", "Aggiorna gli elenchi", "Actualizar las listas"),
    ("Force du zoom", "Zoom strength", "Intensità dello zoom", "Intensidad del zoom"),
    ("Coupe automatique (début, fin, longues pauses)", "Automatic trimming (start, end, long pauses)",
     "Taglio automatico (inizio, fine, pause lunghe)", "Recorte automático (inicio, final, pausas largas)"),
    ("Créer aussi la version 9:16 (Shorts, Reels, TikTok)", "Also create the 9:16 version (Shorts, Reels, TikTok)",
     "Crea anche la versione 9:16 (Shorts, Reels, TikTok)", "Crear también la versión 9:16 (Shorts, Reels, TikTok)"),
    ("Images par seconde", "Frames per second", "Fotogrammi al secondo", "Fotogramas por segundo"),
    ("Démarrer l'enregistrement", "Start recording", "Avvia la registrazione", "Iniciar la grabación"),
    ("Arrêter", "Stop", "Ferma", "Detener"),
    ("Avant de démarrer, ferme ce qui ne doit pas être vu (e-mails, mots de passe, notifications).",
     "Before you start, close anything that should not be seen (emails, passwords, notifications).",
     "Prima di iniziare, chiudi ciò che non deve vedersi (email, password, notifiche).",
     "Antes de empezar, cierra lo que no deba verse (correos, contraseñas, notificaciones)."),
    ("Les vidéos protégées (Netflix…) apparaissent en noir : c'est une protection du système.",
     "Protected videos (Netflix…) appear black: this is a system protection.",
     "I video protetti (Netflix…) appaiono neri: è una protezione del sistema.",
     "Los vídeos protegidos (Netflix…) aparecen en negro: es una protección del sistema."),
    ("Protège ta vie privée", "Protect your privacy", "Proteggi la tua privacy", "Protege tu privacidad"),
    ("Ok, démarrer", "Ok, start", "Ok, avvia", "Ok, empezar"),
    ("Mes enregistrements", "My recordings", "Le mie registrazioni", "Mis grabaciones"),
    ("Ouvrir le dossier", "Open folder", "Apri la cartella", "Abrir la carpeta"),
    ("Créer un lien de partage", "Create a share link", "Crea un link di condivisione", "Crear un enlace para compartir"),
    ("Arrêter le partage", "Stop sharing", "Interrompi la condivisione", "Dejar de compartir"),
    ("Lien de partage", "Share link", "Link di condivisione", "Enlace para compartir"),
    ("Ouvre ce lien sur un téléphone ou un ordinateur connecté au même Wi-Fi. La première fois, Windows peut "
     "demander d'autoriser l'accès au réseau : choisis « Réseaux privés ». Le lien fonctionne tant que MSV est ouvert.",
     "Open this link on a phone or computer connected to the same Wi-Fi. The first time, Windows may ask you to "
     "allow network access: choose “Private networks”. The link works as long as MSV is open.",
     "Apri questo link su un telefono o un computer collegato allo stesso Wi-Fi. La prima volta Windows può "
     "chiedere di consentire l'accesso alla rete: scegli « Reti private ». Il link funziona finché MSV è aperto.",
     "Abre este enlace en un móvil u ordenador conectado a la misma Wi-Fi. La primera vez, Windows puede pedir "
     "que permitas el acceso a la red: elige «Redes privadas». El enlace funciona mientras MSV esté abierto."),
    ("⏳ Départ dans {n} s : affiche la fenêtre ou la page à enregistrer.",
     "⏳ Starting in {n} s: bring up the window or page you want to record.",
     "⏳ Si parte tra {n} s: mostra la finestra o la pagina da registrare.",
     "⏳ Empieza en {n} s: muestra la ventana o la página que quieres grabar."),
    ("🔴 Enregistrement en cours · {time}", "🔴 Recording · {time}", "🔴 Registrazione in corso · {time}",
     "🔴 Grabando · {time}"),
    ("Pour arrêter : bouton « Arrêter » dans MSV, ou {key} depuis n'importe quelle fenêtre.",
     "To stop: the “Stop” button in MSV, or {key} from any window.",
     "Per fermare: pulsante « Ferma » in MSV, oppure {key} da qualsiasi finestra.",
     "Para detener: botón «Detener» en MSV, o {key} desde cualquier ventana."),
    ("Prêt. Choisis ce que tu veux enregistrer, puis clique sur « Démarrer l'enregistrement ».",
     "Ready. Choose what you want to record, then click “Start recording”.",
     "Pronto. Scegli cosa vuoi registrare, poi clicca su « Avvia la registrazione ».",
     "Listo. Elige qué quieres grabar y haz clic en «Iniciar la grabación»."),
    ("✅ Vidéo prête : {dur}.", "✅ Video ready: {dur}.", "✅ Video pronto: {dur}.", "✅ Vídeo listo: {dur}."),
    ("{cut} retirées (début, fin, pauses).", "{cut} removed (start, end, pauses).",
     "{cut} tolti (inizio, fine, pause).", "{cut} eliminados (inicio, final, pausas)."),
    ("{n} zooms automatiques.", "{n} automatic zooms.", "{n} zoom automatici.", "{n} zooms automáticos."),
    ("Choisis d'abord un enregistrement.", "Choose a recording first.", "Scegli prima una registrazione.",
     "Elige primero una grabación."),
    ("principal", "main", "principale", "principal"),
    ("Écran {n}", "Screen {n}", "Schermo {n}", "Pantalla {n}"),
    ("Choisis un écran ou une fenêtre.", "Choose a screen or a window.", "Scegli uno schermo o una finestra.",
     "Elige una pantalla o una ventana."),
    ("Clique sur « Actualiser les listes » si la liste est vide.", "Click “Refresh lists” if the list is empty.",
     "Clicca su « Aggiorna gli elenchi » se l'elenco è vuoto.", "Haz clic en «Actualizar las listas» si la lista está vacía."),
    ("La fenêtre choisie est fermée ou réduite.", "The chosen window is closed or minimized.",
     "La finestra scelta è chiusa o ridotta a icona.", "La ventana elegida está cerrada o minimizada."),
    ("Ouvre-la à l'écran, puis clique sur « Actualiser les listes ».",
     "Bring it up on screen, then click “Refresh lists”.",
     "Aprila sullo schermo, poi clicca su « Aggiorna gli elenchi ».",
     "Ábrela en pantalla y haz clic en «Actualizar las listas»."),
    ("L'enregistrement d'écran fonctionne sous Windows, Linux (X11) et macOS.",
     "Screen recording works on Windows, Linux (X11) and macOS.",
     "La registrazione dello schermo funziona su Windows, Linux (X11) e macOS.",
     "La grabación de pantalla funciona en Windows, Linux (X11) y macOS."),
    ("Un enregistrement est déjà en cours.", "A recording is already in progress.",
     "Una registrazione è già in corso.", "Ya hay una grabación en curso."),
    ("{source} indisponible : {msg}", "{source} unavailable: {msg}", "{source} non disponibile: {msg}",
     "{source} no disponible: {msg}"),
    ("La capture de l'écran n'a pas démarré : {msg}", "Screen capture did not start: {msg}",
     "La cattura dello schermo non è partita: {msg}", "La captura de pantalla no se inició: {msg}"),
    ("Arrêt de l'enregistrement…", "Stopping the recording…", "Arresto della registrazione…",
     "Deteniendo la grabación…"),
    ("Les fichiers bruts sont conservés ici : {path}", "The raw files are kept here: {path}",
     "I file grezzi sono conservati qui: {path}", "Los archivos sin editar se guardan aquí: {path}"),
    ("Rien n'a été enregistré.", "Nothing was recorded.", "Non è stato registrato nulla.", "No se grabó nada."),
    ("Recommence : l'enregistrement a été arrêté trop tôt.", "Try again: the recording was stopped too early.",
     "Riprova: la registrazione è stata fermata troppo presto.", "Vuelve a intentarlo: la grabación se detuvo demasiado pronto."),
    ("Recherche des pauses…", "Looking for pauses…", "Ricerca delle pause…", "Buscando pausas…"),
    ("Export simple de secours…", "Simple backup export…", "Esportazione semplice di riserva…",
     "Exportación simple de respaldo…"),
    ("Terminé.", "Done.", "Fatto.", "Listo."),
    ("Aucun réseau détecté.", "No network detected.", "Nessuna rete rilevata.", "No se detectó ninguna red."),
    ("Connecte l'ordinateur au Wi-Fi ou à la box pour partager.",
     "Connect the computer to Wi-Fi or to your router to share.",
     "Collega il computer al Wi-Fi o al router per condividere.",
     "Conecta el ordenador a la Wi-Fi o al router para compartir."),
    ("Informations système", "System information", "Informazioni di sistema", "Información del sistema"),
    # ---- Screen Record : pause, mises en page 9:16, réduction du bruit
    ("Pause et reprise", "Pause and resume", "Pausa e ripresa", "Pausa y reanudación"),
    ("Mets en pause quand tu veux : rien n'est enregistré pendant la pause.",
     "Pause whenever you like: nothing is recorded during the pause.",
     "Metti in pausa quando vuoi: durante la pausa non viene registrato niente.",
     "Pausa cuando quieras: no se graba nada durante la pausa."),
    ("Réduction du bruit", "Noise reduction", "Riduzione del rumore", "Reducción de ruido"),
    ("Ventilateur, clavier, souffle : ta voix reste, le bruit part.",
     "Fan, keyboard, hiss: your voice stays, the noise goes.",
     "Ventola, tastiera, fruscio: la tua voce resta, il rumore se ne va.",
     "Ventilador, teclado, soplido: tu voz se queda, el ruido se va."),
    ("Pause : bouton « Pause », ou {key}.", "Pause: “Pause” button, or {key}.",
     "Pausa: pulsante «Pausa», oppure {key}.", "Pausa: botón «Pausa», o {key}."),
    ("⏸️ En pause · {time} enregistrées. Rien n'est capturé pendant la pause.",
     "⏸️ Paused · {time} recorded. Nothing is captured during the pause.",
     "⏸️ In pausa · {time} registrati. Durante la pausa non viene catturato niente.",
     "⏸️ En pausa · {time} grabados. No se captura nada durante la pausa."),
    ("Pour reprendre : bouton « Reprendre » (départ dans 3 s), ou {key} (tout de suite).",
     "To resume: “Resume” button (starts in 3 s), or {key} (right away).",
     "Per riprendere: pulsante «Riprendi» (parte tra 3 s), oppure {key} (subito).",
     "Para reanudar: botón «Reanudar» (empieza en 3 s), o {key} (al instante)."),
    ("⏳ Reprise dans {n} s : affiche la fenêtre ou la page à enregistrer.",
     "⏳ Resuming in {n} s: bring up the window or page to record.",
     "⏳ Si riprende tra {n} s: mostra la finestra o la pagina da registrare.",
     "⏳ Se reanuda en {n} s: muestra la ventana o la página que quieres grabar."),
    ("Reprendre", "Resume", "Riprendi", "Reanudar"),
    ("Pause", "Pause", "Pausa", "Pausa"),
    ("Réduction du bruit du micro", "Microphone noise reduction", "Riduzione del rumore del microfono",
     "Reducción de ruido del micrófono"),
    ("Mise en page 9:16", "9:16 layout", "Impaginazione 9:16", "Diseño 9:16"),
    ("sans webcam, « écran en haut + webcam en bas » devient « écran entier + fond flou »",
     "without a webcam, “screen on top + webcam below” becomes “full screen + blurred background”",
     "senza webcam, «schermo sopra + webcam sotto» diventa «schermo intero + sfondo sfocato»",
     "sin webcam, «pantalla arriba + webcam abajo» pasa a ser «pantalla completa + fondo desenfocado»"),
    ("suivre le curseur", "follow the cursor", "segui il cursore", "seguir el cursor"),
    ("écran entier + fond flou", "full screen + blurred background", "schermo intero + sfondo sfocato",
     "pantalla completa + fondo desenfocado"),
    ("écran en haut + webcam en bas", "screen on top + webcam below", "schermo sopra + webcam sotto",
     "pantalla arriba + webcam abajo"),
    ("légère", "light", "leggera", "ligera"),
    ("forte (voix)", "strong (voice)", "forte (voce)", "fuerte (voz)"),
    ("Réduction du bruit (son des clips)", "Noise reduction (clip audio)", "Riduzione del rumore (audio delle clip)",
     "Reducción de ruido (audio de los clips)"),
    ("légère : souffle constant ; forte : garde la voix et retire ventilateur, clavier, climatisation",
     "light: constant hiss; strong: keeps the voice and removes fan, keyboard, air conditioning",
     "leggera: fruscio costante; forte: tiene la voce e toglie ventola, tastiera, condizionatore",
     "ligera: soplido constante; fuerte: conserva la voz y quita ventilador, teclado, aire acondicionado"),
    ("Réduire le bruit", "Reduce noise", "Riduci il rumore", "Reducir el ruido"),
    ("souffle, ventilateur, clavier", "hiss, fan, keyboard", "fruscio, ventola, tastiera", "soplido, ventilador, teclado"),
    ("Niveau", "Level", "Livello", "Nivel"),
    ("Extrait à partir de (s)", "Sample from (s)", "Estratto a partire da (s)", "Fragmento desde (s)"),
    ("Écouter 10 s avant / après", "Listen to 10 s before / after", "Ascolta 10 s prima / dopo",
     "Escuchar 10 s antes / después"),
    ("Nettoyer le fichier", "Clean the file", "Pulisci il file", "Limpiar el archivo"),
    ("Avant", "Before", "Prima", "Antes"),
    ("Après", "After", "Dopo", "Después"),
    ("Vidéo : l'image est copiée sans perte, seul le son est nettoyé (MP4). Audio seul : fichier WAV. Pour un montage, "
     "choisis plutôt « Réduction du bruit » dans Réglages → Audio.",
     "Video: the picture is copied losslessly, only the sound is cleaned (MP4). Audio only: WAV file. For an edit, "
     "use “Noise reduction” in Settings → Audio instead.",
     "Video: l'immagine viene copiata senza perdita, viene pulito solo l'audio (MP4). Solo audio: file WAV. Per un "
     "montaggio, usa invece «Riduzione del rumore» in Impostazioni → Audio.",
     "Vídeo: la imagen se copia sin pérdida, solo se limpia el sonido (MP4). Solo audio: archivo WAV. Para un montaje, "
     "usa mejor «Reducción de ruido» en Ajustes → Audio."),
    ("🔇 Réduction du bruit : {level}", "🔇 Noise reduction: {level}", "🔇 Riduzione del rumore: {level}",
     "🔇 Reducción de ruido: {level}"),
    ("Assemblage des morceaux…", "Joining the parts…", "Unione delle parti…", "Uniendo las partes…"),
    ("Choisis un niveau de réduction du bruit.", "Choose a noise reduction level.",
     "Scegli un livello di riduzione del rumore.", "Elige un nivel de reducción de ruido."),
    ("Ce fichier n'a pas de son : {name}", "This file has no sound: {name}", "Questo file non ha audio: {name}",
     "Este archivo no tiene sonido: {name}"),
    # ---- Screen Record sous Linux et macOS
    ("Le FFmpeg trouvé ne sait pas capturer l'écran ou le son ({what}).",
     "The FFmpeg found cannot capture the screen or sound ({what}).",
     "L'FFmpeg trovato non sa catturare lo schermo o l'audio ({what}).",
     "El FFmpeg encontrado no sabe capturar la pantalla o el sonido ({what})."),
    ("Installe FFmpeg avec ton gestionnaire de paquets : « sudo apt install ffmpeg » (Linux) ou « brew install ffmpeg » "
     "(Mac), puis relance MSV.",
     "Install FFmpeg with your package manager: “sudo apt install ffmpeg” (Linux) or “brew install ffmpeg” (Mac), "
     "then restart MSV.",
     "Installa FFmpeg con il gestore dei pacchetti: «sudo apt install ffmpeg» (Linux) o «brew install ffmpeg» (Mac), "
     "poi riavvia MSV.",
     "Instala FFmpeg con tu gestor de paquetes: «sudo apt install ffmpeg» (Linux) o «brew install ffmpeg» (Mac) y "
     "vuelve a abrir MSV."),
    ("Sous Wayland, l'enregistrement d'écran n'est pas encore possible.",
     "Screen recording is not possible under Wayland yet.",
     "Con Wayland la registrazione dello schermo non è ancora possibile.",
     "Con Wayland todavía no se puede grabar la pantalla."),
    ("À l'écran de connexion, choisis une session « Xorg » (par exemple « Ubuntu sur Xorg »), puis relance MSV.",
     "On the login screen, choose an “Xorg” session (for example “Ubuntu on Xorg”), then restart MSV.",
     "Nella schermata di accesso scegli una sessione «Xorg» (ad esempio «Ubuntu su Xorg»), poi riavvia MSV.",
     "En la pantalla de inicio de sesión, elige una sesión «Xorg» (por ejemplo «Ubuntu en Xorg») y vuelve a abrir "
     "MSV."),
    ("Aucun affichage X11 trouvé (variable DISPLAY vide).", "No X11 display found (DISPLAY variable is empty).",
     "Nessuno schermo X11 trovato (variabile DISPLAY vuota).",
     "No se encontró ninguna pantalla X11 (variable DISPLAY vacía)."),
    ("Lance MSV depuis ta session de bureau, pas depuis une console sans affichage.",
     "Start MSV from your desktop session, not from a console without a display.",
     "Avvia MSV dalla sessione desktop, non da una console senza schermo.",
     "Abre MSV desde tu sesión de escritorio, no desde una consola sin pantalla."),
    ("Micro par défaut", "Default microphone", "Microfono predefinito", "Micrófono predeterminado"),
    ("Son de l'ordinateur (sortie par défaut)", "Computer audio (default output)",
     "Audio del computer (uscita predefinita)", "Audio del ordenador (salida predeterminada)"),
    ("le son n'a pas démarré", "the sound did not start", "l'audio non è partito", "el sonido no se inició"),
    ("Souris et clavier non suivis (zoom et coupe automatiques limités) : {msg}",
     "Mouse and keyboard not tracked (automatic zoom and trimming limited): {msg}",
     "Mouse e tastiera non rilevati (zoom e taglio automatici limitati): {msg}",
     "Ratón y teclado sin seguimiento (zoom y recorte automáticos limitados): {msg}"),
    ("sur Mac : installe BlackHole (gratuit) et envoie le son vers lui, sinon cette liste reste vide",
     "on Mac: install BlackHole (free) and send the sound to it, otherwise this list stays empty",
     "su Mac: installa BlackHole (gratuito) e invia l'audio a BlackHole, altrimenti l'elenco resta vuoto",
     "en Mac: instala BlackHole (gratis) y envía el sonido a él; si no, esta lista queda vacía"),
    ("Mac : autorise MSV (ou le Terminal) dans Réglages Système → Confidentialité et sécurité : « Enregistrement de "
     "l'écran », « Micro », « Caméra », et « Surveillance de l'entrée » pour les raccourcis. Sur un portable, les "
     "touches F8 / F9 se tapent avec fn.",
     "Mac: allow MSV (or Terminal) in System Settings → Privacy & Security: “Screen Recording”, “Microphone”, "
     "“Camera”, and “Input Monitoring” for the shortcuts. On a laptop, press F8 / F9 together with fn.",
     "Mac: autorizza MSV (o il Terminale) in Impostazioni di Sistema → Privacy e sicurezza: «Registrazione schermo», "
     "«Microfono», «Fotocamera» e «Monitoraggio input» per le scorciatoie. Su un portatile, F8 / F9 si premono con fn.",
     "Mac: autoriza MSV (o el Terminal) en Ajustes del Sistema → Privacidad y seguridad: «Grabación de pantalla», "
     "«Micrófono», «Cámara» y «Monitorización de entrada» para los atajos. En un portátil, F8 / F9 se pulsan con fn."),
    ("Linux : fonctionne dans une session X11 (Xorg). Sous Wayland, choisis « Xorg » à l'écran de connexion.",
     "Linux: works in an X11 (Xorg) session. Under Wayland, choose “Xorg” on the login screen.",
     "Linux: funziona in una sessione X11 (Xorg). Con Wayland, scegli «Xorg» nella schermata di accesso.",
     "Linux: funciona en una sesión X11 (Xorg). Con Wayland, elige «Xorg» en la pantalla de inicio de sesión."),
    # ---- Découper en scènes (core/scenecut.py)
    ("Scènes et écran partagé", "Scenes & split screen", "Scene e schermo diviso", "Escenas y pantalla dividida"),
    ("Découper en scènes", "Split into scenes", "Dividi in scene", "Dividir en escenas"),
    ("Vidéo à découper", "Video to split", "Video da dividere", "Vídeo que dividir"),
    ("Comment découper ?", "How to split?", "Come dividere?", "¿Cómo dividir?"),
    ("changements de plan", "shot changes", "cambi di inquadratura", "cambios de plano"),
    ("pauses dans la parole", "pauses in speech", "pause nel parlato", "pausas al hablar"),
    ("toutes les N secondes", "every N seconds", "ogni N secondi", "cada N segundos"),
    ("pauses dans la parole : quelqu'un parle sans changement de plan (tutoriel, podcast, discours) · toutes les N "
     "secondes : morceaux de durée fixe",
     "pauses in speech: someone talks without shot changes (tutorial, podcast, speech) · every N seconds: "
     "fixed-length pieces",
     "pause nel parlato: qualcuno parla senza cambi di inquadratura (tutorial, podcast, discorso) · ogni N secondi: "
     "pezzi di durata fissa",
     "pausas al hablar: alguien habla sin cambios de plano (tutorial, pódcast, discurso) · cada N segundos: "
     "trozos de duración fija"),
    ("Durée de chaque scène (s)", "Length of each scene (s)", "Durata di ogni scena (s)",
     "Duración de cada escena (s)"),
    ("Placer chaque coupure sur la pause la plus proche", "Move each cut to the nearest pause",
     "Sposta ogni taglio sulla pausa più vicina", "Mover cada corte a la pausa más cercana"),
    ("évite de couper au milieu d'un mot ; décoché : coupures exactes",
     "avoids cutting in the middle of a word; unchecked: exact cuts",
     "evita di tagliare a metà parola; senza spunta: tagli esatti",
     "evita cortar en mitad de una palabra; sin marcar: cortes exactos"),
    ("Unir les scènes plus courtes que (s)", "Merge scenes shorter than (s)", "Unisci le scene più corte di (s)",
     "Unir las escenas más cortas que (s)"),
    ("ne découpe pas : une scène trop courte rejoint la précédente",
     "does not split: a scene that is too short joins the previous one",
     "non divide: una scena troppo corta si unisce alla precedente",
     "no divide: una escena demasiado corta se une a la anterior"),
    ("{n} coupures trouvées, mais les scènes duraient moins de {s:g} s et ont été regroupées : baisse « Unir les "
     "scènes plus courtes que ».",
     "{n} cuts found, but the scenes were shorter than {s:g} s and were merged: lower “Merge scenes shorter than”.",
     "{n} tagli trovati, ma le scene duravano meno di {s:g} s e sono state unite: abbassa «Unisci le scene più "
     "corte di».",
     "{n} cortes encontrados, pero las escenas duraban menos de {s:g} s y se han unido: baja «Unir las escenas más "
     "cortas que»."),
    ("Aucune pause trouvée : la parole est continue ou couverte par une musique. Essaie « toutes les N secondes » ou "
     "une sensibilité plus haute.",
     "No pause found: the speech is continuous or covered by music. Try “every N seconds” or a higher sensitivity.",
     "Nessuna pausa trovata: il parlato è continuo o coperto dalla musica. Prova «ogni N secondi» o una sensibilità "
     "più alta.",
     "No se encontró ninguna pausa: el habla es continua o la tapa una música. Prueba «cada N segundos» o una "
     "sensibilidad más alta."),
    ("La scène {k} dure {d} sur {t} : aucune pause trouvée dans cette partie (parole continue ou musique). Essaie "
     "« toutes les N secondes » ou une sensibilité plus haute.",
     "Scene {k} lasts {d} of {t}: no pause found in that part (continuous speech or music). Try “every N seconds” "
     "or a higher sensitivity.",
     "La scena {k} dura {d} su {t}: nessuna pausa trovata in quella parte (parlato continuo o musica). Prova «ogni "
     "N secondi» o una sensibilità più alta.",
     "La escena {k} dura {d} de {t}: no se encontró ninguna pausa en esa parte (habla continua o música). Prueba "
     "«cada N segundos» o una sensibilidad más alta."),
    ("La scène {k} dure {d} sur {t} : cette partie est filmée en une seule prise de vue. Essaie « pauses dans la "
     "parole » ou « toutes les N secondes ».",
     "Scene {k} lasts {d} of {t}: that part is filmed in a single shot. Try “pauses in speech” or “every N seconds”.",
     "La scena {k} dura {d} su {t}: quella parte è ripresa con un'unica inquadratura. Prova «pause nel parlato» o "
     "«ogni N secondi».",
     "La escena {k} dura {d} de {t}: esa parte está grabada en una sola toma. Prueba «pausas al hablar» o «cada N "
     "segundos»."),
    ("La vidéo est plus courte que la durée choisie : baisse « Durée de chaque scène ».",
     "The video is shorter than the chosen length: lower “Length of each scene”.",
     "Il video è più corto della durata scelta: abbassa «Durata di ogni scena».",
     "El vídeo es más corto que la duración elegida: baja «Duración de cada escena»."),
    ("Aucun changement de plan trouvé : c'est sans doute une seule prise de vue. Essaie « pauses dans la parole », "
     "« toutes les N secondes » ou une sensibilité plus haute.",
     "No shot change found: it is probably a single shot. Try “pauses in speech”, “every N seconds” or a higher "
     "sensitivity.",
     "Nessun cambio di inquadratura trovato: probabilmente è un'unica ripresa. Prova «pause nel parlato», «ogni N "
     "secondi» o una sensibilità più alta.",
     "No se encontró ningún cambio de plano: probablemente es una sola toma. Prueba «pausas al hablar», «cada N "
     "segundos» o una sensibilidad más alta."),
    ("Sensibilité", "Sensitivity", "Sensibilità", "Sensibilidad"),
    ("basse", "low", "bassa", "baja"),
    ("moyenne", "medium", "media", "media"),
    ("haute = plus de scènes", "high = more scenes", "alta = più scene", "alta = más escenas"),
    ("Trouver les scènes", "Find the scenes", "Trova le scene", "Buscar las escenas"),
    ("Vidéo d'origine", "Original video", "Video originale", "Vídeo original"),
    ("Choisis les scènes à garder", "Choose the scenes to keep", "Scegli le scene da tenere",
     "Elige las escenas que conservar"),
    ("Clic : garder ✓ / exclure · ▶ : lire la scène · clic droit (ou ⋯) : toutes les options",
     "Click: keep ✓ / exclude · ▶: play the scene · right-click (or ⋯): all options",
     "Clic: tieni ✓ / escludi · ▶: riproduci la scena · clic destro (o ⋯): tutte le opzioni",
     "Clic: conservar ✓ / excluir · ▶: reproducir la escena · clic derecho (o ⋯): todas las opciones"),
    ("Une seule vidéo avec les scènes gardées", "One video with the kept scenes", "Un unico video con le scene tenute",
     "Un solo vídeo con las escenas conservadas"),
    ("Créer la vidéo", "Create the video", "Crea il video", "Crear el vídeo"),
    ("Les scènes trouvées apparaîtront ici.", "The scenes found will appear here.", "Le scene trovate appariranno qui.",
     "Las escenas encontradas aparecerán aquí."),
    ("**{n} scènes** · {k} gardées · durée gardée **{d}** sur {t}", "**{n} scenes** · {k} kept · kept length **{d}** of {t}",
     "**{n} scene** · {k} tenute · durata tenuta **{d}** su {t}",
     "**{n} escenas** · {k} conservadas · duración conservada **{d}** de {t}"),
    ("gardée", "kept", "tenuta", "conservada"),
    ("exclue", "excluded", "esclusa", "excluida"),
    ("Toutes les options", "All options", "Tutte le opzioni", "Todas las opciones"),
    ("Lire cette scène", "Play this scene", "Riproduci questa scena", "Reproducir esta escena"),
    ("Garder cette scène", "Keep this scene", "Tieni questa scena", "Conservar esta escena"),
    ("Exclure cette scène", "Exclude this scene", "Escludi questa scena", "Excluir esta escena"),
    ("Garder seulement celle-ci", "Keep only this one", "Tieni solo questa", "Conservar solo esta"),
    ("Fusionner avec la précédente", "Merge with the previous one", "Unisci alla precedente", "Unir con la anterior"),
    ("Fusionner avec la suivante", "Merge with the next one", "Unisci alla successiva", "Unir con la siguiente"),
    ("Couper en deux", "Split in two", "Dividi in due", "Cortar en dos"),
    ("Exporter cette scène seule", "Export this scene only", "Esporta solo questa scena", "Exportar solo esta escena"),
    ("Tout garder", "Keep all", "Tieni tutte", "Conservar todas"),
    ("Tout exclure", "Exclude all", "Escludi tutte", "Excluir todas"),
    ("Inverser la sélection", "Invert selection", "Inverti la selezione", "Invertir la selección"),
    ("Annuler", "Undo", "Annulla", "Deshacer"),
    ("Rien à annuler.", "Nothing to undo.", "Niente da annullare.", "Nada que deshacer."),
    ("Recherche des scènes", "Finding the scenes", "Ricerca delle scene", "Buscando las escenas"),
    ("Création des miniatures", "Creating thumbnails", "Creazione delle miniature", "Creando miniaturas"),
    ("Création de la vidéo", "Creating the video", "Creazione del video", "Creando el vídeo"),
    ("Clique d'abord sur « Trouver les scènes ».", "First click “Find the scenes”.", "Clicca prima su «Trova le scene».",
     "Primero haz clic en «Buscar las escenas»."),
    ("Choisis un fichier vidéo (MP4, MOV, MKV, WEBM…).", "Choose a video file (MP4, MOV, MKV, WEBM…).",
     "Scegli un file video (MP4, MOV, MKV, WEBM…).", "Elige un archivo de vídeo (MP4, MOV, MKV, WEBM…)."),
    ("Durée de la vidéo illisible : {name}", "Unreadable video length: {name}", "Durata del video illeggibile: {name}",
     "Duración del vídeo ilegible: {name}"),
    ("Le fichier est peut-être incomplet : réexporte-le puis réessaie.",
     "The file may be incomplete: export it again, then retry.",
     "Il file forse è incompleto: esportalo di nuovo e riprova.",
     "Puede que el archivo esté incompleto: vuelve a exportarlo y reinténtalo."),
    ("Cette vidéo n'a pas de son : impossible de trouver les pauses dans la parole.",
     "This video has no sound: pauses in speech cannot be found.",
     "Questo video non ha audio: impossibile trovare le pause nel parlato.",
     "Este vídeo no tiene sonido: no se pueden encontrar las pausas al hablar."),
    ("Choisis plutôt « changements de plan ».", "Choose “shot changes” instead.",
     "Scegli invece «cambi di inquadratura».", "Elige mejor «cambios de plano»."),
    ("Aucune scène gardée.", "No scene kept.", "Nessuna scena tenuta.", "Ninguna escena conservada."),
    ("Clique sur une scène pour la garder (✓), puis réessaie.", "Click a scene to keep it (✓), then retry.",
     "Clicca su una scena per tenerla (✓), poi riprova.", "Haz clic en una escena para conservarla (✓) y reinténtalo."),
    # ---- Barre flottante de Screen Record (core/floatbar.py, core/barapi.py)
    ("Afficher la barre sur le bureau", "Show the bar on the desktop", "Mostra la barra sul desktop",
     "Mostrar la barra en el escritorio"),
    ("Ouvrir la barre au démarrage de MSV", "Open the bar when MSV starts", "Apri la barra all'avvio di MSV",
     "Abrir la barra al iniciar MSV"),
    ("toujours au premier plan : enregistrer, pause, arrêter, photo de l'écran ou d'une zone, sans revenir dans MSV",
     "always on top: record, pause, stop, screenshot of the screen or of an area, without going back to MSV",
     "sempre in primo piano: registra, pausa, ferma, foto dello schermo o di una zona, senza tornare in MSV",
     "siempre en primer plano: grabar, pausa, detener, captura de la pantalla o de una zona, sin volver a MSV"),
    ("Barre ouverte sur le bord droit de l'écran. Fais-la glisser où tu veux.",
     "Bar opened on the right edge of the screen. Drag it wherever you like.",
     "Barra aperta sul bordo destro dello schermo. Trascinala dove vuoi.",
     "Barra abierta en el borde derecho de la pantalla. Arrástrala donde quieras."),
    ("La barre est déjà ouverte.", "The bar is already open.", "La barra è già aperta.", "La barra ya está abierta."),
    ("Ouvrir la barre", "Open the bar", "Apri la barra", "Abrir la barra"),
    ("Réduire la barre", "Collapse the bar", "Riduci la barra", "Reducir la barra"),
    ("Photo de l'écran", "Screenshot", "Foto dello schermo", "Captura de pantalla"),
    ("Réglages", "Settings", "Impostazioni", "Ajustes"),
    ("Annuler le compte à rebours", "Cancel the countdown", "Annulla il conto alla rovescia",
     "Cancelar la cuenta atrás"),
    ("Arrêter l'enregistrement", "Stop recording", "Ferma la registrazione", "Detener la grabación"),
    ("Montage en cours… {p} %", "Editing in progress… {p}%", "Montaggio in corso… {p}%", "Montaje en curso… {p} %"),
    ("Ouvrir la vidéo", "Open the video", "Apri il video", "Abrir el vídeo"),
    ("MSV ne répond pas.", "MSV is not responding.", "MSV non risponde.", "MSV no responde."),
    ("📷 Photo enregistrée : {name}", "📷 Screenshot saved: {name}", "📷 Foto salvata: {name}",
     "📷 Captura guardada: {name}"),
    ("Ouvrir l'image", "Open the image", "Apri l'immagine", "Abrir la imagen"),
    ("Dessiner une zone…", "Draw an area…", "Disegna una zona…", "Dibujar una zona…"),
    ("Zone {w}×{h}", "Area {w}×{h}", "Zona {w}×{h}", "Zona {w}×{h}"),
    ("Ouvrir Screen Record dans MSV", "Open Screen Record in MSV", "Apri Screen Record in MSV",
     "Abrir Screen Record en MSV"),
    ("Ouvrir le dossier des enregistrements", "Open the recordings folder", "Apri la cartella delle registrazioni",
     "Abrir la carpeta de grabaciones"),
    ("Fermer la barre", "Close the bar", "Chiudi la barra", "Cerrar la barra"),
    ("Fais glisser pour choisir la zone · Échap pour annuler", "Drag to choose the area · Esc to cancel",
     "Trascina per scegliere la zona · Esc per annullare", "Arrastra para elegir la zona · Esc para cancelar"),
    ("Zone trop petite (64 × 64 pixels minimum).", "Area too small (64 × 64 pixels minimum).",
     "Zona troppo piccola (minimo 64 × 64 pixel).", "Zona demasiado pequeña (mínimo 64 × 64 píxeles)."),
    ("choisis la zone", "choose the area", "scegli la zona", "elige la zona"),
    ("Photo", "Screenshot", "Foto", "Captura"),
    ("Enregistrer", "Record", "Registra", "Grabar"),
    ("📷 Fais glisser pour choisir la zone de la photo, ou clique sur un écran pour le prendre entier · Échap pour "
     "annuler",
     "📷 Drag to choose the area of the screenshot, or click a screen to take all of it · Esc to cancel",
     "📷 Trascina per scegliere la zona della foto, o clicca su uno schermo per prenderlo intero · Esc per annullare",
     "📷 Arrastra para elegir la zona de la captura, o haz clic en una pantalla para tomarla entera · Esc para "
     "cancelar"),
    ("🎥 Fais glisser pour choisir la zone à filmer, ou clique sur un écran pour le prendre entier · Échap pour "
     "annuler",
     "🎥 Drag to choose the area to record, or click a screen to record all of it · Esc to cancel",
     "🎥 Trascina per scegliere la zona da registrare, o clicca su uno schermo per prenderlo intero · Esc per "
     "annullare",
     "🎥 Arrastra para elegir la zona que grabar, o haz clic en una pantalla para tomarla entera · Esc para "
     "cancelar"),
    ("Fais glisser pour choisir la zone, ou clique sur un écran · Échap pour annuler",
     "Drag to choose the area, or click a screen · Esc to cancel",
     "Trascina per scegliere la zona, o clicca su uno schermo · Esc per annullare",
     "Arrastra para elegir la zona, o haz clic en una pantalla · Esc para cancelar"),
    ("{name} · clic : tout l'écran", "{name} · click: whole screen", "{name} · clic: tutto lo schermo",
     "{name} · clic: toda la pantalla"),
    ("📷 Photo copiée : colle-la où tu veux avec {keys}.", "📷 Screenshot copied: paste it anywhere with {keys}.",
     "📷 Foto copiata: incollala dove vuoi con {keys}.", "📷 Captura copiada: pégala donde quieras con {keys}."),
    ("Enregistrée aussi : {name}", "Also saved as: {name}", "Salvata anche come: {name}",
     "Guardada también como: {name}"),
    # ---- Écran partagé (core/splitscreen.py)
    ("Écran partagé (plusieurs vidéos)", "Split screen (several videos)", "Schermo diviso (più video)",
     "Pantalla dividida (varios vídeos)"),
    ("2 à 4 vidéos", "2 to 4 videos", "Da 2 a 4 video", "De 2 a 4 vídeos"),
    ("une par case, dans l'ordre", "one per cell, in order", "uno per riquadro, in ordine", "uno por casilla, en orden"),
    ("(facultatif)", "(optional)", "(facoltativo)", "(opcional)"),
    ("Disposition", "Layout", "Disposizione", "Disposición"),
    ("côte à côte", "side by side", "affiancati", "lado a lado"),
    ("haut / bas", "top / bottom", "sopra / sotto", "arriba / abajo"),
    ("grille", "grid", "griglia", "cuadrícula"),
    ("une grande + petites", "one large + small ones", "uno grande + piccoli", "una grande + pequeñas"),
    ("Espace entre les cases (px)", "Space between cells (px)", "Spazio tra i riquadri (px)",
     "Espacio entre casillas (px)"),
    ("Durée : comme la vidéo…", "Length: like the video that is…", "Durata: come il video…", "Duración: como el vídeo…"),
    ("la plus courte", "shortest", "più corto", "más corto"),
    ("la plus longue", "longest", "più lungo", "más largo"),
    ("la plus longue : les autres se figent sur leur dernière image",
     "longest: the others freeze on their last frame",
     "più lungo: gli altri restano fermi sull'ultima immagine",
     "más largo: los demás se congelan en su última imagen"),
    ("Son", "Sound", "Audio", "Sonido"),
    ("toutes (mélange)", "all (mixed)", "tutti (mix)", "todos (mezcla)"),
    ("vidéo 1", "video 1", "video 1", "vídeo 1"),
    ("vidéo 2", "video 2", "video 2", "vídeo 2"),
    ("vidéo 3", "video 3", "video 3", "vídeo 3"),
    ("vidéo 4", "video 4", "video 4", "vídeo 4"),
    ("aucun son", "no sound", "nessun audio", "sin sonido"),
    ("Aperçu et vidéo finale", "Preview and final video", "Anteprima e video finale", "Vista previa y vídeo final"),
    ("Ajoute entre 2 et 4 vidéos.", "Add between 2 and 4 videos.", "Aggiungi da 2 a 4 video.", "Añade entre 2 y 4 vídeos."),
    ("Une vidéo par case : « Vidéo 1 », « Vidéo 2 »…", "One video per cell: “Video 1”, “Video 2”…",
     "Un video per riquadro: «Video 1», «Video 2»…", "Un vídeo por casilla: «Vídeo 1», «Vídeo 2»…"),
    ("Ce fichier n'est ni une vidéo ni une image ({name}).", "This file is neither a video nor an image ({name}).",
     "Questo file non è né un video né un'immagine ({name}).", "Este archivo no es ni un vídeo ni una imagen ({name})."),
    ("Il faut au moins une vidéo (les images seules n'ont pas de durée).",
     "At least one video is needed (images alone have no length).",
     "Serve almeno un video (le immagini da sole non hanno durata).",
     "Hace falta al menos un vídeo (las imágenes solas no tienen duración)."),
    ("Remplace une des images par une vidéo.", "Replace one of the images with a video.",
     "Sostituisci una delle immagini con un video.", "Sustituye una de las imágenes por un vídeo."),
    ("Le son choisi ({a}) correspond à une case vide.", "The chosen sound ({a}) belongs to an empty cell.",
     "L'audio scelto ({a}) corrisponde a un riquadro vuoto.", "El sonido elegido ({a}) corresponde a una casilla vacía."),
    ("Choisis le son d'une vidéo ajoutée, ou « toutes (mélange) ».", "Choose the sound of an added video, or “all (mixed)”.",
     "Scegli l'audio di un video aggiunto, oppure «tutti (mix)».",
     "Elige el sonido de un vídeo añadido, o «todos (mezcla)»."),
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
où **une ligne = une vidéo**. Colonnes : `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage; intro; outro`. `intro` et `outro` : « Titre | sous-titre » d'une scène animée d'ouverture et de fin (style du modèle) ; `musique` : un fichier, ou `auto` / `auto:suspense` pour une musique générée.
Dans `medias`, sépare les fichiers par `|`, indique un dossier entier, ou un motif comme `images/*.jpg`.
Si la ligne contient des images et une voix off, les images sont réparties automatiquement sur la durée de la voix.

### Sous-titres
- **script** : colle le texte, il est découpé et minuté automatiquement (sur la durée de la voix off s'il y en a une).
- **srt** : fichier de sous-titres existant (par exemple exporté de ton générateur de voix).
- **whisper** : transcription automatique au mot près, après `pip install faster-whisper`.
- **vidéo** : active les sous-titres déjà intégrés au fichier vidéo (MP4, MKV), dans la langue choisie ;
  ils restent synchronisés même après coupe, changement de vitesse ou suppression des silences.
Un fichier `.srt` est toujours créé à côté de la vidéo : tu peux l'envoyer sur YouTube.

### Scènes animées
Onglet **Scènes animées** : **carte titre**, **téléphone** (ta vidéo dans un téléphone), **écran final** (bouton
« S'abonner » qui se fait cliquer), **liste** à cocher, **chiffres clés** qui défilent, **avant / après** avec balayage
et **question choc** mot par mot. Remplis les textes (un mot entre \\*étoiles\\* prend la couleur d'accent), regarde
l'aperçu, puis « Créer la scène » et « Ajouter à la timeline ». Avec « Utiliser comme intro / fin du projet », la
scène est ajoutée automatiquement à chaque rendu, au format du projet (et dans les modèles de série).

### Musique générée
Réglages → Audio → **Musique générée** : calme, inspirant, énergique ou suspense. Libre de droits, composée sur ton
PC à la durée exacte de la vidéo, avec la musique qui baisse quand on parle. « Écouter 12 s » donne un extrait.

### Calques et photos animées
- **Image ou vidéo incrustée** (section 4) : capture d'écran, sticker, logo ou vidéo par-dessus le montage
  (picture-in-picture). Choisis le média dans la médiathèque, les heures d'apparition, la position (centre en %),
  la largeur et l'entrée animée : **fondu**, **montée** ou **zoom** (avec un léger rebond). Les images opaques et les
  vidéos ont des coins arrondis ; la vidéo incrustée est muette et bouclée si elle est trop courte.
- **Texte animé** : autant de textes que tu veux, chacun avec ses heures, sa position, sa taille, sa couleur et son
  entrée. Les tableaux restent modifiables (animation en toutes lettres, « fin » vide = jusqu'à la fin).
- **Sticker** : clique sur un sticker de la bibliothèque (bouton S'abonner, cœur, flèches, WOW, coche…), choisis un
  emoji en couleur ou importe le tien (PNG, GIF ou WebP animé, WebM transparent). Animations **pulsation**,
  **rebond** et **balancement** : le sticker bouge tant qu'il est à l'écran. Il s'ajoute au tableau des incrustations.
- **Effets spéciaux** (section 5) : sur un passage de la vidéo, **secousse**, **zoom punch** (zoom rapide sur un
  moment fort), **zoom progressif**, **flash** blanc ou noir, **glitch** et filtres (noir et blanc, vintage, couleurs
  vives, cinéma, chaud, froid, vignette, flou, négatif), avec une intensité de 0,1 à 1. Les stickers et les textes
  restent nets par-dessus.
- **Rythme et effets sonores** (section 6) : MSV trouve le tempo de la musique (BPM) et place un effet tous les 1, 2,
  4 ou 8 temps ; les images fixes peuvent finir pile sur un temps. **À chaque coupe** : « zoom alterné » (un plan sur
  deux resserré, style jump cut) ou un effet bref, et un son (whoosh, pop, ding, boom, montée…). Les 11 sons sont
  fabriqués par MSV, libres de droits ; tu peux aussi en placer un à un moment précis ou importer le tien.
- **Mode viral** (en haut à droite) : un clic règle tout façon Short : 9:16, accroche animée, sous-titres karaoké,
  silences coupés, zoom alterné + whoosh, musique énergique au rythme, sticker S'abonner les 3 dernières secondes.
  Dans le tableau des incrustations, un début négatif (-3) compte depuis la fin de la vidéo.
- **Mouvement des photos** (Réglages → Images fixes) : zoom avant ou arrière, panoramique, ou **Ken Burns** (zoom lent
  et déplacement, avec un trajet différent à chaque photo). La colonne « mouvement » de la timeline règle une photo
  précise.

### Studio audio
Onglet **🎚️ Studio audio** (fond noir). Chaque outil range ses fichiers dans son dossier : `sorties/audio/enchainements`,
`sorties/audio/decoupes`, `sorties/audio/superpositions`, `sorties/audio/platine_dj` et `sorties/audio/effets_micro` ;
le sous-onglet **Sorties** les liste, les fait écouter et ouvre chaque dossier.
- **Enchaîner** : autant de morceaux que tu veux (« Ajouter des morceaux » en prend plusieurs d'un coup, ou les sons
  de la médiathèque). Dans le tableau : début et fin (remplis tout seuls avec le morceau entier, à modifier pour
  couper), volume et **transition** vers le morceau suivant. Pads :
  **fondu**, **coupe sèche**, **isolateur (bass swap)** (les basses s'échangent d'un coup au milieu du fondu), et
  effets de relâchement : **écho** (le dernier temps se répète en s'éteignant), **back spin** (rembobinage du
  vinyle), **freinage** (le vinyle ralentit jusqu'à l'arrêt). **Transitions sur le rythme** : tout tombe sur les
  temps. Clique sur une ligne pour l'écouter.
- **Découper** : charge une musique (ou le dernier fichier du Studio), sa forme d'onde s'affiche. Glisse dessus pour
  choisir un passage, fais glisser les poignées de début et de fin, touche la forme d'onde pour y placer la lecture,
  ou tape les temps exacts. **Repères** : coupe le morceau en plusieurs fichiers. Trois choix : **garder la
  sélection**, **couper aux repères** (un fichier par morceau), **enlever la sélection** (le reste est recollé sans
  clic). **Aimant sur le temps** : les poignées tombent sur les temps. Clavier : I = début, O = fin, M = repère,
  flèches = ajuster. **Envoyer dans Enchaîner** ajoute les morceaux au tableau d'Enchaîner.
- **Superposer** : autant de pistes que tu veux en même temps (musique, voix, ambiance), décalage, boucle ;
  **ducking** : la musique baisse d'environ 13 dB quand la voix parle.
- **Platine DJ** : choisis une musique (ou le résultat d'Enchaîner ou de Superposer), lance la lecture et joue des
  pads. **Instruments** (on touche) : corne de stade, sirène, scratch, laser, grosse caisse, clap, roulement,
  montée, impact. **Effets** (on maintient) : filtre grave, filtre aigu, flanger, écho, roll (répétition du temps),
  hachoir. Chaque coup s'inscrit dans un tableau, modifiable à la main. **Caler sur le temps** : tout tombe pile sur
  le temps. Clavier : 1 à 9 pour les instruments, Q W E R T Y pour les effets, Espace = lecture/pause.
  **Textures sonores** (touches A à L) : espace, shimmer, dub, crush, gel (tirées de ta musique) ; vinyle, vent,
  pluie, bruit montant (ajoutées). **Bus d'effets** : Send/Return (l'original reste intact, l'effet s'ajoute avec ses
  niveaux Send et Return, sa queue résonne après le relâchement), Master (l'effet traite tout le mix, dosé par
  Dry/Wet) ou Auto (chaque effet sur son bus). **Fondu des effets** : entrée et sortie en douceur (0,01 à 2 s).
- **Isolateur 3 bandes** (enchaîner et superposer) : trois faders tactiles, graves, médiums, aigus, de -26 à +6 dB.
  Glisse au doigt ou à la souris, double-tap = 0 dB, **KILL** coupe une bande ; au clavier : flèches, 0 = remise à zéro.
- **Effets micro et mixage** : enregistre ta voix dans le navigateur ou importe un fichier, puis choisis un effet
  (voix studio, radio, téléphone, mégaphone, robot, écho, grande salle, voix grave, voix aiguë, monstre, chorale,
  alien) et règle la console : graves, médiums, aigus, compresseur, gain, réduction du bruit, vitesse.
- Fondus d'entrée et de sortie, volume normalisé (-14 LUFS), MP3 ou WAV ; **Utiliser comme musique / voix off du
  projet** envoie le résultat dans l'onglet Montage.

### Classement
Onglet **Classement** : un Short 9:16 « Top N ». Importe 2 à 10 clips (le n° 1 est la première ligne), donne un titre à chaque rang et, si tu veux, le crédit de la source. Écris le titre et coche les mots à surligner, puis choisis un préréglage (Néon sombre, Clair, Brut rouge, Podium), une mise en page (liste à gauche, liste en haut, plein écran, bandeau) et l'ordre (décroissant : compte à rebours, le n° 1 passe en dernier). Entrée dans le titre passe à la ligne. « Police, tailles et couleurs » règle aussi une deuxième couleur de surlignage, la position du badge (coin du clip, à côté du titre, aucun), le panneau derrière la liste, les numéros colorés (or, argent, bronze) et les libellés (taille, majuscules, italique). Le curseur « Rang affiché » montre chaque étape ; « Aperçu rapide » fait une vidéo légère, « Exporter » la version finale dans `sorties/classements`. Enregistre le classement (`.json`) pour le reprendre plus tard, ou pour le rendre en ligne de commande : `python cli.py classement fichier.json`.
**Droits** : n'utilise que des clips dont tu as les droits ou l'autorisation, et crédite toujours la source.

### Voix off
Onglet **Voix off** : écris le texte (scènes séparées par `---`), choisis **Piper** (gratuit, hors ligne) ou
**ElevenLabs** (ta clé API, voix très naturelles et minutage exact des sous-titres), puis « Utiliser dans l'onglet Montage ».
En série, coche « Créer la voix off à partir de la colonne texte ». Une scène générée avec la mauvaise voix se corrige
avec « Remplacer la voix d'un clip existant ».
**Ma voix (clonage local)** : enregistre 30 à 60 s de ta voix (pièce calme, ton naturel), crée la voix une fois, puis choisis-la comme n'importe quelle autre. Tout reste sur ton PC ; la première utilisation installe environ 5 Go. Ne clone que ta voix, ou avec l'accord de la personne.
**Voix plus naturelles** : chaque phrase est lue séparément avec une pause adaptée à sa ponctuation ; `[pause 1s]` force une pause. Nombres, heures, prix et sigles sont lus en lettres, et le **dictionnaire de prononciation** (« Pauses et prononciation ») corrige un mot mal dit (`MSV = èm-èss-vé`). « Son studio » donne à toutes les voix un son plus chaud et plus net. Pour Ma voix, choisis un **style de lecture** (Narration calme, Conversation, Promo énergique) ; avec **2 ou 3 prises par phrase**, chaque phrase est réécoutée par une transcription automatique et refaite si un mot manque ou si un mot inventé s'ajoute. Le modèle imite le ton de ton enregistrement : pour une promo, enregistre-toi avec le ton d'une promo. Écris pour l'oreille : phrases courtes, ponctuation soignée.

### Scènes et écran partagé
**Découper en scènes** : ajoute une vidéo, choisis « changements de plan » (l'image change), « pauses dans la parole » (tutoriel, podcast, discours filmé d'un seul plan) ou « toutes les N secondes » (morceaux de durée fixe, chaque coupure placée sur la pause la plus proche), puis « Trouver les scènes ». « Unir les scènes plus courtes que » ne découpe pas : il regroupe les scènes trop courtes. Clique sur une scène pour la garder (✓) ou l'exclure ; ▶ la lit. **Clic droit** (ou ⋯, ou Maj + F10 au clavier) ouvre toutes les options : garder seulement celle-ci, fusionner avec la précédente ou la suivante, couper en deux, exporter cette scène seule, tout garder, inverser, annuler. « Créer la vidéo » met bout à bout les scènes gardées.
**Écran partagé** : 2 à 4 vidéos dans la même image (côte à côte, haut / bas, grille, une grande + petites), en 16:9, 9:16 ou 1:1. L'aperçu se met à jour à chaque réglage. Choisis la durée (la plus courte, ou la plus longue : les autres se figent) et le son (mélange ou une seule vidéo).

### Outils rapides
- **Convertisseur de temps** (Inspecteur) : tape `90`, `1:30`, `1h 2m 3s` ou `2,5 min`, puis « → Début » / « → Fin ».
- **Effacer un logo** : choisis la zone (coin rapide + curseurs), vérifie avec « Aperçu », puis efface sur toute la vidéo.
- **Logo MSV** : ajoute le logo Montage Studio ; sa position est mémorisée dans la vidéo pour l'enlever ensuite exactement.
- **Réduire le bruit** : choisis le niveau, écoute 10 s avant / après, puis nettoie le fichier (l'image d'une vidéo est copiée sans perte). Dans un montage : Réglages → Audio → « Réduction du bruit ».

### Screen Record (Windows, Linux X11, Mac)
1. Choisis un écran ou une fenêtre, le micro (et sa **réduction du bruit**), le son de l'ordinateur et, si tu veux,
   la webcam.
2. « Démarrer l'enregistrement » : tu as 3 secondes pour afficher la page à filmer.
3. **Pause** : bouton « Pause » ou **Ctrl + Shift + F8** ; rien n'est capturé pendant la pause. « Reprendre » repart
   après 3 secondes, le raccourci repart tout de suite.
4. Arrête avec le bouton « Arrêter » ou **Ctrl + Shift + F9** depuis n'importe quelle fenêtre.
5. MSV coupe les passages dans MSV, raccourcit les longues pauses et zoome sur chaque clic.
   La vidéo est rangée dans `sorties/screen_record`. Version 9:16 au choix : **suivre le curseur**, **écran entier
   + fond flou**, ou **écran en haut + webcam en bas**.
6. « Créer un lien de partage » : le lien s'ouvre sur les appareils du même Wi-Fi, tant que MSV est ouvert.

**Barre sur le bureau** (« Afficher la barre sur le bureau ») : une petite barre bronze, toujours au premier plan. › la replie. 📷 et 🎥 assombrissent l'écran : **fais glisser pour choisir une zone, ou clique sur un écran pour le prendre entier** (pratique avec plusieurs écrans). 📷 enregistre la photo **et la copie** : colle-la tout de suite avec Ctrl+V. 🎥 enregistre (avec les derniers réglages choisis dans MSV) puis ■ arrête, ⏸ met en pause. ▭ choisit un écran, une fenêtre ou une zone dessinée, puis « Photo » ou « Enregistrer ». ⚙ ouvre MSV ou le dossier. Fais-la glisser où tu veux. Sous Windows 10 / 11, elle n'apparaît ni dans les vidéos ni dans les photos.

Linux : session X11 (Xorg), écrans entiers ; micro et son de l'ordinateur par PulseAudio / PipeWire. Mac : écrans entiers ; autorise « Enregistrement de l'écran », « Micro », « Caméra » et « Surveillance de l'entrée » ; pour le son de l'ordinateur, installe BlackHole (gratuit). Le choix d'une seule fenêtre existe seulement sous Windows.

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
where **one row = one video**. Columns: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage; intro; outro`. `intro` and `outro`: “Title | subtitle” of an opening and closing animated scene (template style); `musique`: a file, or `auto` / `auto:suspense` for generated music
(column names stay in French). In `medias`, separate files with `|`, give a whole folder, or a pattern like `images/*.jpg`.
If a row contains images and a voice-over, the images are spread automatically over the length of the voice.

### Subtitles
- **script**: paste the text; it is split and timed automatically (over the voice-over length if there is one).
- **srt**: an existing subtitle file (for example exported from your voice generator).
- **whisper**: automatic word-level transcription, after `pip install faster-whisper`.
- **video track**: turns on the subtitles already embedded in the video file (MP4, MKV), in the chosen language;
  they stay in sync even after trimming, speed changes or silence removal.
A `.srt` file is always created next to the video: you can upload it to YouTube.

### Animated scenes
**Animated scenes** tab: **title card**, **phone** (your video inside a phone), **end screen** (a “Subscribe” button
that gets clicked), check **list**, counting **key figures**, **before / after** with a wipe and a word-by-word **hook
question**. Fill in the texts (a word between \\*asterisks\\* takes the accent color), check the preview, then
“Create the scene” and “Add to timeline”. With “Use as project intro / ending”, the scene is added automatically to
every render, in the project format (and in batch templates).

### Generated music
Settings → Audio → **Generated music**: calm, inspiring, energetic or suspense. Royalty-free, composed on your PC to
the exact length of the video, and lowered while someone speaks. “Listen 12 s” plays a sample.

### Layers and animated photos
- **Image or video overlay** (section 4): screenshot, sticker, logo or video on top of the edit (picture-in-picture).
  Pick the media from the library, when it appears, its position (center in %), width and entrance animation:
  **fade**, **rise** or **zoom** (with a slight bounce). Opaque images and videos get rounded corners; the overlay
  video is muted and looped if it is too short.
- **Animated text**: as many texts as you like, each with its own times, position, size, color and entrance.
  The tables stay editable (animation written out in full, empty “end” = until the end).
- **Sticker**: click a sticker from the library (Subscribe button, heart, arrows, WOW, check mark…), pick a color
  emoji or import your own (PNG, animated GIF or WebP, transparent WebM). **Pulse**, **bounce** and **swing**
  animations keep the sticker moving while it is on screen. It is added to the overlay table.
- **Special effects** (section 5): on part of the video, **shake**, **punch zoom** (quick zoom on a key moment),
  **slow zoom**, white or black **flash**, **glitch** and filters (black and white, vintage, vivid colors, cinematic,
  warm, cool, vignette, blur, negative), with an intensity from 0.1 to 1. Stickers and text stay sharp on top.
- **Rhythm and sound effects** (section 6): MSV finds the music's tempo (BPM) and places an effect every 1, 2, 4 or
  8 beats; still images can end exactly on a beat. **On every cut**: “alternating zoom” (every other shot tighter,
  jump-cut style) or a brief effect, plus a sound (whoosh, pop, ding, boom, riser…). The 11 sounds are made by MSV,
  royalty-free; you can also place one at a given moment or import your own.
- **Viral mode** (top right): one click sets everything up like a Short: 9:16, animated hook, karaoke subtitles,
  silences cut, alternating zoom + whoosh, energetic music on the beat, Subscribe sticker for the last 3 seconds.
  In the overlay table, a negative start (-3) counts from the end of the video.
- **Photo motion** (Settings → Still images): zoom in or out, pan, or **Ken Burns** (slow zoom and drift, with a
  different path for each photo). The timeline's “motion” column sets the motion of a single photo.

### Audio studio
**🎚️ Audio studio** tab (black background). Each tool saves its files in its own folder: `sorties/audio/enchainements`,
`sorties/audio/decoupes`, `sorties/audio/superpositions`, `sorties/audio/platine_dj` and `sorties/audio/effets_micro`;
the **Outputs** sub-tab lists them, plays them and opens each folder.
- **Chain**: as many tracks as you like (“Add tracks” takes several at once, or use the media library sounds). In the
  table: start and end (filled in automatically with the whole track, edit them to trim), volume and **transition** to
  the next track. Pads: **fade**, **hard cut**, **isolator (bass
  swap)** (the bass swaps at once in the middle of the fade), and release effects: **echo** (the last beat repeats as
  it fades), **back spin** (vinyl rewind), **vinyl brake** (the record slows to a stop). **Beat-matched transitions**:
  everything lands on the beats. Click a row to listen to it.
- **Cut**: load a song (or the latest Studio file) and its waveform appears. Drag across it to choose a part, drag
  the start and end handles, tap the waveform to move playback there, or type the exact times. **Markers** split the
  track into several files. Three choices: **keep the selection**, **split at markers** (one file per piece),
  **remove the selection** (the rest is joined back without a click). **Snap to the beat**: the handles land on the
  beats. Keyboard: I = start, O = end, M = marker, arrows = adjust. **Send to Chain** adds the pieces to the Chain
  table.
- **Layer**: as many tracks as you like at the same time (music, voice, ambience), offset, loop; **ducking**: the
  music dips by about 13 dB when the voice speaks.
- **DJ deck**: pick a song (or the Chain or Layer result), press play and hit the pads. **Instruments** (tap): stadium
  horn, siren, scratch, laser, kick drum, clap, snare roll, riser, impact. **Effects** (hold): low filter, high filter,
  flanger, echo, roll (beat repeat), chopper. Every hit is written into a table you can edit by hand. **Snap to the
  beat**: everything lands right on the beat. Keyboard: 1 to 9 for instruments, Q W E R T Y for effects, Space =
  play/pause. **Sound textures** (keys A to L): space, shimmer, dub, crush, freeze (made from your song); vinyl,
  wind, rain, noise riser (added on top). **Effects bus**: Send/Return (the original stays intact, the effect is
  added with its Send and Return levels and its tail rings after release), Master (the effect processes the whole
  mix, set with Dry/Wet) or Auto (each effect on its own bus). **Effect fade**: smooth in and out (0.01 to 2 s).
- **3-band isolator** (chain and layer): three touch faders, bass, mids, treble, from -26 to +6 dB. Slide with your
  finger or mouse, double-tap = 0 dB, **KILL** cuts a band; with the keyboard: arrows, 0 = reset.
- **Mic effects and mixing**: record your voice in the browser or import a file, then pick an effect (studio voice,
  radio, telephone, megaphone, robot, echo, large hall, deep voice, high voice, monster, choir, alien) and adjust the
  console: bass, mids, treble, compressor, gain, noise reduction, speed.
- Fade in and out, normalized volume (-14 LUFS), MP3 or WAV; **Use as project music / voice-over** sends the result
  to the Editor tab.

### Ranking
**Ranking** tab: a 9:16 “Top N” Short. Import 2 to 10 clips (No. 1 is the first row), give each rank a title and, if you like, the source credit. Write the title and tick the words to highlight, then pick a preset (Dark neon, Light, Raw red, Podium), a layout (list on the left, list at the top, full screen, banner) and the order (descending: countdown, No. 1 comes last). Enter in the title starts a new line. “Font, sizes and colours” also sets a second highlight colour, the badge position (clip corner, next to the title, none), the panel behind the list, coloured numbers (gold, silver, bronze) and the labels (size, capitals, italics). The “Rank shown” slider previews each step; “Quick preview” makes a light video, “Export” the final version in `sorties/classements`. Save the ranking (`.json`) to resume it later, or to render it from the command line: `python cli.py classement file.json`.
**Rights**: only use clips you have the rights or permission to use, and always credit the source.

### Voice-over
**Voice-over** tab: write the text (scenes separated by `---`), choose **Piper** (free, offline) or
**ElevenLabs** (your API key, very natural voices and exact subtitle timing), then “Use in the Editor tab”.
In batch mode, tick “Create the voice-over from the texte column”. A scene generated with the wrong voice can be fixed
with “Replace the voice of an existing clip”.
**My voice (local cloning)**: record 30 to 60 s of your voice (quiet room, natural tone), create the voice once, then pick it like any other. Everything stays on your PC; first use installs about 5 GB. Only clone your own voice, or with the person's consent.
**More natural voices**: each sentence is read separately with a pause that matches its punctuation; `[pause 1s]` forces a pause. Numbers, times, prices and acronyms are read out in full, and the **pronunciation dictionary** ("Pauses and pronunciation") fixes a mispronounced word (`MSV = em-ess-vee`). "Studio sound" gives every voice a warmer, cleaner sound. For My voice, pick a **reading style** (Calm narration, Conversation, Energetic promo); with **2 or 3 takes per sentence**, each sentence is checked by automatic transcription and redone if a word is missing or an invented word is added. The model copies the tone of your recording: for a promo, record yourself in a promo tone. Write for the ear: short sentences, careful punctuation.

### Scenes & split screen
**Split into scenes**: add a video, choose “shot changes” (the picture changes), “pauses in speech” (tutorial, podcast, speech filmed in a single shot) or “every N seconds” (fixed-length pieces, each cut moved to the nearest pause), then “Find the scenes”. “Merge scenes shorter than” does not split: it groups scenes that are too short. Click a scene to keep it (✓) or exclude it; ▶ plays it. **Right-click** (or ⋯, or Shift + F10 on the keyboard) opens all options: keep only this one, merge with the previous or next one, split in two, export this scene only, keep all, invert, undo. “Create the video” joins the kept scenes.
**Split screen**: 2 to 4 videos in the same frame (side by side, top / bottom, grid, one large + small ones), in 16:9, 9:16 or 1:1. The preview updates with every setting. Choose the length (shortest, or longest: the others freeze) and the sound (mixed or a single video).

### Quick tools
- **Time converter** (Inspector): type `90`, `1:30`, `1h 2m 3s` or `2.5 min`, then “→ Start” / “→ End”.
- **Remove a logo**: choose the area (quick corner + sliders), check with “Preview”, then remove it from the whole video.
- **MSV logo**: add the Montage Studio logo; its position is stored in the video so it can be removed exactly later.
- **Reduce noise**: choose the level, listen to 10 s before / after, then clean the file (a video's picture is copied losslessly). In an edit: Settings → Audio → “Noise reduction”.

### Screen Record (Windows, Linux X11, Mac)
1. Choose a screen or a window, the microphone (and its **noise reduction**), the computer audio and, if you like,
   the webcam.
2. “Start recording”: you have 3 seconds to bring up the page you want to record.
3. **Pause**: “Pause” button or **Ctrl + Shift + F8**; nothing is captured during the pause. “Resume” restarts after
   3 seconds, the shortcut restarts right away.
4. Stop with the “Stop” button or **Ctrl + Shift + F9** from any window.
5. MSV cuts the moments spent in MSV, shortens long pauses and zooms in on every click.
   The video is saved in `sorties/screen_record`. 9:16 version of your choice: **follow the cursor**, **full screen
   + blurred background**, or **screen on top + webcam below**.
6. “Create a share link”: the link opens on devices on the same Wi-Fi, as long as MSV is open.

**Desktop bar** (“Show the bar on the desktop”): a small bronze bar, always on top. › collapses it. 📷 and 🎥 dim the screen: **drag to choose an area, or click a screen to take all of it** (handy with several screens). 📷 saves the screenshot **and copies it**: paste it right away with Ctrl+V. 🎥 records (with the last settings chosen in MSV) then ■ stops, ⏸ pauses. ▭ chooses a screen, a window or a drawn area, then “Screenshot” or “Record”. ⚙ opens MSV or the folder. Drag it wherever you like. On Windows 10 / 11 it appears neither in videos nor in screenshots.

Linux: X11 (Xorg) session, whole screens; microphone and computer audio through PulseAudio / PipeWire. Mac: whole screens; allow “Screen Recording”, “Microphone”, “Camera” and “Input Monitoring”; for computer audio, install BlackHole (free). Recording a single window is available on Windows only.

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
poi una tabella CSV in cui **una riga = un video**. Colonne: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage; intro; outro`. `intro` e `outro`: « Titolo | sottotitolo » di una scena animata di apertura e di chiusura (stile del modello); `musique`: un file, oppure `auto` / `auto:suspense` per una musica generata
(i nomi delle colonne restano in francese). In `medias`, separa i file con `|`, indica un'intera cartella o un motivo come `images/*.jpg`.
Se la riga contiene immagini e una voce fuori campo, le immagini vengono distribuite automaticamente sulla durata della voce.

### Sottotitoli
- **script**: incolla il testo, viene diviso e sincronizzato automaticamente (sulla durata della voce fuori campo, se presente).
- **srt**: un file di sottotitoli esistente (ad esempio esportato dal tuo generatore di voce).
- **whisper**: trascrizione automatica parola per parola, dopo `pip install faster-whisper`.
- **traccia del video**: attiva i sottotitoli già presenti nel file video (MP4, MKV), nella lingua scelta;
  restano sincronizzati anche dopo taglio, cambio di velocità o rimozione dei silenzi.
Accanto al video viene sempre creato un file `.srt`: puoi caricarlo su YouTube.

### Scene animate
Scheda **Scene animate**: **scheda titolo**, **telefono** (il tuo video dentro un telefono), **schermata finale**
(pulsante « Iscriviti » che viene cliccato), **elenco** con spunte, **numeri chiave** che scorrono, **prima / dopo** con
tendina e **domanda shock** parola per parola. Compila i testi (una parola tra \\*asterischi\\* prende il colore
d'accento), guarda l'anteprima, poi « Crea la scena » e « Aggiungi alla timeline ». Con « Usa come intro / finale del
progetto », la scena viene aggiunta automaticamente a ogni render, nel formato del progetto (e nei modelli di serie).

### Musica generata
Impostazioni → Audio → **Musica generata**: calma, ispirante, energica o suspense. Senza diritti, composta sul tuo PC
alla durata esatta del video, e abbassata quando qualcuno parla. « Ascolta 12 s » fa sentire un estratto.

### Livelli e foto animate
- **Immagine o video sovrapposto** (sezione 4): screenshot, sticker, logo o video sopra il montaggio
  (picture-in-picture). Scegli il media dalla libreria, quando appare, la posizione (centro in %), la larghezza e
  l'entrata animata: **dissolvenza**, **salita** o **zoom** (con un leggero rimbalzo). Le immagini opache e i video
  hanno gli angoli arrotondati; il video sovrapposto è muto e va in loop se è troppo corto.
- **Testo animato**: tutti i testi che vuoi, ognuno con i suoi tempi, posizione, dimensione, colore ed entrata.
  Le tabelle restano modificabili (animazione scritta per esteso, « fine » vuota = fino alla fine).
- **Sticker**: clicca su uno sticker della libreria (pulsante Iscriviti, cuore, frecce, WOW, spunta…), scegli
  un'emoji a colori o importa il tuo (PNG, GIF o WebP animato, WebM trasparente). Le animazioni **pulsazione**,
  **rimbalzo** e **oscillazione** fanno muovere lo sticker finché è sullo schermo. Finisce nella tabella delle
  sovrapposizioni.
- **Effetti speciali** (sezione 5): su un passaggio del video, **scossa**, **zoom punch** (zoom rapido su un momento
  forte), **zoom progressivo**, **flash** bianco o nero, **glitch** e filtri (bianco e nero, vintage, colori vivaci,
  cinema, caldo, freddo, vignettatura, sfocato, negativo), con un'intensità da 0,1 a 1. Sticker e testi restano
  nitidi sopra.
- **Ritmo ed effetti sonori** (sezione 6): MSV trova il tempo della musica (BPM) e mette un effetto ogni 1, 2, 4 o
  8 battiti; le immagini fisse possono finire esattamente su un battito. **A ogni taglio**: « zoom alternato »
  (un'inquadratura su due più stretta, stile jump cut) o un effetto breve, più un suono (whoosh, pop, ding, boom,
  salita…). Gli 11 suoni sono creati da MSV, senza diritti; puoi anche metterne uno in un momento preciso o
  importare il tuo.
- **Modalità virale** (in alto a destra): un clic imposta tutto come uno Short: 9:16, gancio animato, sottotitoli
  karaoke, silenzi tagliati, zoom alternato + whoosh, musica energica a tempo, sticker Iscriviti negli ultimi 3
  secondi. Nella tabella delle sovrapposizioni, un inizio negativo (-3) conta dalla fine del video.
- **Movimento delle foto** (Impostazioni → Immagini fisse): zoom avanti o indietro, panoramica, oppure **Ken Burns**
  (zoom lento e spostamento, con un percorso diverso per ogni foto). La colonna « movimento » della timeline regola
  una sola foto.

### Studio audio
Scheda **🎚️ Studio audio** (sfondo nero). Ogni strumento salva i suoi file nella propria cartella:
`sorties/audio/enchainements`, `sorties/audio/decoupes`, `sorties/audio/superpositions`, `sorties/audio/platine_dj`
e `sorties/audio/effets_micro`; la sotto-scheda **File creati** li elenca, li fa ascoltare e apre ogni cartella.
- **Concatena**: quanti brani vuoi (« Aggiungi brani » ne prende diversi insieme, oppure i suoni della libreria).
  Nella tabella: inizio e fine (compilati da soli con il brano intero, da modificare per tagliare), volume e
  **transizione** verso il brano successivo. Pad: **dissolvenza**, **taglio
  netto**, **isolatore (bass swap)** (i bassi si scambiano di colpo a metà dissolvenza) ed effetti di rilascio:
  **eco** (l'ultimo battito si ripete spegnendosi), **back spin** (riavvolgimento del vinile), **frenata vinile**
  (il disco rallenta fino a fermarsi). **Transizioni a tempo**: tutto cade sui battiti. Clicca su una riga per
  ascoltarla.
- **Taglia**: carica una musica (o l'ultimo file dello Studio) e appare la sua forma d'onda. Trascina sopra per
  scegliere un passaggio, sposta le maniglie di inizio e fine, tocca la forma d'onda per spostare lì la
  riproduzione, oppure scrivi i tempi esatti. I **segnaposto** tagliano il brano in più file. Tre scelte: **tieni
  la selezione**, **taglia ai segnaposto** (un file per pezzo), **togli la selezione** (il resto viene riunito senza
  clic). **Calamita sul battito**: le maniglie cadono sui battiti. Tastiera: I = inizio, O = fine, M = segnaposto,
  frecce = regola. **Invia a Concatena** aggiunge i pezzi alla tabella di Concatena.
- **Sovrapponi**: quante tracce vuoi insieme (musica, voce, ambiente), ritardo, loop; **ducking**: la musica si
  abbassa di circa 13 dB quando parla la voce.
- **Console DJ**: scegli una musica (o il risultato di Concatena o Sovrapponi), avvia l'ascolto e suona i pad.
  **Strumenti** (si toccano): tromba da stadio, sirena, scratch, laser, cassa, clap, rullata, salita, impatto.
  **Effetti** (si tengono premuti): filtro bassi, filtro acuti, flanger, eco, roll (ripetizione del battito),
  trancia. Ogni colpo si scrive in una tabella modificabile a mano. **Aggancia al battito**: tutto cade esattamente
  sul battito. Tastiera: da 1 a 9 per gli strumenti, Q W E R T Y per gli effetti, Spazio = play/pausa.
  **Texture sonore** (tasti da A a L): spazio, shimmer, dub, crush, congela (dalla tua musica); vinile, vento,
  pioggia, rumore in salita (aggiunte). **Bus degli effetti**: Send/Return (l'originale resta intatto, l'effetto si
  aggiunge con i livelli Send e Return e la sua coda risuona dopo il rilascio), Master (l'effetto tratta tutto il
  mix, dosato con Dry/Wet) o Auto (ogni effetto sul suo bus). **Dissolvenza degli effetti**: entrata e uscita
  morbide (da 0,01 a 2 s).
- **Isolatore a 3 bande** (concatena e sovrapponi): tre fader tattili, bassi, medi, acuti, da -26 a +6 dB. Scorri
  con il dito o il mouse, doppio tocco = 0 dB, **KILL** taglia una banda; da tastiera: frecce, 0 = azzera.
- **Effetti microfono e mixaggio**: registra la tua voce nel browser o importa un file, poi scegli un effetto (voce
  da studio, radio, telefono, megafono, robot, eco, grande sala, voce grave, voce acuta, mostro, coro, alieno) e
  regola il mixer: bassi, medi, acuti, compressore, guadagno, riduzione del rumore, velocità.
- Dissolvenze in entrata e in uscita, volume normalizzato (-14 LUFS), MP3 o WAV; **Usa come musica / voce fuori
  campo del progetto** invia il risultato alla scheda Montaggio.

### Classifica
Scheda **Classifica**: uno Short 9:16 «Top N». Importa da 2 a 10 clip (il n. 1 è la prima riga), dai un titolo a ogni posizione e, se vuoi, i crediti della fonte. Scrivi il titolo e spunta le parole da evidenziare, poi scegli una preimpostazione (Neon scuro, Chiaro, Rosso crudo, Podio), un'impaginazione (lista a sinistra, lista in alto, schermo intero, banda) e l'ordine (decrescente: conto alla rovescia, il n. 1 arriva per ultimo). Invio nel titolo va a capo. «Carattere, dimensioni e colori» regola anche un secondo colore di evidenziazione, la posizione del badge (angolo della clip, accanto al titolo, nessuno), il pannello dietro la lista, i numeri colorati (oro, argento, bronzo) e le etichette (dimensione, maiuscolo, corsivo). Il cursore «Posizione mostrata» mostra ogni passaggio; «Anteprima rapida» crea un video leggero, «Esporta» la versione finale in `sorties/classements`. Salva la classifica (`.json`) per riprenderla più tardi o per crearla da riga di comando: `python cli.py classement file.json`.
**Diritti**: usa solo clip di cui hai i diritti o l'autorizzazione, e cita sempre la fonte.

### Voce fuori campo
Scheda **Voce fuori campo**: scrivi il testo (scene separate da `---`), scegli **Piper** (gratuito, offline) o
**ElevenLabs** (la tua chiave API, voci molto naturali e sottotitoli con tempi esatti), poi «Usa nella scheda Montaggio».
In serie, spunta «Crea la voce fuori campo dalla colonna texte». Una scena generata con la voce sbagliata si corregge
con «Sostituisci la voce di una clip esistente».
**La mia voce (clonazione locale)**: registra da 30 a 60 s della tua voce (stanza silenziosa, tono naturale), crea la voce una volta, poi sceglila come le altre. Tutto resta sul tuo PC; il primo utilizzo installa circa 5 GB. Clona solo la tua voce, o con il consenso della persona.
**Voci più naturali**: ogni frase viene letta separatamente con una pausa adatta alla punteggiatura; `[pause 1s]` forza una pausa. Numeri, orari, prezzi e sigle vengono letti per esteso, e il **dizionario di pronuncia** («Pause e pronuncia») corregge una parola pronunciata male (`MSV = emme-esse-vu`). «Suono da studio» dà a tutte le voci un suono più caldo e pulito. Per La mia voce, scegli uno **stile di lettura** (Narrazione calma, Conversazione, Promo energica); con **2 o 3 riprese per frase**, ogni frase viene verificata da una trascrizione automatica e rifatta se manca una parola o se ne viene aggiunta una inventata. Il modello imita il tono della tua registrazione: per una promo, registrati con un tono da promo. Scrivi per l'orecchio: frasi brevi, punteggiatura curata.

### Scene e schermo diviso
**Dividi in scene**: aggiungi un video, scegli «cambi di inquadratura» (l'immagine cambia), «pause nel parlato» (tutorial, podcast, discorso ripreso con un'unica inquadratura) o «ogni N secondi» (pezzi di durata fissa, ogni taglio spostato sulla pausa più vicina), poi «Trova le scene». «Unisci le scene più corte di» non divide: raggruppa le scene troppo corte. Clicca su una scena per tenerla (✓) o escluderla; ▶ la riproduce. Il **clic destro** (o ⋯, o Maiusc + F10 da tastiera) apre tutte le opzioni: tieni solo questa, unisci alla precedente o alla successiva, dividi in due, esporta solo questa scena, tieni tutte, inverti, annulla. «Crea il video» mette in fila le scene tenute.
**Schermo diviso**: da 2 a 4 video nella stessa immagine (affiancati, sopra / sotto, griglia, uno grande + piccoli), in 16:9, 9:16 o 1:1. L'anteprima si aggiorna a ogni impostazione. Scegli la durata (più corto, oppure più lungo: gli altri restano fermi) e l'audio (mix o un solo video).

### Strumenti rapidi
- **Convertitore di tempo** (Ispettore): scrivi `90`, `1:30`, `1h 2m 3s` o `2,5 min`, poi «→ Inizio» / «→ Fine».
- **Rimuovi un logo**: scegli la zona (angolo rapido + cursori), controlla con «Anteprima», poi rimuovilo da tutto il video.
- **Logo MSV**: aggiungi il logo Montage Studio; la posizione resta memorizzata nel video per poterlo togliere con precisione.
- **Riduci il rumore**: scegli il livello, ascolta 10 s prima / dopo, poi pulisci il file (l'immagine di un video viene copiata senza perdita). In un montaggio: Impostazioni → Audio → «Riduzione del rumore».

### Screen Record (Windows, Linux X11, Mac)
1. Scegli uno schermo o una finestra, il microfono (e la sua **riduzione del rumore**), l'audio del computer e, se
   vuoi, la webcam.
2. «Avvia la registrazione»: hai 3 secondi per mostrare la pagina da registrare.
3. **Pausa**: pulsante «Pausa» oppure **Ctrl + Shift + F8**; durante la pausa non viene catturato niente. «Riprendi»
   riparte dopo 3 secondi, la scorciatoia riparte subito.
4. Ferma con il pulsante «Ferma» oppure con **Ctrl + Shift + F9** da qualsiasi finestra.
5. MSV taglia i momenti passati in MSV, accorcia le pause lunghe e fa zoom su ogni clic.
   Il video viene salvato in `sorties/screen_record`. Versione 9:16 a scelta: **segui il cursore**, **schermo intero
   + sfondo sfocato**, oppure **schermo sopra + webcam sotto**.
6. «Crea un link di condivisione»: il link si apre sui dispositivi della stessa rete Wi-Fi, finché MSV è aperto.

**Barra sul desktop** («Mostra la barra sul desktop»): una piccola barra bronzo, sempre in primo piano. › la riduce. 📷 e 🎥 scuriscono lo schermo: **trascina per scegliere una zona, o clicca su uno schermo per prenderlo intero** (comodo con più schermi). 📷 salva la foto **e la copia**: incollala subito con Ctrl+V. 🎥 registra (con le ultime impostazioni scelte in MSV) poi ■ ferma, ⏸ mette in pausa. ▭ sceglie uno schermo, una finestra o una zona disegnata, poi «Foto» o «Registra». ⚙ apre MSV o la cartella. Trascinala dove vuoi. Su Windows 10 / 11 non compare né nei video né nelle foto.

Linux: sessione X11 (Xorg), schermi interi; microfono e audio del computer tramite PulseAudio / PipeWire. Mac: schermi interi; autorizza «Registrazione schermo», «Microfono», «Fotocamera» e «Monitoraggio input»; per l'audio del computer installa BlackHole (gratuito). La scelta di una sola finestra esiste solo su Windows.

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
y luego una tabla CSV donde **una fila = un vídeo**. Columnas: `id; medias; titre; texte; srt; voix_off; musique; debut; fin; recadrage; intro; outro`. `intro` y `outro`: «Título | subtítulo» de una escena animada de apertura y de cierre (estilo de la plantilla); `musique`: un archivo, o `auto` / `auto:suspense` para una música generada
(los nombres de las columnas se quedan en francés). En `medias`, separa los archivos con `|`, indica una carpeta entera o un patrón como `images/*.jpg`.
Si la fila contiene imágenes y una voz en off, las imágenes se reparten automáticamente durante la voz.

### Subtítulos
- **script**: pega el texto; se divide y se sincroniza automáticamente (con la duración de la voz en off, si la hay).
- **srt**: un archivo de subtítulos existente (por ejemplo, exportado de tu generador de voz).
- **whisper**: transcripción automática palabra por palabra, tras `pip install faster-whisper`.
- **pista del vídeo**: activa los subtítulos ya incluidos en el archivo de vídeo (MP4, MKV), en el idioma elegido;
  se mantienen sincronizados incluso tras cortar, cambiar la velocidad o quitar los silencios.
Siempre se crea un archivo `.srt` junto al vídeo: puedes subirlo a YouTube.

### Escenas animadas
Pestaña **Escenas animadas**: **tarjeta de título**, **teléfono** (tu vídeo dentro de un teléfono), **pantalla final**
(botón «Suscribirse» que se pulsa), **lista** con marcas, **cifras clave** que van contando, **antes / después** con
barrido y **pregunta impactante** palabra por palabra. Rellena los textos (una palabra entre \\*asteriscos\\* toma el
color de acento), mira la vista previa y luego «Crear la escena» y «Añadir a la línea de tiempo». Con «Usar como
intro / final del proyecto», la escena se añade automáticamente a cada renderizado, en el formato del proyecto (y en
las plantillas de serie).

### Música generada
Ajustes → Audio → **Música generada**: tranquila, inspiradora, enérgica o suspense. Libre de derechos, compuesta en tu
PC a la duración exacta del vídeo y bajada cuando alguien habla. «Escuchar 12 s» reproduce un fragmento.

### Capas y fotos animadas
- **Imagen o vídeo superpuesto** (sección 4): captura de pantalla, sticker, logo o vídeo encima del montaje
  (picture-in-picture). Elige el medio en la biblioteca, cuándo aparece, la posición (centro en %), el ancho y la
  entrada animada: **fundido**, **subida** o **zoom** (con un ligero rebote). Las imágenes opacas y los vídeos tienen
  esquinas redondeadas; el vídeo superpuesto va sin sonido y en bucle si es demasiado corto.
- **Texto animado**: todos los textos que quieras, cada uno con sus tiempos, posición, tamaño, color y entrada.
  Las tablas siguen siendo editables (animación escrita completa, «fin» vacío = hasta el final).
- **Sticker**: haz clic en un sticker de la biblioteca (botón Suscribirse, corazón, flechas, WOW, marca…), elige
  un emoji en color o importa el tuyo (PNG, GIF o WebP animado, WebM transparente). Las animaciones **pulsación**,
  **rebote** y **balanceo** mueven el sticker mientras está en pantalla. Se añade a la tabla de superposiciones.
- **Efectos especiales** (sección 5): en un tramo del vídeo, **sacudida**, **zoom punch** (zoom rápido en un
  momento clave), **zoom progresivo**, **destello** blanco o negro, **glitch** y filtros (blanco y negro, vintage,
  colores vivos, cine, cálido, frío, viñeta, desenfoque, negativo), con una intensidad de 0,1 a 1. Los stickers y
  los textos quedan nítidos encima.
- **Ritmo y efectos de sonido** (sección 6): MSV encuentra el tempo de la música (BPM) y coloca un efecto cada 1, 2,
  4 u 8 tiempos; las imágenes fijas pueden terminar justo en un tiempo. **En cada corte**: «zoom alterno» (un plano
  de cada dos más cerrado, estilo jump cut) o un efecto breve, y un sonido (whoosh, pop, ding, boom, subida…). Los
  11 sonidos los crea MSV, libres de derechos; también puedes colocar uno en un momento preciso o importar el tuyo.
- **Modo viral** (arriba a la derecha): un clic lo ajusta todo como un Short: 9:16, gancho animado, subtítulos
  karaoke, silencios cortados, zoom alterno + whoosh, música enérgica al ritmo, sticker Suscribirse los últimos 3
  segundos. En la tabla de superposiciones, un inicio negativo (-3) cuenta desde el final del vídeo.
- **Movimiento de las fotos** (Ajustes → Imágenes fijas): acercar o alejar, paneo, o **Ken Burns** (zoom lento y
  desplazamiento, con un recorrido distinto para cada foto). La columna «movimiento» de la línea de tiempo ajusta
  una sola foto.

### Estudio de audio
Pestaña **🎚️ Estudio de audio** (fondo negro). Cada herramienta guarda sus archivos en su carpeta:
`sorties/audio/enchainements`, `sorties/audio/decoupes`, `sorties/audio/superpositions`, `sorties/audio/platine_dj`
y `sorties/audio/effets_micro`; la subpestaña **Salidas** los lista, los reproduce y abre cada carpeta.
- **Encadenar**: tantas pistas como quieras («Añadir pistas» acepta varias a la vez, o los sonidos de la
  biblioteca). En la tabla: inicio y fin (se rellenan solos con la pista entera, cámbialos para recortar), volumen y
  **transición** a la pista siguiente. Pads: **fundido**, **corte
  seco**, **aislador (bass swap)** (los graves se intercambian de golpe a mitad del fundido) y efectos de salida:
  **eco** (el último tiempo se repite apagándose), **back spin** (rebobinado del vinilo), **frenado de vinilo** (el
  disco se frena hasta pararse). **Transiciones al ritmo**: todo cae en los tiempos. Haz clic en una fila para
  escucharla.
- **Cortar**: carga una canción (o el último archivo del Estudio) y aparece su forma de onda. Arrastra encima para
  elegir un fragmento, mueve las asas de inicio y fin, toca la forma de onda para llevar ahí la reproducción, o
  escribe los tiempos exactos. Las **marcas** cortan la pista en varios archivos. Tres opciones: **conservar la
  selección**, **cortar en las marcas** (un archivo por trozo), **quitar la selección** (el resto se vuelve a unir sin
  chasquido). **Imán en el tiempo**: las asas caen en los tiempos. Teclado: I = inicio, O = fin, M = marca,
  flechas = ajustar. **Enviar a Encadenar** añade los trozos a la tabla de Encadenar.
- **Superponer**: tantas pistas como quieras a la vez (música, voz, ambiente), desfase, bucle; **ducking**: la
  música baja unos 13 dB cuando habla la voz.
- **Mesa de DJ**: elige una canción (o el resultado de Encadenar o Superponer), pulsa reproducir y toca los pads.
  **Instrumentos** (se tocan): bocina de estadio, sirena, scratch, láser, bombo, palmada, redoble, subida, impacto.
  **Efectos** (se mantienen pulsados): filtro de graves, filtro de agudos, flanger, eco, roll (repetición del
  tiempo), cortador. Cada golpe se anota en una tabla que puedes editar a mano. **Ajustar al tiempo**: todo cae
  justo en el tiempo. Teclado: 1 a 9 para los instrumentos, Q W E R T Y para los efectos, Espacio = reproducir/pausa.
  **Texturas sonoras** (teclas A a L): espacio, shimmer, dub, crush, congelar (de tu canción); vinilo, viento,
  lluvia, ruido ascendente (añadidas). **Bus de efectos**: Send/Return (el original queda intacto, el efecto se suma
  con sus niveles Send y Return y su cola suena tras soltar), Master (el efecto procesa toda la mezcla, dosificado
  con Dry/Wet) o Auto (cada efecto en su bus). **Fundido de los efectos**: entrada y salida suaves (0,01 a 2 s).
- **Aislador de 3 bandas** (encadenar y superponer): tres faders táctiles, graves, medios, agudos, de -26 a +6 dB.
  Desliza con el dedo o el ratón, doble toque = 0 dB, **KILL** corta una banda; con el teclado: flechas, 0 = reinicio.
- **Efectos de micro y mezcla**: graba tu voz en el navegador o importa un archivo, elige un efecto (voz de estudio,
  radio, teléfono, megáfono, robot, eco, sala grande, voz grave, voz aguda, monstruo, coro, alienígena) y ajusta la
  mesa: graves, medios, agudos, compresor, ganancia, reducción de ruido, velocidad.
- Fundidos de entrada y salida, volumen normalizado (-14 LUFS), MP3 o WAV; **Usar como música / voz en off del
  proyecto** envía el resultado a la pestaña Edición.

### Clasificación
Pestaña **Clasificación**: un Short 9:16 «Top N». Importa de 2 a 10 clips (el n.º 1 es la primera fila), da un título a cada puesto y, si quieres, el crédito de la fuente. Escribe el título y marca las palabras a resaltar; luego elige un preajuste (Neón oscuro, Claro, Rojo crudo, Podio), un diseño (lista a la izquierda, lista arriba, pantalla completa, banda superior) y el orden (descendente: cuenta atrás, el n.º 1 sale el último). Intro en el título hace un salto de línea. «Fuente, tamaños y colores» también ajusta un segundo color de resaltado, la posición de la insignia (esquina del clip, junto al título, ninguno), el panel detrás de la lista, los números de colores (oro, plata, bronce) y las etiquetas (tamaño, mayúsculas, cursiva). El cursor «Puesto mostrado» muestra cada paso; «Vista previa rápida» crea un vídeo ligero y «Exportar» la versión final en `sorties/classements`. Guarda la clasificación (`.json`) para retomarla más tarde o para crearla desde la línea de comandos: `python cli.py classement archivo.json`.
**Derechos**: usa solo clips de los que tengas los derechos o la autorización, y cita siempre la fuente.

### Voz en off
Pestaña **Voz en off**: escribe el texto (escenas separadas por `---`), elige **Piper** (gratis, sin conexión) o
**ElevenLabs** (tu clave API, voces muy naturales y subtítulos con tiempos exactos), y luego «Usar en la pestaña Edición».
En serie, marca «Crear la voz en off a partir de la columna texte». Una escena generada con la voz equivocada se corrige
con «Reemplazar la voz de un clip existente».
**Mi voz (clonación local)**: graba de 30 a 60 s de tu voz (habitación tranquila, tono natural), crea la voz una vez y elígela como cualquier otra. Todo se queda en tu PC; el primer uso instala unos 5 GB. Clona solo tu voz, o con el consentimiento de la persona.
**Voces más naturales**: cada frase se lee por separado con una pausa adaptada a su puntuación; `[pause 1s]` fuerza una pausa. Números, horas, precios y siglas se leen en letras, y el **diccionario de pronunciación** («Pausas y pronunciación») corrige una palabra mal dicha (`MSV = eme-ese-uve`). «Sonido de estudio» da a todas las voces un sonido más cálido y limpio. Para Mi voz, elige un **estilo de lectura** (Narración tranquila, Conversación, Promo enérgica); con **2 o 3 tomas por frase**, cada frase se verifica con una transcripción automática y se rehace si falta una palabra o se añade una inventada. El modelo imita el tono de tu grabación: para una promo, grábate con tono de promo. Escribe para el oído: frases cortas, puntuación cuidada.

### Escenas y pantalla dividida
**Dividir en escenas**: añade un vídeo, elige «cambios de plano» (la imagen cambia), «pausas al hablar» (tutorial, pódcast, discurso grabado en un solo plano) o «cada N segundos» (trozos de duración fija, cada corte movido a la pausa más cercana) y luego «Buscar las escenas». «Unir las escenas más cortas que» no divide: agrupa las escenas demasiado cortas. Haz clic en una escena para conservarla (✓) o excluirla; ▶ la reproduce. El **clic derecho** (o ⋯, o Mayús + F10 con el teclado) abre todas las opciones: conservar solo esta, unir con la anterior o la siguiente, cortar en dos, exportar solo esta escena, conservar todas, invertir, deshacer. «Crear el vídeo» une las escenas conservadas.
**Pantalla dividida**: de 2 a 4 vídeos en la misma imagen (lado a lado, arriba / abajo, cuadrícula, una grande + pequeñas), en 16:9, 9:16 o 1:1. La vista previa se actualiza con cada ajuste. Elige la duración (el más corto, o el más largo: los demás se congelan) y el sonido (mezcla o un solo vídeo).

### Herramientas rápidas
- **Conversor de tiempo** (Inspector): escribe `90`, `1:30`, `1h 2m 3s` o `2,5 min`, y luego «→ Inicio» / «→ Fin».
- **Quitar un logo**: elige la zona (esquina rápida + controles), compruébalo con «Vista previa» y quítalo de todo el vídeo.
- **Logo MSV**: añade el logo de Montage Studio; su posición se guarda en el vídeo para poder quitarlo con precisión.
- **Reducir el ruido**: elige el nivel, escucha 10 s antes / después y limpia el archivo (la imagen de un vídeo se copia sin pérdida). En un montaje: Ajustes → Audio → «Reducción de ruido».

### Screen Record (Windows, Linux X11, Mac)
1. Elige una pantalla o una ventana, el micrófono (y su **reducción de ruido**), el audio del ordenador y, si
   quieres, la webcam.
2. «Iniciar la grabación»: tienes 3 segundos para mostrar la página que quieres grabar.
3. **Pausa**: botón «Pausa» o **Ctrl + Shift + F8**; no se captura nada durante la pausa. «Reanudar» vuelve a empezar
   tras 3 segundos, el atajo vuelve a empezar al instante.
4. Detén con el botón «Detener» o con **Ctrl + Shift + F9** desde cualquier ventana.
5. MSV recorta los momentos pasados en MSV, acorta las pausas largas y hace zoom en cada clic.
   El vídeo se guarda en `sorties/screen_record`. Versión 9:16 a elegir: **seguir el cursor**, **pantalla completa
   + fondo desenfocado**, o **pantalla arriba + webcam abajo**.
6. «Crear un enlace para compartir»: el enlace se abre en los dispositivos de la misma Wi-Fi, mientras MSV esté abierto.

**Barra en el escritorio** («Mostrar la barra en el escritorio»): una pequeña barra bronce, siempre en primer plano. › la reduce. 📷 y 🎥 oscurecen la pantalla: **arrastra para elegir una zona, o haz clic en una pantalla para tomarla entera** (práctico con varias pantallas). 📷 guarda la captura **y la copia**: pégala enseguida con Ctrl+V. 🎥 graba (con los últimos ajustes elegidos en MSV) y luego ■ detiene, ⏸ pausa. ▭ elige una pantalla, una ventana o una zona dibujada, y luego «Captura» o «Grabar». ⚙ abre MSV o la carpeta. Arrástrala donde quieras. En Windows 10 / 11 no aparece ni en los vídeos ni en las capturas.

Linux: sesión X11 (Xorg), pantallas completas; micrófono y audio del ordenador mediante PulseAudio / PipeWire. Mac: pantallas completas; autoriza «Grabación de pantalla», «Micrófono», «Cámara» y «Monitorización de entrada»; para el audio del ordenador, instala BlackHole (gratis). Grabar una sola ventana solo es posible en Windows.

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


def help_sections(lang: str | None = None) -> list[tuple[str, str]]:
    """L'aide découpée en sections (titre, texte Markdown), dans le même ordre pour toutes les langues."""
    text = HELP.get(lang or LANG.get(), HELP[DEFAULT_LANG])
    out = []
    for block in text.split("\n### ")[1:]:
        title, _sep, body = block.partition("\n")
        out.append((title.strip(), body.strip()))
    return out


def pick_lang(accept_language: str | None) -> str:
    """Choisit la langue d'après l'en-tête Accept-Language du navigateur."""
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return "en"
