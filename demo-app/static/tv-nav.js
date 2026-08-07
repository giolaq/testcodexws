import {nextFocus} from './focus.js';

const ARROW_KEYS = new Set([
  'ArrowLeft',
  'ArrowRight',
  'ArrowUp',
  'ArrowDown',
]);

function visibleMovieLinks(root) {
  return [...root.querySelectorAll('.movie-card > a')]
    .filter(link => !link.closest('.movie-card').hidden);
}

export function gridColumnCount(grid, readStyle = getComputedStyle) {
  const columns = readStyle(grid).gridTemplateColumns.trim();
  return columns ? columns.split(/\s+/).length : 1;
}

export function wireMovieGridNavigation(root = document, readStyle = getComputedStyle) {
  if (!root.body.classList.contains('tv')) return;

  const grid = root.querySelector('#movie-grid');
  if (!grid) return;

  const initialLinks = visibleMovieLinks(root);
  initialLinks.forEach((link, index) => {
    link.tabIndex = index === 0 ? 0 : -1;
  });
  initialLinks[0]?.focus();

  root.addEventListener('keydown', event => {
    const links = visibleMovieLinks(root);
    const index = links.indexOf(root.activeElement);
    if (index < 0) return;

    if (event.key === 'Enter') {
      event.preventDefault();
      links[index].click();
      return;
    }

    if (!ARROW_KEYS.has(event.key)) return;

    event.preventDefault();
    const next = nextFocus(
      index,
      gridColumnCount(grid, readStyle),
      links.length,
      event.key,
    );
    if (next === index) return;

    links[index].tabIndex = -1;
    links[next].tabIndex = 0;
    links[next].focus();
  });
}

if (typeof document !== 'undefined') {
  wireMovieGridNavigation();
}
