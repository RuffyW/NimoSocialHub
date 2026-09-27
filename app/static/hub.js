document.querySelectorAll('[data-back]').forEach(button => button.addEventListener('click', () => history.back()));
document.querySelectorAll('[data-media-form]').forEach(form => {
  const list = form.querySelector('[data-selected]');
  const hidden = form.querySelector('[data-media-order]');
  const choice = form.querySelector('[data-media-choice]');
  const update = () => { hidden.value = [...list.children].map(row => row.dataset.id).join(','); };
  list.addEventListener('click', event => {
    const row = event.target.closest('li');
    if (!row) return;
    if (event.target.matches('[data-remove]')) row.remove();
    if (event.target.matches('[data-up]') && row.previousElementSibling) list.insertBefore(row, row.previousElementSibling);
    if (event.target.matches('[data-down]') && row.nextElementSibling) list.insertBefore(row.nextElementSibling, row);
    update();
  });
  form.querySelector('[data-add-media]').addEventListener('click', () => {
    if (!choice.value || [...list.children].some(row => row.dataset.id === choice.value)) return;
    const row = document.createElement('li'); row.dataset.id = choice.value;
    const img = document.createElement('img'); img.src = `/media/${choice.value}/preview`; img.alt = '';
    const label = document.createElement('span'); label.textContent = choice.selectedOptions[0].textContent;
    row.append(img, label);
    for (const [action, text, name] of [['up','↑','Nach oben'],['down','↓','Nach unten'],['remove','×','Entfernen']]) {
      const button = document.createElement('button'); button.type = 'button'; button.dataset[action] = ''; button.textContent = text; button.setAttribute('aria-label',name); row.append(button);
    }
    list.append(row); update();
  });
});
document.body.addEventListener('htmx:configRequest', event => { event.detail.headers['X-Requested-With'] = 'Nimo'; });
document.body.addEventListener('htmx:afterSwap', () => {
  const counter = document.querySelector('[data-open-task-count]');
  if (counter) counter.textContent = [...document.querySelectorAll('.tasks .task')].filter(row => !row.querySelector('.completed')).length;
});
