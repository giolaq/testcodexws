if (document.body.classList.contains('tv')) {
  const actions = [...document.querySelectorAll('[data-tv-action]')];
  actions[0]?.focus();
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' || event.key === 'Backspace') {
      event.preventDefault(); location.assign(document.querySelector('.detail-shell').dataset.browseUrl); return;
    }
    if (!['ArrowUp','ArrowDown'].includes(event.key)) return;
    event.preventDefault();
    const at = Math.max(0, actions.indexOf(document.activeElement));
    actions[event.key === 'ArrowDown' ? Math.min(actions.length-1,at+1) : Math.max(0,at-1)]?.focus();
  });
}
