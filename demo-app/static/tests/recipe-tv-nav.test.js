import test from 'node:test';
import assert from 'node:assert/strict';
import {nextRecipeFocus} from '../recipe-tv-nav.js';

test('remote focus stays in rails and preserves the nearest column',()=>{
  const lengths=[3,2,4];
  assert.deepEqual(nextRecipeFocus(0,0,'ArrowLeft',lengths),[0,0]);
  assert.deepEqual(nextRecipeFocus(0,2,'ArrowDown',lengths),[1,1]);
  assert.deepEqual(nextRecipeFocus(1,1,'ArrowDown',lengths),[2,1]);
  assert.deepEqual(nextRecipeFocus(2,3,'ArrowRight',lengths),[2,3]);
});
