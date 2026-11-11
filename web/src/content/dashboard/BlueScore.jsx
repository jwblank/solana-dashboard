import React, {useEffect, useRef, useState} from 'react';
import {DataComponent, Dropdown} from '../../data-app-public.jsx';
import {date, number, blueScoreChange as explainChange} from './model.js';
import './blue-score.css';

const COLORS=['#527ac4','#4b9a9a','#ad8b58','#8373ad','#7d9e68'];
const valueText = row => row.value==null?'Niet beschikbaar':`${number(row.value*(row.unit==='×'?1:100),1)} ${row.unit}`;

export function BlueScore({rows,features,definitions,history,selectedDate,onSelect,timeDomain}){
  const days=new Set(history.map(r=>r.date));
  const scoped=rows.filter(r=>days.has(r.date));
  const selected=scoped.find(r=>r.date===selectedDate)||scoped.at(-1);
  if(!selected) return null;
  const previous=scoped[scoped.indexOf(selected)-1];
  const scopeFeatures=features.filter(r=>days.has(r.date));
  const selectedFeatures=scopeFeatures.filter(r=>r.date===selected.date);
  const complete=scoped.filter(r=>r.complete).length;
  const why=explainChange(selected,previous,definitions);
  return <section id="blue-score-explainer" className="blue-section">
    <DataComponent id="sol-blue-composition" queryId="blue_breakdown" queryIds={['blue_breakdown','blue_components']}
      sourceRowsByQuery={{blue_breakdown:scoped,blue_components:definitions}} displayRows={[selected]}
      title="Van marktgegevens naar blauwe score" kind="custom" variant="card"
      description="De elf marktvariabelen selecteren historische analogieën. De vijf onderdelen hieronder beoordelen de onderbouwing. De oorspronkelijke score en begrenzingen blijven ongewijzigd.">
      <div className="blue-header"><div className="blue-process"><span>01 · Marktgegevens</span><i>→</i><span>02 · Historische vergelijking</span><i>→</i><b>03 · Onderbouwing</b></div>
        <Dropdown label="Inspectiedag" showLabel value={selected.date} choices={scoped.map(r=>r.date).reverse()} choiceLabels={Object.fromEntries(scoped.map(r=>[r.date,date(r.date)]))} onChange={onSelect}/></div>
      <p className="lab-fine">Datadag {date(selected.date)} · eerste publicatie {date(selected.published_at,true)}. Klik in de koersgrafiek of de blauwe lijn om een dag te inspecteren. Blauwe blokken: score boven 65.</p>
      <div className="blue-components" data-reviewed-rows>{definitions.map((c,i)=><div key={c.key} className="blue-component" style={{'--component-color':COLORS[i]}}>
        <div><span className="blue-dot"/>{c.label}<small>{number(c.weight*100,0)}%</small></div>
        <strong>{selected[c.key+'_points']==null?'—':number(selected[c.key+'_points'],2)} <small>punten</small></strong>
        <div className="blue-meter"><span style={{width:`${selected[c.key]==null?0:selected[c.key]}%`}}/></div>
        <span className="blue-component-value">Invoer {number(selected[c.key],2)} / 100{c.key==='stability'?' · vaste invoer':''}</span>
        {c.key==='sample_adequacy' && <span className="blue-component-value">{number(selected.analog_count,0)} historische situaties</span>}
        <span className="blue-provenance">{selected[c.key+'_provenance']}</span>
        <details><summary>Definitie</summary><p>{c.definition}</p></details>
      </div>)}</div>
      <div className="blue-contribution-strip" data-reviewed-rows aria-label="Gewogen bijdragen op een schaal van 0 tot 100">{definitions.map((c,i)=>selected[c.key+'_points']!=null && <span key={c.key} style={{width:`${selected[c.key+'_points']}%`,background:COLORS[i]}} title={`${c.label}: ${number(selected[c.key+'_points'],2)} punten`}/>)}{selected.ceiling!=null && <i style={{left:`${selected.ceiling}%`}} title={`Bovengrens ${selected.ceiling}`}/>}</div>
      {!selected.complete && <p className="lab-fine">De strook toont uitsluitend bekende deelbijdragen. Het lege deel is geen berekende bijdrage.</p>}
      <div className="blue-formula" data-reviewed-rows>
        <div><small>Gewogen som</small><b>{number(selected.raw_score,2)}</b></div><i>→</i>
        <div><small>Geregistreerde bovengrens</small><b>{selected.ceiling==null?'Geen':selected.ceiling}</b></div><i>→</i>
        <div className="blue-final"><small>Blauwe score</small><b>{number(selected.score,2)} <small>/ 100</small></b></div>
        <span>{selected.complete?'Volledige oorspronkelijke opbouw':`Opbouw gedeeltelijk beschikbaar · ${definitions.filter(c=>selected[c.key]!=null).length}/5 onderdelen`}</span>
      </div>
      <p className="blue-why"><b>Waarom veranderde de lijn?</b> {why}</p>
      {selected.reasons.length>0 && <details className="blue-reasons"><summary>Begrenzingen en context · {selected.reasons.length}</summary><ul>{selected.reasons.map(r=><li key={r}>{r}</li>)}</ul><p className="lab-fine">Contextmeldingen over RPC en ecosysteembreedte vormen op zichzelf geen numerieke bovengrens.</p></details>}
      <details className="blue-history" open><summary>Blauwe lijn en gewogen bijdragen door de tijd <span>{complete}/{scoped.length} dagen volledig opgeslagen</span></summary>
        <CompositionChart rows={scoped} definitions={definitions} selected={selected} onSelect={onSelect} timeDomain={timeDomain}/>
        <div className="blue-legend">{definitions.map((c,i)=><span key={c.key}><i style={{background:COLORS[i]}}/>{c.label}</span>)}<span><i className="blue-line-key"/>Eindscore</span><span>◆ Bovengrens geregistreerd</span></div>
        <p className="lab-fine">Het gestapelde vlak verschijnt alleen bij volledig opgeslagen opbouw; ontbrekende dagen blijven leeg. De lijn bevat alle oorspronkelijke scores. Deelbijdragen uit oude analogieën zijn als reconstructie gemarkeerd. Niet-opgeslagen stabiliteit wordt niet met 70 opgevuld.</p>
      </details>
    </DataComponent>
    <details className="blue-market"><summary>Welke Solana-situatie vergelijken we? <span>11 marktvariabelen · {date(selected.date)}</span></summary>
      <DataComponent id="sol-market-fingerprint" queryId="market_features" kind="custom" title="Oorspronkelijke marktmetingen" sourceRows={scopeFeatures} displayRows={selectedFeatures} variant="plain">
        <p className="lab-fine">Maximaal 40 vergelijkbare historische dagen, minimaal 7 datadagen uit elkaar. Kenmerken worden vergeleken op hun eigen historische schaal. Gewichten hieronder zijn de relatieve gewichten bij volledige invoer; bij ontbrekende kenmerken wordt herwogen. Minimaal 80% van het totale kenmerkgewicht moet beschikbaar zijn.</p>
        <div className="blue-market-grid">{['Koers & marktpositie','Netwerkactiviteit','Kapitaal & liquiditeit'].map(group=><div className="blue-market-group" key={group}>
          <h3>{group}</h3>{selectedFeatures.filter(r=>r.group===group).map(r=><div className="blue-feature" key={r.feature} data-reviewed-rows>
            <div><span>{r.label}</span><b>{valueText(r)}</b></div>
            <div className="blue-feature-sub"><Sparkline rows={scopeFeatures.filter(x=>x.feature===r.feature&&x.date<=selected.date).slice(-30)}/><span>{number(r.normalized_weight*100,1)}% gewicht</span></div>
            <details><summary>Definitie & bron</summary><p>{r.definition}</p><p>{r.provenance}{r.source_run_at?` · run ${date(r.source_run_at,true)}`:''}</p></details>
          </div>)}
        </div>)}</div>
        <p className="lab-fine">Minigrafieken tonen maximaal 30 opgeslagen datadagen tot de inspectiedag, elk op een eigen schaal. Gaten blijven zichtbaar. DEX en fees: circa 7× betekent gelijkblijvende activiteit. TVL omvat prijseffecten; stablecoins meten beschikbare liquiditeit.</p>
      </DataComponent>
    </details>
  </section>;
}

