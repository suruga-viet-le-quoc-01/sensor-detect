# API Contract — FastAPI ↔ Oracle (tab Giám sát)

Backend `src/web_api/` chỉ **đọc** Oracle, trả JSON cho frontend. KHÔNG ghi. Schema nguồn:
`docs/data-sync/schema.md` (`machine_sessions`, `machine_status`).

## Nguyên tắc
- Chỉ GET (read-only). Credential Oracle từ `.env`, không nhận từ client.
- Kết nối short-lived / pool, đóng sau mỗi request.
- Cache nhẹ phía backend cho endpoint FTE (query nặng); endpoint status KHÔNG cache (cần tươi).
- Không trả dữ liệu định danh — chỉ machine_id + trạng thái + thời gian.

## Endpoints

### GET /api/machines/status
Cho tab Giám sát, frontend poll mỗi 2–5s. Nguồn: `machine_status`.
```json
[
  {"machine_id": "CNC-07", "present_now": true, "last_seen": "2026-07-23T09:15:02Z", "sensor_ok": true},
  {"machine_id": "CNC-08", "present_now": false, "last_seen": "2026-07-23T09:15:01Z", "sensor_ok": true},
  {"machine_id": "CNC-09", "present_now": false, "last_seen": "2026-07-23T08:40:00Z", "sensor_ok": false}
]
```
- `sensor_ok=false` khi `last_seen` cũ hơn `SENSOR_TIMEOUT_S` → frontend hiện badge cảnh báo.

### GET /api/machines/{machine_id}/sessions?date=YYYY-MM-DD
Danh sách session 1 máy 1 ngày. Nguồn: `machine_sessions`.
```json
[
  {"start_time": "2026-07-23T08:00:05Z", "end_time": "2026-07-23T08:42:31Z", "duration_min": 42.43, "end_reason": "left"}
]
```

### GET /api/fte?date=YYYY-MM-DD&machine_id=CNC-07
FTE + tỷ lệ có người. `machine_id` tuỳ chọn (bỏ = mọi máy). Công thức theo `docs/dashboard/rules.md`.
```json
[
  {"machine_id": "CNC-07", "date": "2026-07-23", "present_min": 384.0, "shift_min": 480, "fte": 0.80, "occupancy_pct": 80.0}
]
```

## Lỗi
- Oracle không kết nối được → `503` + `{"error": "db_unavailable"}`; frontend hiện "mất kết nối DB", KHÔNG crash.
- `date` sai định dạng → `400`.
- Khoảng lọc rỗng → `200` với mảng rỗng (không phải lỗi).

## Ghi chú realtime
- Đây là **cận realtime bằng polling** — đủ cho presence/FTE. Nếu sau này cần push sub-giây: thêm `GET /api/stream` (SSE) hoặc WebSocket đẩy khi `machine_status` đổi; chưa làm ở giai đoạn này.
