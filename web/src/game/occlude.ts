// 가림 방지: 정보 상자나 버튼 아래에 병사·건물·배(또는 놓을 건물 그림)가 있으면 그 상자를 반투명하게 (.covered).
// 상자는 그대로 누를 수 있다. PC와 터치 모두 쓴다.

export function fadeCovered(els: Iterable<HTMLElement>, pts: [number, number][], pad = 6) {
  for (const el of els) {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) { el.classList.remove('covered'); continue; }
    const x0 = r.left - pad, x1 = r.right + pad, y0 = r.top - pad, y1 = r.bottom + pad;
    let hit = false;
    for (const [x, y] of pts) if (x >= x0 && x <= x1 && y >= y0 && y <= y1) { hit = true; break; }
    el.classList.toggle('covered', hit);
  }
}
