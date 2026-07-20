// SSE 구독 — 수집/동기화 완료 시 화면을 갱신한다. 폴링하지 않는다.
import { loadSources, toast } from './stores.svelte.js';

export function connect() {
  const es = new EventSource('/api/events');

  es.addEventListener('run.finished', (e) => {
    const p = JSON.parse(e.data);
    if (p.status === 'SUCCESS') {
      toast(`수집 완료 — ${p.extracted}장`, 'success');
    } else {
      toast(`수집 실패 — ${p.error || p.status}`, 'error');
    }
    if (p.fiftyone && !p.fiftyone.ok) {
      toast(`FiftyOne 재기동 실패: ${p.fiftyone.detail}`, 'error');
    }
    loadSources();
  });

  es.addEventListener('sync.finished', (e) => {
    const p = JSON.parse(e.data);
    toast(`검수결과 반영 — 학습 승급 ${p.promoted} · 버림 ${p.rejected}`, 'success');
    loadSources();
  });

  es.addEventListener('export.finished', (e) => {
    toast(`내보내기 완료 — ${JSON.parse(e.data).rows}행`, 'success');
  });

  return es;
}
