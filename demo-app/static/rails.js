function validRail(rail) {
  return rail
    && typeof rail.title === 'string'
    && Array.isArray(rail.movie_ids);
}

export async function fetchRails(fetcher = fetch) {
  const response = await fetcher('/api/rails');
  if (!response.ok) {
    throw new Error(`Could not load rails (${response.status})`);
  }

  const rails = await response.json();
  if (!Array.isArray(rails) || !rails.every(validRail)) {
    throw new TypeError('The rails API returned an invalid payload');
  }
  return rails;
}

function movieId(card) {
  return card.querySelector('.watchlist')?.dataset.movieId;
}

function railSection(rail, cards, index, root) {
  const section = root.createElement('section');
  const heading = root.createElement('h2');
  const track = root.createElement('div');
  const headingId = `rail-heading-${index}`;

  section.className = 'rail';
  section.setAttribute('aria-labelledby', headingId);
  heading.id = headingId;
  heading.textContent = rail.title;
  track.className = 'rail-track';

  for (const id of rail.movie_ids) {
    const card = cards.get(id);
    if (!card) continue;
    const copy = card.cloneNode(true);
    copy.hidden = false;
    track.append(copy);
  }

  if (!track.children.length) {
    const empty = root.createElement('p');
    empty.className = 'rail-empty';
    empty.textContent = 'No films here yet.';
    track.append(empty);
  }

  section.append(heading, track);
  return section;
}

export function renderRails(rails, root = document) {
  const grid = root.querySelector('#movie-grid');
  if (!grid) return false;

  const cards = new Map(
    [...grid.querySelectorAll('.movie-card')]
      .map(card => [movieId(card), card])
      .filter(([id]) => id),
  );
  const shelf = root.createElement('div');
  shelf.className = 'rails';
  shelf.setAttribute('aria-live', 'polite');

  rails.forEach((rail, index) => {
    shelf.append(railSection(rail, cards, index, root));
  });
  grid.replaceWith(shelf);

  const links = [...shelf.querySelectorAll('.movie-card > a')];
  links.forEach((link, index) => {
    link.tabIndex = index === 0 ? 0 : -1;
  });
  links[0]?.focus();
  return true;
}

export async function buildRails(root = document, fetcher = fetch) {
  if (!root.body.classList.contains('tv')) return false;

  try {
    return renderRails(await fetchRails(fetcher), root);
  } catch (error) {
    root.body.classList.add('rails-unavailable');
    console.error(error);
    return false;
  }
}

if (typeof document !== 'undefined') {
  buildRails();
}
