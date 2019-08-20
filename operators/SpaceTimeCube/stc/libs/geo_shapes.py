#! /usr/bin/env python3
# -*- coding: utf-8 -*-
#Michael ORTEGA - 26/Avril/2019

import geojson  as gj
import numpy    as np
import copy


class geo_shape:
    def __init__(self, name, id, points):
        self.name       = name
        self.id         = id
        self.points     = points
        self.triangles  = []
        self.color      = [1,1,1,.7]
        self.highlighted= False

    def triangulate(self):
        def _strip_range(stop):
            '''sort verticies in triangle strip order, i.e. 0 -1 1 -2 2 ...'''
            i = 0
            while i < stop:
                i += 1
                v, s = divmod(i, 2)
                yield v*(s*2-1)

        for i in _strip_range(len(self.points)):
            self.triangles.append(self.points[i])

class geo_shapes:

    def __init__(self):
        self.shapes         = []
        self.displayed      = True
        self.LOW_COLOR = [1,1,1,.7]
        self.HIGH_COLOR = [1,0,0,.7]

    def get_shapes_info(self):
        infos = []
        for s in self.shapes:
            infos.append({'name': s.name, 'id': s.id, 'highlighted': s.highlighted})
        return infos

    def highlight_shapes(self, l):
        for s in self.shapes:
            if s.id in l:
                s.color = self.HIGH_COLOR
                s.highlighted = True
            else:
                s.color = self.LOW_COLOR
                s.highlighted = False

    def read_shapes(self, fname):
        if fname:
            geoj = gj.load(open(fname, 'r'))

            for f in geoj['features']:
                n = f['properties']['name']
                c = f['geometry']['coordinates']
                id = int(f['properties']['code'])
                out = []

                #-------------
                #for now we only deal with the contours, no holes
                while len(c) > 1:
                    c = c[0]
                #--------------

                while len(c) > 0:
                    elem = c.pop()
                    if isinstance(elem, list):
                        for e in elem:
                            c.append(e)
                    else:
                        out.append(elem)

                out.reverse()
                out = np.reshape(np.array(out), (-1, 2))
                fs = geo_shape(n, id, out)
                self.shapes.append(fs)
                fs.triangulate()
