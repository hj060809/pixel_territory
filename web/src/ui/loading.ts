// 로딩 화면: 가운데 돌아가는 점 10개(옅어지며 따라감)와 진행 단계, 지난 시간 (데스크톱과 같은 모양).

export class Loading {
  private el: HTMLDivElement;
  private msg: HTMLDivElement;
  private sec: HTMLDivElement;
  private dots: HTMLElement[] = [];
  private start = performance.now();
  private raf = 0;

  constructor(parent: HTMLElement = document.body) {
    this.el = document.createElement('div');
    this.el.className = 'loading';
    const sp = document.createElement('div');
    sp.className = 'spinner';
    for (let k = 0; k < 10; k++) {
      const d = document.createElement('i');
      const r = Math.max(1, Math.floor(4 - k * 0.3)) * 2;
      d.style.width = d.style.height = `${r}px`;
      const c = 230 - k * 18;
      d.style.background = `rgb(${c},${c},${Math.min(255, c + 20)})`;
      sp.appendChild(d);
      this.dots.push(d);
    }
    this.msg = document.createElement('div');
    this.msg.className = 'msg';
    this.sec = document.createElement('div');
    this.sec.className = 'sec';
    this.el.append(sp, this.msg, this.sec);
    parent.appendChild(this.el);
    const tick = () => {
      const t = (performance.now() / 1000) * 4;
      this.dots.forEach((d, k) => {
        const a = t - k * 0.35;
        d.style.transform = `translate(${Math.cos(a) * 22 - 2}px, ${Math.sin(a) * 22 - 2}px)`;
      });
      this.sec.textContent = `${((performance.now() - this.start) / 1000).toFixed(1)}초`;
      this.raf = requestAnimationFrame(tick);
    };
    tick();
  }

  set(text: string) { this.msg.textContent = text; }

  show(text: string) {
    this.start = performance.now();
    this.el.classList.remove('hidden');
    this.set(text);
  }

  hide() { this.el.classList.add('hidden'); }

  /** 메뉴 배경 위에 반투명하게 (게임 시작 때: 설정 화면에서 게임으로 넘어가는 사이). */
  soft(on = true) { this.el.classList.toggle('soft', on); }

  /** 천천히 사라진다 (첫 장면이 그려진 뒤). */
  fadeOut(ms = 250) {
    this.el.classList.add('fade');
    setTimeout(() => { this.hide(); this.el.classList.remove('fade'); }, ms);
  }

  dispose() { cancelAnimationFrame(this.raf); this.el.remove(); }
}
