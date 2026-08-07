import { get } from './api.js';

export const sources = $state({ tree: [], loading: false, error: null });
export const toasts = $state({ items: [] });

// SSE 로 들어온 마지막 이벤트. 열려 있는 상세 화면이 이걸 구독해 자동 갱신한다(폴링 아님).
export const liveEvents = $state({ version: 0, last: null });

export function pushEvent(type, payload) {
  liveEvents.last = { type, payload };
  liveEvents.version += 1;
}

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
