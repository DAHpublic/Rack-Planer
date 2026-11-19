# Antrag bei der SignPath Foundation (Vorlage)

Formular: https://signpath.org/apply – erst ausfüllen, wenn das Repository öffentlich ist und
mindestens ein GitHub-Release mit der EXE existiert (siehe `EINRICHTUNG.md`).
Die Feldnamen im Formular können abweichen; die Texte sind auf Englisch, weil SignPath
englischsprachig prüft. Platzhalter in `<…>` selbst ausfüllen.

| Feld | Angabe |
|---|---|
| Project name | Rack-Planer |
| Repository URL | https://github.com/DAHpublic/Rack-Planer |
| Homepage / download page | https://github.com/DAHpublic/Rack-Planer/releases |
| Code signing policy URL | https://github.com/DAHpublic/Rack-Planer/blob/main/CODE_SIGNING_POLICY.md |
| License | MIT (SPDX: MIT) |
| Programming language / build | Python 3.12, PySide6 (Qt 6, LGPL v3), PyInstaller; built by GitHub Actions on GitHub-hosted `windows-latest` runners |
| Build system | GitHub Actions (trusted build system "GitHub.com") |
| Artifacts to sign | `Rack-Planer_v<version>.exe` – single-file portable Windows executable (Authenticode) with 2D and 3D views, built from this repository. |
| Maintainer | DAHpublic (GitHub) – Klarname nur im Formular, nicht im Repository |
| Contact e-mail | `<E-Mail-Adresse>` |
| Team members / roles | DAHpublic – author, reviewer, approver (single maintainer, MFA enabled) |

## Project description

> Rack-Planer is a free, portable desktop tool for planning server and network racks.
> Users lay out devices by rack unit (front and rear), check mounting depth and rail
> conflicts, label devices with names and IP addresses (with duplicate-IP detection), and see
> the total power draw and heat load (W and BTU/h). Plans are saved as JSON files with a
> built-in change history and can be exported as PDF, PNG and SVG. The program does not
> install anything, writes no settings or registry entries and makes no network connections.
> The program also includes a freely rotatable 3D view. A web edition (HTML/PHP, for a NAS
> or any PHP web server) sharing the same rules and file format is built from the same
> repository.

## Why code signing?

> The program is distributed as a single portable .exe via GitHub Releases. Without a
> signature, Windows SmartScreen shows "Unknown publisher" warnings, which makes users
> distrust the download. Signing through SignPath lets users verify that the executable was
> built unmodified from the public source code by our GitHub workflow.

## Third-party components

> Qt 6 and PySide6/Shiboken6 (unmodified, LGPL v3), Python runtime (PSF License), PyInstaller
> bootloader (GPL v2+ with bootloader exception). No proprietary components. Details:
> THIRD-PARTY-NOTICES.md in the repository.
