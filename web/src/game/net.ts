// 서버와 주고받기 (WebSocket /ws). 처음 메시지 하나 (join: 싱글, room_create/room_join: 멀티 대기실, resume: 다시 접속)
// → start(나라, 자원지, 규칙, sid, token) → 걸음마다 이진 상태 + 알림 JSON. 명령은 JSON (sim/commands.py, server/session.py 설명).
// 연결이 끊기면 resume(sid, token)으로 같은 판의 내 자리에 다시 접속한다 (같은 Connection 객체 안에서 소켓만 새로).
// 대기실 → 판: 대기실 화면이 연결을 들고 있다가 start가 오면 hold()로 받은 것을 모아 두고, 게임 화면이 setHandlers()로 이어받는다
// (그사이 온 상태 메시지는 하나도 버리지 않는다: 바뀐 것만 보내므로 빠지면 안 된다).

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
  error(text: string, fatal: boolean, busy?: boolean): void;   // busy: 서버가 꽉 찼다 (접속자·판·방 상한)
  closed(): void;
  seats?(m: { away: number[]; gone: number[] }): void;   // 사람 나라의 접속 상태 (멀티)
  other?(m: any): void;                    // 그 밖의 JSON (대기실: room, room_error, room_kicked, room_closed)
}

type Item = ArrayBuffer | any;

export class Connection {
  private ws!: WebSocket;
  private nextId = 1;
  private ended = false;
  private h: Handlers | null;
  private buf: Item[] = [];                // 이어받을 화면이 아직 없을 때 받은 것 (차례대로)

  /** 싱글: new Connection(지도 키, 설정, handlers). 그 밖의 처음 메시지는 Connection.open. */
  constructor(map: string | null, options: JoinOptions | null, h: Handlers | null, first?: Record<string, unknown>) {
    this.h = h;
    this.open(first ?? { t: 'join', map, options });
  }

  static open(first: Record<string, unknown>, h: Handlers | null): Connection {
    return new Connection(null, null, h, first);
  }

  /** 끊겼던 판에 다시: sid (판), token (내 자리: 사람이 여럿인 판에서 자리를 찾는다). */
  resume(sid: string, token?: string | null) { if (!this.ended) this.open({ t: 'resume', sid, token }); }

  /** 받는 화면을 잠시 비운다 (first: 맨 앞에 다시 넣을 메시지, 예: 대기실이 받은 start). */
  hold(first?: any) { this.h = null; if (first !== undefined) this.buf.unshift(first); }

  /** 받는 화면을 정하고, 그사이 모아 둔 것을 차례대로 넘긴다. */
  setHandlers(h: Handlers) {
    // 다음 마이크로태스크에 넘긴다: 부르는 쪽(게임 화면 생성자)이 다 만들어진 뒤에 start가 가도록. 그사이 온 것도 buf에 쌓인다
    queueMicrotask(() => {
      this.h = h;
      const b = this.buf;
      this.buf = [];
      for (const it of b) this.deliver(it);
    });
  }

  private deliver(it: Item) {
    const h = this.h;
    if (!h) { this.buf.push(it); return; }
    if (it instanceof ArrayBuffer) { h.state(decodeState(it), it.byteLength); return; }
    const m = it;
    switch (m.t) {
      case 'start': h.start(m); break;
      case 'msg': h.msg(m.items); break;
      case 'over': h.over(m.result); break;
      case 'diplo': h.diplo(m); break;
      case 'seats': h.seats?.(m); break;
      case 'map_status': h.status(m.progress ?? m.state); break;
      case 'error': h.error(m.error, Boolean(m.fatal), Boolean(m.busy)); break;
      default: h.other?.(m);
    }
  }

  private open(first: Record<string, unknown>) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = (this.ws = new WebSocket(`${proto}://${location.host}/ws`));
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => ws.send(JSON.stringify(first));
    ws.onmessage = (ev) => {
      if (ws !== this.ws) return;
      this.deliver(ev.data instanceof ArrayBuffer ? ev.data : JSON.parse(ev.data));
    };
    ws.onclose = () => { if (ws === this.ws && !this.ended) this.h?.closed(); };
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
