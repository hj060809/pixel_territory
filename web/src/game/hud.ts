// 게임 HUD (HTML): 데스크톱 game/app.py의 _draw_panels / _selection_lines / _hover_info와 같은 내용과 자리.

import type { Camera } from '../sim/camera.ts';
import { LEVELS, LEVEL_COLORS } from './diplomacy.ts';
import type { TerrainScene } from '../terrain/scene.ts';
import type { Controller } from './controller.ts';
import type { GameState } from './state.ts';
import { F_FORD, F_WATER, type TerrainRules } from './terrainRules.ts';
import { touchMode } from '../ui/device.ts';
import { A_FIGHT, A_HELD, A_SLEEP, A_TAMING, animalAt, isHostile } from './wildlife.ts';

/** 고른 병사 수: 병종마다 ('보병 3 · 창기병 2', 0인 병종은 뺀다). */
export function unitCounts(st: GameState, slots: Iterable<number>, sep = '   '): string {
  const R = st.info.rules, k = R.unit_names.map(() => 0);
  for (const s of slots) { const u = st.units.get(s); if (u) k[u.kind]++; }
  return k.map((n: number, i: number) => (n || i < 2 ? `${R.unit_names[i]} ${n}` : '')).filter(Boolean).join(sep);
}

export const HELP = [
  '왼쪽: 고르기 · 드래그    오른쪽: 이동 · 공격 · 자원지에 짓기    A: 공격 이동    S: 정지',
  '야생 동물을 오른쪽 클릭하면 병사가 다가가 길들인다 (드래곤은 먼저 쓰러뜨려야 한다)',
  '다른 나라의 거점을 누르면 외교: 동맹 요청 · 동맹끼리 지원 · 공격 요청',
  'Ctrl+숫자: 부대 지정    Shift+숫자: 부대 부르기    Space: 내 거점으로',
  '휠: 확대    P: 일시정지    . : 속도    F1: 도움말 끄기',
];

const BAR_H = 76;          // 하단 버튼 막대 높이 (그 위로 패널을 올린다)
const fmt = (v: number) => (v >= 10000 ? `${(v / 1000).toFixed(1)}K` : `${Math.round(v)}`);

function el(cls: string, parent: HTMLElement = document.body) {
  const d = document.createElement('div');
  d.className = cls;
  parent.appendChild(d);
  return d;
}

export class Hud {
  showHelp = true;
  private top = el('hud');
  private nations = el('hud-nations');
  private sel = el('hud-panel hud-sel');
  private hover = el('hud-hover');
  private msgs = el('hud-msgs');
  private prompt = el('hud-prompt');
  private banner = el('hud-banner');

  constructor(private st: GameState, private ctl: Controller, private scene: TerrainScene, private rules: TerrainRules) {}

  /** 새 판 (같은 지도로 다시): 상태와 선택을 바꾼다. */
  reset(st: GameState, ctl: Controller) { this.st = st; this.ctl = ctl; }

  dispose() { for (const d of this.panels()) d.remove(); this.banner.remove(); }

  /** 가림 검사에 쓸 요소들. */
  panels(): HTMLElement[] { return [this.top, this.nations, this.sel, this.hover, this.msgs, this.prompt]; }

