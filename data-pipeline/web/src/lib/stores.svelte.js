import { get } from './api.js';

export const sources = $state({ tree: [], loading: false, error: null });
export const toasts = $state({ items: [] });

let toastSeq = 0;

export function toast(message, kind = 'info') {
  const id = ++toastSeq;
  toasts.items = [...toasts.items, { id, message, kind }];
  setTimeout(() => {
    toasts.items = toasts.items.filter((t) => t.id !== id);
  }, 5000);
}

export async function loadSources() {
  sources.loading = true;
  sources.error = null;
  try {
    sources.tree = await get('/api/sources');
  } catch (e) {
    sources.error = e.message;
    toast(e.message, 'error');
  } finally {
    sources.loading = false;
  }
}
