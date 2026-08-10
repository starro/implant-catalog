// 단계별 현황 표시와 일시 포맷.
import { STAGE_LABELS } from '../components/funnel_labels.js';

export const FUNNEL_COLORS = {
  training: '#059669',
  rejected: '#dc2626',
  pending: '#e5e7eb',
};

export function funnelSegments(funnel) {
  const total = funnel?.extracted || 0;
  return ['training', 'rejected', 'pending'].map((key) => {
    const count = funnel?.[key] || 0;
    return {
      key,
      label: STAGE_LABELS[key],
      count,
      color: FUNNEL_COLORS[key],
      pct: total ? (count / total) * 100 : 0,
    };
  });
}

const DT = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', hour12: false,
});

export function dateTime(iso) {
  if (!iso) return '—';
  const parts = Object.fromEntries(DT.formatToParts(new Date(iso)).map((p) => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

export function num(n) {
  return (n ?? 0).toLocaleString('ko-KR');
}
