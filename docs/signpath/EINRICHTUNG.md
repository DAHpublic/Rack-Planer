# Code-Signing mit SignPath Foundation – Einrichtung

Ziel: Windows zeigt bei der EXE nicht mehr „Unbekannter Herausgeber“. Die SignPath Foundation
signiert Open-Source-Projekte kostenlos. **Herausgeber im Zertifikat ist „SignPath
Foundation“**, nicht der Entwickler – das ist bei diesem Programm immer so.

## Voraussetzungen (laut https://signpath.org/terms)

- [x] OSI-Lizenz für das ganze Projekt: MIT (`LICENSE`), keine proprietären Bestandteile
      (Qt/PySide6 unter LGPL v3, siehe `THIRD-PARTY-NOTICES.md`)
- [x] Seite „Code signing policy“ mit Attribution, Rollen und Datenschutzsatz
      (`CODE_SIGNING_POLICY.md`, verlinkt im README)
- [x] Build ausschließlich auf GitHub-gehosteten Runnern, Artefakt per `actions/upload-artifact`
- [x] Produktname „Rack-Planer“ und Version in den Dateieigenschaften (build.py)
- [ ] Repository **öffentlich**
- [ ] Das Programm ist bereits **veröffentlicht** (GitHub-Release mit der EXE) und die
      Funktionen sind auf der Download-Seite beschrieben (README / Release-Text)
- [ ] Zwei-Faktor-Authentifizierung bei GitHub (und später bei SignPath)
- [ ] Antrag unter https://signpath.org/apply (Text: `docs/signpath/ANTRAG.md`)

SignPath prüft außerdem einmalig die „Reputation“ des Projekts; Mindestzahlen (Sterne o. ä.)
nennt SignPath nicht, eine Ablehnung ist möglich und nicht anfechtbar.

## Nach der Zusage

1. In SignPath: Projekt `Rack-Planer` anlegen (bzw. das von SignPath angelegte verwenden),
   Trusted Build System „GitHub.com“ verknüpfen und zwei Artifact Configurations anlegen:
   `desktop-2d` aus `docs/signpath/artifact-configuration.xml` und `desktop-3d` aus
   `docs/signpath/artifact-configuration-3d.xml`.
2. In SignPath einen API-Token für einen Benutzer mit Submitter-Rechten erzeugen.
3. In GitHub → Settings → Secrets and variables → Actions:
   - Secret `SIGNPATH_API_TOKEN` = API-Token
   - Variable `SIGNPATH_ORGANIZATION_ID` = Organisations-ID aus SignPath
   - optional `SIGNPATH_PROJECT_SLUG` (Standard `Rack-Planer`), `SIGNPATH_POLICY_SLUG`
     (Standard `release-signing`), `SIGNPATH_ARTIFACT_CONFIG_SLUG` (Standard `desktop-2d`)
4. Release bauen: Tag `v2.04` (o. ä.) pushen. Der Workflow baut, testet, lädt die EXE hoch
   und schickt sie an SignPath. Dort die Signieranfrage **manuell freigeben** (Approver). Die
   signierte EXE erscheint als Artefakt „Rack-Planer-Windows-signiert“ und gehört dann in das
   GitHub-Release.

Ohne die Variable `SIGNPATH_ORGANIZATION_ID` überspringt der Workflow die Signierung; der
Build funktioniert wie bisher.

## 3D-Ansicht und Web-Version

- **3D**: Die 3D-Ansicht ist Teil der Desktop-EXE; es gibt nur eine Artifact Configuration
  (`desktop-2d`).
- **Web (`web/`)**: HTML/PHP, keine eigene Windows-Programmdatei – braucht kein Code-Signing.
- Neue Bibliotheken in
  `THIRD-PARTY-NOTICES.md` aufnehmen; alle müssen eine Open-Source-Lizenz haben.
