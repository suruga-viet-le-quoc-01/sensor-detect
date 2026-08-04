# Setup and Run

## Stack
- Python 3.11 (Windows).
- Dependencies chính: pyserial, oracledb, fastapi, uvicorn, python-dotenv, pytest, ruff. Frontend web dùng Node + Vue (deps trong web/package.json).

## Cài đặt
1. Tạo venv: `python -m venv .venv`
2. Kích hoạt: `.venv\Scripts\activate` (PowerShell: `.venv\Scripts\Activate.ps1`)
3. Cài deps: `pip install -r requirements.txt`
4. Copy `.env.example` → `.env`, điền COM port + Oracle credential.
5. Cài driver converter: **Silicon Labs CP210x VCP driver** (CP2104 thuộc họ CP210x). Tải từ trang Silicon Labs.
6. Tìm cổng COM: Device Manager → Ports (COM & LPT) → tìm **"Silicon Labs CP210x USB to UART Bridge (COMx)"**. Nếu có dấu `!` vàng → driver chưa cài đúng.

## Đấu dây phần cứng (LD2410C ↔ converter CP2104)
Module LD2410C là board rời, phải nối 4 chân tới converter USB-TTL CP2104 (chi tiết pin sensor: docs/references/ld2410c-protocol.md §0.1 — ⚠️ thứ tự chân LD2410C khác LD2410B).
Board CP2104 đang dùng có **6 chân: DTR · 3.3V · 5V · TXD · RXD · GND** — có sẵn chân 5V nguồn riêng và tín hiệu TXD/RXD ở mức 3.3V, rất hợp với LD2410C: **không cần jumper / level shifter**.

| LD2410C | CP2104 (6 chân) | Ghi chú |
|---|---|---|
| VCC | **5V** | LD2410C cần nguồn 5V — dùng chân 5V, KHÔNG dùng chân 3.3V |
| GND | GND | nối đất chung |
| UART_Tx | RXD | **chéo**: Tx sensor → Rx converter |
| UART_Rx | TXD | **chéo**: Rx sensor → Tx converter |
| OUT | (không nối) | project đọc trạng thái qua UART, không dùng chân OUT |

Chân **DTR** và **3.3V** của board: **không nối** (DTR chỉ dùng auto-reset cho vi điều khiển; 3.3V không cần vì sensor ăn nguồn 5V).

Vì sao board này an toàn: chân 5V cấp nguồn cho VCC, còn TXD/RXD của họ CP2102/CP2104 6-chân này chạy **logic 3.3V** — khớp đúng mức logic UART 3.3V của LD2410C, không có chuyện đưa 5V vào chân Rx 3.3V của sensor.
- (Tuỳ chọn) Xác nhận nhanh bằng đồng hồ: đo TXD của board lúc rảnh so với GND → ~3.3V là đúng. Nếu đo ra ~5V (hiếm với board dạng này) thì DỪNG, cần level shifter trước khi nối vào sensor.

Đấu xong: cắm USB → kiểm tra COM lên trong Device Manager → chạy `python -m src.workflows.run_reader --dry-run` để xác nhận nhận được frame.

## Biến môi trường (.env) — xem .env.example
- `COM_PORT` — cổng serial của sensor (vd COM3).
- `BAUD_RATE` — mặc định 256000.
- `MACHINE_ID` — mã máy CNC gắn với sensor này (1 sensor/1 máy).
- `PRESENCE_MIN_DURATION_S` — phải có người liên tục bao lâu mới mở session (3–5s).
- `DEBOUNCE_S` — chờ bao lâu sau khi mất tín hiệu mới đóng session.
- `SENSOR_TIMEOUT_S` — không nhận frame quá lâu → cảnh báo sensor chết.
- `RANGE_RESOLUTION` — 0.75 hoặc 0.2 (m/gate); hiệu lực sau restart module.
- `MAX_MOVING_GATE`, `MAX_STATIC_GATE` — gate tối đa (2–8) khi cấu hình sensor.
- `NO_ONE_DURATION_S` — unmanned duration nạp vào sensor (0–65535).
- `MOTION_SENSITIVITY`, `STATIC_SENSITIVITY` — sensitivity áp cho tất cả gate (0–100), hoặc để trống dùng mặc định.
- `MOTION_SENSITIVITY_PER_GATE`, `STATIC_SENSITIVITY_PER_GATE` — JSON ghi đè theo từng gate (tuỳ chọn).
- `AUTO_CALIBRATE`, `AUTO_CALIBRATE_DURATION_S` — tự hiệu chỉnh nền thay cho set sensitivity tay.
- `BLUETOOTH_ENABLED` — bật/tắt Bluetooth sensor (khuyến nghị false khi vận hành).
- `AUX_LIGHT_MODE`, `AUX_LIGHT_THRESHOLD`, `OUT_DEFAULT_LEVEL` — cảm biến ánh sáng + chân OUT (thường để mặc định).
- Danh mục đầy đủ mọi mục cấu hình: docs/sensor-config/configurable-items.md.
- `ORACLE_USER`, `ORACLE_PASSWORD`, `ORACLE_DSN` — kết nối Oracle.
- `SHIFT_DURATION_MIN` — phút/ca chuẩn dùng để tính FTE (`docs/web-dashboard/api-contract.md`, `docs/dashboard/rules.md`).
- `SQLITE_BUFFER_PATH` — đường dẫn file buffer local (vd data/buffer.db).
- `SYNC_INTERVAL_S` — chu kỳ thử sync buffer lên Oracle.
- `RETENTION_DAYS` — giữ row đã sync bao lâu trong SQLite trước khi tự dọn (mặc định 7 ngày; xem docs/data-sync/rules.md).
- `SHIFT_END_TIME` — giờ kết thúc ca (để flush + đóng session mở).
- `LOG_LEVEL` — INFO/DEBUG.

## Chạy
- Cấu hình sensor (CLI, 1 lần): `python -m src.workflows.configure --port COM3`
- Hiệu chỉnh CLI: `python -m src.workflows.tune --port COM3`
- Reader dry-run: `python -m src.workflows.run_reader --dry-run`
- Reader prod: `python -m src.workflows.run_reader`
- Web API (backend): `uvicorn src.web_api.main:app --reload`
- Web frontend (Vue, dev): `cd web && npm install && npm run dev`
- Cấu hình/hiệu chỉnh qua web: mở tab Cấu hình (Web Serial/BLE) trong Chrome/Edge — xem docs/web-dashboard/rules.md.

> Lưu ý: tab Cấu hình web và reader KHÔNG dùng chung cổng COM đồng thời (serial độc quyền). Đóng reader trước khi cấu hình qua Web Serial.

## Ghi chú vận hành
- SQLite buffer là nguồn sự thật local; Oracle là đích tổng hợp. Mất mạng vẫn ghi được, khi có mạng tự sync.
- Sync KHÔNG xoá dữ liệu ngay — row chỉ được dọn sau `RETENTION_DAYS` kể từ lúc sync thành công (mặc định 7 ngày). Row chưa sync được giữ vô thời hạn tới khi sync xong.
- Khởi động cùng Windows: đăng ký `run_reader` như scheduled task / service (tự chọn), out of scope của code lõi.
