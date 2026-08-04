<script setup>
import { computed, onUnmounted, ref, watch } from "vue";

import { fetchFte, fetchMachineStatus } from "@/lib/api.js";
import FteSummary from "@/components/FteSummary.vue";
import MachineCard from "@/components/MachineCard.vue";
import SessionList from "@/components/SessionList.vue";

const props = defineProps({
  active: { type: Boolean, required: true }, // only poll while this tab is actually visible
});

const STATUS_POLL_INTERVAL_MS = 3000;
// Today's worked-time-so-far doesn't need sub-second freshness like presence does -- poll it
// less often to keep load on the (potentially cached-but-still-real) FTE query lighter.
const FTE_POLL_INTERVAL_MS = 15000;

function todayLocalDate() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

const TODAY = todayLocalDate();

const statusList = ref([]);
const fteToday = ref([]);
const selectedDate = ref(TODAY); // drives the historical FteSummary/SessionList below, independent of "today"
const selectedMachineId = ref(null);
const errorMessage = ref("");

// One card per machine: live status (present/sensor/last_seen) merged with today's running
// worked-time total, per the user's request for a combined at-a-glance card view.
const cards = computed(() => {
  const fteByMachine = new Map(fteToday.value.map((row) => [row.machine_id, row]));

  return statusList.value.map((status) => {
    const fte = fteByMachine.get(status.machine_id);
    return {
      machineId: status.machine_id,
      presentNow: status.present_now,
      sensorOk: status.sensor_ok,
      lastSeen: status.last_seen,
      sessionStart: status.session_start,
      presentMin: fte?.present_min ?? 0,
      occupancyPct: fte?.occupancy_pct ?? 0,
    };
  });
});

async function pollStatus() {
  try {
    statusList.value = await fetchMachineStatus();
    errorMessage.value = "";
  } catch (err) {
    // Keep the last known statusList on screen (stale but visible) instead of blanking it --
    // docs/dashboard/rules.md: DB unreachable must show a banner, not crash/clear the view.
    errorMessage.value = err.message;
  }
}

async function pollFteToday() {
  try {
    fteToday.value = await fetchFte(TODAY);
  } catch {
    // Non-fatal: cards just fall back to presentMin=0/occupancy=0 until the next successful poll.
    // The status banner above already reports DB-unavailable; no need for a second banner here.
  }
}

let statusTimer = null;
let fteTimer = null;

watch(
  () => props.active,
  (active) => {
    if (active) {
      pollStatus();
      pollFteToday();
      statusTimer = setInterval(pollStatus, STATUS_POLL_INTERVAL_MS);
      fteTimer = setInterval(pollFteToday, FTE_POLL_INTERVAL_MS);
    } else {
      if (statusTimer) clearInterval(statusTimer);
      if (fteTimer) clearInterval(fteTimer);
      statusTimer = null;
      fteTimer = null;
    }
  },
  { immediate: true },
);

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer);
  if (fteTimer) clearInterval(fteTimer);
});

function onSelect(machineId) {
  selectedMachineId.value = selectedMachineId.value === machineId ? null : machineId;
}
</script>

<template>
  <div class="monitor-tab">
    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <p v-if="cards.length === 0" class="empty">登録された機器がありません。</p>
    <div v-else class="card-grid">
      <MachineCard
        v-for="c in cards"
        :key="c.machineId"
        :machine-id="c.machineId"
        :present-now="c.presentNow"
        :sensor-ok="c.sensorOk"
        :last-seen="c.lastSeen"
        :session-start="c.sessionStart"
        :present-min="c.presentMin"
        :occupancy-pct="c.occupancyPct"
        @select="onSelect"
      />
    </div>

    <FteSummary v-model:date="selectedDate" :machines="statusList" />

    <SessionList
      v-if="selectedMachineId"
      :machine-id="selectedMachineId"
      :date="selectedDate"
      @close="selectedMachineId = null"
    />
  </div>
</template>

<style scoped>
  .error-banner {
    color: var(--danger);
    background: var(--danger-bg);
    border: 1px solid #4a2226;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 0 0 20px;
    font-size: 13px;
  }

  .empty {
    font-size: 13px;
    color: var(--text-muted);
  }

  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 16px;
    margin-bottom: 20px;
  }
</style>
