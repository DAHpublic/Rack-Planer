# Code signing policy

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

> **Status:** Die Aufnahme bei der SignPath Foundation ist beantragt bzw. in Vorbereitung.
> Bis zur Freigabe sind die veröffentlichten EXE-Dateien **nicht signiert**.

## Was wird signiert?

Nur Programmdateien, die aus dem Quelltext **dieses Repositorys** durch den
GitHub-Workflow auf GitHub-gehosteten Runnern gebaut werden:

- `Rack-Planer_v<Version>.exe` – Desktop-Version mit 2D- und 3D-Ansicht (Windows)

Fremde Programme oder unverändert übernommene Binärdateien anderer Projekte werden **nicht**
mit diesem Zertifikat signiert. Jede signierte Datei trägt in den Dateieigenschaften den
Produktnamen „Rack-Planer“ und die Versionsnummer des jeweiligen Releases.

## Team und Rollen

| Rolle | Mitglieder |
|---|---|
| Committer und Reviewer | [DAHpublic](https://github.com/DAHpublic) |
| Approver | [DAHpublic](https://github.com/DAHpublic) |

- Änderungen von außen (Pull Requests von Nicht-Committern) werden vor dem Zusammenführen
  von einem Committer geprüft.
- Jede Signieranfrage wird für jedes Release einzeln von einem Approver manuell freigegeben.
- Alle Teammitglieder nutzen Zwei-Faktor-Authentifizierung bei GitHub und SignPath.

## Datenschutz / Privacy policy

This program will not transfer any information to other networked systems unless
specifically requested by the user or the person installing or operating it.

Der Rack-Planer (Desktop) baut keine Netzwerkverbindungen auf, legt keine Einstellungen,
Konfigurations- oder Hilfsdateien an und schreibt nichts in die Registry. Dateien entstehen
nur dort, wo der Benutzer speichert oder exportiert.

## Installation und Deinstallation

Die Windows-EXE ist portabel und wird nicht installiert. Zum Entfernen genügt es, die
EXE-Datei zu löschen; es bleiben keine Spuren im System zurück.
