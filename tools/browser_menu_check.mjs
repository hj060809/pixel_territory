// 브라우저 메뉴 흐름 확인 (화면 없는 Chrome으로 사람처럼 조작): 웹을 빌드해 둔 상태에서
//   node tools/browser_menu_check.mjs <스크린샷 폴더>
// 로비 → 게임 방법 → 설정 → 지도 만들기(열도) → 무작위 배치 미리보기 → 다시 무작위 → 색 바꾸기 → 게임 시작(미리보기 배치 그대로인지)
// → F10 로비 → 설정(만든 지도가 남았는지) → 지도에서 고르기(물 → 거절, 땅 → 정함) → 게임(고른 자리인지) → F6 새 지도 → F10.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(path.dirname(fileURLToPath(import.meta.url)), '../web/package.json'));
const puppeteer = require('puppeteer-core');
const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8775;
const OUT = process.argv[2] ?? '.';
const CHROME = process.env.CHROME ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let fails = 0;
const check = (name, ok, extra = '') => { console.log(`  [${ok ? '통과' : '실패'}] ${name}${extra ? ' — ' + extra : ''}`); if (!ok) fails++; };

const srv = spawn('python', ['-m', 'server', '--port', String(PORT)], { cwd: WEB, stdio: 'ignore' });
try {
  for (let i = 0; i < 100; i++) { try { await fetch(`http://127.0.0.1:${PORT}/api/maps`); break; } catch { await sleep(300); } }
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: true,
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--window-size=1280,800'], defaultViewport: { width: 1280, height: 800 } });
  const page = await browser.newPage();
  page.on('pageerror', (e) => { console.log('페이지 오류:', e.message); fails++; });
  page.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('404') && !m.text().includes('422')) console.log('브라우저 오류:', m.text()); });
  const shot = (name) => page.screenshot({ path: path.join(OUT, name) });
  const click = async (text, nth = 0) => {                 // 보이는 버튼 중 글자가 같은 것 (nth번째)
    const ok = await page.evaluate((text, nth) => {
      const b = [...document.querySelectorAll('.menu button')].filter((x) => x.textContent === text && x.offsetParent !== null)[nth];
      if (!b) return false;
      b.scrollIntoView();
      const r = b.getBoundingClientRect();
      window.__clickAt = [r.left + r.width / 2, r.top + r.height / 2];
      return true;
    }, text, nth);
    if (!ok) throw new Error(`버튼 없음: ${text}`);
    const [x, y] = await page.evaluate(() => window.__clickAt);
    await page.mouse.click(x, y);
  };
  const app = (expr) => page.evaluate(`(() => { const a = window.__app.debug; return ${expr}; })()`);

  // 1) 로비
  let t0 = Date.now();
  await page.goto(`http://127.0.0.1:${PORT}/`);
  await page.waitForFunction('window.__app && window.__app.art.ready', { timeout: 60000, polling: 100 });
  check('로비 배경 받음', true, `${Date.now() - t0} ms`);
  await sleep(1200);
  await shot('menu_lobby.png');
  await click('게임 방법');
  await sleep(200);
  check('게임 방법 창', await page.evaluate(() => !!document.querySelector('.howto')));
  await shot('menu_howto.png');
  await page.keyboard.press('Escape');
  check('Esc로 닫힘', await page.evaluate(() => !document.querySelector('.howto')));

  // 2) 설정 → 열도 지도
  await click('게임 시작');
  await page.waitForFunction('window.__app.debug.setup && document.querySelector(".setup")', { timeout: 10000 });
  await sleep(300);
  await shot('menu_setup_empty.png');
  await click('열도');
  await page.click('.setup .field');
  await page.keyboard.down('Control'); await page.keyboard.press('a'); await page.keyboard.up('Control');
  await page.keyboard.type('42');
  await page.keyboard.press('Enter');
  await click('지도 만들기');
  await page.waitForFunction('(() => { const s = window.__app.debug.setup; return s.mapReady && s.layout; })()', { timeout: 60000, polling: 100 });
  const lay1 = await app('a.setup.layout');
  check('지도 만들기 → 무작위 배치 미리보기', lay1.starts.length === 5, `거점 ${JSON.stringify(lay1.starts)}`);
  await sleep(400);
  await shot('menu_setup_preview.png');
  await click('무작위', 1);                                 // 시드 옆 '무작위'가 아니라 시작 자리 '무작위'
  await page.waitForFunction((k) => { const s = window.__app.debug.setup; return s.layout && JSON.stringify(s.layout.starts) !== k; },
    { timeout: 10000 }, JSON.stringify(lay1.starts));
  check('무작위 다시 → 새 배치', true);
  await page.evaluate(() => document.querySelectorAll('.setup .swatch')[3].click());
  await page.waitForFunction('(() => { const s = window.__app.debug.setup; return s.layout && s.layout.colors[0] === 3; })()', { timeout: 10000 });
  await click('+');
  await page.waitForFunction('(() => { const s = window.__app.debug.setup; return s.layout && s.layout.starts.length === 6; })()', { timeout: 10000 });
  const lay2 = await app('a.setup.layout');
  check('색 청록 + AI 5 → 배치 다시', lay2.colors[0] === 3 && lay2.starts.length === 6, `색 ${JSON.stringify(lay2.colors)}`);
  await sleep(300);
  await shot('menu_setup_layout.png');

  // 3) 게임 시작 → 미리보기 배치 그대로인지
  t0 = Date.now();
  await click('게임 시작');
  await page.waitForFunction('window.__game && window.__game.st && window.__game.st.builds.size > 0', { timeout: 120000, polling: 100 });
  const opened = Date.now() - t0;
  const g1 = await page.evaluate(() => {
    const { st, key } = window.__game;
    const halls = [...st.builds.values()].filter((b) => b.kind === st.info.rules.kinds.HALL).map((b) => [b.own, b.y, b.x]);
    return { key, halls, colors: st.info.nations.map((n) => n.color), n: st.info.nations.length };
  });
  const lobbyColors = await page.evaluate(() => window.__app.art.info.colors.map((c) => c[1]));
  const sameColors = g1.colors.every((c, i) => JSON.stringify(c) === JSON.stringify(lobbyColors[lay2.colors[i]]));
  const sameStarts = g1.halls.every(([own, y, x]) => Math.hypot(y - lay2.starts[own][0], x - lay2.starts[own][1]) < 1.5);
  check('게임 = 미리보기 배치 (거점 자리, 나라 색)', g1.key === 'island_arc-512-42' && g1.n === 6 && sameColors && sameStarts,
    `판 열림 ${(opened / 1000).toFixed(1)}초, 지도 ${g1.key}`);
  await sleep(2000);
  await shot('menu_game.png');

  // 4) F10 → 로비, 설정에 만든 지도가 남았는지
  await page.keyboard.press('F10');
  await sleep(300);
  check('F10 → 로비 (게임 화면 정리)', await page.evaluate(() =>
    window.__app.debug.screen === 'lobby' && !document.querySelector('canvas#view') && !document.querySelector('.hud') && !window.__game));
  await click('게임 시작');
  await sleep(300);
  check('설정에 만든 지도가 남음', await app('a.setup.mapReady'));

  // 5) 지도에서 고르기: 물(왼쪽 위 구석) → 거절, 땅(방금 배치의 내 자리) → 정함
  await click('지도에서 고르기');
  const box = await page.evaluate(() => { const r = document.querySelector('.preview').getBoundingClientRect(); return [r.left, r.top, r.width]; });
  await page.mouse.click(box[0] + 3, box[1] + 3);
  await sleep(500);
  const refused = await page.evaluate(() => document.querySelector('.setup-msg').textContent);
  check('물 / 가장자리 클릭 → 거절', (await app('a.settings.spot')) === null && refused.length > 0, refused);
  const want = lay2.starts[0];
  await page.mouse.click(box[0] + ((want[1] + 0.5) / 512) * box[2], box[1] + ((want[0] + 0.5) / 512) * box[2]);
  await page.waitForFunction('window.__app.debug.settings.spot !== null', { timeout: 10000 });
  const spot = await app('a.settings.spot');
  check('땅 클릭 → 시작 자리 정함', Math.hypot(spot[0] - want[0], spot[1] - want[1]) < 3, JSON.stringify(spot));
  await shot('menu_setup_pick.png');
  await click('게임 시작');
  await page.waitForFunction('window.__game && window.__game.st && window.__game.st.builds.size > 0', { timeout: 120000, polling: 100 });
  const myHall = await page.evaluate(() => { const { st } = window.__game; const b = [...st.builds.values()].find((v) => v.own === 0); return [b.y, b.x]; });
  check('게임 = 고른 자리', Math.hypot(myHall[0] - spot[0], myHall[1] - spot[1]) < 1.5, JSON.stringify(myHall));

  // 6) F6 새 지도 (시드 + 1, 서버가 만든다) → F10
  if (process.env.SKIP_F6 !== '1') {
    t0 = Date.now();
    await page.keyboard.press('F6');
    const next = g1.key.replace(/-(\d+)$/, (_, n) => `-${Number(n) + 1}`);
    await page.waitForFunction((k) => window.__game && window.__game.key === k && window.__game.st && window.__game.st.builds.size > 0,
      { timeout: 170000, polling: 200 }, next);
    check('F6 → 새 지도로 판', true, `${((Date.now() - t0) / 1000).toFixed(1)}초 (지도 만들기 포함)`);
    await sleep(1500);
    await shot('menu_f6.png');
  }
  await page.keyboard.press('F10');
  await sleep(300);
  check('다시 로비', await app('a.screen === "lobby"'));
  await browser.close();
} finally {
  srv.kill();
}
console.log(fails ? `실패 ${fails}` : '모두 통과');
process.exit(fails ? 1 : 0);
