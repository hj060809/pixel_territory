// 설정 화면의 '고급 설정' 창: 지형 세부 값 (데스크톱 뷰어 설정 패널과 같은 항목·이름·묶음).
// 서버가 프리셋 기본값을 주고(/api/mapconfig), 고친 값은 설정 화면이 기억한다 (다시 열면 그대로).
// 아래 '지도 만들기'를 누르면 바꾼 값만 지도 요청에 실어 보낸다 (서버가 자료형과 범위를 다시 확인한다).

import { button, div } from './widgets.ts';

export interface FieldInfo { name: string; label: string; group: string | null; kind: 'float' | 'int' | 'bool' | 'range' | 'auto'; value: any }
type Raw = string | boolean | [string, string];

/** 한 프리셋에 대한 고급 설정 (설정 화면이 들고 있다). */
export class AdvancedState {
  values: Record<string, Raw> = {};
  private defaults: Record<string, Raw> = {};

  constructor(readonly preset: string | null, readonly fields: FieldInfo[]) {
    for (const f of fields) this.defaults[f.name] = toRaw(f);
    this.reset();
  }

  static async load(preset: string | null): Promise<AdvancedState> {
    const r = await fetch(`/api/mapconfig${preset ? `?preset=${encodeURIComponent(preset)}` : ''}`);
    if (!r.ok) throw new Error('고급 설정 항목을 받지 못했습니다');
    return new AdvancedState(preset, (await r.json()).fields);
  }

  reset() { this.values = structuredClone(this.defaults); }

  changed(name: string) { return JSON.stringify(this.values[name]) !== JSON.stringify(this.defaults[name]); }

  /** 바꾼 값 (서버로 보낼 형태). 못 읽는 값이 있으면 error에 항목 이름. */
  overrides(): { config: Record<string, any>; error: string | null } {
    const out: Record<string, any> = {};
    for (const f of this.fields) {
      if (!this.changed(f.name)) continue;
      const v = this.values[f.name];
      const num = (t: string) => { const x = Number(String(t).trim()); return t.trim() !== '' && Number.isFinite(x) ? x : NaN; };
      if (f.kind === 'bool') out[f.name] = v;
      else if (f.kind === 'auto') {
        const t = String(v).trim().toLowerCase();
        if (t === '' || t === 'auto') out[f.name] = null;
        else if (Number.isFinite(num(t))) out[f.name] = num(t);
        else return { config: {}, error: f.label };
      } else if (f.kind === 'range') {
        const [a, b] = (v as [string, string]).map(num);
        if (!Number.isFinite(a) || !Number.isFinite(b)) return { config: {}, error: f.label };
        out[f.name] = [a, b];
      } else {
        const x = num(String(v));
        if (!Number.isFinite(x)) return { config: {}, error: f.label };
        out[f.name] = x;
      }
    }
    return { config: out, error: null };
  }

  count() { return this.fields.filter((f) => this.changed(f.name)).length; }
}

function toRaw(f: FieldInfo): Raw {
  if (f.kind === 'bool') return Boolean(f.value);
  if (f.kind === 'range') return [String(f.value[0]), String(f.value[1])];
  if (f.kind === 'auto') return f.value === null ? 'auto' : String(f.value);
  return String(f.value);
}

/** 창 (열 때마다 새로 만든다). onBuild: 아래 '지도 만들기'. */
export class AdvancedDialog {
  readonly el: HTMLDivElement;
  private err: HTMLDivElement;

  constructor(parent: HTMLElement, private st: AdvancedState, title: string,
              private onClose: () => void, private onBuild: () => void) {
    const back = (this.el = div('modal-back', parent));
    const box = div('modal advanced', back);
    div('modal-title', box, '고급 설정');
    div('adv-sub', box, `${title} · 지형 세부 값 (바꾼 항목은 금색). 지도 만들기를 누르면 이 값으로 새로 만듭니다.`);
    const body = div('adv-body', box);
    this.fill(body);
    const foot = div('adv-foot', box);
    this.err = div('adv-err', foot);
    button(foot, '기본값으로', () => { st.reset(); body.innerHTML = ''; this.fill(body); this.err.textContent = ''; }, { size: 15, w: 120, h: 40 });
    button(foot, '닫기', () => this.close(), { size: 15, w: 100, h: 40 });
    button(foot, '지도 만들기', () => this.build(), { size: 17, w: 160, h: 40, selected: true, accent: true });
  }

  private fill(body: HTMLElement) {
    const st = this.st;
    // 분류(땅 모양, 해안선, ...)마다 노란 제목 한 줄, 그 아래 항목을 세 열로. 분류는 위에서 아래로 쌓는다 (세로 스크롤)
    let col: HTMLElement | null = null;
    for (const f of st.fields) {
      if (f.group || !col) {
        const sec = div('adv-group', body);
        div('adv-head', sec, f.group ?? '');
        col = div('adv-grid', sec);
      }
      const row = div('adv-row', col);
      const lab = div('adv-label', row, f.label);
      const mark = () => lab.classList.toggle('changed', st.changed(f.name));
      mark();
      const input = (value: string, w: number, set: (v: string) => void) => {
        const i = document.createElement('input');
        i.className = 'field adv-input';
        i.value = value;
        i.style.width = `${w}px`;
        i.spellcheck = false;
        i.addEventListener('input', () => { set(i.value); mark(); });
        i.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); i.blur(); }
        });
        row.appendChild(i);
      };
      const v = st.values[f.name];
      if (f.kind === 'bool') {
        const b = button(row, v ? '켜짐' : '꺼짐', () => {
          st.values[f.name] = !st.values[f.name];
          b.textContent = st.values[f.name] ? '켜짐' : '꺼짐';
          b.classList.toggle('sel', Boolean(st.values[f.name]));
          mark();
        }, { size: 13, w: 64, h: 26, selected: Boolean(v) });
      } else if (f.kind === 'range') {
        const pair = v as [string, string];
        input(pair[0], 52, (t) => { pair[0] = t; });
        div('adv-dash', row, '~');
        input(pair[1], 52, (t) => { pair[1] = t; });
      } else {
        input(String(v), 118, (t) => { st.values[f.name] = t; });
      }
    }
  }

  private build() {
    const { error } = this.st.overrides();
    if (error) { this.err.textContent = `${error}: 숫자를 넣어 주세요`; return; }
    this.el.remove();
    this.onBuild();
  }

  close() { this.el.remove(); this.onClose(); }
}
