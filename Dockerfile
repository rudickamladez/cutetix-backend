FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

ARG USER_ID=1000
ARG GROUP_ID=1000
RUN echo "Used user id: ${USER_ID}\nUsed group id: ${GROUP_ID}"

# Update system
RUN apt update && apt upgrade -y && apt autoremove -y

# Upgrade python package manager
RUN pip install --upgrade pip

# Change working directory
WORKDIR /var/www

# Copy folders and files – It's important to copy files before changing their ownership
COPY ./.git ./.git
COPY ./app ./app
COPY ./requirements.txt ./requirements.txt
COPY ./logging.json ./logging.json
COPY ./alembic ./alembic
COPY ./alembic.ini ./alembic.ini
COPY ./entrypoint.sh ./entrypoint.sh

# Change ID of www-data user and group to ID from ENV
RUN if [ ${USER_ID:-0} -ne 0 ] && [ ${GROUP_ID:-0} -ne 0 ]; then \
  if getent passwd www-data ; then echo "Delete user www-data" && userdel -f www-data;fi &&\
  if getent group www-data ; then echo "Delete group www-data" && groupdel www-data;fi &&\
  echo "Add new group www-data" && groupadd -g ${GROUP_ID} www-data &&\
  echo "Add new user www-data" && useradd -l -u ${USER_ID} -g www-data www-data &&\
  echo "Change ownership of workdir" && mkdir -p /var/www && chown --changes --no-dereference --recursive www-data:www-data /var/www &&\
  echo "Change ownership of homedir" && mkdir -p /home/www-data && chown --changes --no-dereference --recursive www-data:www-data /home/www-data \
  ;fi

# Change user
USER www-data:www-data

# Install requirements
RUN pip install --no-cache-dir --upgrade -r ./requirements.txt

# Expose port
EXPOSE 80

# Check container status when running
HEALTHCHECK --interval=10s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:${PORT}/health-check || exit 1

CMD ./entrypoint.sh
