<script>
  import { get, post } from '../lib/api.js';
  import { toast } from '../lib/stores.svelte.js';

  const FIELDS = [
    ['DEFAULT_CONF', '기본 conf'],
    ['DEFAULT_DPI', '기본 dpi'],
    ['FIFTYONE_URL', 'FiftyOne 주소'],
    ['FIFTYONE_SERVICE', 'FiftyOne systemd 서비스명'],
  ];

  let values = $state({});
  let dataRoot = $state('');
  let busy = $state(false);

  $effect(() => {
    get('/api/settings')
      .then((s) => { values = s; dataRoot = s.DATA_ROOT; })
      .catch((e) => toast(e.message, 'error'));
  });

  async function save() {
    busy = true;
    try {
      values = await post('/api/settings', values);
      toast('저장했습니다', 'success');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }

  async function restart() {
    busy = true;
    try {
      const r = await post('/api/fiftyone/restart');
      toast(r.ok ? `재기동 완료 (잔여 정리 ${r.orphans_killed}건)` : `재기동 실패: ${r.detail}`,
            r.ok ? 'success' : 'error');
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<h2>설정</h2>

{#each FIELDS as [key, label] (key)}
  <div class="label">{label}</div>
  <input bind:value={values[key]} />
{/each}

<div class="label">데이터 경로 (환경변수 DATA_ROOT 로만 변경)</div>
<input value={dataRoot} readonly />

<div class="actions">
  <button class="primary" onclick={save} disabled={busy}>저장</button>
  <button onclick={restart} disabled={busy}>FiftyOne 재기동</button>
</div>

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  .label { margin: 10px 0 4px; }
  input { max-width: 480px; }
  .actions { display: flex; gap: 6px; margin-top: 16px; }
</style>
