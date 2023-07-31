FROM geopython/pygeoapi:latest

ADD ./docker/pygeoapi.config.yml /pygeoapi/local.config.yml

ADD . /pygeoapi_plugins

RUN pip3 install -e /pygeoapi_plugins

ENTRYPOINT [ "/entrypoint.sh" ]
