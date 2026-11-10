# Gericht voorspelonderzoek

De Voorspelmonitor beantwoordt: voegt een dashboardkenmerk iets toe aan een eenvoudige voorspelling op basis van koersontwikkeling, tijd en weekdag? Alle modelkansen zijn experimenteel. Historische verkenning en nieuwe toetsuitkomsten zijn expliciet gescheiden.

## Dagelijks proces

De bestaande productierun om 09:00 Europe/Amsterdam voert de volgende stappen uit:

1. Controleer/maak het onveranderlijke basisarchief voordat bestaande afgeleide bestanden worden bijgewerkt.
2. Haal data op, bereken de bestaande scores en voeg de oorspronkelijke onderzoeksrun en officiële prediction toe.
3. Werk de bestaande groene-clustermonitor bij.
4. Archiveer verwerkte historie, dashboard, bronstatus, instellingen, indicatorconfiguratie en de gebruikte Python-implementatie, gecomprimeerd en met een inhoudshash.
5. Bereken een alternatieve onderbouwingsscore met een kalendergebalanceerde backtest; bewaar deze naast de oorspronkelijke score.
6. Registreer vier termijnen voor drie onderzoekskandidaten; voeg volledig bekende uitkomsten toe.
7. Controleer originele bronhistorie en alle nieuwe ledgers; publiceer de afgeleide JSON en downloadkopieën.

De dagelijkse en wekelijkse workflows committen ook `data/research`. Er is geen tweede scheduler toegevoegd. Demo-runs vullen deze productiearchieven niet.

## Vaste definities

De machineleesbare definitie staat in `config/research_protocol.json`, met protocolstart op 9 november 2026 15:03:04 UTC. De eerste registratie kopieert de definitie naar de onveranderlijke definitie-ledger.

| Kandidaat | Kenmerk |
|---|---|
| Blauwe duur | Aandeel van de laatste 14 kalenderdagen met de oorspronkelijk gepubliceerde onderbouwingsscore boven 65. |
| Afnemende blauwe blokfrequentie | Minder blokstarts in de laatste 10 kalenderdagen dan in het 10-daags venster dat 7 dagen eerder eindigde. Een start is de overgang van maximaal 65 naar boven 65. |
| Netwerkzwakte | Netwerkscore onder 50, uit een componentsnapshot die bij de eerste officiële prediction al beschikbaar was. |

Ontbrekende kalenderdagen tellen niet als nul: een onvolledig venster krijgt geen kenmerkwaarde. Bij meerdere runs op één datadag gebruiken we de eerste officiële prediction. Een latere componentsnapshot mag niet alsnog informatie aan een eerdere prediction toevoegen.

De twee binaire regels verwachten daling wanneer ze actief zijn; een inactieve regel geeft geen expliciet stijgingssignaal. De afzonderlijke modeluitbreidingen produceren op iedere complete meetdag een experimentele kans op stijging.

## Koersankers en tijdsvolgorde

De instap is het UTC-dagslot van de publicatiedag, dus ná publicatie. De eindkoers is exact 1, 3, 7 of 14 kalenderdagen later. Zeven dagen is primair. Er wordt niet geïnterpoleerd. Rendementen zijn indicatieve dagslotrendementen zonder kosten, slippage, shortfinanciering of uitvoeringsgarantie; er is geen netto handelsstrategie getest.

Voor zowel instap- als uitstapkoers wordt het eerste bronrecord met beschikbaarheidstijd bewaard. Een uitkomst blijft open zolang een benodigde SOL- of BTC-koers ontbreekt. SOL minus BTC betekent het verschil tussen de twee procentuele rendementen; het is geen beta-gecorrigeerde alpha.

Een voorspelling is alleen prospectief als de bronpublicatie na de protocolstart valt en de registratie vóór het instapslot gebeurt. Een later gereconstrueerde prediction blijft historisch, ook als zijn publicatiedatum na de protocolstart ligt. Geen nieuwe uitkomsten worden achteraf aan de bevestigingsperiode toegevoegd door ze prospectief te hernoemen.

