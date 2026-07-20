<script>
  import { post, get } from '../lib/api.js';
  import Modal from '../components/Modal.svelte';
  import { loadSources, toast } from '../lib/stores.svelte.js';
  import { navigate } from '../lib/router.svelte.js';

  let { onclose } = $props();

  let form = $state({ url: '', name: '', brand: 'Osstem', series: '',
                      conf: 0.35, dpi: 200, pages: '', memo: '' });
  let duplicate = $state(null);
  let saving = $state(false);

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
    <div class="label">카탈로그 PDF 주소</div>
    <input bind:value={form.url} onblur={checkUrl} placeholder="https://…/catalog.pdf" />
    {#if duplicate}
      <div class="warn">
        ⚠️ 이미 등록된 URL 입니다 —
        <a href="#/sources/{duplicate.id}" onclick={onclose}>{duplicate.name} 보기 →</a>
      </div>
    {/if}

    <div class="label">이름 <span>(비우면 주소의 파일명)</span></div>
    <input bind:value={form.name} />

    <div class="row">
      <div><div class="label">브랜드</div><input bind:value={form.brand} /></div>
      <div><div class="label">기본 시리즈</div><input bind:value={form.series} placeholder="비우면 미지정" /></div>
    </div>

    <div class="label">기본 수집 설정</div>
    <div class="row">
      <input bind:value={form.conf} placeholder="conf" />
      <input bind:value={form.dpi} placeholder="dpi" />
      <input bind:value={form.pages} placeholder="페이지 (비우면 전체)" />
    </div>

    <div class="label">메모</div>
    <input bind:value={form.memo} placeholder="예: TS·GS 혼재. 10~16p 가 상세" />

    <div class="actions">
      <button class="primary" disabled={saving || !form.url.trim() || !!duplicate}
              onclick={() => save(false)}>등록</button>
      <button disabled={saving || !form.url.trim() || !!duplicate}
              onclick={() => save(true)}>등록하고 바로 수집</button>
    </div>
  {/snippet}
</Modal>

<style>
  .label { margin: 10px 0 4px; }
  .row { display: flex; gap: 6px; }
  .row > * { flex: 1; }
  .warn { margin-top: 6px; padding: 6px 8px; font-size: 11px; border-radius: 4px;
          background: #fffbeb; border: 1px solid #fde68a; color: #b45309; }
  .actions { display: flex; gap: 6px; margin-top: 14px; }
</style>