  update(cam: Camera, mouse: [number, number] | null) {
    const st = this.st, R = st.info.rules, me = st.nations[st.info.me];
    // 왼쪽 위: 자원과 시각
    const lines: string[] = [];
    if (me) {
      const parts = [0, 1, 2].map((k) => `${R.res_names[k]} ${fmt(me.res[k])} (${me.rate[k] >= 0 ? '+' : ''}${me.rate[k].toFixed(1)})`);
      if (me.sulfur > 0 || me.sulfurRate > 0) parts.push(`유황 ${fmt(me.sulfur)} (+${me.sulfurRate.toFixed(1)})`);
      lines.push(parts.join('   ') + `   병사 ${me.nUnits}` + (me.starving ? '   굶주림!' : ''));
    }
    const w = this.scene.season.weights();
    const sf = R.season_yield_food.reduce((s: number, v: number, k: number) => s + v * w[k], 0);
    lines.push(`${this.scene.season.label()}  농사 ×${sf.toFixed(1)}   ${this.scene.cycle.label()}   ×${st.speed}` +
      (st.paused ? '   일시정지' : ''));
    const touch = touchMode();                                  // 터치: 도움말은 ☰ 메뉴에, 고른 것은 아래 한 줄 막대에
    this.top.textContent = [...lines, ...(this.showHelp && !touch ? HELP : [])].join('\n');
    // 오른쪽 위: 나라들
    this.nations.innerHTML = '';
    st.info.nations.forEach((n, i) => {
      const s = st.nations[i];
      if (s && !s.alive) return;
      const row = el('row', this.nations);
      const sw = document.createElement('span');
      sw.className = 'swatch';
      sw.style.background = `rgb(${n.color.join(',')})`;
      row.append(sw, `${n.name}  병사 ${s?.nUnits ?? 0}  건물 ${s?.nBuildings ?? 0}`);
      const d = st.diplo, me = st.info.me;
      if (d) {
        const tag = (text: string, color: string) => {
          const t = document.createElement('span');
          t.textContent = '  ' + text;
          t.style.color = color;
          row.appendChild(t);
        };
        if (i !== me) {
          if (String(i) in d.allies) tag(`동맹 ${Math.floor(d.allies[String(i)] / 60)}분`, LEVEL_COLORS[3]);
          else tag(LEVELS[d.theirs[i] ?? 2], LEVEL_COLORS[d.theirs[i] ?? 2]);
          if (d.incoming.includes(i)) tag('동맹 요청!', 'rgb(255,230,140)');
        }
        if (String(i) in d.traitors) tag('배신자', LEVEL_COLORS[0]);
        const with_ = d.pairs.filter((p) => p.includes(i) && !p.includes(me)).map((p) => (p[0] === i ? p[1] : p[0]));
        if (i !== me && with_.length) tag(`(${with_.map((k) => st.info.nations[k].name.split(' ').pop()).join('·')}와 동맹)`, 'rgb(180,200,220)');
      }
    });
    // 아래 가운데: 고른 것
    const sl = this.selectionLines();
    this.sel.textContent = sl.join('\n');
    this.sel.style.display = sl.length ? '' : 'none';
    // 아래 오른쪽: 마우스 아래
    const placing = typeof this.ctl.mode === 'number';      // 건물을 놓는 중엔 커서의 그림과 아래 안내가 대신한다
    const info = mouse && !placing ? this.hoverInfo(...cam.toMap(mouse[0], mouse[1]), cam.zoom) : null;
    this.hover.textContent = info ?? '';
    this.hover.style.bottom = `${BAR_H + 10 + (this.ctl.hasSelection() ? 60 : 0)}px`;
    // 아래 왼쪽: 알림 (8초 동안, 마지막 2초에 흐려진다)
    this.msgs.innerHTML = '';
    for (const m of [...st.messages].reverse()) {
      const age = st.time - m.t;
      if (age > 8) continue;
      const d = el('msg', this.msgs);
      d.textContent = m.text;
      d.style.opacity = String(Math.min(1, (8 - age) / 2));
    }
    // 가운데: 안내
    const mode = this.ctl.mode;
    let place = '';
    if (typeof mode === 'number') {
      const res = this.ctl.siteRes(mode);
      place = res >= 0 ? `${R.build_names[mode]}: 빈 ${R.site_names[res]} 자원지를 클릭하세요`
        : `${R.build_names[mode]}${mode === R.kinds.HARBOR ? ' (바다에 맞닿은 해안)' : ''} 자리를 클릭하세요`;
      if (touch) place = place.replace('자원지를 클릭하세요', '자원지로 옮기세요').replace('자리를 클릭하세요', '자리로 옮기세요');
      if (touch) place = place.replace('로 옮기세요', '로 옮기고 ✓');           // 터치: 한 줄로 짧게 (✓ 버튼을 가리지 않게)
      else {
        place += this.ctl.sel.size ? ' — 고른 병사가 짓는다' : ' — 가까운 쉬는 병사가 짓는다';
        place += '    (Shift: 여러 개, 오른쪽 클릭 · Esc: 취소)';
      }
    }
    this.prompt.textContent = mode === 'attack' ? `공격할 곳을 ${touch ? '탭' : '클릭'}하세요 (가다가 만나는 적과 싸웁니다)` : place;
    this.prompt.className = `hud-prompt ${mode === 'attack' ? 'warm' : 'cool'}`;
    // 안내는 하단 막대 바로 위 (고른 것 패널이 있으면 그 위)
    this.prompt.style.bottom = `${BAR_H + 10 + (sl.length ? this.sel.offsetHeight + 8 : 0)}px`;
    if (st.over) {
      const next = touch ? '☰ 메뉴: 같은 지도로 새 판 · 새 지도 · 로비로' : 'F5: 같은 지도로 새 판    F6: 새 지도    Enter: 로비로';
      this.banner.innerHTML = `<div class="big">${st.over === '승리' ? '승리!' : '패배'}</div><div>${next}</div>`;
      this.banner.style.display = '';
    } else this.banner.style.display = 'none';
  }

