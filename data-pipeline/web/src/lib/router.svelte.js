// 의존성 없는 해시 라우터. #/sources, #/sources/12, #/overview, #/export, #/settings
const ROUTES = [
  [/^#\/sources\/(\d+)$/, (m) => ({ name: 'sourceDetail', params: { id: Number(m[1]) } })],
  [/^#\/sources$/, () => ({ name: 'sources', params: {} })],
  [/^#\/overview$/, () => ({ name: 'overview', params: {} })],
  [/^#\/export$/, () => ({ name: 'export', params: {} })],
  [/^#\/settings$/, () => ({ name: 'settings', params: {} })],
];

function parse(hash) {
  for (const [re, make] of ROUTES) {
    const m = hash.match(re);
    if (m) return make(m);
  }
  return { name: 'sources', params: {} };
}

export const route = $state(parse(location.hash || '#/sources'));

export function navigate(hash) {
  location.hash = hash;
}

window.addEventListener('hashchange', () => {
  const next = parse(location.hash);
  route.name = next.name;
  route.params = next.params;
});
