async function buildRails() {
  if (!document.body.classList.contains('tv')) return;
  const response = await fetch('/api/rails');
  const rails = await response.json();
  const grid = document.querySelector('#movie-grid');
  const cards = new Map([...grid.children].map(card => [card.querySelector('a').href.split('/').pop(), card]));
  const shelf = document.createElement('div'); shelf.className = 'rails';
  for (const rail of rails) {
    const section = document.createElement('section'); section.className = 'rail';
    section.innerHTML = `<h2>${rail.title}</h2><div class="rail-track"></div>`;
    for (const id of rail.movie_ids) if (cards.has(id)) section.lastElementChild.append(cards.get(id).cloneNode(true));
    shelf.append(section);
  }
  grid.replaceWith(shelf);
  const targets = [...shelf.querySelectorAll('.movie-card > a')];
  targets.forEach((target, index) => target.tabIndex = index === 0 ? 0 : -1);
  targets[0]?.focus();
}
buildRails();
