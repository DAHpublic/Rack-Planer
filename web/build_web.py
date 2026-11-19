"""Baut die Webversion (HTML/PHP) als ZIP für die Synology – und optional portabel für Windows.

    python web/build_web.py                      → dist/Rack-Planer-Web_v<V>.zip
    python web/build_web.py --php <ordner>       → zusätzlich dist/Rack-Planer-Web-portabel_v<V>.zip
                                                   (<ordner> = entpacktes PHP für Windows, NTS x64)

Inhalt des Programmordners „rack-planer“ im ZIP:
    index.html, api.php, app/ (Oberfläche, Rechenkern, Schriften, Bibliotheken),
    vorlagen.json (Kopie von rackcore/vorlagen.json), version.json, manifest.json, LIESMICH.txt
Der Ordner „daten“ (Schränke, eigene Vorlagen) ist NICHT im ZIP – ein Update überschreibt
also nie Daten. manifest.json listet alle Programmdateien; beim Update im Browser werden
Dateien, die es nicht mehr gibt, entfernt.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
FOLDER = "rack-planer"


def version() -> str:
    src = (ROOT / "rackcore" / "version.py").read_text(encoding="utf-8")
    return re.search(r'^APP_VERSION = "([^"]+)"', src, re.M).group(1)


def program_files() -> dict[str, bytes]:
    """Alle Dateien des Programmordners: relativer Pfad → Inhalt."""
    v = version()
    files: dict[str, bytes] = {}
    files["index.html"] = (WEB / "index.html").read_text(encoding="utf-8").replace("__V__", v).encode("utf-8")
    files["api.php"] = (WEB / "api.php").read_bytes()
    for p in sorted((WEB / "app").rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            files["app/" + p.relative_to(WEB / "app").as_posix()] = p.read_bytes()
    files["vorlagen.json"] = (ROOT / "rackcore" / "vorlagen.json").read_bytes()
    files["LIESMICH.txt"] = (WEB / "LIESMICH.txt").read_text(encoding="utf-8").replace("__V__", v).encode("utf-8")
    files["version.json"] = json.dumps({"app": "Rack-Planer", "edition": "web", "version": v,
                                        "built": _dt.date.today().isoformat()}, indent=2).encode("utf-8")
    names = sorted(files) + ["manifest.json"]
    files["manifest.json"] = json.dumps({"files": names}, indent=1).encode("utf-8")
    return files


def write_zip(path: Path, entries: dict[str, bytes]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in entries.items():
            z.writestr(name, data)


PHP_INI = """; PHP-Einstellungen der portablen Webversion (nur für den mitgelieferten PHP-Server)
extension_dir = "ext"
extension = zip
upload_max_filesize = 32M
post_max_size = 40M
memory_limit = 256M
date.timezone = Europe/Berlin
display_errors = Off
"""

START_BAT = r"""@echo off
chcp 65001 >nul
title Rack-Planer (Webversion, portabel)
cd /d "%~dp0"
set PORT=8090
echo Rack-Planer laeuft: http://127.0.0.1:%PORT%/
echo Dieses Fenster offen lassen. Schliessen beendet den Rack-Planer.
echo.
start "" "http://127.0.0.1:%PORT%/"
"%~dp0php\php.exe" -c "%~dp0php\php.ini" -S 127.0.0.1:%PORT% -t "%~dp0rack-planer"
echo.
echo Der Server wurde beendet. Ist Port %PORT% schon belegt? Dann in dieser Datei PORT aendern.
pause
"""

START_LAN_BAT = r"""@echo off
chcp 65001 >nul
title Rack-Planer (Webversion, im Netzwerk)
cd /d "%~dp0"
set PORT=8090
echo Rack-Planer ist im Netzwerk erreichbar unter http://<IP dieses PCs>:%PORT%/
echo IP-Adressen dieses PCs:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do echo    http://%%a:%PORT%/
echo Windows fragt beim ersten Start evtl. nach einer Firewall-Freigabe.
echo Dieses Fenster offen lassen. Schliessen beendet den Rack-Planer.
echo.
start "" "http://127.0.0.1:%PORT%/"
"%~dp0php\php.exe" -c "%~dp0php\php.ini" -S 0.0.0.0:%PORT% -t "%~dp0rack-planer"
pause
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--php", type=Path, help="Ordner mit PHP für Windows (für die portable Variante)")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()
    v = version()
    files = program_files()
    web_zip = a.out / f"Rack-Planer-Web_v{v}.zip"
    write_zip(web_zip, {f"{FOLDER}/{k}": d for k, d in files.items()})
    print(f"Fertig: {web_zip} ({len(files)} Dateien)")
    if a.php:
        if not (a.php / "php.exe").is_file():
            raise SystemExit(f"php.exe fehlt in {a.php}")
        top = f"Rack-Planer-Web-portabel_v{v}"
        entries = {f"{top}/{FOLDER}/{k}": d for k, d in files.items()}
        for p in sorted(a.php.rglob("*")):
            if p.is_file():
                entries[f"{top}/php/{p.relative_to(a.php).as_posix()}"] = p.read_bytes()
        entries[f"{top}/php/php.ini"] = PHP_INI.encode("utf-8")
        entries[f"{top}/Rack-Planer starten.bat"] = START_BAT.replace("\n", "\r\n").encode("utf-8")
        entries[f"{top}/Start im Netzwerk (LAN).bat"] = START_LAN_BAT.replace("\n", "\r\n").encode("utf-8")
        entries[f"{top}/LIESMICH.txt"] = (WEB / "portable" / "LIESMICH.txt").read_text(encoding="utf-8") \
            .replace("__V__", v).replace("\n", "\r\n").encode("utf-8-sig")
        port_zip = a.out / f"{top}.zip"
        write_zip(port_zip, entries)
        print(f"Fertig: {port_zip}")
    shutil.rmtree(ROOT / "web" / "__pycache__", ignore_errors=True)


if __name__ == "__main__":
    main()
