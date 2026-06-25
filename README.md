# AlphaESS Modbus Controller — local monitoring + negative-price PV control + zero-export

A tiny, self-contained Home Assistant integration for **AlphaESS** inverters that
talks **local Modbus TCP** (no cloud) and does three things:

1. **Local measurement sensors** *(new in v1.1)* — reads live **PV power** (total +
   per string), **grid power** (total + per phase), **battery power**, **SoC** and
   **house load** straight from the inverter over Modbus. This makes the AlphaESS
   **cloud integration optional** — keep it only as a backup if you like. Registers
   verified against the cloud values on hardware (see *Register reference*).
2. **Negative-price mode** — when your dynamic electricity price drops below a
   threshold (e.g. below €0.00), it **switches the solar PV OFF** so your house
   imports everything from the grid (you get paid to consume at negative prices),
   and optionally holds / charges / discharges the battery. PV is restored
   automatically the moment the controller stops.
3. **Zero-export** — cap feed-in to the grid (e.g. 0%) on demand.

Two ways to run it:

- **As a Home Assistant integration** (HACS) — runs inside HA, gives you three
  switches (`PV Shutdown`, `Negative-price Charge`, `Zero Export`) + a status
  sensor, all configured through the UI. **Recommended.**
- **As a standalone Docker container** (`bridge.py`) — runs next to HA and reads
  a few `input_boolean` helpers. Use this if you don't run HACS.

Since v1.1 the integration **also reads the inverter's live measurements** over the
same Modbus link, so it covers both monitoring *and* control — the AlphaESS cloud
integration is no longer required (keep it as a backup for lifetime/kWh totals if
you want).

The standalone Docker container (`bridge.py`) is **control-only** and is now
considered legacy — the HACS integration is the complete solution.

> ## ⚠️ Wired Ethernet only — Wi-Fi will NOT work
>
> This talks to the inverter over **local Modbus TCP**, which AlphaESS only
> exposes on the **wired Ethernet (RJ45) port**. The **Wi-Fi / 4G dongle is a
> cloud uplink only** — it uploads telemetry to AlphaCloud and does **not** serve
> Modbus, so you can never reach port `502` through it.
>
> **Your inverter must be connected to your LAN with a network cable.** If it's
> on Wi-Fi only, there is no local Modbus and nothing here can work — no setting
> changes that. (This is AlphaESS firmware behaviour, not a limit of this project.)

## The key discovery

AlphaESS exposes a **Dispatch PV Switch** at Modbus register **`0x088A`**
(`1 = PV on`, `2 = PV off`). It only takes effect **while a dispatch is active**
(`0x0880 = 1`), and the inverter **restores PV automatically when the dispatch
ends** — a built-in safety net. That single register is what lets you truly
curtail the panels to 0 W regardless of house load. Verified on hardware
(SMILE, slave id 85): PV dropped from ~2000 W to 0 W instantly.

The active-power setpoint uses a **32000 offset** (`<32000` = charge,
`>32000` = discharge); `32000` = 0 W (neutral).

## Requirements

- AlphaESS inverter on your LAN by **wired Ethernet (RJ45)** with **Modbus TCP
  enabled** (port 502). **Modbus does NOT work over the Wi-Fi/4G dongle** — that
  dongle only talks to AlphaCloud (see the warning above). Firmware reasonably up
  to date.
- Home Assistant with:
  - a **long-lived access token**,
  - a sensor for the **battery State-of-Charge** (%),
  - a sensor for the **current electricity price** (€/kWh) that can go negative —
    Frank Energie, Nordpool, EPEX, Tibber, ENTSO-e, …
- Docker + Docker Compose on the same LAN as the inverter.

## Install — Home Assistant integration (HACS, recommended)

1. **HACS → ⋮ → Custom repositories** → add
   `https://github.com/RudyH1980/alphaess-modbus-controller`, category **Integration**.
2. Install **AlphaESS Modbus Controller**, then **restart Home Assistant**.
3. **Settings → Devices & Services → Add Integration → AlphaESS Modbus Controller**.
4. Fill in the inverter IP/port/unit and pick your **SOC** and **price** sensors.

