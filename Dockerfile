# Pixel Territory: 게임 서버 + 웹 화면을 한 컨테이너에서 (포트 3000).
# 웹 화면, API(/api), 게임 웹소켓(/ws) 모두 3000번으로 나간다. 앞단 nginx는 3000번으로 넘겨 주기만 하면 된다
# (웹소켓 Upgrade 헤더를 넘겨야 한다: deploy/nginx.conf.example).
#
#   docker compose up -d --build
#
# 판 정보는 서버 메모리에 있으므로 컨테이너(프로세스)는 하나만 띄운다.

# ---- 1. 웹 화면 빌드 (Vite + TypeScript)
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- 2. 게임 서버 (FastAPI + numba)
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TS_WEB_DIR=/app/web/dist \
    TS_DATA_DIR=/data/app \
    TS_CACHE_DIR=/data/cache \
    NUMBA_CACHE_DIR=/data/numba
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ engine/
COPY sim/ sim/
COPY server/ server/
COPY assets/ assets/
# 데모 지도: 구워 둔 assets/maps가 없으면 (git으로 받았으면 없다) 빌드할 때 굽는다 (몇 분 걸린다)
RUN test -f assets/maps/maps.json || python -m engine.bake --cache-dir /tmp/bake-cache && rm -rf /tmp/bake-cache

COPY --from=web /web/dist web/dist

# 직접 만든 지도, 로비 배경, 지형 캐시, numba 컴파일 캐시 (다시 켜도 남게 볼륨으로)
VOLUME /data
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3000/api/maps', timeout=4)" || exit 1
CMD ["python", "-m", "server", "--host", "0.0.0.0", "--port", "3000"]
