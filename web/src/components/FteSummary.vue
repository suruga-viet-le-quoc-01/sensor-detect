<script setup>
import { ref, watch } from "vue";

import { fetchFte } from "@/lib/api.js";

const props = defineProps({
  date: { type: String, required: true },
  machines: { type: Array, required: true }, // for the optional machine filter dropdown
});

const emit = defineEmits(["update:date"]);

const rows = ref([]);
const errorMessage = ref("");
const machineFilter = ref("");

async function load() {
  errorMessage.value = "";
  try {
    rows.value = await fetchFte(props.date, machineFilter.value || undefined);
  } catch (err) {
    errorMessage.value = err.message;
  }
}

watch([() => props.date, machineFilter], load, { immediate: true });
</script>

<template>
  <section class="card fte-summary">
    <div class="header-row">
      <h2>FTE・稼働率</h2>
      <div class="filters">
        <input
          :value="date"
          type="date"
          @input="emit('update:date', $event.target.value)"
        />
        <select v-model="machineFilter">
          <option value="">全機器</option>
          <option v-for="m in machines" :key="m.machine_id" :value="m.machine_id">{{ m.machine_id }}</option>
        </select>
      </div>
    </div>

    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
    <p v-else-if="rows.length === 0" class="empty">データがありません。</p>

    <table v-else>
      <thead>
        <tr>
          <th>機器</th>
          <th>在席時間 (分)</th>
          <th>シフト時間 (分)</th>
          <th>FTE</th>
          <th>稼働率</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.machine_id">
          <td class="machine-id">{{ r.machine_id }}</td>
          <td>{{ r.present_min }}</td>
          <td>{{ r.shift_min }}</td>
          <td class="fte">{{ r.fte }}</td>
          <td>{{ r.occupancy_pct }}%</td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
  .fte-summary {
    margin-bottom: 20px;
  }

  .header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
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

  .filters {
    display: flex;
    gap: 8px;
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

  .machine-id {
    font-weight: 700;
  }

  .fte {
    font-weight: 700;
    color: #60a5fa;
  }
</style>
