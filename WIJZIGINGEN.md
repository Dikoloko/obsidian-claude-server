# Wat er anders is dan bij de maker

Dit is een aangepaste kopie van [jimprosser/obsidian-web-mcp](https://github.com/jimprosser/obsidian-web-mcp) (MIT-licentie), vertrokken van commit `6c429df` en nagelezen op veiligheid voor een Windows-pc achter een Cloudflare-tunnel. Elke aanpassing heeft een test in `tests/test_fork_hardening.py`. Updates van de maker komen er niet vanzelf in.

## Paden (Windows)

De maker blokkeerde verborgen mappen (`.obsidian`, `.git`, `.claude`) alleen op de letterlijke invoer. Windows kent elke map ook onder een korte naam (`OBSIDI~1`), en die glipte erdoor: zo kon een note-tool Obsidian-plugins of git-hooks herschrijven, wat neerkomt op code laten uitvoeren. Nu:
- korte namen, schijfletters, `:` (ook verborgen datastromen), UNC-paden (`//host/share`), absolute paden, Windows-apparaatnamen (`CON`, `NUL`, `COM1` ...) en namen die op een punt of spatie eindigen worden geweigerd vóór er iets op schijf gebeurt (een UNC-pad openen lekt al de Windows-loginhash);
- na het oplossen van het pad wordt nog eens gecontroleerd dat het nergens in een verborgen map of bestand uitkomt;
- `./note.md` wordt ook geweigerd (strenger dan de maker).

## Schrijven

- Tekstschrijven (write, edit, append, daily note) maakt of wijzigt alleen `.md` en `.canvas`, geen `.bat`, `.ps1`, `.url`, `desktop.ini` en dergelijke.
- `vault_write` maakt standaard alleen nieuwe notes. Een bestaande note vervangen kan enkel met `overwrite=true`; `merge_frontmatter=true` werkt de frontmatter van een bestaande note bij.
- Tijdelijke bestanden beginnen met een punt, zodat Obsidian Sync nooit een half geschreven bestand meeneemt.

## Weggehaalde en aangepaste tools

- Weg: frontmatter in bulk, binaire bestanden (afbeeldingen, pdf), de drie canvas-tools en de getekende upload- en download-links (die werkten zonder token; ze staan hard uit, ook als de geheimen gezet zijn).
- Verwijderen verplaatst naar de prullenbak van de vault (`.trash`), zoals Obsidian, en alleen met `confirm=true`. Claude kan de prullenbak niet lezen of leegmaken. Ook een volle map mag naar de prullenbak.
- Verplaatsen of hernoemen werkt elke link naar de note in de hele vault bij, zoals Obsidian; een proefrun toont eerst wat er zou veranderen. Een verplaatsing mag het bestandstype niet veranderen, en de vault zelf kan niet verplaatst of verwijderd worden.
- Risico: één verkeerde opdracht op een map verschuift of verwijdert alles erin. Terughalen kan uit `.trash` of uit de versiegeschiedenis van Obsidian Sync.

## Overig

- `.claude` staat bij de uitgesloten mappen.
- Zoeken is letterlijk (ook met ripgrep): "C++" of "(concept)" vindt gewoon die tekst.
- Zoeken en mappen bekijken geven op Windows paden met `/`, en zoeken op frontmatter binnen een map werkt nu ook op Windows.
- De extra `semantic` is weg (sentence-transformers kon code uit een lokale modelmap uitvoeren, GHSA-jhr6-gm9c-rqjv).
- `uv.lock` ligt vast, zodat elke installatie exact dezelfde versies krijgt; starlette minstens 1.3.1 (GHSA-82w8-qh3p-5jfq).
- mcp 2.x in plaats van 1.x, zodat de server MCP-protocolversie 2026-07-28 aanneemt, waarmee Claude elke verbinding opent. De maker houdt mcp bewust onder 2.x; dit is een eigen afwijking. Bij een fout in een tool ziet de client in 2.x alleen "Error executing tool ..."; weigert het invoermodel een waarde, dan gaat de reden wel mee.
- Inloggen gebeurt via Cloudflare Access (eenmalige code per e-mail). In die modus biedt de server geen eigen inlogpagina aan en heeft hij geen token of wachtwoord nodig.
- Opstarten bij het aanmelden op Windows met geplande taken, zie `scripts/windows/` en `INSTALLATIE-WINDOWS.md`.

## Testbeeld op Windows

Op een gewone Windows-pc falen 38 tests en geven er 3 een fout, ook bij de maker op dezelfde pc: symlinks maken vraagt beheerdersrechten, Unix-bestandsrechten bestaan niet op Windows, tests schrijven met Windows-regeleinden, en de semantische zoekfunctie staat uit. Op GitHub (Linux) slaagt alles. Alle tests in `tests/test_fork_hardening.py` moeten slagen.
