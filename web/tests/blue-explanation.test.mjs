import test from 'node:test';
import assert from 'node:assert/strict';
import {blueScoreChange} from '../src/content/dashboard/model.js';

test('explains a cap release instead of claiming stronger fundamentals',()=>{
  const previous={score:55,raw_score:80,date:'2026-11-08',quality_points:80};
  const current={score:80,raw_score:80,date:'2026-11-09',quality_points:80};
  const text=blueScoreChange(current,previous,[{key:'quality',label:'Testkwaliteit'}]);
  assert.match(text,/begrenzing/);
  assert.match(text,/25/);
  assert.doesNotMatch(text,/Testkwaliteit veranderde/);
});

test('missing historical components cannot produce a causal explanation',()=>{
  const text=blueScoreChange({score:80,raw_score:80},{score:55,raw_score:null,date:'2026-11-08'},[]);
  assert.match(text,/oorzaak is niet vast te stellen/);
});

test('reports weighted contribution change with complete inputs',()=>{
  const text=blueScoreChange({score:78,raw_score:78,quality_points:16},
    {score:77,raw_score:77,quality_points:15},[{key:'quality',label:'Testkwaliteit'}]);
  assert.match(text,/Testkwaliteit veranderde het meest: 1 gewogen punten/);
});
