"""Étape 2 : captures d'écran réelles de l'interface (pilotée automatiquement dans Edge).

    montage_studio\\.venv\\Scripts\\python.exe montage_studio\\app.py --no-browser --port 7866
    uv run --no-project --with playwright python promo\\capture_ui.py --port 7866 --lang it fr en es

Playwright utilise le navigateur Edge déjà installé (rien à télécharger).
Les libellés à cliquer viennent des traductions de l'application (core/i18n.py).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT.parent / "montage_studio"))
from core.i18n import LANG, _  # noqa: E402  (module sans dépendance)

NEUTRAL_FOLDER = "D:\\Video\\Shorts"   # remplace le chemin réel du PC (vie privée)
VOICE_SAMPLE = {
    "it": "15 gennaio 1919, Boston.\n---\nNel quartiere del North End, una cisterna gigante domina il porto.",
    "fr": "15 janvier 1919, Boston.\n---\nDans le quartier du North End, une cuve géante domine le port.",
    "en": "January 15, 1919. Boston.\n---\nIn the North End, a giant tank towers over the harbor.",
    "es": "15 de enero de 1919, Boston.\n---\nEn el barrio del North End, un tanque gigante domina el puerto.",
}


def capture(page, port: int, lang: str) -> None:
    LANG.set(lang)
    clips = [str(BUILD / "footage_tramonto.mp4"), str(BUILD / "footage_aurora.mp4")]
    page.goto(f"http://127.0.0.1:{port}/{lang}/?__theme=dark")
    page.wait_for_selector("#entete")

    # -- Montage : import, recadrage 9:16, extrait dans la timeline, convertisseur de temps
    page.locator("input[type=file]").first.set_input_files(clips)
    page.wait_for_function("document.querySelectorAll('[data-testid=\"image\"] img, .image-frame img').length > 0",
                           timeout=60000)
    page.get_by_text(_("Recadrer l'image")).click()
    page.get_by_label("9:16").first.check()
    page.wait_for_timeout(2500)
    page.get_by_role("button", name=_("Ajouter l'extrait à la timeline")).click()
    page.wait_for_timeout(1500)
    page.get_by_text(_("Convertisseur de temps")).click()
    page.get_by_placeholder("1:30 · 90 · 1h 2m 3s · 2,5 min").fill("1h 2m 3s")
    page.wait_for_timeout(1500)
    page.screenshot(path=str(BUILD / f"ui_montage_{lang}.png"), full_page=True)

    # -- Voix off
    page.get_by_role("tab", name=_("Voix off")).click()
    page.get_by_label(_("Texte de la voix off")).fill(VOICE_SAMPLE[lang])
    page.wait_for_timeout(800)
    page.screenshot(path=str(BUILD / f"ui_voice_{lang}.png"), full_page=True)

    # -- Série (dossier neutre à la place du chemin réel)
    page.get_by_role("tab", name=_("Shorts en série")).click()
    page.get_by_label(_("Dossier de base des chemins du CSV")).fill(NEUTRAL_FOLDER)
    page.wait_for_timeout(800)
    page.screenshot(path=str(BUILD / f"ui_series_{lang}.png"), full_page=True)

    # -- Outils : effacement de logo avec aperçu
    page.get_by_role("tab", name=_("Outils rapides")).click()
    page.wait_for_timeout(800)
    page.locator("input[type=file]").nth(-2).set_input_files(str(BUILD / "demo_logo_msv.mp4"))
    page.wait_for_timeout(1500)
    for label, value in ((_("Largeur (%)"), "19"), (_("Hauteur (%)"), "33")):   # zone du logo de démo
        box = page.get_by_label(f"number input for {label}")
        box.fill(value)
        box.press("Enter")
    page.wait_for_timeout(500)
    page.get_by_label(_("bas droite")).first.check()
    page.wait_for_timeout(500)
    page.get_by_role("button", name=_("Aperçu"), exact=True).click()
    page.wait_for_timeout(5000)
    page.screenshot(path=str(BUILD / f"ui_tools_{lang}.png"), full_page=True)


def main(port: int, langs: list[str]) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        for lang in langs:
            page = browser.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
            capture(page, port, lang)
            page.close()
            print("✓ captures", lang)
        browser.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7866)
    ap.add_argument("--lang", nargs="+", default=["it"])
    a = ap.parse_args()
    main(a.port, a.lang)
