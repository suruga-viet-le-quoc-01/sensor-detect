<script setup>
const form = defineModel("form", { required: true }); // { resolutionM, movingGate, staticGate, noOneDurationS }
const thresholds = defineModel("thresholds", { required: true }); // { motion: number[9], static: number[9] }

defineProps({
  disabled: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits(["read-back", "write-flash", "auto-calibrate", "factory-reset", "restart"]);

function confirmAnd(eventName, message) {
  if (window.confirm(message)) emit(eventName);
}
</script>

<template>
  <section class="card parameters-panel">
    <h2>Parameters</h2>
    <p class="gate-note">GATE 0 = センサー至近、GATE 8 = 最遠（プロトコルのゲート番号 0-8 と一致）</p>

    <div class="slider-grid">
      <div class="slider-header">
        <span></span>
        <span>MOTION</span>
        <span>REST</span>
      </div>

      <!-- `gate` is 1-based from v-for; the internal/protocol gate index is `gate - 1` (0-8),
           which is also what's displayed. -->
      <div v-for="gate in 9" :key="gate" class="slider-row">
        <span class="gate-label">GATE {{ gate - 1 }}</span>

        <div class="slider-with-value">
          <input
            v-model.number="thresholds.motion[gate - 1]"
            type="range"
            min="0"
            max="100"
            :style="{ '--fill': thresholds.motion[gate - 1] + '%' }"
            :disabled="disabled || busy"
          />
          <span class="slider-value">{{ thresholds.motion[gate - 1] }}</span>
        </div>

        <!-- Static (REST) sensitivity isn't settable on gate 0/1 -- docs/sensor-config/rules.md.
             Those are the first two v-for iterations (gate <= 2). -->
        <div class="slider-with-value">
          <input
            v-model.number="thresholds.static[gate - 1]"
            type="range"
            min="0"
            max="100"
            :style="{ '--fill': thresholds.static[gate - 1] + '%' }"
            :disabled="disabled || busy || gate <= 2"
          />
          <span class="slider-value" :class="{ muted: gate <= 2 }">{{ thresholds.static[gate - 1] }}</span>
        </div>
      </div>
    </div>

    <div class="fields">
      <label>
        <span>距離分解能</span>
        <select v-model.number="form.resolutionM" :disabled="disabled || busy">
          <option :value="0.2">0.2m/gate</option>
          <option :value="0.75">0.75m/gate</option>
        </select>
      </label>

      <label>
        <span>Timeout period (s)</span>
        <input v-model.number="form.noOneDurationS" type="number" min="0" max="65535" :disabled="disabled || busy" />
      </label>

      <label>
        <span>Maximum moving distance gate</span>
        <input v-model.number="form.movingGate" type="number" min="1" max="8" :disabled="disabled || busy" />
      </label>

      <label>
        <span>Maximum static distance gate</span>
        <input v-model.number="form.staticGate" type="number" min="1" max="8" :disabled="disabled || busy" />
      </label>
    </div>

    <div class="actions">
      <button class="btn" :disabled="disabled || busy" @click="emit('read-back')">読み込み直し</button>
      <button
        class="btn primary"
        :disabled="disabled || busy"
        @click="confirmAnd('write-flash', 'センサーのフラッシュに書き込みます。よろしいですか？')"
      >
        書き込み
      </button>
      <button
        class="btn"
        :disabled="disabled || busy"
        @click="confirmAnd('auto-calibrate', '自動較正を開始します。センサーの検知範囲内に誰もいないことを確認してください。よろしいですか？')"
      >
        自動較正 (背景ノイズ)
      </button>
      <button
        class="btn"
        :disabled="disabled || busy"
        @click="confirmAnd('factory-reset', '出荷時設定に戻します。よろしいですか？')"
      >
        出荷時リセット
      </button>
      <button
        class="btn"
        :disabled="disabled || busy"
        @click="confirmAnd('restart', 'モジュールを再起動します。よろしいですか？')"
      >
        モジュール再起動
      </button>
    </div>
  </section>
</template>

<style scoped>
  .parameters-panel {
    margin-bottom: 0;
  }

  h2 {
    font-size: 15px;
    margin: 0 0 8px;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }

  .gate-note {
    font-size: 11px;
    color: var(--text-muted);
    margin: 0 0 16px;
  }

  .slider-grid {
    margin-bottom: 20px;
  }

  .slider-header {
    display: grid;
    grid-template-columns: 70px 1fr 1fr;
    gap: 16px;
    font-size: 11px;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 6px;
  }

  .slider-row {
    display: grid;
    grid-template-columns: 70px 1fr 1fr;
    gap: 16px;
    align-items: center;
    padding: 5px 0;
  }

  .gate-label {
    font-size: 12px;
    color: var(--text-muted);
  }

  .slider-with-value {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  /* Custom range fill via the --fill CSS var (set inline per slider): native accent-color
     leaves a gap after the thumb at max value because the thumb's own radius can never reach
     the track's right edge, so the track color is drawn explicitly instead. */
  input[type="range"] {
    flex: 1;
    min-width: 0;
    appearance: none;
    -webkit-appearance: none;
    height: 4px;
    border-radius: 999px;
    background: linear-gradient(to right, var(--accent) var(--fill, 0%), var(--surface-2) var(--fill, 0%));
    outline: none;
    cursor: pointer;
  }

  input[type="range"]:disabled {
    background: linear-gradient(to right, var(--text-muted) var(--fill, 0%), var(--surface-2) var(--fill, 0%));
    opacity: 0.6;
    cursor: not-allowed;
  }

  input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 14px;
    height: 14px;
    margin-top: -5px;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
  }

  input[type="range"]:disabled::-webkit-slider-thumb {
    background: var(--text-muted);
    cursor: not-allowed;
  }

  input[type="range"]::-webkit-slider-runnable-track {
    height: 4px;
    border-radius: 999px;
    background: transparent;
  }

  input[type="range"]::-moz-range-track {
    height: 4px;
    border-radius: 999px;
    background: linear-gradient(to right, var(--accent) var(--fill, 0%), var(--surface-2) var(--fill, 0%));
  }

  input[type="range"]:disabled::-moz-range-track {
    background: linear-gradient(to right, var(--text-muted) var(--fill, 0%), var(--surface-2) var(--fill, 0%));
  }

  input[type="range"]::-moz-range-thumb {
    width: 14px;
    height: 14px;
    border: none;
    border-radius: 50%;
    background: var(--accent);
    cursor: pointer;
  }

  input[type="range"]:disabled::-moz-range-thumb {
    background: var(--text-muted);
    cursor: not-allowed;
  }

  .slider-value {
    width: 28px;
    flex-shrink: 0;
    text-align: right;
    font-size: 12px;
    font-weight: 700;
    color: var(--text);
  }

  .slider-value.muted {
    color: var(--text-muted);
    font-weight: 500;
  }

  .fields {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin-bottom: 18px;
  }

  label {
    display: flex;
    flex-direction: column;
    font-size: 12px;
    color: var(--text-muted);
    gap: 6px;
  }

  label span {
    font-weight: 600;
  }

  input,
  select {
    min-width: 120px;
  }

  .actions {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
  }
</style>
