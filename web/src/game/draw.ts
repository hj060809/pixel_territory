// 지도 위 물체 그리기 (Canvas 2D, 화면 픽셀): 데스크톱 game/app.py의 _draw_sites / _draw_buildings / _draw_boats /
// _draw_units / _draw_badges / _draw_shots / _draw_pings / _draw_ghost를 옮겼다. 위치는 상태 사이를 보간한 값.

import type { Camera } from '../sim/camera.ts';
import { type Controller, UNIT_ZOOM } from './controller.ts';
import { F_OCEAN } from './terrainRules.ts';
import type { BuildRec } from './protocol.ts';
import { SpriteBank } from './sprites.ts';
import { type GameState, lerp } from './state.ts';

const WAKE = 'rgb(236,244,248)';
const SEL = 'rgb(240,250,240)';
const MOVING_BOAT = new Set([1, 2, 3, 5, 6, 8]);     // move hunt pickup cross return ahead

export class Overlay {
  constructor(private g: CanvasRenderingContext2D, private bank: SpriteBank, private st: GameState,
              private ctl: Controller) {}

  private text(s: string, x: number, y: number, size: number, col: string, bold = false,
               align: CanvasTextAlign = 'left', base: CanvasTextBaseline = 'middle') {
    const g = this.g;
    g.font = `${bold ? 'bold ' : ''}${size}px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif`;
    g.textAlign = align; g.textBaseline = base;
    g.lineWidth = 2; g.strokeStyle = 'black'; g.strokeText(s, x, y);
    g.fillStyle = col; g.fillText(s, x, y);
  }

  private bar(cx: number, y: number, w: number, frac: number, col?: string) {
    frac = Math.min(Math.max(frac, 0), 1);
    col ??= `rgb(${Math.trunc(230 - 150 * frac)},${Math.trunc(70 + 160 * frac)},60)`;
    const x0 = Math.trunc(cx - w / 2), g = this.g;
    g.fillStyle = 'rgb(20,20,24)'; g.fillRect(x0 - 1, y - 1, w + 2, 4);
    g.fillStyle = col; g.fillRect(x0, y, Math.trunc(w * frac), 2);
  }

  /** 픽셀 말풍선: 어두운 1칸 테두리, 밝은 바탕, 아래로 계단 꼬리. 안에 대기열 병사 아이콘 (최대 5). */
  private bubble(b: BuildRec, cx: number, top: number, z: number) {
    const g = this.g, R = this.st.info.rules;
    const items: number[] = [];
    for (let k = 0; k < 5; k++) { const c = (b.qbits >> (2 * k)) & 3; if (c) items.push(c - 1); }
    if (!items.length) return;
    const p = Math.max(1, Math.round(z / 2.6));                 // 말풍선 픽셀 한 칸
    const icons = items.map((kind) => this.bank.unit(kind === 2 ? 0 : kind, b.own, 0, p));
    const iw = icons[0].width, ih = icons[0].height, gap = p;
    const w = icons.length * iw + (icons.length - 1) * gap + 4 * p, h = ih + 6 * p;
    const x0 = Math.round(cx - w / 2), y0 = Math.round(top - h - 4 * p);
    const ink = 'rgb(26,24,30)', paper = 'rgb(244,238,222)';
    g.fillStyle = ink;                                           // 테두리 (모서리는 한 칸 깎는다)
    g.fillRect(x0 + p, y0, w - 2 * p, h);
    g.fillRect(x0, y0 + p, w, h - 2 * p);
    g.fillStyle = paper;
    g.fillRect(x0 + p, y0 + p, w - 2 * p, h - 2 * p);
    const tx = Math.round(cx - p);                               // 꼬리: 두 계단
    g.fillStyle = ink; g.fillRect(tx - p, y0 + h - p, 4 * p, p); g.fillRect(tx, y0 + h, 2 * p, p); g.fillRect(tx + p, y0 + h + p, p, p);
    g.fillStyle = paper; g.fillRect(tx, y0 + h - p, 2 * p, p); g.fillRect(tx + p, y0 + h, p, p);
    icons.forEach((img, i) => g.drawImage(img, x0 + 2 * p + i * (iw + gap), y0 + 2 * p));
    const total = items[0] === 2 ? R.warship_time : R.unit_time[items[0]];   // 맨 앞: 훈련 진행 막대
    const f = Math.min(Math.max(1 - b.qtime / total, 0), 1);
    g.fillStyle = 'rgb(200,192,170)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, iw, p);
    g.fillStyle = 'rgb(90,170,90)'; g.fillRect(x0 + 2 * p, y0 + h - 3 * p, Math.max(p, Math.round(iw * f)), p);
  }

