// 카메라: 최상위 viewer/app.py의 카메라를 옮겼다.
// - 처음에는 지도 전체가 화면에 딱 맞는 배율. 더 작게/크게 볼 수 있고, 지나갈 때 딱 맞는 배율에서 한 번 멈춘다.
// - 휠로 바꾼 목표 배율을 실제 배율이 부드럽게 따라간다 (커서 아래 지점은 그대로).
// 단위: 배율 = 화면(CSS) 픽셀 / 지도 칸, 카메라 = 화면 왼쪽 위의 지도 좌표.

export class Camera {
  zoom = 1;
  zoomTarget = 1;
  x = 0;
  y = 0;
  viewW = 1;
  viewH = 1;
  private anchor: [number, number] = [0, 0];

  constructor(readonly mapW: number, readonly mapH: number) {}

  resize(w: number, h: number) {
    this.viewW = Math.max(w, 1);
    this.viewH = Math.max(h, 1);
    this.clamp();
  }

  fitZoom() { return Math.min(this.viewW / this.mapW, this.viewH / this.mapH); }
  zoomMin() { return this.fitZoom() * 0.25; }
  zoomMax() { return Math.max(12.0, this.fitZoom() * 2); }

  fit() {
    this.zoom = this.zoomTarget = this.fitZoom();
    this.x = this.y = 0;
    this.clamp();
  }

  toMap(sx: number, sy: number): [number, number] {
    return [this.x + sx / this.zoom, this.y + sy / this.zoom];
  }

  clamp() {
    if (this.zoom < this.zoomMin()) this.zoom = this.zoomMin();
    this.zoomTarget = Math.min(Math.max(this.zoomTarget, this.zoomMin()), this.zoomMax());
    const vw = this.viewW / this.zoom, vh = this.viewH / this.zoom;
    // 지도가 화면보다 작은 방향은 가운데에, 큰 방향은 지도 밖으로 나가지 않게
    this.x = this.mapW <= vw ? (this.mapW - vw) / 2 : Math.min(Math.max(this.x, 0), this.mapW - vw);
    this.y = this.mapH <= vh ? (this.mapH - vh) / 2 : Math.min(Math.max(this.y, 0), this.mapH - vh);
  }

  /** 목표 배율을 factor배로. 화면에 딱 맞는 배율을 건너뛰게 되면 그 배율에서 멈춘다. */
  zoomTo(factor: number, anchor: [number, number]) {
    const old = this.zoomTarget;
    let next = Math.min(Math.max(old * factor, this.zoomMin()), this.zoomMax());
    const fit = this.fitZoom();
    if ((old < fit && fit < next) || (old > fit && fit > next)) next = fit;
    this.zoomTarget = next;
    this.anchor = anchor;
  }

  ease(dt: number) {
    if (this.zoom === this.zoomTarget) return;
    let z = this.zoom + (this.zoomTarget - this.zoom) * (1.0 - Math.exp(-dt * 14.0));
    if (Math.abs(z - this.zoomTarget) < 0.002) z = this.zoomTarget;
    this.setZoom(z, this.anchor);
  }

  setZoom(zoom: number, anchor: [number, number]) {
    zoom = Math.min(Math.max(zoom, this.zoomMin()), this.zoomMax());
    if (zoom === this.zoom) return;
    const [ax, ay] = anchor;
    const mx = this.x + ax / this.zoom, my = this.y + ay / this.zoom;    // 커서 아래 지도 좌표 유지
    this.zoom = zoom;
    this.x = mx - ax / zoom;
    this.y = my - ay / zoom;
    this.clamp();
  }

  pan(dxScreen: number, dyScreen: number) {
    this.x -= dxScreen / this.zoom;
    this.y -= dyScreen / this.zoom;
    this.clamp();
  }

  /** 화면에서 보이는 지도 칸 수. */
  view(): [number, number] { return [this.viewW / this.zoom, this.viewH / this.zoom]; }
}
