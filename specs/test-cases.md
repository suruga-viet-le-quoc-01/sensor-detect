# Test Cases

## Frame parser (src/protocol) — DONE, xem tests/test_frame_parser.py
- Input: `F4 F3 F2 F1 0D 00 02 AA 02 51 00 00 00 00 3B 00 00 55 00 F8 F7 F6 F5`
  → Expected: target_state=2, present=True, moving_dist=81.
- Input: frame với target_state byte = 0x00 → present=False.
- Input: target_state=0x03 → present=True.
- Input: byte rác `AA BB` trước header hợp lệ → parser resync, trả frame đúng, không crash.
- Input: tail `55 00` sai (vd `56 00`) → frame bị loại, không đổi state.
- presence() với đủ 7 giá trị target_state đã tài liệu hoá (0–6): 1/2/3=True, 0/4/5/6=False.
- Buffer chưa đủ byte theo length khai báo → trả về `(None, buffer)` KHÔNG đổi (chờ đọc thêm).
- Buffer toàn rác, không có header `F4 F3 F2 F1` nào → trả `(None, phần đuôi ngắn ≤3 byte)`, không phình bộ đệm vô hạn.
- Header thật nhưng length khai báo bất thường lớn (vd `FF FF`) → coi là hỏng, bỏ qua ngay, không chờ vô thời hạn.

### Lọc theo khoảng cách — `presence_in_range()` (DONE, xem tests/test_frame_parser.py)
- Window rỗng (không đặt min/max) → kết quả y hệt `presence()` thuần.
- Moving target trong dải 40–60cm (vd 50) → True; ngoài dải (20 hoặc 85) → False.
- Static target trong dải → True; ngoài dải → False.
- `target_state=3` (cả 2 kênh): chỉ cần **một** kênh trong dải → True; cả hai ngoài dải → False.
- Chỉ đặt min (hoặc chỉ max) → biên còn lại mở vô hạn.
- **Regression quan trọng**: state 4/5/6 (noise-detection) KHÔNG được coi là mục tiêu, dù bit của chúng trùng với bit moving/static (`0x05`=`0b101` có bit0, `0x06`=`0b110` có bit1). Test cả khi có lọc lẫn không lọc.
- ⚠️ **Phát hiện trên hardware thật**: zoning bằng sensitivity=100 **có** tắt được gate (đặt tất cả gate = 100 → không nhận diện gì), nhưng KHÔNG khoanh được vùng theo khoảng cách vì thân người phản xạ sang gate lân cận → đó là lý do phải lọc bằng khoảng cách ở phần mềm. Xem docs/realtime-reader/rules.md.

- **TODO (chưa làm, thuộc phase sau)**: parse engineering mode (`data_type=0x01`, energy từng gate) — hoãn tới khi implement lệnh `0x0062`/`0x0063`, vì ví dụ byte đầy đủ trong PDF gốc bị lược (`...`) nên chưa có fixture chính xác để test; test lúc đó nên dùng capture thật từ `tune.py` thay vì bịa byte.

## Config frame builder (src/protocol) — DONE, xem tests/test_protocol_commands.py
- Build set max gate 8/8 + unmanned 5s → bytes khớp:
  `FD FC FB FA 14 00 60 00 00 00 08 00 00 00 01 00 08 00 00 00 02 00 05 00 00 00 04 03 02 01`
