const BACK_KEYS = new Set(['Escape', 'Backspace']);
const PREVIOUS_KEYS = new Set(['ArrowUp', 'ArrowLeft']);
const NEXT_KEYS = new Set(['ArrowDown', 'ArrowRight']);

export function isBrowseBackKey(key) {
  return BACK_KEYS.has(key);
}

export function nextDetailAction(index, count, key) {
  if (!Number.isInteger(index) || index < 0 || index >= count || count < 1) {
    return index;
  }
  if (PREVIOUS_KEYS.has(key)) return Math.max(0, index - 1);
  if (NEXT_KEYS.has(key)) return Math.min(count - 1, index + 1);
  return index;
}

export function wireTvDetail(
  root = document,
  navigate = url => window.location.assign(url),
) {
  if (!root.body.classList.contains('tv')) return;

  const shell = root.querySelector('.detail-shell');
  if (!shell) return;

  const actions = [...shell.querySelectorAll('[data-tv-action]')];
  const initial = shell.querySelector('[data-tv-primary]') || actions[0];
  actions.forEach(action => {
    action.tabIndex = action === initial ? 0 : -1;
  });
  initial?.focus();

  root.addEventListener('keydown', event => {
    if (isBrowseBackKey(event.key)) {
      event.preventDefault();
      navigate(shell.dataset.browseUrl || '/');
      return;
    }

    if (!PREVIOUS_KEYS.has(event.key) && !NEXT_KEYS.has(event.key)) return;

    const current = actions.indexOf(root.activeElement);
    const index = current < 0 ? actions.indexOf(initial) : current;
    const next = nextDetailAction(index, actions.length, event.key);
    event.preventDefault();
    if (next === index) return;

    actions[index].tabIndex = -1;
    actions[next].tabIndex = 0;
    actions[next].focus();
  });
}

if (typeof document !== 'undefined' && typeof window !== 'undefined') {
  wireTvDetail();
}
