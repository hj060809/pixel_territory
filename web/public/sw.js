// 앱 설치(홈 화면에 추가) 조건을 맞추기 위한 최소 서비스 워커: 아무것도 저장하지 않고, 요청은 그대로 네트워크로 간다.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
