"""Baut die Windows-EXE als dist\\Rack-Planer_v<Version>.exe.

Die Versionsnummer kommt aus APP_VERSION in rackcore/version.py. Ältere EXE-Dateien
bleiben erhalten: Existiert die EXE dieser Version schon, bricht der Build ab
(dann zuerst APP_VERSION erhöhen).
"""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src = (ROOT / "rackcore" / "version.py").read_text(encoding="utf-8")
version = re.search(r'^APP_VERSION = "([^"]+)"', src, re.M).group(1)
author = re.search(r'^APP_AUTHOR = "([^"]+)"', src, re.M).group(1)
name = f"Rack-Planer_v{version}"
exe = ROOT / "dist" / f"{name}.exe"
if exe.exists() and "--force" not in sys.argv:
    sys.exit(f"{exe.name} existiert bereits. Bitte APP_VERSION in rackcore/version.py erhöhen.")

nums = [int(x) for x in re.findall(r"\d+", version)][:4]
nums += [0] * (4 - len(nums))
vt = tuple(nums)
(ROOT / "build").mkdir(exist_ok=True)
vfile = ROOT / "build" / "version_info.txt"
vfile.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={vt}, prodvers={vt}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
      StringStruct('CompanyName', '{author}'),
      StringStruct('FileDescription', 'Rack-Planer – Serverschränke planen'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'Rack-Planer'),
      StringStruct('LegalCopyright', '© {author} · MIT-Lizenz'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', 'Rack-Planer'),
      StringStruct('ProductVersion', '{version}'),
      StringStruct('Comments', 'Entwickler: {author}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
""", encoding="utf-8")

cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
       "--name", name, "--icon", "rack.ico", "--version-file", str(vfile),
       "--exclude-module", "tkinter", "--exclude-module", "unittest"]
# Lizenztexte in die EXE packen (Hilfe → Lizenzen, Pflicht wegen Qt/PySide6 unter LGPL v3)
# und die Gerätevorlagen (rackcore/vorlagen.json, gemeinsam mit der Webversion)
for data, dest in [("LICENSE", "."), ("THIRD-PARTY-NOTICES.md", "."), ("licenses", "licenses"),
                   (os.path.join("rackcore", "vorlagen.json"), "rackcore")]:
    cmd += ["--add-data", f"{data}{os.pathsep}{dest}"]
cmd.append("rack_planer.py")
print(" ".join(cmd))
subprocess.run(cmd, cwd=ROOT, check=True)
print(f"Fertig: dist\\{name}.exe")
