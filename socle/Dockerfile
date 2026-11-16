# L'image unique des agents MEGGA : la même chez Cloudflare, en Suisse et chez le client.
# Publiée et signée par .github/workflows/publier.yml (docs/deploiement.md, « Publier une version »).
# Le service de fiche PDF (fiche/, pdf-lib) : ses dépendances, installées à part ; seuls Node et le service passent.
# Les images de base par leur empreinte : l'image signée ne dépend pas du jour où elle est construite.
FROM --platform=linux/amd64 node:22.11.0-slim@sha256:f035ba7ffee18f67200e2eb8018e0f13c954ec16338f264940f701997e3c12da AS fiche
WORKDIR /fiche
COPY fiche/package.json fiche/package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts
COPY fiche/src ./src
COPY fiche/modeles ./modeles

FROM --platform=linux/amd64 python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

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
COPY --from=fiche /usr/local/bin/node /usr/local/bin/node
COPY --from=fiche /fiche ./fiche
COPY pyproject.toml ./
COPY noyau ./noyau
COPY packs ./packs
COPY atelier ./atelier
COPY pilote ./pilote
# La clé publique cosign de MEGGA (scripts/cle_signature.sh), quand elle existe : le pilote vérifie avec elle
# chaque image qu'on lui propose (le Dockerfile, toujours là, évite l'échec de COPY sans la clé).
COPY socle/Dockerfile socle/modele.py socle/cosign.pu[b] ./socle/
# Le modèle de recherche de la base de connaissances (noyau/connaissances.py) : révision et empreinte figées.
RUN python socle/modele.py /opt/megga/modele
RUN if [ -f socle/cosign.pub ]; then cp socle/cosign.pub noyau/cosign.pub; fi \
    && pip install --no-cache-dir . && useradd --create-home --uid 10001 agent \
    && mkdir /sauvegardes && chown agent /sauvegardes
USER agent

EXPOSE 8080
CMD ["python", "-m", "noyau"]
