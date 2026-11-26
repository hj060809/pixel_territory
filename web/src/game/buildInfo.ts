// 건물 말풍선: 건물을 누르면 그 위에 외교 말풍선(diplomacy.ts)과 같은 모양으로 그 건물의 정보.
//   거점·자원 건물: 이 건물에 보관된 자원 (가진 자원 × 이 건물이 늘린 한도 / 그 자원의 한도, sim/storage.py) — 무너지면 빼앗기는 몫.
//   자원 건물: 생산물과 1초 생산량 (풍부함 × 계절, 서버 sim/world.py _economy와 같은 식).
//   망루·화염탑·항구: 공격력, 간격, 사거리. 모든 건물: 체력, 짓는 중이면 진행.
// 내 건물은 고른 건물(ctl.selB), 다른 나라 건물은 살펴보기(ctl.inspect). 땅이나 다른 것을 누르면 꺼진다 (controller.selectPoint).

import type { Camera } from '../sim/camera.ts';
import type { Controller } from './controller.ts';
import type { GameState } from './state.ts';
import type { BuildRec } from './protocol.ts';
import { icon } from '../ui/icons.ts';

const RES_ICONS = ['food', 'wood', 'stone', 'sulfur'];

export class BuildInfoUi {
  private bubble = document.createElement('div');
  private cur: [number, number] | null = null;
  private sig = '';

  constructor(private st: GameState, private ctl: Controller, private weights: () => number[]) {
    this.bubble.className = 'diplo-bubble build-bubble';
    this.bubble.style.display = 'none';
    document.body.appendChild(this.bubble);
    this.bubble.addEventListener('pointerdown', (e) => e.stopPropagation());   // 말풍선을 눌러도 땅을 누른 것으로 치지 않게
    this.bubble.addEventListener('mousedown', (e) => e.stopPropagation());
    this.bubble.addEventListener('contextmenu', (e) => { e.preventDefault(); e.stopPropagation(); });
  }

  reset(st: GameState, ctl: Controller) { this.st = st; this.ctl = ctl; this.hide(); }

  private target(): BuildRec | null {
    const ref = this.ctl.selB ?? this.ctl.inspect;
    if (!ref || this.ctl.sel.size) return null;                 // 병사를 함께 골랐으면 띄우지 않는다
    const b = this.st.builds.get(ref[0]);
    return b && b.gen === ref[1] ? b : null;
  }

  private hide() { this.cur = null; this.sig = ''; this.bubble.style.display = 'none'; }

  /** 내용을 지금 상태로 (0.25초마다). */
  render() {
    const b = this.target();
    if (!b) { this.hide(); return; }
    this.cur = [b.slot, b.gen];
    this.bubble.style.display = '';
    const html = this.html(b);
    if (html !== this.sig) {
      this.sig = html;
      this.bubble.innerHTML = html;
      this.bubble.querySelector('.dclose')?.addEventListener('click', (e) => {
        e.stopPropagation();
        this.ctl.selB = null; this.ctl.inspect = null; this.hide();
      });
    }
  }

  /** 말풍선을 건물 위에 (매 프레임). */
  frame(cam: Camera) {
    if (!this.cur) return;
    const b = this.st.builds.get(this.cur[0]);
    if (!b) return;
    const r = this.st.info.rules.build[b.kind]?.r ?? 3;
    this.bubble.style.left = `${Math.round((b.x - cam.x) * cam.zoom)}px`;
    this.bubble.style.top = `${Math.round((b.y - r - 1.5 - cam.y) * cam.zoom)}px`;
  }

  dispose() { this.bubble.remove(); }

  // ------------------------------------------------------------- 내용
  private html(b: BuildRec): string {
    const st = this.st, R = st.info.rules, K = R.kinds, me = st.info.me;
    const nat = st.info.nations[b.own], mine = b.own === me;
    const maxhp = R.build[b.kind].hp;
    const parts: string[] = [];
    // 머리줄: 나라 색, (다른 나라면 나라 이름) 건물 이름, 닫기
    const sw = nat ? `<span class="swatch" style="background:rgb(${nat.color.join(',')})"></span>` : '';
    parts.push(`<div class="dhead">${sw}<span>${mine || !nat ? '' : esc(nat.name) + '의 '}${R.build_names[b.kind]}</span>`
      + `<button class="dclose" title="닫기 (Esc)">×</button></div>`);
    // 체력, 짓는 중
    const hp = Math.round(b.hp * maxhp);
    parts.push(bar('체력', `${hp} / ${Math.round(maxhp)}`, b.hp, b.hp < 0.35 ? 'low' : ''));
    if (b.prog < 1) parts.push(bar('짓는 중', `${Math.round(b.prog * 100)}%`, b.prog, 'build'));
    const done = b.prog >= 1;
    // 거점·자원 건물: 보관된 자원 (이 건물이 늘린 한도만큼의 몫)
    const add = this.contrib(b.kind);
    const owner = st.nations[b.own];
    if (add.some((v) => v > 0) && owner) {
      const rows = [0, 1, 2, 3].filter((k) => add[k] > 0 && (k < 3 || owner.sulfur > 0 || b.kind !== K.HALL)).map((k) => {
        const total = owner.caps?.[k] ?? 0;
        const have = done && total > 0 ? (k < 3 ? owner.res[k] : owner.sulfur) * Math.min(add[k] / total, 1) : 0;
        return `<div class="bres">${icon(RES_ICONS[k])}<b>${Math.floor(have)}</b><span class="bcap">/ ${Math.round(add[k])}</span>`
          + `<span class="bgauge"><span style="width:${Math.min(have / add[k], 1) * 100}%"></span></span></div>`;
      }).join('');
      const head = !done ? '다 지으면 자원 한도가 는다' : mine ? '이곳에 보관된 자원 (무너지면 빼앗긴다)' : '이곳의 자원 (무너뜨리면 빼앗는다)';
      parts.push(`<div class="bsec"><div class="bhead">${head}</div>${rows}</div>`);
    }
    // 생산
    const prod = this.production(b);
    if (prod.length) {
      parts.push(`<div class="bsec"><div class="bhead">${done ? '생산' : '다 지으면 생산'}</div>`
        + prod.map(([k, v, note]) => `<div class="bstat">${icon(RES_ICONS[k])}<b>+${v.toFixed(2)}</b><span>/초 ${note}</span></div>`).join('')
        + `</div>`);
    }
    // 싸움
    const fight = this.combat(b);
    if (fight.length) parts.push(`<div class="bsec"><div class="bhead">공격</div>${fight.map((t) => `<div class="bstat">${icon('soldier')}<span>${t}</span></div>`).join('')}</div>`);
    if (b.kind === K.HALL && done && b.qlen) parts.push(`<div class="bnote">훈련 대기 ${b.qlen} (${Math.round(b.qtime)}초)</div>`);
    return parts.join('');
  }

