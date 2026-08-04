# CLAUDE.md

Mục tiêu: Phát hiện có/không người tại từng máy CNC bằng sensor mmWave LD2410C (UART) → ghi session thời gian có người vào Oracle để tính FTE.
Stack: Python 3.11 · pyserial · SQLite (buffer) · oracledb · FastAPI + Vue (web app) · Windows.

## Commands (copy-paste được)
- Cấu hình sensor (chạy 1 lần khi lắp): `python -m src.workflows.configure --port COM3`
- Reader dry-run (in ra, KHÔNG ghi DB): `python -m src.workflows.run_reader --dry-run`
- Reader prod (ghi session): `python -m src.workflows.run_reader`
- Hiệu chỉnh sensitivity (engineering mode, in energy từng gate): `python -m src.workflows.tune --port COM3`
- Dò UUID BLE (setup 1 lần, xem docs/sensor-config/ble-transport.md): `python -m src.workflows.ble_discover --address <MAC>`
- Web API (backend, đọc Oracle): `uvicorn src.web_api.main:app --reload`
- Web frontend (Vue, dev): `npm run dev` (trong thư mục web/)
- Test 1 file: `pytest tests/test_frame_parser.py -q`
- Lint: `ruff check src tests`

## Nguyên tắc làm việc
- Chỉ đọc file cần cho task hiện tại. KHÔNG nạp toàn bộ docs.
- Reader/config đụng phần cứng thật: luôn chạy `--dry-run` hoặc `--port` giả trước; KHÔNG ghi Oracle prod khi chưa xác nhận.
- Presence là **binary**: `target_state in (1,2,3)` = có người. KHÔNG đếm người, KHÔNG định danh cá nhân.
- Xong mỗi phase → tóm tắt ngắn (đã sửa file nào, lệnh test nào) rồi mới sang phase sau.

## Entry points
- Tổng quan: @docs/project-overview.md
- Setup + .env: docs/setup-and-run.md
- Chuẩn code (comment, SOLID, clean code): docs/coding-standards.md
- Protocol LD2410C: docs/references/ld2410c-protocol.md (hoặc gọi skill `/ld2410c-protocol`)

## Nếu đang sửa CẤU HÌNH SENSOR (configure/tune CLI; UI cấu hình nay ở WEB APP)
> **Nguồn sự thật cấu hình cảm biến = WEB (tab 設定, Web Serial)**, ghi thẳng vào flash cảm biến.
> `configure.py`/`tune.py` (CLI, đọc `.env`) là **tuỳ chọn/legacy** — dùng khi không có trình duyệt.
> Cùng ghi 1 flash, lần ghi cuối thắng. **KHÔNG chạy `configure.py` sau khi tune web** (đọc `.env` cũ → ghi đè).
> `run_reader` chỉ đọc, không đụng flash, không đọc biến gate/sensitivity trong `.env`.
1. docs/sensor-config/rules.md
2. docs/sensor-config/configurable-items.md (danh mục đầy đủ mục config được)
3. docs/sensor-config/ble-transport.md (nếu đụng kết nối BLE — SCAFFOLD, UUID chưa xác nhận thật)
4. docs/references/ld2410c-protocol.md (§1–§7: command frames, §8 data output)
(UI cấu hình gate/sensitivity/resolution: xem WEB APP bên dưới)

## Nếu đang sửa READER REALTIME (đọc + logic session)
1. docs/realtime-reader/rules.md
2. docs/references/ld2410c-protocol.md (§8: data output)
3. specs/test-cases.md

## Nếu đang sửa ĐỒNG BỘ DỮ LIỆU (Oracle/SQLite)
1. docs/data-sync/rules.md
2. docs/data-sync/schema.md

## Nếu đang sửa WEB APP (SPA Vue + FastAPI: giám sát + cấu hình Web Serial/BLE)
1. docs/web-dashboard/rules.md
2. docs/web-dashboard/api-contract.md (backend đọc Oracle)
3. docs/web-dashboard/protocol-js.md (port protocol sang JS cho tab Cấu hình)
4. docs/dashboard/rules.md (business rules: FTE, tỷ lệ có người, cảnh báo)
5. docs/data-sync/schema.md

## Nếu đang viết test
1. specs/test-cases.md
2. docs/realtime-reader/rules.md

## Bảo mật
- KHÔNG hard-code COM port / Oracle credential. Dùng .env (xem .env.example).
- KHÔNG log dữ liệu định danh. Chỉ log machine_id + trạng thái + thời gian.
- KHÔNG sửa file trong archive/.

## Cấu trúc src/
- src/protocol/    — Ghép/parse frame LD2410C (command + data output)
- src/sensor/      — Transport tới sensor: Serial (pyserial) + BLE (bleak, scaffold), gửi lệnh config, đọc stream
- src/session/     — Logic presence → session (debounce, min-duration)
- src/storage/     — SQLite buffer + sync Oracle
- src/web_api/     — Backend FastAPI cho web app (đọc Oracle → JSON)
- web/             — Frontend SPA Vue (giám sát + cấu hình Web Serial/BLE)
- src/workflows/   — Entry points: configure, run_reader, tune