You get a device with:

| Entity | What it does |
|---|---|
| `switch.alphaess_pv_shutdown` | Force PV off now (curtail panels to 0 W). |
| `switch.alphaess_negative_price_charge` | While PV is off, charge the battery from the grid. |
| `switch.alphaess_zero_export` | Cap feed-in to 0%. |
| `sensor.alphaess_status` | Current mode (`normal` / `pv_off` / `zero_export`) + price/SOC attributes. |

PV also switches off **automatically** whenever the price sensor drops below the
configured threshold — no automation needed. Thresholds are editable later via
**Configure** (options) without re-adding the integration.

### Live measurement sensors (v1.1)

The same device also exposes read-only power/SoC sensors, polled over Modbus every
cycle (so much fresher than the cloud — seconds, not a minute):

| Quantity | Notes |
|---|---|
| PV power — total + strings 1–4 | W, per MPPT string |
| Grid power — total + L1/L2/L3 | W, signed (`+` = import, `−` = export) |
| Battery power | W, signed (`−` = charging, `+` = discharging) |
| Battery SoC | % |
| House load | W, derived from the energy balance (PV + grid + battery) |

Because the SoC now comes from Modbus, the integration **no longer depends on a
cloud SoC sensor** for its control logic (a configured SOC sensor, if any, is only
a fallback). Energy/kWh totals (daily generation, feed-in, etc.) are **not**
provided locally yet — keep the AlphaESS cloud integration as a backup for those.

### Dashboard card

A ready-made Lovelace card lives in [`lovelace-card.yaml`](lovelace-card.yaml)
(built-in cards only). **Dashboard → Edit → Add card → Manual** and paste it —
you get the three switches plus the status sensor with price/SOC attributes.

## Install — standalone Docker container (alternative)

```bash
git clone <this-repo> alphaess-bridge && cd alphaess-bridge
cp compose.example.yml docker-compose.yml
# edit docker-compose.yml: inverter IP, HA token, your SOC + price sensor names
docker compose up -d --build
docker compose logs -f
```

### Optional Home Assistant helpers (toggles, Docker mode)

The container reads these if they exist (both default to "enabled" when absent):

- `input_boolean.alphaess_zero_export` — turn zero-export on/off.
- `input_boolean.alphaess_negative_price_mode` — master kill-switch for the
  negative-price automation.

## Configuration (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `ALPHAESS_HOST` | `192.168.1.55` | Inverter IP |
| `ALPHAESS_PORT` | `502` | Modbus TCP port |
| `ALPHAESS_UNIT` | `85` | Modbus slave id |
| `HA_URL` | `http://127.0.0.1:8123` | Home Assistant base URL |
| `HA_TOKEN` | — | Long-lived access token (**required**) |
| `POLL_INTERVAL` | `60` | Seconds between cycles |
| `HA_SOC_SENSOR` | — | Battery SOC sensor (%) |
| `DEFAULT_ZERO_EXPORT` | `false` | Zero-export when the helper is absent |
| `NEG_PRICE_ENABLED` | `true` | Enable negative-price mode |
| `NEG_PRICE_SENSOR` | — | Electricity price sensor (€/kWh) |
| `NEG_PRICE_THRESHOLD` | `0.0` | Go to PV-off below this price |
| `NEG_BATTERY_MODE` | `neutral` | `neutral` \| `charge` \| `discharge` |
| `NEG_BATTERY_POWER` | `2000` | W for charge/discharge |
| `NEG_DISCHARGE_SOC_FLOOR` | `15` | Don't discharge below this SOC % |

## What it does NOT do

- It reads live **power + SoC** but does **not** provide energy/kWh totals yet
  (daily generation, feed-in, lifetime) — keep the AlphaESS cloud integration as a
  backup for those figures.
- It does **not** replace your normal battery strategy. Outside negative-price /
  zero-export moments it leaves the inverter on its own self-consumption logic.
- It does **not** touch the cloud, the AlphaESS app, or any installer settings —
  pure local Modbus, nothing is unlocked or reflashed.
