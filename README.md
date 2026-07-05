# SOL Reality Check

SOL Reality Check is een statisch dataproduct voor Solana. Het laat niet alleen zien wat de actuele data suggereert, maar ook hoe sterk het bewijs voor die conclusie is.

Auteur: Jan-Willem Blank, Senior Data Scientist.

## Kern

- Marktsignaal en bewijskwaliteit blijven gescheiden.
- De datapipeline bouwt dagelijkse historie, features, analogieën, backtests en JSON-publicatiebestanden.
- De website draait zonder frontend-buildketen met HTML, CSS, vanilla JavaScript en Chart.js.
- Productiemodus gebruikt live publieke API's. Demomodus gebruikt herkenbare demodata en toont dat zichtbaar.

## Lokaal starten

```bash
python -m pip install -e ".[dev]"
APP_MODE=demo python -m sol_reality_check bootstrap
python -m sol_reality_check validate
python -m sol_reality_check ledger-check
python scripts/build_site.py
python -m http.server --directory site 8000
```

## Secrets

- `COINGECKO_API_KEY`: optioneel voor CoinGecko Demo API.
- `SOLANA_RPC_URL`: optioneel RPC-endpoint.

## GitHub Pages

De workflows publiceren de inhoud van `site/`. Voor private repositories kan GitHub Pages afhankelijk zijn van het GitHub-abonnement. Zie `docs/PAGES_SETUP.md`.

## Disclaimer

SOL Reality Check is een educatief en analytisch dataproduct. Het geeft geen financieel advies en doet geen garantie over toekomstige rendementen. Historische patronen kunnen veranderen en crypto-investeringen kunnen sterk in waarde dalen.
