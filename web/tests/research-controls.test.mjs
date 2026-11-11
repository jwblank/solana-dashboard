import test from 'node:test';
import assert from 'node:assert/strict';
import {sampleMarks, scopeHistory} from '../src/content/dashboard/model.js';

test('mark sampling is chronological and cannot select by outcome', () => {
  const rows=Array.from({length:30},(_,i)=>({
    forecast_id:String(i), model_available:true, predicted_direction:i%2?'up':'down',
    mark_time:i, entry_date:`2026-01-${String(i+1).padStart(2,'0')}`,
    exit_date:i+8<=31?`2026-01-${String(i+8).padStart(2,'0')}`:'2026-02-01',
    correct:i%3===0, sol_return:i%2?.1:-.1,
  })).reverse();
  const chosen=sampleMarks(rows);
  assert.deepEqual(chosen.map(r=>r.forecast_id), ['0','7','14','21','28']);
  assert.deepEqual(sampleMarks(rows.map(r=>({...r,correct:!r.correct,sol_return:-r.sol_return})))
    .map(r=>r.forecast_id), chosen.map(r=>r.forecast_id));
  assert.equal(sampleMarks(rows,true).length,30);
  assert.equal(sampleMarks([...rows,{model_available:false}]).length,5);
});

test('range uses elapsed time, preserving gaps and full-history default', () => {
  const rows=[0,5,40,60].map(day=>({close_time:day*86400000}));
  assert.equal(scopeHistory(rows,'all'),rows);
  assert.deepEqual(scopeHistory(rows,'30'),rows.slice(2));
});
