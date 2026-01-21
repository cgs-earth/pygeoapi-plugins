FROM geopython/pygeoapi:latest

ADD ./docker/pygeoapi.config.yml /pygeoapi/local.config.yml

ADD . /pygeoapi_plugins

RUN /venv/bin/python3 -m pip install -e /pygeoapi_plugins

ENTRYPOINT [ "/entrypoint.sh" ]
