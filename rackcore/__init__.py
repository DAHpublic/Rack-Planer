"""rackcore – gemeinsamer Kern aller Rack-Planer-Versionen (Desktop mit 2D- und 3D-Ansicht, Web).

Enthält Datenmodell, Vorlagen, IP-Prüfung und das Dateiformat. Keine Abhängigkeit von
Qt oder einer anderen Oberfläche: Die Desktop-Version und die Web-Version (Server) nutzen
dieselben Module, damit Dateien und Regeln (Belegung, Tiefe, doppelte IPs) überall
gleich sind.
"""

from .fileformat import (  # noqa: F401
    FILE_SUFFIX, FORMAT_VERSION, RackDocument, Snapshot, load_document, load_rack, now_iso,
    save_document, save_rack,
)
from .ips import duplicate_ips, ip_is_valid, ip_key  # noqa: F401
from .model import *  # noqa: F401,F403
from .model import Conflict, Item, Rack  # noqa: F401
from .templates import SHELF_DEPTH_MM, TEMPLATES, Template, find_template, template_matches  # noqa: F401
