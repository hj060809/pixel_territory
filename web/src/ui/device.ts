// 기기 판별: 터치로 하는 기기인가 (휴대폰·태블릿). 처음 화면을 정할 때 쓰고,
// 게임 중에는 '마지막으로 쓴 입력'(터치 / 마우스)으로 바꾼다 (마우스를 꽂은 태블릿은 PC 방식으로).

export function isTouchDevice(): boolean {
  const ua = navigator.userAgent;
  if (/Android|iPhone|iPad|iPod|Mobile|Silk|Kindle/i.test(ua)) return true;
  if ((navigator as any).userAgentData?.mobile === true) return true;
  if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) return true;     // Mac처럼 보이는 아이패드
  // '데스크톱 사이트'를 켠 휴대폰은 PC처럼 보이는 이름을 보낸다: 주 입력이 손가락이고 마우스 올리기가 안 되면 터치 기기
  if (navigator.maxTouchPoints > 0 && (matchMedia('(pointer: coarse)').matches || matchMedia('(hover: none)').matches)) return true;
  return false;
}

/** 화면을 터치 방식으로 (body.touch: 터치용 버튼과 크기). */
export function setTouchMode(on: boolean) { document.body.classList.toggle('touch', on); }
export function touchMode(): boolean { return document.body.classList.contains('touch'); }

/** 사이트가 전체 화면을 요청할 수 있나 (안드로이드 Chrome 등. 아이폰 Safari는 안 된다). */
export function canFullscreen(): boolean {
  return !!document.documentElement.requestFullscreen && document.fullscreenEnabled;
}

/** 홈 화면에 추가해서 앱처럼 열었나 (이미 주소창이 없다). */
export function isStandalone(): boolean {
  return matchMedia('(display-mode: fullscreen), (display-mode: standalone)').matches || (navigator as any).standalone === true;
}

/** 전체 화면으로 (주소창을 내린다) + 가로로 고정. 사용자가 무언가를 누른 순간에만 된다 (브라우저 정책). */
export async function enterFullscreen() {
  if (!canFullscreen() || document.fullscreenElement || isStandalone()) return;
  try {
    await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
    await (screen.orientation as any)?.lock?.('landscape');
  } catch { /* 거절되면 그대로 */ }
}

/** 주소창을 내릴 수 없는 기기 (아이폰 Safari)에서 보여 줄 안내. 이미 앱처럼 열었거나 내릴 수 있으면 null. */
export function addToHomeHint(): string | null {
  if (isStandalone() || canFullscreen()) return null;
  return '주소창 없이 하려면: 공유 버튼 → 홈 화면에 추가';
}
