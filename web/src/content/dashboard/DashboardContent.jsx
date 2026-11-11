import React,{useMemo,useState} from "react";
import {DataComponent,DataTable,EvidenceChart,Section,SegmentedControl,Dropdown,Switch,
  useDataApp,useDashboardTabs,chartConfigEntries} from "../../data-app-public.jsx";
import {Timeline} from "./Timeline.jsx";
import {date,direction,evaluationRows,featureValue,money,number,percent,sampleMarks,scopeHistory} from "./model.js";
import "./lab.css";

const REPO="https://github.com/jwblank/solana-dashboard";
const phaseOptions=[{value:"prospective",label:"Nieuwe toets"},{value:"reconstructed",label:"Historisch · verkennend"}];
const rangeOptions=[{value:"all",label:"Alle historie"},{value:"90",label:"90 dagen"},{value:"30",label:"30 dagen"}];
const formatCount=(correct,total)=>total ? `${correct} / ${total} · ${percent(correct/total)}` : "Nog geen uitkomsten";

export function DashboardContent() {
  const {snapshot,reviewedRows}=useDataApp();
  const {activeTabId}=useDashboardTabs([
    {id:"onderzoek",label:"Onderzoek"},{id:"methode",label:"Methode & data"},{id:"over",label:"Over het onderzoek"}
  ]);
  const meta=reviewedRows("meta")[0];
  const candidates=reviewedRows("candidates");
  const history=reviewedRows("history",["date"]);
  const forecasts=reviewedRows("forecasts");
  const evaluations=reviewedRows("evaluations");
  const [candidateId,setCandidateId]=useState(candidates[0]?.candidate_id);
  const [phase,setPhase]=useState("prospective");
  const [range,setRange]=useState("all");
  const [showAll,setShowAll]=useState(false);
  const [selectedId,setSelectedId]=useState(null);
  const candidate=candidates.find(c=>c.candidate_id===candidateId)||candidates[0];
  const tab=activeTabId||"onderzoek";
  const visibleHistory=useMemo(()=>scopeHistory(history,range),[history,range]);
  const scopedForecasts=forecasts.filter(r=>r.candidate_id===candidate?.candidate_id && r.phase===phase);
  const visibleForecasts=scopedForecasts.filter(r=>r.mark_time>=(visibleHistory[0]?.close_time||0));
  const marks=sampleMarks(visibleForecasts,showAll);
  const selected=marks.find(r=>r.forecast_id===selectedId)||marks.at(-1)||null;
  const phaseMetrics=evaluationRows(evaluations,phase);
  const chosenMetric=phaseMetrics.find(r=>r.candidate_id===candidate?.candidate_id);
  if(!meta || !candidate) return <article className="lab-page"><p role="status">Geen gecontroleerde onderzoeksgegevens beschikbaar.</p></article>;

  return <article className="page lab-page">
    {tab==="onderzoek" && <>
      <div className="lab-intro">
        <div><p className="lab-question">Voegen Solana-signalen voorspelkracht toe aan koersontwikkeling?</p>
          <div className="lab-meta"><span>Data t/m {date(meta.data_cutoff)}</span><span>{meta.history_days} datadagen · {meta.research_runs} runs bewaard</span><span>7 dagen primair</span></div>
        </div>
        <div className="lab-close"><small>SOL · laatst vastgelegd dagslot</small><strong>{money(meta.last_close)}</strong>
          <span className={meta.price_warning?"lab-warning-label":"lab-quality-label"}>{meta.price_warning?"Herstelbron actief":"Broncontroles beschikbaar"} · details bij Methode & data</span></div>
      </div>
      <div className={`lab-status-band ${phase==='reconstructed'?'historical':''}`}>
        <div><b>{phase==="prospective" ? meta.mature_forward_days ? "Nieuwe toets · bewijs in opbouw" : "Nieuwe toets in opbouw" : "Historische verkenning"}</b>
          <span>{phase==="prospective" ? `${meta.forward_days} meetdagen vastgelegd · ${meta.mature_forward_days} afgerond na 7 dagen. ${meta.mature_forward_days?"Meerwaarde wordt per kandidaat getoetst.":"Nog geen uitspraak over voorspelkracht."}` : "Deze periode hielp de hypotheses vinden. De uitkomsten zijn geen onafhankelijke bevestiging."}</span></div>
        <SegmentedControl label="Onderzoeksperiode" options={phaseOptions} value={phase} onChange={setPhase}/>
      </div>
      <div className="lab-research-grid">
        <DataComponent id="sol-signals-timeline" queryId="history" queryIds={["history","forecasts","candidates"]}
          title="Signalen en koersverloop" kind="custom" variant="card"
          sourceRowsByQuery={{history:visibleHistory,forecasts:visibleForecasts,candidates:[candidate]}}
          displayRows={visibleHistory} className="lab-main-chart"
          description="Echte tijdposities, eigen schalen. De koers staat op het UTC-dagslot; KPI's op publicatie. Nieuwe verwachtingen staan op registratie, historische reconstructies blijven verkennend."
          headerControls={<><Dropdown label="KPI" showLabel value={candidate.candidate_id}
            choices={candidates.map(c=>c.candidate_id)} choiceLabels={Object.fromEntries(candidates.map(c=>[c.candidate_id,c.name]))} onChange={setCandidateId}/>
            <SegmentedControl label="Grafiekperiode" options={rangeOptions} value={range} onChange={setRange} size="compact"/></>}>
          <Timeline history={visibleHistory} candidate={candidate} marks={marks} selected={selected} onSelect={r=>setSelectedId(r.forecast_id)}/>
          <div className="lab-chart-footer"><span>Alle lijnen zijn waarnemingen. Blauwe band: geselecteerd meetvenster.</span>
            <Switch label="Alle markeringen" checked={showAll} onChange={setShowAll} size="compact"/></div>
          <p className="lab-fine">{marks.length} van {visibleForecasts.filter(r=>r.model_available).length} modelmarkeringen getoond{marks.length<visibleForecasts.filter(r=>r.model_available).length?" · vaste selectie zonder overlappende meetvensters":""}. Statistiek gebruikt de hele gekozen toetsperiode.</p>
          <ForecastDetail row={selected} phase={phase}/>
        </DataComponent>
        <EvidencePanel evaluations={phaseMetrics} meta={meta} phase={phase}/>
      </div>
      <DataComponent id="sol-hypotheses" queryId="candidates" kind="custom" title="Drie vastgelegde hypotheses" variant="plain" sourceRows={candidates} displayRows={candidates}>
        <div className="lab-hypotheses">{candidates.map(c=><button type="button" key={c.candidate_id} className="lab-hypothesis" data-selected={c.candidate_id===candidate.candidate_id} onClick={()=>setCandidateId(c.candidate_id)}>
          <span className="lab-family">{c.family}</span><div><b>{c.name}</b><strong>{featureValue(c)}</strong></div><p>{c.hypothesis}</p>
        </button>)}</div>
      </DataComponent>
      <div className="lab-lower-grid">
        <DataComponent id="sol-research-note" queryId="meta" kind="custom" title="Duiding" variant="plain" sourceRows={[meta]} displayRows={[meta]}>
          <p className="lab-note">{phase==="reconstructed" ? "De historische verschillen zijn aanknopingspunten. Ze kunnen mede ontstaan door koersregime, overlap of het weekritme van de berekening. De nieuwe toets bepaalt of ze standhouden." : meta.research_note?.text || "De kandidaten zijn vooraf vastgelegd. De nieuwe meetvensters moeten eerst aflopen voordat extra voorspelkracht kan worden beoordeeld."}</p>
          <p className="lab-fine">{phase==="prospective" && meta.research_note?.status==="llm_success" ? `LLM-redactie · ${meta.research_note.model} · ${date(meta.research_note.generated_at,true)}` : "Feitelijke onderzoeksduiding · berekeningen en bewijsstatus komen uit de vaste rekenlogica."}</p>
        </DataComponent>
        <details className="lab-disclosure"><summary>Gemiddeld koerspad na de geselecteerde regel</summary>
          <EventStudy candidate={candidate} phase={phase} rows={reviewedRows("event_paths")}/></details>
      </div>
      <details className="lab-disclosure"><summary>Voorspellingen en uitkomsten controleren</summary>
        <DataComponent id="sol-forecast-register" queryId="forecasts" kind="table" title="Volledig register · 7 dagen" variant="plain" sourceRows={scopedForecasts} displayRows={scopedForecasts}>
          <p className="lab-fine">{phase==='reconstructed'?"Markeringen en verwachtingen zijn achteraf gereconstrueerd.":"Iedere verwachting is vóór het instapslot geregistreerd."} Modelkansen zijn experimentele uitvoer, geen betrouwbaar vastgestelde koerskansen.</p>
          <DataTable rows={scopedForecasts.toSorted((a,b)=>b.mark_time-a.mark_time)} columns={[
            {key:"date",label:"Datadag"},{key:"mark_at",label:phase==='reconstructed'?"Bronmoment":"Geregistreerd",renderCell:v=>date(v,true)},
            {key:"predicted_direction",label:"Verwachting",renderCell:v=>direction(v)},
            {key:"probability_up",label:"Modelkans stijging",renderCell:v=>percent(v)},
            {key:"baseline_probability_up",label:"Koersbasis",renderCell:v=>percent(v)},
            {key:"sol_return",label:"SOL daarna",renderCell:v=>v==null?"Open":percent(v)},
            {key:"relative_return",label:"SOL minus BTC",renderCell:v=>percent(v)},
          ]} label="Voorspellingen en uitkomsten" rowKey="forecast_id" onRowSelect={r=>{setShowAll(true);setSelectedId(r.forecast_id);}} rowActionLabel={()=>"Toon meetvenster in de koersgrafiek"}/>
        </DataComponent>
      </details>
    </>}
    {tab==="methode" && <MethodPage meta={meta} quality={reviewedRows("source_quality")} checks={reviewedRows("price_checks")} evaluations={evaluations} forecasts={forecasts}/>}
    {tab==="over" && <AboutPage/>}
  </article>;
}

