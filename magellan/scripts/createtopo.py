import sys
import osgeo.gdal as gdal
import osgeo.gdalconst as gdalconst
from magellan.Map import Map
from magellan.mapdir import Image,MapDirectory
from magellan.CellElement import CellElementPolyline
from magellan.SearchGroup import Feature,FeatureNormal,FeatureStreet, GroupNormal
from magellan.Layer import Layer, LayerTypePolyline, DetailMapLayerStyle

def getBBox(blxfile):
    dataset = gdal.Open(blxfile, gdalconst.GA_ReadOnly)

    # Extract georeferencing info
    geotransform = dataset.GetGeoTransform()
    
    xsize = dataset.RasterXSize
    ysize = dataset.RasterYSize

    north = geotransform[3]
    south = geotransform[3]+geotransform[5]*ysize
    east = geotransform[0]+geotransform[1]*xsize
    west = geotransform[0]

    return north, south, east, west

    
def createMapFromBLX(mapdir, blxfile):
    north, south, east, west = getBBox(blxfile)

    m = Map(mapdir)
    m.open('w')
    m.bbox = ((west, south), (east,north))

    ## Add dummy layer
    trails = Layer(m, name="00_dummy", filename="00dummy", layertype=LayerTypePolyline)
    trails.open(mode='w')
    trailstyle = DetailMapLayerStyle()
    m.addLayer(trails, layerstyle = trailstyle)

    roadsgroup = m.getGroupByName('00_Roads')
    roadsgroup.addLayer(trails)

    m.addTopo(blxfile)
    m.close()
    mapdir.write()
    
if __name__ == '__main__':
    createMapFromBLX(Image(sys.argv[2], bigendian=False), sys.argv[1])
    
    
    
