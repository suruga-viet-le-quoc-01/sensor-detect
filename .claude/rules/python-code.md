---
paths:
  - "src/**/*.py"
  - "tests/**/*.py"
---

# Khi viết/sửa code Python — invariant dễ quên

- **Ngôn ngữ**: comment/docstring → **tiếng Anh**; message cho người vận hành (CLI print, `--help`, lỗi hướng dẫn setup) → **tiếng Nhật**; tiếng Việt CHỈ trong file `.md`, không có trong code. (Exception thuần lỗi lập trình như `RuntimeError("... must be called first")` giữ tiếng Anh.)
- **Comment `#` (KHÔNG docstring `"""..."""`)** đặt trên `def`/`class` cho MỌI hàm/method (kể cả private/helper) + module + class, mô tả mục đích dễ hiểu; comment inline giải thích **WHY** khi không hiển nhiên.
- **Dòng trống**: có 1 dòng trống sau guard-clause trước logic chính, và trước đoạn xử lý ý mới; KHÔNG chen dòng trống giữa comment và đúng dòng code nó mô tả. Chi tiết bảng: docs/coding-standards.md.
- **Presence là binary**: `target_state ∈ {1,2,3}` = có người. KHÔNG đếm số người, KHÔNG định danh cá nhân.
- **Đụng phần cứng/Oracle**: chạy `--dry-run` hoặc `--port` giả trước; KHÔNG ghi Oracle prod khi chưa xác nhận.
- **Dependency Inversion**: tầng `session/` và `workflows/` phụ thuộc abstraction `SensorTransport`, KHÔNG import trực tiếp `pyserial`/`bleak`.
- **Không nuốt exception** (`except: pass`) — log hoặc raise lại kèm ngữ cảnh.

Chi tiết đầy đủ: docs/coding-standards.md
