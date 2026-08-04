---
name: add-edge-case
description: >
  Dùng khi người dùng gõ /add-edge-case hoặc báo vừa gặp 1 tình huống thực tế
  (bug/edge case) cần ghi lại vào rules.md + test-cases.md rồi sửa code để
  không lặp lại. KHÔNG dùng cho việc implement tính năng mới từ đầu (dùng skill
  config-sensor hoặc run-reader tương ứng module).
---

Bạn là kỹ sư maintainer. Vừa phát hiện 1 edge case ở hiện trường. Nhiệm vụ: cố định nó để không lặp lại.

## Quy trình (KHÔNG bỏ bước)
1. Xác định module liên quan (sensor-config / realtime-reader / data-sync / dashboard).
2. Thêm mô tả edge case + cách xử lý vào `docs/{{module}}/rules.md` (mục Edge cases), có ví dụ input→output.
3. Thêm 1 test case vào `specs/test-cases.md` và 1 test thật trong `tests/`.
4. Chạy test → thấy FAIL (tái hiện bug).
5. Sửa code tối thiểu để PASS.
6. Chạy lại toàn bộ test liên quan.

## Verify
- `pytest tests/ -q`

## Trả kết quả
- Edge case là gì · file docs/test/code đã sửa · trạng thái test trước và sau fix.

Edge case cụ thể: $ARGUMENTS
