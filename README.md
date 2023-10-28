# cutetix

Cute Tickets Information System

## Production

### Instalation

Copy Docker Compose sample configuration file
`cp docker-compose.sample.yml docker-compose.yml`

Edit Docker Compose configuration file
`vim docker-compose.yml`

Copy Enviroment sample file
`cp .env.sample .env`

Get Local User and Group ID for user in container
`cat /etc/passwd | grep YOUR_LOCAL_USER`
`cat /etc/group | grep YOUR_LOCAL_GROUP`

Edit Enviroment sample file
`vim .env`

### Running

Run Docker Compose with see logs (Close with Ctrl+C)
`docker compose up -d && docker compose logs -f`
