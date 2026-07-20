<script>
  import StatusBadge from './StatusBadge.svelte';
  import { dateTime, num } from '../lib/format.js';

  let { runs, dagsterBase } = $props();
</script>

{#if runs.length === 0}
  <p class="label">수집 이력이 없습니다.</p>
{:else}
  <table>
    <thead>
      <tr><th>일시</th><th>설정</th><th>상태</th><th>추출</th><th></th></tr>
    </thead>
    <tbody>
      {#each runs as r (r.id)}
        <tr>
          <td>{dateTime(r.started_at)}</td>
          <td class="label">conf {r.conf} · dpi {r.dpi} · {r.pages || '전체'}</td>
          <td>
            <StatusBadge status={r.status} />
            {#if r.error}<span class="label" title={r.error}>· {r.error.slice(0, 40)}</span>{/if}
          </td>
          <td class="num">{num(r.extracted)}</td>
          <td>
            {#if r.dagster_run_id}
              <a href="{dagsterBase}/runs/{r.dagster_run_id}" target="_blank" rel="noreferrer">로그</a>
            {/if}
          </td>
        </tr>
      {/each}
    </tbody>
  </table>
{/if}
