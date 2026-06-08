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
import io
import logging

from pygeoapi.formatter.base import BaseFormatter
from pygeoapi.crs import DEFAULT_CRS, get_crs

LOGGER = logging.getLogger(__name__)


class ParquetFormatter(BaseFormatter):
    """Parquet formatter"""

    def __init__(self, formatter_def: dict):
        """
        Initialize object

        :param formatter_def: formatter definition

        :returns: `pygeoapi_plugins.formatter.parquet.ParquetFormatter`
        """

        super().__init__({'name': 'Parquet', 'attachment': True})

        self.mimetype = 'application/vnd.apache.parquet'
        self.f = 'parquet'
        self.extension = 'parquet'

    def write(self, options: dict = {}, data: dict | None = {}) -> str:
        """
        Generate data in Parquet format

        :param options: Parquet formatting options
        :param data: dict of GeoJSON data

        :returns: string representation of format
        """

        format_conditions = [
            data is None,
            isinstance(data, dict) and not data.get('features'),
        ]
        if any(format_conditions):
            LOGGER.warning('No features to write to Parquet')
            return str()

        content_crs = options.get('content_crs') or DEFAULT_CRS
        crs = get_crs(content_crs)
        [auth, code] = crs.to_authority()
        gdf = gpd.GeoDataFrame.from_features(data, crs=f'{auth}:{code}')

        output = io.BytesIO()
        gdf.to_parquet(output, index=True)
        return output.getvalue()

    def __repr__(self):
        return f'<ParquetFormatter> {self.name}'
