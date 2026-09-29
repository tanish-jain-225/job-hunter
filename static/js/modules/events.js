/**
 * Event delegation registry and action mappings for CSP compliance.
 */

export function setupEventDelegation(handlers) {
  document.addEventListener('click', (e) => {
    const actionTarget = e.target.closest('[data-action]');
    if (!actionTarget) return;

    const action = actionTarget.getAttribute('data-action');
    if (handlers && typeof handlers[action] === 'function') {
      handlers[action](actionTarget, e);
    }
  });

  document.addEventListener('submit', (e) => {
    if (!e.target || !e.target.id) return;
    const formId = e.target.id;
    if (handlers && typeof handlers[formId] === 'function') {
      handlers[formId](e.target, e);
    }
  });

  document.addEventListener('change', (e) => {
    if (!e.target) return;
    const changeAction = e.target.getAttribute('data-change-action') || e.target.id;
    if (handlers && typeof handlers[changeAction] === 'function') {
      handlers[changeAction](e.target, e);
    }
  });

  document.addEventListener('input', (e) => {
    if (!e.target || !e.target.id) return;
    const inputId = e.target.id;
    if (handlers && typeof handlers[inputId] === 'function') {
      handlers[inputId](e.target, e);
    }
  });
}
