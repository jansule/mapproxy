# -:- encoding: utf-8 -:-
# This file is part of the MapProxy project.
# Copyright (C) 2011 Omniscale <http://omniscale.de>
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

class ImageOptions(object):
    def __init__(self, transparent=False, opacity=None, resampling=None, format=None):
        self.transparent = transparent
        self.opacity = opacity
        self.resampling = resampling
        self.format = format
    
    def __repr__(self):
        return 'ImageOptions(transparent=%r, opacity=%r, resampling=%r, format=%r)' % (
            self.transparent, self.opacity, self.resampling, self.format,
        )