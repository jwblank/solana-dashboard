# Publiek onderzoek naar SOL-signalen

De hoofdpagina stelt één vraag: voegen de vastgelegde kandidaten informatie toe
aan dezelfde SOL/BTC-koersbasis, voor zowel stijging als daling? Een zichtbaar
verband tussen twee lijnen beantwoordt die vraag niet zelfstandig.

## Weergave

- **Onderzoek:** oorspronkelijke SOL-dagsloten en één geselecteerde KPI, elk op
  een eigen schaal en met een gedeelde werkelijke tijdas. Standaard de volledige
  beschikbare historie. Markeringen tonen modelrichting en juist/onjuist/open;
  klikken toont het instapslot en het zevendaagse meetvenster.
- **Methode & data:** vaste definities, benchmark, onzekerheid, richtingtellingen,
  secundaire horizons, kalibratie, prijsbroncontroles, downloads en oudere toets.
- **Over het onderzoek:** anonieme uitleg van de onderzoeksvraag, de Solana-context
  en de grenzen van de gevolgtrekkingen.

Nieuwe toetsen en historische reconstructies staan altijd apart. Standaard
worden bij veel markeringen vaste niet-overlappende vensters getoond, zonder
selectie op rendement of juistheid. De schakelaar toont ze allemaal. De statistiek
gebruikt steeds de volledige geselecteerde toetsperiode, ook bij een korter
grafiekbereik. Niet-overlappende vensters zijn niet noodzakelijk onafhankelijk.

De stijgings- en dalingspercentages hebben werkelijke stijgings- en dalingsweken
als noemer (recall); ze zijn dus geen kans dat een aankomend signaal uitkomt.
Het Brier-verschil vergelijkt de kansfout op dezelfde meetdagen. Positief betekent
minder fout, niet automatisch een bruikbare handelsstrategie. Intervallen zijn
per kandidaat, zonder correctie voor alle eerder verkende hypotheses.

Het gemiddelde koerspad voor de twee binaire dalingsregels is beschrijvend en
niet op marktregime gematcht. De 95%-band gebruikt een moving-block bootstrap
van zeven dagelijkse, overlappende vensters (1000 trekkingen; vaste seed).
De continue duur-KPI krijgt geen achteraf gekozen aan/uit-grens.

## Behoud en beschikbaarheid

`lab_snapshot.py` leest oorspronkelijke voorspellingen en parallelarchieven via
de bestaande bronselectie. Per dag worden de eerst opgeslagen koers en KPI
getoond. Een herberekening overschrijft deze niet. KPI-tijden zijn publicatietijden,
prijs-tijden zijn UTC-dagsloten. Prospectieve markeringen staan op registratie;
historische reconstructies op het oorspronkelijke bronmoment, expliciet benoemd.

Alle Parquetbestanden, JSONL-ledgers, protocolversies, voorspellingen, uitkomsten,
schaduwmetingen, het oorspronkelijke archief en de oude prijslogica blijven behouden.
Alleen `site/data/lab_snapshot.json`, `site/data/research_note.json` en de HTML-build
zijn afgeleide presentatieproducten. De oude interface blijft op `legacy.html`.
Dagelijkse prijsvergaring gebruikt de bestaande bronconsensus en herstelbronnen.
Een opgevraagde bron is niet automatisch een werkelijk gebruikte bron. De tabel
toont daarom `used`, controledatum en afwijking afzonderlijk; een controledatum
kan afwijken van het oorspronkelijke getoonde dagslot.

## Taal en dagelijkse bouw

De bestaande volledige LLM-marktduiding blijft toegankelijk. De compacte
onderzoeksduiding laat de bestaande Hugging Face-verbinding alleen kiezen uit
gecontroleerde formuleringen die bij de berekende meetstatus horen. De LLM kan
geen cijfers, bewijsstatus of voorspellingen toevoegen. Bij ontbrekend token of
providerfout verschijnt een vaste formulering; de dataverzameling blijft lopen.

De bestaande scheduler blijft op 09:00 Europe/Amsterdam, inclusief zomer- en
wintertijd. Na de productie-update worden de nieuwe presentatiesnapshot en korte
duiding geschreven. Elke deployment compileert de React-weergave opnieuw uit
die snapshot, met een vast pnpm-lockbestand en runtime-integriteitscontrole.

Lokale bouw:

```sh
pip install -e '.[dev]'
pnpm --dir web install --frozen-lockfile --ignore-scripts
python scripts/export_lab_snapshot.py
python scripts/build_site.py
python scripts/smoke_test.py
```

Test de volledige Python-suite in een afzonderlijke kopie: bestaande demotests
schrijven afgeleide dashboardbestanden. Voer geen demobootstrap uit in een
productiedatawerkmap die daarna gepubliceerd moet worden.
