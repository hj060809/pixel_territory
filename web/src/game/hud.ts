// 게임 HUD (HTML): 데스크톱 game/app.py의 _draw_panels / _selection_lines / _hover_info와 같은 내용과 자리.

import type { Camera } from '../sim/camera.ts';
import { LEVELS, LEVEL_COLORS } from './diplomacy.ts';
import type { TerrainScene } from '../terrain/scene.ts';
import type { Controller } from './controller.ts';
import type { GameState } from './state.ts';
import { F_FORD, F_WATER, type TerrainRules } from './terrainRules.ts';
import { touchMode } from '../ui/device.ts';
import { coffeeLink } from '../ui/coffee.ts';
import { chatLine } from './chat.ts';
import { SEASON_ICONS, icon } from '../ui/icons.ts';
import { SEASON_NAMES } from '../sim/clock.ts';
import { A_FIGHT, A_HELD, A_SLEEP, A_TAMING, animalAt, isHostile } from './wildlife.ts';

/** 고른 병사 수: 병종마다 ('보병 3 · 창기병 2', 0인 병종은 뺀다). */
export function unitCounts(st: GameState, slots: Iterable<number>, sep = '   '): string {
  const R = st.info.rules, k = R.unit_names.map(() => 0);
  for (const s of slots) { const u = st.units.get(s); if (u) k[u.kind]++; }
  return k.map((n: number, i: number) => (n || i < 2 ? `${R.unit_names[i]} ${n}` : '')).filter(Boolean).join(sep);
}

/** 왼쪽 위 칩 하나: 아이콘 + 값 (굵게) + 1초 수입 (작게). */
interface Chip { el: HTMLSpanElement; v: HTMLElement; r: HTMLElement; fill: HTMLElement; last: string }
interface TopParts {
  res: Chip[]; sulfur: Chip; units: Chip; starve: HTMLSpanElement; mini: HTMLSpanElement;
  season: Chip; time: Chip; speed: Chip; icons: string; capTip: string;
}

const BAR_H = 76;          // 하단 버튼 막대 높이 (그 위로 패널을 올린다)
const fmt = (v: number) => (v >= 10000 ? `${(v / 1000).toFixed(1)}K` : `${Math.round(v)}`);

function el(cls: string, parent: HTMLElement = document.body) {
  const d = document.createElement('div');
  d.className = cls;
  parent.appendChild(d);
  return d;
}

export class Hud {
  private bannerMode = '';
  /** 결과·관전 표시의 버튼이 할 일 (게임 화면이 정한다). */
  actions: { lobby: () => void; restart: () => void; newMap: () => void; room: (() => void) | null } =
    { lobby: () => {}, restart: () => {}, newMap: () => {}, room: null };
  private top = el('hud hud-top');
  private topParts: TopParts | null = null;
  private nations = el('hud-nations');
  private sel = el('hud-panel hud-sel');
  private hover = el('hud-hover');
  private msgs = el('hud-msgs');
  private prompt = el('hud-prompt');
  private banner = el('hud-banner');

  constructor(private st: GameState, private ctl: Controller, private scene: TerrainScene, private rules: TerrainRules) {}

  /** 새 판 (같은 지도로 다시): 상태와 선택을 바꾼다. */
  reset(st: GameState, ctl: Controller) { this.st = st; this.ctl = ctl; }

  /** 왼쪽 위 상자를 한 번 만든다: 자원 칩 줄, 계절·시각·속도 줄, (PC) F1 줄. 매 프레임엔 글자만 바꾼다. */
  private buildTop(): TopParts {
    const R = this.st.info.rules, box = this.top;
    box.textContent = '';
    const row = (cls: string) => el('hud-row ' + cls, box);
    const r1 = row('hud-res'), r2 = row('hud-env'), r3 = row('hud-keys');
    const chip = (parent: HTMLElement, ico: string, tip: string, rate = true): Chip => {
      const c = document.createElement('span');
      c.className = 'chip';
      c.title = tip;
      c.dataset.tip = tip;
      c.innerHTML = icon(ico);
      const v = document.createElement('b'); c.appendChild(v);
      const r = document.createElement('i');
      if (rate) c.appendChild(r);
      const gauge = document.createElement('span');               // 자원 한도 게이지 (자원 칩만)
      gauge.className = 'gauge';
      const fill = document.createElement('span');
      gauge.appendChild(fill);
      if (rate) c.appendChild(gauge);
      parent.appendChild(c);
      return { el: c, v, r, fill, last: '' };
    };
    const names = R.res_names as string[];
    const res = [
      chip(r1, 'food', `${names[0]} · 농장·거점에서 난다. 병사가 먹는다`),
      chip(r1, 'wood', `${names[1]} · 벌목장·거점에서 난다`),
      chip(r1, 'stone', `${names[2]} · 채석장에서 난다`),
    ];
    const sulfur = chip(r1, 'sulfur', '유황 · 사막의 유황 채취장에서 난다. 화염탑의 연료');
    const units = chip(r1, 'soldier', '병사 수', false);
    const starve = document.createElement('span');
    starve.className = 'starve-tag';
    starve.textContent = '굶주림!';
    r1.appendChild(starve);
    const mini = document.createElement('span');                 // 터치: 계절·시각 아이콘만 (둘째 줄 대신)
    mini.className = 'env-mini';
    r1.appendChild(mini);
    const season = chip(r2, 'spring', '계절 · 농사 배율: 가을에 많고, 추운 곳은 겨울에 멈춘다', false);
    const time = chip(r2, 'sun', '시각 (낮·밤)', false);
    const speed = chip(r2, 'play', '게임 속도', false);
    r3.innerHTML = `<span class="kbd">F1</span><span>조작 설명</span>`;
    return { res, sulfur, units, starve, mini, season, time, speed, icons: '', capTip: '' };
  }

