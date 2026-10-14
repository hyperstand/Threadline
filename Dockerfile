FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e . \
    && pip install --no-cache-dir uvicorn

ENV THREADLINE_ENV=dev \
    DATABASE_URL=sqlite:///./data/threadline.db

EXPOSE 8000
VOLUME ["/app/data"]

CMD ["uvicorn", "threadline.main:app", "--host", "0.0.0.0", "--port", "8000"]
