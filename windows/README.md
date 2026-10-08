# Windows-agent

Alleen CPU, geheugen, schijven, netwerk, accu en uptime. Geen Linux-beheeracties, updatebeheer of ingebouwde temperatuurmeting.

Maak eerst op de hub een aparte machineconfig met `install/create-agent.py`. Houd de volledige repository op Windows, zodat de agent ook `../common.py` kan lezen. Installeer Python met PATH ingeschakeld.

```powershell
powershell -ExecutionPolicy Bypass -File install-windows.ps1 -ConfigPath C:\privé\windows-pc.env
```

Het script beperkt de lokale configuratierechten, test een meting en een echte push, en registreert daarna een taak bij inloggen. De taak mag op accu blijven draaien. Gebruik geen Supabase-service-key op deze machine; alleen de eigen agent-token.

Controleer Taakplanner na installatie en na opnieuw inloggen. Deze PowerShell-/Taakplanner-praktijktest is nog niet uitgevoerd op echte Windows-hardware.
