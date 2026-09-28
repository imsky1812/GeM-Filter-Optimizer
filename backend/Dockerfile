# API-only backend. The frontend is deployed separately (Vercel) and calls
# this service over HTTPS; set ALLOWED_ORIGINS to that site's origin.
#
# The Playwright image ships Chromium and the system libraries it needs, at
# the version matching requirements.txt -- GeM's firewall only lets a real
# browser through, so the crawler can't run without it.
FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

ENV PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

# Hosts inject PORT; one worker, because the browser, the page pool and the
# result caches live in this process and aren't shared across workers.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
