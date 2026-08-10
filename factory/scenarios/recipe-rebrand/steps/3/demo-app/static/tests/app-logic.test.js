import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesRecipe,cookbookState} from '../app-logic.js';

test('recipe matching ignores case and surrounding whitespace',()=>{
  assert.equal(matchesRecipe('Tomato Pasta basil',' BASIL '),true);
  assert.equal(matchesRecipe('Tomato Pasta','miso'),false);
});

test('cookbook state toggles without mutating its input',()=>{
  const saved=new Set(['one']);
  assert.deepEqual([...cookbookState(saved,'two')],['one','two']);
  assert.deepEqual([...saved],['one']);
  assert.deepEqual([...cookbookState(saved,'one')],[]);
});
