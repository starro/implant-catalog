import { afterEach, expect, test, vi } from 'vitest';
import { ApiError, get, post } from './api.js';

afterEach(() => vi.restoreAllMocks());

function mockFetch(body, status = 200) {
  globalThis.fetch = vi.fn(async () => ({
    status,
    json: async () => body,
  }));
}

test('get 은 봉투를 벗겨 data 를 반환한다', async () => {
  mockFetch({ ok: true, data: { id: 1 }, error: null });
  expect(await get('/api/sources')).toEqual({ id: 1 });
});

test('get 은 쿼리 파라미터를 붙인다', async () => {
  mockFetch({ ok: true, data: null, error: null });
  await get('/api/sources/check', { url: 'https://ex.com/a.pdf' });
  expect(globalThis.fetch.mock.calls[0][0]).toBe(
    '/api/sources/check?url=https%3A%2F%2Fex.com%2Fa.pdf',
  );
});

test('ok:false 면 ApiError 를 던진다', async () => {
  mockFetch({ ok: false, data: null, error: { code: 'duplicate_url', message: '이미 등록됨' } }, 409);
  await expect(post('/api/sources', {})).rejects.toMatchObject({
    code: 'duplicate_url',
    message: '이미 등록됨',
    status: 409,
  });
});

test('post 는 JSON 본문을 보낸다', async () => {
  mockFetch({ ok: true, data: { id: 2 }, error: null });
  await post('/api/sources', { url: 'x' });
  const init = globalThis.fetch.mock.calls[0][1];
  expect(init.method).toBe('POST');
  expect(JSON.parse(init.body)).toEqual({ url: 'x' });
});

test('ApiError 는 Error 를 상속한다', () => {
  expect(new ApiError('c', 'm', 400)).toBeInstanceOf(Error);
});