function ForecastDetail({row,phase}) {
  if(!row) return <div className="lab-selected"><b>Geen modelmarkering in dit bereik</b><span>KPI- en koershistorie blijven zichtbaar. Een modelverwachting vereist voldoende toen bekende trainingsdata.</span></div>;
  const baseline=row.baseline_probability_up>=.5?"stijging":"daling";
  return <div className="lab-selected" aria-live="polite">
    <div><span>{phase==='reconstructed'?"Reconstructie bij bronmoment":"Vooraf vastgelegd"} · {date(row.mark_at,true)}</span><b>Verwachting: {direction(row.predicted_direction)} <small>· koersbasis: {baseline}</small></b></div>
    <div><span>Meetvenster: {date(row.entry_date)} → {date(row.exit_date)}</span><b>{row.sol_return==null?`Open · vanaf ${date(row.outcome_after_utc)}`:`SOL ${percent(row.sol_return)} · ${row.correct?'richting juist':'richting onjuist'}`}</b></div>
  </div>;
}

function EvidencePanel({evaluations,meta,phase}) {
  const scored=evaluations.some(r=>r.scored_n>0);
  const body=<>
    {!scored && <div className="lab-evidence-empty"><span className="lab-status-dot"/><b>Meetvensters lopen</b><p>De eerste nieuwe uitkomsten zijn nog niet beschikbaar.</p><dl><dt>Verwachte eerste 7-daagse uitkomst</dt><dd>{date(meta.first_maturity)}</dd></dl></div>}
    {scored && <p className="lab-fine">Van de werkelijke stijgings- en dalingsweken correct herkend:</p>}
    <div className="lab-direction-list">{evaluations.map(row=><div key={row.candidate_id}>
      <b>{row.name}</b><span>Stijging: {formatCount(row.up_correct_n,row.actual_up_n)}</span><span>Daling: {formatCount(row.down_correct_n,row.actual_down_n)}</span>
      <small>{row.scored_n} modeluitkomsten · {row.nonoverlap_n} niet-overlappende vensters</small>
    </div>)}</div>
    <p className="lab-fine">Dagvensters overlappen. Niet-overlap garandeert geen onafhankelijkheid. {phase==='reconstructed'?"Historische intervallen zijn niet voor kandidaatselectie gecorrigeerd.":"Beoordeel meerwaarde met het interval, de aantallen en vervolgmetingen."}</p>
  </>;
  if(!scored) return <DataComponent id="sol-predictive-evidence" queryId="evaluations" kind="custom" title="Voorspelkracht · 7 dagen" variant="card" sourceRows={evaluations} displayRows={evaluations} className="lab-evidence">{body}</DataComponent>;
  const chartRows=evaluations.map(r=>({name:r.name,"Brier-verschil":r["Brier-verschil"],low:r.low,high:r.high}));
  const [chart]=chartConfigEntries({id:"sol-predictive-evidence",title:"Meerwaarde versus koersbasis",rows:chartRows,
    spec:{type:"horizontalBar",x:"Brier-verschil",y:"name",showValues:true,valueDecimals:3,showLegend:false,
      uncertainty:{lower:"low",upper:"high",style:"bars",label:"95%-interval per kandidaat"}}});
  return <EvidenceChart {...chart} queryId="evaluations" sourceRows={evaluations} height={190} className="lab-evidence"
    description="Positief betekent minder kansfout dan dezelfde koersbasis. Bevat het 95%-interval nul, dan is de meerwaarde onzeker.">
    <p className="lab-fine">Brier-verschil: fout van de basis minus fout van de uitbreiding. Positief is gunstiger; lijnen zijn 95%-intervallen.</p>{body}
  </EvidenceChart>;
}

