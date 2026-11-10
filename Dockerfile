FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -r -u 10001 appuser
COPY app ./app
RUN mkdir /srv/data && chown -R appuser:appuser /srv/data
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=15s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=2)"
CMD ["uvicorn","app.api:app","--host","0.0.0.0","--port","8000","--workers","1","--proxy-headers"]
