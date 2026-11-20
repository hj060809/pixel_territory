"""Pixel Territory 서버: 게임 시뮬레이션을 돌리고(판마다 스레드 하나), 브라우저와 WebSocket으로 주고받는다.

- config: 설정 (지도 크기 상한 등, 환경 변수 TS_*)
- maps: 지도 저장소 (데모 지도, 직접 입력한 시드는 별도 프로세스에서 만들고 굽기)
- protocol: 상태 메시지 형식 (이진, 바뀐 것만)
- session: 판 하나 (걸음, 명령, 보내기)
- app: HTTP + WebSocket (FastAPI). 실행: python -m server
"""
