FROM python:3.6-alpine

RUN apk --update add --virtual .build-deps build-base libffi-dev openssl-dev linux-headers \
    && rm -rf /var/cache/apk/*

RUN pip3 install -U pip setuptools

ADD requirements /opt/app/requirements
WORKDIR /opt/app
RUN pip3 install -r requirements/dev.txt \
    && apk del .build-deps
