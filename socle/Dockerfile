# L'image unique des agents MEGGA : la même chez Cloudflare, en Suisse et chez le client.
FROM --platform=linux/amd64 python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGNO_TELEMETRY=false \
    PORT=8080

WORKDIR /app
COPY pyproject.toml ./
COPY noyau ./noyau
COPY packs ./packs
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 agent
USER agent

EXPOSE 8080
CMD ["python", "-m", "noyau"]
