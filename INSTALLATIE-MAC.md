# Installatie op een Mac, één vault

Dit bestand is geschreven voor een Claude Code-sessie die de server installeert voor iemand zonder technische kennis. Doe het technische werk zelf, leg elke stap in gewone taal uit, en vraag de gebruiker alleen wat hij zelf moet doen: inloggen bij Cloudflare, klikken in het Cloudflare-dashboard, de connector toevoegen in Claude. Gebruik in deze uitleg `a.jouwdomein.com` voor het adres van de gebruiker.

Deze kopie werd getest op Windows. Op een Mac draait dezelfde server (de maker bouwde hem oorspronkelijk voor macOS), maar deze installatie is nog niet van begin tot eind op een Mac nagelopen. Meld wat afwijkt aan de gebruiker.

## Wat er al moet zijn

- Een Mac die altijd aanstaat en niet in slaap valt (zie de gids, of: Systeeminstellingen, "Energie", "Voorkom automatische sluimerstand wanneer het beeldscherm is uitgeschakeld"; op een MacBook onder "Batterij", "Opties", op netstroom). Een MacBook met het deksel dicht slaapt, tenzij er een extern scherm aan hangt.
- De vault van de gebruiker in een gewone map in zijn thuismap, bij voorkeur `~/Obsidian/<naam>`, gesynchroniseerd met Obsidian Sync, en Obsidian in de inloglijst (Systeeminstellingen, "Algemeen", "Inlogonderdelen"). Niet in iCloud Drive, Documenten of Bureaublad: macOS schermt die mappen af voor achtergrondprogramma's, en iCloud synchroniseert er dan ook nog naast Obsidian Sync.
- Een Cloudflare-account met tweestapsverificatie en een domein bij Cloudflare.

## Stappen

1. **Onderdelen.** Installeer wat ontbreekt met Homebrew (eerst Homebrew zelf als dat ontbreekt): `brew install uv cloudflared git`.
2. **Code.** Clone deze repository naar `~/Claude/obsidian-claude-server`, nooit in de vault zelf.
3. **Installeren en testen.** `uv sync --extra dev --extra cloudflare-access`, daarna `uv run --no-sync pytest tests/test_fork_hardening.py -q`. De tests die specifiek Windows nagaan, worden op een Mac overgeslagen; de rest moet slagen.
4. **Tunnel.** `cloudflared tunnel login` (de gebruiker meldt zich aan in de browser en kiest zijn domein), dan `cloudflared tunnel create vault` en `cloudflared tunnel route dns vault a.jouwdomein.com`. Maak `~/.cloudflared/config.yml` volgens `scripts/windows/cloudflared-config.example.yml`, met het pad `~/.cloudflared/<tunnel-id>.json` (volledig uitgeschreven, zonder `~`).
5. **Het slot (de gebruiker, in het Cloudflare-dashboard, Zero Trust).** Precies zoals in stap 5 van `INSTALLATIE-WINDOWS.md`: een teamnaam en het gratis plan, een zelf gehoste toepassing op `a.jouwdomein.com` met "One-time PIN", een regel "Allow" voor alleen het e-mailadres van de gebruiker, "Managed OAuth" aan met de terugkeeradressen `https://claude.ai/api/mcp/auth_callback` en `https://claude.com/api/mcp/auth_callback`. De gebruiker geeft de teamnaam en de AUD-tag door.
6. **Opstarten bij het inloggen.** Maak de mappen `~/.vault-mcp/a/logs`, `~/.vault-mcp/a/oauth` en `~/.vault-mcp/tunnel`. Kopieer `scripts/macos/vault-mcp.plist.example` naar `~/Library/LaunchAgents/com.obsidian-claude-server.a.plist` en `scripts/macos/cloudflared-vault.plist.example` naar `~/Library/LaunchAgents/com.obsidian-claude-server.tunnel.plist`, vul elke `REPLACE_WITH_...` in met volledige paden (`which cloudflared` voor de tunnel), en start ze met `launchctl bootstrap gui/$(id -u) <pad naar de plist>`.
7. **Controle.** Op de Mac zelf antwoordt `http://127.0.0.1:8421/health`. Via `https://a.jouwdomein.com` vraagt Cloudflare eerst de code uit de mail. Logs staan in `~/.vault-mcp/a/logs` en `~/.vault-mcp/tunnel`.
8. **Connector (de gebruiker).** In Claude: "Customize", "Connectors", "+ Add", "Add custom connector", met het adres `https://a.jouwdomein.com`. Verbinden, de code uit de mail invullen, en testen met "Welke mappen staan er in mijn vault?", eerst op de Mac, dan op de iPhone.

## Spelregels

- **Terwijl de server draait: tests alleen met `uv run --no-sync pytest`.**
- **Bijwerken:** `git pull`, de server stoppen (`launchctl bootout gui/$(id -u)/com.obsidian-claude-server.a`), `uv sync --extra dev --extra cloudflare-access`, en weer starten met `launchctl bootstrap`.
- **Komen er tools bij of vallen er weg, dan moet de gebruiker de connector in Claude opnieuw verbinden.**
- **Start de server nooit met de vault als werkmap,** en installeer nooit via `pip install obsidian-web-mcp`.
- **Geen token of wachtwoord in de plist.** Deze opstelling gebruikt alleen Cloudflare Access; de plist bevat geen geheimen.
- **Geen tweede Access-regel die anderen toelaat.**
