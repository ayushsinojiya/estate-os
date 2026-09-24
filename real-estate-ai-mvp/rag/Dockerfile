FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DEFAULT_TIMEOUT=30 PIP_RETRIES=2 HF_HOME=/models
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-guj \
    && rm -rf /var/lib/apt/lists/*
RUN pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu
COPY pyproject.toml constraints.txt ./
COPY rag_ingestion ./rag_ingestion
RUN pip install -c constraints.txt '.[test]'
RUN useradd --uid 10001 --create-home ingestion && mkdir -p /data /models \
    && chown -R ingestion:ingestion /data /models /app
USER ingestion
EXPOSE 8090
ENTRYPOINT ["estateos-rag"]
CMD ["api", "--host", "0.0.0.0"]
