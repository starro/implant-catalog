// API 래퍼 — 서버 봉투 {ok,data,error} 를 벗겨 data 만 돌려준다.
export class ApiError extends Error {
  constructor(code, message, status) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function request(path, init) {
  const res = await fetch(path, init);
  const body = await res.json();
  if (!body.ok) {
    const e = body.error || {};
    throw new ApiError(e.code || 'unknown', e.message || '알 수 없는 오류', res.status);
  }
  return body.data;
}

export function get(path, params) {
  const qs = params ? `?${new URLSearchParams(params)}` : '';
  return request(`${path}${qs}`, { method: 'GET' });
}

export function post(path, body) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  });
}
