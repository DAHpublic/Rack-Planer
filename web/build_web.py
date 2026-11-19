"""Baut die Webversion (HTML/PHP) als ZIP für die Synology bzw. jeden PHP-Webserver.

    python web/build_web.py                      → dist/Rack-Planer-Web_v<V>.zip

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    a = ap.parse_args()
    v = version()
    files = program_files()
    web_zip = a.out / f"Rack-Planer-Web_v{v}.zip"
    write_zip(web_zip, {f"{FOLDER}/{k}": d for k, d in files.items()})
    print(f"Fertig: {web_zip} ({len(files)} Dateien)")
    shutil.rmtree(ROOT / "web" / "__pycache__", ignore_errors=True)


if __name__ == "__main__":
    main()
