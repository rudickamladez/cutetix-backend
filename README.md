# CuteTix Backend

Cute Tickets Information System

## ERD

Made in [Umbrello](https://uml.sourceforge.io/)

## Production

### Instalation

Copy Docker Compose sample configuration file \
`cp docker-compose.sample.yml docker-compose.yml`

Edit Docker Compose configuration file \
`vim docker-compose.yml`

Create folder for SQL Lite database \
`mkdir db`

### Running

Generate JWT keys:

```sh
# Secret key
openssl genrsa -out private.pem 2048

# Public key
openssl rsa -in private.pem -pubout -out public.pem
```

Run Docker Compose with logs printed (Close with Ctrl+C) \
`docker compose up -d && docker compose logs -f`
