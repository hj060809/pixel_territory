// 메뉴 화면 부품: 데스크톱 game/menu.py의 UI(버튼, 입력 칸)와 도트 제목, 왼쪽 그늘.
// 모양은 style.css의 .btn / .field (어두운 테두리, 위쪽 밝은 줄, 고르면 금색 테두리).

export const INK = 'rgb(238,232,214)';
export const DIM = 'rgb(170,168,160)';
export const GOLD = 'rgb(255,214,120)';

/** 메뉴 크기 배율: 1280×800 창 기준으로 화면에 맞춰 줄이거나 키운다 (작은 노트북 창, 큰 모니터).
 *  .menu에 CSS zoom으로 입히고, 메뉴 안의 위치 계산은 이 배율로 나눈 '메뉴 픽셀'로 한다. */
export function uiScale(): number {
  const s = Math.min(window.innerWidth / 1280, window.innerHeight / 800);
  return Math.min(Math.max(s, 0.6), 1.4);
}

export function applyUiScale() {
  document.documentElement.style.setProperty('--ui-scale', uiScale().toFixed(4));
}

export function div(cls: string, parent?: HTMLElement, text?: string): HTMLDivElement {
  const d = document.createElement('div');
  d.className = cls;
  if (text !== undefined) d.textContent = text;
  parent?.appendChild(d);
  return d;
}

export interface ButtonOpts { selected?: boolean; size?: number; accent?: boolean; w?: number; h?: number }

export function button(parent: HTMLElement, label: string, onClick: () => void, o: ButtonOpts = {}): HTMLButtonElement {
  const b = document.createElement('button');
  b.className = 'btn' + (o.selected ? ' sel' : '') + (o.accent ? ' accent' : '');
  b.textContent = label;
  if (o.size) b.style.fontSize = `${o.size}px`;
  if (o.w) b.style.width = `${o.w}px`;
  if (o.h) b.style.height = `${o.h}px`;
  b.addEventListener('click', (e) => { e.preventDefault(); onClick(); });
  parent.appendChild(b);
  return b;
}

export function field(parent: HTMLElement, value: string, maxLength: number, w: number, onInput: (v: string) => void): HTMLInputElement {
  const f = document.createElement('input');
  f.className = 'field';
  f.value = value;
  f.maxLength = maxLength;
  f.spellcheck = false;
  f.style.width = `${w}px`;
  f.addEventListener('input', () => onInput(f.value));
  f.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === 'Tab' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); f.blur(); }
  });
  parent.appendChild(f);
  return f;
}

/** 작게 그린 글자를 정수 배로 키워 도트 글씨처럼 (데스크톱 pixel_title: 글자 테두리 대신 오른쪽 아래로 그림자). */
export function pixelTitle(text: string, scale = 4, col = [255, 226, 150]): HTMLCanvasElement {
  const font = "bold 20px 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans CJK KR', sans-serif";
  const m = document.createElement('canvas').getContext('2d')!;
  m.font = font;
  const w = Math.ceil(m.measureText(text).width) + 2, h = 28;
  const mask = (() => {                                     // 부드럽게 칠한 가장자리를 0/1로 (안티에일리어싱 없이)
    const c = document.createElement('canvas');
    c.width = w; c.height = h;
    const g = c.getContext('2d')!;
    g.font = font;
    g.textBaseline = 'top';
    g.fillStyle = '#fff';
    g.fillText(text, 0, 3);
    const d = g.getImageData(0, 0, w, h).data, out = new Uint8Array(w * h);
    for (let i = 0; i < w * h; i++) out[i] = d[i * 4 + 3] >= 128 ? 1 : 0;
    return out;
  })();
  const W = w + 3, H = h + 3;
  const small = document.createElement('canvas');
  small.width = W; small.height = H;
  const g = small.getContext('2d')!;
  const img = g.createImageData(W, H);
  const stamp = (ox: number, oy: number, c: number[]) => {
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      if (!mask[y * w + x]) continue;
      const i = ((y + oy) * W + x + ox) * 4;
      img.data[i] = c[0]; img.data[i + 1] = c[1]; img.data[i + 2] = c[2]; img.data[i + 3] = 255;
    }
  };
  for (const [ox, oy] of [[0, 1], [2, 1], [1, 0], [1, 2], [2, 3], [3, 2], [3, 3]]) stamp(ox, oy, [30, 18, 10]);
  stamp(1, 1, col);
  g.putImageData(img, 0, 0);
  const big = document.createElement('canvas');
  big.width = W * scale; big.height = H * scale;
  const bg = big.getContext('2d')!;
  bg.imageSmoothingEnabled = false;
  bg.drawImage(small, 0, 0, big.width, big.height);
  big.className = 'pixel-title';
  return big;
}

/** 왼쪽이 어둡고 오른쪽으로 옅어지는 그늘 (데스크톱 _shade_left: 알파 190 × (1 - x/폭)^1.4). */
export function shadeLeft(g: CanvasRenderingContext2D, width: number, H: number, alpha = 190) {
  const grad = g.createLinearGradient(0, 0, width, 0);
  for (let k = 0; k <= 16; k++) {
    const f = k / 16;
    grad.addColorStop(f, `rgba(10,12,18,${((alpha * (1 - f) ** 1.4) / 255).toFixed(3)})`);
  }
  g.fillStyle = grad;
  g.fillRect(0, 0, width, H);
}
