// 서버와 주고받기 (WebSocket /ws). join → start(나라, 자원지, 규칙, sid) → 걸음마다 이진 상태 + 알림 JSON.
// 명령은 JSON (sim/commands.py, server/session.py 설명).
// 연결이 끊기면 resume(sid)로 같은 판에 다시 접속한다 (같은 Connection 객체 안에서 소켓만 새로).

import { decodeState, type StateMsg } from './protocol.ts';
import type { StartInfo } from './state.ts';

export interface JoinOptions {
  bots?: number; color?: number; name?: string; difficulty?: string; season?: number;
  spot?: [number, number] | null; starts?: number[][] | null; colors?: number[] | null;
}

export interface Handlers {
  start(info: StartInfo): void;
  state(m: StateMsg, bytes: number): void;
  msg(items: string[]): void;
  over(result: string): void;
  diplo(m: any): void;
  status(text: string): void;
  error(text: string, fatal: boolean): void;
  closed(): void;
}

export class Connection {
  private ws!: WebSocket;
  private nextId = 1;
  private ended = false;

  constructor(map: string, options: JoinOptions, private h: Handlers) {
    this.open({ t: 'join', map, options });
  }

  /** 끊겼던 판에 다시 접속. */
  resume(sid: string) { if (!this.ended) this.open({ t: 'resume', sid }); }

  private open(first: Record<string, unknown>) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = (this.ws = new WebSocket(`${proto}://${location.host}/ws`));
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => ws.send(JSON.stringify(first));
    ws.onmessage = (ev) => {
      if (ws !== this.ws) return;
      if (ev.data instanceof ArrayBuffer) {
        this.h.state(decodeState(ev.data), ev.data.byteLength);
        return;
      }
      const m = JSON.parse(ev.data);
      switch (m.t) {
        case 'start': this.h.start(m); break;
        case 'msg': this.h.msg(m.items); break;
        case 'over': this.h.over(m.result); break;
        case 'diplo': this.h.diplo(m); break;
        case 'map_status': this.h.status(m.progress ?? m.state); break;
        case 'error': this.h.error(m.error, Boolean(m.fatal)); break;
      }
    };
    ws.onclose = () => { if (ws === this.ws && !this.ended) this.h.closed(); };
  }

  get connected() { return this.ws.readyState === WebSocket.OPEN; }

  send(cmd: Record<string, unknown>) {
    if (this.ws.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(cmd));
  }

  command(units: number[][], ships: number[], x: number, y: number, attack: boolean, r: number) {
    this.send({ t: 'command', id: this.nextId++, units, ships, x, y, attack, r });
  }

  close() { this.ended = true; this.ws.close(); }
}
