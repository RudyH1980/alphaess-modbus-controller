# AlphaESS Modbus Controller — negative-price PV control + zero-export

A tiny, self-contained controller for **AlphaESS** inverters that does two things
the AlphaESS app won't let you do directly, over **local Modbus TCP** (no cloud):

1. **Negative-price mode** — when your dynamic electricity price drops below a
   threshold (e.g. below €0.00), it **switches the solar PV OFF** so your house
   imports everything from the grid (you get paid to consume at negative prices),
   and optionally holds / charges / discharges the battery. PV is restored
   automatically the moment the controller stops.
2. **Zero-export** — cap feed-in to the grid (e.g. 0%) on demand.

It runs as a small Docker container next to Home Assistant. HA does the
monitoring (use any AlphaESS integration); this just does the *control*.

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

## Install

```bash
git clone <this-repo> alphaess-bridge && cd alphaess-bridge
cp compose.example.yml docker-compose.yml
# edit docker-compose.yml: inverter IP, HA token, your SOC + price sensor names
docker compose up -d --build
docker compose logs -f
```

### Optional Home Assistant helpers (toggles)

The controller reads these if they exist (both default to "enabled" when absent):

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

## ⚠️ Safety

- This **writes control commands to your battery inverter**. Use at your own risk.
- Discharging the battery **to the grid** at negative prices can **cost** money and
  may affect your **warranty** and feed-in tariff. The default (`neutral`) never
  exports — it only stops the panels and lets the house import.
- AlphaESS allows **one Modbus TCP connection at a time** — don't run two clients.

## Register reference

Dispatch block `0x0880`–`0x088A`: start, active power (×2, offset 32000),
reactive power (×2), mode, SOC (0.4%/bit), time (×2, 1s/bit), flow direction,
**PV switch (`0x088A`: 1=on, 2=off)**. Feed-in limit: `0x0800` (% of AC capacity).

Register knowledge thanks to the AlphaESS community
([Alpha2MQTT](https://github.com/dxoverdy/Alpha2MQTT),
[ha-alphaess-modbus](https://github.com/senalse/ha-alphaess-modbus)).