  private docks = new Map<number, [number, number] | null>();

  /** 전함을 짓는 자리: 항구 앞 물 칸(서버 Fleet.dock_of와 같은 규칙: 9칸 안의 가장 가까운 바다)에서
   *  바다 쪽으로 몇 칸 더 나간 곳 (항구 그림과 겹치지 않게). */
  private dock(b: BuildRec): [number, number] | null {
    const key = b.slot * 65536 + b.gen;
    if (this.docks.has(key)) return this.docks.get(key)!;
    const m = this.ctl.rules, y = Math.floor(b.y), x = Math.floor(b.x), r = 9;
    let best: [number, number] | null = null, bd = Infinity;
    for (let yy = Math.max(y - r, 0); yy <= Math.min(y + r, m.H - 1); yy++) {
      for (let xx = Math.max(x - r, 0); xx <= Math.min(x + r, m.W - 1); xx++) {
        if (!(m.at(yy, xx) & F_OCEAN)) continue;
        const d = (yy - y) ** 2 + (xx - x) ** 2;
        if (d < bd) { bd = d; best = [yy, xx]; }
      }
    }
    if (best) {                                                  // 항구 → 물 칸 방향으로 더 나가 바다인 곳
      const r0 = this.st.info.rules.build[b.kind].r, dy = best[0] - y, dx = best[1] - x, n = Math.hypot(dy, dx) || 1;
      for (let t = r0 + 6; t >= Math.hypot(dy, dx); t--) {
        const yy = Math.round(y + (dy / n) * t), xx = Math.round(x + (dx / n) * t);
        if (yy >= 0 && yy < m.H && xx >= 0 && xx < m.W && m.at(yy, xx) & F_OCEAN) { best = [yy, xx]; break; }
      }
    }
    this.docks.set(key, best);
    return best;
  }

  /** 항구 앞 바다에서 전함을 짓는 중: 흐린 윤곽 위로 아래부터 차오르는 배, 비계, 반짝이는 망치질. */
  private shipyard(b: BuildRec, sx: (x: number) => number, sy: (y: number) => number, z: number, now: number) {
    const d = this.dock(b);
    if (!d) return;
    const g = this.g, R = this.st.info.rules;
    const f = Math.min(Math.max(1 - b.qtime / R.warship_time, 0), 1);
    const k = Math.max(1, Math.round(z * 0.55));
    const img = this.bank.ship('warship', b.own, k);
    const x = Math.round(sx(d[1] + 0.5) - img.width / 2), y = Math.round(sy(d[0] + 0.5) + k - img.height);
    g.globalAlpha = 0.28;                                        // 다 지은 모습의 흐린 윤곽
    g.drawImage(img, x, y);
    g.globalAlpha = 1;
    const fill = Math.round(img.height * (0.15 + 0.85 * f));     // 아래(배 밑)부터 차오른다
    g.drawImage(img, 0, img.height - fill, img.width, fill, x, y + img.height - fill, img.width, fill);
    g.fillStyle = 'rgb(150,112,70)';                             // 비계: 양옆 기둥과 짓는 높이의 가로대
    const line = y + img.height - fill;
    g.fillRect(x - k, line, k, img.height - (line - y));
    g.fillRect(x + img.width, line, k, img.height - (line - y));
    g.fillRect(x - k, line, img.width + 2 * k, k);
    if (Math.floor(now / 180) % 3 !== 0) {                       // 망치질 반짝임
      const sxp = x + ((Math.floor(now / 540) * 7) % Math.max(1, img.width - k));
      g.fillStyle = 'rgb(255,236,170)';
      g.fillRect(sxp, line - k, k, k);
    }
    if (b.qlen > 1) this.text(`+${b.qlen - 1}`, x + img.width + 2 * k, y + 2, 11, 'rgb(255,240,200)');
  }

