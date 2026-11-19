"""Rack-Planer – Serverschränke grafisch planen (Desktop-Version mit 2D- und 3D-Ansicht).

Startpunkt für `python rack_planer.py` und den Windows-Build. Der Code liegt in
`planer2d/` (Oberfläche mit 2D- und 3D-Ansicht) und `rackcore/` (gemeinsamer Kern für
Desktop und Web).
"""

from planer2d.app import main

if __name__ == "__main__":
    main()
