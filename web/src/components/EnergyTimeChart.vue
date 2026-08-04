<script setup>
import { computed, onUnmounted, ref, watch } from "vue";

import { pushSample } from "@/lib/energyHistory.js";

const props = defineProps({
  frame: { type: Object, default: null },
  connected: { type: Boolean, default: false },
});

// ~10 frames/s * 15s = 150 points. A shorter window spreads each sample out so the lines read as
// normal, legible zigzags instead of a dense compressed wall.
const MAX_SAMPLES = 150;
const CHART_H = 240; // CSS pixels; width is responsive (100% of the card)
const PAD_LEFT = 28;
const PAD_TOP = 16;
const PAD_BOTTOM = 24;

// One distinct hue per gate for easy telling-apart. Interleaved warm/cool + ordered so adjacent
// entries are far apart; validated with the dataviz palette checker (normal-vision separation and
// contrast PASS on the dark surface; CVD sits in the acceptable band, which is fine because
// identity is also carried by the end-of-line number labels, the hover highlight/tooltip, and the
// legend swatches -- never color alone).
const GATE_COLORS = [
  "#f87171",
  "#4ade80",
  "#fb923c",
  "#60a5fa",
  "#facc15",
  "#c084fc",
  "#22d3ee",
  "#f472b6",
  "#a3e635",
];

const canvasEl = ref(null);

// Which energy channel the chart plots: "moving" (chuyển động) or "static" (đứng yên/REST).
const channel = ref("moving");

// history: array of samples, each sample = { moving: number[], static: number[] } per-gate energies.
let history = [];
// Set of selected gate indices. Empty = show all gates; otherwise show only the selected ones
// (multi-select, for comparing several gates side by side).
const selectedGates = ref(new Set());
// Live hover readout (stock-chart style): which gate line is nearest the cursor + its value.
const hover = ref(null);
// Gate hovered in the corner mini-legend -- highlights that line without needing a cursor on it.
const legendHoverGate = ref(null);

// Per-gate energy array of the currently selected channel, from a sample or the live frame.
function channelOf(sample) {
  return (channel.value === "static" ? sample?.static : sample?.moving) ?? [];
}

const gateCount = computed(
  () => props.frame?.movingGateEnergies?.length ?? props.frame?.staticGateEnergies?.length ?? 0,
);
const hasEnergies = computed(() => gateCount.value > 0);
const latestByGate = computed(() =>
  channel.value === "static" ? (props.frame?.staticGateEnergies ?? []) : (props.frame?.movingGateEnergies ?? []),
);

// A gate is shown when nothing is selected (show all) or it's in the selected set.
function isShown(gate) {
  return selectedGates.value.size === 0 || selectedGates.value.has(gate);
}

function isSelected(gate) {
  return selectedGates.value.has(gate);
}

// Geometry of the last render, reused by the hover hit-test so it matches exactly what's drawn.
let geom = null;

function clamp01to100(v) {
  return Math.max(0, Math.min(100, v));
}

function resetHistory() {
  history = [];
  selectedGates.value = new Set();
  hover.value = null;
  legendHoverGate.value = null;
  draw();
}

// Redraw when the corner mini-legend hover changes (canvas hover already redraws via onMove).
watch(legendHoverGate, draw);

// Screen x of history sample `i` (newest sample sits at the right edge, older scroll left).
function sampleX(i, g) {
  return g.left + (MAX_SAMPLES - history.length + i) * g.stepX;
}

function energyY(value, g) {
  return g.bottom - (clamp01to100(value) / 100) * g.chartHeight;
}

