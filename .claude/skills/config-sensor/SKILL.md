---
name: config-sensor
description: >
  Dùng khi người dùng gõ /config-sensor hoặc yêu cầu viết/sửa script cấu hình
  sensor LD2410C qua UART (set max gate, sensitivity, unmanned duration, baud,
  range resolution, auto-calib...). KHÔNG dùng cho logic đọc realtime/session
  (xem skill run-reader) hay việc thêm edge case (xem skill add-edge-case).
---

Bạn là kỹ sư firmware/serial cấp cao. Nhiệm vụ: cấu hình sensor LD2410C khi lắp vào máy.

## Đọc context theo thứ tự
1. docs/sensor-config/rules.md
2. docs/sensor-config/configurable-items.md (danh mục đầy đủ mục config được)
3. docs/references/ld2410c-protocol.md (§1 quy trình, §3 max gate, §5 sensitivity, §6 baud, §8 data output)
(UI cấu hình đã chuyển sang web — xem docs/web-dashboard/ nếu làm tab Cấu hình)
(CLAUDE.md đã tự nạp — không liệt kê lại)

## Yêu cầu implementation
- Tuân thủ trình tự: Enable config (0x00FF) → các lệnh → End config (0x00FE), verify ACK từng lệnh.
- Đọc tham số từ .env: MAX_MOVING_GATE, MAX_STATIC_GATE, NO_ONE_DURATION_S, và sensitivity từng gate.
- Set max gate + unmanned duration (0x0060), set sensitivity (0x0064), lưu flash.
- Sau khi set, gọi Read parameters (0x0061) để xác nhận cấu hình đã ghi đúng, in ra so sánh.
- Hỗ trợ Enable engineering mode (0x0062) để bước tune đọc energy từng gate.
- Xử lý lỗi: không có ACK / ACK status != 0 → raise rõ ràng, không nuốt lỗi.
- KHÔNG hard-code COM port; nhận qua `--port` hoặc .env.

## Verify
- `pytest tests/test_config_frames.py -q` (frame ghép ra khớp ví dụ trong ref doc).

## Trả kết quả mỗi phase
- Đã làm gì · sửa/tạo file nào · lệnh test.

Yêu cầu cụ thể từ người dùng: $ARGUMENTS
