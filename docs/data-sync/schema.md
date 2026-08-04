# Schema: machine_sessions

## Oracle (đích tổng hợp)
```sql
CREATE TABLE machine_sessions (
  session_id    VARCHAR2(64)  PRIMARY KEY,        -- uuid sinh ở edge PC
  machine_id    VARCHAR2(32)  NOT NULL,
  session_date  DATE          NOT NULL,           -- ngày của start_time
  start_time    TIMESTAMP     NOT NULL,
  end_time      TIMESTAMP,                          -- NULL nếu chưa đóng (không nên sync khi NULL)
  duration_min  NUMBER(10,2)  NOT NULL,
  end_reason    VARCHAR2(16)  NOT NULL,            -- left | shift_end | signal_lost | error
  created_at    TIMESTAMP     DEFAULT SYSTIMESTAMP,
  CONSTRAINT uq_machine_start UNIQUE (machine_id, start_time)
);
CREATE INDEX ix_ms_machine_date ON machine_sessions (machine_id, session_date);
```
- UPSERT theo `(machine_id, start_time)` để idempotent (MERGE).

## SQLite buffer (local, `SQLITE_BUFFER_PATH`)
```sql
CREATE TABLE IF NOT EXISTS sessions (
  session_id    TEXT PRIMARY KEY,
  machine_id    TEXT NOT NULL,
  session_date  TEXT NOT NULL,          -- ISO date 'YYYY-MM-DD'
  start_time    TEXT NOT NULL,          -- ISO 8601
  end_time      TEXT,
  duration_min  REAL NOT NULL,
  end_reason    TEXT NOT NULL,
  synced        INTEGER NOT NULL DEFAULT 0,   -- 0=chưa, 1=đã sync, -1=lỗi cần review
  synced_at     TEXT
);
CREATE INDEX IF NOT EXISTS ix_sessions_synced ON sessions (synced);
```
- **Retention cleanup** (xem docs/data-sync/rules.md): job định kỳ chạy
  `DELETE FROM sessions WHERE synced = 1 AND synced_at < datetime('now', '-' || :RETENTION_DAYS || ' days')`.
  Chỉ xoá `synced=1`; KHÔNG bao giờ đụng tới `synced=0` hoặc `synced=-1`.

## Trạng thái realtime + health sensor (cho dashboard)
Ghi 1 bảng nhẹ (SQLite hoặc Oracle tuỳ chọn) cập nhật định kỳ:
```sql
CREATE TABLE machine_status (
  machine_id    VARCHAR2(32) PRIMARY KEY,
  last_seen     TIMESTAMP,       -- lần cuối nhận frame
  present_now   NUMBER(1),       -- 0/1
  sensor_ok     NUMBER(1),       -- 0 nếu quá SENSOR_TIMEOUT_S
  session_start TIMESTAMP        -- start_time của session đang mở (NULL nếu không có ai) — để dashboard cộng thời gian realtime của phiên chưa đóng
);
```

## Ví dụ 1 row session
```
session_id=uuid4, machine_id='CNC-07', session_date=2026-07-13,
start_time=2026-07-13T08:00:05, end_time=2026-07-13T08:42:31,
duration_min=42.43, end_reason='left'
```
