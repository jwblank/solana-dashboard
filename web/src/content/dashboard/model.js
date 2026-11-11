export const percent = value => value == null ? "—" : `${(100 * value).toLocaleString("nl-NL", {maximumFractionDigits:1})}%`;
export const number = (value, digits=3) => value == null ? "—" : Number(value).toLocaleString("nl-NL", {maximumFractionDigits:digits});
export const money = value => value == null ? "—" : Number(value).toLocaleString("nl-NL", {style:"currency",currency:"USD",maximumFractionDigits:2});
export const date = (value, withTime=false) => value ? new Intl.DateTimeFormat("nl-NL", {day:"numeric",month:"short",...(withTime ? {hour:"2-digit",minute:"2-digit",timeZone:"Europe/Amsterdam"} : {timeZone:"UTC"})}).format(new Date(value.length===10 ? `${value}T12:00:00Z` : value)) : "—";
export const direction = value => ({up:"stijging",down:"daling",flat:"ongewijzigd"}[value] || "geen modeluitvoer");
export function featureValue(candidate) {
  const value=candidate.current_value;
  return value == null ? "—" : `${number(value,1)}${candidate.unit === "%" ? "%" : candidate.unit === "/100" ? " / 100" : ""}`;
}
export function sampleMarks(rows, showAll=false) {
  const available=rows.filter(row=>row.model_available && row.predicted_direction).toSorted((a,b)=>a.mark_time-b.mark_time);
  if(showAll || available.length<=12) return available;
  let end="";
  return available.filter(row=> {
    if(row.entry_date<end) return false;
    end=row.exit_date; return true;
  });
}
export function scopeHistory(history, days) {
  if(days==="all" || !history.length) return history;
  const start=history.at(-1).close_time-Number(days)*86400000;
  return history.filter(row=>row.close_time>=start);
}
export function evaluationRows(evaluations,phase) {
  return evaluations.filter(row=>row.phase===phase && row.horizon_days===7).map(row=>({
    ...row, "Brier-verschil":row.brier_improvement,
    low:row.brier_improvement_ci95[0],high:row.brier_improvement_ci95[1],
  }));
}

export function blueScoreChange(current,previous,definitions){
  if(!previous) return 'De eerste opgeslagen waarneming in dit bereik.';
  const delta=current.score-previous.score;
  if(current.raw_score!=null && previous.raw_score!=null){
    const capNow=current.raw_score-current.score, capBefore=previous.raw_score-previous.score;
    if(Math.abs(capNow-capBefore)>.05 && Math.abs(capNow-capBefore)>Math.abs(delta)*.5)
      return `De begrenzing veranderde de scorebijdrage met ${number(-(capNow-capBefore),2)} punten; verandering van de eindscore: ${number(delta,2)} punten.`;
    const differences=definitions.map(c=>({label:c.label,delta:current[c.key+'_points']-previous[c.key+'_points']})).sort((a,b)=>Math.abs(b.delta)-Math.abs(a.delta));
    return Math.abs(delta)<.005?'De eindscore bleef gelijk aan de vorige waarneming.':`${differences[0].label} veranderde het meest: ${number(differences[0].delta,2)} gewogen punten. De totale eindscore veranderde ${number(delta,2)} punten.`;
  }
  return `Eindscore ${delta>=0?'+':''}${number(delta,2)} punten versus ${date(previous.date)}. De volledige oude opbouw ontbreekt; de oorzaak is niet vast te stellen. ${current.ceiling!=null?`Geregistreerde bovengrens: ${current.ceiling}.`:''}`;
}
