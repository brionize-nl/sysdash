# Architectuur

De hub serveert een statisch dashboard met een alleen-lezen API-proxy. Zowel dashboard als beheer-API controleren de Tailscale-identiteit tegen de ingestelde operators. Er wordt geen login-geheim of Supabase-key in de browserconfig gezet. Het dashboard bindt op het eigen Tailscale-IPv4-adres, niet op alle interfaces.

Agents gebruiken de anon-key uitsluitend om `sysdash_agent_api` aan te roepen. Hun aparte token wordt in Supabase als SHA-256-hash opgeslagen en bindt ieder verzoek aan één machinenaam. De functie accepteert vaste operaties en gebruikt altijd die gecontroleerde machinenaam, ongeacht de machinenaam in een ingestuurd meetobject. Het hub-dashboard en n8n gebruiken server-side een service-key; extra machines krijgen die niet.

Code en privileged helpers zijn root-owned. Een vaste helper kan geselecteerde SysDash-diensten herstarten, caches/logs opruimen, een energieprofiel zetten of rebooten. Hij accepteert geen commando's of bestandspaden van de aanroeper. Basis installeert geen passwordless sudoacties. Moduswisselen gebeurt lokaal met de installer.

Livegegevens worden alleen gebruikt als de timestamp recent is. Historie wordt gepagineerd; sessiedetectie controleert tijdgaten. Een lagere klokfrequentie wordt als frequentiedaling weergegeven, zonder bewezen temperatuurdiagnose. Er is nog geen statistische baseline/anomaliedetector.

Drempels komen uit config plus machine-overrides. Schijfalerts beoordelen afzonderlijke mounts; temperatuuralarm vereist minstens twee minuten aanhoudend hoge temperatuur in de opeenvolgende workflowwaarnemingen. Kernel-/uitstelrisico is geen bewijs dat een update een beveiligingsupdate is.

De updater is optioneel, beheert alleen zijn eigen apt-holds, stopt op onzekere input en rapporteert geen aantallen die alleen gepland waren. Pakketbeheeracties delen een lock. Er is geen automatische reboot of pakket-autoremove.

De heartbeat bewaakt recente metingen, database, renderer en de laatste bevestigde rapportbezorging. Er blijven praktische beperkingen zoals hardware-/OS-ondersteuning, Tailscale-regels en de n8n-netwerkopzet; die worden getest volgens VALIDATION.md.
