<script>
  import { get } from '../lib/api.js';
  import FunnelBar from '../components/FunnelBar.svelte';
  import StatusBadge from '../components/StatusBadge.svelte';
  import { dateTime, num } from '../lib/format.js';
  import { toast } from '../lib/stores.svelte.js';

  let data = $state(null);

  $effect(() => {
    get('/api/overview').then((d) => (data = d)).catch((e) => toast(e.message, 'error'));
  });
</script>

<h2>현황</h2>

{#if !data}
  <p class="label">불러오는 중…</p>
{:else}
  <div class="funnel"><FunnelBar funnel={data.funnel} height={14} /></div>

  <div class="label">
    FiftyOne: {data.services.fiftyone.ok ? '정상' : `이상 — ${data.services.fiftyone.detail}`}
    (포트 {data.services.fiftyone.port})
  </div>

  <h3>최근 수집</h3>
  <table>
    <thead><tr><th>일시</th><th>문서</th><th>상태</th><th>검출</th></tr></thead>
    <tbody>
      {#each data.recent_runs as r (r.id)}
        <tr>
          <td>{dateTime(r.started_at)}</td>
          <td><a href="#/sources/{r.document_id}">{r.document_name}</a></td>
          <td><StatusBadge status={r.status} /></td>
          <td class="num">{num(r.extracted)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  h3 { font-size: 13px; margin: 20px 0 6px; }
  .funnel { max-width: 620px; margin-bottom: 10px; }
</style>
