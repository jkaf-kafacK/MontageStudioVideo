"""Page /pro. Édition libre : passage à l'édition pro (bouton « ⭐ Passer à Pro »). Édition pro : licence (bouton
« 🔑 Licence Pro ») : état, activation d'une clé, retrait.

La page présente MSV Pro, puis :
  * l'ouvre si elle tourne déjà sur cet ordinateur (port 7870) ;
  * la démarre si elle est installée à côté (lancer_windows_pro.bat), dans sa propre fenêtre de console : la première
    fois, l'installation de son environnement prend quelques minutes ;
  * sinon explique comment l'obtenir (adresse de vente : MSV_PRO_URL, vide tant que la vente n'est pas ouverte).
Les deux éditions restent séparées : environnements, FFmpeg et ports différents (voir core/edition.py, TIERS.md).
"""
from __future__ import annotations

import html
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from . import edition, licence, updates
from .i18n import LANG, LANGS, _
from .paths import APP_DIR

PRO_PORT = 7870                      # port de lancer_windows_pro.bat (l'édition libre reste sur 7860)
START_WAIT = 600                     # un démarrage est « en cours » pendant 10 min au plus (1re installation)
_started: dict[str, float] = {}


def pro_url() -> str:
    """Page de vente de MSV Pro (vide tant que la vente n'est pas ouverte) : variable MSV_PRO_URL, sinon fichier
    PRO_URL à côté de l'application (écrit par l'installateur). Modèle de page : docs/pro/index.html."""
    url = os.environ.get("MSV_PRO_URL", "").strip()
    if not url:
        try:
            url = (APP_DIR / "PRO_URL").read_text(encoding="utf-8").strip()
        except OSError:
            url = ""
    return url if url.startswith(("https://", "http://")) else ""


def launcher() -> Optional[Path]:
    """Lanceur de l'édition pro installé à côté de cette copie de MSV (Windows), sinon None."""
    p = APP_DIR / "lancer_windows_pro.bat"
    return p if os.name == "nt" and p.is_file() else None


