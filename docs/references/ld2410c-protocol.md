# LD2410C Serial Communication Protocol — Bản chưng cất (V1.07)

> Nguồn gốc: `docs/references/HLK-LD2410C Serial communication protocol V1.07.pdf` (Hi-Link Electronic).
> File này là bản chưng cất để Claude đọc nhanh. Khi nghi ngờ, đối chiếu lại PDF gốc.
> Protocol byte-level của LD2410C **giống hệt LD2410B** (cùng command word, frame format, target_state).
> Khác biệt chính so với B: **thứ tự chân** (xem §0.1), yêu cầu nguồn ≥200mA, IO 3.3V.

## 0. Thông số UART mặc định
- Baud mặc định: **256000**, 8 data bits, **1 stop bit, no parity**.
- Little-endian cho mọi trường đa byte (trừ MAC address là big-endian).
- Tất cả giá trị dưới đây là **hexadecimal**.
- Nguồn: **VCC 5V**, dòng cấp yêu cầu **> 200mA**. Mức logic IO/UART: **3.3V**.

### 0.1 Định nghĩa chân (Table 1) — ⚠️ KHÁC thứ tự so với LD2410B
| Pin | Symbol | Chức năng |
|---|---|---|
| 1 | UART_Tx | UART Tx (sensor phát) |
| 2 | UART_Rx | UART Rx (sensor nhận) |
| 3 | OUT | Target state output (có người = high, không = low) |
| 4 | GND | Power ground |
| 5 | VCC | Power input 5V |

> So với LD2410B (thứ tự: OUT, UART_Tx, UART_Rx, GND, VCC), LD2410C đảo thành **UART_Tx, UART_Rx, OUT, GND, VCC**. Đấu dây theo **tên chân**, không theo số thứ tự — xem docs/setup-and-run.md.

---

## 1. Command frame (host → radar)

```
Frame header        Length (2B, LE)   Intra-frame data        End of frame
FD FC FB FA         N                 <cmd word 2B><value>    04 03 02 01
```
- `Length` = số byte của `Intra-frame data` (cmd word + value), little-endian.
- Intra-frame data = **Command word (2B, LE)** + **Command value (N bytes)**.

### ACK frame (radar → host)
```
Frame header        Length (2B, LE)   Intra-frame data              End of frame
FD FC FB FA         N                 <cmd word|0x0100><return>     04 03 02 01
```
- ACK command word = command word gửi đi **OR 0x0100** (vd gửi 0x0060 → ACK 0x0160).
- Return value thường bắt đầu bằng **2 byte ACK status**: `00 00` = success, `01 00` = fail.

### Quy trình BẮT BUỘC khi cấu hình (2.4)
1. Gửi **Enable configuration** (0x00FF) → chờ ACK success.
2. Gửi (các) lệnh cấu hình → chờ ACK từng lệnh.
3. Gửi **End configuration** (0x00FE) → chờ ACK success.
> Không gửi Enable trước → mọi lệnh khác vô hiệu. Không có ACK / ACK fail = lệnh thất bại.

---

## 2. Danh sách lệnh (Command word)

| Lệnh | Word | Value gửi | Ghi chú |
|---|---|---|---|
| Enable configuration | `0x00FF` | `0x0001` | Return: status + 2B protocol ver + 2B buffer size |
| End configuration | `0x00FE` | none | Radar về working mode |
| Set max gate + unmanned duration | `0x0060` | xem §3 | Lưu vào flash (không mất khi tắt nguồn) |
| Read parameters | `0x0061` | none | Return: cấu hình hiện tại, xem §4 |
| Enable engineering mode | `0x0062` | none | Thêm energy từng gate vào data. **Mất khi tắt nguồn** |
| Close engineering mode | `0x0063` | none | Tắt engineering mode |
| Set gate sensitivity | `0x0064` | xem §5 | Lưu vào flash |
| Read firmware version | `0x00A0` | none | Return: firmware type (`0x0001`) + major + minor |
| Set serial baud rate | `0x00A1` | 2B index (xem §6) | Có hiệu lực sau restart |
| Factory reset | `0x00A2` | none | Có hiệu lực sau restart |
| Restart module | `0x00A3` | none | Tự restart sau khi ACK. ⚠️ **Xác nhận trên hardware thật**: phải gửi TRƯỚC End config (`0x00FE`), gửi sau khi End config đã ACK sẽ bị từ chối |
| Bluetooth on/off | `0x00A4` | `0x0100` on / `0x0000` off | Có hiệu lực sau restart |
| Get MAC address | `0x00A5` | `0x0001` | MAC big-endian |
| Get Bluetooth access (xác thực BLE) | `0x00A8` | 6B password (mặc định "HiLink" = `48 69 4c 69 6e 6b`) | **ACK chỉ trả về qua kênh BLE, không qua serial** — bằng chứng protocol byte-level dùng chung cho cả BLE (xem docs/sensor-config/ble-transport.md) |
| Set Bluetooth password | `0x00A9` | 6B password | Có hiệu lực sau restart |
| Set range resolution | `0x00AA` | `0x0000`=0.75m / `0x0001`=0.2m | Mỗi gate = 0.75m hoặc 0.2m |
| Query range resolution | `0x00AB` | none | |
| Auxiliary (light) control | `0x00AD` | 4B (xem PDF §2.2.18) | Điều khiển chân OUT theo cảm biến ánh sáng |
| Start noise detection + auto sensitivity | `0x000B` | 2B duration (giây) | Cần KHÔNG có người trong 10s + suốt quá trình |
| Query noise detection status | `0x001B` | none | 0=chưa chạy, 1=đang chạy, 2=xong |

