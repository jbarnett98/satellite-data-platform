FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app/pipeline

ENV PYTHONPATH=/app

CMD ["python", "-m", "pipeline.scripts.run_pipeline"]