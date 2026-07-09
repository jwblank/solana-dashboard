# SOL Reality Check

**Live dashboard:** https://jwblank.github.io/solana-dashboard/

SOL Reality Check is een transparant, dagelijks bijgewerkt datadashboard voor Solana. Het dashboard kijkt niet alleen naar de koers van SOL, maar naar het bredere bewijs achter de markt: koerskracht, netwerkgebruik, kapitaalstromen, ecosysteembreedte, historische vergelijkingen, bronkwaliteit en backtests.

Het doel is bewust niet om een simpele koop- of verkoopscore te tonen. SOL Reality Check laat zien **welk beeld de data geeft, hoe sterk dat beeld is onderbouwd en waar de onzekerheid zit**. Daarmee is het dashboard bedoeld als analytisch instrument: compact genoeg om dagelijks te gebruiken, maar volledig genoeg om de aannames en datakwaliteit te kunnen controleren.

## Wat het dashboard bijzonder maakt

Veel crypto-dashboards tonen losse cijfers zonder context. SOL Reality Check bouwt die context juist expliciet in. Elke dagelijkse run combineert marktdata, netwerkdata en historische patronen tot een gestructureerde beoordeling.

De kern bestaat uit twee gescheiden onderdelen:

* **Marktbeeld:** wat zeggen de indicatoren vandaag over Solana?
* **Onderbouwing:** hoe betrouwbaar is dat beeld op basis van datakwaliteit, historie en backtests?

Die scheiding is belangrijk. Een hoog marktsignaal met zwakke onderbouwing betekent iets anders dan een hoog signaal dat historisch goed getest is. Het dashboard probeert die nuance zichtbaar te maken in plaats van te verstoppen.

## Datagedreven, maar controleerbaar

De pipeline haalt publieke data op, valideert bronnen, berekent indicatoren en publiceert daarna statische JSON-bestanden voor GitHub Pages. In het dashboard is zichtbaar welke bronnen succesvol zijn gebruikt en welke fallback-routes eventueel actief waren.

Voor koersdata wordt gewerkt met broncontrole en consensuslogica, zodat afwijkende of onrealistische waarden niet zomaar het dashboard kunnen vervuilen. Extreme uitschieters worden gedetecteerd, bronstatussen worden gelogd en de gebruiker kan terugzien hoe de gepubliceerde waarden tot stand komen.

Het dashboard bevat daarnaast een onderzoeksdataset per run. Elke dagelijkse update legt de belangrijkste waarden vast, zoals SOL- en BTC-koers, score, onderbouwing, koerskracht, netwerkgebruik, kapitaalstromen en ecosysteembreedte. Daarmee ontstaat automatisch een dataset die later gebruikt kan worden voor signaalonderzoek, modelvalidatie en voorspellende analyses.

## Belangrijkste onderdelen

* **Duiding:** een compacte Nederlandstalige interpretatie van de actuele dashboardwaarden, inclusief datum, modelstatus en archief.
* **Vandaag:** de actuele samenvatting van het marktbeeld en de onderbouwing.
* **Prijs:** koerskracht van SOL, inclusief momentum en relatieve sterkte tegenover BTC.
* **Netwerk & ecosysteem:** gebruik van het Solana-netwerk, DeFi-activiteit en breedte binnen het ecosysteem.
* **Kapitaal:** kapitaalstromen, TVL en stablecoin-gerelateerde signalen.
* **Bewijs:** methodiek, backtests, datakwaliteit, bronvalidatie en uitleg van de gebruikte termen.
* **Signaalonderzoek:** een run-voor-run tabel waarmee de ontwikkeling van de signalen kan worden gevolgd.

## Techniek

SOL Reality Check draait volledig statisch op GitHub Pages. Er is geen eigen backend, geen betaalde server en geen handmatige dataverwerking nodig.

De techniek bestaat uit:

* Python voor de datapipeline, validatie, feature-engineering, scoring en backtests.
* GitHub Actions voor dagelijkse updates en deployment.
* GitHub Pages voor publicatie.
* HTML, CSS en vanilla JavaScript voor de frontend.
* Chart.js voor compacte visualisaties.
* JSON en Parquet voor publiceerbare data en onderzoeksdata.

Deze opzet maakt het dashboard reproduceerbaar, goedkoop te draaien en goed controleerbaar. De broncode, data-output en methodiek staan in dezelfde repository, waardoor aannames en resultaten naast elkaar te inspecteren zijn.

## Methodische uitgangspunten

SOL Reality Check is gebouwd rond een paar principes:

* Geen black box zonder uitleg: scores worden gekoppeld aan onderliggende metingen.
* Geen signaal zonder onzekerheid: het dashboard toont ook de kwaliteit van de onderbouwing.
* Geen demo-data in productie: productiedata wordt gevalideerd voordat deze wordt gepubliceerd.
* Geen toekomstinformatie in backtests: historische vergelijkingen worden zo ingericht dat toekomstige data buiten beeld blijft.
* Geen financieel advies: het dashboard is een analytisch dataproduct, geen handelsadvies.

## Lokaal starten

```bash
python -m pip install -e ".[dev]"
APP_MODE=demo python -m sol_reality_check bootstrap
python -m sol_reality_check validate
python -m sol_reality_check ledger-check
python scripts/build_site.py
python -m http.server --directory site 8000
```

Open daarna lokaal:

```text
http://localhost:8000
```

## GitHub Pages

De live versie staat hier:

```text
https://jwblank.github.io/solana-dashboard/
```

De GitHub Actions-workflows bouwen de data, voeren controles uit en publiceren de inhoud van `site/` naar GitHub Pages. Zie ook `docs/PAGES_SETUP.md` voor de Pages-configuratie.

## Disclaimer

SOL Reality Check is bedoeld als analyse- en onderzoeksdashboard. Het is geen financieel advies, geen garantie op rendement en geen automatische handelsstrategie. Crypto-assets kunnen sterk in waarde dalen. Historische patronen kunnen verdwijnen en iedere score moet gelezen worden samen met de datakwaliteit, bronstatus en methodische beperkingen.
