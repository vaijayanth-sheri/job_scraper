FROM node:22-bookworm-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html ./
COPY frontend/src ./src
RUN npm install && npm run build

FROM python:3.11-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY config.yaml search_jobs.py ./
COPY job_search ./job_search
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN mkdir -p output runtime/searches

EXPOSE 8000

CMD ["uvicorn", "job_search.api:app", "--host", "0.0.0.0", "--port", "8000"]