  private selectionLines(): string[] {
    const st = this.st, R = st.info.rules, ctl = this.ctl, lines: string[] = [];
    ctl.prune();
    if (ctl.sel.size) {
      let building = false, taming = false;
      for (const s of ctl.sel.keys()) { const u = st.units.get(s); building ||= u?.state === 4; taming ||= u?.state === 5; }
      lines.push(unitCounts(st, ctl.sel.keys()) + (building ? '   (짓는 중)' : '') + (taming ? '   (길들이는 중)' : ''));
      lines.push('오른쪽 클릭: 이동 · 공격 · 자원지에 짓기 · 야생말 길들이기 (바다 건너면 배)    A: 공격 이동    S: 정지    1~8: 이 병사들로 건물 짓기');
    }
    if (ctl.selShips.size) {
      const boats = [...ctl.selShips].map((id) => st.boats.get(id)!);
      const war = boats.filter((b) => b.kind === 1), fer = boats.filter((b) => b.kind === 0);
      if (war.length) {
        const hp = war.reduce((s, b) => s + b.hp, 0);
        lines.push(`전함 ${war.length}척  체력 ${Math.round((hp / war.length) * 100)}%    오른쪽 클릭: 물 → 이동, 적 배 → 공격`);
      }
      if (fer.length) {
        lines.push(`나룻배 ${fer.length}척 (병사 ${fer.reduce((s, b) => s + b.cargo, 0)}명)    오른쪽 클릭: 물 → 그 자리에서 기다림, 땅 → 가까운 해안에 내려 줌`);
      }
    }
    const b = ctl.selB ? st.builds.get(ctl.selB[0]) : null;
    if (b) {
      const maxhp = R.build[b.kind].hp;
      let s = `${R.build_names[b.kind]}  체력 ${Math.round(b.hp * maxhp)}/${Math.round(maxhp)}`;
      const qname = b.qkind === 2 ? '' : `${R.unit_names[b.qkind]} `;   // 대기열 번호: 0 보병, 1 궁수, 2 전함
      const qtxt = b.qlen ? ` (${qname}${Math.round(b.qtime)}초)` : '';
      if (b.prog < 1) s += `  짓는 중 ${Math.round(b.prog * 100)}%`;
      else if (b.kind === R.kinds.HALL) {
        lines.push(s + `  훈련 대기 ${b.qlen}` + qtxt);
        s = `Q: 보병 (식량 ${R.unit_cost[0][0]})    W: 궁수 (식량 ${R.unit_cost[1][0]}, 목재 ${R.unit_cost[1][1]})    이 거점에서 만든다 (기병은 야생말을 길들여서)`;
      } else if (b.kind === R.kinds.HARBOR) {
        const ships = [...st.boats.values()].filter((x) => x.own === st.info.me && x.kind === 1).length;
        lines.push(s + `  전함 ${ships}척  만드는 중 ${b.qlen}` + qtxt);
        s = `E: 전함 (목재 ${R.warship_cost[1]}, 석재 ${R.warship_cost[2]})    바다 건너로 보낸 이 땅의 병사들이 여기 모여 차례로 배를 탄다`;
      } else if (b.site >= 0 && R.yield_res[b.kind] !== undefined) {
        const site = st.info.sites[b.site];
        s += `  ${R.res_names[R.yield_res[b.kind]]} 풍부함 ${site.rich.toFixed(1)}`;
      }
      lines.push(s);
    }
    return lines;
  }

  /** 그 자리 설명 (터치: 길게 누르기). */
  infoAt(x: number, y: number, zoom: number): string | null { return this.hoverInfo(x, y, zoom); }

