"""지도 묶음 파일 형식 (.tsb): 브라우저가 쉽게 읽는 단순한 이진 묶음, 전체를 gzip으로 압축.

압축을 푼 내용:
    'TSB1' (4바이트) | 머리말 길이 n (uint32, little-endian) | 머리말 JSON (UTF-8, n바이트) | 0으로 채워 8바이트 정렬
    | 배열들 (각각 8바이트 정렬, little-endian, C 순서)

머리말: {"format": 1, "meta": {...}, "arrays": [{"name", "dtype", "shape", "offset", "nbytes"}, ...]}
offset은 배열 영역 시작 기준. dtype은 uint8 int8 uint16 int16 float16 float32 중 하나.
브라우저에서는 DecompressionStream('gzip')으로 풀고 DataView/TypedArray로 바로 읽는다.
"""
from __future__ import annotations

import gzip
import json
import struct

import numpy as np

MAGIC = b'TSB1'
DTYPES = {'uint8', 'int8', 'uint16', 'int16', 'float16', 'float32'}


def _pad8(n: int) -> int:
    return (-n) % 8


def pack(meta: dict, arrays: dict[str, np.ndarray], level: int = 6) -> bytes:
    entries, chunks, offset = [], [], 0
    for name, a in arrays.items():
        a = np.ascontiguousarray(a)
        if a.dtype.name not in DTYPES:
            raise TypeError(f'{name}: {a.dtype} 는 묶음에 넣을 수 없다 ({sorted(DTYPES)})')
        raw = a.astype(a.dtype.newbyteorder('<'), copy=False).tobytes()
        entries.append({'name': name, 'dtype': a.dtype.name, 'shape': list(a.shape), 'offset': offset, 'nbytes': len(raw)})
        chunks.append(raw + b'\0' * _pad8(len(raw)))
        offset += len(raw) + _pad8(len(raw))
    head = json.dumps({'format': 1, 'meta': meta, 'arrays': entries}, ensure_ascii=False).encode('utf-8')
    body = MAGIC + struct.pack('<I', len(head)) + head
    body += b'\0' * _pad8(len(body))
    return gzip.compress(body + b''.join(chunks), compresslevel=level)


def unpack(blob: bytes) -> tuple[dict, dict[str, np.ndarray]]:
    data = gzip.decompress(blob)
    if data[:4] != MAGIC:
        raise ValueError('지도 묶음이 아니다')
    n = struct.unpack('<I', data[4:8])[0]
    head = json.loads(data[8:8 + n].decode('utf-8'))
    start = 8 + n + _pad8(8 + n)
    arrays = {}
    for e in head['arrays']:
        dt = np.dtype(e['dtype']).newbyteorder('<')
        a = np.frombuffer(data, dt, count=int(np.prod(e['shape'])) if e['shape'] else 1, offset=start + e['offset'])
        arrays[e['name']] = a.reshape(e['shape']).astype(dt.newbyteorder('='))
    return head['meta'], arrays
