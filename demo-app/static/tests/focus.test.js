import test from 'node:test';
import assert from 'node:assert/strict';
import {nextFocus} from '../focus.js';

test('moves through a regular grid', () => {
  assert.equal(nextFocus(4, 3, 9, 'ArrowLeft'), 3);
  assert.equal(nextFocus(4, 3, 9, 'ArrowRight'), 5);
  assert.equal(nextFocus(4, 3, 9, 'ArrowUp'), 1);
  assert.equal(nextFocus(4, 3, 9, 'ArrowDown'), 7);
});

test('stays put at grid boundaries and short final rows', () => {
  assert.equal(nextFocus(0, 3, 8, 'ArrowLeft'), 0);
  assert.equal(nextFocus(2, 3, 8, 'ArrowRight'), 2);
  assert.equal(nextFocus(7, 3, 8, 'ArrowDown'), 7);
  assert.equal(nextFocus(7, 3, 8, 'ArrowRight'), 7);
});
