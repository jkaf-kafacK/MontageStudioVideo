"""Corrige automatiquement les failles de sécurité signalées dans requirements.lock.

Usage (depuis la racine du dépôt) :
    python outils/maj_securite.py            # audit + correction + nouvel audit
    python outils/maj_securite.py --audit    # audit seulement

Prérequis : uv (https://astral.sh/uv) et pip-audit (pip install pip-audit).

Fonctionnement :
  1. pip-audit liste les paquets vulnérables du fichier figé et les versions qui les corrigent ;
  2. uv met à jour UNIQUEMENT ces paquets (les autres versions restent identiques), en autorisant
     exceptionnellement des versions récentes pour eux (enregistré dans montage_studio/securite.json) ;
  3. un nouvel audit vérifie qu'il ne reste aucune faille.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
APP = RACINE / "montage_studio"
LOCK = APP / "requirements.lock"
CONFIG = APP / "securite.json"


def audit() -> dict[str, list[str]]:
    """Renvoie {paquet: [versions correctives]} pour chaque paquet vulnérable du fichier figé."""
    cmd = [sys.executable, "-m", "pip_audit", "-r", str(LOCK), "--no-deps", "--disable-pip", "-f", "json"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(res.stdout)
    except json.JSONDecodeError:
        sys.exit(f"pip-audit n'a pas fonctionné. Installe-le avec : pip install pip-audit\n{res.stderr[-800:]}")
    vuln = {}
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            vuln.setdefault(dep["name"].lower(), []).append((v["id"], v.get("fix_versions") or []))
    return vuln


def version_cle(v: str):
    return [int(x) if x.isdigit() else 0 for x in v.replace("-", ".").split(".")]


def version_minimale(lst: list[tuple[str, list[str]]]) -> str:
    """Plus petite version qui corrige TOUTES les failles du paquet."""
    return max((min(fix, key=version_cle) for _, fix in lst), key=version_cle)


def date_publication(paquet: str, version: str) -> str:
    """Date de publication sur PyPI (+1 jour) : on autorise jusqu'à la version corrective, pas au-delà."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{paquet}/{version}/json", timeout=30) as r:
        data = json.load(r)
    jour = min(f["upload_time"] for f in data["urls"])[:10]
    return (dt.date.fromisoformat(jour) + dt.timedelta(days=1)).isoformat()


def entete(cfg: dict) -> str:
    exc = ", ".join(f"{p} (autorisé jusqu'au {d})" for p, d in sorted(cfg["exceptions"].items()))
    return (
        "# Versions exactes installées par l'installateur Windows, avec empreintes SHA-256 (chaque paquet téléchargé\n"
        "# est exactement celui qui a été testé). Ne pas modifier à la main : utiliser outils/maj_securite.py.\n"
        f"# Paquets publiés avant le {cfg['exclude_newer']} (règle des 2 semaines), sauf correctifs de sécurité :\n"
        f"#   {exc}\n"
    )


def compiler(cfg: dict, a_mettre_a_jour: list[str]) -> None:
    uv = shutil.which("uv")
    if not uv:
        sys.exit("uv est introuvable. Installe-le : https://docs.astral.sh/uv/getting-started/installation/")
    cmd = [uv, "pip", "compile", "requirements.txt", "--override", "overrides.txt", "--universal",
           "--python-version", "3.12", "--exclude-newer", cfg["exclude_newer"], "--generate-hashes",
           "--no-header", "-q", "-o", "requirements.lock"]
    for p, d in cfg["exceptions"].items():
        cmd += ["--exclude-newer-package", f"{p}={d}"]
    for p in a_mettre_a_jour:
        cmd += ["--upgrade-package", p]
    corps = LOCK.read_text(encoding="utf-8")
    res = subprocess.run(cmd, cwd=APP, capture_output=True, text=True)
    if res.returncode != 0:
        LOCK.write_text(corps, encoding="utf-8")
        sys.exit(f"uv n'a pas pu mettre à jour les dépendances :\n{res.stderr[-1500:]}")
    lignes = [l for l in LOCK.read_text(encoding="utf-8").splitlines() if not l.startswith("#")]
    LOCK.write_text(entete(cfg) + "\n".join(lignes) + "\n", encoding="utf-8")


def versions() -> dict[str, str]:
    out = {}
    for l in LOCK.read_text(encoding="utf-8").splitlines():
        if "==" in l and not l.startswith((" ", "#")):
            nom, ver = l.split("==", 1)
            out[nom.strip().lower()] = ver.split()[0].strip(" \\")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Corrige les failles de sécurité de requirements.lock")
    ap.add_argument("--audit", action="store_true", help="vérifier seulement, sans rien modifier")
    args = ap.parse_args()

    vuln = audit()
    if not vuln:
        print("✅ Aucune faille connue dans requirements.lock")
        return
    print("Failles trouvées :")
    for p, lst in vuln.items():
        print(f"  {p} : {len(lst)} faille(s) ({', '.join(i for i, _ in lst)})")
    if args.audit:
        sys.exit(1)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    sans_correctif = [p for p, lst in vuln.items() if any(not fix for _, fix in lst)]
    if sans_correctif:
        print(f"⚠ Aucune version corrective publiée pour : {', '.join(sans_correctif)}. "
              "Il faudra attendre un correctif ou retirer ce paquet.")
    a_corriger = [p for p in vuln if p not in sans_correctif]
    for p in a_corriger:
        cible = version_minimale(vuln[p])
        cfg["exceptions"][p] = max(cfg["exceptions"].get(p, ""), date_publication(p, cible))
        print(f"  -> {p} : version corrective minimale {cible}")
    avant = versions()
    compiler(cfg, a_corriger)
    apres = versions()
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("\nVersions modifiées :")
    for p in sorted(set(avant) | set(apres)):
        if avant.get(p) != apres.get(p):
            print(f"  {p} : {avant.get(p, '—')} → {apres.get(p, '—')}")
    reste = audit()
    if reste:
        sys.exit(f"❌ Il reste des failles : {', '.join(reste)}")
    print("\n✅ Plus aucune faille connue. Lance les tests, puis commit et push :")
    print("   git add montage_studio/requirements.lock montage_studio/securite.json")
    print('   git commit -m "Sécurité : mise à jour des dépendances vulnérables"')
    print("   git push")


if __name__ == "__main__":
    main()
