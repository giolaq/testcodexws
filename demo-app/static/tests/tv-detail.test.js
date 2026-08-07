import test from 'node:test';
import assert from 'node:assert/strict';
import {
  isBrowseBackKey,
  nextDetailAction,
  wireTvDetail,
} from '../tv-detail.js';

function detailFixture(tv = true) {
  let keydown;
  const navigations = [];
  const root = {
    activeElement: null,
    body: {classList: {contains: value => value === 'tv' && tv}},
    addEventListener(type, listener) {
      if (type === 'keydown') keydown = listener;
    },
  };
  const actions = Array.from({length: 2}, (_, index) => ({
    tabIndex: 0,
    focus() { root.activeElement = actions[index]; },
  }));
  const shell = {
    dataset: {browseUrl: '/?mode=tv'},
    querySelectorAll: selector => selector === '[data-tv-action]' ? actions : [],
    querySelector: selector => selector === '[data-tv-primary]' ? actions[1] : null,
  };
  root.querySelector = selector => selector === '.detail-shell' ? shell : null;

  return {
    actions,
    navigations,
    root,
    dispatch(key) {
      let prevented = false;
      keydown?.({key, preventDefault() { prevented = true; }});
      return prevented;
    },
    wire() { wireTvDetail(root, url => navigations.push(url)); },
  };
}

test('detail action movement supports remote arrow keys and boundaries', () => {
  assert.equal(nextDetailAction(1, 2, 'ArrowUp'), 0);
  assert.equal(nextDetailAction(0, 2, 'ArrowLeft'), 0);
  assert.equal(nextDetailAction(0, 2, 'ArrowDown'), 1);
  assert.equal(nextDetailAction(1, 2, 'ArrowRight'), 1);
});

test('TV detail initially focuses its primary action and moves to browse', () => {
  const fixture = detailFixture();
  fixture.wire();

  assert.equal(fixture.root.activeElement, fixture.actions[1]);
  assert.deepEqual(fixture.actions.map(action => action.tabIndex), [-1, 0]);
  assert.equal(fixture.dispatch('ArrowUp'), true);
  assert.equal(fixture.root.activeElement, fixture.actions[0]);
  assert.deepEqual(fixture.actions.map(action => action.tabIndex), [0, -1]);
});

test('Escape and Backspace both return to TV browse', () => {
  const fixture = detailFixture();
  fixture.wire();

  assert.equal(isBrowseBackKey('Escape'), true);
  assert.equal(isBrowseBackKey('Backspace'), true);
  assert.equal(fixture.dispatch('Escape'), true);
  assert.equal(fixture.dispatch('Backspace'), true);
  assert.deepEqual(fixture.navigations, ['/?mode=tv', '/?mode=tv']);
});

test('mobile detail does not install TV remote behavior', () => {
  const fixture = detailFixture(false);
  fixture.wire();

  assert.equal(fixture.root.activeElement, null);
  assert.equal(fixture.dispatch('Escape'), false);
  assert.deepEqual(fixture.navigations, []);
});
