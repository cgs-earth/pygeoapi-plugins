# =================================================================
#
# Authors: Ben Webb <bwebb@lincolninst.edu>
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

import geopandas as gpd
import os
import tempfile
import zipfile
import io
import logging

from pygeoapi.formatter.base import BaseFormatter

LOGGER = logging.getLogger(__name__)


class ShapefileFormatter(BaseFormatter):
    """Shapefile formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.shape.ShapefileFormatter`
        """

        super().__init__({'name': 'SHP', 'attachment': True})

        self.mimetype = 'application/zip'
        self.f = 'shp'
        self.extension = 'zip'

    def write(self, options: dict = {}, data: dict = None) -> str:
        """
        Generate data in Zipped Shapefile format

        :param options: Shapefile formatting options
        :param data: dict of GeoJSON data

        :returns: string representation of format
        """
        dataset = options.get('dataset', 'data')

        gdf = gpd.GeoDataFrame.from_features(data['features'])

        # Create a temporary directory for shapefile components
        with tempfile.TemporaryDirectory() as tmpdir:
            shapefile_path = os.path.join(tmpdir, f'{dataset}.shp')
            gdf.to_file(shapefile_path)

            # Create a zip in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for filename in os.listdir(tmpdir):
                    full_path = os.path.join(tmpdir, filename)
                    zipf.write(full_path, arcname=filename)

            return zip_buffer.getvalue()

    def __repr__(self):
        return f'<ShapefileFormatter> {self.name}'


class BaseShapeFormatter(BaseFormatter):
    """Base Shape formatter"""

    def _write(self, driver=str, options: dict = {}, data: dict = None) -> str:
        """
        Generate data in driver format

        :param driver: OGR driver name
        :param options: formatting options
        :param data: dict of GeoJSON data

        :returns: string representation of format
        """

        gdf = gpd.GeoDataFrame.from_features(data['features'])
        output = io.BytesIO()
        try:
            gdf.to_file(output, driver=driver, use_arrow=True)
        except ModuleNotFoundError:
            gdf.to_file(output, driver=driver)

        return output.getvalue()


class KMLFormatter(BaseShapeFormatter):
    """KML formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.shape.KMLFormatter`
        """

        super().__init__({'name': 'KML', 'attachment': True})

        self.f = 'kml'
        self.mimetype = 'application/vnd.google-earth.kml+xml'
        self.extension = 'kml'

    def write(self, options: dict = {}, data: dict = None) -> str:
        """
        Generate data in KML format
        """
        return self._write('KML', options, data)

    def __repr__(self):
        return f'<KMLFormatter> {self.name}'


class GPKGFormatter(BaseShapeFormatter):
    """GPKG formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.shape.GPKGFormatter`
        """

        super().__init__({'name': 'GPKG', 'attachment': True})

        self.f = 'gpkg'
        self.mimetype = 'application/geopackage+sqlite3'
        self.extension = 'gpkg'

    def write(self, options: dict = {}, data: dict = None) -> str:
        """
        Generate data in GPKG format
        """
        return self._write('GPKG', options, data)

    def __repr__(self):
        return f'<GPKGFormatter> {self.name}'