function EventStudy({candidate,phase,rows}) {
  if(candidate.candidate_id==='blue-duration-v1') return <p>Blauwe duur is een continue KPI zonder vaste aan/uit-grens. Hiervoor toetsen we het model tegenover dezelfde koersbasis; er wordt geen dalingssignaal achteraf geconstrueerd.</p>;
  const selected=rows.filter(r=>r.candidate_id===candidate.candidate_id&&r.phase===phase);
  if(!selected.length) return <p>Voor deze periode zijn nog geen volledige meetvensters beschikbaar.</p>;
  const display=selected.map(r=>({...r,"Koerspad (%)":r.mean_pct,"Ondergrens (%)":r.lo_pct,"Bovengrens (%)":r.hi_pct}));
  return <EvidenceChart id="sol-event-path" queryId="event_paths" title="Gemiddeld SOL-verloop na instap" rows={display} sourceRows={selected} height={240} variant="plain"
    spec={{type:"line",x:"day",y:"Koerspad (%)",series:"group",stackable:false,valueDecimals:1,
      uncertainty:{lower:"Ondergrens (%)",upper:"Bovengrens (%)",style:"band",label:"95% block-bootstrapband"}}}>
    <p className="lab-fine">{[...new Map(selected.map(r=>[r.group,r.n])).entries()].map(([g,n])=>`${g}: n=${n}`).join(" · ")}. Beschrijvend, zonder matching op marktregime. Dagvensters overlappen.</p>
  </EvidenceChart>;
}

