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

    <div class="label">기본 수집 설정</div>
    <div class="row">
      <input bind:value={form.conf} placeholder="conf" />
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
</style>
