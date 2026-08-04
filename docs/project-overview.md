# Project Overview — 設備在席検知システム (Machine Presence Tracking)

## Mục tiêu
- Phát hiện **có/không người** tại từng máy CNC bằng sensor mmWave 24GHz LD2410C.
- Ghi lại khoảng thời gian có người (session) để tính **FTE** theo máy/ngày.
- CHỈ binary presence — KHÔNG đếm số người, KHÔNG định danh cá nhân (privacy by design).
- Lọc nhiễu: người đi ngang qua không tạo session; mất tín hiệu tạm không cắt session.
- Cảnh báo khi sensor ngừng gửi dữ liệu.

## Công nghệ
- Python 3.11 + pyserial (UART) + oracledb (Oracle) + SQLite (buffer offline) + FastAPI (web API) + Vue (web SPA). Cấu hình sensor qua web (Web Serial/BLE), không còn GUI desktop.
- Test: pytest · Lint/format: ruff.
- Chạy trên Windows tablet/mini PC đặt tại máy; module LD2410C nối qua converter USB-TTL UART **CP2104** (Silicon Labs CP210x) tới cổng COM — cần đấu dây 4 chân (xem docs/setup-and-run.md).
- 1 sensor / 1 máy, baud 256000.

## Luồng tổng
1. **Lắp đặt (1 lần)**: `configure` (CLI) hoặc **tab Cấu hình trên web** (Web Serial/BLE) — set range resolution + max gate + sensitivity + unmanned duration, lưu flash sensor.
2. **Hiệu chỉnh**: tab Cấu hình web vẽ energy từng gate realtime + đường ngưỡng sensitivity kéo được (hoặc `tune` CLI in energy).
3. **Vận hành**: `run_reader` — đọc stream realtime, lấy target_state.
4. Áp logic session: present liên tục > ngưỡng → mở session; mất tín hiệu > debounce → đóng.
5. Ghi session vào SQLite buffer local.
6. Sync lên Oracle `machine_sessions` (per-session khi có mạng + flush cuối ca).
7. **Web app**: Vue SPA + FastAPI (đọc Oracle) → giám sát cận realtime từng máy, FTE/máy/ngày, tỷ lệ có người, cảnh báo sensor; kèm tab cấu hình sensor qua Web Serial/BLE.

## Cấu trúc folder
```
src/
  protocol/   — Ghép/parse frame LD2410C (thuần byte, không I/O)
  sensor/     — Transport tới sensor: Serial (pyserial) + BLE (bleak, scaffold), gửi lệnh config, đọc stream
  session/    — Presence → session (debounce, min-duration)
  storage/    — SQLite buffer + sync Oracle
  web_api/    — Backend FastAPI (đọc Oracle → JSON cho web SPA)
  workflows/  — Entry points: configure / run_reader / tune
web/          — Frontend SPA Vue (giám sát + cấu hình Web Serial/BLE)
```

## Tài liệu liên quan
- Cấu hình sensor: docs/sensor-config/rules.md · danh mục đầy đủ: docs/sensor-config/configurable-items.md · UI cấu hình (web): docs/web-dashboard/rules.md
- Reader + session: docs/realtime-reader/rules.md
- Đồng bộ dữ liệu: docs/data-sync/rules.md · schema: docs/data-sync/schema.md
- Web app (Vue SPA + FastAPI: giám sát cận realtime + cấu hình Web Serial/BLE): docs/web-dashboard/rules.md · api-contract.md · protocol-js.md
- Business rules dashboard (FTE, tỷ lệ có người, cảnh báo): docs/dashboard/rules.md
- Protocol: docs/references/ld2410c-protocol.md
- Setup: docs/setup-and-run.md
- Test cases: specs/test-cases.md
