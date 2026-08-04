# Data Sync Rules (SQLite buffer ↔ Oracle)

Module: `src/storage/` · Schema: docs/data-sync/schema.md

## Nguyên tắc
- **SQLite là nguồn sự thật local**, ghi trước tiên (kể cả khi có mạng). Oracle là đích tổng hợp.
- Mỗi session ghi SQLite ngay khi đóng, cột `synced=0`.
- Sync đẩy các row `synced=0` lên Oracle; thành công → set `synced=1` + `synced_at`.
- **Sync KHÔNG xoá dữ liệu local ngay** — row vẫn giữ trong SQLite sau khi `synced=1` để làm lớp đối chiếu/audit. Việc dọn dẹp do một job **retention cleanup** riêng đảm nhiệm (xem bên dưới), không lẫn vào luồng sync.

## Quy tắc nghiệp vụ
- **Sync per-session**: sau khi đóng 1 session, thử đẩy ngay lên Oracle. Lỗi mạng → giữ `synced=0`, thử lại chu kỳ sau.
- **Sync định kỳ**: mỗi `SYNC_INTERVAL_S`, quét toàn bộ `synced=0` đẩy lên (bù các lần mất mạng).
- **Flush cuối ca**: trước khi thoát, đóng session mở + sync toàn bộ `synced=0`.
- **Idempotent**: dùng khoá tự nhiên (machine_id + start_time) để tránh ghi trùng khi retry.
  - Ví dụ: đẩy session (MACHINE_A, start=2026-07-13 08:00:05) 2 lần do retry → Oracle chỉ có 1 row (MERGE/UPSERT theo khoá).
- **Retention cleanup**: chạy định kỳ (vd cùng chu kỳ `SYNC_INTERVAL_S` hoặc 1 lần/ngày), xoá khỏi SQLite các row thoả:
  `synced = 1 AND synced_at < now - RETENTION_DAYS`.
  - Mặc định `RETENTION_DAYS=7` — đủ để đối chiếu nếu Oracle thiếu dữ liệu, không để buffer phình vô hạn trên máy xưởng.
  - Ví dụ: session sync thành công lúc 2026-07-06 08:00, `RETENTION_DAYS=7` → đủ điều kiện xoá từ 2026-07-13 08:00 trở đi.
  - **Chỉ xoá row `synced=1`**. KHÔNG bao giờ xoá `synced=0` (chưa đẩy được) hay `synced=-1` (lỗi cần review) — dù có cũ đến đâu.

## Edge cases / Skip logic
- Mất mạng khi sync → bắt exception oracledb, log WARNING, giữ `synced=0`, KHÔNG crash reader.
- Oracle từ chối (constraint) → log ERROR kèm session_id, đánh dấu `synced=-1` (cần review), không retry vô hạn.
- Buffer phình to (mạng chết dài ngày) → vẫn ghi; cảnh báo khi số row `synced=0` vượt ngưỡng.
- Mất mạng liên tục quá `RETENTION_DAYS` → row vẫn `synced=0` nên KHÔNG bị cleanup xoá; buffer sẽ lớn hơn bình thường cho tới khi sync lại được — đây là hành vi đúng (ưu tiên không mất dữ liệu hơn tiết kiệm dung lượng).
- Clock lệch giữa các PC → luôn dùng giờ local PC làm chuẩn cho start/end; ghi kèm timezone nếu Oracle yêu cầu.

## Ràng buộc
- Không lưu thông tin định danh — chỉ machine_id + thời gian + end_reason.
- Credential Oracle lấy từ .env, không hard-code, không log.
- Kết nối Oracle dùng pool/short-lived connection, đóng sau mỗi lần sync (tránh giữ session treo).

## Chế độ chạy
- dry-run reader: KHÔNG ghi SQLite/Oracle.
- prod: ghi SQLite + sync theo quy tắc trên.
