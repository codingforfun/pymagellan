import sys
from magellan.mapdir import MapDirectory, Image
from magellan.Map import Map, MapImage
from magellan.Layer import Layer, LayerTypePolyline, DetailMapLayerStyle
from magellan.CellElement import CellElementPolyline
from magellan.SearchGroup import Feature,FeatureNormal,FeatureStreet, GroupNormal
import osgeo.ogr as ogr
from magellan.rsttable import toRSTtable

layerinfo = True
dbinfo = False

filename = sys.argv[1]

mi = MapImage(filename)
mi.open('r')
m = mi.maps[0]
m.open('r')

print "Group names: ", m.getGroupNames()

print ""

## Print layer element
print 80 * "*"
print "Layers:"
if layerinfo:
    for layer in m.layers:
        layer.open('r')

        print "Layer: ", layer.name
        print "Header:"
        print layer.header_info()
        
        

#        print toRSTtable([['Text slot', 'object type']]+
#            [['0x%x'%ce.textslot, ce.objtype] for ce in layer.getCellElements()])

## Database info
if dbinfo:
    db = m.getDB()
    schema = db.schema
    schema.check(verbose=True)
    print schema
