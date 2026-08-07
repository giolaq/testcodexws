import test from 'node:test';
import assert from 'node:assert/strict';
import {gridColumnCount, wireMovieGridNavigation} from '../tv-nav.js';

function navigationFixture() {
  let keydown;
  const root = {
    activeElement: null,
    body: {classList: {contains: value => value === 'tv'}},
    addEventListener(type, listener) {
      if (type === 'keydown') keydown = listener;
    },
  };
  const card = {hidden: false};
  const links = Array.from({length: 6}, (_, index) => ({
    tabIndex: 0,
    clicks: 0,
    closest: () => card,
    focus() { root.activeElement = links[index]; },
    click() { links[index].clicks += 1; },
  }));
  const grid = {};
  root.querySelectorAll = selector => selector === '.movie-card > a' ? links : [];
  root.querySelector = selector => selector === '#movie-grid' ? grid : null;

  return {
    root,
    links,
    dispatch(key) {
      let prevented = false;
      keydown({key, preventDefault() { prevented = true; }});
      return prevented;
    },
    readStyle: () => ({gridTemplateColumns: '100px 100px 100px'}),
  };
}

test('column count follows the rendered grid', () => {
  assert.equal(gridColumnCount({}, () => ({gridTemplateColumns: '100px 100px'})), 2);
});

test('TV navigation initially focuses the first movie and uses arrow movement', () => {
  const fixture = navigationFixture();
  wireMovieGridNavigation(fixture.root, fixture.readStyle);

  assert.equal(fixture.root.activeElement, fixture.links[0]);
  assert.deepEqual(fixture.links.map(link => link.tabIndex), [0, -1, -1, -1, -1, -1]);
  assert.equal(fixture.dispatch('ArrowDown'), true);
  assert.equal(fixture.root.activeElement, fixture.links[3]);
  assert.deepEqual(fixture.links.map(link => link.tabIndex), [-1, -1, -1, 0, -1, -1]);
});

test('Enter opens the focused movie', () => {
  const fixture = navigationFixture();
  wireMovieGridNavigation(fixture.root, fixture.readStyle);

  fixture.dispatch('ArrowRight');
  assert.equal(fixture.dispatch('Enter'), true);
  assert.equal(fixture.links[1].clicks, 1);
});
