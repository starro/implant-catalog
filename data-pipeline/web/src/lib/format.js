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

// 시작~완료 소요시간을 사람이 읽기 좋게. 미완료면 빈 문자열.
export function duration(startIso, endIso) {
  if (!startIso || !endIso) return '';
  const ms = new Date(endIso) - new Date(startIso);
  if (!(ms >= 0)) return '';
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return rs ? `${m}분 ${rs}초` : `${m}분`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm ? `${h}시간 ${rm}분` : `${h}시간`;
}
