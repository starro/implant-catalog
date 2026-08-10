<script>
  import { post, get } from '../lib/api.js';
  import Modal from '../components/Modal.svelte';
  import { loadSources, toast } from '../lib/stores.svelte.js';
  import { navigate } from '../lib/router.svelte.js';

  let { onclose } = $props();

  let form = $state({ url: '', name: '', brand: '', series: '',
                      conf: 0.35, dpi: 200, pages: '', memo: '' });
  let duplicate = $state(null);
  let saving = $state(false);
  let uploading = $state(false);
  let dragover = $state(false);

  // NAS 브라우저 — 호스트에 마운트된 카탈로그 루트(<브랜드>/<pdf>)를 탐색해 선택한다.
  let nas = $state({ open: false, avail: true, path: '', dirs: [], files: [], loading: false });
  // 선택한 NAS PDF — 총 페이지 수를 보여줘 페이지 범위 지정을 돕는다.
  let picked = $state(null);   // { name, pages: number|null }

  function fmtSize(n) {
    if (!n) return '';
    const mb = n / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`;
  }

  async function nasBrowse(path = '') {
    nas.loading = true;
    try {
      const r = await get('/api/nas/browse', { path });
      nas.avail = r.available; nas.path = r.path; nas.dirs = r.dirs; nas.files = r.files;
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      nas.loading = false;
    }
  }

  function nasToggle() {
    nas.open = !nas.open;
    if (nas.open && !nas.dirs.length && !nas.files.length) nasBrowse('');
  }

  function nasUp() {
    const parts = nas.path.split('/').filter(Boolean);
    parts.pop();
    nasBrowse(parts.join('/'));
  }

  async function nasPick(file) {
    form.url = file.abs;                              // 호스트 절대경로 — 수집 시 docker cp 주입
    const brandSeg = nas.path.split('/').filter(Boolean)[0];   // 최상위 폴더 = 브랜드
    if (brandSeg) form.brand = brandSeg;
    if (!form.name.trim()) form.name = file.name;
    picked = { name: file.name, pages: null };
    await checkUrl();
    try {                                             // 총 페이지 수 조회(선택은 이거 없이도 유효)
      const rel = (nas.path ? nas.path + '/' : '') + file.name;
      const info = await get('/api/nas/pdfinfo', { path: rel });
      picked = { name: file.name, pages: info.pages };
    } catch (e) {
      picked = { name: file.name, pages: null };
    }
    toast('NAS 파일을 선택했습니다', 'success');
  }

  async function checkUrl() {
    duplicate = null;
    if (!form.url.trim()) return;
    try {
      const r = await get('/api/sources/check', { url: form.url });
      if (r.exists) duplicate = r.document;
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  // 드롭/선택된 PDF 를 서버로 업로드하고 반환 경로를 주소 칸에 채운다.
  async function uploadFile(file) {
    if (!file) return;
    if (!form.brand.trim()) { toast('브랜드를 먼저 입력하세요', 'error'); return; }
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast('PDF 파일만 업로드할 수 있습니다', 'error'); return;
    }
    uploading = true;
    duplicate = null;
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('brand', form.brand);
      const res = await fetch('/api/uploads', { method: 'POST', body: fd });
      const body = await res.json();
      if (!body.ok) throw new Error(body.error?.message || '업로드 실패');
      form.url = body.data.path;
      if (!form.name.trim()) form.name = body.data.filename;
      await checkUrl();
      toast('업로드 완료', 'success');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      uploading = false;
    }
  }

  function onDrop(e) {
    e.preventDefault();
    dragover = false;
    const file = e.dataTransfer?.files?.[0];
    uploadFile(file);
  }

  function onPick(e) {
    uploadFile(e.target.files?.[0]);
    e.target.value = '';                 // 같은 파일 다시 선택 가능하게
  }

  async function save(andCollect) {
    saving = true;
    try {
      const { id } = await post('/api/sources', {
        url: form.url, name: form.name, brand: form.brand,
        series: form.series || '_unknown', conf: Number(form.conf),
        dpi: Number(form.dpi), pages: form.pages, memo: form.memo,
      });
      await loadSources();
      onclose();
      if (andCollect) {
        await post(`/api/sources/${id}/collect`, {});
        toast('수집을 시작했습니다', 'info');
      }
      navigate(`#/sources/${id}`);
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      saving = false;
    }
  }
</script>

