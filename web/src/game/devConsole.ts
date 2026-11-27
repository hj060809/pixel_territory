// 개발용 숨은 콘솔: 서버를 --dev로 켰을 때만 (start 정보의 dev). 게임 중 ` 키로 열고 닫는다.
//   res 5000            모든 자원 +5000 (식량·목재·석재·유황)
//   res food 2000       하나만 (food/wood/stone/sulfur 또는 식량/목재/석재/유황)
//   spawn infantry 20  병사 소환: 지금 보는 화면 가운데에서 가장 가까운 걸을 수 있는 칸부터 (수를 빼면 1, 한 번에 200까지)
//                       infantry/archer/lancer/horsearcher/rider/tortoise 또는 보병/궁수/창기병/기마궁수/용기사/바위거북
// 서버도 --dev가 아니면 이 명령을 받지 않는다 (배포 서버에서는 쓸 수 없다).

import type { Connection } from './net.ts';

const RES: Record<string, number> = { food: 0, wood: 1, stone: 2, sulfur: 3, 식량: 0, 목재: 1, 석재: 2, 유황: 3 };
const UNITS: Record<string, number> = {                    // 병종 번호 (sim/rules.py)
  infantry: 0, archer: 1, lancer: 2, horsearcher: 3, rider: 4, tortoise: 6,
  보병: 0, 궁수: 1, 창기병: 2, 기마궁수: 3, 용기사: 4, 바위거북: 6,
};

export class DevConsole {
  readonly el = document.createElement('input');

  constructor(private net: Connection, private say: (t: string) => void, private center: () => number[]) {
    this.el.className = 'dev-console';
    this.el.placeholder = 'res 5000 · res sulfur 200 · spawn infantry 20  (Enter 보내기, ` 닫기)';
    this.el.style.cssText = 'position:fixed;left:50%;top:70px;transform:translateX(-50%);width:420px;z-index:30;display:none;'
      + 'font:14px monospace;padding:6px 10px;background:rgba(10,12,20,0.92);color:#d8f0c8;border:1px solid #5a8a50;outline:none';
    this.el.addEventListener('keydown', (e) => {
      e.stopPropagation();                                   // 게임 단축키로 가지 않게
      if (e.key === 'Enter') { this.run(this.el.value.trim()); this.el.value = ''; }
      else if (e.key === 'Escape' || e.key === '`') { e.preventDefault(); this.toggle(false); }
    });
    document.body.appendChild(this.el);
  }

  get open() { return this.el.style.display !== 'none'; }

  toggle(on = !this.open) {
    this.el.style.display = on ? '' : 'none';
    if (on) setTimeout(() => this.el.focus(), 0); else this.el.blur();
  }

  private run(line: string) {
    const [cmd, a, b] = line.split(/\s+/);
    if (cmd === 'res') {
      const amount = Number(b ?? a);
      if (!Number.isFinite(amount)) { this.say('개발: res 숫자 / res food 숫자'); return; }
      const add = [0, 0, 0, 0];
      if (b !== undefined && RES[a] === undefined) { this.say('개발: 자원은 food / wood / stone / sulfur'); return; }
      if (b === undefined) add.fill(amount); else add[RES[a]] = amount;
      this.net.send({ t: 'dev', cmd: 'res', add });
    } else if (cmd === 'spawn') {                              // 화면 가운데 가까이에 병사 소환
      const kind = UNITS[(a ?? '').toLowerCase()], n = b === undefined ? 1 : Math.trunc(Number(b));
      if (kind === undefined) { this.say('개발: spawn infantry|archer|lancer|horsearcher|rider|tortoise (또는 보병|궁수|창기병|기마궁수|용기사|바위거북) [수]'); return; }
      if (!Number.isFinite(n) || n < 1) { this.say('개발: 수는 1 이상'); return; }
      const [x, y] = this.center();
      this.net.send({ t: 'dev', cmd: 'spawn', kind, n: Math.min(n, 200), x, y });
    } else if (line) this.say(`개발: 모르는 명령 ${cmd}`);
  }

  dispose() { this.el.remove(); }
}
