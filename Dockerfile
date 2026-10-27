# Controva app image: the API + dashboard on port 8080.
# Started together with Postgres by docker-compose.yml — see HOW_TO_RUN.md.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    LEADGEN_HOME=/data

RUN pip install --no-cache-dir "psycopg2-binary>=2.9" "dnspython>=2.6"

WORKDIR /app
COPY server/ /app/server/
RUN chmod +x /app/server/docker-entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/app/server/docker-entrypoint.sh"]
