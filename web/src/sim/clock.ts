// 낮밤 시계와 1년 시계: engine/render/daylight.py, engine/render/seasons.py의 SeasonCycle을 옮겼다.

export const SEASON_CENTERS = [0.10, 0.35, 0.60, 0.85];      // 봄 / 여름 / 가을 / 겨울이 가장 뚜렷한 때
export const SEASON_NAMES = ['봄', '여름', '가을', '겨울'];

export class DayNightCycle {
  hour: number;
  auto: boolean;
  dayLength: number;
  private keys: any[];
  private maxSun: number;
  private maxMoon: number;

  constructor(light: any, hour = 12, dayLength = 120, auto = true) {
    this.hour = ((hour % 24) + 24) % 24;
    this.dayLength = dayLength;
    this.auto = auto;
    this.keys = light.keys;
    this.maxSun = light.max_sun_alt;
    this.maxMoon = light.max_moon_alt;
  }

  update(dt: number) { if (this.auto) this.advance((dt * 24.0) / this.dayLength); }
  advance(hours: number) { this.hour = (((this.hour + hours) % 24) + 24) % 24; }

  label(): string {
    const h = Math.floor(this.hour);
    return `${String(h).padStart(2, '0')}:${String(Math.floor((this.hour - h) * 60)).padStart(2, '0')}`;
  }

  sunAlt(): number { return this.maxSun * Math.sin((Math.PI * (this.hour - 6.0)) / 12.0); }
  moonAlt(): number { return this.maxMoon * Math.sin((Math.PI * (this.hour - 18.0)) / 12.0); }

  /** 지금 해 고도의 (빛 색 배율, 그늘 색 배율, 하늘색, 물에 비치는 하늘 비율). */
  keyframe(): { light: number[]; shadow: number[]; sky: number[]; skyAmount: number } {
    const alt = this.sunAlt();
    const keys = this.keys;
    let i = 0;
    while (i + 1 < keys.length && keys[i + 1][0] <= alt) i++;      // searchsorted(side='right') - 1
    i = Math.min(Math.max(i, 0), keys.length - 2);
    const a0 = keys[i], a1 = keys[i + 1];
    const t = Math.min(Math.max((alt - a0[0]) / (a1[0] - a0[0]), 0), 1);
    const mix = (u: number[], v: number[]) => u.map((x, k) => x * (1 - t) + v[k] * t);
    return { light: mix(a0[1], a1[1]), shadow: mix(a0[2], a1[2]), sky: mix(a0[3], a1[3]), skyAmount: a0[4] * (1 - t) + a1[4] * t };
  }

  /** 빛을 주는 해와 달: [(고도, 비중)]. */
  sources(): [number, number][] {
    const sun = this.sunAlt(), moon = this.moonAlt();
    const c = (x: number) => Math.min(Math.max(x, 0), 1);
    return [[sun, c(sun / 3.0)], [moon, c((-sun - 6.0) / 6.0) * c(moon / 3.0)]];
  }

  /** 그늘 표(0~255)와 빛 표(256~511)를 이어 붙인 RGBA (512×1). numpy와 같게: clip(v·배율) → 버림. */
  table(): Uint8Array {
    const { light, shadow } = this.keyframe();
    const out = new Uint8Array(512 * 4);
    for (let v = 0; v < 256; v++) {
      for (let c = 0; c < 3; c++) {
        out[v * 4 + c] = Math.trunc(Math.min(Math.max(v * shadow[c], 0), 255));
        out[(256 + v) * 4 + c] = Math.trunc(Math.min(Math.max(v * light[c], 0), 255));
      }
      out[v * 4 + 3] = 255;
      out[(256 + v) * 4 + 3] = 255;
    }
    return out;
  }
}

export class SeasonCycle {
  year: number;
  yearLength: number;
  auto: boolean;

  constructor(year = 0.35, yearLength = 240, auto = true) {
    this.year = ((year % 1) + 1) % 1;
    this.yearLength = yearLength;
    this.auto = auto;
  }

  update(dt: number) { if (this.auto) this.advance(dt / this.yearLength); }
  advance(years: number) { this.year = (((this.year + years) % 1) + 1) % 1; }

  /** (봄, 여름, 가을, 겨울) 비중. 이웃한 두 계절 사이를 선형으로. */
  weights(): number[] {
    const c = SEASON_CENTERS, w = [0, 0, 0, 0], y = this.year;
    for (let k = 0; k < 4; k++) {
      const a = c[k], b = c[(k + 1) % 4] + (k === 3 ? 1.0 : 0.0);
      const yy = k === 3 && y < c[0] ? y + 1.0 : y;
      if (a <= yy && yy < b) {
        const t = (yy - a) / (b - a);
        w[k] = 1 - t;
        w[(k + 1) % 4] = t;
        break;
      }
    }
    return w;
  }

  /** 지금 달 (1~12). */
  month(): number { return (Math.floor(this.year * 12 + 2) % 12) + 1; }
  /** 지금 계절 번호 (0 봄, 1 여름, 2 가을, 3 겨울: SEASON_NAMES 순서). */
  index(): number { return Math.floor(((((this.month() - 3) % 12) + 12) % 12) / 3); }

  label(): string { return `${SEASON_NAMES[this.index()]} (${this.month()}월)`; }
}
