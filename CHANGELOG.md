# Changelog

## 2026-11-09

* Voorspelmonitor uitgebreid met drie vaste onderzoekskandidaten voor stijging en daling, een koersbasis, kansfout, herkenning per richting, kalibratie en aparte historische/nieuwe toetsen.
* Onveranderlijk basisarchief met 157 oorspronkelijke bestanden en automatische controle op behoud van alle oorspronkelijke ledgerregels en Parquet-cellen.
* Iedere nieuwe productierun archiveert zijn verwerkte invoer, scores, bronstatus, instellingen en Python-implementatie.
* Afzonderlijke append-only registraties voor definities, voorspellingen en uitkomsten; instap ná publicatie en training uitsluitend met al gepubliceerde uitkomsten.
* Alternatieve blauwe onderbouwing op 26 volledige weken met gelijke vertegenwoordiging van alle weekdagen. De oorspronkelijke scores en groene-clustertoets blijven bewaard.

## 2026-10-26

* Voorspelmonitor toegevoegd voor de vooraf vastgelegde piekdichtheidshypothese.
* Append-only, gehashte ledgers toegevoegd voor signaaldefinities, events en uitkomsten.
* Statusladder, primaire metrics, horizonprofiel, eventstudie, stabiliteitsweergave en downloadbaar eventregister toegevoegd.
* Productiepipeline, validatie, Pages-artifact en tests uitgebreid zonder bestaande historische databestanden te herschrijven.

## 1.0.0

- Eerste volledige SOL Reality Check-implementatie.