function Sparkline({rows}){
  const valid=rows.filter(r=>r.value!=null);
  if(valid.length<2) return <span className="blue-spark-empty">Te weinig historie</span>;
  const min=Math.min(...valid.map(r=>r.value)),max=Math.max(...valid.map(r=>r.value));
  const start=Date.parse(rows[0].date),end=Date.parse(rows.at(-1).date);
  let pen=false;
  const d=rows.map(r=>{if(r.value==null){pen=false;return '';}const a=pen?'L':'M';pen=true;return `${a}${(Date.parse(r.date)-start)/(end-start||1)*100},${25-(r.value-min)/(max-min||1)*22}`;}).join(' ');
  return <svg className="blue-spark" viewBox="0 0 100 28" role="img" aria-label="Historie tot de geselecteerde dag"><path d={d} fill="none" stroke="currentColor" strokeWidth="1.8"/></svg>;
}

function CompositionChart({rows,definitions,selected,onSelect,timeDomain}){
  const ref=useRef(null);const [width,setWidth]=useState(900);
  useEffect(()=>{const observer=new ResizeObserver(([e])=>setWidth(Math.max(240,e.contentRect.width)));if(ref.current)observer.observe(ref.current);return()=>observer.disconnect();},[]);
  const left=30,right=12,start=timeDomain?.[0]??rows[0].published_time,end=timeDomain?.[1]??rows.at(-1).published_time;
  const x=t=>left+(t-start)/(end-start||1)*(width-left-right),y=v=>162-v*1.4;
  const line=(key)=>{let pen=false;return rows.map(r=>{if(r[key]==null){pen=false;return '';}const c=pen?'L':'M';pen=true;return `${c}${x(r.published_time)},${y(r[key])}`;}).join(' ');};
  const segments=[];let current=[];
  rows.forEach((r,i)=>{if(r.complete){if(i&&Date.parse(r.date)-Date.parse(rows[i-1].date)>86400000){if(current.length)segments.push(current);current=[];}current.push(r);}else if(current.length){segments.push(current);current=[];}});if(current.length)segments.push(current);
  const choose=e=>{const rect=e.currentTarget.getBoundingClientRect();const t=start+Math.max(0,Math.min(1,(e.clientX-rect.left-left)/(width-left-right)))*(end-start);onSelect(rows.reduce((a,b)=>Math.abs(b.published_time-t)<Math.abs(a.published_time-t)?b:a).date);};
  return <div ref={ref} className="blue-composition-chart" data-reviewed-rows>
    <svg width="100%" height="195" viewBox={`0 0 ${width} 195`} onClick={choose} role="img" aria-label="Blauwe eindscore en volledig opgeslagen gewogen bijdragen, op publicatietijd">
      {[0,50,100].map(v=><g key={v}><line x1={left} x2={width-right} y1={y(v)} y2={y(v)} className="lab-grid-line"/><text x={left-7} y={y(v)+4} textAnchor="end" className="lab-axis">{v}</text></g>)}
      {segments.flatMap((segment,si)=>definitions.map((c,ci)=>{const low=r=>definitions.slice(0,ci).reduce((s,a)=>s+r[a.key+'_points'],0);const high=r=>low(r)+r[c.key+'_points'];const path=segment.map((r,i)=>`${i?'L':'M'}${x(r.published_time)},${y(high(r))}`).join(' ')+segment.toReversed().map(r=>`L${x(r.published_time)},${y(low(r))}`).join(' ')+'Z';return <path key={`${si}-${c.key}`} d={path} fill={COLORS[ci]} opacity=".72"/>;}))}
      <line x1={left} x2={width-right} y1={y(65)} y2={y(65)} className="lab-threshold"/>
      <path d={line('score')} fill="none" stroke="var(--lab-kpi)" strokeWidth="2.2"/>
      {rows.filter(r=>r.ceiling!=null).map(r=><path key={r.date} d={`M${x(r.published_time)},${y(r.score)-3}l3,3 -3,3 -3,-3Z`} fill="var(--lab-amber)"/>)}
      <line x1={x(selected.published_time)} x2={x(selected.published_time)} y1="15" y2="165" className="lab-cursor"/><circle cx={x(selected.published_time)} cy={y(selected.score)} r="4" fill="var(--lab-kpi)"/>
      {[0,.5,1].map((f,i)=><text key={f} x={x(start+f*(end-start))} y="185" textAnchor={i===0?'start':i===2?'end':'middle'} className="lab-axis">{date(new Date(start+f*(end-start)).toISOString())}</text>)}
    </svg>
  </div>;
}
