// 기기 판별: 터치로 하는 기기인가 (휴대폰·태블릿). 처음 화면을 정할 때 쓰고,
// 게임 중에는 '마지막으로 쓴 입력'(터치 / 마우스)으로 바꾼다 (마우스를 꽂은 태블릿은 PC 방식으로).

export function isTouchDevice(): boolean {
  const ua = navigator.userAgent;
  if (/Android|iPhone|iPad|iPod|Mobile|Silk|Kindle/i.test(ua)) return true;
  if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1) return true;     // Mac처럼 보이는 아이패드
  return matchMedia('(pointer: coarse)').matches && !matchMedia('(any-pointer: fine)').matches;
}

/** 화면을 터치 방식으로 (body.touch: 터치용 버튼과 크기). */
export function setTouchMode(on: boolean) { document.body.classList.toggle('touch', on); }
export function touchMode(): boolean { return document.body.classList.contains('touch'); }
