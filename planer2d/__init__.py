"""Rack-Planer Desktop – Oberfläche (Qt/PySide6) auf Basis von rackcore.

Ein Programm mit drei Ansichten: 2D-Vorderseite, 2D-Rückseite (scene.py) und die frei
drehbare 3D-Ansicht (view3d.py). Das Hauptfenster ist MainWindow3D (mainwindow3d.py), das
das 2D-Hauptfenster (mainwindow.py) um die 3D-Ansicht erweitert.
Die Versionsnummer ist für Desktop und Web gleich und steht in rackcore/version.py.
"""

from rackcore.version import APP_AUTHOR, APP_VERSION, EDITION_DESKTOP  # noqa: F401

EDITION = EDITION_DESKTOP
