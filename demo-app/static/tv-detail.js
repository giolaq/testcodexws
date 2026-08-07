if (document.body.classList.contains('tv')) {
  const actions = [...document.querySelectorAll('.detail-shell a,.detail-shell button')];
  actions[0]?.focus();
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' || event.key === 'Backspace') { event.preventDefault(); history.back(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const at = Math.max(0, actions.indexOf(document.activeElement));
      actions[(at + (event.key === 'ArrowDown' ? 1 : actions.length - 1)) % actions.length].focus();
    }
  });
}
