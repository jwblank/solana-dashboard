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

* **Overzicht:** de standaardpagina rond de vraag wat sinds de vorige officiële productierun veranderde.
* **Duiding:** een compacte Nederlandstalige interpretatie van de actuele dashboardwaarden, inclusief datum, modelstatus en archief.
* **Vandaag:** de actuele samenvatting van het marktbeeld en de onderbouwing.
* **Prijs:** koerskracht van SOL, inclusief momentum en relatieve sterkte tegenover BTC.
* **Netwerk & ecosysteem:** gebruik van het Solana-netwerk, DeFi-activiteit en breedte binnen het ecosysteem.
* **Kapitaal:** kapitaalstromen, TVL en stablecoin-gerelateerde signalen.
* **Bewijs:** methodiek, backtests, datakwaliteit, bronvalidatie en uitleg van de gebruikte termen.
* **Signaalonderzoek:** een run-voor-run tabel waarmee de ontwikkeling van de signalen kan worden gevolgd.

## Wat Veranderde?

De homepage is ontworpen rond één praktische vraag: **wat veranderde sinds de vorige officiële productierun?**

Daarom toont het dashboard niet alleen de huidige score, maar ook:

* de vorige officiële productierun waarmee wordt vergeleken;
* de verandering in huidige sterkte, uitgedrukt in scorepunten;
* de verandering in onderbouwing, ook uitgedrukt in scorepunten;
* de verandering in SOL-slotkoers, uitgedrukt in dollars en procenten;
* de grootste positieve en negatieve driververanderingen;
* de belangrijkste omslagpunten om vanaf nu te volgen.

Een scoreverschil is dus geen kanspercentage. Een koersverschil is iets anders dan een scoreverschil. Die scheiding is bewust zichtbaar gemaakt.

## Driver-Waterfall

De overzichtspagina bevat een driver-waterfall die laat zien waardoor de totaalscore veranderde. De waterfall gebruikt gewogen bijdragen:

```text
gewogen bijdrage = blokscore x blokgewicht
```

Voorbeelden van blokken zijn koerskracht, netwerkgebruik, kapitaalstromen en ecosysteembreedte. De waterfall vergelijkt de gewogen bijdrage van elk blok met de vorige officiële productierun. De stappen zijn cumulatief: de balk voor netwerkgebruik begint op het niveau waar koerskracht eindigde. Als methodeversies niet betrouwbaar vergelijkbaar zijn, wordt geen misleidende waterfall getoond en valt de pagina terug op ruwe scoreveranderingen.

Nieuwe runs slaan de gebruikte blokgewichten en gewogen bijdragen additief op in `data/curated/signaalonderzoek.parquet`. Bestaande historische rijen worden niet herschreven om latere visualisaties mooier te maken.

## Publiek Trackrecord

Het dashboard maakt expliciet onderscheid tussen:

* **historische backtest:** toetsing op historische data;
* **publiek forward trackrecord:** werkelijk gepubliceerde productieruns en later beschikbare uitkomsten.

Een backtest wordt nooit gepresenteerd als live trackrecord. De maturiteitsstatus is gebaseerd op unieke officiële signalen uit het append-only prediction-ledger, niet op technische GitHub Actions-runs. Een technische rerun met dezelfde `prediction_id` telt dus niet als nieuw signaal.

De maturiteitsstatus zegt alleen iets over de lengte van het publieke trackrecord:

* 0-29 officiële runs: Startfase
* 30-99 officiële runs: Opbouwfase
* 100-249 officiële runs: Eerste structurele evaluatie mogelijk
* 250 of meer officiële runs: Volwassen publiek trackrecord

Meer observaties betekenen niet automatisch betere voorspellingen. Daarom toont het dashboard apart:

* technische updates;
* officiële signalen;
* afgeronde forward-uitkomsten;
* historische backteststatistieken;
* datakwaliteit en methode-informatie.

Forwardstatus gebruikt uitsluitend forwardgegevens. Backteststatus gebruikt uitsluitend historische backtestgegevens.

## Methodeversies

Methodegewichten en methodebeschrijvingen staan centraal in:

```text
config/method_versions.yml
```

Deze configuratie wordt gebruikt voor de driver-waterfall, methodevergelijkbaarheid en methodewijzigingsmarkers in de scorehistorie. Wanneer meerdere methodeversies in de historie voorkomen, toont de grafiek de overgang zichtbaar en worden scorelijnen per methodeversie onderbroken, zodat een rekenkundige methodewijziging niet als marktbeweging wordt gelezen.

## Nieuwe Publicatiebestanden

Naast de bestaande JSON-bestanden publiceert de pipeline:

* `site/data/overview.json`: actuele vergelijking met de vorige officiële productierun, driver-waterfall en trackrecordstatus;
* `site/data/overview_history.json`: compacte scorehistorie en methodewijzigingen voor de homepagegrafiek;
* `site/data/signaalonderzoek.parquet`: volledige publieke kopie van de bron-Parquet;
* `site/data/signaalonderzoek.json`: compacte recente selectie voor de frontendtabel.

De bron van waarheid blijft altijd:

```text
data/curated/signaalonderzoek.parquet
```

Afgeleide bestanden in `site/data/` mogen deze bron nooit overschrijven.

## Veilige Migratie Van Signaalonderzoek

De historische onderzoeksdata is een primaire asset. Bestaande rijen worden nooit achteraf aangepast, verwijderd of gereconstrueerd om een mooier trackrecord te creëren.

Het append-proces voor `data/curated/signaalonderzoek.parquet` is daarom niet-destructief:

* bestaande kolommen blijven behouden;
* onbekende legacykolommen blijven behouden;
* nieuwe kolommen worden uitsluitend additief toegevoegd;
* demo-runs worden niet naar de productiehistorie geschreven;
* dezelfde `run_at_utc` met identieke inhoud is idempotent;
* dezelfde `run_at_utc` met afwijkende inhoud veroorzaakt een harde fout;
* er wordt eerst naar een tijdelijk Parquet-bestand geschreven;
* het tijdelijke bestand wordt opnieuw gelezen en gevalideerd;
* pas daarna vervangt een atomaire operatie het definitieve bestand.

Dry-run:

```bash
PYTHONPATH=src python scripts/migrate_signal_research.py
```

Toepassen met back-up:

```bash
PYTHONPATH=src python scripts/migrate_signal_research.py --apply
```

Bij `--apply` maakt het script eerst een timestamped back-up naast de bron-Parquet. Herstellen kan door de back-up terug te plaatsen als `data/curated/signaalonderzoek.parquet` en daarna de pipeline opnieuw te draaien zodat de publieke bestanden opnieuw worden afgeleid.

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

## License

This project is licensed under the PolyForm Noncommercial License 1.0.0.

You may view, copy, modify, and share the source code for personal, educational, research, and other non-commercial purposes. Commercial use is not permitted without prior written permission.

Copyright © 2026 Jan-Willem Blank.

