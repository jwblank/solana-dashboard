import React,{useEffect,useRef,useState} from "react";
import {date,money,number,direction} from "./model.js";

// A coupled price/KPI chart needs two independent y-scales, true event timestamps,
// a shared cursor and forecast registration marks. No artificial OHLC bars,
// interpolated market quotes or backwards-shifted signals are constructed.
export function Timeline({history,candidate,marks,selected,onSelect}) {
  const ref=useRef(null);
  const [width,setWidth]=useState(800);
  const [active,setActive]=useState(null);
  useEffect(()=>{
    const observer=new ResizeObserver(([entry])=>setWidth(Math.max(260,entry.contentRect.width)));
    if(ref.current) observer.observe(ref.current);
    return ()=>observer.disconnect();
  },[]);
  if(!history.length) return <p className="lab-empty">Geen koerswaarnemingen in deze periode.</p>;
  const height=368,left=52,right=14,plotWidth=width-left-right;
  const start=history[0].close_time;
  const end=Math.max(history.at(-1).published_time,history.at(-1).close_time,selected?.exit_time||0);
  const x=t=>left+(t-start)/Math.max(1,end-start)*plotWidth;
  const quotes=history.filter(row=>row.sol_close!=null);
  const values=quotes.map(row=>row.sol_close);
  const low=Math.floor(Math.min(...values)*.97/5)*5;
  const high=Math.ceil(Math.max(...values)*1.03/5)*5;
  const priceY=v=>66+(high-v)/Math.max(1,high-low)*150;
  const kpi=history.filter(row=>row[candidate.field]!=null);
  const extent=Math.max(1,...kpi.map(row=>Math.abs(row[candidate.field])));
  const kLow=candidate.unit==="blokken" ? -extent-1 : 0;
  const kHigh=candidate.unit==="blokken" ? extent+1 : 100;
  const kY=v=>253+(kHigh-v)/(kHigh-kLow)*70;
  const path=(rows,xField,yField,scale)=>{
    let pen=false;
    return rows.map(row=>{
      if(row[yField]==null) {pen=false;return "";}
      const prefix=pen?"L":"M";pen=true;
      return `${prefix}${x(row[xField]).toFixed(2)},${scale(row[yField]).toFixed(2)}`;
    }).join(" ");
  };
  const selectedStart=selected ? Math.max(start,selected.entry_time) : null;
  const selectedEnd=selected ? Math.min(end,selected.exit_time) : null;
  const tickCount=width<500?3:5;
  const ticks=Array.from({length:tickCount},(_,i)=>start+(end-start)*i/(tickCount-1));
  const nearest=(t,field)=>history.reduce((a,b)=>Math.abs(b[field]-t)<Math.abs(a[field]-t)?b:a,history[0]);
  function hover(event) {
    const bounds=event.currentTarget.getBoundingClientRect();
    const t=start+Math.max(0,Math.min(1,(event.clientX-bounds.left-left)/plotWidth))*(end-start);
    setActive({t,quote:nearest(t,"close_time"),kpi:nearest(t,"published_time")});
  }
  return <div ref={ref} className="lab-timeline" data-chart-interaction-root data-reviewed-rows>
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} role="img"
      aria-label={`SOL-dagslot en ${candidate.name}, op dezelfde tijdas met eigen schalen`}
      onPointerMove={hover} onPointerLeave={()=>setActive(null)}>
      {selectedStart!=null && selectedEnd>selectedStart && <rect x={x(selectedStart)} y="53" width={Math.max(1,x(selectedEnd)-x(selectedStart))} height="278" fill="var(--lab-window)"/>}
      {[0,1,2,3].map(i=>{
        const v=low+(high-low)*i/3;
        return <g key={i}><line x1={left} x2={width-right} y1={priceY(v)} y2={priceY(v)} className="lab-grid-line"/><text x={left-9} y={priceY(v)+4} textAnchor="end" className="lab-axis">{number(v,0)}</text></g>;
      })}
      <text x={left} y="56" className="lab-plot-title">SOL · USD-dagslot</text>
      <path d={path(history,"close_time","sol_close",priceY)} fill="none" stroke="var(--lab-price)" strokeWidth="2.4"/>
      {quotes.length>0 && <circle cx={x(quotes.at(-1).close_time)} cy={priceY(quotes.at(-1).sol_close)} r="3.5" fill="var(--lab-price)"/>}
      <line x1={left} x2={width-right} y1="238" y2="238" className="lab-grid-line"/>
      <text x={left} y="251" className="lab-plot-title">{candidate.name} · {candidate.unit}</text>
      {[kLow,(kLow+kHigh)/2,kHigh].map(v=><g key={v}><line x1={left} x2={width-right} y1={kY(v)} y2={kY(v)} className="lab-grid-line"/><text x={left-9} y={kY(v)+4} textAnchor="end" className="lab-axis">{number(v,0)}</text></g>)}
      {candidate.threshold!=null && <line x1={left} x2={width-right} y1={kY(candidate.threshold)} y2={kY(candidate.threshold)} className="lab-threshold"/>}
      <path d={path(history,"published_time",candidate.field,kY)} fill="none" stroke="var(--lab-kpi)" strokeWidth="2"/>
      {marks.map(mark=><line key={mark.forecast_id} x1={x(mark.mark_time)} x2={x(mark.mark_time)} y1="43" y2="326" className="lab-forecast-line" data-selected={mark.forecast_id===selected?.forecast_id}/>) }
      {ticks.map((t,i)=><text key={t} x={x(t)} y="351" textAnchor={i===0?"start":i===ticks.length-1?"end":"middle"} className="lab-axis">{date(new Date(t).toISOString())}</text>)}
      {active && <line x1={x(active.t)} x2={x(active.t)} y1="54" y2="327" className="lab-cursor"/>}
    </svg>
    <div className="lab-mark-track" aria-label="Voorspellingen op hun vastgelegde tijdstip">
      {marks.map((mark,i)=><button key={mark.forecast_id} type="button"
        className={`lab-mark ${mark.predicted_direction}`} data-selected={mark.forecast_id===selected?.forecast_id}
        style={{left:`${100*x(mark.mark_time)/width}%`,top:`${i%2?17:0}px`}}
        onClick={()=>onSelect(mark)}
        aria-label={`${mark.phase==='reconstructed'?'Gereconstrueerd':'Vastgelegd'} ${date(mark.mark_at,true)}: ${direction(mark.predicted_direction)}; ${mark.correct==null?'uitkomst open':mark.correct?'juist':'onjuist'}`}
        title={`${date(mark.mark_at,true)} · ${direction(mark.predicted_direction)} · klik voor meetvenster`}>
        {mark.predicted_direction==='up'?'↑':'↓'}<sup>{mark.correct==null?'○':mark.correct?'✓':'×'}</sup>
      </button>)}
    </div>
    <div className="lab-hover" aria-live="polite">
      {active ? <><span>Dagslot {date(active.quote.date)}: <b>{money(active.quote.sol_close)}</b> · {active.quote.price_method}</span><span>KPI gepubliceerd {date(active.kpi.published_at,true)}: <b>{number(active.kpi[candidate.field],1)} {candidate.unit}</b></span></>
        : <><span>Beweeg over de lijnen voor bron, waarde en tijdstip.</span><span>↑/↓ verwachting · ✓/× uitkomst · ○ nog open</span></>}
    </div>
  </div>;
}
