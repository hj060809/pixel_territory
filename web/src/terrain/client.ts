// 화면 스레드 쪽: 지형 워커에 '이 계절, 이 물결 시각의 그림'을 부탁하고 받는다. 한 번에 하나만 부탁한다.

export interface TerrainFrame {
  rgba: Uint8Array;
  ice: Uint8Array;
  mat: Uint8Array;
  season: number[] | null;
  waveT: number | null;
}

export class TerrainClient {
  private worker: Worker;
  private nextId = 1;
  private waiting = new Map<number, (f: TerrainFrame) => void>();
  busy = false;

  private constructor(worker: Worker) {
    this.worker = worker;
  }

  /** raw: 압축을 푼 지도 묶음. 워커에 복사해 넘기고 준비가 끝나면 돌아온다. */
  static async create(raw: ArrayBuffer, progress: (t: string) => void = () => {}): Promise<TerrainClient> {
    const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
    const c = new TerrainClient(worker);
    await new Promise<void>((resolve, reject) => {
      worker.onerror = (e) => reject(new Error(e.message));
      worker.onmessage = (ev) => {
        const m = ev.data;
        if (m.type === 'progress') progress(m.text);
        else if (m.type === 'ready') resolve();
      };
      worker.postMessage({ type: 'init', raw: raw.slice(0) });
    });
    worker.onmessage = (ev) => {
      const m = ev.data;
      if (m.type === 'frame') {
        const done = c.waiting.get(m.id);
        c.waiting.delete(m.id);
        c.busy = c.waiting.size > 0;
        done?.(m);
      }
    };
    return c;
  }

  request(season: number[] | null, waveT: number | null): Promise<TerrainFrame> {
    const id = this.nextId++;
    this.busy = true;
    return new Promise((resolve) => {
      this.waiting.set(id, (m: any) => resolve({ rgba: m.rgba, ice: m.ice, mat: m.mat, season, waveT }));
      this.worker.postMessage({ type: 'frame', id, season, waveT });
    });
  }

  dispose() { this.worker.terminate(); }
}