function MethodPage({meta,quality,checks,evaluations,forecasts}) {
  const [phase,setPhase]=useState("prospective");
  const [horizon,setHorizon]=useState(7);
  const selected=evaluations.filter(r=>r.phase===phase&&r.horizon_days===Number(horizon));
  const calibration=selected.flatMap(r=>r.calibration.map(b=>({candidate:r.name,n:b.n,"Voorspeld (%)":b.predicted==null?null:b.predicted*100,"Werkelijk (%)":b.observed==null?null:b.observed*100}))).filter(r=>r.n);
  return <>
    <Section id="lab-method-header" title="Methode & data" spacing="none">
      <div className="lab-method-intro"><p>Elke uitkomst is terug te voeren op een vooraf vastgelegde definitie, bronversie en meetvenster. De bestaande koersverzameling, broncontroles en statistische logica blijven leidend.</p>
        <a href={`${REPO}/blob/main/docs/RESEARCH_MONITOR.md`} target="_blank" rel="noreferrer">Volledig protocol ↗</a></div>
    </Section>
    <div className="lab-method-grid">
      <DataComponent id="lab-protocol" queryId="meta" kind="custom" title="Vaste onderzoeksopzet" sourceRows={[meta]} displayRows={[meta]} variant="card">
        <dl className="lab-definition"><dt>Protocol</dt><dd>{meta.protocol.protocol_id} · vastgelegd {date(meta.protocol.locked_at_utc)}</dd><dt>Primaire toets</dt><dd>7 dagen. Andere termijnen zijn aanvullende analyses.</dd><dt>Instap</dt><dd>{meta.protocol.entry_policy}</dd><dt>Koersbasis</dt><dd>SOL- en BTC-momentum over 7 dagen, tijdtrend en weekdag. De uitbreiding voegt precies één KPI toe op dezelfde trainingsrijen.</dd><dt>Training</dt><dd>Laatste 45 complete rijen. Alleen toen al gepubliceerde uitkomsten; standaardisatie uitsluitend op training.</dd><dt>Onzekerheid</dt><dd>Gepaarde moving-block bootstrap. Een interval per kandidaat is geen gezamenlijke bevestiging van alle verkende varianten.</dd></dl>
      </DataComponent>
      <DataComponent id="lab-price-sources" queryId="source_quality" queryIds={["source_quality","price_checks"]} kind="custom" title="Koersbronnen en herstelpad" variant="card" sourceRowsByQuery={{source_quality:quality,price_checks:checks}} displayRows={quality}>
        <p className={meta.price_warning?"lab-price-warning":""}>{meta.price_warning?"De laatste run gebruikte een herstelbron. Dat blijft zichtbaar; een opgevraagde bron telt niet automatisch als gebruikte koersbron.":"De broncontroles van de laatste productierun zijn beschikbaar."}</p>
        <DataTable rows={quality} columns={[{key:"name",label:"Bron"},{key:"role",label:"Rol"},{key:"status",label:"Status"}]} searchable={false} label="Bronstatus"/>
        <details className="lab-disclosure"><summary>Exacte exchange-controle bekijken</summary>
          <p className="lab-fine">Dit is de broncontrole van de laatste run. De controledatum kan verschillen van de datadag in de koersgrafiek; symbolen en werkelijk gebruikte bronnen staan expliciet vermeld.</p>
          <DataTable rows={checks} columns={[{key:"asset",label:"Asset"},{key:"exchange",label:"Exchange"},{key:"symbol",label:"Symbool"},{key:"date",label:"Controledag"},{key:"close",label:"Bronkoers",renderCell:v=>money(v)},{key:"used",label:"Gebruikt",renderCell:v=>v?"Ja":"Nee"},{key:"status",label:"Toelichting"}]} label="Exchangeprijzen"/>
        </details>
        <p className="lab-fine">Livecheck bij update: {money(meta.live_check)} · {date(meta.generated_at,true)}. Dit is geen actuele intraday-reeks in de grafiek.</p>
      </DataComponent>
    </div>
    <Section id="lab-calibration-header" title="Kalibratie en robuustheid" spacing="section" filters={<><SegmentedControl label="Periode kalibratie" options={phaseOptions} value={phase} onChange={setPhase}/><Dropdown label="Termijn" value={String(horizon)} choices={["1","3","7","14"]} choiceLabels={{1:"1 dag",3:"3 dagen",7:"7 dagen · primair",14:"14 dagen"}} onChange={setHorizon}/></>}>
      <DataComponent id="lab-calibration" queryId="evaluations" kind="table" title="Komen modelkansen uit?" sourceRows={selected} displayRows={calibration}>
        <p className="lab-fine">Per kansgroep: gemiddelde voorspelling naast het werkelijk gestegen aandeel. Kleine groepen geven weinig zekerheid. De primaire toets blijft zeven dagen.</p>
        {calibration.length?<DataTable rows={calibration} columns={[{key:"candidate",label:"Kandidaat"},{key:"Voorspeld (%)",label:"Voorspeld",renderCell:v=>`${number(v,1)}%`},{key:"Werkelijk (%)",label:"Werkelijk",renderCell:v=>`${number(v,1)}%`},{key:"n",label:"Aantal"}]} label="Kalibratie"/>:<p className="lab-empty">Nog geen afgeronde modeluitkomsten in deze selectie.</p>}
        <p className="lab-fine">Naast de koersbasis vergelijken we met 50/50, altijd stijging en altijd daling. Herkenning van beide richtingen en marktregimes blijft nodig; een hoog totaalpercentage alleen is onvoldoende.</p>
        <details className="lab-disclosure"><summary>Exacte kansfouten en aantallen vergelijken</summary>
          <p className="lab-fine">Brier-fout: lager is gunstiger. Alle vergelijkingen binnen een rij gebruiken dezelfde meetdagen. Zonder modeluitvoer telt een volwassen koersvenster niet mee voor modelbewijs.</p>
          <DataTable rows={selected} columns={[
            {key:"name",label:"Kandidaat"},{key:"brier",label:"Model",renderCell:v=>number(v)},
            {key:"baseline_brier",label:"Koersbasis",renderCell:v=>number(v)},
            {key:"coinflip_brier",label:"50/50",renderCell:v=>number(v)},
            {key:"always_up_brier",label:"Altijd stijging",renderCell:v=>number(v)},
            {key:"always_down_brier",label:"Altijd daling",renderCell:v=>number(v)},
            {key:"scored_n",label:"Modeluitkomsten"},{key:"unscored_matured_n",label:"Zonder modeluitvoer"},
          ]} label="Gelijke-dagenvergelijking"/>
        </details>
      </DataComponent>
    </Section>
    <div className="lab-method-grid lab-method-lower">
      <DataComponent id="lab-calendar-check" queryId="meta" kind="custom" title="Wat leerde het blauwe weekritme?" variant="card" sourceRows={[meta]} displayRows={[meta]}>
        <p>Een visueel piekpatroon leidde tot een hypothese. Controle liet ook een weekdageffect in de scoreberekening zien. Daarom loopt een kalendergebalanceerde variant naast de oorspronkelijke score.</p>
        {meta.shadow_quality?.[0] && <p><b>Laatste vergelijking:</b> oorspronkelijk {number(meta.shadow_quality[0].original_quality,1)} / 100 · alternatief {number(meta.shadow_quality[0].alternative_quality,1)} / 100.</p>}
        <p className="lab-fine">De alternatieve backtest bevat 26 volledige weken met iedere weekdag even vaak. De dagelijkse weekuitkomsten overlappen nog steeds. Een onderbouwingsscore is geen koerskans.</p>
      </DataComponent>
      <DataComponent id="lab-data-retention" queryId="meta" kind="custom" title="Historie en reproduceerbaarheid" variant="card" sourceRows={[meta]} displayRows={[meta]}>
        <p><b>{meta.research_runs} oorspronkelijke runs</b> blijven bewaard, naast bronversies, voorspellingen en ongunstige uitkomsten. De huidige interface leest die gegevens; ze begint geen nieuwe historie.</p>
        <p className="lab-fine">Definitiewijzigingen vereisen een nieuwe versie. Dagelijkse publicaties en parallelle bronversies blijven identificeerbaar op tijdstip en controlehash.</p>
        <div className="lab-links"><a href="./data/signaalonderzoek.parquet" download>Volledige onderzoeksdata ↓</a><a href="./data/research_forecasts.jsonl" download>Voorspellingen en modelbewijs ↓</a><a href="./data/research_outcomes.jsonl" download>Uitkomsten ↓</a><a href="./data/research_baseline.tar.gz" download>Oorspronkelijk archief ↓</a><a href={`${REPO}/tree/main/data/research`} target="_blank" rel="noreferrer">Alle bronversies ↗</a><a href="./legacy.html#voorspelmonitor">Eerdere dashboardweergave ↗</a></div>
      </DataComponent>
    </div>
    <details className="lab-disclosure"><summary>Bestaande groene-piekclustertoets</summary>
      <p>{meta.legacy_status.retrospective_mature_event_n} historische events · {meta.legacy_status.prospective_mature_event_n} nieuwe afgeronde events. Deze eerdere toets behoudt haar eigen definitie en historie.</p>
      <p className="lab-fine">De eerdere toets gebruikt een ander rendementsanker. De resultaten worden daarom niet samengevoegd met de nieuwe, na publicatie vastgelegde meetvensters.</p>
      <a href="./legacy.html#voorspelmonitor">Volledige eerdere monitor openen ↗</a>
    </details>
    <details className="lab-disclosure"><summary>LLM-marktduiding en gebruikte feiten</summary>
      <p className="lab-fine">{meta.llm.provider} · {meta.llm.model} · {meta.llm.status} · {date(meta.llm.generated_at_utc,true)}. Dit is marktcontext en geen bewijs van voorspelkracht.</p>
      <p className="lab-long-text">{meta.llm.analysis_text}</p>
    </details>
  </>;
}