  private bscale(kind: number, z: number) {
    return Math.max(1, Math.round((z * 2 * this.st.info.rules.build[kind].r) / SpriteBank.buildingWidth(kind)));
  }

  draw(cam: Camera, now: number, mouse: [number, number] | null, box: [number, number, number, number] | null) {
    const g = this.g, st = this.st, z = cam.zoom, R = st.info.rules, me = st.info.me;
    const W = cam.viewW, H = cam.viewH;
    const sx = (x: number) => (x - cam.x) * z, sy = (y: number) => (y - cam.y) * z;
    const vis = (x: number, y: number, pad = 40) => x >= -pad && x <= W + pad && y >= -pad && y <= H + pad;
    const a = st.alpha(now), t = st.smoothTime(now);
    g.imageSmoothingEnabled = false;
    this.ctl.prune();

    // 자원지 (확대할수록 커진다. 멀리서도 2배 아래로는 줄지 않는다)
    const taken = st.siteTaken(), ks = Math.max(2, Math.round(z * 0.6));
    for (const s of st.info.sites) {
      if (taken.has(s.id)) continue;
      const x = sx(s.x), y = sy(s.y);
      if (!vis(x, y)) continue;
      const img = this.bank.site(s.kind, ks);
      g.drawImage(img, Math.round(x - img.width / 2), Math.round(y - img.height / 2));
    }
    // 건물
    const selB = this.ctl.selB;
    const bubbles: [BuildRec, number, number][] = [];       // 말풍선 (병사들 위에 그리려고 나중에)
    const yards: BuildRec[] = [];
    for (const b of [...st.builds.values()].sort((p, q) => p.y - q.y)) {
      const x = sx(b.x), y = sy(b.y);
      if (!vis(x, y, 80)) continue;
      const done = b.prog >= 1, r = R.build[b.kind].r;
      const img = this.bank.building(b.kind, b.own, this.bscale(b.kind, z), !done);
      const rx = Math.round(x - img.width / 2), ry = Math.round(y + r * z * 0.6 - img.height);
      g.drawImage(img, rx, ry);
      if (selB && selB[0] === b.slot) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(rx - 2.5, ry - 2.5, img.width + 4, img.height + 4); }
      const bw = Math.max(img.width, 14);
      if (!done) this.bar(rx + img.width / 2, ry + img.height + 3, bw, b.prog, 'rgb(120,200,255)');
      else if (b.hp < 0.999) this.bar(rx + img.width / 2, ry - 4, bw, b.hp);
      if (done && b.kind === R.kinds.HALL && b.qlen && b.own === me) {
        if (z >= UNIT_ZOOM) bubbles.push([b, rx + img.width / 2, ry]);   // 가까이: 말풍선에 대기열 병사 아이콘
        else this.text(`${b.qlen}`, rx + img.width + 2, ry + 4, 12, 'rgb(255,240,200)');
      }
      if (done && b.kind === R.kinds.HARBOR && b.qlen && b.qkind === 2) yards.push(b);
    }
    for (const b of yards) this.shipyard(b, sx, sy, z, now);    // 항구 앞바다의 전함 건조 (건물에 가리지 않게 나중에)
    // 배
    const kb = Math.max(1, Math.round(z * 0.55));
    for (const b of st.boats.values()) {
      if (b.bits & 1) continue;                                     // 아직 항구에서 출발 전
      const bx = lerp(b.px, b.x, a), by = lerp(b.py, b.y, a), x = sx(bx), y = sy(by);
      if (!vis(x, y, 60)) continue;
      const ferry = b.kind === 0;
      const img = this.bank.ship(ferry ? 'ferry' : 'warship', b.own, kb, b.dir < 0);
      const bob = ferry && Math.trunc(t * 2 + bx) % 2 ? 1 : 0;      // 살짝 출렁인다
      const rx = Math.round(x - img.width / 2), ry = Math.round(y + 2 * kb + bob - img.height);
      if (MOVING_BOAT.has(b.state)) {                                // 지나간 물보라
        g.fillStyle = WAKE;
        for (const k of [1, 2]) g.fillRect(rx + img.width / 2 - b.dir * (img.width / 2 + k * 3 * kb), ry + img.height - kb - k * kb, kb, kb);
      }
      g.drawImage(img, rx, ry);
      if (this.ctl.selShips.has(b.id)) { g.strokeStyle = SEL; g.lineWidth = 1; g.strokeRect(rx - 2.5, ry - 2.5, img.width + 4, img.height + 4); }
      if (b.hp < 0.999) this.bar(rx + img.width / 2, ry - 4, Math.max(img.width, 12), b.hp);
      if (ferry && b.cargo) this.text(`${b.cargo}`, rx + img.width + 2, ry + img.height / 2, 12, 'white', true);
    }
    // 병사: 가까이서는 하나하나, 멀리서는 무리 배지
    const units = [...st.units.values()].filter((u) => !(u.bits & 2));
    if (z >= UNIT_ZOOM) {
      const k = z < 4.5 ? 2 : z < 8 ? 3 : 4;
      const list = units.map((u) => ({ u, x: sx(lerp(u.px, u.x, a)), y: sy(lerp(u.py, u.y, a)) }))
        .filter((p) => p.x > -20 && p.x < W + 20 && p.y > -20 && p.y < H + 20).sort((p, q) => p.y - q.y);
      for (const { u, x, y } of list) {
        const frame = u.bits & 1 ? Math.trunc(t * 4.5 * 1.2 + u.slot * 0.37) % 2 : 0;   // 걸을 때 다리
        const img = this.bank.unit(u.kind, u.own, frame, k);
        const rx = Math.round(x - img.width / 2), ry = Math.round(y + 1 - img.height);
        if (this.ctl.sel.has(u.slot)) { g.strokeStyle = 'rgb(235,250,235)'; g.lineWidth = 1; g.beginPath(); g.moveTo(rx, ry + img.height + 1.5); g.lineTo(rx + img.width, ry + img.height + 1.5); g.stroke(); }
        g.drawImage(img, rx, ry);
        if (u.hp < 0.99) this.bar(rx + img.width / 2, ry - 3, img.width - 2, u.hp);
      }
    } else {
      const cell = 34, groups = new Map<string, { own: number; n: number; x: number; y: number; sel: boolean }>();
      for (const u of units) {
        const x = sx(lerp(u.px, u.x, a)), y = sy(lerp(u.py, u.y, a));
        const key = `${u.own},${Math.floor(y / cell)},${Math.floor(x / cell)}`;
        const e = groups.get(key) ?? { own: u.own, n: 0, x: 0, y: 0, sel: false };
        e.n++; e.x += x; e.y += y; e.sel ||= this.ctl.sel.has(u.slot);
        groups.set(key, e);
      }
      const list = [...groups.values()].map((e) => ({ ...e, x: e.x / e.n, y: e.y / e.n })).sort((p, q) => p.y - q.y);
      for (const e of list) {
        if (!vis(e.x, e.y)) continue;
        g.font = `bold 12px 'Malgun Gothic', sans-serif`;
        const w = Math.max(g.measureText(`${e.n}`).width + 8, 16), h = 15;
        const x0 = e.x - w / 2, y0 = e.y - h / 2;
        g.fillStyle = 'rgb(20,18,24)'; roundRect(g, x0 - 1, y0 - 1, w + 2, h + 2, 4); g.fill();
        const c = st.info.nations[e.own].color;
        g.fillStyle = `rgb(${c[0]},${c[1]},${c[2]})`; roundRect(g, x0, y0, w, h, 4); g.fill();
        if (e.sel) { g.strokeStyle = 'rgb(240,255,240)'; g.lineWidth = 1; roundRect(g, x0 - 2.5, y0 - 2.5, w + 5, h + 5, 5); g.stroke(); }
        this.text(`${e.n}`, e.x, e.y + 1, 12, 'white', true, 'center');
      }
    }
    // 공격: 화살(날아가는 짧은 선), 포탄(검은 점 → 물보라), 칼부림(반짝)
    for (const s of st.shots) {
      const age = (t - s.t0) / 0.3;
      const ax = sx(s.x0), ay = sy(s.y0), bx = sx(s.x1), by = sy(s.y1);
      if (s.kind >= 2) {
        const f = Math.min(age * 1.3, 1.0);
        if (f < 1) {
          g.fillStyle = 'rgb(30,28,34)'; g.beginPath();
          g.arc(ax + (bx - ax) * f, ay + (by - ay) * f - 6 * z * f * (1 - f), Math.max(1, Math.trunc(z * 0.45)), 0, 7); g.fill();
        } else { g.strokeStyle = WAKE; g.lineWidth = 1; g.beginPath(); g.arc(bx, by, Math.max(2, Math.trunc(z)), 0, 7); g.stroke(); }
      } else if (s.kind >= 1) {
        const f = Math.min(Math.max(age, 0) * 1.6, 1.0), h = Math.max(f - 0.15, 0.0);
        g.strokeStyle = 'rgb(236,226,196)'; g.lineWidth = 1; g.beginPath();
        g.moveTo(ax + (bx - ax) * h, ay + (by - ay) * h); g.lineTo(ax + (bx - ax) * f, ay + (by - ay) * f); g.stroke();
      } else if (age < 0.5) {
        g.fillStyle = 'rgb(255,250,230)'; g.beginPath(); g.arc(bx, by - 2 * z, Math.max(1, Math.trunc(z * 0.5)), 0, 7); g.fill();
      }
    }
    // 거점 위 말풍선: 대기열에 있는 병사 아이콘 (맨 앞은 훈련 진행 막대)
    for (const [b, cx, top] of bubbles) this.bubble(b, cx, top, z);
    // 명령 표시
    this.ctl.pings = this.ctl.pings.filter((p) => now - p.t0 < 600);
    for (const p of this.ctl.pings) {
      const f = (now - p.t0) / 600;
      g.strokeStyle = p.col; g.lineWidth = 1; g.beginPath(); g.arc(Math.trunc(sx(p.x)), Math.trunc(sy(p.y)), Math.trunc(4 + 10 * f), 0, 7); g.stroke();
    }
    // 드래그 상자
    if (box) { g.strokeStyle = 'rgb(230,240,230)'; g.lineWidth = 1; g.strokeRect(Math.min(box[0], box[2]) + 0.5, Math.min(box[1], box[3]) + 0.5, Math.abs(box[2] - box[0]), Math.abs(box[3] - box[1])); }
    // 건물 자리 미리보기
    const mode = this.ctl.mode;
    if (mouse && typeof mode === 'number') {                     // 놓을 건물이 커서에 (자원지 건물은 빈 자원지에 붙는다)
      const kind = mode;
      const [mx, my] = cam.toMap(mouse[0], mouse[1]);
      const t = this.ctl.placeTarget(kind, mx, my, z);
      const ok = t.ok;
      const px = t.ok ? sx(t.x) : mouse[0], py = t.ok ? sy(t.y) : mouse[1];
      const img = this.bank.building(kind, me, this.bscale(kind, z), true);
      const rx = Math.round(px - img.width / 2), ry = Math.round(py + R.build[kind].r * z * 0.6 - img.height);
      g.drawImage(img, rx, ry);
      g.strokeStyle = ok ? 'rgb(120,230,120)' : 'rgb(230,90,80)'; g.lineWidth = 1; g.strokeRect(rx - 2.5, ry - 2.5, img.width + 4, img.height + 4);
    }
  }
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.roundRect(x, y, w, h, r);
}