  private hoverInfo(x: number, y: number, zoom: number): string | null {
    const st = this.st, R = st.info.rules, m = this.rules;
    const xi = Math.floor(x), yi = Math.floor(y);
    if (!(xi >= 0 && xi < m.W && yi >= 0 && yi < m.H)) return null;
    const an = animalAt(st, x, y, Math.max(1.8, 8 / zoom));
    if (an) {
      const a = R.wildlife[an.kind], into = Object.entries(a.mounts as Record<string, number>)
        .map(([u, v]) => `${R.unit_names[Number(u)]} → ${R.unit_names[v]}`).join(', ');
      const act = touchMode() ? '탭' : '오른쪽 클릭';
      if (isHostile(R, an.kind)) {
        const rider = R.unit_names[Object.values(a.mounts as Record<string, number>)[0]], hp = `체력 ${Math.round(an.hp * 100)}%`;
        if (an.state === A_SLEEP) return `${a.name} · 잠 · ${hp} · 병사를 보내 치면 깨어 싸운다. 체력을 ${Math.round(a.subdue * 100)}% 아래로 깎으면 쓰러진다`;
        if (an.state === A_FIGHT) return `${a.name} · 싸우는 중 · ${hp} · 서리 숨결 (범위 피해, 느려짐) · ${Math.round(a.subdue * 100)}% 아래면 쓰러진다`;
        if (an.state === A_TAMING) return `${a.name} · 길들이는 중 ${Math.round(an.prog * 100)}% · 쓰러짐 ${an.sub}초 남음`;
        return `${a.name} · 쓰러짐 ${an.sub}초 · 병사를 고르고 ${act}하면 한 명이 가서 길들인다 (${Math.round(a.tame)}초) → ${rider} (나라마다 ${a.limit}기)`;
      }
      if (a.companion >= 0) {                                    // 함께 싸우는 동물 (바위거북)
        if (an.state === A_TAMING) return `먹이를 받아먹는 ${a.name} · ${Math.round(an.prog * 100)}%`;
        return `야생 ${a.name} · 병사를 고르고 ${act}하면 한 명이 가서 먹이를 준다 (식량 ${a.food}, ${Math.round(a.tame)}초) → 함께 싸우는 탱커 (발 구르기, 낮은 포효, 껍질 숨기)`;
      }
      if (an.state === A_TAMING) return `길들이는 중인 ${a.name} · ${Math.round(an.prog * 100)}%`;
      if (an.state === A_HELD) return `야생${a.name} · 병사가 길들이러 오는 중`;
      return `야생${a.name} · 병사를 고르고 ${touchMode() ? '탭' : '오른쪽 클릭'}하면 말마다 한 명씩 가서 길들인다 (${Math.round(a.tame)}초) · ${into}`;
    }
    const s = this.ctl.siteAt(x, y, Math.max(4.0, 10 / zoom));
    if (s && !st.siteTaken().has(s.id)) {
      const kind = R.site_building[s.kind];
      const cost = R.build[kind].cost.map((v: number, k: number) => (v ? `${R.res_names[k]} ${v}` : '')).filter(Boolean).join(', ');
      const act = `병사를 고르고 ${touchMode() ? '탭' : '오른쪽 클릭'}하면 ${R.build_names[kind]} (${cost})`;
      return `${s.snow ? '눈 덮인 숲' : R.site_names[s.kind]} 자원지 · 풍부함 ${s.rich.toFixed(1)}${s.snow ? ' (보통 숲보다 덜 난다)' : ''} · ${act}`;
    }
    const i = yi * m.W + xi, f = m.flags[i];
    const ice = !!this.scene.ice?.[i] && !!(f & F_WATER) && !(f & F_FORD);
    if (ice) return '얼어붙은 바다 · 걸어서 건널 수 있다 (녹으면 빠진다)';
    if (f & F_FORD) return '여울 · 건너는 데 오래 걸린다';
    if (f & F_WATER) {
      const boat = this.ctl.boatAt(x, y, Math.max(3.0, 10 / zoom));
      if (boat) {
        const maxhp = boat.kind === 1 ? R.warship_hp : R.ferry_hp;
        return `${st.info.nations[boat.own].name}의 ${boat.kind === 1 ? '전함' : '나룻배'} · 체력 ${Math.round(boat.hp * maxhp)}/${Math.round(maxhp)}`;
      }
      return '바다 · 병사들이 있는 땅에 항구가 있으면 배로 건넌다';
    }
    const mat = this.scene.mat ? this.scene.mat[i] : -1;
    const name = R.mat_names[mat] ?? '땅';
    const extra = m.cover[i] < 70 ? ' · 화살을 덜 맞는다' : '';
    return `${name} · 걷는 속도 ${Math.round(m.speed(yi, xi, mat, false) * 100)}%${extra}`;
  }
}
