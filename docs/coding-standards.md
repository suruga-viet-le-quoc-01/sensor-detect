# Coding Standards

## Comment style
- Dùng **comment `#`**, KHÔNG dùng docstring `"""..."""` (kể cả Google-style). Comment mô tả mục đích đặt **ngay trên** `def`/`class` (trên cả decorator nếu có).
- **Mọi hàm/method (kể cả private, helper), class, và module** đều có comment mô tả mục đích, viết cho người đọc lần đầu hiểu ngay "để làm gì". Đơn giản 1 dòng; phức tạp thì thêm dòng cho tham số quan trọng + giá trị trả về.
  - KHÔNG lặp lại y nguyên tên hàm (`# connect the connection` vô nghĩa) — nói mục đích thật (`# Open the serial port and start reading`).
- **Comment inline** đặt ngay trên khối code nó giải thích; bắt buộc khi **WHY** không hiển nhiên: byte offset theo protocol, workaround phần cứng, quyết định kỹ thuật gây tranh luận. Tránh comment thừa lặp code hiển nhiên (`# tăng i lên 1` trên `i += 1`).
- Khi phân vân thêm hay bỏ comment: **ưu tiên viết cho dễ đọc**.

## Blank line quanh comment/khối
| Tình huống | Dòng trống? |
|---|---|
| Guard clause (validate) → logic chính | **Có** — 2 mối quan tâm khác nhau |
| Comment ngay trên dòng code nó giải thích (cùng 1 khối) | **Không** — để sát nhau |
| Giữa 2 bước tuần tự cùng 1 "câu chuyện" (đọc → parse → return, ngắn) | Thường **không** |
| Trước đoạn dài xử lý ý mới hoàn toàn (sau `for`, trước phần tổng hợp kết quả) | **Có** |

- Không để dòng trống chen giữa comment và đúng dòng code nó mô tả — comment phải dính vào code của nó.

## Ngôn ngữ (3 loại, theo đối tượng đọc)
- **Comment `#` trong code → tiếng Anh** (đọc bởi lập trình viên).
- **Message cho người vận hành → tiếng Nhật** (CLI `print`, `--help`/argparse, exception hướng dẫn setup như `BleConfigError`, `ValueError` cấu hình sai) — môi trường vận hành là Nhật.
- **File `.md` (docs, skills, agents, rules) → tiếng Việt.** Tiếng Việt CHỈ trong `.md`, không xuất hiện trong code.
- Ngoại lệ: exception thuần lỗi lập trình (vd `RuntimeError("connect() must be called first")`) giữ **tiếng Anh** — assertion cho dev, không phải hướng dẫn vận hành.

## SOLID
- **S — Single Responsibility**: mỗi module (`protocol/`, `sensor/`, `session/`, `storage/`, `web_api/`) chỉ làm đúng 1 việc — không để logic parse frame lẫn vào logic ghi DB.
- **O — Open/Closed**: thêm tính năng mới nên mở rộng bằng class/case mới, hạn chế sửa code đã chạy ổn định.
  - Ví dụ đã áp dụng: `SensorTransport` (ABC) trong `src/sensor/transport/base.py` — thêm `BleTransport` không cần sửa `SerialTransport`.
- **L — Liskov Substitution**: mọi implementation của 1 interface (vd `SensorTransport`) phải dùng thay thế lẫn nhau được — code gọi nó không cần biết đang chạy implementation nào.
- **I — Interface Segregation**: interface nhỏ, chỉ chứa method thực sự dùng chung — không ép 1 class implement method nó không cần.
- **D — Dependency Inversion**: tầng logic cao hơn (`session/`, `workflows/`) phụ thuộc vào abstraction (`SensorTransport`), KHÔNG import trực tiếp `pyserial`/`bleak` — dễ test bằng mock, dễ đổi transport mà không sửa logic session.
  - Ví dụ: `create_transport()` trong `src/sensor/transport/__init__.py` là nơi DUY NHẤT biết chọn `SerialTransport` hay `BleTransport`; phần còn lại của code chỉ thấy `SensorTransport`.

## Clean code khác
- Type hint đầy đủ cho mọi function signature (Python 3.11); dùng `from __future__ import annotations` để cú pháp `X | None` gọn.
- Tên biến/hàm rõ nghĩa, tránh viết tắt khó hiểu (trừ tên đã chuẩn hoá trong protocol: `ack`, `uuid`, `gate`...).
- Function ngắn, làm đúng 1 việc; > ~40 dòng thì cân nhắc tách hàm con.
- KHÔNG nuốt exception (`except: pass`) — luôn log hoặc raise lại kèm ngữ cảnh (xem ví dụ `BleConfigError` — raise sớm, message nói rõ cách sửa).
- Ưu tiên composition hơn kế thừa sâu nhiều tầng.

## Áp dụng cho project này (đừng over-engineer)
- Project quy mô nhỏ (1 sensor/1 máy) — KHÔNG áp SOLID cứng nhắc tới mức thêm interface/abstraction cho thứ chỉ có 1 cách triển khai và không có kế hoạch mở rộng.
- Khi 2 nguyên tắc mâu thuẫn (vd tách interface làm 1 hàm đơn giản trở nên dài dòng hơn), ưu tiên **rõ ràng, dễ đọc** hơn tuân thủ máy móc.
- Khi review code cũ chưa theo chuẩn này: sửa dần khi đụng tới file đó, KHÔNG cần sweep toàn bộ repo trong 1 lần trừ khi được yêu cầu.
