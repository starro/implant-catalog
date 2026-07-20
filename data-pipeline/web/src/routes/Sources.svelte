<script>
  import BrandGroup from '../components/BrandGroup.svelte';
  import NewSource from './NewSource.svelte';
  import { loadSources, sources } from '../lib/stores.svelte.js';

  let showNew = $state(false);
  $effect(() => { loadSources(); });
</script>

<header class="page">
  <h2>소스</h2>
  <button class="primary" onclick={() => (showNew = true)}>+ 새 카탈로그 등록</button>
</header>

{#if sources.loading}
  <p class="label">불러오는 중…</p>
{:else if sources.tree.length === 0}
  <p class="label">등록된 소스가 없습니다. 카탈로그 PDF 주소를 등록해 시작하세요.</p>
{:else}
  {#each sources.tree as g (g.brand_id)}
    <BrandGroup group={g} />
  {/each}
{/if}

{#if showNew}
  <NewSource onclose={() => (showNew = false)} />
{/if}

<style>
  .page { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
  h2 { font-size: 15px; margin: 0; }
</style>
