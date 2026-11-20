// 브라우저 게임 확인 (화면 없이 Chrome으로 사람처럼 조작): 웹을 빌드해 둔 상태에서
//   node tools/browser_game_check.mjs <스크린샷 폴더>
// 드래그로 내 병사 고르기 → 식량 자원지 오른쪽 클릭(농장) → Q 두 번(훈련) → 멀리 보기 → 4배속 → 스크린샷과 지연 측정.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(path.dirname(fileURLToPath(import.meta.url)), '../web/package.json'));
const puppeteer = require('puppeteer-core');
const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8772;
const OUT = process.argv[2] ?? '.';
const CHROME = process.env.CHROME ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const srv = spawn('python', ['-m', 'server', '--port', String(PORT)], { cwd: WEB, stdio: 'ignore' });
try {
  for (let i = 0; i < 100; i++) { try { await fetch(`http://127.0.0.1:${PORT}/api/maps`); break; } catch { await sleep(300); } }
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true,
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--window-size=1280,800'], defaultViewport: { width: 1280, height: 800 } });
  const page = await browser.newPage();
  page.on('pageerror', (e) => console.log('페이지 오류:', e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('404')) console.log('브라우저 오류:', m.text()); });
  const t0 = Date.now();
  await page.goto(`http://127.0.0.1:${PORT}/?quick=1&color=6&name=시험`);
  await page.waitForFunction('window.__game && window.__game.st && window.__game.st.units.size > 0', { timeout: 120000, polling: 200 });
  console.log(`판이 열리기까지 ${((Date.now() - t0) / 1000).toFixed(1)}초`);
  await sleep(2500);
  await page.screenshot({ path: path.join(OUT, 'game_start.png') });

  // 1) 내 병사를 감싸는 상자를 드래그
  const box = await page.evaluate(() => {
    const { st, cam } = window.__game;
    const mine = [...st.units.values()].filter((u) => u.own === st.info.me);
    const xs = mine.map((u) => (u.x - cam.x) * cam.zoom), ys = mine.map((u) => (u.y - cam.y) * cam.zoom);
    return [Math.min(...xs) - 12, Math.min(...ys) - 18, Math.max(...xs) + 12, Math.max(...ys) + 8, mine.length];
  });
  await page.mouse.move(box[0], box[1]);
  await page.mouse.down();
  await page.mouse.move((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, { steps: 5 });
  await page.mouse.move(box[2], box[3], { steps: 5 });
  await page.mouse.up();
  const selected = await page.evaluate(() => window.__game.ctl.sel.size);
  console.log(`드래그로 고른 병사 ${selected} / ${box[4]}`);

  // 2) 가장 가까운 식량 자원지를 오른쪽 클릭
  const target = await page.evaluate(() => {
    const { st, cam } = window.__game;
    const mine = [...st.units.values()].filter((u) => u.own === st.info.me);
    const cx = mine.reduce((s, u) => s + u.x, 0) / mine.length, cy = mine.reduce((s, u) => s + u.y, 0) / mine.length;
    const site = st.info.sites.filter((s) => s.kind === 0).sort((a, b) => Math.hypot(a.x - cx, a.y - cy) - Math.hypot(b.x - cx, b.y - cy))[0];
    window.__t_click = performance.now();
    window.__t_moved = 0;
    const iv = setInterval(() => {
      if ([...st.units.values()].some((u) => u.own === st.info.me && u.state !== 0)) { window.__t_moved = performance.now(); clearInterval(iv); }
    }, 2);
    return [(site.x - cam.x) * cam.zoom, (site.y - cam.y) * cam.zoom, site.id];
  });
  await page.mouse.click(target[0], target[1], { button: 'right' });
  await page.waitForFunction('window.__t_moved > 0', { timeout: 5000 });
  const lat = await page.evaluate(() => window.__t_moved - window.__t_click);
  await sleep(1500);
  const farm = await page.evaluate((sid) => [...window.__game.st.builds.values()].some((b) => b.site === sid && b.own === window.__game.st.info.me), target[2]);
  console.log(`오른쪽 클릭 → 병사가 움직인 상태 도착 ${lat.toFixed(0)} ms, 농장 자리 잡힘: ${farm}`);
  await page.screenshot({ path: path.join(OUT, 'game_command.png') });

  // 3) Q 두 번 → 거점 훈련 대기열
  await page.keyboard.press('q');
  await page.keyboard.press('q');
  await sleep(600);
  const q = await page.evaluate(() => Math.max(...[...window.__game.st.builds.values()].filter((b) => b.own === window.__game.st.info.me).map((b) => b.qlen)));
  console.log(`Q 두 번 → 훈련 대기열 ${q}`);

  // 4) 4배속, 한동안 흘린 뒤 멀리서 보기와 전투 근처 보기
  await page.keyboard.press('.');
  await page.keyboard.press('.');
  const runEnd = Date.now() + Number(process.env.RUN_MS ?? 40000);
  let battleShot = false;
  while (Date.now() < runEnd) {                       // 화살·포탄이 처음 보이면 그 자리를 가까이 찍는다
    await sleep(400);
    if (battleShot) continue;
    const at = await page.evaluate(() => {
      const { st, cam } = window.__game;
      const s = st.shots.find((x) => x.kind >= 1) ?? st.shots[0];
      if (!s) return null;
      cam.zoom = cam.zoomTarget = 6;
      const [vw, vh] = cam.view();
      cam.x = s.x1 - vw / 2; cam.y = s.y1 - vh / 2; cam.clamp();
      return [s.x1, s.y1];
    });
    if (at) { await sleep(120); await page.screenshot({ path: path.join(OUT, 'game_battle.png') }); battleShot = true; console.log(`전투 장면 찍음 (${at.map((v) => v.toFixed(0))})`); }
  }
  const info = await page.evaluate(() => {
    const st = window.__game.st;
    return { t: st.time, speed: st.speed, sim: st.simMs, nations: st.nations.map((n) => [n.nUnits, n.nBuildings]), msgs: st.messages.map((m) => m.text) };
  });
  console.log(`게임 시각 ${info.t.toFixed(0)}초 (속도 ×${info.speed}), 서버 걸음 ${info.sim} ms, 나라(병사, 건물) ${JSON.stringify(info.nations)}`);
  console.log(`알림: ${info.msgs.join(' / ')}`);
  await page.evaluate(() => { const c = window.__game.cam; c.zoom = c.zoomTarget = c.fitZoom(); c.clamp(); });
  await sleep(800);
  await page.screenshot({ path: path.join(OUT, 'game_far.png') });
  const fight = await page.evaluate(() => {
    const { st, cam } = window.__game;
    const us = [...st.units.values()];
    let best = null, bn = 0;
    for (const u of us) {
      const n = us.filter((v) => v.own !== u.own && Math.hypot(v.x - u.x, v.y - u.y) < 10).length;
      if (n > bn) { bn = n; best = u; }
    }
    const t = best ?? us[0];
    cam.zoom = cam.zoomTarget = 6;
    const [vw, vh] = cam.view();
    cam.x = t.x - vw / 2; cam.y = t.y - vh / 2; cam.clamp();
    return bn;
  });
  await sleep(800);
  await page.screenshot({ path: path.join(OUT, 'game_near.png') });
  console.log(`가까이 본 곳의 적 병사 수 ${fight}`);

  // 5) 탭을 숨기면 일시정지, 돌아오면 이어 간다
  const setHidden = (h) => page.evaluate((h) => {
    Object.defineProperty(document, 'hidden', { value: h, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  }, h);
  await setHidden(true);
  await sleep(500);
  const hiddenPaused = await page.evaluate(() => window.__game.st.paused);
  await setHidden(false);
  await sleep(500);
  const backRunning = await page.evaluate(() => !window.__game.st.paused);
  console.log(`탭 숨김 → 일시정지 ${hiddenPaused}, 돌아오면 이어 감 ${backRunning}`);

  // 6) 연결이 끊기면 같은 판에 다시 접속 (화면 자리는 그대로)
  const before = await page.evaluate(() => {
    const { st, cam } = window.__game;
    window.__t_cut = performance.now();
    window.__camBefore = [cam.x, cam.y];
    const n = st.units.size;
    window.__game.net.ws.close();
    return n;
  });
  await page.waitForFunction('window.__game.st && window.__game.st.info.resumed && window.__game.st.units.size > 0', { timeout: 20000, polling: 50 });
  const back = await page.evaluate(() => ({ ms: performance.now() - window.__t_cut, n: window.__game.st.units.size,
    cam: Math.hypot(window.__game.cam.x - window.__camBefore[0], window.__game.cam.y - window.__camBefore[1]) }));
  await sleep(1500);
  const running = await page.evaluate(() => !window.__game.st.paused);
  console.log(`끊김 → 다시 접속 ${back.ms.toFixed(0)} ms, 병사 ${before} → ${back.n}, 화면 이동 ${back.cam.toFixed(1)}칸, 진행 중 ${running}`);
  await browser.close();
} finally {
  srv.kill();
}
