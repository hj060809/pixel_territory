// 개발용 숨은 콘솔: 서버를 --dev로 켰을 때만 (start 정보의 dev). 게임 중 ` 키로 열고 닫는다.
//   res 5000            세 자원 모두 +5000
//   res food 2000       식량만 (food/wood/stone 또는 식량/목재/석재)
// 서버도 --dev가 아니면 이 명령을 받지 않는다 (배포 서버에서는 쓸 수 없다).

import type { Connection } from './net.ts';

const RES: Record<string, number> = { food: 0, wood: 1, stone: 2, 식량: 0, 목재: 1, 석재: 2 };

export class DevConsole {
  readonly el = document.createElement('input');

  constructor(private net: Connection, private say: (t: string) => void) {
    this.el.className = 'dev-console';
    this.el.placeholder = 'res 5000 · res food 2000  (Enter 보내기, ` 닫기)';
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
      const add = [0, 0, 0];
      if (b !== undefined && RES[a] === undefined) { this.say('개발: 자원은 food / wood / stone'); return; }
      if (b === undefined) add.fill(amount); else add[RES[a]] = amount;
      this.net.send({ t: 'dev', cmd: 'res', add });
    } else if (line) this.say(`개발: 모르는 명령 ${cmd}`);
  }

  dispose() { this.el.remove(); }
}
