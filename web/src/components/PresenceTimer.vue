<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

const props = defineProps({
  frame: { type: Object, default: null },
  connected: { type: Boolean, default: false },
});

// Live, client-side sensor sanity check -- NOT the official recorded working time (that's the
// 監視 tab, computed from Oracle sessions). This just accumulates how long the sensor reports
// combined presence (target_state in {1,2,3}) since connecting, so an operator can stand in front
// and watch it count up, step away and watch it stop, and spot flicker via the current-state timer.

const totalPresentMs = ref(0);
const presentNow = ref(false);
const stateStartMs = ref(Date.now());
const nowTick = ref(Date.now());

let lastFrameMs = null;
let timer = null;

function reset() {
  totalPresentMs.value = 0;
  presentNow.value = false;
  stateStartMs.value = Date.now();
  lastFrameMs = null;
}

// Format milliseconds as H時間M分S秒 (dropping empty leading units).
function formatDuration(ms) {
  const total = Math.floor(ms / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}時間${m}分${s}秒`;
  if (m > 0) return `${m}分${s}秒`;
  return `${s}秒`;
}

const totalLabel = computed(() => formatDuration(totalPresentMs.value));
const stateSeconds = computed(() => Math.floor((nowTick.value - stateStartMs.value) / 1000));

watch(
  () => props.frame,
  (frame) => {
    const now = Date.now();
    // A null frame means the stream stalled (parent's watchdog cleared it) -- treat as absent so
    // the timer stops counting and doesn't freeze on the last "在席" state.
    const present = frame?.present === true;

    // Add the elapsed time of the interval that just ended if the sensor was present during it.
    // Cap the delta so a pause/gap (e.g. tab hidden) can't inflate the total.
    if (frame && lastFrameMs !== null && presentNow.value) {
      totalPresentMs.value += Math.min(now - lastFrameMs, 500);
    }
    lastFrameMs = frame ? now : null;

    if (present !== presentNow.value) {
      presentNow.value = present;
      stateStartMs.value = now;
    }
  },
);

watch(
  () => props.connected,
  (connected) => {
    if (!connected) reset();
  },
);

onMounted(() => {
  timer = setInterval(() => {
    nowTick.value = Date.now();
  }, 250);
});

onUnmounted(() => clearInterval(timer));
</script>

<template>
  <section class="card presence-timer">
    <div class="header">
      <h2>在席時間チェック (簡易・ライブ)</h2>
      <button class="btn" @click="reset">リセット</button>
    </div>

    <div class="rows">
      <div class="metric">
        <span class="label">累計在席時間</span>
        <span class="value">{{ totalLabel }}</span>
      </div>

      <div class="metric">
        <span class="label">現在の状態</span>
        <span class="state">
          <span class="badge" :class="presentNow ? 'present' : 'absent'">{{ presentNow ? "在席" : "不在" }}</span>
          <span class="dur">{{ stateSeconds }}秒</span>
        </span>
      </div>
    </div>

    <p class="note">
      センサーが報告する presence（移動+静止）をそのまま集計した確認用の値です。正式な稼働時間は監視タブ（Oracle 集計）を参照してください。
    </p>
  </section>
</template>

<style scoped>
  .presence-timer {
    margin-bottom: 16px;
  }

  .header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
  }

  h2 {
    font-size: 15px;
    margin: 0;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .rows {
    display: flex;
    gap: 40px;
    flex-wrap: wrap;
  }

  .metric {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .label {
    font-size: 12px;
    color: var(--text-muted);
  }

  .value {
    font-size: 28px;
    font-weight: 700;
    color: #60a5fa;
  }

  .state {
    display: flex;
    align-items: center;
    gap: 10px;
    height: 37px;
  }

  .badge {
    font-size: 14px;
    font-weight: 700;
    padding: 4px 14px;
    border-radius: 999px;
  }

  .badge.present {
    background: rgba(96, 165, 250, 0.18);
    color: #60a5fa;
  }

  .badge.absent {
    background: var(--surface-2);
    color: var(--text-muted);
  }

  .dur {
    font-size: 18px;
    font-weight: 600;
    color: var(--text);
  }

  .note {
    font-size: 11px;
    color: var(--text-muted);
    margin: 16px 0 0;
  }
</style>
