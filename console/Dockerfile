# L'image de la console MEGGA (console.megga.ai) : Next.js en sortie autonome (output: "standalone"), servie par Node.
# Le conteneur du Worker megga-console (hebergement/) la construit depuis ce dossier ; la CI la construit et la démarre une
# fois (.github/workflows/console.yml, job image). Ni le serveur d'agents de l'essai ni l'atelier d'essai (agents/) n'y
# entrent (.dockerignore).
# Les images de base par leur empreinte, comme socle/Dockerfile : l'image ne dépend pas du jour où elle est construite.
# linux/amd64 : la plateforme des conteneurs de Cloudflare.

FROM --platform=linux/amd64 node:24.22.1-slim@sha256:be8204d4bd327363357f532187b752ff62759c31bedf98e9e18fc08c9cbd605c AS construction
WORKDIR /console
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM --platform=linux/amd64 node:24.22.1-slim@sha256:be8204d4bd327363357f532187b752ff62759c31bedf98e9e18fc08c9cbd605c

# Passé à la construction : le commit. /api/sante le rend ; le Worker le remplace au démarrage par l'étiquette du déploiement.
ARG CONSOLE_REVISION=inconnue
LABEL org.opencontainers.image.title="megga-console" \
      org.opencontainers.image.revision="${CONSOLE_REVISION}"

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    COPILOTKIT_TELEMETRY_DISABLED=true \
    CONSOLE_REVISION=${CONSOLE_REVISION} \
    PORT=3000 \
    HOSTNAME=0.0.0.0

WORKDIR /console
COPY --from=construction /console/.next/standalone ./
COPY --from=construction /console/.next/static ./.next/static
# En ligne, la base est Postgres (CONSOLE_BASE_URL). Sans elle, la console écrit son fichier SQLite ici : le seul dossier où
# l'utilisateur sans droits peut écrire (un essai local de l'image, la CI).
RUN mkdir .donnees && chown node:node .donnees
USER node

EXPOSE 3000
CMD ["node", "server.js"]
