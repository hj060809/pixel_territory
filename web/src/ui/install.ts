// 모바일: 웹 앱 설치(홈 화면에 추가 → 주소창 없이 전체 화면)와 전체 화면 안내.
// - 로비의 [앱으로 설치] 버튼: 안드로이드 Chrome은 바로 설치 창, 그 밖의 환경은 설치 방법 안내 상자.
// - 처음 로비에서 한 번: '싱글·멀티 플레이를 누르면 전체 화면이 됩니다' (주소창을 못 내리는 브라우저는 앱 설치를 권한다).

import { canFullscreen, isStandalone } from './device.ts';

// 안드로이드 Chrome: 설치할 수 있으면 이 이벤트가 온다 (페이지를 열자마자 올 수 있어서 처음부터 받아 둔다)
let installEvent: any = null;
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  installEvent = e;
});

/** 앱 설치(홈 화면에 추가) 조건을 맞추는 최소 서비스 워커 (아무것도 저장하지 않는다). */
export function registerServiceWorker() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

type Env = 'kakao' | 'inapp' | 'ios' | 'samsung' | 'android';

function env(): Env {
  const ua = navigator.userAgent;
  if (/KAKAOTALK/i.test(ua)) return 'kakao';
  if (/Instagram|FBAN|FBAV|NAVER|Line\/|DaumApps|everytimeApp/i.test(ua)) return 'inapp';
  if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios';
  if (/SamsungBrowser/i.test(ua)) return 'samsung';
  return 'android';
}

/** 안내 상자 하나 (어두운 배경, 바깥을 누르면 닫힌다). */
function dialog(title: string, body: string, buttons: [string, () => void, boolean?][], onClose?: () => void) {
  const back = document.createElement('div');
  back.className = 'install-gate';
  const box = document.createElement('div');
  box.className = 'box';
  back.appendChild(box);
  const close = () => { back.remove(); onClose?.(); };
  box.innerHTML = `<img class="icon" src="/icon-192.png"><div class="title">${title}</div><div class="why">${body}</div>`;
  const row = document.createElement('div');
  row.className = 'actions';
  box.appendChild(row);
  for (const [text, fn, main] of buttons) {
    const b = document.createElement('button');
    b.className = `t-btn ${main ? 'ok' : ''}`;
    b.textContent = text;
    b.addEventListener('click', () => fn());
    row.appendChild(b);
  }
  back.addEventListener('click', (e) => { if (e.target === back) close(); });
  document.body.appendChild(back);
  return { box, close };
}

/** 로비 [앱으로 설치]: 안드로이드 Chrome은 바로 설치 창, 아니면 그 환경의 설치 방법. */
export async function installApp() {
  if (installEvent) {
    installEvent.prompt();
    await installEvent.userChoice.catch(() => null);
    installEvent = null;
    return;
  }
  const url = location.origin + '/';
  const copy = () => navigator.clipboard?.writeText(url).catch(() => {});
  const steps: Record<Env, string> = {
    kakao: '카카오톡 안의 브라우저에서는 설치할 수 없습니다. <b>기본 브라우저로 열기</b>를 누르거나 <b>⋮ → 다른 브라우저로 열기</b>로 연 뒤 다시 눌러 주세요.',
    inapp: '이 앱 안의 브라우저에서는 설치할 수 없습니다. 메뉴에서 <b>브라우저로 열기</b>를 누르거나 주소를 복사해 Chrome·Safari에서 열어 주세요.',
    ios: 'Safari의 <b>공유 버튼 □↑</b> → <b>홈 화면에 추가</b> → <b>추가</b>. 홈 화면의 Pixel Territory 아이콘으로 열면 주소창 없이 플레이합니다.',
    samsung: '아래 <b>≡ 메뉴 → 현재 페이지 추가 → 홈 화면</b>. 홈 화면의 Pixel Territory 아이콘으로 열면 주소창 없이 플레이합니다.',
    android: '오른쪽 위 <b>⋮ → 홈 화면에 추가</b> (또는 <b>앱 설치</b>). 홈 화면의 Pixel Territory 아이콘으로 열면 주소창 없이 플레이합니다.',
  };
  const e = env();
  const buttons: [string, () => void, boolean?][] = [];
  if (e === 'kakao') buttons.push(['기본 브라우저로 열기', () => { location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(url); }, true]);
  buttons.push(['주소 복사', copy], ['닫기', () => d.close()]);
  const d = dialog('앱으로 설치하기', steps[e], buttons);
}

const NOTE_SEEN = 'pt.fsnote';

/** 처음 로비에서 한 번: 전체 화면 안내 ([확인]을 누르면 다음부터 띄우지 않는다). 앱으로 열었으면 띄우지 않는다. */
export function showFullscreenNote() {
  if (isStandalone()) return;
  try { if (localStorage.getItem(NOTE_SEEN) === '1') return; } catch { /* 그대로 */ }
  if (document.querySelector('.install-gate')) return;
  const remember = () => { try { localStorage.setItem(NOTE_SEEN, '1'); } catch { /* 그대로 */ } };
  const text = canFullscreen()
    ? '<b>싱글·멀티 플레이</b>를 누르면 주소창이 내려가고 전체 화면이 됩니다.'
    : '이 브라우저는 주소창을 내릴 수 없습니다. 주소창 없이 하려면 로비의 <b>앱으로 설치</b>를 눌러 주세요.';
  const d = dialog('전체 화면으로 플레이', text, [['확인', () => { remember(); d.close(); }, true]], remember);
}