- Build set all-gate sensitivity motion=40/static=40 → gate word `FF FF`, value `28 00 00 00`.
- Parse ACK `FD FC FB FA 04 00 60 01 00 00 04 03 02 01` → status=success.
- Parse ACK status `01 00` → raise / fail.
- Build set max gate=1 (biên tranh cãi giữa §1.2.2 và §2.2.3) → code KHÔNG tự raise trước khi gửi; vẫn build và gửi frame, để ACK sensor quyết định.
- Set max gate=1, mock ACK fail → raise lỗi rõ ràng gợi ý thử gate≥2.
- Set max gate=1, mock ACK success → chấp nhận bình thường, không cảnh báo giả.
- Khoanh vùng: set sensitivity gate 3=20, gate 4=20, các gate khác=100 → build đúng 1 lệnh 0xFFFF trước (baseline=100) rồi override gate 3,4=20 (hoặc build từng gate riêng theo thiết kế code).
- Build enable config / end config → bytes khớp `0x00FF`/`0x00FE` trong ref doc, kèm ACK có "extra" payload (vd enable config trả thêm 4 byte protocol version + buffer size).
- Parse ACK hỏng cấu trúc (sai header, sai footer, length không khớp payload, bit ACK 0x0100 không set) → raise lỗi rõ ràng (MalformedFrameError), không nuốt silent.
- raise_for_ack: ACK thành công KHÔNG raise dù có truyền hint; ACK fail + có hint → raise kèm đúng nội dung hint; ACK fail không hint → vẫn raise được.
- Build set range resolution 0.2m/0.75m → bytes khớp `0x00AA` trong ref doc; giá trị khác 0.2/0.75 → raise ValueError.
- Build restart → bytes khớp `0x00A3` trong ref doc.
- `parse_next_ack_frame` (buffer-scan cho kênh ACK, dùng khi gửi lệnh cấu hình thật): đọc đúng ACK sạch; bỏ qua frame data-output xen giữa (header khác hẳn `F4F3F2F1` vs `FDFCFBFA` nên không nhầm); buffer chưa đủ byte → chờ thêm; không có header nào → trim đuôi ngắn, không phình vô hạn (mirror y hệt `parse_next_data_frame`).

## Configure workflow (src/workflows/configure.py) — DONE, đã test trên hardware thật
- Trình tự ĐÚNG (đã sửa sau khi test thật): enable config → set range resolution → set max gate/no-one duration → (set sensitivity nếu có) → **restart** → (KHÔNG gửi end config sau restart). Mỗi bước verify ACK, fail thì raise rõ ràng (dùng `MAX_GATE_ACK_HINT` cho bước set max gate).
- ⚠️ **Bug phát hiện lúc test hardware thật**: bản đầu gửi `end config` → `restart` (theo đúng thứ tự "tưởng là hợp lý"). Sensor thật: 4 bước đầu ACK thành công, riêng `restart` bị **ACK từ chối** — vì `end config` đã đưa sensor thoát config mode, và `restart` (giống mọi lệnh cấu hình khác) cần đang ở TRONG config mode mới được chấp nhận. Sửa: gửi `restart` TRƯỚC `end config`, bỏ hẳn bước `end config` khi có restart (restart tự làm module reboot, đã thoát config mode). Xem docs/sensor-config/rules.md.
- Đã verify wiring thật qua CLI: `python -m src.workflows.configure --port COM99` (COM giả) → lỗi đúng ở `serial.Serial()`, không vỡ ở bước nào phía trên (đọc .env, build lệnh, tạo transport) — cùng cách verify đã dùng cho `run_reader.py`.
- ⚠️ **Bug .env phát hiện lúc test thật**: `python-dotenv` không tách được comment `#...` khi giá trị để trống (`KEY=          # comment` → value = `"# comment"` literal, không phải rỗng). Đã sửa `.env.example` (comment lên dòng riêng) + thêm hàm phòng vệ `_clean_env()` trong `configure.py` và `src/sensor/transport/__init__.py`.
- **Cấu hình mặc định hiện tại trong `.env.example`**: `RANGE_RESOLUTION=0.2`, `MAX_MOVING_GATE=5`, `MAX_STATIC_GATE=5` → phát hiện trong phạm vi **~1m** (5 × 0.2m), loại người/vật xa hơn. Đổi giá trị này trong `.env` nếu cần phạm vi khác.

