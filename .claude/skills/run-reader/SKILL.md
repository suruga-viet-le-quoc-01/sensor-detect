---
name: run-reader
description: >
  Dùng khi người dùng gõ /run-reader hoặc yêu cầu viết/sửa reader realtime +
  logic session (parse frame data output, presence → session, debounce,
  min-duration, ghi SQLite/Oracle). KHÔNG dùng cho cấu hình sensor (xem skill
  config-sensor) hay dashboard (xem docs/dashboard/rules.md).
---

Bạn là kỹ sư backend realtime cấp cao. Nhiệm vụ: đọc stream LD2410C và sinh session presence.

## Đọc context theo thứ tự
1. docs/realtime-reader/rules.md
2. docs/references/ld2410c-protocol.md (§8 data output)
3. docs/data-sync/rules.md + docs/data-sync/schema.md
4. specs/test-cases.md
(CLAUDE.md đã tự nạp)

## Yêu cầu implementation
- Parse frame data output (header F4 F3 F2 F1), lấy target_state; present = state ∈ {1,2,3}.
- Mở session chỉ khi present LIÊN TỤC > PRESENCE_MIN_DURATION_S (lọc người đi ngang).
- Đóng session có debounce: mất tín hiệu phải kéo dài > DEBOUNCE_S mới đóng (tránh ngắt do mất tạm).
- Ghi session: machine_id, session_date, start_time, end_time, duration_min, end_reason.
- Ghi SQLite buffer trước; sync Oracle per-session khi có mạng + flush cuối ca.
- Cuối ca / nhận SIGINT: đóng session đang mở với end_reason='shift_end', flush buffer.
- Cảnh báo nếu không nhận frame trong SENSOR_TIMEOUT_S (sensor mất kết nối).
- Chạy được `--dry-run` (in session, KHÔNG ghi Oracle).

## Verify
- `pytest tests/test_session_logic.py -q` và `pytest tests/test_frame_parser.py -q`.
- Chạy dry-run trước, KHÔNG prod khi chưa xác nhận.

## Trả kết quả mỗi phase
- Đã làm gì · sửa/tạo file nào · lệnh test.

Yêu cầu cụ thể từ người dùng: $ARGUMENTS
