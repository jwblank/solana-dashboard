# SOL Reality Check

SOL Reality Check is een statisch dataproduct dat Solana-marktsignalen koppelt aan de kwaliteit van het onderliggende bewijs. Het toont dus niet alleen **wat** de data suggereert, maar ook **hoe betrouwbaar** die conclusie is.

## Uitgangspunten

* Marktsignaal en bewijskracht worden afzonderlijk beoordeeld.
* De datapipeline bouwt dagelijks historische data, indicatoren, marktanalogieën, backtests en publiceerbare JSON-bestanden.
* De website gebruikt HTML, CSS, vanilla JavaScript en Chart.js, zonder frontend-buildproces.
* De productiemodus gebruikt publieke live-API’s. De demomodus gebruikt duidelijk gemarkeerde voorbeelddata.

## Lokaal starten

python -m pip install -e ".[dev]"
APP_MODE=demo python -m sol_reality_check bootstrap
python -m sol_reality_check validate
python -m sol_reality_check ledger-check
python scripts/build_site.py
python -m http.server --directory site 8000

## GitHub Pages

De workflows publiceren de inhoud van `site/`. Bij private repositories kan beschikbaarheid afhankelijk zijn van het GitHub-abonnement. Zie `docs/PAGES_SETUP.md`.

## Disclaimer

SOL Reality Check is bedoeld analyse. Het is geen financieel advies en biedt geen garantie op toekomstig rendement. Historische patronen kunnen verdwijnen en crypto-investeringen kunnen sterk in waarde dalen.
