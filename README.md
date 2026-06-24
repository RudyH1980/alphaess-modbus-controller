# AlphaESS Modbus Controller — negative-price PV control + zero-export

A tiny, self-contained controller for **AlphaESS** inverters that does two things
the AlphaESS app won't let you do directly, over **local Modbus TCP** (no cloud):

1. **Negative-price mode** — when your dynamic electricity price drops below a
   threshold (e.g. below €0.00), it **switches the solar PV OFF** so your house
   imports everything from the grid (you get paid to consume at negative prices),
   and optionally holds / charges / discharges the battery. PV is restored
   automatically the moment the controller stops.
2. **Zero-export** — cap feed-in to the grid (e.g. 0%) on demand.

Two ways to run it:

- **As a Home Assistant integration** (HACS) — runs inside HA, gives you three
  switches (`PV Shutdown`, `Negative-price Charge`, `Zero Export`) + a status
  sensor, all configured through the UI. **Recommended.**
- **As a standalone Docker container** (`bridge.py`) — runs next to HA and reads
  a few `input_boolean` helpers. Use this if you don't run HACS.

Either way HA does the monitoring (use any AlphaESS integration); this just does
the *control*.

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

- AlphaESS inverter reachable by **wired Ethernet** with **Modbus TCP enabled**
  (port 502; Modbus does not work over Wi-Fi). Firmware reasonably up to date.
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

- It is **not** a monitoring/dashboard tool — Home Assistant already reads your
  inverter; this only *writes* control commands.
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

Register knowledge thanks to the AlphaESS community
([Alpha2MQTT](https://github.com/dxoverdy/Alpha2MQTT),
[ha-alphaess-modbus](https://github.com/senalse/ha-alphaess-modbus)).

---

## Samenvatting (Nederlands)

Een klein, zelfstandig Docker-containertje dat je **AlphaESS-omvormer lokaal via
Modbus TCP** aanstuurt (geen cloud), voor twee dingen die de AlphaESS-app niet
toelaat:

1. **Negatieve-prijs-modus** — zakt je stroomprijs onder een drempel (bijv. < €0,00),
   dan zet hij de **zonnepanelen uit** zodat je huis alles van het net trekt (je krijgt
   bij negatieve prijzen betáald om te verbruiken) en houdt/laadt/ontlaadt de accu
   optioneel. Stopt de controller, dan herstelt de omvormer de PV **vanzelf**.
2. **Zero-export** — teruglevering aan het net begrenzen (bijv. 0%) op commando.

Te installeren **als HACS-integratie** (draait in HA, geeft drie schakelaars +
status-sensor, alles via de UI) óf als losse Docker-container. Home Assistant doet
de monitoring, dit doet alléén de besturing. De kern is Modbus-register `0x088A`
(PV-switch) — daarmee knijp je de panelen écht naar 0 W. Op hardware bewezen:
PV van ~2000 W naar 0 W.
