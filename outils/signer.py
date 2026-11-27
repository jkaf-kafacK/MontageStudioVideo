"""Signature numérique (Authenticode) de MSV-Editeur.exe et de l'installateur : évite l'alerte « Windows a protégé
votre ordinateur » (SmartScreen) et prouve que les fichiers viennent bien de toi.

Il faut un certificat de signature de code (acheté chez une autorité : Sectigo, DigiCert…, ou le service Azure
Trusted Signing de Microsoft). Le certificat et son mot de passe ne sont JAMAIS écrits dans le code : ils viennent
des variables d'environnement ci-dessous.

Trois façons de signer (la première trouvée est utilisée) :
  MSV_SIGN_THUMBPRINT=<empreinte SHA-1>     certificat installé dans Windows (magasin « Personnel »)
  MSV_SIGN_PFX=C:\\chemin\\cert.pfx            fichier PFX, avec MSV_SIGN_PASSWORD=<mot de passe>
  MSV_SIGN_AZURE_DLIB=<Azure.CodeSigning.Dlib.dll> et MSV_SIGN_AZURE_METADATA=<metadata.json>   Azure Trusted Signing
Horodatage (la signature reste valable après l'expiration du certificat) : MSV_SIGN_TIMESTAMP, par défaut
http://timestamp.digicert.com.

    python outils\\signer.py fichier.exe [autre.exe …]
    python outils\\signer.py --verifier fichier.exe
    python outils\\signer.py --essai                 essai complet avec un certificat jetable (ne retire pas
                                                    SmartScreen : sert seulement à vérifier que tout marche)
Installateur : ISCC.exe /DPro /DSign "/Smsvsign=python outils\\signer.py $f" installer\\MontageStudioVideo.iss
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESCRIPTION = "Montage Studio Video"
TIMESTAMP = "http://timestamp.digicert.com"


def signtool() -> str:
    """signtool.exe : variable SIGNTOOL, sinon le plus récent des kits Windows (installé avec Visual Studio)."""
    env = os.environ.get("SIGNTOOL", "").strip()
    if env and Path(env).is_file():
        return env
    found = sorted(glob.glob(r"C:\Program Files (x86)\Windows Kits\10\bin\10.*\x64\signtool.exe"))
    if found:
        return found[-1]
    exe = shutil.which("signtool")
    if exe:
        return exe
    sys.exit("signtool.exe introuvable : installe le « Windows SDK » (avec Visual Studio Build Tools), ou indique "
             "son chemin dans la variable SIGNTOOL.")


def method_args(env: dict) -> tuple[list[str], str]:
    """Arguments de signtool pour le certificat configuré, et son nom (pour le journal)."""
    if env.get("MSV_SIGN_THUMBPRINT"):
        return ["/sha1", env["MSV_SIGN_THUMBPRINT"].replace(" ", "")], "certificat installé dans Windows"
    if env.get("MSV_SIGN_PFX"):
        pfx = Path(env["MSV_SIGN_PFX"])
        if not pfx.is_file():
            sys.exit(f"Fichier PFX introuvable : {pfx}")
        args = ["/f", str(pfx)]
        if env.get("MSV_SIGN_PASSWORD"):
            args += ["/p", env["MSV_SIGN_PASSWORD"]]
        return args, f"fichier {pfx.name}"
    if env.get("MSV_SIGN_AZURE_DLIB") and env.get("MSV_SIGN_AZURE_METADATA"):
        return ["/dlib", env["MSV_SIGN_AZURE_DLIB"], "/dmdf", env["MSV_SIGN_AZURE_METADATA"]], "Azure Trusted Signing"
    sys.exit("Aucun certificat configuré : définis MSV_SIGN_THUMBPRINT, ou MSV_SIGN_PFX (et MSV_SIGN_PASSWORD), ou "
             "MSV_SIGN_AZURE_DLIB et MSV_SIGN_AZURE_METADATA. Voir l'en-tête de outils/signer.py.")


def sign(files: list[Path], env: dict | None = None, timestamp: bool = True) -> None:
    env = dict(os.environ if env is None else env)
    tool = signtool()
    cert, label = method_args(env)
    for f in files:
        if not f.is_file():
            sys.exit(f"Fichier introuvable : {f}")
        cmd = [tool, "sign", *cert, "/fd", "SHA256", "/d", DESCRIPTION]
        if timestamp:
            cmd += ["/tr", env.get("MSV_SIGN_TIMESTAMP") or TIMESTAMP, "/td", "SHA256"]
        res = subprocess.run([*cmd, str(f)], capture_output=True, text=True)
        if res.returncode != 0:
            # le mot de passe n'apparaît jamais dans le message
            sys.exit(f"Signature de {f.name} impossible ({label}) :\n{(res.stdout + res.stderr).strip()[-800:]}")
        print(f"✅ {f.name} signé ({label})")


def signer_name(f: Path) -> tuple[str, str]:
    """(état de la signature selon Windows, titulaire du certificat) — via PowerShell Get-AuthenticodeSignature."""
    ps = (f"$s = Get-AuthenticodeSignature -LiteralPath '{f}'; "
          "Write-Output $s.Status; if ($s.SignerCertificate) { Write-Output $s.SignerCertificate.Subject }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    lines = [x.strip() for x in out.splitlines() if x.strip()]
    return (lines[0] if lines else "?"), (lines[1] if len(lines) > 1 else "")


def essai() -> None:
    """Certificat jetable (créé dans un dossier temporaire, jamais installé dans Windows), signature d'une copie de
    MSV-Editeur.exe, puis vérification : prouve que la chaîne de signature fonctionne."""
    from datetime import datetime, timedelta, timezone

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    exe = ROOT / "desktop" / "src-tauri" / "target" / "release" / "MSV-Editeur.exe"
    if not exe.is_file():
        sys.exit(f"Compile d'abord l'application de bureau : {exe} est introuvable.")
    tmp = Path(tempfile.mkdtemp(prefix="msv_signature_"))
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "MSV essai de signature (jetable)")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CODE_SIGNING]), critical=False)
            .sign(key, hashes.SHA256()))
    password = os.urandom(12).hex()
    pfx = tmp / "essai.pfx"
    pfx.write_bytes(pkcs12.serialize_key_and_certificates(b"msv", key, cert, None,
                                                          serialization.BestAvailableEncryption(password.encode())))
    copy = tmp / exe.name
    shutil.copy2(exe, copy)
    try:
        sign([copy], {**os.environ, "MSV_SIGN_PFX": str(pfx), "MSV_SIGN_PASSWORD": password,
                      "MSV_SIGN_THUMBPRINT": "", "MSV_SIGN_AZURE_DLIB": ""}, timestamp=False)
        status, subject = signer_name(copy)
        print(f"Signature lue par Windows : {status} · {subject}")
        if "MSV essai de signature" not in subject:
            sys.exit("❌ La signature n'a pas été trouvée dans le fichier.")
        print("✅ La signature fonctionne. Avec un vrai certificat, l'état sera « Valid ».")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Signe MSV-Editeur.exe et l'installateur (Authenticode).")
    ap.add_argument("fichiers", nargs="*", type=Path)
    ap.add_argument("--verifier", action="store_true", help="affiche l'état de la signature des fichiers")
    ap.add_argument("--essai", action="store_true", help="essai complet avec un certificat jetable")
    ap.add_argument("--sans-horodatage", action="store_true", help="pas de serveur d'horodatage (déconseillé)")
    a = ap.parse_args()
    if a.essai:
        essai()
        return
    if not a.fichiers:
        ap.error("indique au moins un fichier à signer")
    if a.verifier:
        for f in a.fichiers:
            status, subject = signer_name(f)
            print(f"{f.name} : {status}{' · ' + subject if subject else ''}")
        return
    sign(a.fichiers, timestamp=not a.sans_horodatage)


if __name__ == "__main__":
    main()
