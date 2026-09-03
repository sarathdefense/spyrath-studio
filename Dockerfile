FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e ".[studio]"
RUN useradd --create-home --uid 10001 spyrath && mkdir -p /data && chown -R spyrath:spyrath /data /app
USER spyrath
ENV SPYRATH_PROJECTS_ROOT=/data/projects SPYRATH_METADATA_DB=/data/studio.db
EXPOSE 8000
CMD ["uvicorn","spyrath.studio.app:app","--host","0.0.0.0","--port","8000"]
