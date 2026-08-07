import test from 'node:test';
import assert from 'node:assert/strict';
import {nextFocus} from '../focus.js';

test('all four arrow keys move to adjacent cells', () => {
  assert.equal(nextFocus(4, 3, 9, 'ArrowLeft'), 3);
  assert.equal(nextFocus(4, 3, 9, 'ArrowRight'), 5);
  assert.equal(nextFocus(4, 3, 9, 'ArrowUp'), 1);
  assert.equal(nextFocus(4, 3, 9, 'ArrowDown'), 7);
});

test('focus stays inside each edge of a complete grid', () => {
  assert.equal(nextFocus(0, 3, 9, 'ArrowLeft'), 0);
  assert.equal(nextFocus(2, 3, 9, 'ArrowRight'), 2);
  assert.equal(nextFocus(1, 3, 9, 'ArrowUp'), 1);
  assert.equal(nextFocus(7, 3, 9, 'ArrowDown'), 7);
});

test('focus handles a partial final row without escaping or wrapping', () => {
  assert.equal(nextFocus(4, 3, 8, 'ArrowDown'), 7);
  assert.equal(nextFocus(5, 3, 8, 'ArrowDown'), 5);
  assert.equal(nextFocus(7, 3, 8, 'ArrowUp'), 4);
  assert.equal(nextFocus(7, 3, 8, 'ArrowRight'), 7);
  assert.equal(nextFocus(6, 3, 8, 'ArrowLeft'), 6);
});

test('unsupported or invalid inputs do not produce another index', () => {
  assert.equal(nextFocus(4, 3, 9, 'Enter'), 4);
  assert.equal(nextFocus(4, 0, 9, 'ArrowRight'), 4);
  assert.equal(nextFocus(-1, 3, 9, 'ArrowRight'), -1);
  assert.equal(nextFocus(9, 3, 9, 'ArrowLeft'), 9);
});
