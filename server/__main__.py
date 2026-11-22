"""서버 실행: python -m server [--host 0.0.0.0] [--port 8000] [--dev]
--dev: 개발용 명령을 연다 (게임 중 ` 키 콘솔: 자원 받기). 배포 서버에서는 켜지 않는다."""
import argparse
import os

import uvicorn


def main():
    p = argparse.ArgumentParser(description='Pixel Territory 서버')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8000)
    p.add_argument('--dev', action='store_true', help='개발용 명령 (자원 받기 등)')
    args = p.parse_args()
    if args.dev:
        os.environ['TS_DEV'] = '1'                     # 설정(ServerConfig)이 읽는다
    # ws_ping: 끊긴 연결을 알아차리게. 압축은 끈다 (메시지가 작고, 압축 시간만큼 늦어진다)
    uvicorn.run('server.app:app', host=args.host, port=args.port, ws='websockets', ws_per_message_deflate=False,
                log_level='info')


if __name__ == '__main__':
    main()