  private updateTop() {
    const st = this.st, R = st.info.rules, me = st.nations[st.info.me];
    const t = (this.topParts ??= this.buildTop());
    const put = (c: Chip, v: string, r?: string) => {
      const key = v + '|' + (r ?? '');
      if (key === c.last) return;
      c.last = key;
      c.v.textContent = v;
      if (r !== undefined) c.r.textContent = r;
    };
    const caps = me?.caps ?? [0, 0, 0, 0];
    const rate = (c: Chip, x: number, have: number, cap: number) => {   // 수입 + 그 자원의 한도 게이지 (가득 차면 '가득')
      const f = cap > 0 ? Math.min(have / cap, 1) : 0, full = f >= 0.999;
      c.fill.style.width = `${(f * 100).toFixed(1)}%`;
      c.el.classList.toggle('near', f >= 0.85 && !full);
      c.el.classList.toggle('full', full);
      c.r.className = full ? 'full' : x > 0.05 ? 'up' : x < -0.05 ? 'down' : 'zero';
      return full && x > 0 ? '가득' : `${x > 0.05 ? '+' : ''}${x.toFixed(1)}`;
    };
    t.res.forEach((c, k) => { put(c, me ? fmt(me.res[k]) : '0', rate(c, me ? me.rate[k] : 0, me ? me.res[k] : 0, caps[k])); });
    const sul = !!me && (me.sulfur > 0 || me.sulfurRate > 0);
    t.sulfur.el.style.display = sul ? '' : 'none';
    if (sul) put(t.sulfur, fmt(me!.sulfur), rate(t.sulfur, me!.sulfurRate, me!.sulfur, caps[3]));
    const capTip = caps.map((v) => Math.round(v)).join(',');
    if (t.capTip !== capTip) {                                      // 마우스를 올리면: 그 자원의 한도와 늘리는 법
      t.capTip = capTip;
      [...t.res, t.sulfur].forEach((c, k) => {
        c.el.title = `${c.el.dataset.tip}\n한도 ${Math.round(caps[k])} (거점마다 +${R.store?.hall ?? 50}, 이 자원 건물마다 +${R.store?.site ?? 25})`;
      });
    }
    put(t.units, `${me ? me.nUnits : 0}`);
    const starving = !!me?.starving;
    t.res[0].el.classList.toggle('starving', starving);
    t.starve.style.display = starving ? '' : 'none';
    // 계절·시각·속도
    const season = this.scene.season, cycle = this.scene.cycle, w = season.weights();
    const sf = R.season_yield_food.reduce((s: number, v: number, k: number) => s + v * w[k], 0);
    const si = season.index(), night = cycle.sunAlt() <= 0, paused = st.paused;
    const icons = `${si}|${night}|${paused}`;
    if (icons !== t.icons) {
      t.icons = icons;
      t.season.el.querySelector('svg')!.outerHTML = icon(SEASON_ICONS[si]);
      t.time.el.querySelector('svg')!.outerHTML = icon(night ? 'moon' : 'sun');
      t.speed.el.querySelector('svg')!.outerHTML = icon(paused ? 'pause' : 'play');
      t.mini.innerHTML = icon(SEASON_ICONS[si]) + icon(night ? 'moon' : 'sun');
    }
    put(t.season, `${SEASON_NAMES[si]} ${season.month()}월 · 농사 ×${sf.toFixed(1)}`);
    put(t.time, cycle.label());
    put(t.speed, paused ? '일시정지' : `×${st.speed}`);
  }

  dispose() { for (const d of this.panels()) d.remove(); this.banner.remove(); }

  /** 가림 검사에 쓸 요소들. */
  panels(): HTMLElement[] { return [this.top, this.nations, this.sel, this.hover, this.msgs, this.prompt]; }

