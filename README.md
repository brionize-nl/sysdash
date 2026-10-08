# SysDash

Een privé dashboard voor één of meer machines. Linux-agents meten CPU, geheugen, temperaturen, schijven, netwerk en accu; Windows gebruikt een lichte agent. Supabase bewaart de data. Advanced voegt beheer via Tailscale en optionele Discord-rapporten toe.

## Begin hier

Lees [de installatiehandleiding](docs/AAN_DE_SLAG.md). Geen ISO of herinstallatie van Linux nodig: SysDash draait bovenop een bestaande Debian/Ubuntu-machine met systemd.

De begeleide installer vraagt de instellingen, controleert de database en Tailscale, installeert beschermde systeembestanden en bevestigt pas succes na een echte eerste meting.

```bash
sudo bash install/setup.sh --role hub --mode basis
```

- **Basis:** dashboard en metingen; geen systeemacties of automatische updates.
- **Advanced:** vaste beheeracties voor toegestane Tailscale-gebruikers, met optionele Discord-rapporten.
- **Updates:** blijven uit totdat je expliciet `--enable-updates` gebruikt.
- **Privé:** geen publieke tunnel; de browser krijgt geen Supabase-sleutels. Extra agents krijgen uitsluitend een eigen machine-token.

Gebruik een apart Supabase-project. De nieuwe toegangsmigratie is een wijziging van de oude publieke template; lees het [migratieplan](docs/SETUP.md) voordat je een bestaande installatie vervangt.

## Controle en beperkingen

Zie [de uitgevoerde controles en resterende praktijktests](docs/VALIDATION.md). Database-, browser- en foutpadtests worden ook in CI uitgevoerd. Tests met mocks zijn geen bewijs dat jouw hardware, Tailscale-regels, Windows-taak of Discord-kanaal al werkt.

MIT-licentie, zie [LICENSE](LICENSE).
