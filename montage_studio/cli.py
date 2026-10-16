"""Montage Studio en ligne de commande (pratique pour automatiser).

Exemples :
  python cli.py rendu projets/mon_projet.json -o sorties/final.mp4
  python cli.py serie templates/short_storytelling.json exemples/serie_storytelling.csv --base D:/chaine --sortie sorties/lot1
  python cli.py dossier templates/short_clip_parle.json D:/rushs --duree 59 --sortie sorties/clips
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core import batch
from core.render import load_project, merge_defaults, render_project


def bar(frac: float, msg: str) -> None:
    n = int(frac * 30)
    sys.stdout.write(f"\r[{'█' * n}{'·' * (30 - n)}] {frac * 100:5.1f}%  {msg[:60]:<60}")
    sys.stdout.flush()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description="Montage Studio (ligne de commande)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("rendu", help="rendre un projet JSON")
    r.add_argument("projet")
    r.add_argument("-o", "--sortie", default=None)
    r.add_argument("--qualite", choices=["aperçu", "standard", "haute"], default=None)

    s = sub.add_parser("serie", help="une vidéo par ligne d'un CSV")
    s.add_argument("modele")
    s.add_argument("csv")
    s.add_argument("--base", default=None, help="dossier de base des chemins (défaut : dossier du CSV)")
    s.add_argument("--sortie", default="sorties/serie")
    s.add_argument("--qualite", choices=["aperçu", "standard", "haute"], default="haute")

    d = sub.add_parser("dossier", help="une vidéo par fichier d'un dossier")
    d.add_argument("modele")
    d.add_argument("dossier")
    d.add_argument("--duree", type=float, default=59)
    d.add_argument("--titre-nom", action="store_true", help="titre = nom du fichier")
    d.add_argument("--sortie", default="sorties/dossier")
    d.add_argument("--qualite", choices=["aperçu", "standard", "haute"], default="haute")

    a = ap.parse_args()
    if a.cmd == "rendu":
        proj = load_project(a.projet)
        out = a.sortie or f"sorties/{proj.get('name', 'video')}.mp4"
        res = render_project(proj, out, progress=bar, quality=a.qualite)
        print(f"\n✅ {res['video']} ({res['duration']:.1f} s, en {res['seconds']:.0f} s)\n{res['log']}")
    else:
        tpl = merge_defaults(json.loads(Path(a.modele).read_text(encoding="utf-8")))
        if a.cmd == "serie":
            rows = batch.read_csv(a.csv)
            base = a.base or str(Path(a.csv).resolve().parent)
        else:
            rows = batch.folder_rows(a.dossier, a.duree, a.titre_nom)
            base = a.dossier
        files, log = batch.run_batch(tpl, rows, base, a.sortie, quality=a.qualite, progress=bar)
        print("\n" + log)


if __name__ == "__main__":
    main()