## Basis en modeluitbreiding

De basis bevat SOL- en BTC-momentum over zeven dagen, een lineaire tijdtrend en weekdagindicatoren. Elke kandidaat wordt afzonderlijk aan dezelfde basis toegevoegd. Alle modellen gebruiken dezelfde complete trainingsrijen, zodat de vergelijking gepaard is.

Per voorspelling en termijn worden de laatste 45 volledige trainingsrijen van dezelfde scoremethode gebruikt. Beide richtingen moeten in de training aanwezig zijn. De eindkoersen van trainingsuitkomsten moeten vóór de testpublicatie gepubliceerd zijn. Alle standaardisatie wordt alleen op trainingsdata geschat.

Het model is logistische regressie met L2, C=0,1, lbfgs, maximaal 2000 iteraties en tolerantie 1e-10. De kansdrempel voor richting is 0,5. Een ongewijzigde koers telt niet als stijging. De registerrij bewaart inputs, trainings-IDs, parameters, standaardisatie, sklearn-versie en bronhashes. Verandering van kenmerken, model, horizon of drempel vereist een nieuw protocol-ID.

De oude onderzoeksanalyse gebruikte deels andere modelvarianten en een andere teststart. De historische cijfers van dit vaste protocol zijn daarom niet identiek aan alle eerdere analyses. Ze gelden bovendien uitsluitend als verkenning.

## Interpretatie van de resultaten

* Brier/kansfout: gemiddeld kwadraat van modelkans minus daadwerkelijke stijging; lager is beter.
* Verbetering: kansfout van de basis minus die van de uitbreiding; positief betekent lagere fout voor de uitbreiding op dezelfde dagen.
* 95%-interval: gepaarde moving-block bootstrap, bloklengte max(7,termijn), 2000 trekkingen en seed 20261109. Alleen bij ten minste 20 modeluitkomsten en drie niet-overlappende vensters. Dit is een interval per kandidaat, geen gezamenlijke bevestiging van alle onderzochte varianten.
* Herkenning per richting: correct voorspelde stijgingen gedeeld door alle werkelijke stijgingen, en overeenkomstig voor dalingen. Beide noemers blijven zichtbaar.
* Kalibratie: per kansgroep gemiddelde voorspelde kans naast het werkelijk gestegen aandeel en de groepsomvang.
* Dalingsregels: alle actieve dagen met complete uitkomst, tegenover de overige geldige dagen. Deze populatie kan groter zijn dan de modelpopulatie, die eerst voldoende training vereist.
* Niet-overlappende vensters worden afzonderlijk geteld. Die zijn niet automatisch statistisch onafhankelijk en een vast aantal events garandeert geen bewijs.

De vergelijkingen met 50/50, altijd stijging en altijd daling staan op dezelfde modeldagen. Het dashboard kent geen automatisch label 'bewezen' toe op basis van alleen een gunstig historisch percentage of interval.

## Kalendergebalanceerde alternatieve onderbouwing

De bestaande onderbouwing gebruikt een historische backtest die iedere zevende rij bemonstert. De alternatieve methode evalueert iedere dag in 26 volledige maandag-zondagweken met bekende 7-daagse uitkomsten: 26 testmomenten per weekdag, 182 totaal. Een nieuwe week wordt pas opgenomen wanneer de hele week voldoende is uitontwikkeld. De kansbasis gebruikt uitsluitend eerdere testuitkomsten; de eerste kans is 0,5.

De andere onderdelen van de onderbouwingsscore en de bestaande caps blijven van toepassing. De oorspronkelijke blauwe score wordt niet vervangen. Kalenderbalans verwijdert de wisselende weekdagselectie, maar maakt overlappende weekuitkomsten niet onafhankelijk en bewijst geen voorspelkracht. Er wordt geen alternatieve historie gereconstrueerd wanneer de oorspronkelijke historische invoer niet beschikbaar is.

## Archief en bewaring