- It will **not** keep PV off if it crashes or stops: the inverter restores PV by
  itself when the dispatch ends, so a dead container can't strand you at 0 W.
- It does **not** manage other loads (heat pumps, EV, etc.) — battery + PV only.

## Notes

- This **writes control commands to your inverter** over Modbus — use at your own risk.
- The default (`neutral` / `charge`) never exports: it stops the panels and lets the house import.
- AlphaESS allows **one Modbus TCP connection at a time** — don't run two clients.

## Register reference

Dispatch block `0x0880`–`0x088A`: start, active power (×2, offset 32000),
reactive power (×2), mode, SOC (0.4%/bit), time (×2, 1s/bit), flow direction,
**PV switch (`0x088A`: 1=on, 2=off)**. Feed-in limit: `0x0800` (% of AC capacity).

**Measurement registers** *(read-only, FC3 holding, 32-bit big-endian unless noted;
verified against cloud values on hardware 2026-06-25):*

| Register | Quantity | Type / scale | Sign |
|---|---|---|---|
| `0x0453` | PV total power | uint32, W | + |
| `0x041F`/`0x0423`/`0x0427`/`0x042B` | PV string 1–4 power | uint32, W | + |
| `0x001B`/`0x001D`/`0x001F` | Grid power L1/L2/L3 | int32, W | + import / − export |
| `0x0021` | Grid power total | int32, W | + import / − export |
| `0x0126` | Battery power | int16, W | − charge / + discharge |
| `0x0102` | Battery SoC | int16, ×0.1 → % | + |

Register knowledge thanks to the AlphaESS community
([Alpha2MQTT](https://github.com/dxoverdy/Alpha2MQTT),
[ha-alphaess-modbus](https://github.com/senalse/ha-alphaess-modbus),
[hillviewlodge AlphaESS Modbus](https://projects.hillviewlodge.ie/alphaess/)).

---

## Samenvatting (Nederlands)

Een Home Assistant-integratie die je **AlphaESS-omvormer lokaal via Modbus TCP**
uitleest én aanstuurt (geen cloud), voor drie dingen:

1. **Lokale meetsensoren** *(nieuw in v1.1)* — leest live **PV-vermogen** (totaal +
   per string), **grid-vermogen** (totaal + per fase), **accu-vermogen**, **SoC** en
   **huisverbruik** rechtstreeks uit de omvormer. Daarmee is de AlphaESS-**cloud­
   integratie optioneel** (alleen nog backup voor kWh-totalen). Registers op hardware
   geijkt tegen de cloud-waardes.
2. **Negatieve-prijs-modus** — zakt je stroomprijs onder een drempel (bijv. < €0,00),
   dan zet hij de **zonnepanelen uit** zodat je huis alles van het net trekt (je krijgt
   bij negatieve prijzen betáald om te verbruiken) en houdt/laadt/ontlaadt de accu
   optioneel. Stopt de controller, dan herstelt de omvormer de PV **vanzelf**.
3. **Zero-export** — teruglevering aan het net begrenzen (bijv. 0%) op commando.

> ### ⚠️ Alleen via bekabeld ethernet — wifi werkt NIET
>
> De besturing loopt over **lokaal Modbus TCP**, en AlphaESS stelt dat alléén
> beschikbaar op de **bekabelde ethernetpoort (RJ45)**. De **wifi-/4G-dongle is
> puur een cloud-uplink** (telemetrie naar AlphaCloud) en serveert géén Modbus —
> poort `502` is daar nooit bereikbaar. **De inverter moet dus met een
> netwerkkabel aan je LAN hangen.** Alleen-wifi = geen lokale Modbus = niks
> werkt. Dit is firmware-gedrag van AlphaESS, geen beperking van dit project.

Te installeren **als HACS-integratie** (draait in HA, geeft drie schakelaars +
status-sensor, alles via de UI) plus de live meetsensoren (PV/grid/accu/SoC/
huisverbruik). De losse Docker-container is control-only en daarmee legacy. De kern
van de besturing is Modbus-register `0x088A`
(PV-switch) — daarmee knijp je de panelen écht naar 0 W. Op hardware bewezen:
PV van ~2000 W naar 0 W.
