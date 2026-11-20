// 브라우저 확인 (화면 없이 설치된 Chrome으로): 웹을 빌드해 둔 상태에서
//   node tools/browser_check.mjs parity            기준 그림 비교 (데모 지도 전부)
//   node tools/browser_check.mjs shot <파일.png>   뷰어 화면 스크린샷 (?map= 등은 SHOT_QUERY 환경 변수)
// 파이썬 서버를 따로 띄우고 끝나면 끈다.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(path.join(path.dirname(fileURLToPath(import.meta.url)), '../web/package.json'));
const puppeteer = require('puppeteer-core');
const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const PORT = 8771;
const CHROME = process.env.CHROME ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const [mode, arg] = process.argv.slice(2);

const srv = spawn('python', ['-m', 'server', '--port', String(PORT)], { cwd: WEB, stdio: 'ignore' });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
try {
  for (let i = 0; i < 100; i++) { try { await fetch(`http://127.0.0.1:${PORT}/api/maps`); break; } catch { await sleep(300); } }
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: true,
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--window-size=1280,800', '--no-first-run'],
    defaultViewport: { width: 1280, height: 800 },
  });
  const page = await browser.newPage();
  page.on('console', (m) => { if (m.type() === 'error') console.log('브라우저 오류:', m.text()); });
  page.on('pageerror', (e) => console.log('페이지 오류:', e.message));
  if (mode === 'parity') {
    await page.goto(`http://127.0.0.1:${PORT}/parity.html${arg ? '?maps=' + arg : ''}`);
    await page.waitForFunction('window.__parity && window.__parity.done', { timeout: 600000, polling: 500 });
    const res = await page.evaluate('window.__parity');
    if (res.error) console.log('오류:', res.error);
    let worst = 1;
    for (const r of res.results) {
      const match = 1 - r.diff / r.total;
      worst = Math.min(worst, match);
      console.log(`${r.map.padEnd(11)} ${r.ref.padEnd(22)} 다른 칸 ${String(r.diff).padStart(5)} / ${r.total} (최대 차이 ${r.maxd}), 그리기 ${r.ms.toFixed(0)} ms`);
    }
    console.log(`최저 일치율 ${(worst * 100).toFixed(4)}% (${res.results.length}장면)`);
  } else if (mode === 'shot') {
    await page.goto(`http://127.0.0.1:${PORT}/${process.env.SHOT_QUERY ?? ''}`);
    await sleep(Number(process.env.SHOT_WAIT ?? 8000));
    if (process.env.SHOT_EVAL) { await page.evaluate(process.env.SHOT_EVAL); await sleep(1500); }   // 예: 확대
    await page.screenshot({ path: arg });
    console.log('저장', arg);
  }
  await browser.close();
} finally {
  srv.kill();
}
