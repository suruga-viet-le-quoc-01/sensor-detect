<script setup>
import { computed, onUnmounted, reactive, ref, shallowRef, watch } from "vue";

import { BleTransport } from "@/lib/ld2410c/ble.js";
import { SensorConfigClient } from "@/lib/ld2410c/config.js";
import { SerialTransport } from "@/lib/ld2410c/serial.js";
import ConnectPanel from "@/components/ConnectPanel.vue";
import EnergyTimeChart from "@/components/EnergyTimeChart.vue";
import LogPanel from "@/components/LogPanel.vue";
import OutputPanel from "@/components/OutputPanel.vue";
import ParametersPanel from "@/components/ParametersPanel.vue";
import PresenceTimer from "@/components/PresenceTimer.vue";

const client = shallowRef(null);

const connected = ref(false);
const connecting = ref(false);
const busy = ref(false);
const errorMessage = ref("");
const streamWarning = ref("");
const latestFrame = ref(null);
const logEntries = ref([]);

// If no frame arrives for this long while still "connected", the stream has silently stalled
// (cable half-out, sensor stopped) -- clear the frozen status instead of showing the last frame
// forever. Frames arrive ~10Hz so 3s is many misses.
const STREAM_STALE_MS = 3000;
let lastFrameAt = 0;
let watchdogTimer = null;

// Single frame handler: record the latest frame and keep the stream-stall watchdog fed.
function onFrame(frame) {
  lastFrameAt = Date.now();
  streamWarning.value = "";
  latestFrame.value = frame;
}

function startWatchdog() {
  lastFrameAt = Date.now();
  stopWatchdog();
  watchdogTimer = setInterval(() => {
    if (!connected.value) return;

    if (Date.now() - lastFrameAt > STREAM_STALE_MS) {
      // Port still open but no data -- drop the frozen frame so Output/timer/chart stop showing
      // a stale state, and warn the operator.
      latestFrame.value = null;
      streamWarning.value = "センサーからのデータ受信が途絶えています。ケーブル/センサーを確認してください。";
    }
  }, 1000);
}

function stopWatchdog() {
  if (watchdogTimer) {
    clearInterval(watchdogTimer);
    watchdogTimer = null;
  }
}

// The transport dropped on its own (device unplugged / port closed) -- leave the connected state
// and return to the connect screen instead of freezing on the last frame.
function onStreamClosed() {
  client.value = null;
  connected.value = false;
  latestFrame.value = null;
  streamWarning.value = "";
  stopWatchdog();
  errorMessage.value = "接続が切断されました。ケーブル/センサーを確認して再接続してください。";
}

onUnmounted(stopWatchdog);

const form = reactive({
  resolutionM: 0.2,
  movingGate: 8,
  staticGate: 8,
  noOneDurationS: 5,
});

// Sensitivity threshold lines shown/dragged on the energy chart. Default to 100 (disabled) for
// every gate until "読み込み直し" loads the sensor's real values -- matches the docs' zoning
// technique (sensitivity=100 = gate effectively off).
const thresholds = reactive({
  motion: new Array(9).fill(100),
  static: new Array(9).fill(100),
});

// Detection distance band (cm) -- mirrors run_reader's DETECT_MIN_CM / DETECT_MAX_CM. Empty
// string = bound unset. Persisted so a page reload doesn't lose the values being tuned.
const WINDOW_STORAGE_KEY = "ld2410c.detectWindow";

function loadWindow() {
  try {
    return { minCm: "", maxCm: "", ...JSON.parse(localStorage.getItem(WINDOW_STORAGE_KEY) ?? "{}") };
  } catch {
    return { minCm: "", maxCm: "" };
  }
}

const detectWindow = ref(loadWindow());
watch(detectWindow, (value) => localStorage.setItem(WINDOW_STORAGE_KEY, JSON.stringify(value)), {
  deep: true,
});

// Scale for the Output panel's distance bars -- the sensor can never report a target beyond its
// own configured max gate range.
const maxDistanceCm = computed(() => Math.max(form.movingGate, form.staticGate) * form.resolutionM * 100);

function pushLog(entry) {
  logEntries.value = [...logEntries.value, entry];
}

async function onConnectSerial({ baudRate }) {
  errorMessage.value = "";
  connecting.value = true;
  try {
    const newClient = new SensorConfigClient(new SerialTransport());
    await newClient.connect(onFrame, { baudRate }, onStreamClosed);
    client.value = newClient;
    connected.value = true;
    startWatchdog();
    await onReadBack(); // show the sensor's real current config immediately, not just defaults
  } catch (err) {
    errorMessage.value = err.message;
  } finally {
    connecting.value = false;
  }
}

async function onConnectBle({ serviceUuid, writeUuid, notifyUuid, password }) {
  errorMessage.value = "";
  connecting.value = true;
  try {
    const newClient = new SensorConfigClient(new BleTransport());
    await newClient.connect(onFrame, { serviceUuid, writeUuid, notifyUuid }, onStreamClosed);

    if (password) {
      await newClient.authenticateBluetooth(password).catch((err) => {
        pushLog({ ok: false, label: "BLE 認証 (0x00A8)", detail: err.message });
      });
    }

    client.value = newClient;
    connected.value = true;
    startWatchdog();
    await onReadBack();
  } catch (err) {
    errorMessage.value = err.message;
  } finally {
    connecting.value = false;
  }
}

