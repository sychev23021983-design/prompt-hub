FROM python:3.12-slim

WORKDIR /app

COPY app/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Код (app/, templates/, static/) монтируется как volume в docker-compose.yml,
# а не копируется сюда — поэтому `git pull` + `docker compose up -d --force-recreate`
# всегда подхватывает свежий код БЕЗ пересборки образа. Пересборка (docker compose build)
# нужна только если менялся requirements.txt.

EXPOSE 8030

CMD ["gunicorn", "--bind", "0.0.0.0:8030", "--workers", "2", "--chdir", "/app", "server:app"]
