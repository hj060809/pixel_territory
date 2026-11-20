"""의존성 없는 PNG 저장 (RGB 8비트)."""
from __future__ import annotations

import struct
import zlib

import numpy as np


def png_bytes(img: np.ndarray, level: int = 9) -> bytes:
    img = np.ascontiguousarray(img, np.uint8)
    h, w = img.shape[:2]
    raw = b''.join(b'\0' + img[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, level)) + chunk(b'IEND', b''))


def save_png(path, img) -> None:
    with open(path, 'wb') as f:
        f.write(png_bytes(img))
