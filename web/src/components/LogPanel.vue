<script setup>
defineProps({
  entries: { type: Array, required: true }, // [{ ok, label, detail }]
});
</script>

<template>
  <section class="card log-panel">
    <h2>ログ</h2>
    <p v-if="entries.length === 0" class="empty">まだ操作はありません。</p>
    <ul v-else>
      <li v-for="(entry, i) in entries" :key="i" :class="{ ok: entry.ok, fail: !entry.ok }">
        <span class="mark">{{ entry.ok ? "✓" : "✗" }}</span>
        <span class="label">{{ entry.label }}</span>
        <span v-if="entry.detail" class="detail">{{ entry.detail }}</span>
      </li>
    </ul>
  </section>
</template>

<style scoped>
  .log-panel {
    margin-bottom: 16px;
  }

  h2 {
    font-size: 16px;
    margin: 0 0 12px;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 220px;
    overflow-y: auto;
    font-size: 13px;
  }

  li {
    padding: 6px 0;
    display: flex;
    gap: 10px;
    align-items: baseline;
    border-bottom: 1px solid var(--border);
  }

  li:last-child {
    border-bottom: none;
  }

  li.ok .mark {
    color: var(--success);
  }

  li.fail .mark {
    color: var(--danger);
  }

  .label {
    color: var(--text);
  }

  .detail {
    color: var(--text-muted);
    font-size: 12px;
  }
</style>
