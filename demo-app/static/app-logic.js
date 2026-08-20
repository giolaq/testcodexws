export function matchesRecipe(recipe, query) {
  return recipe.toLowerCase().includes(query.trim().toLowerCase());
}

export function cookbookState(saved, id) {
  const next = new Set(saved);
  next.has(id) ? next.delete(id) : next.add(id);
  return next;
}
