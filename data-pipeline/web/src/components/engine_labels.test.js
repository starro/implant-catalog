import { expect, test } from 'vitest';
import { ENGINE_LABELS } from './engine_labels.js';

test('엔진 상태 한국어 라벨', () => {
  expect(ENGINE_LABELS.down).toBe('내림');
  expect(ENGINE_LABELS.starting).toBe('켜는중');
  expect(ENGINE_LABELS.ready).toBe('준비됨');
});