<Modal title="새 카탈로그 등록" {onclose}>
  {#snippet children()}
    <div class="row">
      <div>
        <div class="label">브랜드 <span class="req">*</span></div>
        <input bind:value={form.brand} placeholder="예: Osstem, ADIN, Straumann"
               class:missing={!form.brand.trim()} />
      </div>
      <div><div class="label">기본 시리즈</div><input bind:value={form.series} placeholder="비우면 미지정" /></div>
    </div>

    <div class="drop" class:over={dragover}
         ondragover={(e) => { e.preventDefault(); dragover = true; }}
         ondragleave={() => (dragover = false)}
         ondrop={onDrop}
         role="button" tabindex="0">
      {#if uploading}
        업로드 중…
      {:else}
        PDF 를 여기로 드롭 <span class="muted">→ {form.brand.trim() || '브랜드 미정'}/ 폴더로 업로드</span>
        <label class="pick">파일 선택<input type="file" accept=".pdf,application/pdf" onchange={onPick} hidden /></label>
      {/if}
    </div>

    <div class="nashead">
      <span class="label">또는 NAS 에서 선택 <span>(이미 NAS 에 있는 파일)</span></span>
      <button type="button" class="naslink" onclick={nasToggle}>{nas.open ? '닫기' : 'NAS 열기'}</button>
    </div>
    {#if nas.open}
      <div class="nas">
        {#if !nas.avail}
          <div class="muted">NAS 가 마운트되어 있지 않습니다 (/mnt/nas). 관리자에게 문의하세요.</div>
        {:else}
          <div class="crumb">
            <button type="button" onclick={() => nasBrowse('')}>루트</button>
            {#if nas.path}<span>/ {nas.path}</span>
              <button type="button" onclick={nasUp}>↑ 상위</button>{/if}
          </div>
          {#if nas.loading}<div class="muted">불러오는 중…</div>{/if}
          <ul class="naslist">
            {#each nas.dirs as d (d.path)}
              <li><button type="button" onclick={() => nasBrowse(d.path)}>📁 {d.name}</button></li>
            {/each}
            {#each nas.files as f (f.abs)}
              <li><button type="button" class="pdf" onclick={() => nasPick(f)}>📄 {f.name}
                <span class="muted">{fmtSize(f.size)}</span></button></li>
            {/each}
          </ul>
          {#if !nas.loading && !nas.dirs.length && !nas.files.length}
            <div class="muted">(비어 있음 · PDF 없음)</div>
          {/if}
        {/if}
      </div>
    {/if}

    {#if picked}
      <div class="picked">
        <div>📄 <b>{picked.name}</b>
          {#if picked.pages}<span class="tot">· 총 {picked.pages}페이지</span>{/if}</div>
        <div class="prow">
          <span class="label">수집할 페이지</span>
          <input bind:value={form.pages}
                 placeholder={picked.pages ? `예: 1-${picked.pages} 중 12-26, 30 · 비우면 전체` : '예: 12-26, 30 · 비우면 전체'} />
        </div>
      </div>
    {/if}

    <div class="label">카탈로그 PDF 주소 또는 파일 드롭</div>
    <input bind:value={form.url} onblur={checkUrl} placeholder="https://…/catalog.pdf" />
    {#if duplicate}
      <div class="warn">
        ⚠️ 이미 등록된 URL 입니다 —
        <a href="#/sources/{duplicate.id}" onclick={onclose}>{duplicate.name} 보기 →</a>
      </div>
    {/if}

    <div class="label">이름 <span>(비우면 주소의 파일명)</span></div>
    <input bind:value={form.name} />

    <div class="label">기본 수집 설정 <span>(검출 임계값 = 낮을수록 더 검출)</span></div>
    <div class="row">
      <input bind:value={form.conf} placeholder="검출 임계값 (예: 0.3)" />
      <input bind:value={form.dpi} placeholder="dpi" />
      <input bind:value={form.pages} placeholder="페이지 예: 12-26, 30 (비우면 전체)" />
    </div>

    <div class="label">메모</div>
    <input bind:value={form.memo} placeholder="예: TS·GS 혼재. 10~16p 가 상세" />

    <div class="actions">
      <button class="primary" disabled={saving || uploading || !form.url.trim() || !form.brand.trim() || !!duplicate}
              onclick={() => save(false)}>등록</button>
      <button disabled={saving || uploading || !form.url.trim() || !form.brand.trim() || !!duplicate}
              onclick={() => save(true)}>등록하고 바로 수집</button>
    </div>
  {/snippet}
</Modal>

<style>
  .label { margin: 10px 0 4px; }
  .label span { color: var(--muted); font-size: 11px; }
  .label .req { color: var(--rejected); }
  input.missing { border-color: var(--rejected); }
  .row { display: flex; gap: 6px; }
  .row > * { flex: 1; }
  .drop { margin-top: 10px; padding: 14px; border: 1px dashed var(--border);
          border-radius: 6px; text-align: center; color: var(--muted); font-size: 12px; }
  .drop.over { border-color: var(--accent); color: var(--text); }
  .drop .muted { color: var(--muted); }
  .drop .pick { margin-left: 8px; color: var(--accent); cursor: pointer; text-decoration: underline; }
  .warn { margin-top: 6px; padding: 6px 8px; font-size: 11px; border-radius: 4px;
          background: #fffbeb; border: 1px solid #fde68a; color: #b45309; }
  .actions { display: flex; gap: 6px; margin-top: 14px; }
  .nashead { display: flex; align-items: center; justify-content: space-between; }
  .naslink { font-size: 11px; color: var(--accent); background: none; border: none;
             cursor: pointer; text-decoration: underline; padding: 0; }
  .nas { margin-top: 6px; border: 1px solid var(--border); border-radius: 6px; padding: 8px; }
  .crumb { display: flex; align-items: center; gap: 6px; font-size: 11px;
           color: var(--muted); margin-bottom: 6px; }
  .crumb button { font-size: 11px; background: none; border: none; color: var(--accent);
                  cursor: pointer; padding: 0; text-decoration: underline; }
  .naslist { list-style: none; margin: 0; padding: 0; max-height: 220px; overflow-y: auto; }
  .naslist li button { width: 100%; text-align: left; background: none; border: none;
                       padding: 4px 6px; font-size: 12px; cursor: pointer; border-radius: 4px;
                       color: var(--text); }
  .naslist li button:hover { background: var(--pending); }
  .naslist li button.pdf { color: var(--accent); }
  .nas .muted { color: var(--muted); font-size: 11px; }
  .picked { margin-top: 8px; padding: 8px 10px; border: 1px solid var(--accent);
            border-radius: 6px; background: color-mix(in srgb, var(--accent) 6%, transparent); }
  .picked .tot { color: var(--muted); font-size: 12px; margin-left: 4px; }
  .prow { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
  .prow .label { margin: 0; white-space: nowrap; }
  .prow input { flex: 1; }
</style>
