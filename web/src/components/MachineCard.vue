<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

const props = defineProps({
  machineId: { type: String, required: true },
  presentNow: { type: Boolean, required: true },
  sensorOk: { type: Boolean, required: true },
  lastSeen: { type: String, default: null }, // ISO timestamp or null
  sessionStart: { type: String, default: null }, // ISO start of currently-open session, or null
  presentMin: { type: Number, default: 0 }, // today's CLOSED-session total present minutes
  occupancyPct: { type: Number, default: 0 },
});

const emit = defineEmits(["select"]);

// If no heartbeat has arrived for this long, the reader is effectively offline (crashed, stopped,
// or the machine PC is off). Its present_now / session_start in Oracle are then stale and must not
// be trusted -- otherwise a machine left "present" reads as occupied forever and its open-session
// timer keeps ticking (the "97h在席中" bug). The heartbeat writes every ~5s, so 60s = many misses.
const STALE_AFTER_MS = 60_000;

// Ticks every second so the relative "◯秒前" label stays live without needing a fresh fetch.
const now = ref(Date.now());
let timer = null;
onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
});
onUnmounted(() => clearInterval(timer));

const lastSeenMs = computed(() => (props.lastSeen ? new Date(props.lastSeen).getTime() : null));

// Stale = no recent heartbeat -> treat status as unknown/offline, not "present".
const isStale = computed(() => lastSeenMs.value === null || now.value - lastSeenMs.value > STALE_AFTER_MS);

// Only trust "present" when the data is fresh.
const isPresent = computed(() => props.presentNow && !isStale.value);

const relativeLastSeen = computed(() => {
  if (lastSeenMs.value === null) return "受信履歴なし";

  const diffS = Math.max(0, Math.round((now.value - lastSeenMs.value) / 1000));
  if (diffS < 60) return `${diffS}秒前`;
  if (diffS < 3600) return `${Math.floor(diffS / 60)}分前`;
  return `${Math.floor(diffS / 3600)}時間前`;
});

// Closed-session total (from FTE) plus the currently-open session's live elapsed time. The open
// portion only counts while the machine is actually present AND fresh -- a stale open session
// (reader died without closing it) must NOT keep accumulating hours.
const workedTimeLabel = computed(() => {
  let totalMin = props.presentMin;

  if (isPresent.value && props.sessionStart) {
    const openMin = (now.value - new Date(props.sessionStart).getTime()) / 60000;
    if (openMin > 0) totalMin += openMin;
  }

  const rounded = Math.round(totalMin);
  const hours = Math.floor(rounded / 60);
  const minutes = rounded % 60;
  return hours > 0 ? `${hours}時間${minutes}分` : `${minutes}分`;
});
</script>

<template>
  <button class="card machine-card" :class="{ present: isPresent, stale: isStale }" @click="emit('select', machineId)">
    <div class="top-row">
      <span class="machine-id">{{ machineId }}</span>
      <span
        class="sensor-dot"
        :class="isStale ? 'warn' : sensorOk ? 'ok' : 'warn'"
        :title="isStale ? 'オフライン（受信なし）' : sensorOk ? '正常' : '警告'"
      ></span>
    </div>

    <div class="presence-badge" :class="isStale ? 'offline' : isPresent ? 'present' : 'absent'">
      {{ isStale ? "オフライン" : isPresent ? "在席中" : "不在" }}
    </div>

    <p class="last-seen">最終受信: {{ relativeLastSeen }}</p>

    <div class="worked-time">
      <span class="label">本日の稼働時間</span>
      <span class="value">{{ workedTimeLabel }}</span>
    </div>

    <div class="bar-track">
      <div class="bar-fill" :style="{ width: Math.min(100, occupancyPct) + '%' }"></div>
    </div>
    <p class="occupancy">稼働率 {{ occupancyPct }}%</p>
  </button>
</template>

<style scoped>
  .machine-card {
    display: block;
    width: 100%;
    text-align: left;
    font: inherit;
    color: inherit;
    cursor: pointer;
    border: 1px solid var(--border);
    transition: border-color 0.15s;
  }

  .machine-card:hover {
    border-color: var(--accent);
  }

  .machine-card.present {
    border-color: rgba(96, 165, 250, 0.4);
  }

  .top-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
  }

  .machine-id {
    font-weight: 700;
    font-size: 15px;
  }

  .sensor-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  .sensor-dot.ok {
    background: var(--success);
    box-shadow: 0 0 6px var(--success);
  }

  .sensor-dot.warn {
    background: var(--danger);
    box-shadow: 0 0 6px var(--danger);
  }

  .presence-badge {
    display: inline-block;
    font-size: 14px;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 999px;
    margin-bottom: 10px;
  }

  .presence-badge.present {
    background: rgba(96, 165, 250, 0.18);
    color: #60a5fa;
  }

  .presence-badge.absent {
    background: var(--surface-2);
    color: var(--text-muted);
  }

  .presence-badge.offline {
    background: var(--danger-bg);
    color: var(--danger);
  }

  .machine-card.stale {
    opacity: 0.7;
  }

  .last-seen {
    font-size: 12px;
    color: var(--text-muted);
    margin: 0 0 16px;
  }

  .worked-time {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 8px;
  }

  .worked-time .label {
    font-size: 12px;
    color: var(--text-muted);
  }

  .worked-time .value {
    font-size: 20px;
    font-weight: 700;
    color: var(--text);
  }

  .bar-track {
    height: 6px;
    border-radius: 999px;
    background: var(--surface-2);
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 999px;
    background: #60a5fa;
  }

  .occupancy {
    font-size: 11px;
    color: var(--text-muted);
    margin: 6px 0 0;
  }
</style>