  update(cam: Camera, mouse: [number, number] | null) {
    const st = this.st, R = st.info.rules;
    this.updateTop();
    const touch = touchMode();                                  // 터치: 도움말은 ☰ 메뉴에, 고른 것은 아래 한 줄 막대에
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
      const conn = (text: string, color: string) => {          // 사람 나라의 접속 상태 (멀티)
        const t = document.createElement('span');
        t.textContent = '  ' + text;
        t.style.color = color;
        row.appendChild(t);
      };
      if (st.seats.gone.includes(i)) conn('떠남', 'rgb(170,170,170)');
      else if (st.seats.away.includes(i)) conn('연결 끊김', 'rgb(255,190,120)');
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
    // 아래 왼쪽: 알림 (8초 동안, 마지막 2초에 흐려진다). 대화는 이름(나라 색)과 함께 20초. 대화를 입력하는 중엔 모두 그대로
    this.msgs.innerHTML = '';
    const typing = document.body.classList.contains('chat-typing');
    for (const m of [...st.messages].reverse()) {
      const age = st.time - m.t, life = m.from !== undefined ? 20 : 8;
      if (age > life && !typing) continue;
      const d = m.from !== undefined ? chatLine(st, m.from, m.text, 'msg chat') : el('msg', this.msgs);
      if (m.from !== undefined) this.msgs.appendChild(d); else d.textContent = m.text;
      d.style.opacity = typing ? '1' : String(Math.min(1, (life - age) / 2));
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
    // 판 끝: 결과 + 버튼 (싱글은 새 판·새 지도도). 진 뒤 판이 이어지는 동안: 관전 + [나가기]
    const solo = (st.info.humans ?? 1) <= 1;
    const toRoom = st.info.room ? this.actions.room : null;
    const bmode = st.info.tutorial ? '' : st.over && st.ended ? `end:${st.over}:${solo}:${!!toRoom}` : st.over ? 'watch' : '';   // 튜토리얼은 안내 창이 대신
    if (bmode !== this.bannerMode) {
      this.bannerMode = bmode;
      this.banner.innerHTML = '';
      this.banner.className = 'hud-banner' + (bmode === 'watch' ? ' watch' : '');
      if (bmode) {
        const big = document.createElement('div');
        big.className = 'big';
        big.textContent = bmode === 'watch' ? '패배 · 관전 중' : st.over === '승리' ? '승리!' : '패배';
        this.banner.appendChild(big);
        const row = document.createElement('div');
        row.className = 'banner-btns';
        const b = (label: string, fn: () => void) => {
          const e = document.createElement('button');
          e.className = 'dbtn';
          e.textContent = label;
          e.addEventListener('click', (ev) => { ev.stopPropagation(); fn(); });
          row.appendChild(e);
        };
        if (bmode !== 'watch' && solo) {
          b('같은 지도로 새 판', () => this.actions.restart());
          b('새 지도', () => this.actions.newMap());
        }
        if (bmode !== 'watch' && toRoom) b('대기실로', () => toRoom());
        b(bmode === 'watch' ? '나가기' : '로비로', () => this.actions.lobby());
        this.banner.appendChild(row);
        if (!touch) {
          const hint = document.createElement('div');
          hint.className = 'hint';
          hint.textContent = bmode === 'watch' ? '판이 끝날 때까지 볼 수 있습니다 · Enter: 나가기'
            : solo ? 'F5: 같은 지도로 새 판    F6: 새 지도    Enter: 로비로' : toRoom ? '같은 사람들과 다시 하려면 대기실로' : 'Enter: 로비로';
          this.banner.appendChild(hint);
        }
        {                                                      // 판 끝·관전 중: 결과 아래 작게 (개발자에게 커피)
          const c = document.createElement('div');
          c.className = 'banner-coffee';
          const t = document.createElement('div');
          t.textContent = '재밌으셨나요? 개발자에게 따뜻한 커피 한 잔 선물하는 건 어떠세요?';
          c.append(t, coffeeLink('커피 선물하기', 'coffee-mini', 14));
          this.banner.appendChild(c);
        }
      }
    }
    this.banner.style.display = bmode ? '' : 'none';
  }

  private selectionLines(): string[] {
    const st = this.st, R = st.info.rules, ctl = this.ctl, lines: string[] = [];
    ctl.prune();
    if (ctl.sel.size) {
      let building = false, taming = false;
      for (const s of ctl.sel.keys()) { const u = st.units.get(s); building ||= u?.state === 4; taming ||= u?.state === 5; }
      lines.push(unitCounts(st, ctl.sel.keys()) + (building ? '   (짓는 중)' : '') + (taming ? '   (길들이는 중)' : ''));
      lines.push('오른쪽 클릭: 이동 · 공격 · 자원지에 짓기 · 야생말 길들이기 (바다 건너면 배)    A: 공격 이동    S: 정지    1~9: 이 병사들로 건물 짓기');
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
