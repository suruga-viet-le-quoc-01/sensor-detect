<script setup>
import { reactive } from "vue";

import { SUPPORTED_BAUD_RATES, DEFAULT_BAUD_RATE } from "@/lib/ld2410c/serial.js";

defineProps({
  connecting: { type: Boolean, required: true },
  errorMessage: { type: String, default: "" },
});

const emit = defineEmits(["connect-serial", "connect-ble"]);

const STORAGE_KEY = "ld2410c.ble";

// BLE service/characteristic UUIDs are unconfirmed at the protocol level (protocol PDF only
// documents UART, see docs/sensor-config/ble-transport.md) -- persisted here so a technician who
// already discovered them via `python -m src.workflows.ble_discover` only has to type them once
// per browser. This is the browser-side equivalent of that workflow's .env BLE_* variables.
function loadBleConfig() {
  try {
    return { serviceUuid: "", writeUuid: "", notifyUuid: "", password: "HiLink", ...JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") };
  } catch {
    return { serviceUuid: "", writeUuid: "", notifyUuid: "", password: "HiLink" };
  }
}

const serial = reactive({ baudRate: DEFAULT_BAUD_RATE });
const ble = reactive(loadBleConfig());

function saveBleConfig() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ble));
}

function onConnectSerial() {
  emit("connect-serial", { baudRate: serial.baudRate });
}

function onConnectBle() {
  saveBleConfig();
  emit("connect-ble", { ...ble });
}
</script>

<template>
  <section class="connect-cards">
    <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>

    <div class="cards">
      <div class="card connect-card">
        <div class="card-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6">
            <rect x="6" y="6" width="12" height="12" rx="2" />
            <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" stroke-linecap="round" />
          </svg>
          <h2>シリアル (Serial)</h2>
        </div>

        <p class="desc">LD2410C をシリアル-USB 変換アダプタ経由で接続します：</p>
        <ul>
          <li>5V を VCC に、GND を GND に接続</li>
          <li>RX を TX に、TX を RX に接続</li>
          <li>アダプタのドライバがインストール済みであること</li>
        </ul>

        <label class="field">
          <span>ボーレート</span>
          <select v-model.number="serial.baudRate">
            <option v-for="rate in SUPPORTED_BAUD_RATES" :key="rate" :value="rate">
              {{ rate }}{{ rate === 256000 ? " (default)" : "" }}
            </option>
          </select>
        </label>

        <button class="btn primary full" :disabled="connecting" @click="onConnectSerial">
          {{ connecting ? "接続中..." : "シリアルで接続" }}
        </button>
      </div>

      <div class="card connect-card">
        <div class="card-title">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6">
            <path d="M7 7l10 10-5 5V2l5 5L7 17" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <h2>Bluetooth</h2>
        </div>

        <p class="desc">「スキャンして接続」を押すとセンサー本体（HLK-LD2410*）を探します：</p>
        <ul>
          <li>センサー側の Bluetooth を事前に有効化 (0x00A4)</li>
          <li>Service/Characteristic UUID 未入力でもデバイスの発見はできます</li>
          <li>UUID は <code>python -m src.workflows.ble_discover</code> で調査</li>
        </ul>

        <label class="field">
          <span>パスワード</span>
          <input v-model="ble.password" type="text" placeholder="HiLink" />
        </label>

        <label class="field">
          <span>Service UUID（任意・未確認なら空欄可）</span>
          <input v-model="ble.serviceUuid" type="text" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
        </label>

        <label class="field">
          <span>Write Characteristic UUID</span>
          <input v-model="ble.writeUuid" type="text" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
        </label>

        <label class="field">
          <span>Notify Characteristic UUID</span>
          <input v-model="ble.notifyUuid" type="text" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
        </label>

        <button class="btn primary full" :disabled="connecting" @click="onConnectBle">
          {{ connecting ? "接続中..." : "スキャンして接続" }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
  .connect-cards {
    margin-bottom: 20px;
  }

  .cards {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    align-items: stretch;
  }

  @media (max-width: 760px) {
    .cards {
      grid-template-columns: 1fr;
    }
  }

  .connect-card {
    display: flex;
    flex-direction: column;
  }

  .card-title {
    display: flex;
    align-items: center;
    gap: 10px;
    color: var(--text-muted);
    margin-bottom: 14px;
  }

  .card-title h2 {
    font-size: 16px;
    margin: 0;
    color: var(--text);
  }

  .desc {
    font-size: 13px;
    color: var(--text-muted);
    margin: 0 0 8px;
  }

  ul {
    margin: 0 0 16px;
    padding-left: 18px;
    font-size: 13px;
    color: var(--text-muted);
  }

  li {
    margin-bottom: 4px;
  }

  code {
    background: var(--surface-2);
    border-radius: 4px;
    padding: 1px 5px;
    font-size: 12px;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 14px;
  }

  .field select,
  .field input {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
    width: 100%;
  }

  .btn.full {
    width: 100%;
    margin-top: auto;
  }

  .error-banner {
    color: var(--danger);
    background: var(--danger-bg);
    border: 1px solid #4a2226;
    border-radius: 8px;
    padding: 10px 14px;
    margin: 0 0 12px;
    font-size: 13px;
  }
</style>
