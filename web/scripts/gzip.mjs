// 빌드 뒤: dist/의 JS·CSS·HTML 옆에 미리 압축한 .gz를 만든다 (서버가 gzip을 받는 브라우저에게 그것을 보낸다).
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const root = new URL('../dist/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
let before = 0, after = 0;
const walk = (dir) => {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|css|html|json|svg)$/.test(name)) {
      const raw = readFileSync(p), gz = gzipSync(raw, { level: 9 });
      writeFileSync(p + '.gz', gz);
      before += raw.length; after += gz.length;
    }
  }
};
walk(root);
console.log(`gzip: ${(before / 1024).toFixed(0)} KB → ${(after / 1024).toFixed(0)} KB`);
