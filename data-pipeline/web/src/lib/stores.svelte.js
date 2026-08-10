import { get } from './api.js';

export const sources = $state({ tree: [], loading: false, error: null });
export const toasts = $state({ items: [] });

// 엔진 전원 상태 — 헤더 위젯이 폴링해 채우고, 다른 화면(수집 버튼 가드)이 함께 구독한다.
export const engine = $state({ status: 'down' });

export async function refreshEngineStatus() {
  try {
    const r = await get('/api/engine/status');
    engine.status = r.status;
  } catch {
    // 폴링 실패는 조용히 무시 — 다음 주기(2초)에 재시도
  }
}

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
