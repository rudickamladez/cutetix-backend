FROM tiangolo/uvicorn-gunicorn-fastapi:python3.11

ARG USER_ID
ARG GROUP_ID
RUN echo "Used user id: ${USER_ID}\nUsed group id: ${GROUP_ID}"

# Update system
RUN apt update && apt upgrade -y && apt autoremove -y

# Upgrade python package manager
RUN pip install --upgrade pip

# Change ID of www-data user and group to ID from ENV
RUN set -x && if [ ${USER_ID:-0} -ne 0 ] && [ ${GROUP_ID:-0} -ne 0 ]; then \
    if getent passwd www-data ; then echo "Delete user www-data" && userdel -f www-data;fi &&\
    if getent group www-data ; then echo "Delete group www-data" && groupdel www-data;fi &&\
    echo "Add new group www-data" && groupadd -g ${GROUP_ID} www-data &&\
    echo "Add new user www-data" && useradd -l -u ${USER_ID} -g www-data www-data &&\
    echo "Change ownership of workdir" && mkdir -p /var/www && chown --changes --no-dereference --recursive www-data:www-data /var/www &&\
    echo "Change ownership of homedir" && mkdir -p /home/www-data && chown --changes --no-dereference --recursive www-data:www-data /home/www-data &&\
    echo "ahoj";fi

# Change user
USER www-data:www-data

# Change working directory
WORKDIR /var/www

# Copy folders and files
COPY ./.git ./.git
COPY ./app ./app
COPY ./requirements.txt ./requirements.txt

# Install requirements
RUN pip install --no-cache-dir --upgrade -r ./requirements.txt

# Expose port
EXPOSE 80

# Command on start of container
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "80"]
