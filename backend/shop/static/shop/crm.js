(() => {
  'use strict';

  const app = document.querySelector('.crm-app');
  if (!app) return;
  const submitContents = new WeakMap();

  // Ordinary POST forms remain functional when JavaScript is unavailable.
  app.addEventListener('submit', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const confirmation = form.dataset.confirm;
    if (confirmation && !window.confirm(confirmation)) {
      event.preventDefault();
      return;
    }
    if (!form.hasAttribute('data-submit-lock') || event.defaultPrevented) return;
    const button = event.submitter;
    if (!(button instanceof HTMLButtonElement)) return;
    submitContents.set(button, [...button.childNodes]);
    button.style.minWidth = `${button.getBoundingClientRect().width}px`;
    button.disabled = true;
    button.setAttribute('aria-busy', 'true');
    button.textContent = form.dataset.submitMessage || 'Enregistrement…';
  });

  // Back/forward cache can restore the exact previous DOM, including disabled buttons.
  window.addEventListener('pageshow', () => {
    app.querySelectorAll('button[aria-busy="true"]').forEach(button => {
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.style.removeProperty('min-width');
      const content = submitContents.get(button);
      if (content) button.replaceChildren(...content);
    });
  });

  app.querySelectorAll('.crm-field.has-error').forEach(field => {
    const input = field.querySelector('input, textarea, select');
    if (!input) return;
    input.setAttribute('aria-invalid', 'true');
    const errors = [...field.querySelectorAll('.crm-field-error[id]')].map(error => error.id);
    if (errors.length) input.setAttribute('aria-describedby', errors.join(' '));
  });

  const photoInput = app.querySelector('input[name="photo"]');
  const preview = app.querySelector('[data-photo-preview]');
  const photoFeedback = app.querySelector('[data-photo-feedback]');
  if (photoInput && preview && photoFeedback) {
    photoInput.setAttribute('accept', 'image/jpeg,image/png,image/webp');
    photoInput.addEventListener('change', () => {
      const file = photoInput.files?.[0];
      photoFeedback.textContent = '';
      photoFeedback.classList.remove('is-error');
      if (!file) return;
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
        photoFeedback.textContent = 'Choisissez une photo JPEG, PNG ou WebP de 5 Mo maximum.';
        photoFeedback.classList.add('is-error');
        return;
      }
      const reader = new FileReader();
      reader.addEventListener('load', () => {
        if (typeof reader.result !== 'string') return;
        const image = document.createElement('img');
        image.src = reader.result;
        image.alt = 'Aperçu de la nouvelle photo du plat';
        preview.replaceChildren(image);
        preview.classList.remove('is-empty');
        photoFeedback.textContent = 'Nouvelle photo sélectionnée. Enregistrez le plat pour la publier.';
      });
      reader.addEventListener('error', () => {
        photoFeedback.textContent = 'La photo ne peut pas être lue. Choisissez un autre fichier.';
        photoFeedback.classList.add('is-error');
      });
      reader.readAsDataURL(file);
    });
  }

  const hoursList = app.querySelector('[data-hours-list]');
  const hoursTemplate = app.querySelector('#crm-empty-hours');
  const addHours = app.querySelector('[data-add-hours]');
  const updateHourNotes = () => {
    hoursList?.querySelectorAll('[data-hours-row]').forEach(row => {
      const opens = row.querySelector('[name$="-opens"]');
      const closes = row.querySelector('[name$="-closes"]');
      const removed = row.querySelector('[name$="-DELETE"]');
      const note = row.querySelector('[data-hours-note]');
      row.classList.toggle('is-deleted', Boolean(removed?.checked));
      if (!note) return;
      note.textContent = removed?.checked ? 'Ce créneau sera supprimé à l’enregistrement.'
        : opens?.value && closes?.value && closes.value < opens.value ? 'Ferme le lendemain.' : '';
    });
  };
  if (hoursList) {
    hoursList.addEventListener('change', updateHourNotes);
    updateHourNotes();
  }
  if (hoursList && hoursTemplate && addHours) {
    addHours.addEventListener('click', () => {
      const total = app.querySelector('input[name="hours-TOTAL_FORMS"]');
      const max = app.querySelector('input[name="hours-MAX_NUM_FORMS"]');
      const feedback = app.querySelector('[data-hours-feedback]');
      if (!total) return;
      const count = Number(total.value);
      const maximum = Number(max?.value) || 28;
      if (!Number.isInteger(count) || count >= maximum) {
        if (feedback) feedback.textContent = `Vous pouvez renseigner au maximum ${maximum} créneaux.`;
        return;
      }
      const content = hoursTemplate.content.cloneNode(true);
      content.querySelectorAll('*').forEach(element => {
        for (const attribute of ['name', 'id', 'for', 'aria-describedby']) {
          if (element.hasAttribute(attribute)) element.setAttribute(attribute, element.getAttribute(attribute).replaceAll('__prefix__', String(count)));
        }
      });
      hoursList.append(content);
      total.value = String(count + 1);
      const last = hoursList.lastElementChild;
      last?.querySelector('select, input:not([type="hidden"])')?.focus();
      if (feedback) feedback.textContent = 'Créneau ajouté. Enregistrez les changements pour le conserver.';
      updateHourNotes();
    });
  }

  app.querySelectorAll('[data-refresh-fragment]').forEach(container => {
    const toolbar = container.previousElementSibling;
    const status = toolbar?.querySelector('[data-refresh-status]');
    const button = toolbar?.querySelector('[data-refresh-button]');
    const endpoint = container.dataset.refreshFragment;
    const fragmentName = container.dataset.fragmentName;
    if (!status || !button || !endpoint || !fragmentName) return;
    let busy = false;
    const actionInProgress = () => Boolean(container.querySelector('form [aria-busy="true"]'));

    const displayTime = root => {
      const raw = root.querySelector('[data-crm-updated-at]')?.dataset.crmUpdatedAt;
      if (!raw) return;
      const date = new Date(raw);
      if (Number.isNaN(date.getTime())) return;
      const time = new Intl.DateTimeFormat('fr-FR', {hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Paris'}).format(date);
      status.textContent = `Actualisé à ${time}`;
      status.classList.remove('is-error');
    };
    displayTime(container);

    const refresh = async (manual = false) => {
      if (busy || document.hidden) return;
      // Keep an active action, keyboard focus and expanded order details intact.
      if (actionInProgress() || (!manual && container.contains(document.activeElement))) return;
      busy = true;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(endpoint, {
          credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
          headers: {'X-Requested-With': 'XMLHttpRequest'},
        });
        if (response.redirected || response.status === 401 || response.status === 403) {
          const link = document.createElement('a');
          link.href = '/crm/connexion/';
          link.textContent = 'Se reconnecter';
          status.replaceChildren('La mise à jour demande une connexion autorisée. ', link);
          status.classList.add('is-error');
          return;
        }
        if (!response.ok) throw new Error('refresh');
        if (response.headers.get('X-STC-Fragment') !== fragmentName) throw new Error('fragment');
        const html = await response.text();
        const documentFragment = new DOMParser().parseFromString(html, 'text/html');
        const updated = documentFragment.querySelector('[data-crm-updated-at]');
        if (!updated) throw new Error('fragment');
        // The user may have started an action while the response was in flight.
        if (document.hidden || container.contains(document.activeElement) || actionInProgress()) return;
        const expanded = new Set([...container.querySelectorAll('details[data-order-detail][open]')].map(detail => detail.dataset.orderDetail));
        container.replaceChildren(...documentFragment.body.childNodes);
        container.querySelectorAll('details[data-order-detail]').forEach(detail => {detail.open = expanded.has(detail.dataset.orderDetail);});
        displayTime(container);
      } catch {
        status.textContent = 'Mise à jour interrompue. Les dernières données restent affichées.';
        status.classList.add('is-error');
      } finally {
        window.clearTimeout(timer);
        busy = false;
        button.disabled = false;
        button.removeAttribute('aria-busy');
      }
    };
    button.addEventListener('click', () => refresh(true));
    window.setInterval(() => refresh(), 15000);
    document.addEventListener('visibilitychange', () => {if (!document.hidden) refresh();});
    window.addEventListener('focus', () => refresh());
  });
})();
