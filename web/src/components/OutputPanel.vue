<script setup>
import { computed, onUnmounted, ref, watch } from "vue";

const props = defineProps({
  frame: { type: Object, default: null },
  maxDistanceCm: { type: Number, default: 600 },
});

const GATE_COUNT = 9;

// How long the banner keeps showing "在席中" after the sensor last reported presence, in seconds,
// operator-adjustable at runtime via the input below. This is a DISPLAY-ONLY smoothing so a
// stationary person (whose movement energy briefly drops to zero) doesn't make the banner
// flicker. It does NOT touch the recorded data -- session/FTE logic has its own debounce in
// src/session/state_machine.py.
const holdSeconds = ref(3);

// target_state bit0 = moving present, bit1 = stationary present (Table 14). Kept per-channel
// (raw, un-held) for the two "Detected" badges below, which are diagnostic during tuning.
const movingDetected = computed(() => ((props.frame?.targetState ?? 0) & 0x01) !== 0);
const staticDetected = computed(() => ((props.frame?.targetState ?? 0) & 0x02) !== 0);

// Raw combined presence straight from the frame: target_state in {1,2,3} (moving OR stationary),
// same rule the production reader uses -- not movement-only.
const rawPresent = computed(() => props.frame?.present === true);

// Held/smoothed presence actually shown in the banner. Goes true instantly, but waits HOLD_MS of
// continuous absence before going false.
const displayedPresent = ref(false);
let offTimer = null;

watch(rawPresent, (present) => {
  if (present) {
    if (offTimer) {
      clearTimeout(offTimer);
      offTimer = null;
    }
    displayedPresent.value = true;
  } else if (displayedPresent.value && offTimer === null) {
    offTimer = setTimeout(() => {
      displayedPresent.value = false;
      offTimer = null;
    }, Math.max(0, holdSeconds.value) * 1000);
  }
});

onUnmounted(() => {
  if (offTimer) clearTimeout(offTimer);
});

function pct(value, max) {
  return Math.max(0, Math.min(100, (value / max) * 100));
}

function movingEnergyAt(gateIndex) {
  const arr = props.frame?.movingGateEnergies;
  return arr && gateIndex < arr.length ? arr[gateIndex] : null;
}

function staticEnergyAt(gateIndex) {
  const arr = props.frame?.staticGateEnergies;
  return arr && gateIndex < arr.length ? arr[gateIndex] : null;
}
</script>