---

## 3. Set max gate + unmanned duration (0x0060)

Command value = 3 cặp (parameter word 2B + parameter value 4B):

| Parameter | Word | Value |
|---|---|---|
| Max **moving** distance gate | `0x0000` | 1~8 hoặc 2~8 (xem cảnh báo dưới) |
| Max **static** distance gate | `0x0001` | 1~8 hoặc 2~8 (xem cảnh báo dưới) |
| **No-one duration** (giây) | `0x0002` | 0~65535 |

> ⚠️ **Mâu thuẫn trong chính tài liệu Hi-Link** (vẫn còn ở bản C): §1.2.2 (tổng quan) ghi *"the range can be set from 1 to 8"*; §2.2.3 (đặc tả lệnh này) ghi *"configuration range 2~8"*. Không rõ giá trị `1` có thực sự được sensor chấp nhận hay không.
> **Cách xử lý an toàn**: KHÔNG chặn cứng giá trị `1` ở phía code. Cứ gửi lệnh xuống sensor và đọc **ACK status** làm nguồn sự thật — ACK `00 00` = sensor chấp nhận, ACK fail = từ chối (khi đó báo lỗi rõ ràng cho người dùng thay vì áp đặt giới hạn suy đoán).

**Ví dụ** — max moving gate 8, max static gate 8, unmanned 5s:
```
FD FC FB FA 14 00 60 00 00 00 08 00 00 00 01 00 08 00 00 00 02 00 05 00 00 00 04 03 02 01
```
ACK success:
```
FD FC FB FA 04 00 60 01 00 00 04 03 02 01
```

**Ví dụ tính khoảng cách xa nhất** (§1.2.2): farthest gate = 2, resolution = 0.75m → chỉ phát hiện người trong phạm vi **1.5m** (2 × 0.75m). Công thức: `farthest_distance = max_gate × resolution`.

---

## 4. Read parameters (0x0061) — cấu trúc return

Sau `status(2B)`:
`0xAA` (head) + max gate N (1B) + max moving gate (1B) + max static gate (1B)
+ motion sensitivity gate 0..8 (9B) + static sensitivity gate 0..8 (9B) + no-one duration (2B).

---

## 5. Set gate sensitivity (0x0064)

Command value = 3 cặp (word 2B + value 4B):

| Parameter | Word |
|---|---|
| Distance gate | `0x0000` (dùng `0xFFFF` = áp cho **tất cả** gate) |
| Motion sensitivity | `0x0001` (0~100) |
| Static sensitivity | `0x0002` (0~100) |

**Ví dụ** — gate 3, motion sens 40, static sens 40:
```
FD FC FB FA 14 00 64 00 00 00 03 00 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01
```
**Ví dụ** — tất cả gate, motion 40, static 40 (gate word = FF FF):

