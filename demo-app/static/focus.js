const ARROWS = new Set(['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown']);

export function nextFocus(index, columns, count, key) {
  if (!ARROWS.has(key) || count <= 0 || index < 0 || index >= count) return index;
  const row = Math.floor(index / columns);
  const column = index % columns;
  if (key === 'ArrowLeft') return column === 0 ? index : index - 1;
  if (key === 'ArrowRight') return column === columns - 1 || index + 1 >= count ? index : index + 1;
  if (key === 'ArrowUp') return row === 0 ? index : index - columns;
  return index + columns >= count ? index : index + columns;
}
