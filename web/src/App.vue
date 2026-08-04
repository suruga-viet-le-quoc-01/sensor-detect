<script setup>
import { ref } from "vue";

import ConfigTabView from "./views/ConfigTabView.vue";
import MonitorTabView from "./views/MonitorTabView.vue";

const activeTab = ref("config");
</script>

<template>
  <div class="app-shell">
    <nav class="tab-switcher">
      <button :class="{ active: activeTab === 'monitor' }" @click="activeTab = 'monitor'">監視</button>
      <button :class="{ active: activeTab === 'config' }" @click="activeTab = 'config'">設定</button>
    </nav>

    <main>
      <!-- v-show (not v-if): switching tabs must NOT tear down ConfigTabView -- it holds the live
           serial/BLE connection, and destroying+remounting it would leak the still-open COM port
           (no unmount hook releases it) while resetting all connection state, so coming back to
           this tab would try to reopen an already-held port and fail. -->
      <ConfigTabView v-show="activeTab === 'config'" />
      <MonitorTabView v-show="activeTab === 'monitor'" :active="activeTab === 'monitor'" />
    </main>
  </div>
</template>

<style scoped>
  .app-shell {
    max-width: 1080px;
    margin: 0 auto;
    padding: 32px 24px 60px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  main {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  main > * {
    flex: 1;
    display: flex;
    flex-direction: column;
  }

  .tab-switcher {
    display: inline-flex;
    gap: 2px;
    background: var(--surface-2);
    border-radius: 999px;
    padding: 4px;
    margin-bottom: 20px;
  }

  .tab-switcher button {
    border: none;
    background: transparent;
    color: var(--text-muted);
    padding: 8px 22px;
    border-radius: 999px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition:
      background 0.12s ease,
      color 0.12s ease;
  }

  .tab-switcher button:hover:not(.active) {
    background: var(--surface-3);
    color: var(--text);
  }

  .tab-switcher button.active {
    background: var(--accent);
    color: #fff;
  }
</style>