function AboutPage() {
  return <div className="lab-about">
    <p className="lab-question">Van zichtbaar patroon naar toetsbare hypothese.</p>
    <p>SOL Reality Check onderzoekt of netwerk-, markt- en modelgegevens informatie bevatten over toekomstige SOL-rendementen. De kern is de extra informatie boven een eenvoudige koersbasis, met zichtbare onzekerheid en reproduceerbare registraties.</p>
    <div className="lab-about-grid"><section><h2>Statistiek als ruggengraat</h2><p>Vooraf vastgelegde definities, training met uitsluitend bekende uitkomsten, kalibratie en controle van overlap. Historische verkenning en nieuwe bevestiging blijven herkenbaar gescheiden.</p></section><section><h2>Solana als onderzoeksvraag</h2><p>Netwerkgebruik, DEX-volume, fees en stablecoins beschrijven verschillende aspecten van het ecosysteem. De vraag is welke daarvan werkelijk extra informatie over SOL bevatten, en welke vooral de brede cryptomarkt of een bestaande trend volgen.</p></section><section><h2>Een zichtbaar leerproces</h2><p>Ook missers, bronproblemen en verzwakte hypotheses blijven staan. Het gevonden weekritme in de onderbouwing leidde tot een aanvullende controle. Nieuwe ideeën krijgen eerst een definitie en vervolgens hun eigen toetsperiode.</p></section></div>
    <p className="lab-fine">Tekst kan worden ondersteund door een LLM. Cijfers, modeluitkomsten en bewijsstatus worden door de onderzoekslogica bepaald. Indicatieve dagslotrendementen bevatten geen handelskosten, slippage of uitvoeringsgarantie.</p>
    <div className="lab-links"><a href={REPO} target="_blank" rel="noreferrer">Open broncode ↗</a><a href={`${REPO}/blob/main/docs/RESEARCH_MONITOR.md`} target="_blank" rel="noreferrer">Onderzoeksprotocol ↗</a><a href={`${REPO}/blob/main/docs/LAB_DASHBOARD.md`} target="_blank" rel="noreferrer">Dataverwerking en grafiekdefinities ↗</a></div>
  </div>;
}