<template>
  <section class="card output-panel">
    <h2>Output</h2>

    <!-- Combined presence (target_state in {1,2,3}, moving OR stationary), same rule the
         production reader uses, plus a display-only hold smoothing so a still person doesn't
         make the banner flicker. Does not affect recorded data. -->
    <div class="presence-row">
      <div class="presence-banner" :class="displayedPresent ? 'present' : 'absent'">
        <span class="dot"></span>
        {{ displayedPresent ? "在席中" : "検知なし" }}
      </div>
      <label class="hold-field">
        <span>表示保持 (秒)</span>
        <input v-model.number="holdSeconds" type="number" min="0" max="60" step="1" />
      </label>
    </div>

    <div class="metric">
      <span class="metric-label">Detection distance</span>
      <div class="metric-value blue">{{ frame?.detectionDistanceCm ?? "-" }}<small>cm</small></div>
      <div class="bar-track">
        <div class="bar-fill blue" :style="{ width: pct(frame?.detectionDistanceCm ?? 0, maxDistanceCm) + '%' }"></div>
      </div>
    </div>

    <div class="metric">
      <div class="metric-label-row">
        <span class="metric-label">Movement target</span>
        <span v-if="movingDetected" class="badge purple">Detected</span>
      </div>
      <div class="metric-value purple">{{ frame?.movingDistanceCm ?? "-" }}<small>cm</small></div>
      <div class="bar-track">
        <div class="bar-fill purple" :style="{ width: pct(frame?.movingDistanceCm ?? 0, maxDistanceCm) + '%' }"></div>
      </div>
    </div>

    <div class="metric">
      <div class="metric-label-row">
        <span class="metric-label">Stationary target</span>
        <span v-if="staticDetected" class="badge orange">Detected</span>
      </div>
      <div class="metric-value orange">{{ frame?.staticDistanceCm ?? "-" }}<small>cm</small></div>
      <div class="bar-track">
        <div class="bar-fill orange" :style="{ width: pct(frame?.staticDistanceCm ?? 0, maxDistanceCm) + '%' }"></div>
      </div>
    </div>

    <table class="gate-table">
      <thead>
        <tr>
          <th></th>
          <th>MOTION</th>
          <th>REST</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="gate in GATE_COUNT" :key="gate">
          <td class="gate-label">GATE {{ gate - 1 }}</td>
          <td>
            <div v-if="movingEnergyAt(gate - 1) !== null" class="cell">
              <span class="cell-value purple">{{ movingEnergyAt(gate - 1) }}</span>
              <div class="mini-bar-track">
                <div class="mini-bar-fill purple" :style="{ width: movingEnergyAt(gate - 1) + '%' }"></div>
              </div>
            </div>
            <span v-else class="dash">-</span>
          </td>
          <td>
            <div v-if="staticEnergyAt(gate - 1) !== null" class="cell">
              <span class="cell-value orange">{{ staticEnergyAt(gate - 1) }}</span>
              <div class="mini-bar-track">
                <div class="mini-bar-fill orange" :style="{ width: staticEnergyAt(gate - 1) + '%' }"></div>
              </div>
            </div>
            <span v-else class="dash">-</span>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
  .output-panel {
    margin-bottom: 0;
  }

  h2 {
    font-size: 15px;
    margin: 0 0 18px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .presence-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 20px;
  }

  .presence-banner {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 15px;
    font-weight: 700;
    padding: 12px 16px;
    border-radius: 12px;
    flex: 1;
  }

  .hold-field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 11px;
    color: var(--text-muted);
    flex-shrink: 0;
  }

  .hold-field input {
    width: 70px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }

  .presence-banner .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
  }

  .presence-banner.present {
    background: rgba(96, 165, 250, 0.15);
    color: #60a5fa;
  }

  .presence-banner.present .dot {
    background: #60a5fa;
    box-shadow: 0 0 8px #60a5fa;
  }

  .presence-banner.absent {
    background: var(--surface-2);
    color: var(--text-muted);
  }

  .presence-banner.absent .dot {
    background: var(--text-muted);
  }

  .metric {
    margin-bottom: 18px;
  }

  .metric-label,
  .metric-label-row {
    font-size: 13px;
    color: var(--text-muted);
  }

  .metric-label-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 2px;
  }

  .metric-value {
    font-size: 28px;
    font-weight: 700;
    line-height: 1.3;
  }

  .metric-value small {
    font-size: 14px;
    font-weight: 500;
    color: var(--text-muted);
    margin-left: 4px;
  }

  .metric-value.blue {
    color: #60a5fa;
  }

  .metric-value.purple {
    color: #c084fc;
  }

  .metric-value.orange {
    color: #fb923c;
  }

  .badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 999px;
  }

  .badge.purple {
    background: rgba(168, 85, 247, 0.18);
    color: #c084fc;
  }

  .badge.orange {
    background: rgba(249, 115, 22, 0.18);
    color: #fb923c;
  }

  .bar-track {
    height: 6px;
    border-radius: 999px;
    background: var(--surface-2);
    margin-top: 6px;
    overflow: hidden;
  }

  .bar-fill {
    height: 100%;
    border-radius: 999px;
  }

  .bar-fill.blue {
    background: #60a5fa;
  }

  .bar-fill.purple {
    background: #c084fc;
  }

  .bar-fill.orange {
    background: #fb923c;
  }

  .gate-table {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
  }

  .gate-table th {
    text-align: left;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
    padding: 6px 8px;
  }

  .gate-table td {
    padding: 6px 8px;
    border-top: 1px solid var(--border);
  }

  .gate-label {
    font-size: 12px;
    color: var(--text-muted);
    white-space: nowrap;
  }

  .cell-value {
    font-size: 13px;
    font-weight: 700;
    display: block;
  }

  .cell-value.purple {
    color: #c084fc;
  }

  .cell-value.orange {
    color: #fb923c;
  }

  .dash {
    color: var(--text-muted);
  }

  .mini-bar-track {
    height: 5px;
    width: 100px;
    max-width: 100%;
    border-radius: 999px;
    background: var(--surface-2);
    margin-top: 3px;
    overflow: hidden;
  }

  .mini-bar-fill {
    height: 100%;
    border-radius: 999px;
  }

  .mini-bar-fill.purple {
    background: #c084fc;
  }

  .mini-bar-fill.orange {
    background: #fb923c;
  }
</style>
