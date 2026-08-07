import {nextFocus} from './focus.js';

if (document.body.classList.contains('tv')) {
  const getTargets = () => [...document.querySelectorAll('.movie-card > a')].filter(target => target.offsetParent !== null);
  const initial = getTargets();
  initial.forEach((target, index) => target.tabIndex = index === 0 ? 0 : -1);
  initial[0]?.focus();
  document.addEventListener('keydown', event => {
    const targets = getTargets();
    const index = targets.indexOf(document.activeElement);
    if (index < 0) return;
    if (event.key === 'Enter') { document.activeElement.click(); return; }
    const next = nextFocus(index, 6, targets.length, event.key);
    if (next !== index) {
      event.preventDefault(); targets[index].tabIndex = -1; targets[next].tabIndex = 0; targets[next].focus();
    }
  });
}
