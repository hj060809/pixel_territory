// 지형 뷰어 (3단계): 데스크톱 pygame 뷰어와 같은 화면과 조작.
// 주소: /?map=<지도 키>  (없으면 첫 데모 지도)

import '../ui/style.css';
import { TerrainScene } from '../terrain/scene.ts';
import { Camera } from '../sim/camera.ts';
import { Loading } from '../ui/loading.ts';
import { Life } from '../life/life.ts';

const HELP = [
  '마우스 드래그 / 방향키: 이동    휠 / +,-: 확대',
  'Space: 시간 자동 흐름 켜기/끄기    Q / E: 30분 뒤로 / 앞으로',
  'Y: 계절 자동 흐름 켜기/끄기    [ / ]: 반 달 뒤로 / 앞으로',
  'P: 물결 켜기/끄기    A / D: 물결 애니메이션 느리게 / 빠르게',
  'L: 생물 켜기/끄기    마우스를 대면 새와 물고기가 피하고, 클릭하면 놀라거나 물에 파문이 인다',
  'H: 도움말',
];

async function main() {
  const canvas = document.createElement('canvas');
  canvas.id = 'view';
  document.body.appendChild(canvas);
  const hud = document.createElement('div');
  hud.className = 'hud';
  document.body.appendChild(hud);
  const loading = new Loading();
  loading.show('지도 목록 받는 중...');

  const gl = canvas.getContext('webgl2', { antialias: false, alpha: false, preserveDrawingBuffer: true });
  if (!gl) { loading.set('이 브라우저는 WebGL2를 지원하지 않습니다'); return; }
  const params = new URLSearchParams(location.search);
  let key = params.get('map');
  if (!key) {
    const list = await (await fetch('/api/maps')).json();
    key = list.demo[0].key;
  }
  const scene = await TerrainScene.load(gl, `/api/maps/${key}/bundle.tsb`,
    { hour: Number(params.get('hour') ?? 12), dayLength: 120, year: 0.35, yearLength: 240 }, (t) => loading.set(t));
  const life = new Life(scene.bundle, 0);
  let lifeOn = true;
  const cam = new Camera(scene.W, scene.H);
  let showHelp = true;
  const dpr = () => window.devicePixelRatio || 1;
  const resize = () => {
    canvas.width = Math.round(window.innerWidth * dpr());
    canvas.height = Math.round(window.innerHeight * dpr());
    cam.resize(window.innerWidth, window.innerHeight);
  };
  resize();
  cam.fit();
  window.addEventListener('resize', resize);
  loading.hide();

  // ---- 입력
  const keys = new Set<string>();
  let drag = false, dragDist = 0;
  let mouse: [number, number] | null = null;
  let click: [number, number] | null = null;
  canvas.addEventListener('wheel', (e) => { e.preventDefault(); cam.zoomTo(1.15 ** (-e.deltaY / 100), [e.clientX, e.clientY]); }, { passive: false });
  canvas.addEventListener('mousedown', (e) => { if (e.button === 0) { drag = true; dragDist = 0; } });
  window.addEventListener('mouseup', (e) => {
    if (e.button === 0 && drag) {
      drag = false;
      if (dragDist < 5) click = cam.toMap(e.clientX, e.clientY);      // 거의 안 움직였으면 클릭
    }
  });
  window.addEventListener('mousemove', (e) => {
    mouse = cam.toMap(e.clientX, e.clientY);
    if (drag) { dragDist += Math.abs(e.movementX) + Math.abs(e.movementY); cam.pan(e.movementX, e.movementY); }
  });
  canvas.addEventListener('mouseleave', () => { mouse = null; });
  window.addEventListener('keyup', (e) => keys.delete(e.key));
  window.addEventListener('keydown', (e) => {
    keys.add(e.key);
    const center: [number, number] = [cam.viewW / 2, cam.viewH / 2];
    switch (e.key) {
      case ' ': scene.cycle.auto = !scene.cycle.auto; e.preventDefault(); break;
      case 'q': case 'Q': scene.cycle.advance(-0.5); break;
      case 'e': case 'E': scene.cycle.advance(0.5); break;
      case 'y': case 'Y': scene.season.auto = !scene.season.auto; break;
      case '[': scene.season.advance(-1 / 24); void scene.refresh(true); break;
      case ']': scene.season.advance(1 / 24); void scene.refresh(true); break;
      case 'p': case 'P': scene.wavesOn = !scene.wavesOn; void scene.refresh(); break;
      case 'd': case 'D': scene.waveFps = Math.min(scene.waveFps + 0.5, 10); break;
      case 'a': case 'A': scene.waveFps = Math.max(scene.waveFps - 0.5, 0.5); break;
      case '+': case '=': cam.zoomTo(1.25, center); break;
      case '-': cam.zoomTo(1 / 1.25, center); break;
      case 'l': case 'L': lifeOn = !lifeOn; break;
      case 'h': case 'H': showHelp = !showHelp; break;
    }
    hudWait = 1;
  });

  // ---- 루프
  let last = performance.now(), hudWait = 1, fps = 60;
  const frame = (now: number) => {
    const dt = Math.min((now - last) / 1000, 0.1);
    last = now;
    fps = fps * 0.95 + (1 / Math.max(dt, 1e-3)) * 0.05;
    cam.ease(dt);
    const step = (600 * dt) / cam.zoom;
    const dx = (+keys.has('ArrowRight') - +keys.has('ArrowLeft')) * step;
    const dy = (+keys.has('ArrowDown') - +keys.has('ArrowUp')) * step;
    if (dx || dy) { cam.x += dx; cam.y += dy; cam.clamp(); }
    scene.update(dt, dt);
    if (lifeOn) life.update(dt, mouse, click);
    click = null;
    scene.draw(canvas.width, canvas.height, cam.x, cam.y, cam.zoom * dpr(), lifeOn ? life : null);
    hudWait += dt;
    if (hudWait >= 0.25) {
      hudWait = 0;
      const c = scene.cycle, s = scene.season;
      const line = `${c.label()}  ${c.auto ? '자동' : '정지'}  해 고도 ${c.sunAlt().toFixed(0)}°   ` +
        `${s.label()} ${s.auto ? '자동' : '정지'}   물결 ${scene.wavesOn ? '켜짐' : '꺼짐'} (속도 ${scene.waveFps.toFixed(1)})   ` +
        `x${cam.zoom.toFixed(1)}   ${fps.toFixed(0)} fps`;
      hud.textContent = [line, ...(showHelp ? HELP : [])].join('\n');
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
  (window as any).__viewer = { scene, cam, life };
}

main().catch((e) => {
  console.error(e);
  document.body.insertAdjacentHTML('beforeend', `<div class="hud">오류: ${String(e)}</div>`);
});
