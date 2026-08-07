const ARROW_KEYS = new Set([
  'ArrowLeft',
  'ArrowRight',
  'ArrowUp',
  'ArrowDown',
]);

/**
 * Return the grid index reached by pressing an arrow key.
 *
 * Movement does not wrap between rows. If the requested neighbouring cell is
 * outside the grid (including a missing cell in a partial final row), the
 * current index is returned.
 */
export function nextFocus(index, columns, count, key) {
  if (
    !ARROW_KEYS.has(key)
    || !Number.isInteger(columns)
    || columns <= 0
    || !Number.isInteger(count)
    || count <= 0
    || !Number.isInteger(index)
    || index < 0
    || index >= count
  ) {
    return index;
  }

  const column = index % columns;

  if (key === 'ArrowLeft') {
    return column === 0 ? index : index - 1;
  }

  if (key === 'ArrowRight') {
    return column === columns - 1 || index + 1 >= count ? index : index + 1;
  }

  if (key === 'ArrowUp') {
    return index < columns ? index : index - columns;
  }

  return index + columns >= count ? index : index + columns;
}