FD FC FB FA 14 00 64 00 00 00 FF FF 00 00 01 00 28 00 00 00 02 00 28 00 00 00 04 03 02 01
```

**Kỹ thuật khoanh vùng phát hiện bằng sensitivity=100** (§1.2.2): energy mục tiêu chỉ trong khoảng 0~100, nên đặt sensitivity **= 100** cho 1 gate = coi như **vô hiệu hoá** gate đó (không energy nào vượt ngưỡng 100 được). Kết hợp: đặt sensitivity thấp (nhạy) cho gate cần bắt, sensitivity=100 (tắt) cho gate còn lại → chỉ phát hiện đúng 1 dải khoảng cách.
- Ví dụ (nguyên văn PDF): gate 3 & gate 4 sensitivity=20 (nhạy), các gate khác sensitivity=100 (tắt) → **chỉ phát hiện người trong khoảng 2.25–3.75m** (gate 3 = 3×0.75=2.25m, gate 4 = 4×0.75=3.75m). Hữu ích để loại người đi ngang ngoài vùng máy mà không cần đổi max gate tổng thể.
---

## 6. Baud rate index (0x00A1)
`0x0001`=9600 · `0x0002`=19200 · `0x0003`=38400 · `0x0004`=57600 · `0x0005`=115200 · `0x0006`=230400 · **`0x0007`=256000 (mặc định)** · `0x0008`=460800.

---

## 7. Giá trị mặc định xuất xưởng (Table 7)
- Max moving gate = 8, max static gate = 8, no-one duration = 5s, baud = 256000, resolution = 0.75m.

Sensitivity mặc định theo gate:

| Gate | Motion | Static |
|---|---|---|
| 0 | 50 | (không đặt được) |
| 1 | 50 | (không đặt được) |
| 2 | 40 | 40 |
| 3 | 30 | 40 |
| 4 | 20 | 30 |
| 5 | 15 | 30 |
| 6 | 15 | 20 |
| 7 | 15 | 20 |
| 8 | 15 | 20 |

---

## 8. Data output frame (radar → host, tự động phát)

```
Frame header    Length (2B, LE)   Intra-frame data                          End of frame
F4 F3 F2 F1     N                 <Data Type 1B><0xAA><target data><55><00>  F8 F7 F6 F5
```

**Data Type:** `0x01` = engineering mode, `0x02` = target basic info.

### 8.1 Target basic info (Table 13) — LUÔN có
| Trường | Bytes |
|---|---|
| **Target state** | 1 |
| Moving target distance (cm) | 2 |
| Moving target energy | 1 |
| Static target distance (cm) | 2 |
| Static target energy | 1 |
| Detection distance (cm) | 2 |

### 8.2 Target state value (Table 14) — QUAN TRỌNG NHẤT cho presence
| Value | Ý nghĩa | Presence? |
|---|---|---|
| `0x00` | No target | KHÔNG |
| `0x01` | Movement target | CÓ |
| `0x02` | Stationary target | CÓ |
| `0x03` | Movement & Stationary | CÓ |
| `0x04` | Đang chạy noise detection | (chỉ khi hiệu chỉnh) |
| `0x05` | Noise detection thành công | (chỉ khi hiệu chỉnh) |
| `0x06` | Noise detection thất bại | (chỉ khi hiệu chỉnh) |

> **Presence binary** = `target_state in (0x01, 0x02, 0x03)`.

### 8.3 Engineering mode thêm (Table 15) — chỉ khi bật 0x0062
Sau target basic info: max moving gate N (1B) + max static gate N (1B)
+ moving gate 0..N energy (N+1 B) + static gate 0..N energy (N+1 B)
+ photosensitive value (1B, 0~255) + OUT pin status (1B: 0=unmanned, 1=occupied).

### 8.4 Ví dụ parse

**Normal mode** (length `0D 00` = 13):
```
F4 F3 F2 F1  0D 00  02 AA 02 51 00 00 00 00 3B 00 00 55 00  F8 F7 F6 F5
                    │  │  │  └─ moving dist 0x0051=81cm ...  │  │
                    │  │  └ target_state=0x02 (stationary→CÓ người)
                    │  └ head 0xAA
                    └ data type 0x02 (basic)
```

**Engineering mode** (length `23 00` = 35):
```
F4 F3 F2 F1 23 00 01 AA 03 1E 00 3C 00 00 39 00 00 08 08 ... 60 01 55 00 F8 F7 F6 F5
                  │        │ └ target_state=0x03 ...          │  └ OUT=1 (occupied)
                  │        └ head 0xAA                        └ photosensitive 0x60
                  └ data type 0x01 (engineering)
```

### 8.5 Lưu ý parser
- Tìm frame header `F4 F3 F2 F1`, đọc `length`, đọc đủ `length` byte data + 4 byte end `F8 F7 F6 F5`.
- Verify tail trong data: `... 55 00` trước end-of-frame.
- Data output (`F4 F3 F2 F1`) và command/ACK (`FD FC FB FA`) là **hai loại frame khác header** — khi ở config mode vẫn có thể xen kẽ, cần tách theo header.
