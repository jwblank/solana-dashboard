# Methodology

Rendement is `prijs_t / prijs_t-n - 1`. Relatieve sterkte is SOL-rendement min BTC-rendement. Volatiliteit gebruikt log-rendementen over 30 dagen. Drawdown is de afstand tot de hoogste koers in 90 dagen.

Normalisatie gebruikt uitsluitend eerdere data: `0.6745 * (waarde - rolling mediaan) / MAD`, geclipt op `[-4, 4]`. Indicatoren worden naar 0-100 vertaald met `50 + 12.5 * z`.

Analogieën gebruiken een gewogen Euclidische afstand op robuust genormaliseerde features. Similarity is `100 * exp(-0.5 * afstand^2)`.

Bewijskwaliteit combineert datakwaliteit, steekproefomvang, out-of-sample kwaliteit, stabiliteit en analogie-overeenkomst. Caps voorkomen te stellige conclusies bij zwakke onderbouwing.

## Overzicht: Wat veranderde?

De standaardpagina vergelijkt de actuele officiële productierun met de vorige officiële productierun. Scoreveranderingen worden in punten getoond; koersveranderingen worden in dollars en procenten getoond. Een score is geen kanspercentage.

De driver-waterfall gebruikt gewogen bijdragen:

```text
gewogen bijdrage = blokscore x blokgewicht
```

Voor nieuwe runs worden blokgewichten en gewogen bijdragen additief opgeslagen in `data/curated/signaalonderzoek.parquet`. Bestaande historische rijen worden niet herschreven wanneer nieuwe visualisaties of kolommen worden toegevoegd.

## Backtest versus publiek trackrecord

Een historische backtest en een publiek forward trackrecord zijn verschillende vormen van bewijs. De backtest gebruikt historische data om de methode te toetsen. Het publieke trackrecord bestaat uit werkelijk gepubliceerde productieruns en later beschikbare uitkomsten.

De maturiteitsstatus van het publieke trackrecord zegt alleen iets over de lengte van dat openbare spoor:

* 0-29 officiële runs: Startfase
* 30-99 officiële runs: Opbouwfase
* 100-249 officiële runs: Eerste structurele evaluatie mogelijk
* 250 of meer officiële runs: Volwassen publiek trackrecord

Deze status is geen prestatieclaim en zegt niets over winstgevendheid.
