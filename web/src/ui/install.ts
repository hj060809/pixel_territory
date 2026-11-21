// 모바일에서 브라우저로 열면: 웹 앱 설치(주소창 없이 화면 전체)와 브라우저에서 계속하기 중에서 고른다.
// 설치 방법은 환경마다 달라서 맞춰 보여 준다. 브라우저에서 계속하면 '게임 시작'을 누를 때 주소창을 내린다 (안드로이드).
// 브라우저를 고르면 기억해 두고 다음부터는 묻지 않는다 (이 브라우저에만). PC는 해당 없음.

import { canFullscreen, isStandalone } from './device.ts';

const CHOSE_BROWSER = 'pt.browser';
const choseBrowser = () => { try { return localStorage.getItem(CHOSE_BROWSER) === '1'; } catch { return false; } };

// 안드로이드 Chrome: 설치할 수 있으면 이 이벤트가 온다 (페이지를 열자마자 올 수 있어서 처음부터 받아 둔다)
let installEvent: any = null;
const waiting: (() => void)[] = [];
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault();
  installEvent = e;
  waiting.splice(0).forEach((f) => f());
});

/** 앱 설치(홈 화면에 추가) 조건을 맞추는 최소 서비스 워커 (아무것도 저장하지 않는다). */
export function registerServiceWorker() {
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(() => {});
}

/** 모바일인데 앱으로 열지 않았고 아직 브라우저를 고르지 않았으면 true (고르기 화면). ?nogate=1: 개발·시험용으로 건너뛰기. */
export function needsInstall(touchDevice: boolean): boolean {
  return touchDevice && !isStandalone() && !choseBrowser() && !new URLSearchParams(location.search).has('nogate');
}

type Env = 'kakao' | 'inapp' | 'ios' | 'samsung' | 'android';

function env(): Env {
  const ua = navigator.userAgent;
  if (/KAKAOTALK/i.test(ua)) return 'kakao';
  if (/Instagram|FBAN|FBAV|NAVER|Line\/|DaumApps|everytimeApp|Whale\/.*Mobile.*inapp/i.test(ua)) return 'inapp';
  if (/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'ios';
  if (/SamsungBrowser/i.test(ua)) return 'samsung';
  return 'android';
}

/** 고르기 화면: 앱 설치 안내 + 브라우저에서 계속하기 (onBrowser: 로비로). */
export function showInstallGate(onBrowser: () => void) {
  const back = document.createElement('div');
  back.className = 'install-gate';
  const box = document.createElement('div');
  box.className = 'box';
  back.appendChild(box);
  const add = (tag: string, cls: string, html: string) => {
    const e = document.createElement(tag);
    e.className = cls;
    e.innerHTML = html;
    box.appendChild(e);
    return e;
  };
  add('img', 'icon', '').setAttribute('src', '/icon-192.png');
  add('div', 'title', '어떻게 플레이할까요?');
  add('div', 'why', '<b>앱으로 설치</b>하면 홈 화면 아이콘으로 열고, 주소창 없이 화면 전체로 플레이합니다 (몇 초면 끝나고 따로 내려받는 것은 없습니다).'
    + (canFullscreen() ? ' <b>브라우저에서 계속</b>해도 게임 시작을 누르면 주소창이 내려갑니다.' : ' 브라우저에서 계속하면 주소창이 보이는 채로 플레이합니다.'));
  add('div', 'sub', '앱으로 설치하기');
  const steps = add('ol', 'steps', '');
  const step = (html: string) => { const li = document.createElement('li'); li.innerHTML = html; steps.appendChild(li); };
  const actions = add('div', 'actions', '');
  const button = (text: string, fn: () => void, main = false) => {
    const b = document.createElement('button');
    b.className = `t-btn ${main ? 'ok' : ''}`;
    b.textContent = text;
    b.addEventListener('click', fn);
    actions.appendChild(b);
    return b;
  };
  const copy = () => {
    navigator.clipboard?.writeText(location.origin + '/').then(() => { copyBtn.textContent = '복사했습니다'; }).catch(() => {});
  };
  let copyBtn: HTMLButtonElement;

  switch (env()) {
    case 'kakao':
      step('카카오톡 안의 브라우저에서는 설치할 수 없습니다.');
      step('아래 <b>기본 브라우저로 열기</b>를 누르거나, 오른쪽 아래 <b>⋮</b> → <b>다른 브라우저로 열기</b>');
      step('열린 Chrome이나 Safari에서 이 안내를 따라 설치');
      button('기본 브라우저로 열기', () => { location.href = 'kakaotalk://web/openExternal?url=' + encodeURIComponent(location.origin + '/'); }, true);
      copyBtn = button('주소 복사', copy);
      break;
    case 'inapp':
      step('이 앱 안의 브라우저에서는 설치할 수 없습니다.');
      step('메뉴(⋮ 또는 공유)에서 <b>브라우저로 열기</b>를 누르거나, 주소를 복사해 Chrome·Safari에 붙여 넣기');
      step('열린 브라우저에서 이 안내를 따라 설치');
      copyBtn = button('주소 복사', copy, true);
      break;
    case 'ios':
      step('Safari 아래(아이패드는 위)의 <b>공유 버튼</b> <span class="key">□↑</span> 을 누르기');
      step('목록에서 <b>홈 화면에 추가</b> → <b>추가</b>');
      step('홈 화면의 <b>Pixel Territory</b> 아이콘으로 실행');
      copyBtn = button('주소 복사', copy);
      break;
    case 'samsung':
      step('아래 <b>≡ 메뉴</b> → <b>현재 페이지 추가</b> → <b>홈 화면</b>');
      step('홈 화면의 <b>Pixel Territory</b> 아이콘으로 실행');
      copyBtn = button('주소 복사', copy);
      break;
    default: {
      step('아래 <b>앱 설치</b>를 누르거나, 오른쪽 위 <b>⋮</b> → <b>홈 화면에 추가</b> (또는 <b>앱 설치</b>)');
      step('홈 화면의 <b>Pixel Territory</b> 아이콘으로 실행');
      const inst = button('앱 설치', async () => {
        if (!installEvent) return;
        installEvent.prompt();
        const r = await installEvent.userChoice.catch(() => null);
        if (r?.outcome === 'accepted') {
          inst.textContent = '설치했습니다 · 홈 화면의 아이콘으로 실행해 주세요';
          inst.disabled = true;
        }
        installEvent = null;
      }, true);
      const ready = () => { inst.style.display = ''; };
      inst.style.display = 'none';                    // Chrome이 설치를 허락하면 보인다
      if (installEvent) ready(); else waiting.push(ready);
      copyBtn = button('주소 복사', copy);
    }
  }
  const alt = add('div', 'alt', '');                 // 브라우저에서 계속하기 (기억해 두고 다음부터 묻지 않는다)
  const go = document.createElement('button');
  go.className = 't-btn';
  go.textContent = '브라우저에서 계속하기';
  go.addEventListener('click', () => {
    try { localStorage.setItem(CHOSE_BROWSER, '1'); } catch { /* 저장 못 해도 그대로 */ }
    back.remove();
    onBrowser();
  });
  alt.appendChild(go);
  window.addEventListener('appinstalled', () => {
    add('div', 'done', '설치했습니다. 홈 화면의 Pixel Territory 아이콘으로 실행해 주세요.');
  });
  document.body.appendChild(back);
}
