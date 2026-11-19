#!/usr/bin/env bash
# Hängt Dateien an das Release v<Version> (Version aus rackcore/version.py); legt es an, falls
# es noch nicht existiert. Aufruf: .github/scripts/release.sh <datei> [<datei> ...]
# (braucht GH_TOKEN mit contents: write)
set -euo pipefail
v="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' rackcore/version.py)"
tag="v$v"
notes="**Desktop-Version (Windows):** \`Rack-Planer_v$v.exe\` herunterladen und starten – keine Installation nötig.

**Webversion:** \`Rack-Planer-Web_v$v.zip\` für die Synology (Web Station) oder jeden Webserver mit PHP 7.4+ – Ordner \`rack-planer\` kopieren, fertig ([Anleitung](https://github.com/$GITHUB_REPOSITORY/blob/main/web/SYNOLOGY.md)). Ab 2.06 aktualisiert sich eine bestehende Installation nachts selbst (Einstellungen in \`einstellungen.ini\`, die Updates nie überschreiben).

Die EXE ist noch nicht digital signiert; Windows SmartScreen kann beim ersten Start warnen."
if ! gh release view "$tag" >/dev/null 2>&1; then
  # Beide Workflows können gleichzeitig ankommen – schlägt das Anlegen fehl, gibt es das Release schon.
  gh release create "$tag" --target "$GITHUB_SHA" --title "Rack-Planer $v" --notes "$notes" --latest \
    || sleep 5
fi
gh release upload "$tag" "$@" --clobber
