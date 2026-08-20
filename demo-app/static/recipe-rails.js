export async function buildRecipeRails(fetcher=fetch) {
  if (!document.body.classList.contains('tv')) return;
  const response = await fetcher('/api/rails');
  const rails = await response.json();
  const grid = document.querySelector('#recipes');
  const cards = new Map([...grid.children].map(card => [card.dataset.recipeId, card]));
  const shelf = document.createElement('div'); shelf.className = 'recipe-rails';
  rails.forEach((rail, row) => {
    const section = document.createElement('section'); section.className = 'recipe-rail'; section.dataset.row = row;
    section.innerHTML = `<h2>${rail.title}</h2><div class="recipe-track"></div>`;
    for (const id of rail.recipe_ids) if (cards.has(id)) section.lastElementChild.append(cards.get(id).cloneNode(true));
    shelf.append(section);
  });
  grid.replaceWith(shelf);
  document.dispatchEvent(new CustomEvent('tablestory:rails-ready'));
}
buildRecipeRails();