async function onDisconnect() {
  stopWatchdog();
  await client.value?.disconnect();
  client.value = null;
  connected.value = false;
  latestFrame.value = null;
  streamWarning.value = "";
  errorMessage.value = "";
}

async function onReadBack() {
  busy.value = true;
  try {
    const params = await client.value.readParameters();
    form.movingGate = params.maxMovingGate;
    form.staticGate = params.maxStaticGate;
    form.noOneDurationS = params.noOneDurationS;
    if (params.resolutionM != null) form.resolutionM = params.resolutionM;
    thresholds.motion = [...params.motionSensitivity];
    thresholds.static = [...params.staticSensitivity];
    pushLog({
      ok: true,
      label: "読み込み直し",
      detail: `moving=${params.maxMovingGate} static=${params.maxStaticGate} duration=${params.noOneDurationS}s | raw=${params.rawExtraHex}`,
    });
  } catch (err) {
    pushLog({ ok: false, label: "読み込み直し", detail: err.message });
  } finally {
    busy.value = false;
  }
}

async function onWriteFlash() {
  busy.value = true;
  try {
    // Per-gate sensitivity entries -- only gates 2..8 support a static value (gate 0/1 static is
    // not settable), motion supports gates 0..8, per docs/sensor-config/rules.md.
    const sensitivity = thresholds.motion.map((motion, gate) => ({
      gate,
      motion,
      static: gate >= 2 ? thresholds.static[gate] : 0,
    }));

    const { log } = await client.value.writeConfig({
      resolutionM: form.resolutionM,
      movingGate: form.movingGate,
      staticGate: form.staticGate,
      noOneDurationS: form.noOneDurationS,
      sensitivity,
    });
    logEntries.value = [...logEntries.value, ...log];
  } catch (err) {
    pushLog({ ok: false, label: "書き込み失敗", detail: err.message });
  } finally {
    busy.value = false;
  }
}

async function onAutoCalibrate() {
  busy.value = true;
  try {
    const params = await client.value.autoCalibrate(10, (status) => {
      pushLog({ ok: true, label: "自動較正の進捗", detail: `status=${status}` });
    });
    thresholds.motion = [...params.motionSensitivity];
    thresholds.static = [...params.staticSensitivity];
    pushLog({ ok: true, label: "自動較正 完了" });
  } catch (err) {
    pushLog({ ok: false, label: "自動較正 失敗", detail: err.message });
  } finally {
    busy.value = false;
  }
}

async function onFactoryReset() {
  busy.value = true;
  try {
    await client.value.factoryReset();
    pushLog({ ok: true, label: "出荷時リセット" });
  } catch (err) {
    pushLog({ ok: false, label: "出荷時リセット 失敗", detail: err.message });
  } finally {
    busy.value = false;
  }
}

async function onRestart() {
  busy.value = true;
  try {
    await client.value.restart();
    pushLog({ ok: true, label: "モジュール再起動" });
  } catch (err) {
    pushLog({ ok: false, label: "モジュール再起動 失敗", detail: err.message });
  } finally {
    busy.value = false;
  }
}

</script>

<template>
  <div class="config-tab">
    <header class="topbar card">
      <h1>LD2410C コンフィギュレーター</h1>
      <div class="topbar-right">
        <span class="pill" :class="connected ? 'is-on' : 'is-off'">{{ connected ? "接続済み" : "未接続" }}</span>
        <button v-if="connected" class="btn" @click="onDisconnect">切断</button>
      </div>
    </header>

    <div v-if="!connected" class="connect-wrap">
      <ConnectPanel
        :connecting="connecting"
        :error-message="errorMessage"
        @connect-serial="onConnectSerial"
        @connect-ble="onConnectBle"
      />
    </div>

    <template v-else>
      <p v-if="streamWarning" class="stream-warning">{{ streamWarning }}</p>

      <div class="dashboard">
        <OutputPanel v-model:window="detectWindow" :frame="latestFrame" :max-distance-cm="maxDistanceCm" />

        <ParametersPanel
          v-model:form="form"
          v-model:thresholds="thresholds"
          :disabled="!connected"
          :busy="busy"
          @read-back="onReadBack"
          @write-flash="onWriteFlash"
          @auto-calibrate="onAutoCalibrate"
          @factory-reset="onFactoryReset"
          @restart="onRestart"
        />
      </div>

      <PresenceTimer :frame="latestFrame" :connected="connected" :window="detectWindow" />

      <EnergyTimeChart :frame="latestFrame" :connected="connected" />

      <LogPanel :entries="logEntries" />
    </template>
  </div>
</template>

<style scoped>
  .config-tab {
    display: flex;
    flex-direction: column;
    gap: 20px;
  }

  .topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 18px 24px;
  }

  .topbar h1 {
    font-size: 20px;
    margin: 0;
  }

  .topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .stream-warning {
    color: var(--danger);
    background: var(--danger-bg);
    border: 1px solid #4a2226;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 0;
    font-size: 13px;
  }

  .connect-wrap {
    display: flex;
    align-items: center;
    justify-content: center;
    flex: 1;
    padding: 40px 0;
  }

  .connect-wrap > :deep(.connect-cards) {
    width: 100%;
    margin-bottom: 0;
  }

  .dashboard {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    align-items: start;
  }

  @media (max-width: 860px) {
    .dashboard {
      grid-template-columns: 1fr;
    }
  }
</style>