## Transport (src/sensor/transport) — đã có test thật, xem tests/test_transport.py
- `TRANSPORT=serial` + `COM_PORT=COM3` → `create_transport()` trả về `SerialTransport`.
- `TRANSPORT=ble` thiếu `BLE_SERVICE_UUID`/`BLE_WRITE_CHAR_UUID`/`BLE_NOTIFY_CHAR_UUID` → raise `BleConfigError`.
- `TRANSPORT=ble` với UUID = placeholder `00000000-0000-0000-0000-000000000000` → raise `BleConfigError` (không âm thầm chấp nhận).
- `TRANSPORT` giá trị lạ (vd "carrier-pigeon") → raise `ValueError`.
- (Cần phần cứng thật, chưa tự động hoá được) BLE connect với UUID thật → gửi Enable config (0x00FF) → nhận đúng ACK qua notify characteristic, khớp bảng ACK ở docs/references/ld2410c-protocol.md.

## Session logic (src/session) — DONE, xem tests/test_session_state_machine.py + tests/test_run_reader.py
- PRESENCE_MIN_DURATION_S=4: present t=0..2s rồi mất → KHÔNG session (đi ngang).
- present liên tục 0..4s → mở session, start_time=t0.
- DEBOUNCE_S=5: ACTIVE, mất t=10s, quay lại t=13s → session KHÔNG cắt.
- ACTIVE, mất t=10s, không quay lại tới t=15s → đóng, end_time=10s, end_reason='left'.
- SIGINT khi ACTIVE → đóng, end_reason='shift_end'.
- Không frame trong SENSOR_TIMEOUT_S → cảnh báo; hết ca đóng end_reason='signal_lost'.
- Session bắt đầu 23:50 kết thúc 00:10 → session_date của ngày start, duration=20 phút.
- close() gọi khi không có session mở (IDLE/CANDIDATE) → no-op, trả None.
- ⚠️ **Lệch nhỏ đã phát hiện**: rules.md viết "phải kéo dài **>** DEBOUNCE_S mới đóng" (strict), nhưng chính ví dụ số ở trên (mất t=10s, debounce=5s, đóng đúng lúc t=15s, tức đúng bằng 5s) lại dùng **≥**. Code hiện dùng `>=` cho cả 2 ngưỡng (presence_min_duration_s và debounce_s) để khớp ví dụ số cụ thể (nguồn sự thật để test), nhất quán với cách xử lý mâu thuẫn gate=1 ở protocol/.
- `_run_loop` (src/workflows/run_reader.py, wiring transport→protocol→session) đã verify bằng: (1) test đơn vị cho `_parse_shift_end_time` + `_drain_frames`; (2) chạy CLI thật `python -m src.workflows.run_reader --dry-run` với `COM_PORT` giả → lỗi đúng ở bước `serial.Serial()` (không có gì phía trên bị vỡ); (3) chạy CLI KHÔNG có `--dry-run` → raise `NotImplementedError` rõ ràng (vì src/storage/ chưa tồn tại, prod mode cố tình chưa cho chạy thay vì âm thầm no-op).
- **TODO (chưa làm, thuộc phase src/storage/)**: prod mode thật (ghi SQLite buffer + trigger sync Oracle) — hiện `run_reader.py` không có `--dry-run` sẽ raise NotImplementedError, chưa ghi gì cả.

## Data sync (src/storage)
- Đóng session → SQLite có row synced=0.
- Sync thành công → synced=1, synced_at set.
- Sync khi mất mạng (mock oracledb raise) → giữ synced=0, không crash.
- Đẩy trùng (machine_id, start_time) 2 lần → Oracle 1 row (idempotent MERGE).
- Retention cleanup: row synced=1, synced_at = now-8 ngày, RETENTION_DAYS=7 → bị xoá khỏi SQLite.
- Retention cleanup: row synced=1, synced_at = now-3 ngày, RETENTION_DAYS=7 → KHÔNG bị xoá (chưa đủ hạn).
- Retention cleanup: row synced=0 (chưa sync), dù cũ 30 ngày → KHÔNG bị xoá.
- Retention cleanup: row synced=-1 (lỗi cần review), dù cũ 30 ngày → KHÔNG bị xoá.

