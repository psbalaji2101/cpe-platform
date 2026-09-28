FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home cpe && mkdir /data && chown cpe:cpe /data
COPY --chown=cpe:cpe . .
USER cpe
EXPOSE 8000
CMD ["uvicorn", "cpe.api:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
