FROM python:3.12-slim-bookworm

# ping + `ip neigh` isi WiFi ke devices dekhne ke liye.
# wireless-tools / iw Linux host pe SSID padhte hain.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        iproute2 \
        iputils-ping \
        iw \
        libcap2-bin \
        wireless-tools \
    && rm -rf /var/lib/apt/lists/* \
    && setcap cap_net_raw+ep "$(command -v ping)" \
    && groupadd --system --gid 1000 scanner \
    && useradd --system --uid 1000 --gid scanner --home-dir /app --shell /usr/sbin/nologin scanner \
    && mkdir -p /app /data /seed \
    && chown scanner:scanner /data

WORKDIR /app

COPY wifi_scanner.py wifi_web.py entrypoint.sh /app/
RUN chmod 755 /app/entrypoint.sh \
    && chown -R scanner:scanner /app /seed

ENV PYTHONUNBUFFERED=1 \
    WIFI_DATA_DIR=/data \
    WIFI_HOST=0.0.0.0 \
    PORT=8765 \
    WIFI_INTERVAL=20

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8765')+'/api/health', timeout=3)"

ENTRYPOINT ["/app/entrypoint.sh"]