## Web API (src/web_api) — DONE, xem tests/test_web_api.py
- GET /api/fte: 384 phút / ca 480 → FTE=0.80, occupancy=80.0%.
- GET /api/fte: máy có trong machine_status nhưng chưa có session (present_min=0) → vẫn trả 1 dòng fte=0, KHÔNG bị bỏ qua (LEFT JOIN từ machine_status).
- GET /api/machines/status: đọc thẳng cột present_now/sensor_ok đã lưu sẵn (KHÔNG tự tính lại từ last_seen — việc so sánh SENSOR_TIMEOUT_S thuộc phía ghi/reader, chưa tồn tại).
- Khoảng lọc rỗng → 200 + mảng rỗng (không exception).
- Oracle mất kết nối (connection_scope raise DBUnavailableError) → 503 `{"error":"db_unavailable"}`, không crash.
- `date` sai định dạng → 400 `{"error":"invalid_date"}`.
- ⚠️ **Bug phát hiện lúc code, đã sửa + khoá bằng test riêng**: nếu dùng `Depends(get_connection)` kiểu FastAPI thông thường, việc mở kết nối Oracle chạy TRƯỚC khi validate `date` trong thân hàm → date sai vẫn trả nhầm 503 (db_unavailable) thay vì 400 khi Oracle đồng thời cũng down. Verify bằng curl thật (không phải chỉ pytest) mới lộ ra, vì test đầu tiên dùng fake connection luôn thành công nên không kích hoạt được thứ tự lỗi này. Đã sửa: bỏ `Depends()`, gọi `connection_scope()` thủ công TRONG thân hàm SAU khi validate xong — thứ tự do code Python đảm bảo, không phụ thuộc cơ chế nội bộ của FastAPI. Test `test_invalid_date_returns_400_even_when_db_is_unreachable` khoá chặt hành vi này.
- Đã verify thật qua HTTP (không chỉ TestClient): chạy `uvicorn src.web_api.main:app`, `curl` cả 3 endpoint + case date sai khi Oracle không kết nối được (DSN giả) → đúng 503/503/503/400.

## Web frontend (Vue) — protocol JS (web/src/lib/ld2410c), test thuần không cần DOM
- buildCommand set max gate 8/8 + no-one 5s → bytes khớp ví dụ §3 ref doc.
- buildCommand set sensitivity gate 3 static=60 → 0x0064 (gate 3, static word 0x0002, value 60).
- parseDataFrame frame basic → target_state đúng; presence(2)=true, presence(0)=false.
- parse engineering frame → energy 9 gate motion + 9 gate static đúng vị trí byte (§8.4).
- parseAck status `01 00` → báo fail (Ghi flash → log đỏ, KHÔNG đánh dấu đã ghi).

## Web frontend (Vue) — tab Cấu hình (hành vi UI)
- Feature-detect thiếu navigator.serial/bluetooth → tab Cấu hình disable + báo rõ.
- COM đang bị reader chiếm (Web Serial open fail) → hiện cảnh báo "dừng reader", KHÔNG crash.
- Kéo slider chỉ đổi đường ngưỡng; chỉ Ghi flash mới gửi 0x0064; sau ghi tự đọc lại (0x0061) so khớp.
- Auto-calib: đếm ngược + poll 0x001B tới status=2 rồi đọc lại sensitivity.

## Run modes
- dry-run: in session, KHÔNG ghi SQLite/Oracle.
- prod: ghi SQLite + sync.

## Reliability
- Serial read timeout, vòng lặp không block vô hạn.
- Retry sync theo chu kỳ; lỗi constraint → synced=-1 (không retry vô hạn).