def running(port: int = PRO_PORT, timeout: float = 0.8) -> bool:
    """L'édition pro de MSV répond-elle sur ce port ?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/editeur/config", timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8")).get("edition") == edition.PRO
    except (OSError, ValueError, AttributeError):
        return False


def state() -> dict:
    """« ouvert » (adresse prête), « demarrage », « installe » (peut être démarrée) ou « absent »."""
    url = f"http://127.0.0.1:{PRO_PORT}/"
    if running():
        return {"state": "ouvert", "url": url}
    if launcher() and time.time() - _started.get("t", 0) < START_WAIT:
        return {"state": "demarrage", "url": url}
    if launcher():
        return {"state": "installe", "url": url}
    return {"state": "absent", "buy": pro_url()}


def start() -> dict:
    """Démarre l'édition pro dans sa fenêtre de console (comme un double-clic sur lancer_windows_pro.bat)."""
    st = state()
    if st["state"] != "installe":
        return st
    env = {k: v for k, v in os.environ.items() if k not in ("MSV_EDITION", "MONTAGE_FFMPEG")}
    env["MSV_NO_BROWSER"] = "1"      # la page /pro ouvre elle-même la Pro quand elle est prête
    subprocess.Popen(["cmd.exe", "/c", str(launcher())], cwd=str(APP_DIR), env=env,
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    _started["t"] = time.time()
    return {"state": "demarrage", "url": f"http://127.0.0.1:{PRO_PORT}/"}


# --------------------------------------------------------------------------- page

INCLUDED = [
    ("🛡", "Aucun composant GPL : pensée pour un usage professionnel et commercial."),
    ("🎞", "Export en 4K."),
    ("🔁", "Plusieurs vidéos d'un coup : les mêmes réglages appliqués à toutes."),
    ("🎛", "Export vers Premiere Pro et DaVinci Resolve, pour finir le montage dans ces logiciels."),
    ("🖼", "Miniatures YouTube de tendance : podcast face-à-face, réaction, avant / après, top, tuto, alerte ; visages cadrés tout seuls, 3 variantes pour les tests A/B."),
    ("⚡", "Vidéo encodée par la carte graphique (NVIDIA, Intel, AMD) ou par Windows."),
    ("🖥", "Application de bureau : l'éditeur dans sa propre fenêtre, sans navigateur."),
    ("🔑", "Clé de licence personnelle, vérifiée sans connexion Internet."),
    ("🎬", "Les mêmes outils de montage : sous-titres animés, recadrage sur le visage, images clés, filtres LUT, "
          "éditeur avec timeline."),
]


def page_html(lang: str) -> str:
    e = html.escape
    st = state()
    items = "".join(f"<li><span>{ico}</span>{e(_(txt))}</li>" for ico, txt in INCLUDED)
    labels = {"start": _("Démarrer MSV Pro"), "open": _("Ouvrir MSV Pro"),
              "starting": _("MSV Pro démarre… La première fois, l'installation prend quelques minutes : "
                            "laisse sa fenêtre noire ouverte."),
              "late": _("MSV Pro met du temps à démarrer. Regarde sa fenêtre noire pour voir où il en est."),
              "error": _("Impossible de démarrer MSV Pro."),
              "confirm": _("Retirer la licence de cet ordinateur ? Les extras Pro seront verrouillés jusqu'à la "
                           "prochaine activation.")}
    if edition.is_pro():                          # édition pro : la page sert à la licence
        action = licence_card()
    elif st["state"] == "absent":
        action = f"<p class='note'>{e(_('MSV Pro n’est pas installé sur cet ordinateur.'))}</p>"
        action += (f"<a class='bouton' href='{e(st['buy'])}' target='_blank' rel='noopener'>{e(_('Obtenir MSV Pro'))}</a>"
                   if st["buy"] else f"<p class='note'>{e(_('La vente de MSV Pro ouvrira bientôt.'))}</p>")
    else:
        label = labels["open"] if st["state"] == "ouvert" else labels["start"]
        action = f"<button id='go' class='bouton' data-state='{st['state']}'>{e(label)}</button>" \
                 f"<p id='msg' class='note' role='status' aria-live='polite'></p>"
    return f"""<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{"MSV Pro · " + e(_("Licence")) if edition.is_pro() else "MSV Pro"}</title><link rel="icon" href="/favicon.ico">
<style>
:root {{ --fond:#FBF7F1; --carte:#fff; --texte:#2B2118; --doux:#6B5D50; --ligne:#EBD7BC; --accent:#A85F05; color-scheme:light; }}
@media (prefers-color-scheme: dark) {{ :root {{ --fond:#17130E; --carte:#211B14; --texte:#F3E9DC; --doux:#BFAE99;
  --ligne:#42372A; --accent:#D9943A; color-scheme:dark; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--fond); color:var(--texte); font:16px/1.5 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width:720px; margin:0 auto; padding:32px 16px 48px; }}
.retour {{ color:var(--doux); text-decoration:none; font-size:14px; }}
h1 {{ font-size:34px; margin:18px 0 4px; }} h1 b {{ color:var(--accent); }}
.sous {{ color:var(--doux); margin:0 0 24px; }}
.carte {{ background:var(--carte); border:1px solid var(--ligne); border-radius:14px; padding:18px 20px; margin-bottom:16px; }}
h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.05em; color:var(--doux); margin:0 0 10px; }}
ul {{ margin:0; padding:0; list-style:none; display:grid; gap:10px; }}
ul.inclus li {{ display:flex; gap:12px; }} ul.inclus li span {{ width:24px; flex:none; text-align:center; }}
ul.bientot {{ display:flex; flex-wrap:wrap; gap:8px; }}
ul.bientot li {{ border:1px dashed var(--ligne); border-radius:999px; padding:3px 12px; color:var(--doux); font-size:14px; }}
.bouton {{ display:inline-block; border:0; border-radius:12px; padding:12px 22px; font:inherit; font-weight:700; cursor:pointer;
  color:#fff; background:linear-gradient(135deg,#C47A12,#A85F05); text-decoration:none; }}
.bouton:disabled {{ opacity:.6; cursor:progress; }}
.bouton:focus-visible, .retour:focus-visible {{ outline:3px solid var(--accent); outline-offset:2px; }}
.note {{ color:var(--doux); margin:10px 0 0; }}
textarea {{ width:100%; font:13px/1.4 Consolas, monospace; border:1px solid var(--ligne); border-radius:10px; padding:10px;
  background:var(--fond); color:var(--texte); margin:6px 0 10px; resize:vertical; }}
.lien {{ background:none; border:0; color:var(--doux); text-decoration:underline; cursor:pointer; font:inherit; }}
.etat-ok {{ color:#2E7D32; font-weight:600; }} .etat-non {{ color:var(--accent); font-weight:600; }}
@media (prefers-color-scheme: dark) {{ .etat-ok {{ color:#81C784; }} }}
</style></head>
<body><main>
<a class="retour" href="/{lang}/">◀ {e(_("Retour à MSV"))}</a>
<h1>⭐ MSV <b>Pro</b></h1>
<p class="sous">{e(_("L'édition professionnelle de Montage Studio Video."))}</p>
<section class="carte"><h2>{e(_("Ce que Pro apporte"))}</h2><ul class="inclus">{items}</ul></section>
<section class="carte">{action}</section>
<section class="carte" id="maj"><h2>{e(_("Mises à jour"))}</h2>
  <p class="note" id="maj-etat">{e(_("Version installée : {v}", v=updates.__version__))}</p>
  <button id="maj-verifier" class="lien">{e(_("Vérifier maintenant"))}</button>
  <button id="maj-installer" class="bouton" hidden>{e(_("Télécharger et installer"))}</button>
  <p class="note" id="maj-msg" role="status" aria-live="polite"></p>
</section>
</main>
<script>
const L = {json.dumps(labels, ensure_ascii=False)};
const LANG_PATH = "langue/{lang}";                     // la Pro s'ouvre dans la même langue
const go = document.getElementById("go"), msg = document.getElementById("msg");
async function etat() {{ return (await fetch("/api/pro/etat")).json(); }}
async function attendre(url) {{
  for (let i = 0; i < 400; i++) {{                      // jusqu'à 10 minutes (première installation)
    const s = await etat().catch(() => ({{}}));
    if (s.state === "ouvert") {{ location.href = s.url + LANG_PATH; return; }}
    if (i === 120) msg.textContent = L.late;
    await new Promise((r) => setTimeout(r, 1500));
  }}
}}
if (go) go.onclick = async () => {{
  if (go.dataset.state === "ouvert") {{ location.href = "{st.get('url', '')}" + LANG_PATH; return; }}
  go.disabled = true; msg.textContent = L.starting;
  try {{
    const s = await (await fetch("/api/pro/ouvrir", {{ method: "POST" }})).json();
    if (s.state === "ouvert") location.href = s.url + LANG_PATH; else await attendre(s.url);
  }} catch (err) {{ msg.textContent = L.error; go.disabled = false; }}
}};
if (go && go.dataset.state === "demarrage") go.click();   // déjà en train de démarrer : on attend
const act = document.getElementById("lic-activer"), del = document.getElementById("lic-retirer");
const lmsg = document.getElementById("lic-msg");
if (act) act.onclick = async () => {{
  act.disabled = true; lmsg.textContent = "";
  const r = await fetch("/api/pro/licence", {{ method: "POST", headers: {{ "Content-Type": "application/json" }},
    body: JSON.stringify({{ cle: document.getElementById("lic-cle").value }}) }});
  if (r.ok) {{ location.reload(); return; }}
  lmsg.textContent = (await r.json().catch(() => ({{}}))).detail || "Erreur";
  act.disabled = false;
}};
const MAJ = {json.dumps({"none": _("Les mises à jour ne sont pas configurées sur cet ordinateur."),
                          "uptodate": _("MSV est à jour."), "available": _("Nouvelle version disponible : {v}"),
                          "checking": _("Vérification…"), "downloading": _("Téléchargement et vérification de l'installateur…"),
                          "launched": _("L'installateur s'ouvre : suis ses étapes (il demandera de fermer MSV).")},
                         ensure_ascii=False)};
async function majVerifier() {{
  const msg = document.getElementById("maj-msg"), inst = document.getElementById("maj-installer");
  msg.textContent = MAJ.checking;
  const s = await (await fetch("/api/maj")).json().catch(() => ({{}}));
  inst.hidden = !s.disponible;
  msg.textContent = s.erreur || (!s.configure ? MAJ.none : s.disponible
    ? MAJ.available.replace("{{v}}", s.version) + (s.notes ? " · " + s.notes : "") : MAJ.uptodate);
}}
document.getElementById("maj-verifier").onclick = majVerifier;
document.getElementById("maj-installer").onclick = async () => {{
  const msg = document.getElementById("maj-msg"), inst = document.getElementById("maj-installer");
  inst.disabled = true; msg.textContent = MAJ.downloading;
  const r = await fetch("/api/maj/installer", {{ method: "POST" }});
  msg.textContent = r.ok ? MAJ.launched : ((await r.json().catch(() => ({{}}))).detail || "Erreur");
  inst.disabled = false;
}};
majVerifier();
if (del) del.onclick = async () => {{
  if (!confirm(L.confirm)) return;
  await fetch("/api/pro/licence", {{ method: "DELETE" }}); location.reload();
}};
</script>
</body></html>"""


def licence_card() -> str:
    """Carte « Licence » de l'édition pro : état, champ pour coller la clé, activation, retrait."""
    e = html.escape
    st = licence.status()
    if st["active"]:
        fin = _("permanente") if not st["fin"] else _("jusqu'au {date}", date=st["fin"])
        etat = f"<p class='etat-ok'>✅ {e(_('Licence active : {nom}', nom=st['nom']))} · {e(fin)}</p>"
        retirer = f"<button id='lic-retirer' class='lien'>{e(_('Retirer la licence de cet ordinateur'))}</button>"
    else:
        etat = f"<p class='etat-non'>{e(_('Aucune licence active : les extras Pro (4K, série, Premiere / Resolve, miniatures) sont verrouillés.'))}</p>"
        if st["erreur"]:
            etat += f"<p class='note'>{e(_('Licence enregistrée refusée : {erreur}', erreur=st['erreur']))}</p>"
        retirer = ""
    return (f"<h2>{e(_('Licence'))}</h2>{etat}"
            f"<label for='lic-cle'>{e(_('Clé de licence (reçue à l’achat)'))}</label>"
            f"<textarea id='lic-cle' rows='3' placeholder='MSV-PRO-…' spellcheck='false'></textarea>"
            f"<button id='lic-activer' class='bouton'>{e(_('Activer'))}</button> {retirer}"
            f"<p id='lic-msg' class='note' role='alert'></p>")


def router() -> APIRouter:
    r = APIRouter(include_in_schema=False)

    @r.get("/pro")
    def page(lang: str = Query("fr")):
        lang = lang if lang in LANGS else "fr"
        token = LANG.set(lang)
        try:
            return HTMLResponse(page_html(lang), headers={"Cache-Control": "no-cache"})
        finally:
            LANG.reset(token)

    @r.get("/api/pro/etat")
    def etat():
        return state()

    @r.post("/api/pro/ouvrir")
    def ouvrir():
        return start()

    @r.get("/api/pro/licence")
    def licence_etat():
        return licence.status()

    @r.post("/api/pro/licence")
    def licence_activer(body: dict):
        from fastapi import HTTPException
        if not edition.is_pro():
            raise HTTPException(400, _("La licence s'active dans MSV Pro."))
        try:
            return licence.activate(str(body.get("cle") or ""))
        except ValueError as err:
            raise HTTPException(400, str(err))

    @r.delete("/api/pro/licence")
    def licence_retirer():
        return licence.deactivate()

    @r.get("/api/maj")
    def maj():
        """Mises à jour (core/updates.py) : rien n'est demandé à Internet sans adresse configurée."""
        return updates.check()

    @r.post("/api/maj/installer")
    def maj_installer():
        from fastapi import HTTPException
        try:
            updates.launch(updates.download())
        except (ValueError, OSError) as err:
            raise HTTPException(400, str(err)[:300])
        return {"ok": True}

    return r
