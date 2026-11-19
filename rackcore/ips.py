"""IP-Adressen: Prüfung, Vergleich und Erkennung doppelter Adressen."""

from __future__ import annotations

import ipaddress
import re

from .model import Item, Rack

_V4_LEADING_ZEROS = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _parse(text: str):
    """IP-Adresse aus einer Eingabe wie „192.168.1.10“, „192.168.1.10/24“,
    „192.168.1.10/255.255.255.0“, „192.168.1.10 255.255.255.0“ oder „fe80::1%eth0“.
    Die Subnetzmaske wird geprüft, gehört aber nicht zur Adresse. None = ungültig."""
    text = re.sub(r"\s*/\s*", "/", text.strip())
    if not text:
        return None
    parts = text.split()
    if len(parts) == 2 and "/" not in text:           # „IP Maske“
        text = f"{parts[0]}/{parts[1]}"
    elif len(parts) != 1:
        return None
    addr, _, mask = text.partition("/")
    addr = addr.split("%", 1)[0]                      # IPv6-Zone (fe80::1%eth0)
    if _V4_LEADING_ZEROS.match(addr):                 # 192.168.001.010 → 192.168.1.10
        addr = ".".join(str(int(o)) for o in addr.split("."))
    try:
        ip = ipaddress.ip_address(addr)
        if mask:
            ipaddress.ip_interface(f"{ip}/{mask.strip()}")
    except ValueError:
        return None
    return ip


def ip_is_valid(text: str) -> bool:
    return not text.strip() or _parse(text) is not None


def ip_key(text: str) -> str:
    """Vergleichswert einer IP-Adresse. Die Subnetzmaske spielt keine Rolle:
    192.168.1.10/24, 192.168.1.10/16, 192.168.1.10 255.255.255.0 und 192.168.1.10 sind
    gleich. Ungültige Eingaben werden ohne Maske getrimmt und klein geschrieben verglichen."""
    ip = _parse(text)
    if ip is not None:
        return str(ip)
    return text.strip().split("/", 1)[0].strip().lower()


def duplicate_ips(rack: Rack) -> dict[str, list[Item]]:
    """IP-Adressen, die mehr als einem Gerät zugeordnet sind: {IP: [Geräte]}.
    Dieselbe IP mehrfach an einem Gerät zählt ebenfalls als doppelt."""
    seen: dict[str, list[Item]] = {}
    for d in rack.devices():
        for a in d.all_ips():
            seen.setdefault(ip_key(a), []).append(d)
    return {ip: devs for ip, devs in seen.items() if len(devs) > 1}
