import { test } from 'node:test';
import assert from 'node:assert/strict';
import { matchHospitals } from './hospital-search.ts';

// Constructed names, not source records.
const options = [
  { id: 'A', name: 'ALLIED CARE EXPERTS (ACE) MEDICAL CENTER - QUEZON CITY, INC.' },
  { id: 'B', name: 'BERNARDINO GENERAL HOSPITAL' },
  { id: 'C', name: 'CAPITOL MEDICAL CENTER, INC.' },
  { id: 'D', name: 'QUEZON CITY GENERAL HOSPITAL' },
];

test('empty search lists every hospital in the given order', () => {
  assert.deepEqual(matchHospitals(options, '  ').map(o => o.id), ['A', 'B', 'C', 'D']);
});

test('every typed word must start a word of the name, ignoring case and punctuation', () => {
  assert.deepEqual(matchHospitals(options, 'ace med').map(o => o.id), ['A']);
  assert.deepEqual(matchHospitals(options, 'capitol').map(o => o.id), ['C']);
  assert.deepEqual(matchHospitals(options, 'general hosp').map(o => o.id), ['B', 'D']);
  assert.deepEqual(matchHospitals(options, 'apitol'), []);
});

test('names that start with the search come first', () => {
  assert.deepEqual(matchHospitals(options, 'quezon').map(o => o.id), ['D', 'A']);
});
