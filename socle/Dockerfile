# L'image unique des agents MEGGA : la même chez Cloudflare, en Suisse et chez le client.
# Publiée et signée par .github/workflows/publier.yml (docs/deploiement.md, « Publier une version »).
FROM --platform=linux/amd64 python:3.12-slim

# Passés à la construction : la version (celle de pyproject.toml) et le commit.
ARG MEGGA_VERSION=dev
ARG MEGGA_REVISION=inconnue
LABEL org.opencontainers.image.title="megga-agents" \
      org.opencontainers.image.version="${MEGGA_VERSION}" \
      org.opencontainers.image.revision="${MEGGA_REVISION}" \
      org.opencontainers.image.source="https://github.com/megga/megga-agents"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AGNO_TELEMETRY=false \
    MEGGA_REVISION=${MEGGA_REVISION} \
    PORT=8080

WORKDIR /app
COPY pyproject.toml ./
COPY noyau ./noyau
COPY packs ./packs
COPY atelier ./atelier
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 agent
USER agent

EXPOSE 8080
CMD ["python", "-m", "noyau"]
