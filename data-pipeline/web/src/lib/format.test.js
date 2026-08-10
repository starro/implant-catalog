import { expect, test } from 'vitest';
import { dateTime, duration, funnelSegments } from './format.js';

const FUNNEL = { extracted: 100, training: 30, rejected: 10, pending: 60 };

test('funnelSegments 는 학습·버림·대기 순으로 3구간을 만든다', () => {
  const segs = funnelSegments(FUNNEL);
  expect(segs.map((s) => s.key)).toEqual(['training', 'rejected', 'pending']);
  expect(segs.map((s) => s.count)).toEqual([30, 10, 60]);
});

test('funnelSegments 의 비율 합은 100 이다', () => {
  const total = funnelSegments(FUNNEL).reduce((a, s) => a + s.pct, 0);
  expect(Math.round(total)).toBe(100);
});

test('추출이 0이면 모든 구간이 0% 다', () => {
  const segs = funnelSegments({ extracted: 0, training: 0, rejected: 0, pending: 0 });
  expect(segs.every((s) => s.pct === 0)).toBe(true);
});

test('dateTime 은 서울 시간으로 분까지 표시한다', () => {
  expect(dateTime('2026-07-20T05:02:00+00:00')).toBe('2026-07-20 14:02');
});

test('dateTime 은 빈 값에 대해 대시를 반환한다', () => {
  expect(dateTime(null)).toBe('—');
});

test('duration 은 초/분/시간 단위로 소요시간을 만든다', () => {
  const s = '2026-08-10T00:00:00Z';
  expect(duration(s, '2026-08-10T00:00:45Z')).toBe('45초');
  expect(duration(s, '2026-08-10T00:03:00Z')).toBe('3분');
  expect(duration(s, '2026-08-10T00:03:12Z')).toBe('3분 12초');
  expect(duration(s, '2026-08-10T01:05:00Z')).toBe('1시간 5분');
});

test('duration 은 미완료(끝시간 없음)면 빈 문자열이다', () => {
  expect(duration('2026-08-10T00:00:00Z', null)).toBe('');
});