function draw() {
  const canvas = canvasEl.value;
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const W = Math.round(rect.width);
  if (W === 0) return; // not laid out yet; a later frame will redraw

  // Scale the backing store by devicePixelRatio so lines are crisp on HiDPI screens (the root
  // cause of the "blurry" look was drawing at CSS resolution and letting the browser upscale).
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== W * dpr || canvas.height !== CHART_H * dpr) {
    canvas.width = W * dpr;
    canvas.height = CHART_H * dpr;
  }

  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, CHART_H);
  ctx.fillStyle = "#0b0e14";
  ctx.fillRect(0, 0, W, CHART_H);

  const g = {
    left: PAD_LEFT,
    bottom: CHART_H - PAD_BOTTOM,
    chartHeight: CHART_H - PAD_BOTTOM - PAD_TOP,
    stepX: (W - PAD_LEFT) / (MAX_SAMPLES - 1),
    W,
  };
  geom = g;

  // Recessive gridlines + y labels at 0/25/50/75/100.
  ctx.strokeStyle = "#1c2333";
  ctx.fillStyle = "#8b93a7";
  ctx.font = "10px sans-serif";
  ctx.lineWidth = 1;
  for (let v = 0; v <= 100; v += 25) {
    const y = energyY(v, g);
    ctx.beginPath();
    ctx.moveTo(PAD_LEFT, y);
    ctx.lineTo(W, y);
    ctx.stroke();
    ctx.fillText(String(v), 6, y + 3);
  }

  if (history.length < 2) return;

  const n = channelOf(history[history.length - 1]).length;
  // Line to highlight: the one under the cursor, or the one hovered in the corner mini-legend.
  const hoverGate = hover.value?.gate ?? legendHoverGate.value;

  const shown = [];
  for (let gate = 0; gate < n; gate++) {
    if (isShown(gate)) shown.push(gate);
  }

  ctx.lineJoin = "round";
  for (const gate of shown) {
    // Hovering a line brightens it (full alpha + thicker) and fades the rest, so it stands out.
    const isHovered = hoverGate === gate;
    ctx.globalAlpha = hoverGate !== null && !isHovered ? 0.2 : 1;
    ctx.strokeStyle = GATE_COLORS[gate % GATE_COLORS.length];
    ctx.lineWidth = isHovered ? 2.5 : 1.5;
    ctx.beginPath();
    for (let i = 0; i < history.length; i++) {
      const x = sampleX(i, g);
      const y = energyY(channelOf(history[i])[gate] ?? 0, g);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Label each shown line's right end with its gate number (when more than one line is visible,
  // so the traces are identifiable); also faded when another gate is being hovered.
  if (shown.length > 1) {
    const last = channelOf(history[history.length - 1]);
    ctx.font = "10px sans-serif";
    ctx.textAlign = "left";
    for (const gate of shown) {
      ctx.globalAlpha = hoverGate !== null && hoverGate !== gate ? 0.2 : 1;
      const y = energyY(last[gate] ?? 0, g);
      ctx.fillStyle = GATE_COLORS[gate % GATE_COLORS.length];
      ctx.beginPath();
      ctx.arc(W - 16, y, 2.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillText(String(gate), W - 11, y + 3);
    }
    ctx.globalAlpha = 1;
  }

  // Hover crosshair + marker on the nearest line (stock-chart style).
  if (hover.value) {
    const { gate, sampleIndex } = hover.value;
    const hx = sampleX(sampleIndex, g);
    const hy = energyY(channelOf(history[sampleIndex])[gate] ?? 0, g);

    ctx.strokeStyle = "#3a465e";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(hx, PAD_TOP);
    ctx.lineTo(hx, g.bottom);
    ctx.stroke();

    ctx.fillStyle = GATE_COLORS[gate % GATE_COLORS.length];
    ctx.beginPath();
    ctx.arc(hx, hy, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#0b0e14";
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
}

// Map a cursor position to the nearest gate line at that time-column, for the hover readout.
function onMove(event) {
  const canvas = canvasEl.value;
  if (!canvas || !geom || history.length < 2) return;

  const rect = canvas.getBoundingClientRect();
  const cx = event.clientX - rect.left;
  const cy = event.clientY - rect.top;

  let i = Math.round((cx - geom.left) / geom.stepX - (MAX_SAMPLES - history.length));
  i = Math.max(0, Math.min(history.length - 1, i));
  const arr = channelOf(history[i]);

  let bestGate = null;
  let bestDy = Infinity;
  for (let gate = 0; gate < arr.length; gate++) {
    if (!isShown(gate)) continue;

    const dy = Math.abs(energyY(arr[gate] ?? 0, geom) - cy);
    if (dy < bestDy) {
      bestDy = dy;
      bestGate = gate;
    }
  }

  if (bestGate === null) return;

  hover.value = { gate: bestGate, value: arr[bestGate], sampleIndex: i, cursorX: cx, cursorY: cy };
  draw();
}

function onLeave() {
  hover.value = null;
  draw();
}

// Toggle a gate in/out of the selected set (reassign a new Set so Vue sees the change). An empty
// set means "show all".
function toggleGate(gate) {
  const next = new Set(selectedGates.value);
  if (next.has(gate)) next.delete(gate);
  else next.add(gate);
  selectedGates.value = next;
  draw();
}

function showAll() {
  selectedGates.value = new Set();
  draw();
}

watch(
  () => props.frame,
  (frame) => {
    if (!frame?.movingGateEnergies && !frame?.staticGateEnergies) return;
    // Store both channels per sample so switching Motion/Rest shows the buffered history too.
    history = pushSample(
      history,
      { moving: [...(frame.movingGateEnergies ?? [])], static: [...(frame.staticGateEnergies ?? [])] },
      MAX_SAMPLES,
    );
    draw();
  },
);

// Redraw immediately when the operator switches the Motion/Rest channel.
watch(channel, draw);

watch(
  () => props.connected,
  (connected) => {
    if (!connected) resetHistory();
  },
);

onUnmounted(() => {
  history = [];
});
</script>

<template>
  <section class="card energy-time-chart">
    <div class="chart-head">
      <h2>エネルギー推移 (ゲート別)</h2>
      <div class="channel-switch">
        <button :class="{ active: channel === 'moving' }" @click="channel = 'moving'">移動 (Motion)</button>
        <button :class="{ active: channel === 'static' }" @click="channel = 'static'">静止 (Rest)</button>
      </div>
    </div>

    <p v-if="!hasEnergies" class="hint">エンジニアリングモードのデータ待ち…</p>

    <template v-else>
      <!-- Chart on the left, a vertical gate selector down the right side (outside the plot, so it
           never covers the lines). Hover a gate to highlight it; click to show/hide it (multi-
           select to compare); 全表示 shows all. -->
      <div class="chart-row">
        <div class="chart-wrap">
          <canvas ref="canvasEl" :style="{ height: CHART_H + 'px' }" @mousemove="onMove" @mouseleave="onLeave"></canvas>

          <div
            v-if="hover"
            class="tooltip"
            :style="{ left: hover.cursorX + 12 + 'px', top: hover.cursorY + 12 + 'px' }"
          >
            <span class="swatch" :style="{ background: GATE_COLORS[hover.gate % GATE_COLORS.length] }"></span>
            GATE {{ hover.gate }}: <strong>{{ hover.value }}</strong>
          </div>
        </div>

        <div class="gate-panel">
          <button class="gate-item all" :class="{ active: selectedGates.size === 0 }" @click="showAll">全表示</button>

          <button
            v-for="gate in gateCount"
            :key="gate"
            class="gate-item"
            :class="{ selected: isSelected(gate - 1), hovered: legendHoverGate === gate - 1 }"
            @mouseenter="legendHoverGate = gate - 1"
            @mouseleave="legendHoverGate = null"
            @click="toggleGate(gate - 1)"
          >
            <span class="swatch" :style="{ background: GATE_COLORS[(gate - 1) % GATE_COLORS.length] }"></span>
            <span class="g">G{{ gate - 1 }}</span>
            <span class="val">{{ latestByGate[gate - 1] ?? "-" }}</span>
          </button>
        </div>
      </div>

      <p class="hint sub">ゲート番号は 0-8（GATE 0 = センサー至近）。クリックで表示/非表示（複数選択で比較可）、全表示ですべて表示。ホバーで強調表示。</p>
    </template>
  </section>
</template>

<style scoped>
  .energy-time-chart {
    margin-bottom: 16px;
  }

  h2 {
    font-size: 15px;
    margin: 0;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .chart-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 16px;
  }

  .channel-switch {
    display: inline-flex;
    gap: 2px;
    background: var(--surface-2);
    border-radius: 999px;
    padding: 3px;
  }

  .channel-switch button {
    border: none;
    background: transparent;
    color: var(--text-muted);
    padding: 5px 14px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }

  .channel-switch button:hover:not(.active) {
    color: var(--text);
  }

  .channel-switch button.active {
    background: var(--accent);
    color: #fff;
  }

  .chart-row {
    display: flex;
    gap: 10px;
    align-items: stretch;
  }

  .chart-wrap {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  canvas {
    display: block;
    width: 100%;
    border-radius: 10px;
    border: 1px solid var(--border);
    cursor: pointer;
  }

  .gate-panel {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 92px;
    flex-shrink: 0;
    overflow-y: auto;
  }

  .gate-item {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--text-muted);
    background: var(--surface-2);
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 3px 7px;
    cursor: pointer;
    transition:
      background 0.12s ease,
      border-color 0.12s ease,
      color 0.12s ease;
  }

  .gate-item:hover,
  .gate-item.hovered {
    background: var(--surface-3);
    color: var(--text);
  }

  .gate-item.selected {
    border-color: var(--accent);
    color: var(--text);
  }

  .gate-item .swatch {
    width: 9px;
    height: 9px;
  }

  .gate-item .g {
    min-width: 16px;
  }

  .gate-item .val {
    margin-left: auto;
    font-weight: 700;
    color: var(--text);
  }

  .gate-item.all {
    justify-content: center;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 2px;
  }

  .gate-item.all.active {
    border-color: var(--accent);
  }

  .tooltip {
    position: absolute;
    pointer-events: none;
    background: #1b2230;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    color: var(--text);
    white-space: nowrap;
    display: flex;
    align-items: center;
    gap: 6px;
  }

  .hint {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0;
  }

  .hint.sub {
    font-size: 11px;
    margin: 8px 0 0;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }
</style>
