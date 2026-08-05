# Realtime Reader & Session Rules

Module: `src/session/` + `src/protocol/` + `src/sensor/` · Entry: `src/workflows/run_reader.py`
Protocol: docs/references/ld2410c-protocol.md §8

## Các thành phần chính
- **Frame parser**: đồng bộ header `F4 F3 F2 F1`, đọc len (2B LE), lấy `target_state = data[2]`.
- **presence(state)**: `state ∈ {1,2,3}` → True; `state == 0` → False; `state ∈ {4,5,6}` = trạng thái noise-detection, KHÔNG coi là presence bình thường.
- **presence_in_range(frame, window)**: presence() + lọc theo khoảng cách (xem mục dưới).
- **Session state machine**: IDLE → CANDIDATE → ACTIVE → (CLOSING) → IDLE.

## Lọc theo khoảng cách (DETECT_MIN_CM / DETECT_MAX_CM)
Chỉ tính là có người khi khoảng cách mục tiêu nằm trong dải cấu hình. Để trống cả 2 = không lọc.
- Luật: `presence(state)` **VÀ** (`bit moving` bật và `moving_distance_cm` trong dải **HOẶC** `bit static` bật và `static_distance_cm` trong dải).
  - `target_state` bit0 = có moving, bit1 = có static — **chỉ đọc bit khi state ∈ {1,2,3}**; state 5 (`0b101`) và 6 (`0b110`) cũng có bit trùng nhưng là trạng thái hiệu chỉnh nhiễu, không phải mục tiêu.
- **Vì sao không dùng zoning sensitivity để khoanh vùng**: đã xác nhận trên hardware thật rằng đặt sensitivity=100 **có** tắt được gate (đặt tất cả = 100 thì không nhận diện gì). NHƯNG tắt gate KHÔNG khoanh được vùng theo khoảng cách — thân người phản xạ năng lượng sang cả gate lân cận, nên tắt gate 1 không ngăn được chính người đứng ở gate 1 bị **gate 2 bắt được**. Khoảng cách cảm biến báo cho từng mục tiêu thì cụ thể → lọc theo nó mới thật sự giới hạn được vùng.
- **Hạn chế**: cảm biến chỉ báo **1 mục tiêu mỗi kênh** (mạnh nhất), không phải danh sách. Có 2 người (1 trong vùng, 1 ngoài) thì người ngoài có thể che mất người trong vùng.
- Cách chọn dải: chạy `run_reader --verbose`, đứng đúng vị trí làm việc, đọc `moving_cm`/`static_cm` thực tế rồi lấy khoảng đó ± biên độ. Log `--verbose` in cả `present=` (sau lọc) và `raw=` (trước lọc) để thấy rõ mục tiêu nào bị loại.

## Quy tắc nghiệp vụ (state machine)
- **IDLE + present** → chuyển CANDIDATE, ghi `t_candidate_start`.
- **CANDIDATE + present liên tục ≥ PRESENCE_MIN_DURATION_S** → mở session (ACTIVE), `start_time = t_candidate_start`.
  - Ví dụ: PRESENCE_MIN_DURATION_S=4. Người xuất hiện t=0s, vẫn present tới t=4s → mở session start_time=t0.
- **CANDIDATE + mất present trước ngưỡng** → về IDLE, KHÔNG tạo session (lọc người đi ngang).
  - Ví dụ: người đi ngang present t=0..2s rồi mất (ngưỡng 4s) → không có session.
- **ACTIVE + mất present** → CLOSING, ghi `t_lost`. Nếu present quay lại trước DEBOUNCE_S → về ACTIVE (không cắt).
  - Ví dụ: DEBOUNCE_S=5. Đang ACTIVE, tín hiệu mất t=10s, quay lại t=13s → session KHÔNG cắt.
- **CLOSING + vẫn mất present > DEBOUNCE_S** → đóng session, `end_time = t_lost`, `end_reason='left'`.
  - Ví dụ: mất t=10s, không quay lại tới t=15s (ngưỡng 5s) → đóng, end_time=10s.
- **Cuối ca / SIGINT** → đóng session đang mở, `end_reason='shift_end'`, `end_time=now`.
- `duration_min = round((end_time - start_time) / 60, 2)`.

## Edge cases / Skip logic
- Không nhận frame nào trong `SENSOR_TIMEOUT_S` → phát cảnh báo "sensor mất kết nối" (log + cờ trạng thái cho dashboard). Nếu đang ACTIVE, tiếp tục coi như CLOSING; hết ca đóng với `end_reason='signal_lost'`.
- Frame lỗi / checksum-tail (`55 00`) không khớp → bỏ frame đó, KHÔNG đổi state.
- Byte rác đầu stream → parser tự resync theo header, không crash.
- Session qua nửa đêm: `session_date` = ngày của `start_time`; duration tính theo timestamp thật (không reset).

## Ràng buộc
- Reader không được block vô hạn: serial read có timeout, vòng lặp kiểm tra cả sensor-timeout lẫn shift-end.
- `--dry-run`: in session ra stdout, KHÔNG ghi SQLite/Oracle.
- Không log khoảng cách/energy ở mức prod (privacy + gọn log); DEBUG mới in.

## Chế độ chạy
- dry-run: parse + state machine + in session, không ghi DB.
- prod: ghi SQLite buffer per-session + trigger sync (xem docs/data-sync/rules.md).

## end_reason hợp lệ
`left` (người rời) · `shift_end` (hết ca/flush) · `signal_lost` (sensor mất tín hiệu) · `error` (lỗi bất thường).
