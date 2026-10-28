# Installatie op een Windows-pc, één vault

Dit bestand is geschreven voor een Claude Code-sessie die de server installeert voor iemand zonder technische kennis. Doe het technische werk zelf, leg elke stap in gewone taal uit, en vraag de gebruiker alleen wat hij zelf moet doen: inloggen bij Cloudflare, klikken in het Cloudflare-dashboard, de connector toevoegen in Claude. Gebruik in deze uitleg `a.jouwdomein.com` voor het adres van de gebruiker.

## Wat er al moet zijn

- Windows 10 of 11, een pc die altijd aanstaat (slaapstand op "Nooit").
- De vault van de gebruiker in een gewone map, bij voorkeur `C:\Obsidian\<naam>`, gesynchroniseerd met Obsidian Sync, en Obsidian start mee bij het aanmelden. Niet in OneDrive, iCloud of Dropbox.
- Een Cloudflare-account met tweestapsverificatie en een domein bij Cloudflare.

## Stappen

1. **Onderdelen.** Installeer wat ontbreekt met `winget`: `astral-sh.uv`, `Cloudflare.cloudflared` en, als git ontbreekt, `Git.Git`.
2. **Code.** Clone deze repository naar `C:\CLAUDE CODE\obsidian-claude-server`, nooit in de vault zelf.
3. **Installeren en testen.** `uv sync --extra dev --extra cloudflare-access`, daarna `uv run --no-sync pytest tests/test_fork_hardening.py -q`: alles moet slagen. De volledige testreeks heeft op Windows een bekend aantal fouten, zie `WIJZIGINGEN.md`.
4. **Tunnel.** `cloudflared tunnel login` (de gebruiker meldt zich aan in de browser en kiest zijn domein), dan `cloudflared tunnel create vault` en `cloudflared tunnel route dns vault a.jouwdomein.com`. Kopieer `scripts\windows\cloudflared-config.example.yml` naar `%USERPROFILE%\.cloudflared\config.yml` en vul de tunnel-id, de gebruikersnaam en de hostnaam in.
5. **Het slot (de gebruiker, in het Cloudflare-dashboard, Zero Trust).** De eerste keer: een teamnaam kiezen en het gratis plan (vraagt betaalgegevens, rekent niets aan). Dan een zelf gehoste toepassing op `a.jouwdomein.com`, aanmelden met "One-time PIN", een regel "Allow" voor alleen het e-mailadres van de gebruiker, en "Managed OAuth" aan met de terugkeeradressen `https://claude.ai/api/mcp/auth_callback` en `https://claude.com/api/mcp/auth_callback`. De gebruiker geeft de teamnaam (`...cloudflareaccess.com`) en de "Application Audience (AUD) Tag" door; dat zijn geen geheimen.
6. **Instellingen.** Maak `%USERPROFILE%\.vault-mcp\a\server.json` volgens het voorbeeld bovenaan `scripts\windows\start-vault.ps1`: het pad van de vault, poort 8421, de hostnaam, de teamnaam en de AUD-tag.
7. **Opstarten.** `scripts\windows\install-tasks.ps1 -Names a` registreert een taak voor de server en een voor de tunnel, die starten bij het aanmelden. Start ze meteen in Taakplanner (map `\vault-mcp\`). Logs staan in `%USERPROFILE%\.vault-mcp\a\logs` en `%USERPROFILE%\.vault-mcp\tunnel\`.
8. **Controle.** Op de pc zelf antwoordt `http://127.0.0.1:8421/health`. Via `https://a.jouwdomein.com` vraagt Cloudflare eerst de code uit de mail; zonder Cloudflare-pasje antwoordt de server zelf met 401.
9. **Connector (de gebruiker).** In Claude: "Customize", "Connectors", "+ Add", "Add custom connector", met het adres `https://a.jouwdomein.com`. Verbinden, de code uit de mail invullen, en testen met "Welke mappen staan er in mijn vault?", eerst op de pc, dan op de iPhone.

Een tweede vault krijgt een eigen naam (`b`), poort (8422), hostnaam, Access-toepassing met eigen AUD-tag en `server.json`, en `install-tasks.ps1 -Names a,b`.

## Spelregels

- **Schrijf geen instellingen onder AppData.** De Claude-app is een Windows-pakket: wat een sessie daar schrijft, belandt in een privékopie en de geplande taak ziet het niet. Gebruik `%USERPROFILE%\.vault-mcp`.
- **Terwijl de server draait: tests alleen met `uv run --no-sync pytest`.** Een gewone `uv run` of `uv sync` wil de onderdelen bijwerken en botst met de draaiende server.
- **Bijwerken:** `git pull`, de taken stoppen, `uv sync --extra dev --extra cloudflare-access`, de taken weer starten. Zonder `cloudflare-access` weigert de server te starten.
- **Komen er tools bij of vallen er weg, dan moet de gebruiker de connector in Claude opnieuw verbinden.** Claude onthoudt de lijst met tools per verbinding.
- **Start de server nooit met de vault als werkmap,** en installeer nooit via `pip install obsidian-web-mcp`: die naam bestaat niet op PyPI en kan door iemand anders geclaimd worden.
- **Geen tweede Access-regel die anderen toelaat.** Wie toegang heeft, kan alles in de vault lezen, wijzigen en naar de prullenbak verplaatsen.
