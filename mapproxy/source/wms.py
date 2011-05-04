# This file is part of the MapProxy project.
# Copyright (C) 2010 Omniscale <http://omniscale.de>
# 
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Retrieve maps/information from WMS servers.
"""
import sys
from mapproxy.request.base import split_mime_type
from mapproxy.cache.legend import Legend, legend_identifier
from mapproxy.image import concat_legends, make_transparent, ImageSource
from mapproxy.image.transform import ImageTransformer
from mapproxy.image.opts import ImageOptions
from mapproxy.layer import MapExtent, DefaultMapExtent, BlankImage, LegendQuery, MapQuery
from mapproxy.source import Source, InfoSource, SourceError, LegendSource
from mapproxy.client.http import HTTPClientError
from mapproxy.util import reraise_exception

import logging
log = logging.getLogger(__name__)

class WMSSource(Source):
    supports_meta_tiles = True
    def __init__(self, client, image_opts=None, coverage=None, res_range=None,
                 transparent_color=None, transparent_color_tolerance=None,
                 supported_srs=None, supported_formats=None):
        Source.__init__(self, image_opts=image_opts)
        self.client = client
        self.supported_srs = supported_srs or []
        self.supported_formats = supported_formats or []
        
        self.transparent_color = transparent_color
        self.transparent_color_tolerance = transparent_color_tolerance
        if self.transparent_color:
            self.transparent = True
        self.coverage = coverage
        self.res_range = res_range
        if self.coverage:
            self.extent = MapExtent(self.coverage.bbox, self.coverage.srs)
        else:
            self.extent = DefaultMapExtent()
    
    def get_map(self, query):
        if self.res_range and not self.res_range.contains(query.bbox, query.size,
                                                          query.srs):
            raise BlankImage()
        if self.coverage and not self.coverage.intersects(query.bbox, query.srs):
            raise BlankImage()
        try:
            resp = self._get_map(query)
            if self.transparent_color:
                resp = make_transparent(resp, self.transparent_color,
                                        self.transparent_color_tolerance)
            resp.opacity = self.opacity
            return resp
            
        except HTTPClientError, e:
            reraise_exception(SourceError(e.args[0]), sys.exc_info())
    
    def _get_map(self, query):
        format = self.image_opts.format
        if not format:
            format = query.format
        if self.supported_formats and format not in self.supported_formats:
            format = self.supported_formats[0]
        if self.supported_srs:
            if query.srs not in self.supported_srs:
                return self._get_transformed(query, format)
            # some srs are equal but not the same (e.g. 900913/3857)
            # use only supported srs so we use the right srs code.
            idx = self.supported_srs.index(query.srs)
            if self.supported_srs[idx] is not query.srs:
                query.srs = self.supported_srs[idx]
        resp = self.client.retrieve(query, format)
        return ImageSource(resp, size=query.size, format=format,
                           transparent=self.image_opts.transparent)
    
    def _get_transformed(self, query, format):
        dst_srs = query.srs
        src_srs = self._best_supported_srs(dst_srs)
        dst_bbox = query.bbox
        src_bbox = dst_srs.transform_bbox_to(src_srs, dst_bbox)
        
        src_width, src_height = src_bbox[2]-src_bbox[0], src_bbox[3]-src_bbox[1]
        ratio = src_width/src_height
        dst_size = query.size
        xres, yres = src_width/dst_size[0], src_height/dst_size[1]
        if xres < yres:
            src_size = dst_size[0], int(dst_size[0]/ratio + 0.5)
        else:
            src_size = int(dst_size[1]*ratio +0.5), dst_size[1]
        
        src_query = MapQuery(src_bbox, src_size, src_srs, format)
        resp = self.client.retrieve(src_query, format)
        
        img = ImageSource(resp, format, size=src_size,
                          transparent=self.image_opts.transparent)
        
        img = ImageTransformer(src_srs, dst_srs, self.image_opts.resampling).transform(img, src_bbox, 
            query.size, dst_bbox)
        
        img.format = format
        return img
    
    def _best_supported_srs(self, srs):
        latlong = srs.is_latlong
        
        for srs in self.supported_srs:
            if srs.is_latlong == latlong:
                return srs
        
        # else
        return self.supported_srs[0]
    
    def combined_layer(self, other, query):
        if not isinstance(other, WMSSource):
            return None
        
        if self.opacity is not None or other.opacity is not None:
            return None
        
        if self.supported_srs != other.supported_srs:
          return None

        if self.supported_formats != other.supported_formats:
          return None
        
        
        client = self.client.combined_client(other.client, query)
        if not client:
            return None
        
        return WMSSource(client, image_opts=self.image_opts)
        
class WMSInfoSource(InfoSource):
    def __init__(self, client, fi_transformer=None):
        self.client = client
        self.fi_transformer = fi_transformer
    
    def get_info(self, query):
        doc = self.client.get_info(query)
        if self.fi_transformer:
            doc = self.fi_transformer(doc)
        return doc
    

class WMSLegendSource(LegendSource):
    def __init__(self, clients, legend_cache):
        self.clients = clients
        self.identifier = legend_identifier([c.identifier for c in self.clients])
        self._cache = legend_cache
        self._size = None
    
    @property
    def size(self):
        if not self._size:
            legend = self.get_legend(LegendQuery(format='image/png', scale=None))
            # TODO image size without as_image?
            self._size = legend.as_image().size
        return self._size
    
    def get_legend(self, query):
        legend = Legend(id=self.identifier, scale=query.scale)
        if not self._cache.load(legend):
            legends = []
            error_occured = False
            for client in self.clients:
                try:
                    legends.append(client.get_legend(query))
                except HTTPClientError, e:
                    error_occured = True
                    log.error(e.args[0])
                except SourceError, e:
                    error_occured = True
                    # TODO errors?
                    log.error(e.args[0])
            format = split_mime_type(query.format)[1]
            legend = Legend(source=concat_legends(legends, format=format),
                            id=self.identifier, scale=query.scale)
            if not error_occured:
                self._cache.store(legend)
        return legend.source
    
