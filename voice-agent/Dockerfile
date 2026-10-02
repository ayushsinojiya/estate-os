FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app app

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# One worker per container: the rate governor, degradation monitors, active calls, the outbound
# registry and the outbox are in-process state. Scale out only after moving that state to a
# shared store.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
