FROM python:3.12-alpine
RUN apk add --no-cache age
WORKDIR /app
COPY app ./app
COPY web ./web
COPY data ./data
COPY docs ./docs
RUN addgroup -S envshelf && adduser -S -G envshelf envshelf && mkdir -p /var/lib/envshelf && chown -R envshelf:envshelf /app /var/lib/envshelf
USER envshelf
EXPOSE 8787
CMD ["python", "-m", "app.server"]
