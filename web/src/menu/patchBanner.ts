// 패치노트 배너 (960×540 캔버스, menu/lobby.ts showPatch): 게임 화면을 배경으로 깔고, 로비 제목과 같은 도트 글꼴 (widgets.pixelTitle)로
// PATCH NOTES · 버전 배지 · 한 줄 제목 · 부제 · 기능 태그 · 날짜를 얹는다. 버전마다 강조색, 도트 테두리, 최신이면 NEW 띠.

import { pixelTitle } from './widgets.ts';
import type { Patch } from './patchNotes.ts';

const W = 960, H = 540;
const INK = [30, 18, 10];

type RGB = number[];
const rgb = (c: RGB, a = 1) => `rgba(${c[0]},${c[1]},${c[2]},${a})`;

/** 도트 글자 한 줄 (pixelTitle: 그림자까지 들어간 캔버스)을 (x, y)에. 반환: 그린 넓이·높이. */
function text(g: CanvasRenderingContext2D, s: string, x: number, y: number, scale: number, col: RGB, maxW = Infinity) {
  let c = pixelTitle(s, scale, col);
  while (c.width > maxW && scale > 1) c = pixelTitle(s, --scale, col);   // 넘치면 한 단계 작게
  g.drawImage(c, Math.round(x), Math.round(y));
  return [c.width, c.height];
}

/** 도트 글자 여러 줄: scale에서 넘치면 낱말로 나눠 두 줄까지, 그래도 넘치면 한 단계 작게 (minScale까지). 반환: 높이. */
function title(g: CanvasRenderingContext2D, s: string, x: number, y: number, scale: number, col: RGB, maxW: number, minScale = 2) {
  for (let sc = scale; sc >= minScale; sc--) {
    const one = pixelTitle(s, sc, col);
    if (one.width <= maxW) { g.drawImage(one, x, y); return one.height; }
    const words = s.split(' ');
    for (let k = words.length - 1; k > 0; k--) {
      const a = pixelTitle(words.slice(0, k).join(' '), sc, col), b = pixelTitle(words.slice(k).join(' '), sc, col);
      if (a.width <= maxW && b.width <= maxW) {
        g.drawImage(a, x, y); g.drawImage(b, x, y + a.height - 11 * sc);   // 두 줄은 촘촘하게
        return a.height * 2 - 11 * sc;
      }
    }
  }
  const [, h] = text(g, s, x, y, minScale, col, maxW);
  return h;
}

/** 부제: 굵은 글꼴 (검은 테두리), maxW 안에서 줄바꿈. 반환: 높이. */
function caption(g: CanvasRenderingContext2D, s: string, x: number, y: number, col: RGB, maxW: number) {
  g.font = "bold 24px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";
  g.textBaseline = 'top';
  const lines: string[] = [];
  let cur = '';
  for (const w of s.split(' ')) { const t = cur ? cur + ' ' + w : w; if (g.measureText(t).width > maxW && cur) { lines.push(cur); cur = w; } else cur = t; }
  if (cur) lines.push(cur);
  lines.forEach((l, i) => {
    g.lineWidth = 5; g.strokeStyle = 'rgb(10,10,16)'; g.lineJoin = 'round'; g.strokeText(l, x, y + i * 32);
    g.fillStyle = rgb(col); g.fillText(l, x, y + i * 32);
  });
  return lines.length * 32;
}

/** 각진 도트 상자 (모서리를 한 칸씩 깎는다). */
function box(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, fill: string, edge: string, p = 4) {
  g.fillStyle = edge;
  g.fillRect(x + p, y, w - 2 * p, h); g.fillRect(x, y + p, w, h - 2 * p);
  g.fillStyle = fill;
  g.fillRect(x + p, y + p, w - 2 * p, h - 2 * p);
}

