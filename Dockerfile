FROM node:22-alpine AS dashboard-build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build

FROM python:3.12-alpine
RUN apk add --no-cache age
WORKDIR /app
COPY app ./app
COPY data ./data
COPY docs ./docs
COPY --from=dashboard-build /src/web/dist ./web/dist
RUN addgroup -S envshelf && adduser -S -G envshelf envshelf \
    && mkdir -p /var/lib/envshelf /workspace /keys \
    && chown -R envshelf:envshelf /app /var/lib/envshelf /workspace
USER envshelf
EXPOSE 8787
CMD ["python", "-m", "app.server"]
