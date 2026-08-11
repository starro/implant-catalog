<script>
  import { get, post } from '../lib/api.js';
  import FunnelBar from '../components/FunnelBar.svelte';
  import RunTable from '../components/RunTable.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { ENGINE_LABELS } from '../components/engine_labels.js';
  import { dateTime, duration } from '../lib/format.js';
  import { engine, liveEvents, loadSources, toast } from '../lib/stores.svelte.js';

  let { id } = $props();

  let doc = $state(null);
  let busy = $state(false);
  let editing = $state(false);
  let edit = $state({ name: '', brand: '', memo: '', conf: 0.35, dpi: 200, pages: '' });
  let settings = $state({ FIFTYONE_URL: '' });
  let progress = $state({ done: 0, total: 0, crops: 0, phase: 'process' });   // 수집 중 실시간 진행

  // 최신 수집이 진행 중인가 — 진행 중엔 빈 단계별 현황 대신 인디케이터를 보여준다.
  let running = $derived(
    !!doc?.runs?.[0] && ['QUEUED', 'RUNNING'].includes(doc.runs[0].status),
  );

  // 수집 중이면 3초마다 진행상황을 가져온다(컨테이너 progress.json). GPU 안 씀.
  $effect(() => {
    if (!running) return;
    let alive = true;
    const tick = async () => {
      try {
        const p = await get(`/api/sources/${id}/runs/latest/progress`);
        if (alive) progress = p;
      } catch { /* 진행 파일 없거나 일시 오류 — 무시 */ }
    };
    tick();
    const t = setInterval(tick, 5000);          // 5초 — 페이지당 ~15초라 충분, docker exec cat 은 가벼움
    return () => { alive = false; clearInterval(t); };
  });

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
    // 수집할 페이지를 그 자리에서 지정 (기본값은 문서에 저장된 값). 취소하면 중단.
    const pages = prompt('수집할 페이지 (예: 12-26, 30 · 비우면 전체)', doc.default_pages || '');
    if (pages === null) return;
    busy = true;
    try {
      await post(`/api/sources/${id}/collect`, { pages });
      toast('수집을 시작했습니다. 완료되면 자동으로 갱신됩니다.', 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function cancelCollect() {
    if (!confirm('진행 중인 수집을 중단할까요? (컨테이너 프로세스까지 종료)')) return;
    busy = true;
    try {
      const r = await post(`/api/sources/${id}/collect/cancel`, {});
      toast(r.killed ? '수집을 중단했습니다.' : '진행 중인 프로세스가 없었습니다.', 'info');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function runSync() {
    // 이 문서(PDF)의 검수결과만 반영 → DB + training 승급. 결과 토스트는 SSE.
    busy = true;
    try {
      await post(`/api/sources/${id}/sync`, {});
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function runExport() {
    // 이 문서의 training 승급분만 내보내기 → export/doc-<id>/labels.tsv + manifest.jsonl
    busy = true;
    try {
      const r = await post(`/api/sources/${id}/export`, {});
      toast(`학습용 데이터 라벨 생성 완료 — ${r.rows}행 (${r.labels_tsv})`, 'success');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  // '이 문서만 보기' — 서버에서 세션 뷰를 doc-N 으로 확정한 뒤 FiftyOne 탭을 연다.
  // (URL ?view= 는 단일세션에서 이전 필터와 충돌 → 서버 session.view 세팅이 확실)
  async function viewInFiftyone() {
    try {
      await post(`/api/sources/${id}/fiftyone-view`);
    } catch (e) {
      toast(e.message, 'error');
    }
    window.open(`${settings.FIFTYONE_URL}/datasets/drheri`, 'fiftyone');
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

  async function reset() {
    const f = doc.funnel;
    let msg = `이 문서의 수집 결과를 모두 지웁니다 (검출 ${f.extracted}장). `
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
    {#if doc.runs[0]?.finished_at}
      <span class="label">· 완료 {dateTime(doc.runs[0].finished_at)}{#if duration(doc.runs[0].started_at, doc.runs[0].finished_at)} (소요 {duration(doc.runs[0].started_at, doc.runs[0].finished_at)}){/if}</span>
    {/if}
    {#if doc.status === 'archived'}<b class="archived">보관됨</b>{/if}
  </div>

  <div class="funnel">
    {#if running}
      {#if progress.total > 0}
        <div class="pbar"><span style="width: {Math.round(progress.done / progress.total * 100)}%"></span></div>
        <div class="label">
          {#if progress.phase === 'render'}렌더링 {progress.done}/{progress.total} 페이지
          {:else}페이지 {progress.done}/{progress.total} · 검출 {progress.crops}장{/if} (수집 중…)
        </div>
      {:else}
        <div class="progress"><span></span></div>
        <div class="label">수집 준비 중…</div>
      {/if}
    {:else}
      <FunnelBar funnel={doc.funnel} height={14} />
    {/if}
  </div>

  <div class="lifecycle">
    <section class="step">
      <div class="step-head"><span class="badge">1</span> 수집</div>
      <div class="step-body">
        <button onclick={() => (editing = !editing)}>{editing ? '취소' : '수집 설정 변경'}</button>
        <button class="primary" onclick={collect} disabled={busy || engine.status !== 'ready' || running}>수집 실행</button>
        {#if running}
          <button onclick={cancelCollect} disabled={busy} class="danger">수집 중단</button>
        {/if}
        <button onclick={reset} disabled={busy} class="danger">수집 초기화</button>
        {#if engine.status !== 'ready'}
          <span class="hint">엔진 준비 후 수집 가능 (현재: {ENGINE_LABELS[engine.status] ?? engine.status})</span>
        {/if}
      </div>
    </section>

    <section class="step">
      <div class="step-head"><span class="badge">2</span> 검수 (FiftyOne)</div>
      <div class="step-body">
        <button class="btn" onclick={viewInFiftyone} disabled={doc.funnel.extracted === 0}>수집확인(FiftyOne)</button>
        <button class="review" onclick={runSync} disabled={busy}>검수결과 반영</button>
      </div>
    </section>

    <section class="step">
      <div class="step-head"><span class="badge">3</span> 학습 라벨</div>
      <div class="step-body">
        <button class="train" onclick={runExport} disabled={busy}>학습용 데이터 라벨 생성</button>
      </div>
    </section>
  </div>

  {#if editing}
    <div class="edit">
      <div class="row">
        <div><div class="label">이름</div><input bind:value={edit.name} /></div>
        <div><div class="label">브랜드</div><input bind:value={edit.brand} /></div>
      </div>
      <div class="row">
        <div><div class="label">검출 임계값 <span>(낮을수록 더 검출)</span></div><input bind:value={edit.conf} /></div>
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
  <RunTable runs={doc.runs} />
{/if}

<style>
  h2 { font-size: 16px; margin: 10px 0 2px; }
  h3 { font-size: 13px; margin: 20px 0 6px; }
  .url { word-break: break-all; }
  .funnel { margin: 14px 0; max-width: 620px; }
  /* 진행 중 인디케이터 — 좌우로 흐르는 막대(결정 불가 상태). 빈 단계별 현황과 헷갈리지 않게. */
  /* 결정형 진행바 — 페이지 진행률(done/total) 을 실제 폭으로 표시 */
  .pbar { height: 14px; border-radius: 4px; background: var(--pending); overflow: hidden; }
  .pbar span { display: block; height: 100%; background: var(--accent);
               border-radius: 4px; transition: width 0.4s ease; }
  .progress { height: 14px; border-radius: 4px; background: var(--pending); overflow: hidden; }
  .progress span { display: block; width: 35%; height: 100%; border-radius: 4px;
                   background: var(--accent); animation: slide 1.2s ease-in-out infinite; }
  @keyframes slide {
    0%   { margin-left: -35%; }
    100% { margin-left: 100%; }
  }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin: 12px 0; align-items: center; }
  /* 라이프사이클 스테퍼 — 수집 → 검수 → 학습 라벨, 좌→우 진행 */
  .lifecycle { display: flex; gap: 10px; margin: 16px 0; flex-wrap: wrap; align-items: stretch; }
  .step { flex: 1 1 240px; border: 1px solid var(--border); border-radius: 10px;
          padding: 12px 14px 14px; display: flex; flex-direction: column; gap: 10px;
          position: relative; }
  /* 카드 사이 진행 화살표(넓을 때만) */
  .step:not(:last-child)::after {
    content: '›'; position: absolute; right: -10px; top: 50%; transform: translate(50%, -50%);
    color: var(--border); font-size: 20px; line-height: 1; z-index: 1;
  }
  .step-head { display: flex; align-items: center; gap: 8px; font-size: 12.5px; font-weight: 600;
               padding-bottom: 8px; border-bottom: 1px solid var(--border); }
  .badge { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
           border-radius: 50%; background: var(--accent); color: #fff; font-size: 12px;
           font-weight: 700; flex: none; }
  .step:nth-child(2) .badge { background: #d97706; }           /* 검수 — 앰버 */
  .step:nth-child(3) .badge { background: var(--training); }   /* 최종 산출(학습 라벨) */
  .step-body { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .step-body .hint { flex-basis: 100%; font-size: 11px; color: var(--muted); margin-top: 2px; }
  @media (max-width: 860px) { .step:not(:last-child)::after { display: none; } }
  .btn { padding: 6px 12px; border: 1px solid var(--border); border-radius: 4px;
         color: var(--text); text-decoration: none; background: none;
         cursor: pointer; font: inherit; }
  .edit { border: 1px solid var(--border); border-radius: 6px; padding: 12px; max-width: 620px; }
  .row { display: flex; gap: 6px; margin-bottom: 6px; }
  .row > * { flex: 1; }
  .memo { color: var(--muted); }
  .archived { color: var(--rejected); margin-left: 6px; }
  button.danger { color: var(--rejected); border-color: var(--rejected); }
  button.review { background: #d97706; border-color: #d97706; color: #fff; }
  button.train { background: var(--training); border-color: var(--training); color: #fff; }
</style>
