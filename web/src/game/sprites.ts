// 그림 묶음: 유닛·건물·배·동물은 스프라이트 스태킹 (stack.ts, 아이콘은 정오 빛), 자원지 표시는 납작한 픽셀 그림.
// 게임 화면은 stack으로 지금 빛·방향에 맞춰 그리고, 버튼·로비·설정 화면은 아래 함수(아이콘)를 쓴다.

import { SPRITES } from './spriteData.ts';
import { StackRenderer } from './stack.ts';
import { model } from './models.ts';

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
  readonly stack: StackRenderer;
  constructor(colors: number[][]) { this.stack = new StackRenderer(colors); }

  private get(key: string, build: () => Img): Img {
    let s = this.cache.get(key);
    if (!s) { s = build(); this.cache.set(key, s); }
    return s;
  }

  /** 병사 아이콘 (조금 비스듬히 앞을 본다. flip: 왼쪽). */
  unit(kind: number, nid: number, frame: number, k: number, flip = false): Img {
    return this.stack.icon(`u${kind}`, nid, k, { frame, dir: flip ? 7 : 1 });
  }

  building(kind: number, nid: number, k: number, ghost = false): Img {
    const img = this.stack.icon(`b${kind}`, nid, k, { dirs: 4 });
    if (!ghost) return img;
    return this.get(`g${kind},${nid},${k}`, () => {
      const c = document.createElement('canvas');
      c.width = img.width; c.height = img.height;
      const g = c.getContext('2d')!;
      g.globalAlpha = 0.5;
      g.drawImage(img, 0, 0);
      return c;
    });
  }

  ship(kind: 'ferry' | 'warship', nid: number, k: number, left = false): Img {
    return this.stack.icon(kind, nid, k, { dir: left ? 7 : 1 });
  }

  /** 야생 동물 (나라 색 없음). frame: 0 서 있기, 1 달리기, 2 풀 뜯기, 3 앞발 들기. */
  animal(name: 'horse', frame: number, k: number, flip = false): Img {
    return this.stack.icon(name, 0, k, { frame, dir: flip ? 7 : 1 });
  }

  /** 자원지 표시. snow: 눈 덮인 숲 (하얀 나무). */
  site(kind: number, k: number, snow = false): Img {
    const key = snow ? `${kind}s` : `${kind}`;
    return this.get(`t${key},${k}`, () => scaled(make((SPRITES.sites as any)[key], [0, 0, 0], 200), k));
  }

  static buildingWidth(kind: number): number { return model(`b${kind}`).W; }
}
