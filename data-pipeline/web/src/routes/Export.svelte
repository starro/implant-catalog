<script>
  import { get, post } from '../lib/api.js';
  import { num } from '../lib/format.js';
  import { toast } from '../lib/stores.svelte.js';

  let dist = $state(null);
  let busy = $state(false);
  let result = $state(null);

  async function load() {
    try {
      dist = await get('/api/export/summary');
    } catch (e) {
      toast(e.message, 'error');
    }
  }

  $effect(() => { load(); });

  async function run() {
    busy = true;
    try {
      result = await post('/api/export');
      await load();
    } catch (e) {
      toast(e.message, 'error');
    } finally {
      busy = false;
    }
  }
</script>

<h2>학습데이터</h2>

<button class="primary" onclick={run} disabled={busy}>
  {busy ? '생성 중…' : 'DGX 내보내기 생성'}
</button>

{#if result}
  <p class="label">{result.rows}행 · {result.labels_tsv} · {result.manifest_jsonl}</p>
{/if}

{#if dist}
  <p class="label">학습 이미지 {num(dist.total)}장</p>
  <div class="cols">
    {#each [['브랜드', dist.brands], ['모델', dist.models]] as [title, rows] (title)}
      <div>
        <h3>{title}</h3>
        <table>
          <tbody>
            {#each rows.slice(0, 20) as r (r.name)}
              <tr><td>{r.name}</td><td class="num">{num(r.count)}</td></tr>
            {/each}
          </tbody>
        </table>
        {#if rows.length > 20}<p class="label">외 {rows.length - 20}종</p>{/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  h2 { font-size: 15px; margin: 0 0 12px; }
  h3 { font-size: 12px; margin: 14px 0 4px; color: var(--muted); }
  .cols { display: flex; gap: 24px; align-items: flex-start; }
  .cols > div { flex: 1; }
</style>
