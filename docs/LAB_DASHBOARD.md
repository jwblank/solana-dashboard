# Publiek onderzoek naar SOL-signalen

## Ontleding van de blauwe score

De sectie onder de koersgrafiek koppelt dezelfde inspectiedag aan vijf gewogen
bijdragen en elf marktvariabelen. De gestapelde strook, som, geregistreerde
bovengrens en oorspronkelijke eindscore maken begrenzingen zichtbaar. De
historische compositiegrafiek volgt dezelfde tijdperiode als de koersgrafiek.
Een klik op een van de grafieken of de dagkeuze wijzigt de inspectie.

De volledige opbouw komt uitsluitend uit het runarchief met hetzelfde
publicatietijdstip, datadag en dezelfde eindscore. Het archief wordt op hash
gecontroleerd; de gewogen som na begrenzing moet binnen 0,03 punt aansluiten
op de opgeslagen eindscore (afronding). Voor oudere dagen zijn aantal en
gelijkenis soms uit opgeslagen analogieën te herleiden; deze bijdragen staan
expliciet als reconstructie aangeduid. Ontbrekende datakwaliteit, testkwaliteit
en vaste stabiliteitsinvoer worden niet teruggevuld. De oorspronkelijke
blauwe lijn blijft volledig; het gestapelde vlak bevat alleen complete dagen.

Marktmetingen komen bij een exact passend runarchief uit de opgeslagen
modelinvoer, inclusief controle van de Parquet-hash. Anders uit de eerste beschikbare Parquet-run voor dezelfde
datadag, uiterlijk op het eerste publicatietijdstip. Ontbrekende waarden
blijven leeg, ook in minigrafieken. De gewichten zijn de gedocumenteerde
analogiegewichten, genormaliseerd bij volledige invoer; het zijn geen gewichten
van de blauwe score of causale effecten. Alle presentatieproducten zijn
afgeleid en veranderen de primaire datasets en modellen niet.

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
