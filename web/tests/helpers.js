// Parse a whitespace-separated hex string ("FD FC FB FA") into a Uint8Array, mirroring Python's
// bytes.fromhex() used throughout the reference test suite (tests/test_frame_parser.py etc.).
export function hexToBytes(hex) {
  const clean = hex.replace(/\s+/g, "");
  const bytes = new Uint8Array(clean.length / 2);
  for (let i = 0; i < bytes.length; i++) {
    bytes[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return bytes;
}
