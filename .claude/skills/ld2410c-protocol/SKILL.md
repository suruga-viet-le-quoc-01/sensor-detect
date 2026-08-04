---
name: ld2410c-protocol
description: >
  Dùng khi cần ghép/giải mã frame UART của sensor LD2410C: viết lệnh cấu hình
  (enable/end config, set max gate, set sensitivity, engineering mode, baud, noise
  detection), parse data output frame để lấy target_state / energy từng gate, hoặc
  debug byte stream không khớp. KHÔNG dùng cho logic session/debounce (xem
  docs/realtime-reader) hay ghi DB (xem docs/data-sync).
---

# LD2410C Serial Protocol

Chi tiết đầy đủ: **docs/references/ld2410c-protocol.md**. Dưới đây là phần dùng thường xuyên.
Protocol byte-level giống hệt LD2410B; khác chính ở thứ tự chân + yêu cầu nguồn (xem ref §0).

## Hai loại frame (phân biệt bằng header)
- **Command / ACK**: header `FD FC FB FA` … end `04 03 02 01`. Host chủ động gửi, radar ACK.
- **Data output**: header `F4 F3 F2 F1` … end `F8 F7 F6 F5`. Radar tự phát liên tục.

## Ghép command frame
```
FD FC FB FA | len(2B LE) | cmd_word(2B LE) + value | 04 03 02 01
```
`len` = độ dài (cmd_word + value). ACK word = cmd_word | 0x0100. Status `00 00`=OK.

Thứ tự BẮT BUỘC: Enable config (0x00FF, val 0x0001) → lệnh cấu hình → End config (0x00FE).

## Parse data output frame → presence
1. Đồng bộ tới header `F4 F3 F2 F1`.
2. Đọc `len` (2B LE), đọc `len` byte data, đọc end `F8 F7 F6 F5`.
3. `data[0]` = data type (0x02 basic / 0x01 engineering), `data[1]` = 0xAA.
4. `data[2]` = **target_state**.

## Ví dụ input → output (BẮT BUỘC)
- Input bytes `... 02 AA 02 51 00 00 00 00 3B 00 00 55 00 ...`
  → target_state = `0x02` (stationary) → **present = True**, moving_dist = 0x0051 = 81cm.
- Input target_state = `0x00` → **present = False**.
- Input target_state = `0x03` → present = True (moving & stationary).
- Ghép lệnh set max gate 8/8, unmanned 5s → §3 ref doc:
  `FD FC FB FA 14 00 60 00 00 00 08 00 00 00 01 00 08 00 00 00 02 00 05 00 00 00 04 03 02 01`

## Bẫy thường gặp
- Little-endian mọi trường đa byte (trừ MAC big-endian).
- Engineering mode mất khi tắt nguồn; sensitivity/max-gate/baud lưu flash.
- Thứ tự chân LD2410C khác LD2410B (C: Tx/Rx/OUT/GND/VCC) — đấu dây theo tên chân, xem docs/setup-and-run.md.
- Khi ở config mode vẫn có thể xen frame data output — tách theo header, đừng giả định luồng thuần ACK.

## Files tham chiếu (progressive disclosure)
- docs/references/ld2410c-protocol.md — bảng lệnh + parse đầy đủ
- docs/references/HLK-LD2410C Serial communication protocol V1.07.pdf — nguồn gốc (chỉ mở khi ref .md thiếu)
