const search = document.querySelector('#search');
const cards = [...document.querySelectorAll('.recipe-card')];
const count = document.querySelector('#count');
const empty = document.querySelector('#empty');

search?.addEventListener('input', () => {
  const query = search.value.trim().toLowerCase();
  let visible = 0;
  for (const card of cards) {
    card.hidden = !card.dataset.search.includes(query);
    if (!card.hidden) visible += 1;
  }
  count.textContent = `${visible} ${visible === 1 ? 'recipe' : 'recipes'}`;
  empty.hidden = visible !== 0;
});

let saved = new Set();
function render(button) {
  const active = saved.has(button.dataset.recipeId);
  button.setAttribute('aria-pressed', String(active));
  button.textContent = active ? 'Saved' : (button.closest('.detail-content') ? 'Save to My Cookbook' : 'Save');
  const title = button.closest('.recipe-card')?.querySelector('h3')?.textContent || document.querySelector('h1')?.textContent || 'recipe';
  button.setAttribute('aria-label', `${active ? 'Remove' : 'Add'} ${title} ${active ? 'from' : 'to'} My Cookbook`);
}

const buttons = [...document.querySelectorAll('.cookbook[data-recipe-id]')];
fetch('/api/cookbook').then(response => response.json()).then(recipes => {
  saved = new Set(recipes.map(recipe => recipe.id)); buttons.forEach(render);
});
for (const button of buttons) button.addEventListener('click', async () => {
  const id = button.dataset.recipeId;
  const active = saved.has(id);
  await fetch(active ? `/api/cookbook/${id}` : '/api/cookbook', {
    method: active ? 'DELETE' : 'POST', headers: {'Content-Type':'application/json'},
    body: active ? undefined : JSON.stringify({id}),
  });
  active ? saved.delete(id) : saved.add(id); render(button);
});
