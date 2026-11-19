"""Gemeinsame Versionsnummer aller Rack-Planer-Versionen (Desktop und Web).

Beide Versionen tragen dieselbe Nummer; dazu steht jeweils, um welche Version es sich
handelt. Die Desktop-Version vereint seit 2.04 die 2D-Ansichten (Vorder- und Rückseite) und
die 3D-Ansicht in einem Programm. Für eine neue Version nur APP_VERSION hier erhöhen
(build.py liest die Nummer aus dieser Datei).
"""

APP_VERSION = "2.06"
APP_AUTHOR = "DAHpublic"

EDITION_DESKTOP = "Desktop-Version"
EDITION_WEB = "Webversion"


def version_label(edition: str) -> str:
    """z. B. „Rack-Planer 2.06 (Desktop-Version)“."""
    return f"Rack-Planer {APP_VERSION} ({edition})"