  /** 이 건물이 늘리는 한도 (자원마다: 서버 sim/storage.py contrib와 같다). 거점은 모든 자원, 자원 건물은 그 자원. */
  private contrib(kind: number): number[] {
    const R = this.st.info.rules, K = R.kinds, st = R.store ?? { hall: 50, site: 25 };
    if (kind === K.HALL) return [st.hall, st.hall, st.hall, st.hall];
    const out = [0, 0, 0, 0];
    const res = kind === K.SULFUR_PIT ? 3 : kind === K.PASTURE ? 0 : R.yield_res?.[kind];   // 목장은 식량
    if (res !== undefined) out[res] = st.site;
    return out;
  }

  /** [자원 번호(유황 3), 1초 생산량, 설명]. 서버 _economy와 같은 식 (AI 난이도 배율은 빼고). */
  private production(b: BuildRec): [number, number, string][] {
    const st = this.st, R = st.info.rules, K = R.kinds, w = this.weights();
    const dot = (a: number[]) => a.reduce((s, v, i) => s + v * w[i], 0);
    if (b.kind === K.HALL) return (R.hall_yield as number[]).map((v, k) => [k, v, ''] as [number, number, string]).filter((x) => x[1] > 0);
    if (b.kind === K.PASTURE) {                                 // 목장: 든 동물마다 (겨울엔 덜), 서버 sim/pasture.py food와 같다
      const p = st.pens.get(b.slot), P = R.pasture;
      if (!p) return [];
      const n = p.spots.length, name = R.wildlife[p.kind]?.name ?? '';
      const per = P.food[String(p.kind)] ?? 0, f = 1 - w[3] * (1 - (P.winter[String(p.kind)] ?? 1));
      if (!p.done) return [[0, 0, `· 다 지으면 울타리 안의 ${name}이 든다`]];
      return [[0, per * n * f, `· ${name} ${n}/${P.cap}마리` + (w[3] > 0.05 ? ` · 겨울 ×${f.toFixed(1)}` : '') + (n >= 2 && n < P.cap ? ' · 봄·여름에 새끼' : '')
        + (Object.keys(R.wildlife[p.kind]?.mounts ?? {}).length && b.own === st.info.me ? ' · 보병·궁수를 고르고 오른쪽 클릭하면 말을 꺼내 탄다 (2마리는 남긴다)' : '')]];
    }
    const site = b.site >= 0 ? st.info.sites[b.site] : null;
    if (!site) return [];
    if (b.kind === K.SULFUR_PIT) return [[3, R.sulfur_yield * site.rich, `· 풍부함 ${site.rich.toFixed(1)}`]];
    const base = R.yield_base?.[b.kind];
    if (base === undefined) return [];
    const res = R.yield_res[b.kind];
    const sf = dot(R.season_yield[res]);
    const cold = site.cold ?? 1;
    const season = 1 + cold * (sf - 1);
    const note = `· 풍부함 ${site.rich.toFixed(1)}` + (Math.abs(season - 1) > 0.05 ? ` · 계절 ×${season.toFixed(1)}` : '');
    return [[res, base * site.rich * season, note]];
  }

  /** 공격 설명 줄들. */
  private combat(b: BuildRec): string[] {
    const R = this.st.info.rules, K = R.kinds;
    if (b.kind === K.TOWER) {
      const t = R.tower;
      return [`화살 ${t.dmg} · ${t.cd}초마다`, `사거리 ${t.range}칸`];
    }
    if (b.kind === K.FIRE_TOWER) {
      const f = R.fire;
      return [`불 ${f.dmg} · ${f.cd}초마다 · 둘레 ${f.splash}칸에 ×${f.splash_mul}`, `사거리 ${f.range.toFixed(1)}칸 · 드래곤에 ×${f.vs_dragon}`,
              `유황이 없으면 ×${f.weak}`];
    }
    if (b.kind === K.HARBOR) {
      const s = R.warship;
      return [`전함: 포 ${s.dmg} · ${s.cd}초마다 · 사거리 ${s.range}칸`];
    }
    return [];
  }
}

function bar(label: string, value: string, f: number, cls = ''): string {
  return `<div class="bbar ${cls}"><span class="blabel">${label}</span><span class="bgauge"><span style="width:${Math.max(0, Math.min(f, 1)) * 100}%"></span></span>`
    + `<span class="bval">${value}</span></div>`;
}

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
}
