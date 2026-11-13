"""Préparation du texte lu par les voix off.

* pauses : le script est découpé en phrases, chacune suivie d'un silence qui dépend de sa ponctuation
  (point, point d'exclamation, points de suspension, changement de paragraphe, balise ``[pause 1s]``) ;
* texte parlé : nombres, heures, pourcentages, prix et sigles écrits en toutes lettres, puis dictionnaire de
  prononciation de l'utilisateur (``MSV = èm-èss-vé``).

Les sous-titres gardent le texte écrit par l'utilisateur : seul le texte envoyé au moteur de voix change.
Ce module n'importe rien d'autre de MSV : le programme de clonage (environnement séparé) s'en sert aussi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

PAUSES = {".": 0.3, "!": 0.35, "?": 0.35, "…": 0.5, ";": 0.25, ":": 0.25}
PAUSE_OTHER = 0.25      # phrase coupée par une balise [pause] ou sans ponctuation finale
PAUSE_PARAGRAPH = 0.6   # ligne vide entre deux paragraphes
PAUSE_TAG = 0.6         # [pause] sans durée
PAUSE_MAX = 5.0

TAG = re.compile(r"\[\s*pause\s*(?:(\d+(?:[.,]\d+)?)\s*(ms|s)?)?\s*\]", re.I)
_ABBREV = re.compile(r"(?:^|\s)(?:[A-Z]|MM|Mme|Mlle|Mr|Mrs|Ms|Dr|Pr|St|Sr|Sra|Dott|Sig|ex|p|vs|cf)\.$")


@dataclass
class Segment:
    text: str      # texte écrit (sous-titres)
    pause: float   # silence après la phrase, en secondes


# --------------------------------------------------------------------------- pauses

def _sentences(text: str) -> list[str]:
    out: list[str] = []
    # coupe après . ! ? … (et après le guillemet fermant qui les suit : « Fin. » Suite)
    for part in re.split(r"(?<=[.!?…])\s+(?![»”\"')])|(?<=[.!?…][»”\"')])\s+|(?<=[.!?…]\s[»”])\s+", text):
        if out and (_ABBREV.search(out[-1]) or not re.search(r"\w", part)):
            out[-1] += " " + part      # « M. Dupont », ou guillemet fermant isolé
        else:
            out.append(part)
    return [s for s in out if s.strip()]


def _end_pause(sentence: str) -> float:
    s = sentence.rstrip(" »\"')”’]")
    if s.endswith("..."):
        return PAUSES["…"]
    return PAUSES.get(s[-1:], PAUSE_OTHER)


def segments(text: str) -> list[Segment]:
    """Découpe une scène en phrases, chacune suivie de la pause qui convient (la dernière : 0, sauf balise)."""
    out: list[Segment] = []
    explicit = False
    for para in re.split(r"\n\s*\n", text.strip()):
        pieces = TAG.split(para)          # [texte, durée, unité, texte, durée, unité, …, texte]
        for i in range(0, len(pieces), 3):
            chunk = re.sub(r"\s+", " ", pieces[i]).strip()
            for sent in _sentences(chunk) if chunk else []:
                out.append(Segment(sent, _end_pause(sent)))
                explicit = False
            if i + 1 < len(pieces) and out:
                num, unit = pieces[i + 1], (pieces[i + 2] or "").lower()
                d = PAUSE_TAG if num is None else float(num.replace(",", ".")) / (1000 if unit == "ms" else 1)
                out[-1].pause = min(PAUSE_MAX, d)
                explicit = True
        if out and not explicit:
            out[-1].pause = max(out[-1].pause, PAUSE_PARAGRAPH)
    if out and not explicit:
        out[-1].pause = 0.0
    return out


def merge_short(segs: list[Segment], min_chars: int = 30, max_chars: int = 200) -> list[Segment]:
    """Regroupe les phrases très courtes avec leur voisine (« Simple ? Oui ! »).

    Le clonage de voix invente des mots sur un « Oui ! » isolé ; lu dans une phrase plus longue, il est naturel.
    Une pause choisie (balise, paragraphe, points de suspension) n'est jamais supprimée.
    """
    out: list[Segment] = []
    for seg in segs:
        prev = out[-1] if out else None
        if prev and prev.pause <= PAUSES["!"] and (len(prev.text) < min_chars or len(seg.text) < min_chars)                 and len(prev.text) + len(seg.text) < max_chars:
            out[-1] = Segment(f"{prev.text} {seg.text}", seg.pause)
        else:
            out.append(Segment(seg.text, seg.pause))
    return out


def plain(text: str) -> str:
    """Le texte sans balises [pause] (pour les moteurs qui lisent le texte d'un bloc)."""
    return re.sub(r"[ \t]+", " ", TAG.sub(" ", text)).strip()


# --------------------------------------------------------------------------- assemblage audio

def trim(x: np.ndarray, sr: int, floor_db: float = -40.0, keep: float = 0.03) -> np.ndarray:
    """Retire les silences du début et de la fin d'une phrase (avec 30 ms de marge et un fondu de 5 ms)."""
    x = np.asarray(x, dtype=np.float32)
    if not len(x) or not np.abs(x).max():
        return x[:0]
    hop = max(1, sr // 100)
    n = len(x) // hop
    if n < 2:
        return x
    env = np.abs(x[: n * hop]).reshape(n, hop).max(axis=1)
    loud = np.nonzero(env > env.max() * 10 ** (floor_db / 20))[0]
    a = max(0, loud[0] * hop - int(keep * sr))
    b = min(len(x), (loud[-1] + 1) * hop + int(keep * sr))
    y = x[a:b].copy()
    f = min(len(y) // 2, int(0.005 * sr))
    if f:
        ramp = np.linspace(0, 1, f, dtype=np.float32)
        y[:f] *= ramp
        y[-f:] *= ramp[::-1]
    return y


def assemble(pieces: list[tuple[np.ndarray, float]], sr: int) -> tuple[np.ndarray, list[tuple[float, float]]]:
    """Met bout à bout des phrases (rognées) séparées par leurs pauses.

    Renvoie l'audio et, pour chaque phrase, ses heures de début et de fin (pour minuter les sous-titres).
    """
    parts, spans, t = [], [], 0
    for samples, pause in pieces:
        y = trim(samples, sr)
        spans.append((t / sr, (t + len(y)) / sr))
        parts += [y, np.zeros(int(round(max(0.0, pause) * sr)), dtype=np.float32)]
        t += len(y) + len(parts[-1])
    audio = np.concatenate(parts) if parts else np.zeros(int(0.1 * sr), dtype=np.float32)
    return audio, spans


# --------------------------------------------------------------------------- nombres en lettres

_FR_U = ("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize").split()
_FR_T = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def _fr_99(n: int) -> str:
    if n < 17:
        return _FR_U[n]
    if n < 20:
        return "dix-" + _FR_U[n - 10]
    t, u = divmod(n, 10)
    if t == 7:
        return "soixante et onze" if u == 1 else "soixante-" + _fr_99(n - 60)
    if t == 8:
        return "quatre-vingts" if u == 0 else "quatre-vingt-" + _FR_U[u]
    if t == 9:
        return "quatre-vingt-" + _fr_99(n - 80)
    return _FR_T[t] + ("" if u == 0 else " et un" if u == 1 else "-" + _FR_U[u])


def _fr_999(n: int) -> str:
    h, r = divmod(n, 100)
    if not h:
        return _fr_99(r)
    head = "cent" if h == 1 else _FR_U[h] + " cent" + ("s" if not r else "")
    return head + (" " + _fr_99(r) if r else "")


def _fr(n: int) -> str:
    if n == 0:
        return "zéro"
    parts = []
    for value, one, many in ((10 ** 9, "un milliard", "milliards"), (10 ** 6, "un million", "millions")):
        q, n = divmod(n, value)
        if q:
            parts.append(one if q == 1 else f"{_fr(q)} {many}")
    q, n = divmod(n, 1000)
    if q:   # « mille » est invariable, et « cent » / « vingt » devant lui aussi
        parts.append("mille" if q == 1 else re.sub(r"(cent|vingt)s$", r"\1", _fr_999(q)) + " mille")
    if n:
        parts.append(_fr_999(n))
    return " ".join(parts)


_EN_U = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_EN_T = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def _en_999(n: int) -> str:
    h, r = divmod(n, 100)
    out = [_EN_U[h] + " hundred"] if h else []
    if r:
        out.append(_EN_U[r] if r < 20 else _EN_T[r // 10] + ("-" + _EN_U[r % 10] if r % 10 else ""))
    return " ".join(out)


def _en(n: int, year: bool = False) -> str:
    if n == 0:
        return "zero"
    if year and 1100 <= n <= 1999 and n % 100:     # 1990 → nineteen ninety
        hi, lo = divmod(n, 100)
        return f"{_en_999(hi)} {'oh ' + _EN_U[lo] if lo < 10 else _en_999(lo)}"
    parts = []
    for value, word in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        q, n = divmod(n, value)
        if q:
            parts.append(f"{_en(q)} {word}")
    if n:
        parts.append(_en_999(n))
    return " ".join(parts)


_ES_U = ("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
         "diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro veinticinco veintiséis "
         "veintisiete veintiocho veintinueve").split()
_ES_T = "_ _ _ treinta cuarenta cincuenta sesenta setenta ochenta noventa".split()
_ES_H = ("_ ciento doscientos trescientos cuatrocientos quinientos seiscientos setecientos ochocientos "
         "novecientos").split()


def _es_999(n: int) -> str:
    h, r = divmod(n, 100)
    if n == 100:
        return "cien"
    out = [_ES_H[h]] if h else []
    if r:
        out.append(_ES_U[r] if r < 30 else _ES_T[r // 10] + (" y " + _ES_U[r % 10] if r % 10 else ""))
    return " ".join(out)


def _es_apocope(words: str) -> str:
    """« uno » devient « un » devant « mil » ou « millones » (veintiún mil)."""
    return re.sub(r"uno$", "ún" if words.endswith("veintiuno") else "un", words)


def _es(n: int) -> str:
    if n == 0:
        return "cero"
    parts = []
    q, n = divmod(n, 10 ** 6)
    if q:
        parts.append("un millón" if q == 1 else f"{_es_apocope(_es(q))} millones")
    q, n = divmod(n, 1000)
    if q:
        parts.append("mil" if q == 1 else f"{_es_apocope(_es_999(q))} mil")
    if n:
        parts.append(_es_999(n))
    return " ".join(parts)


_IT_U = ("zero uno due tre quattro cinque sei sette otto nove dieci undici dodici tredici quattordici quindici "
         "sedici diciassette diciotto diciannove").split()
_IT_T = "_ _ venti trenta quaranta cinquanta sessanta settanta ottanta novanta".split()


def _it_999(n: int) -> str:
    h, r = divmod(n, 100)
    out = "" if not h else "cento" if h == 1 else _IT_U[h] + "cento"
    if r:
        if r < 20:
            tail = _IT_U[r]
        else:
            t, u = divmod(r, 10)
            tens = _IT_T[t][:-1] if u in (1, 8) else _IT_T[t]       # ventuno, ventotto
            tail = tens + ("" if not u else "tré" if u == 3 else _IT_U[u])
        if out and tail[0] == "o":                                  # centotto, centottanta
            out = out[:-1]
        out += tail
    return out


def _it(n: int) -> str:
    if n == 0:
        return "zero"
    parts = []
    q, n = divmod(n, 10 ** 6)
    if q:
        parts.append("un milione" if q == 1 else f"{_it(q)} milioni")
    q, n = divmod(n, 1000)
    if q:
        parts.append("mille" if q == 1 else re.sub(r"uno$", "un", _it_999(q)) + "mila")   # ventunmila
    if n:
        parts.append(_it_999(n))
    return " ".join(parts)


_WORDS = {"fr": _fr, "en": _en, "es": _es, "it": _it}
_DECIMAL = {"fr": "virgule", "en": "point", "es": "coma", "it": "virgola"}


def number_words(n: int, lang: str = "fr") -> str:
    """Un entier en toutes lettres (fr, en, es, it)."""
    return _WORDS.get(lang, _fr)(n)


def _lang(lang: str) -> str:
    lang = (lang or "fr")[:2].lower()
    return lang if lang in _WORDS else "fr"


def _num_pattern(lang: str) -> str:
    if lang == "en":
        return r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
    if lang == "fr":
        return r"\d{1,3}(?:[   ]\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
    return r"\d{1,3}(?:[.   ]\d{3})+(?:,\d+)?|\d+(?:,\d+)?"


def _read_number(s: str, lang: str, year: bool = False) -> str:
    """« 1 250,5 » → « mille deux cent cinquante virgule cinq »."""
    dec_sep = "." if lang == "en" else ","
    whole, _, dec = s.partition(dec_sep)
    whole = re.sub(r"\D", "", whole)
    if len(whole) > 12:
        return " ".join(number_words(int(c), lang) for c in whole)
    words = _en(int(whole), year) if lang == "en" else number_words(int(whole), lang)
    if dec:
        if lang == "en":
            tail = " ".join(_EN_U[int(c)] for c in dec)
        else:
            zeros = len(dec) - len(dec.lstrip("0"))
            tail = " ".join([number_words(0, lang)] * zeros + ([number_words(int(dec), lang)] if dec.strip("0") else []))
        words += f" {_DECIMAL[lang]} {tail}"
    return words


# --------------------------------------------------------------------------- texte parlé

_LETTERS = {
    "fr": "a bé cé dé e èf jé ach i ji ka èl èm ène o pé ku èr èss té u vé double-vé ixe i-grec zède",
    "es": "a be ce de e efe ge hache i jota ka ele eme ene o pe cu erre ese te u uve uve-doble equis i-griega zeta",
    "it": "a bi ci di e effe gi acca i i-lunga cappa elle emme enne o pi cu erre esse ti u vu doppia-vu ics "
          "ipsilon zeta",
}
_CURRENCY = {   # symbole → (singulier, pluriel) en fr, en, es, it
    "€": (("euro", "euros"), ("euro", "euros"), ("euro", "euros"), ("euro", "euro")),
    "$": (("dollar", "dollars"), ("dollar", "dollars"), ("dólar", "dólares"), ("dollaro", "dollari")),
    "£": (("livre", "livres"), ("pound", "pounds"), ("libra", "libras"), ("sterlina", "sterline")),
}
_SAY = {   # fr, en, es, it
    "percent": ("pour cent", "percent", "por ciento", "per cento"),
    "and": ("et", "and", "y", "e"),
    "plus": ("plus", "plus", "más", "più"),
    "equals": ("égale", "equals", "igual a", "uguale a"),
    "at": ("arobase", "at", "arroba", "chiocciola"),
    "dot": ("point", "dot", "punto", "punto"),
    "degrees": ("degrés", "degrees", "grados", "gradi"),
    "hours": ("heures", "hours", "horas", "ore"),
}
_UNITS = {   # unité après un nombre → (fr, en, es, it), au pluriel
    "km": ("kilomètres", "kilometers", "kilómetros", "chilometri"),
    "kg": ("kilos", "kilos", "kilos", "chili"),
    "cm": ("centimètres", "centimeters", "centímetros", "centimetri"),
    "mm": ("millimètres", "millimeters", "milímetros", "millimetri"),
    "min": ("minutes", "minutes", "minutos", "minuti"),
    "fps": ("images par seconde", "frames per second", "imágenes por segundo", "fotogrammi al secondo"),
    "Go": ("gigaoctets", "gigabytes", "gigabytes", "gigabyte"),
    "Mo": ("mégaoctets", "megabytes", "megabytes", "megabyte"),
    "GB": ("gigaoctets", "gigabytes", "gigabytes", "gigabyte"),
    "MB": ("mégaoctets", "megabytes", "megabytes", "megabyte"),
}
_IDX = {"fr": 0, "en": 1, "es": 2, "it": 3}
_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")
_URL = re.compile(r"\b(?:https?://)?(?:www\.)?((?:[\w-]+\.)+(?:com|fr|org|net|io|it|es|eu|ai|app|dev|be|ch|ca|co))"
                  r"\b(?:/[^\s,;]*)?", re.I)
_EMAIL = re.compile(r"\b([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)\b")


def parse_lexicon(text: str | None) -> list[tuple[re.Pattern, str]]:
    """Dictionnaire de prononciation : une règle par ligne, « mot = prononciation » (# pour un commentaire)."""
    rules = []
    for line in (text or "").splitlines():
        line = line.split("#", 1)[0]
        m = re.match(r"\s*(.+?)\s*(?:=|→|->)\s*(.+?)\s*$", line)
        if m:
            rules.append((m.group(1), m.group(2)))
    rules.sort(key=lambda r: -len(r[0]))   # « MSV Pro » avant « MSV »
    return [(re.compile(rf"(?<!\w){re.escape(k)}(?!\w)", re.I), v) for k, v in rules]


def spell(word: str, lang: str = "fr") -> str:
    """Épelle un sigle : « MSV » → « èm èss vé »."""
    names = _LETTERS.get(_lang(lang))
    if not names:
        return " ".join(word)
    table = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", names.split()))
    return " ".join(table.get(c, c) for c in word.upper())


def _fr_ordinal(n: int, feminine: bool = False) -> str:
    if n == 1:
        return "première" if feminine else "premier"
    w = _fr(n)
    w = re.sub(r"(cent|vingt)s$", r"", w)
    w = w[:-1] if w.endswith("e") else w
    w = re.sub(r"cinq$", "cinqu", re.sub(r"neuf$", "neuv", w))
    return w + "ième"


def _en_ordinal(n: int) -> str:
    w = _en(n)
    irregular = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
                 "nine": "ninth", "twelve": "twelfth"}
    head, _, last = w.rpartition(" ") if " " in w else ("", "", w)
    pre, _, unit = last.rpartition("-")
    unit = irregular.get(unit) or (unit[:-1] + "ieth" if unit.endswith("y") else unit + "th")
    last = f"{pre}-{unit}" if pre else unit
    return f"{head} {last}".strip()


def spoken(text: str, lang: str = "fr", lexicon: str | list | None = None) -> str:
    """Le texte tel qu'il doit être prononcé : dictionnaire, adresses, nombres, symboles et sigles en lettres."""
    lang = _lang(lang)
    i = _IDX[lang]
    say = {k: v[i] for k, v in _SAY.items()}
    t = TAG.sub(" ", text)
    for pat, rep in (parse_lexicon(lexicon) if isinstance(lexicon, str) or lexicon is None else lexicon):
        t = pat.sub(rep, t)
    t = _EMOJI.sub(" ", t)
    t = _EMAIL.sub(lambda m: f"{m.group(1)} {say['at']} {m.group(2)}", t)
    t = _URL.sub(lambda m: m.group(1).replace(".", f" {say['dot']} "), t)
    t = re.sub(r"[*_#•|~^`]+", " ", t)
    num = _num_pattern(lang)
    read = lambda s: _read_number(s, lang)  # noqa: E731

    if lang == "fr":
        def hour(m):
            h = int(m.group(1))
            words = "une" if h == 1 else _fr(h)
            return f"{words} heure{'s' if h > 1 else ''}" + (f" {_fr(int(m.group(2)))}" if m.group(2) else "")
        t = re.sub(r"\b([01]?\d|2[0-3])\s?h\s?([0-5]\d)?\b", hour, t)
        t = re.sub(r"\b1(?:er|re|ère)\b", lambda m: _fr_ordinal(1, m.group(0) != "1er"), t)
        t = re.sub(r"\b(\d+)(?:e|è|ème|eme)\b", lambda m: _fr_ordinal(int(m.group(1))), t)
    elif lang == "en":
        t = re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", lambda m: _en_ordinal(int(m.group(1))), t)

    def money(m):
        n_txt = m.group("n")
        return f"{read(n_txt)} {_CURRENCY[m.group('s')][i][0 if re.fullmatch(r'0*1', n_txt) else 1]}"
    t = re.sub(rf"(?P<n>{num})\s?(?P<s>[€$£])", money, t)
    t = re.sub(rf"(?P<s>[€$£])\s?(?P<n>{num})", money, t)
    t = re.sub(rf"({num})\s?%", lambda m: f"{read(m.group(1))} {say['percent']}", t)
    t = re.sub(rf"({num})\s?°C?\b", lambda m: f"{read(m.group(1))} {say['degrees']}", t)
    units = "|".join(sorted(_UNITS, key=len, reverse=True))
    t = re.sub(rf"({num})\s?({units})\b", lambda m: f"{read(m.group(1))} {_UNITS[m.group(2)][i]}", t)
    t = re.sub(rf"({num})([A-Z])\b", lambda m: f"{read(m.group(1))} {spell(m.group(2), lang)}", t)   # 4K
    t = re.sub(r"\b([12]\d{3})\b", lambda m: _read_number(m.group(1), lang, year=True), t) if lang == "en" else t
    t = re.sub(num, lambda m: read(m.group(0)), t)
    t = re.sub(r"\b([B-DF-HJ-NP-TV-XZ]{2,6})\b", lambda m: spell(m.group(1), lang), t)   # sigle sans voyelle
    t = re.sub(r"\s&\s", f" {say['and']} ", t)
    t = re.sub(r"\s\+\s?", f" {say['plus']} ", t)
    t = re.sub(r"\s=\s", f" {say['equals']} ", t)
    t = re.sub(r"%", f" {say['percent']}", t)
    return re.sub(r"\s+", " ", t).strip()