`data/research/baseline/collected-data.tar.gz` bevat alle oorspronkelijke bestanden uit `data/curated`, `data/ledger` en `site/data` op het moment van invoering. Het bijbehorende manifest bewaart iedere bestandsnaam, byteomvang en SHA-256. De initiële archiefkopie omvat 157 bestanden. Ze bevat ook dubbele runs en eerdere ongunstige uitkomsten.

Iedere controle valideert de bytes in het archief, de oorspronkelijke ledgerprefixen en alle oorspronkelijke cellen van de onderzoeks-Parquet. Het archief vervangt de werkende datasets niet. Herstel gebeurt eerst naar een afzonderlijke map; een beschadigde bron wordt nooit stilzwijgend door een nieuwe lege dataset vervangen.

| Bestand | Betekenis |
|---|---|
| `data/research/definitions.jsonl` | Vastgelegde onderzoeksprotocollen. |
| `data/research/forecasts.jsonl` | Onveranderlijke voorspellingen met trainings- en modelbewijs. |
| `data/research/outcomes.jsonl` | Eenmalig vastgelegde uitkomsten met gebruikte eindpuntkoersen. |
| `data/research/parallel_predictions.jsonl` | Oorspronkelijke bronversies uit parallelle research/live-runs met dezelfde prediction-ID. Bronhash en publicatietijd onderscheiden ze. |
| `data/research/inputs/*.json.gz` | Exacte verwerkte invoer en implementatie per nieuwe productierun, geadresseerd op inhoud. |
| `data/research/runs.jsonl` | Runregister met verwijzing naar het invoerarchief. |
| `data/research/shadow_definitions.jsonl` | Definitie van de alternatieve onderbouwing. |
| `data/research/shadow_quality.jsonl` | Alternatieve score met oorspronkelijke score en backtestdetails per run. |
| `site/data/research_monitor.json` | Afgeleide gegevens voor de gebruikersinterface. |
| `site/data/research_*.jsonl` | Byte-identieke downloadkopieën van onderzoeksledgers. |

Oude protocollen en registraties blijven behouden wanneer een volgende versie wordt toegevoegd. Er is geen automatische verwijder- of uitdunregel. Gecomprimeerde invoerarchieven groeien met nieuwe runs; opslagomvang moet periodiek worden beoordeeld zonder de originele data te verwijderen.

Bij het combineren van parallelle dagelijkse updates blijft de live prediction-ledger byte-identiek behouden en worden de Parquet-runs verenigd op hun unieke runtijd. Een eerdere research-publicatie met dezelfde prediction-ID wordt afzonderlijk ongewijzigd bewaard. De researchmonitor blijft zijn eerste vastgelegde bron gebruiken; iedere voorspelling verwijst naar zowel bron-ID als bronhash. Zo veranderen eerder geregistreerde modelinputs niet door een latere live-publicatie. Beide oorspronkelijke datasets zijn ook als gecontroleerde snapshots bewaard: de live-versie in `source_snapshots/` en de research-versie in `parallel_snapshot/`.

In invoerarchiefschema 1.1 staat de verwerkte historie als base64-gecodeerde Parquet onder `history.bytes_base64`, met eigen hash. Dit behoudt de volledige getalprecisie, ontbrekende waarden en datatypes. `research_parquet_base64` bewaart ook de volledige oorspronkelijke onderzoeks-Parquet van die run. Het eerste installatiecontrolearchief met schema 1.0 blijft behouden; dat bevat de historie als JSON-weergave.

## Opnieuw genereren en controleren

```sh
python -m sol_reality_check research
python -m sol_reality_check ledger-check
python -m sol_reality_check validate
python scripts/build_site.py
```

`research` haalt geen nieuwe marktdata op. Het voegt ontbrekende reconstructies/uitkomsten toe, bewaart bestaande registers en genereert de weergave opnieuw. Voor volledige nieuwe invoer en de alternatieve score draait de normale productie-update. Tests van demo-output worden in een afzonderlijke kopie uitgevoerd wanneer de productiepreview behouden moet blijven.
