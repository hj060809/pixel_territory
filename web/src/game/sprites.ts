// 픽셀 스프라이트 (데스크톱 game/sprites.py의 SpriteBank를 옮겼다).
// - 어떤 지형 위에서도 보이게 어두운 1칸 테두리. 병사는 걷는 동안 다리가 번갈아 움직인다 (2프레임).
// - 건물은 지붕/깃발에 나라 색, 짓는 중이면 반투명. 배는 왼쪽으로 갈 때 뒤집는다.

import { SPRITES } from './spriteData.ts';

type Img = HTMLCanvasElement;
const dark = (c: readonly number[], k = 0.6) => c.map((v) => Math.trunc(v * k));

function make(rows: readonly string[], color: readonly number[], alpha = 255): Img {
  const pal: Record<string, readonly number[]> = { ...SPRITES.pal, n: color, N: dark(color) };
  const h = rows.length, w = rows[0].length;
  const c = document.createElement('canvas');
  c.width = w + 2;
  c.height = h + 2;
  const g = c.getContext('2d')!;
  const img = g.createImageData(w + 2, h + 2);
  const filled = (x: number, y: number) => y >= 0 && y < h && x >= 0 && x < w && rows[y][x] !== '.';
  const put = (x: number, y: number, col: readonly number[]) => {
    const i = (y * (w + 2) + x) * 4;
    img.data[i] = col[0]; img.data[i + 1] = col[1]; img.data[i + 2] = col[2]; img.data[i + 3] = alpha;
  };
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    if (!filled(x, y)) continue;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      if (!filled(x + dx, y + dy)) put(x + dx + 1, y + dy + 1, SPRITES.outline);
    }
  }
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) if (filled(x, y)) put(x + 1, y + 1, pal[rows[y][x]]);
  g.putImageData(img, 0, 0);
  return c;
}

function scaled(src: Img, k: number, flip = false): Img {
  if (k === 1 && !flip) return src;
  const c = document.createElement('canvas');
  c.width = src.width * k;
  c.height = src.height * k;
  const g = c.getContext('2d')!;
  g.imageSmoothingEnabled = false;
  if (flip) { g.translate(c.width, 0); g.scale(-1, 1); }
  g.drawImage(src, 0, 0, c.width, c.height);
  return c;
}

export class SpriteBank {
  private cache = new Map<string, Img>();
  constructor(private colors: number[][]) {}

  private get(key: string, build: () => Img): Img {
    let s = this.cache.get(key);
    if (!s) { s = build(); this.cache.set(key, s); }
    return s;
  }

  unit(kind: number, nid: number, frame: number, k: number, flip = false): Img {
    return this.get(`u${kind},${nid},${frame},${k},${flip}`,
      () => scaled(make(SPRITES.units[kind][frame], this.colors[nid]), k, flip));
  }

  building(kind: number, nid: number, k: number, ghost = false): Img {
    return this.get(`b${kind},${nid},${k},${ghost}`,
      () => scaled(make((SPRITES.buildings as any)[kind], this.colors[nid], ghost ? 120 : 255), k));
  }

  ship(kind: 'ferry' | 'warship', nid: number, k: number, left = false): Img {
    return this.get(`s${kind},${nid},${k},${left}`, () => scaled(make(SPRITES.ships[kind], this.colors[nid]), k, left));
  }

  site(kind: number, k: number): Img {
    return this.get(`t${kind},${k}`, () => scaled(make((SPRITES.sites as any)[kind], [0, 0, 0], 200), k));
  }

  static buildingWidth(kind: number): number { return (SPRITES.buildings as any)[kind][0].length; }
}
