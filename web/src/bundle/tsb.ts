// 지도 묶음(.tsb) 읽기. 형식은 engine/bake/container.py 참고:
//   gzip( 'TSB1' | u32 머리말 길이 | 머리말 JSON | 8바이트 정렬 | 배열들(각각 8바이트 정렬, little-endian) )

export type Arr = Uint8Array | Int8Array | Uint16Array | Int16Array | Float32Array;

export interface BundleArray {
  data: Arr;
  shape: number[];
}

export interface Bundle {
  meta: any;
  arrays: Record<string, BundleArray>;
}

/** float16 비트 → float32 값 (모든 브라우저에서 되게 직접 푼다). */
export function halfToFloat(h: number): number {
  const s = h & 0x8000 ? -1 : 1;
  const e = (h >> 10) & 0x1f;
  const f = h & 0x3ff;
  if (e === 0) return s * f * 2 ** -24;
  if (e === 31) return f ? NaN : s * Infinity;
  return s * (1 + f / 1024) * 2 ** (e - 15);
}

export async function gunzip(buf: ArrayBuffer): Promise<ArrayBuffer> {
  const stream = new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'));
  return await new Response(stream).arrayBuffer();
}

export function parseBundle(raw: ArrayBuffer): Bundle {
  const bytes = new Uint8Array(raw);
  const magic = String.fromCharCode(...bytes.subarray(0, 4));
  if (magic !== 'TSB1') throw new Error('지도 묶음이 아니다');
  const n = new DataView(raw).getUint32(4, true);
  const head = JSON.parse(new TextDecoder().decode(bytes.subarray(8, 8 + n)));
  let start = 8 + n;
  start += (8 - (start % 8)) % 8;
  const arrays: Record<string, BundleArray> = {};
  for (const e of head.arrays) {
    const off = start + e.offset;
    const count = e.shape.reduce((a: number, b: number) => a * b, 1);
    let data: Arr;
    switch (e.dtype) {
      case 'uint8': data = new Uint8Array(raw, off, count); break;
      case 'int8': data = new Int8Array(raw, off, count); break;
      case 'uint16': data = new Uint16Array(raw, off, count); break;
      case 'int16': data = new Int16Array(raw, off, count); break;
      case 'float32': data = new Float32Array(raw, off, count); break;
      case 'float16': {
        const h = new Uint16Array(raw, off, count);
        const f = new Float32Array(count);
        for (let i = 0; i < count; i++) f[i] = halfToFloat(h[i]);
        data = f;
        break;
      }
      default: throw new Error(`모르는 자료형 ${e.dtype}`);
    }
    arrays[e.name] = { data, shape: e.shape };
  }
  return { meta: head.meta, arrays };
}

export async function loadBundle(url: string): Promise<Bundle> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`지도 묶음을 받지 못했다: ${r.status}`);
  return parseBundle(await gunzip(await r.arrayBuffer()));
}
