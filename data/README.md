# Data

`data/curated` bevat opgebouwde dagreeksen. `data/ledger` bevat append-only logboeken met officiële voorspellingen, kandidaat-signalen en latere uitkomsten. Fixtures horen alleen in tests of expliciete demomodus.

De Voorspelmonitor gebruikt drie afzonderlijke ledgers:

* `signal_definitions.jsonl`: onveranderlijke, geversioneerde signaaldefinities;
* `signal_events.jsonl`: onafhankelijke clusterstarts op basis van de eerste officiële dagpublicatie;
* `signal_outcomes.jsonl`: later volwassen geworden uitkomsten per event en horizon.

Elke regel bevat `payload_sha256`. Bestaande regels worden niet gewijzigd of verwijderd. Een conflicterende sleutel stopt de generator. Historische backfill is permanent gemarkeerd als `retrospective`; alleen na de definitielock gepubliceerde events kunnen als `prospective` meetellen.

Opnieuw genereren:

```bash
PYTHONPATH=src python scripts/generate_predictive_monitor.py
```

De generator leest `predictions.jsonl` en `signaalonderzoek.parquet`, schrijft alleen ontbrekende ledgerregels bij en bouwt `site/data/predictive_monitor.json`. De drie publieke JSONL-bestanden in `site/data/` zijn byte-identieke downloadkopieën.
