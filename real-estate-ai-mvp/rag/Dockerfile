FROM python:3.12-slim

WORKDIR /srv
# INSTALL_RERANKER=false builds a smaller image without torch; set RERANKER=none or cohere then.
ARG INSTALL_RERANKER=true
COPY requirements.txt requirements-rerank.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
 && if [ "$INSTALL_RERANKER" = "true" ]; then pip install --no-cache-dir -r requirements-rerank.txt; fi

COPY rag_service rag_service

RUN useradd --system --uid 10001 rag && mkdir -p /data/sources /models && chown -R rag /data /models
USER rag
ENV PYTHONUNBUFFERED=1 RAG_STORAGE_PATH=/data/sources HF_HOME=/models
EXPOSE 8090
ENTRYPOINT ["python", "-m", "rag_service"]
CMD ["api"]
