import { expect, test } from 'vitest';
import { STAGE_LABELS } from './funnel_labels.js';

test('한국어 단계 라벨', () => {
  expect(STAGE_LABELS.extracted).toBe('검출');
  expect(STAGE_LABELS.needs_review).toBe('검수대기');
  expect(STAGE_LABELS.training).toBe('학습');
  expect(STAGE_LABELS.rejected).toBe('버림');
  expect(STAGE_LABELS.not_fixture).toBe('픽스처의심');
});
