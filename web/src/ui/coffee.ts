// 개발자에게 커피 (Buy Me a Coffee): 로비 오른쪽 아래 버튼과 창 (menu/lobby.ts), 판이 끝난 결과 표시 아래 한 줄 (game/hud.ts),
// 서버가 꽉 찼다는 안내 (busyBox: 로비·멀티 화면·대기실, 싱글 시작 실패 화면)에 '서버비 보내주기'.

export const COFFEE_URL = 'https://buymeacoffee.com/hjbanf89';

/** 커피 잔 그림 (도트 느낌: 각진 잔 + 손잡이 + 김). */
export function cupIcon(size: number): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 16 16" shape-rendering="crispEdges" aria-hidden="true">
    <path d="M5 1h1v1H5zM6 2h1v2H6zM5 4h1v1H5zM9 1h1v1H9zM10 2h1v2h-1zM9 4h1v1H9z" fill="rgba(255,255,255,0.75)"/>
    <path d="M2 6h10v6H3v-1H2z" fill="rgb(250,244,228)"/>
    <path d="M3 7h8v1H3z" fill="rgb(120,72,40)"/>
    <path d="M12 7h2v3h-1v1h-1v-1h1V8h-1z" fill="rgb(250,244,228)"/>
    <path d="M3 12h8v1H4z" fill="rgb(200,190,170)"/>
    <path d="M1 14h13v1H1z" fill="rgb(200,190,170)"/>
  </svg>`;
}

/** 새 탭으로 여는 커피 링크 (cls: 모양). */
export function coffeeLink(label: string, cls: string, icon = 20): HTMLAnchorElement {
  const a = document.createElement('a');
  a.className = cls;
  a.href = COFFEE_URL;
  a.target = '_blank';
  a.rel = 'noopener noreferrer';
  a.innerHTML = `${cupIcon(icon)}<span>${label}</span>`;
  return a;
}

/** '불쌍한 개발자에게 서버비 보내주기!' + 커피 버튼 (서버가 꽉 찼다는 안내마다). */
export function serverPlea(): HTMLDivElement {
  const d = document.createElement('div');
  d.className = 'server-plea';
  const t = document.createElement('div');
  t.textContent = '불쌍한 개발자에게 서버비 보내주기!';
  d.append(t, coffeeLink('서버비 보내기', 'coffee-link', 22));
  return d;
}

/** 서버가 꽉 찼다는 안내 창: 반투명 검은 배경 위 상자 (제목, 설명, 서버비, 버튼들). 버튼은 [이름, 할 일 (창을 닫을지 돌려준다)]. */
export function busyBox(parent: HTMLElement, text: string, buttons: [string, () => boolean | void][]): () => void {
  const back = document.createElement('div');
  back.className = 'modal-back busy-back';
  const box = document.createElement('div');
  box.className = 'modal coffee busy';
  const title = document.createElement('div');
  title.className = 'modal-title';
  title.textContent = '지금은 접속자가 많아요';
  const body = document.createElement('div');
  body.className = 'coffee-text';
  body.textContent = text.replace('. ', '.\n');
  box.append(title, body, serverPlea());
  const row = document.createElement('div');
  row.className = 'busy-btns';
  const close = () => back.remove();
  for (const [label, fn] of buttons) {
    const b = document.createElement('button');
    b.className = 'btn';
    b.textContent = label;
    b.addEventListener('click', () => { if (fn() !== false) close(); });
    row.appendChild(b);
  }
  box.appendChild(row);
  back.appendChild(box);
  parent.appendChild(back);
  return close;
}