function draw(cv: HTMLCanvasElement, p: Patch, latest: boolean, bg: HTMLImageElement | null) {
  const g = cv.getContext('2d')!;
  g.imageSmoothingEnabled = false;
  const ac = p.accent ?? [255, 214, 120];
  // 배경: 게임 화면 (없으면 짙은 바탕에 강조색 빛)
  g.fillStyle = 'rgb(16,18,24)'; g.fillRect(0, 0, W, H);
  if (bg) {
    const ox = Math.round(W * (0.76 - (p.focus ?? 0.5)));              // 그림의 주인공 (focus)이 배너의 76% 자리에: 글자에 가리지 않게
    g.drawImage(bg, ox, 0, W, H);
    if (ox > 0) {                                                       // 그림 왼쪽 끝이 끊겨 보이지 않게: 바탕색으로 서서히 사라진다
      const f = g.createLinearGradient(ox, 0, ox + 260, 0);
      f.addColorStop(0, 'rgb(16,18,24)'); f.addColorStop(0.45, 'rgba(16,18,24,0.6)'); f.addColorStop(1, 'rgba(16,18,24,0)');
      g.fillStyle = f; g.fillRect(ox, 0, 260, H);
    }
  }
  else { const r = g.createRadialGradient(W * 0.75, H * 0.4, 20, W * 0.75, H * 0.4, 420); r.addColorStop(0, rgb(ac, 0.35)); r.addColorStop(1, 'rgba(0,0,0,0)'); g.fillStyle = r; g.fillRect(0, 0, W, H); }
  // 왼쪽 (글자 자리)만 어둡게: 58%까지 짙게, 72%에서 사라진다. 아래도 살짝
  const TX = W * 0.58;
  const lg = g.createLinearGradient(0, 0, W * 0.72, 0);
  lg.addColorStop(0, 'rgba(10,10,16,0.95)'); lg.addColorStop(0.7, 'rgba(10,10,16,0.82)'); lg.addColorStop(1, 'rgba(10,10,16,0)');
  g.fillStyle = lg; g.fillRect(0, 0, W * 0.72, H);
  const bgd = g.createLinearGradient(0, H * 0.7, 0, H);
  bgd.addColorStop(0, 'rgba(10,10,16,0)'); bgd.addColorStop(1, 'rgba(10,10,16,0.6)');
  g.fillStyle = bgd; g.fillRect(0, 0, W, H);
  // 왼쪽 강조색 세로 띠와 도트 줄무늬
  g.fillStyle = rgb(ac); g.fillRect(36, 40, 8, H - 80);
  g.fillStyle = rgb(ac, 0.35);
  for (let y = 40; y < H - 40; y += 8) g.fillRect(48, y, 4, 4);

  // 위: 날짜 + 버전 배지 / PATCH NOTES
  let y = 40;
  const [dw, dh] = text(g, p.date.replace(/-/g, '.'), 68, y, 2, [214, 208, 192]);
  const vb = pixelTitle(`v${p.version}`, 2, ac);                       // 버전 배지: 어두운 바탕에 강조색 글자
  box(g, 68 + dw + 14, y - 4, vb.width + 20, dh + 6, 'rgb(14,14,20)', rgb(ac));
  g.drawImage(vb, 68 + dw + 24, y - 1);
  y += dh + 8;
  const [, th] = text(g, 'PATCH NOTES', 64, y, 3, [255, 226, 150], TX);
  y += th;
  // 한 줄 제목 (도트 글자: 넘치면 두 줄, 그래도 넘치면 작게)과 부제 (굵은 글꼴, 줄바꿈)
  y += title(g, p.title ?? '', 66, y, 3, [250, 246, 236], TX - 66) + 4;
  if (p.sub) y += caption(g, p.sub, 72, y, ac, TX - 72) + 14;
  // 기능 태그 (글자 자리 안까지만)
  const TH = 40, GAP = 10;                                               // 태그: 도트 상자 + 굵은 글꼴 (한 줄에 서너 개), 넘치면 다음 줄로
  g.font = "bold 21px 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif";
  g.textBaseline = 'middle';
  const rows: [string, number][][] = [[]];
  let x = 68;
  for (const t of p.tags ?? []) {
    const w = Math.ceil(g.measureText(t).width) + 26;
    if (x + w > TX + 30 && rows[rows.length - 1].length) { rows.push([]); x = 68; }
    rows[rows.length - 1].push([t, w]);
    x += w + 10;
  }
  y = Math.min(y, H - 64 - rows.length * (TH + GAP) + GAP);              // 아래 끝에서 64 넘게 띄운다
  for (const row of rows) {
    x = 68;
    for (const [t, w] of row) {
      box(g, x, y, w, TH, 'rgba(10,10,16,0.82)', rgb(ac));
      g.lineWidth = 4; g.strokeStyle = 'rgb(10,10,16)'; g.lineJoin = 'round';
      g.strokeText(t, x + 13, y + TH / 2 + 1);
      g.fillStyle = 'rgb(250,246,236)'; g.fillText(t, x + 13, y + TH / 2 + 1);
      x += w + 10;
    }
    y += TH + GAP;
  }
  // 최신: 오른쪽 위 NEW 띠 (비스듬히)
  if (latest) {
    g.save();
    g.translate(W - 90, 70);
    g.rotate(Math.PI / 4);
    g.fillStyle = 'rgb(10,10,14)'; g.fillRect(-150, -26, 300, 52);
    g.fillStyle = rgb(ac); g.fillRect(-150, -22, 300, 44);
    const nc = pixelTitle('NEW', 2, INK);
    g.drawImage(nc, -nc.width / 2, -nc.height / 2);
    g.restore();
  }
  // 도트 테두리: 바깥 검정, 안쪽 금빛 한 줄, 네 모서리 장식
  g.fillStyle = 'rgb(10,10,14)';
  g.fillRect(0, 0, W, 8); g.fillRect(0, H - 8, W, 8); g.fillRect(0, 0, 8, H); g.fillRect(W - 8, 0, 8, H);
  g.fillStyle = rgb(ac, 0.9);
  g.fillRect(14, 14, W - 28, 3); g.fillRect(14, H - 17, W - 28, 3); g.fillRect(14, 14, 3, H - 28); g.fillRect(W - 17, 14, 3, H - 28);
  for (const [cx, cy] of [[14, 14], [W - 30, 14], [14, H - 30], [W - 30, H - 30]]) { g.fillRect(cx, cy, 16, 16); g.fillStyle = 'rgb(10,10,14)'; g.fillRect(cx + 5, cy + 5, 6, 6); g.fillStyle = rgb(ac, 0.9); }
}

/** 배너 캔버스: 바로 글자를 그리고, 배경 그림이 오면 다시 그린다. */
export function patchBanner(p: Patch, latest: boolean): HTMLCanvasElement {
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  cv.className = 'patch-img';
  draw(cv, p, latest, null);
  if (p.image) {
    const img = new Image();
    img.onload = () => draw(cv, p, latest, img);
    img.src = p.image;
  }
  return cv;
}
