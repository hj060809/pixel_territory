// 로비 배경 (데스크톱 game/menu.py의 LobbyArt.draw를 옮겼다).
// 서버가 고른 지형 조각을 크게 확대하고 천천히 좌우로 흘리며, 그 위에 반짝임 → 배(물보라) → 건물과 병사(위에서 아래 순서)를 얹는다.
// 장식일 뿐이라 게임 계산은 하지 않는다.

import { SpriteBank } from '../game/sprites.ts';

export interface LobbyInfo {
  map: string;
  w: number; h: number; cw: number; margin: number;
  buildings: { kind: number; nat: number; y: number; x: number }[];
  walkers: { kind: number; nat: number; a: number[]; b: number[]; speed: number; phase: number }[];
  ships: { kind: 'ferry' | 'warship'; nat: number; a: number[]; b: number[]; speed: number; phase: number }[];
  sparkles: number[][];
  colors: [string, number[], number[]][];
  difficulty: string[];
  rules: any;
}

export class LobbyArt {
  ready = false;
  info: LobbyInfo | null = null;
  bank: SpriteBank | null = null;
  private img: HTMLImageElement | null = null;
  private t0 = performance.now();

  /** 서버에서 배치와 조각 그림을 받는다. 실패해도 로비는 뜬다 (어두운 배경). */
  async load(): Promise<LobbyInfo | null> {
    try {
      const info: LobbyInfo = await (await fetch('/api/lobby')).json();
      const img = new Image();
      img.src = '/api/lobby.png';
      await img.decode();
      this.info = info;
      this.img = img;
      this.bank = new SpriteBank(info.colors.map((c) => c[1]));
      this.ready = true;
      this.t0 = performance.now();
      return info;
    } catch (e) {
      console.warn('로비 배경 실패:', e);
      return null;
    }
  }

  /** W, H: CSS 픽셀. g는 이미 장치 배율로 변환된 상태. */
  draw(g: CanvasRenderingContext2D, W: number, H: number) {
    g.imageSmoothingEnabled = false;
    if (!this.ready || !this.info || !this.img || !this.bank) {
      g.fillStyle = 'rgb(14,16,22)';
      g.fillRect(0, 0, W, H);
      return;
    }
    const a = this.info, bank = this.bank, R = a.rules;
    const ch = a.h, cw = a.w;
    // 정수 배율 (도트가 고르게): 높이와 폭을 모두 덮는다. 폭은 흘러갈 여유의 절반을 남겨 두고 맞춘다 (넓은 창에서도 빈 곳 없이).
    const Z = Math.max(2, Math.ceil(H / ch), Math.ceil(W / (cw - a.margin / 2)));
    const t = (performance.now() - this.t0) / 1000;
    const span = Math.max(cw * Z - W, 0);
    const ox = span * (0.5 + 0.5 * Math.sin(t * 0.03 - Math.PI / 2));     // 천천히 좌우로 흘러간다
    const oy = (ch * Z - H) / 2;
    g.fillStyle = 'rgb(14,16,22)';
    g.fillRect(0, 0, W, H);
    g.drawImage(this.img, -ox, -oy, cw * Z, ch * Z);
    const to = (y: number, x: number): [number, number] => [x * Z - ox, y * Z - oy];
    const blit = (img: HTMLCanvasElement, cx: number, bottom: number) =>
      g.drawImage(img, Math.trunc(cx - img.width / 2), Math.trunc(bottom - img.height));
    // 물 위 반짝임
    g.fillStyle = 'rgb(236,246,250)';
    const sp = Math.max(2, Math.floor(Z / 3));
    for (const [y, x, ph, s] of a.sparkles) {
      if (Math.sin(t * s * 2 + ph) > 0.82) { const [sx, sy] = to(y, x); g.fillRect(Math.trunc(sx), Math.trunc(sy), sp, sp); }
    }
    // 배와 지나간 물보라
    for (const s of a.ships) {
      const f = (t * s.speed + s.phase) % 2.0, k = f < 1 ? f : 2 - f;
      const y = s.a[0] + (s.b[0] - s.a[0]) * k, x = s.a[1] + (s.b[1] - s.a[1]) * k;
      const img = bank.ship(s.kind, s.nat, Math.max(2, Math.round(Z * 0.6)), f >= 1);
      const [sx, sy] = to(y, x);
      const cx = Math.trunc(sx), bottom = Math.trunc(sy + Z), d = f >= 1 ? -1 : 1, half = Math.floor(Z / 2);
      g.fillStyle = 'rgb(236,244,248)';
      for (const j of [1, 2]) g.fillRect(Math.trunc(cx - d * (img.width / 2 + j * Z)), bottom - half - j * 2, half, half);
      blit(img, cx, bottom);
    }
    // 건물과 병사: 아래쪽에 있는 것이 앞에
    type Item = { y: number; draw: () => void };
    const items: Item[] = a.buildings.map((b) => ({
      y: b.y,
      draw: () => {
        const r = R.build[b.kind].r;
        const k = Math.max(1, Math.round((Z * 2 * r) / SpriteBank.buildingWidth(b.kind)));
        const [sx, sy] = to(b.y, b.x);
        blit(bank.building(b.kind, b.nat, k), sx, sy + r * Z * 0.6);
      },
    }));
    for (const w of a.walkers) {
      const f = w.speed ? (t * w.speed + w.phase) % 2.0 : 0, k = f < 1 ? f : 2 - f;
      const y = w.a[0] + (w.b[0] - w.a[0]) * k, x = w.a[1] + (w.b[1] - w.a[1]) * k;
      const moving = w.speed > 0;
      const frame = moving ? Math.trunc(t * 5 + w.phase * 10) % 2 : 0;
      items.push({
        y,
        draw: () => {
          const img = bank.unit(w.kind, w.nat, frame, Math.max(2, Math.round(Z * 0.45)), moving && f >= 1);
          const [sx, sy] = to(y, x);
          blit(img, sx, sy);
        },
      });
    }
    items.sort((p, q) => p.y - q.y);
    for (const it of items) it.draw();
  }
}
