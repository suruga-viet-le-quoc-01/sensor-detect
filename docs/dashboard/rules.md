# Dashboard Business Rules (framework-neutral)

Quy tắc nghiệp vụ hiển thị FTE/presence — KHÔNG gắn framework cụ thể. Được **web app** tiêu thụ:
backend `src/web_api/` (docs/web-dashboard/api-contract.md) tính, frontend Vue hiển thị.
Nguồn dữ liệu: Oracle `machine_sessions` + `machine_status` (docs/data-sync/schema.md).

## Mục tiêu hiển thị
- **FTE theo máy/ngày**: FTE = tổng duration_min có người trong ngày / phút-ca-chuẩn (cấu hình, vd 480).
- **Tỷ lệ thời gian có người** (occupancy): tổng duration_min / thời lượng ca × 100%.
- **Trạng thái cận realtime từng máy**: present_now + last_seen từ machine_status.
- **Cảnh báo sensor không gửi dữ liệu**: sensor_ok=0 hoặc last_seen quá cũ → badge đỏ.

## Quy tắc nghiệp vụ
- Chỉ đọc, KHÔNG ghi Oracle từ tầng hiển thị.
- Bộ lọc: khoảng ngày + máy. Mặc định hôm nay.
- FTE làm tròn 2 số; tỷ lệ % làm tròn 1 số.
  - Ví dụ: máy CNC-07 ngày 2026-07-13 tổng 384 phút có người, ca 480 phút → FTE=0.80, tỷ lệ=80.0%.
- Backend cache truy vấn FTE (query nặng) với TTL; endpoint trạng thái KHÔNG cache (cần tươi cho cận realtime). Chi tiết: docs/web-dashboard/api-contract.md.

## Edge cases
- Không có session trong khoảng lọc → hiện "Không có dữ liệu", không lỗi.
- Máy có trong status nhưng chưa có session → FTE=0, vẫn hiện dòng.
- last_seen NULL → coi sensor chưa từng báo → cảnh báo.
- session end_reason='signal_lost' chiếm tỷ lệ cao → gợi ý kiểm tra sensor (badge cảnh báo).

## Ràng buộc
- Credential Oracle từ .env (dùng chung config loader với reader), không nhập trên UI.
- Không hiển thị bất kỳ dữ liệu định danh cá nhân (không có trong schema).
