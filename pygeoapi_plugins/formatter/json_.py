# =================================================================
#
# Authors: Benjamin Webb <bwebb@lincolninst.edu>
#
# Copyright (c) 2026 Lincoln Institute of Land Policy
#
# Permission is hereby granted, free of charge, to any person
# obtaining a copy of this software and associated documentation
# files (the "Software"), to deal in the Software without
# restriction, including without limitation the rights to use,
# copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following
# conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
# OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# =================================================================
"""JSON capabilities
Returns content as JSON without HTML-escaping the serialized output
"""

import logging
import re
from typing import overload

import orjson
from pygeoapi.formatter.base import (
    BaseFormatter,
    FormatterSerializationError,
)
from pygeoapi.util import json_serial

LOGGER = logging.getLogger(__name__)

# Leading "type" member of a GeoJSON geometry, as written by ST_AsGeoJSON
_GEOMETRY_TYPE = re.compile(rb'\s*\{\s*"type"\s*:\s*"(\w+)"')


class JSONFormatter(BaseFormatter):
    """JSON formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.json_.JSONFormatter`
        """

        geom = formatter_def.get('geom', False)

        super().__init__({'name': 'json', 'geom': geom})
        self.mimetype = 'application/geo+json'
        self.f = 'json'
        self.extension = 'json'

    # pygeoapi sends bytes content as-is, though BaseFormatter declares str
    def write(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, options: dict | None = None, data: dict | None = None
    ) -> bytes:
        """
        Generate data in JSON format

        Unlike `pygeoapi.util.to_json`, `<` and `>` are left as-is
        rather than being cast to `&lt;` and `&gt;`.

        :param options: JSON formatting options
        :param data: dict of GeoJSON data

        :returns: bytes representation of format
        """

        if data is None:
            LOGGER.warning('No data to write to JSON')
            return b''

        options = options or {}
        option = orjson.OPT_INDENT_2 if options.get('pretty') else None

        if data.get('type') == 'Feature':
            data = _embed_geometry(data)
        elif 'features' in data:
            data = {
                **data,
                'features': [_embed_geometry(f) for f in data['features']],
            }

        try:
            return orjson.dumps(data, default=json_serial, option=option)
        except orjson.JSONEncodeError as err:
            LOGGER.error(err)
            raise FormatterSerializationError(
                'Error writing JSON output'
            ) from err

    def __repr__(self):
        return f'<JSONFormatter> {self.name}'


class GeoJSONGeometry(dict):
    """
    A GeoJSON geometry that keeps the JSON it came from in `raw`, and only
    parses it the first time its contents are read.

    Until then the dict holds just `type`, so a geometry that `JSONFormatter`
    writes out from `raw` never creates its coordinate lists. Every read
    method parses first, so pygeoapi (HTML, JSON-LD, other formatters) sees
    an ordinary dict. `raw` is not updated if the dict is changed.

    `orjson.dumps` reads dict storage directly, so it must be given `raw`
    (as `JSONFormatter` does) rather than an unread `GeoJSONGeometry`.

    `GeoJSONGeometry(None)` returns `None`, for features without geometry.
    """

    __slots__ = ('_loaded', 'raw')

    @overload
    def __new__(cls, raw: None) -> None: ...

    @overload
    def __new__(cls, raw: str | bytes) -> 'GeoJSONGeometry': ...

    def __new__(cls, raw: str | bytes | None) -> 'GeoJSONGeometry | None':
        if raw is None:
            return None
        return super().__new__(cls)

    def __init__(self, raw: str | bytes):
        self.raw = raw
        match = _GEOMETRY_TYPE.match(
            raw.encode() if isinstance(raw, str) else raw
        )
        if match:
            # Non-empty, so json's C encoder calls items() rather than
            # writing {} for an empty dict
            super().__init__(type=match.group(1).decode())
            self._loaded = False
        else:
            super().__init__(orjson.loads(raw))
            self._loaded = True

    def _load(self):
        """Parse `raw` into the dict, once"""
        if not self._loaded:
            self._loaded = True
            dict.update(self, orjson.loads(self.raw))

    def __reduce__(self):
        self._load()
        return (_rebuild_geometry, (self.raw, dict(self)))

    __hash__ = None


def _parse_first(name: str):
    """Wrap a dict method so it parses the geometry before running"""
    method = getattr(dict, name)

    def wrapper(self, *args, **kwargs):
        self._load()
        return method(self, *args, **kwargs)

    wrapper.__name__ = name
    wrapper.__doc__ = method.__doc__
    return wrapper


for _name in (
    '__getitem__',
    '__setitem__',
    '__delitem__',
    '__iter__',
    '__len__',
    '__contains__',
    '__eq__',
    '__ne__',
    '__repr__',
    '__or__',
    '__ror__',
    '__ior__',
    '__reversed__',
    'get',
    'keys',
    'values',
    'items',
    'copy',
    'pop',
    'popitem',
    'setdefault',
    'update',
    'clear',
):
    setattr(GeoJSONGeometry, _name, _parse_first(_name))
del _name


def _rebuild_geometry(raw: str | bytes, data: dict) -> GeoJSONGeometry:
    """Unpickle a `GeoJSONGeometry` with its (possibly changed) contents"""
    geometry = GeoJSONGeometry(raw)
    geometry._loaded = True
    dict.clear(geometry)
    dict.update(geometry, data)
    return geometry


# Feature members that can hold a geometry: GeoJSON geometry, JSON-FG place
_GEOMETRY_KEYS = ('geometry', 'place')


def _embed_geometry(feature: dict) -> dict:
    """
    Embed pre-serialized geometries (e.g. from ST_AsGeoJSON) verbatim,
    rather than re-encoding them

    :param feature: `dict` of GeoJSON or JSON-FG feature

    :returns: `dict` of feature
    """

    embedded = {}
    for key in _GEOMETRY_KEYS:
        geometry = feature.get(key)
        if isinstance(geometry, GeoJSONGeometry):
            geometry = geometry.raw
        if isinstance(geometry, (str, bytes)):
            embedded[key] = orjson.Fragment(geometry)

    return {**feature, **embedded} if embedded else feature
