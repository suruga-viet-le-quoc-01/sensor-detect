<script setup>
import { ref, watch } from "vue";

import { fetchSessions } from "@/lib/api.js";

const props = defineProps({
  machineId: { type: String, required: true },
  date: { type: String, required: true },
});

defineEmits(["close"]);

const END_REASON_LABEL = {
  left: "退席",
  shift_end: "終業",
  signal_lost: "信号途絶",
  error: "エラー",
};

const rows = ref([]);
const errorMessage = ref("");

async function load() {
  errorMessage.value = "";
  try {
    rows.value = await fetchSessions(props.machineId, props.date);
  } catch (err) {
    errorMessage.value = err.message;
  }
}

watch([() => props.machineId, () => props.date], load, { immediate: true });
</script>

<template>
  <section class="card session-list">
    <div class="header-row">
      <h2>{{ machineId }} のセッション ({{ date }})</h2>
      <button class="btn" @click="$emit('close')">戻る</button>
    </div>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-else-if="rows.length === 0" class="empty">この日はセッションがありません。</p>

    <table v-else>
      <thead>
        <tr>
          <th>開始</th>
          <th>終了</th>
          <th>時間 (分)</th>
          <th>終了理由</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(s, i) in rows" :key="i">
          <td>{{ new Date(s.start_time).toLocaleString("ja-JP") }}</td>
          <td>{{ s.end_time ? new Date(s.end_time).toLocaleString("ja-JP") : "-" }}</td>
          <td>{{ s.duration_min }}</td>
          <td>{{ END_REASON_LABEL[s.end_reason] ?? s.end_reason }}</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
  .session-list {
    margin-bottom: 20px;
  }

  .header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    margin-bottom: 16px;
  }

  h2 {
    font-size: 15px;
    margin: 0;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .error-banner {
    color: var(--danger);
    background: var(--danger-bg);
    border: 1px solid #4a2226;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 0;
    font-size: 13px;
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    text-align: left;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
    padding: 6px 10px;
  }

  td {
    padding: 8px 10px;
    border-top: 1px solid var(--border);
    font-size: 13px;
  }
</style>
