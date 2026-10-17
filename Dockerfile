FROM python:3.12-slim
LABEL org.opencontainers.image.source="https://github.com/kermess14/bulle" \
      org.opencontainers.image.description="Bulle — lecteur de BD maison (CBZ/CBR/PDF), navigation par dossiers"

# unar : ouverture des CBR / RAR (et 7z) ; 7z et bsdtar (libarchive) en secours si unar bute sur une archive. Le reste est en pur Python.
RUN apt-get update \
 && apt-get install -y --no-install-recommends unar p7zip-full libarchive-tools ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Pages en HEIC/HEIF et JPEG XL (facultatif : si ces modules ne s'installent pas sur une architecture, Bulle s'en passe)
RUN pip install --no-cache-dir pillow-heif pillow-jxl-plugin || echo "HEIC/JPEG XL non disponibles"
COPY bulle ./bulle

ENV LIBRARY_ROOT=/library \
    DATA_DIR=/data \
    PORT=2205 \
    PYTHONUNBUFFERED=1

EXPOSE 2205
VOLUME ["/data"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/stats' % os.environ.get('PORT', '2205'), timeout=4)" || exit 1

CMD ["python", "-m", "bulle.server"]
