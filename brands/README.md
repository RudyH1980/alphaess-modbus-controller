# Brand assets — AlphaESS Modbus Controller

Logo/icon voor de Home Assistant-integratie (`domain: alphaess_controller`).

| Bestand | Formaat | Doel |
|---|---|---|
| `raw_logo.png` | 1024×1024, RGBA | Bronbestand (door Grok gegenereerd), bewaar voor toekomstige edits |
| `icon.png` | 256×256, transparant | home-assistant/brands icon |
| `icon@2x.png` | 512×512, transparant | home-assistant/brands hi-DPI icon |
| `custom_integrations/alphaess_controller/` | — | exacte map om in een **brands**-fork te plakken |

Accu + bliksem + zon, flat vector, groen/blauw. Geen tekst (brands-eis). Achtergrond
volledig transparant; getrimd en gecentreerd op een vierkant canvas.

## home-assistant/brands PR (nodig voor de officiële HACS-lijst)

De officiële HACS-default-lijst vereist dat het domein bij **home-assistant/brands**
geregistreerd staat. Voor een via HACS gedistribueerde (niet-core) integratie horen de
iconen onder **`custom_integrations/<domain>/`**.

1. Fork https://github.com/home-assistant/brands
2. Kopieer `custom_integrations/alphaess_controller/` (deze map) naar de root van de fork:
   ```
   custom_integrations/alphaess_controller/icon.png      # 256×256
   custom_integrations/alphaess_controller/icon@2x.png   # 512×512
   ```
   (Een `logo.png` is optioneel; zonder logo gebruikt HA het icon. Niet nodig.)
3. Commit + push + open een PR naar `home-assistant/brands`.
4. De CI van brands controleert: exacte afmetingen (256/512), transparante achtergrond,
   getrimd, geen tekst. Deze assets voldoen daaraan.
5. Na merge: haal `ignore: brands` uit `.github/workflows/validate.yml` zodat ook de
   brands-check in de HACS-validatie meedraait.

## Regenereren / aanpassen

```bash
# vanuit deze map, met ImageMagick:
convert raw_logo.png -trim +repage -resize 224x224 -background none \
  -gravity center -extent 256x256 icon.png
convert raw_logo.png -trim +repage -resize 448x448 -background none \
  -gravity center -extent 512x512 icon@2x.png
cp icon.png icon@2x.png custom_integrations/alphaess_controller/
```
