import numpy as N
from numpy import asarray
import shapely.wkt as wkt
from shapely import geometry as geo
from shapely.ops import polygonize
from magellan.CellElement import Rec

class CoastLine(object):
    """The coastline class produces polygons from coastline segments

    >>> coastline = CoastLine()
    >>> coastline.add(((0.3,-1), (0.4,0.5)))
    >>> coastline.add(((0.4,0.5), (0.4,2)))
    >>> tuple(coastline.polygons(bbox = ((0,0), (1,1))))
    ((((0.40000000000000002, 1.0), (1.0, 1.0), (1.0, 0.0), (0.3666666666666667, 0.0), (0.40000000000000002, 0.5), (0.40000000000000002, 1.0)),),)
    
    """

    def __init__(self):
        self.coastlinesegments = []

    def add(self, segment):
        """Add coastline segment"""
        self.coastlinesegments.append(segment)

    def polygons(self, bbox = None, assumewater = False):
        coastline = geo.MultiLineString(self.coastlinesegments)

        if bbox == None:
            bboxpolygon = coastline.envelope
        else:
            bboxpolygon = wkt.loads(Rec(*bbox).wkt)

        hydropolygons = coastline2polygon(bboxpolygon, coastline.geoms, assumewater = assumewater)

        for p in hydropolygons:
            exterior = tuple(p.exterior.coords)
            interiors = tuple((tuple(interior.coords) for interior in p.interiors))
            yield (exterior,) + interiors

def isccw(coords):
    """Returns true if a closed sequence of coordinates are oriented counter-clockwise

    >>> isccw([[-1., -1.],[ 1., -1.],[ 1.,  1.],[-1.,  1.],[-1., -1.]])
    True
    >>> isccw([[-1.0, -1.0], [-1.0, 1.0], [1.0, 1.0], [1.0, -1.0], [-1.0, -1.0]])
    False

    """
    ## Calculate area of polygon as
    ## area = area + (x2 - x1) * (y2 + y1) / 2
    a = N.asarray(coords)

    ## x2 - x1
    x = N.diff(a[:,0])

    ## y2 + y1
    y = a[1:, 1] + a[:-1, 1]

    return sum(x*y) < 0

def issubseq(a, b):
    """Return true if b is a subsequence of a

    >>> issubseq([0, 1, 2, 3], [1, 2])
    True
    >>> issubseq([0, 1, 2, 3], [1, 2 ,3, 4])
    False
    >>> issubseq([0, 1, 2, 3], [99])
    False
    
    """
    try:
        i = a.index(b[0])
        return a[i:i + len(b)] == b
    except ValueError:
        return False

def coastline2polygon(bbox, linestrings, assumewater = False):
    """Return water polygons from a bounding box and coastline segments which always have
    land on the left side

    >>> bbox = geo.Polygon(((0,0), (1,0), (1,1), (0,1), (0,0)))
    >>> island = geo.LineString(((0.4, 0.1), (0.5,0.1), (0.5,0.2), (0.4,0.2), (0.4,0.1)))
    >>> ocean = geo.LineString(tuple(reversed(((0.4, 0.1), (0.5,0.1), (0.5,0.2), (0.4,0.2), (0.4,0.1)))))
    >>> coastlines_downup = [geo.LineString(((0.3,-1), (0.4,0.5))), geo.LineString(((0.4,0.5), (0.4,2))) ]
    >>> coastlines_updown = [geo.LineString(((0.4,0.5), (0.3,-1))), geo.LineString(((0.4,2), (0.4,0.5))) ]
    >>> print coastline2polygon(bbox, [island] + coastlines_downup)[0]
    POLYGON ((0.4000000000000000 1.0000000000000000, 1.0000000000000000 1.0000000000000000, 1.0000000000000000 0.0000000000000000, 0.3666666666666667 0.0000000000000000, 0.4000000000000000 0.5000000000000000, 0.4000000000000000 1.0000000000000000), (0.4000000000000000 0.1000000000000000, 0.5000000000000000 0.1000000000000000, 0.5000000000000000 0.2000000000000000, 0.4000000000000000 0.2000000000000000, 0.4000000000000000 0.1000000000000000))
    >>> print coastline2polygon(bbox, coastlines_updown)[0]
    POLYGON ((0.3666666666666667 0.0000000000000000, 0.0000000000000000 0.0000000000000000, 0.0000000000000000 1.0000000000000000, 0.4000000000000000 1.0000000000000000, 0.4000000000000000 0.5000000000000000, 0.3666666666666667 0.0000000000000000))
    >>> print coastline2polygon(bbox, [island])[0]
    POLYGON ((0.0000000000000000 0.0000000000000000, 0.0000000000000000 1.0000000000000000, 1.0000000000000000 1.0000000000000000, 1.0000000000000000 0.0000000000000000, 0.0000000000000000 0.0000000000000000), (0.4000000000000000 0.1000000000000000, 0.5000000000000000 0.1000000000000000, 0.5000000000000000 0.2000000000000000, 0.4000000000000000 0.2000000000000000, 0.4000000000000000 0.1000000000000000))
    >>> print coastline2polygon(bbox, [ocean])[0]
    POLYGON ((0.4000000000000000 0.1000000000000000, 0.4000000000000000 0.2000000000000000, 0.5000000000000000 0.2000000000000000, 0.5000000000000000 0.1000000000000000, 0.4000000000000000 0.1000000000000000))
   
    """

    islands = []
    oceans = []
    coastlines = []
    result = [] ## Resulting polygons
    for linestring in linestrings:
        if linestring.is_ring:
            if isccw(linestring.coords):
                islands.append(linestring)
            else:
                oceans.append(linestring)
        else:
            coastlines.append(linestring)

    lines = bbox.exterior
    for coastline in coastlines:
        lines = lines.union(coastline)

    if len(oceans) > 0:
        ## Find which islands that belongs to which oceans
        for ocean in oceans:
            oceancoords = list(ocean.coords)

            myislandscoords = []
            for i, island in reversed(list(enumerate(islands))):
                if geo.Polygon(oceancoords).contains(island):
                    myislandscoords.append(list(islands.pop(i).coords))

            result.append(geo.Polygon(oceancoords, myislandscoords))
            
    elif len(coastlines) > 0:
        coastpart = list(coastlines[0].intersection(bbox).coords)

        ## The polygonize function will return both land and water polygons
        ## The correct one has and exterior which has the same order of the points as
        ## any of the coastline segments
        waterpolygon = None
        for poly in polygonize((lines,) + tuple(islands)):
            if issubseq(list(poly.exterior.coords), coastpart):
                result.append(poly)
    elif len(islands) > 0:
        allislands = geo.MultiPolygon([(list(island.coords), []) for island in islands])
        result.append(bbox.difference(allislands))
    elif assumewater:
        result.append(bbox)
        
    return result

def showpoly(p):
    import pylab
    a = asarray(p.exterior)
    pylab.fill(a[:,0], a[:,1])

    for interior in p.interiors:
        a = asarray(interior)
        pylab.fill(a[:,0], a[:,1], 'g')
        
    pylab.show()



#for qq in q:
#    showpoly(qq)


if __name__ == "__main__":
    import doctest
    doctest.testmod()
