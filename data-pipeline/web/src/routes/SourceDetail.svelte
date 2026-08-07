<script>
  import { get, post } from '../lib/api.js';
  import FunnelBar from '../components/FunnelBar.svelte';
  import RunTable from '../components/RunTable.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { dateTime } from '../lib/format.js';
  import { liveEvents, loadSources, toast } from '../lib/stores.svelte.js';
  import { navigate } from '../lib/router.svelte.js';

  let { id } = $props();

  let doc = $state(null);
  let busy = $state(false);
  let editing = $state(false);
  let edit = $state({ name: '', brand: '', memo: '', conf: 0.35, dpi: 200, pages: '' });
  let settings = $state({ DAGSTER_URL: '', FIFTYONE_URL: '' });

  // 최신 수집이 진행 중인가 — 진행 중엔 빈 퍼널 대신 인디케이터를 보여준다.
  let running = $derived(
    !!doc?.runs?.[0] && ['QUEUED', 'RUNNING'].includes(doc.runs[0].status),
  );

  async function load() {
    try {
      doc = await get(`/api/sources/${id}`);
      edit = {
        name: doc.name, brand: doc.brand_raw || doc.brand, memo: doc.memo,
        conf: doc.default_conf, dpi: doc.default_dpi, pages: doc.default_pages,
      };
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  $effect(() => {
    id;                                   // id 가 바뀌면 다시 불러온다
    load();
    get('/api/settings').then((s) => (settings = s)).catch(() => {});
  });

  // 완료/동기화 SSE 가 오면 이 문서 상세를 자동 갱신한다(폴링 아님).
  $effect(() => {
    liveEvents.version;                   // 의존성 등록
    const ev = liveEvents.last;
    if (!ev) return;
    const mine = ev.type === 'sync.finished'
      || (ev.type === 'run.finished' && ev.payload?.document_id === id);
    if (mine) load();
  });

  async function collect() {
    busy = true;
    try {
      await post(`/api/sources/${id}/collect`, {});
      toast('수집을 시작했습니다. 완료되면 자동으로 갱신됩니다.', 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function checkStatus() {
    busy = true;
    try {
      const r = await get(`/api/sources/${id}/runs/latest`);
      toast(`최근 수집 상태: ${r.status}`, 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function save() {
    try {
      await post(`/api/sources/${id}/update`, {
        name: edit.name, brand: edit.brand, memo: edit.memo,
        conf: Number(edit.conf), dpi: Number(edit.dpi), pages: edit.pages,
      });
      editing = false;
      await load();
      await loadSources();
      toast('저장했습니다', 'success');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function archive() {
    if (!confirm('이 문서를 보관 처리할까요? 수집된 이미지와 이력은 남습니다.')) return;
    try {
      await post(`/api/sources/${id}/archive`);
      await loadSources();
      navigate('#/sources');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  async function reset() {
    const f = doc.funnel;
    let msg = `이 문서의 수집 결과를 모두 지웁니다 (추출 ${f.extracted}장). `
      + '문서·설정은 남아 바로 재수집할 수 있습니다.';
    if (f.training > 0) msg += `\n\n⚠️ 학습 승급된 ${f.training}장도 함께 삭제됩니다.`;
    if (!confirm(msg)) return;
    busy = true;
    try {
      const r = await post(`/api/sources/${id}/reset`);
      toast(`수집 초기화 — ${r.deleted_images}장 삭제`, 'success');
      await load();
      await loadSources();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

{#if !doc}
  <p class="label">불러오는 중…</p>
{:else}
  <a href="#/sources" class="label">← 소스</a>

  <h2>{doc.name}</h2>
  <div class="label url">{doc.url}</div>
  <div class="label">
    브랜드 <b>{doc.brand}</b> · 등록 {dateTime(doc.created_at)}
    · 마지막 수집 {dateTime(doc.runs[0]?.started_at)}
    {#if doc.runs[0]}<StatusBadge status={doc.runs[0].status} />{/if}
    {#if doc.status === 'archived'}<b class="archived">보관됨</b>{/if}
  </div>

  <div class="funnel">
    {#if running}
      <div class="progress"><span></span></div>
      <div class="label">수집 중… 완료되면 자동으로 채워집니다</div>
    {:else}
      <FunnelBar funnel={doc.funnel} height={14} />
    {/if}
  </div>

  <div class="actions">
    <button class="primary" onclick={collect} disabled={busy}>수집 실행</button>
    <button onclick={checkStatus} disabled={busy}>상태 확인</button>
    <a class="btn" href="{settings.FIFTYONE_URL}/datasets/drheri/samples?view=doc-{doc.id}"
       target="_blank" rel="noreferrer">FiftyOne 에서 이 문서만 보기</a>
    <button onclick={() => (editing = !editing)}>{editing ? '취소' : '수정'}</button>
    <button onclick={reset} disabled={busy} class="danger">수집 초기화</button>
    <button onclick={archive}>보관</button>
  </div>

  {#if editing}
    <div class="edit">
      <div class="row">
        <div><div class="label">이름</div><input bind:value={edit.name} /></div>
        <div><div class="label">브랜드</div><input bind:value={edit.brand} /></div>
      </div>
      <div class="row">
        <div><div class="label">conf</div><input bind:value={edit.conf} /></div>
        <div><div class="label">dpi</div><input bind:value={edit.dpi} /></div>
        <div><div class="label">페이지</div><input bind:value={edit.pages} placeholder="예: 12-26, 30" /></div>
      </div>
      <div class="label">메모</div>
      <input bind:value={edit.memo} />
      <div class="actions"><button class="primary" onclick={save}>저장</button></div>
    </div>
  {:else if doc.memo}
    <p class="memo">{doc.memo}</p>
  {/if}

  <h3>수집 이력</h3>
  <RunTable runs={doc.runs} dagsterBase={settings.DAGSTER_URL} />
  <p class="label">같은 이미지는 content_hash 로 중복 제거됩니다 — 재수집해도 퍼널이 부풀지 않습니다.</p>
{/if}

<style>
  h2 { font-size: 16px; margin: 10px 0 2px; }
  h3 { font-size: 13px; margin: 20px 0 6px; }
  .url { word-break: break-all; }
  .funnel { margin: 14px 0; max-width: 620px; }
  /* 진행 중 인디케이터 — 좌우로 흐르는 막대(결정 불가 상태). 빈 퍼널과 헷갈리지 않게. */
  .progress { height: 14px; border-radius: 4px; background: var(--pending); overflow: hidden; }
  .progress span { display: block; width: 35%; height: 100%; border-radius: 4px;
                   background: var(--accent); animation: slide 1.2s ease-in-out infinite; }
  @keyframes slide {
    0%   { margin-left: -35%; }
    100% { margin-left: 100%; }
  }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; align-items: center; }
  .btn { padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px;
         color: var(--text); text-decoration: none; }
  .edit { border: 1px solid var(--border); border-radius: 6px; padding: 12px; max-width: 620px; }
  .row { display: flex; gap: 6px; margin-bottom: 6px; }
  .row > * { flex: 1; }
  .memo { color: var(--muted); }
  .archived { color: var(--rejected); margin-left: 6px; }
  button.danger { color: var(--rejected); border-color: var(--rejected); }
</style>
