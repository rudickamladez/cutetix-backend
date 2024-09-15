ARG VERSION
FROM mariadb:${VERSION:-latest}

ARG VERSION
RUN echo "Used version: ${VERSION:-latest}\n"

ARG USER_ID
ARG GROUP_ID
RUN echo "Used user id: ${USER_ID}\n"
RUN echo "Used group id: ${GROUP_ID}\n"

#RUN if [ ${USER_ID:-0} -ne 0 ] && [ ${GROUP_ID:-0} -ne 0 ]; then \
#    userdel -f mysql &&\
#    if getent group mysql ; then groupdel mysql; fi &&\
#    groupadd -g ${GROUP_ID} mysql &&\
#    useradd -l -u ${USER_ID} -g mysql mysql &&\
#    install -d -m 0775 -o mysql -g mysql /home/mysql &&\
#    chown --changes --silent --no-dereference --recursive ${USER_ID}:${GROUP_ID} \
#        /home/mysql \
#        /var/lib/mysql \
#        /var/run/mysqld \
#;fi

RUN userdel -f mysql
RUN if getent group mysql ; then groupdel mysql; fi
RUN groupadd -g ${GROUP_ID} mysql
RUN useradd -l -u ${USER_ID} -g mysql mysql
RUN install -d -m 0775 -o mysql -g mysql /home/mysql
RUN chown --changes --silent --no-dereference --recursive ${USER_ID}:${GROUP_ID} /home/mysql /var/lib/mysql /var/run/mysqld
