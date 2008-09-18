#!/usr/bin/env python
import sys
from glob import glob
import osgeo.ogr as ogr
import os
from sets import Set

from magellan.Map import Map
import magellan.OGRInterface as OGRInterface
import magellan.mapdir as mapdir

outpath = sys.argv[2]

if os.path.isfile(sys.argv[1]):
    map = Map(mapdir.Image(sys.argv[1]))
elif os.path.isdir(sys.argv[1]):
    map = Map(mapdir.MapDirectory(sys.argv[1]))
else:
    raise Exception("Cannot open " + sys.argv[1])
map.debug=False
map.open()

driver=ogr.GetDriverByName('ESRI Shapefile')
ds=driver.CreateDataSource(outpath)

pge = OGRInterface.OGRExporter(map)

layers = list(map.layers)

for group in map.groups:
    group.open('r')
    
    for layer in group.layers:
        print repr(layer)
        layers.remove(layer)
    
    pge.import_group(group, ds)
    group.close()

## export remaining layers
for layer in layers:
    layer.open('r')
    pge.import_layer(layer, ds)
    
    print repr(layer)

    for cellelement in layer.getCellElements():
        ref = map.getLayerByIndex(cellelement.layernumref).getCellElement((cellelement.cellnumref, cellelement.numincellref-1))
        print cellelement.cellnum, cellelement.numincell, cellelement

try:
    poigroup = map.getPOIGroup()
    if poigroup != None:
        poigroup.open('r')
        for layer in poigroup.layers:
            print repr(layer)
        pge.import_group(poigroup, ds)
        poigroup.close()
finally:    
    ds.Destroy()



