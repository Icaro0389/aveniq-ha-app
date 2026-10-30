# Aveniq · Home Assistant App

**Versione 0.1.0 — prima release sperimentale**

Plancia domotica indipendente da Lovelace, con layout desktop/mobile, schede luminose e collegamento a Home Assistant OS tramite la proxy API del Supervisor. Non è una fork di DomusUI né di GdAHome; grafica e codice di questa release sono originali.

## Installazione

1. Crea un repository GitHub pubblico, per esempio `aveniq-ha-app`.
2. Carica **il contenuto** di questa cartella nella radice del repository (non la cartella ZIP).
3. Modifica `repository.yaml` e `aveniq/config.yaml` sostituendo `REPLACE_WITH_YOUR_USERNAME` con il tuo username GitHub.
4. In Home Assistant OS: **Impostazioni → App → Negozio → ⋮ → Repository**, incolla `https://github.com/TUO_USERNAME/aveniq-ha-app`, poi aggiorna l'elenco.
5. Installa l'App **Aveniq** e avviala. Apri la UI attraverso **Apri interfaccia web**.
6. Nella pagina dell'App abilita **Mostra nella barra laterale**: apparirà `Aveniq` con la sua icona.

Se il pulsante è assente, verifica che la tua versione di HA OS mostri le App e che l'App sia avviata. Non richiede HACS, VM o LXC aggiuntivi.

### Struttura

- `repository.yaml`: metadati repository delle App.
- `aveniq/config.yaml`: configurazione Supervisor, Ingress, pannello sidebar.
- `aveniq/Dockerfile`: runtime Python precompilato a installazione (nessun npm nel container).
- `aveniq/app/server.py`: piccolo server HTTP e proxy autorizzato verso HA Core.
- `aveniq/app/static`: interfaccia responsive con CSS/JavaScript senza dipendenze esterne.

### Sicurezza

- Token `SUPERVISOR_TOKEN` custodito esclusivamente nel backend dell'App.
- Accesso tramite **Ingress**: non si pubblicano porte sulla rete.
- Allowlist dei comandi consentiti; antifurto, serratura e accessi sono di sola lettura.
- Per un'installazione sperimentale, evitare esposizioni del servizio al di fuori di Ingress.
- Il backend dispone dei privilegi HA Core concessi dal Supervisor: proteggere il repository da modifiche non fidate.

### Funzioni della v0.1

- Stati reali dalle entità già note (temperatura, umidità, energia, luci, tende, allarme, Nuki, UPS, batterie, Proxmox).
- Lettura periodica ogni 8 secondi (non ancora WebSocket live).
- Comandi luci ON/OFF, cover apri/stop/chiudi, climatizzazione e vacuum.
- Frontend responsive progettato per desktop e iPhone.
- Integrazione lato server con HA Core senza token personali.

### Ancora da sviluppare

- Builder drag-and-drop, configurazione entità dall'interfaccia, WebSocket streaming.
- Kodi Smart Bridge (telecomando originale), live camera Tapo, grafici storici, timer, SPA e gestione stanze configurabile.
- Test reale dell'installazione Supervisor e screenshot dal browser dentro Home Assistant.
- Frontend React/TypeScript: questa prima versione usa JS/CSS senza build per semplificare la verifica dell'App; il passaggio a React è previsto quando Ingress e autenticazione sono confermati.

## Test locale

Per controllare che il server serva i file statici senza Home Assistant:

```bash
cd aveniq/app
PORT=8099 python3 server.py
# In un altro terminale:
curl -I http://localhost:8099/ # -I non implementato; usare GET
curl http://localhost:8099/api/health
```

Gli endpoint che richiedono HA falliscono correttamente in locale senza `SUPERVISOR_TOKEN`.


## Aveniq 0.7 — Kodi Smart Bridge

The previous provisional Kodi media_player-only remote has been replaced by
an authenticated backend proxy for Kodi Smart Bridge. The Multimedia page now
uses the real bridge API for Film, Serie TV, Live TV, Radio, VOD, search,
playback and Kodi-native favourites (add/remove), plus navigation D-pad
and transport controls using the bridge's `/v1/remote` endpoint.

### One-time private configuration

In **Home Assistant → Settings → Apps → Aveniq → Configuration**:

- `bridge_url`: your trusted LAN bridge base URL, e.g. `http://KODI_BRIDGE_IP:8787`.
  If using Kodi Smart Bridge HA App (Pilot), use the reachable HA host and mapped port (default 8790).
- `bridge_token`: the existing **Kodi Smart Bridge** bearer token (at least 32 chars).

Save and restart Aveniq. Do not paste the token in GitHub, a YAML dashboard,
or public chat. Aveniq sends it server-to-server; it never reaches browser JS.
The bridge must be reachable from the Aveniq App container.

**Important:** Kodi Smart Bridge **v0.2.2** includes the new `/v1/remote`
API. If your active bridge is the older LXC service, update that LXC's bridge
application to the matching implementation. Updating the separate pilot
repository does **not** automatically update the original LXC service.
The catalog endpoints continue using the prior compatible v0.2 API.

### Widgets

Aveniq's built-in diagnostic gauges and Studio widgets render real HA sensor
values as SVG indicators; they are *not* a verbatim import of the Lovelace-only
Smart Home Cards components. Widget order and width are stored with shared
configuration. Drag and drop currently targets desktop pointers; on mobile the
width control remains available.

### Recovery

The Git branch `backup/pre-0.7.0` preserves Aveniq before this update.
