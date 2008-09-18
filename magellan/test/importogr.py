from mapdir import MapDirectory
from Map import Map, MapTypeImage
from Layer import Layer, LayerTypePolyline, DetailMapLayerStyle
from CellElement import CellElementPolyline
from SearchGroup import Feature,FeatureNormal,FeatureStreet, GroupNormal
import osgeo.ogr as ogr

def importLayer(map, layer, searchgroup, ogrlayer, nameattribute = None):
    """Import a OGR layer into a Magellan map

    """

    ogrfeature = ogrlayer.GetNextFeature()
    i=0
    while ogrfeature:
        geo = ogrfeature.geometry()

        ## Create cell element
        if geo.GetGeometryName() == 'LINESTRING':
            ce = CellElementPolyline(layer, wkt=geo.ExportToWkt())
        else:
            raise ValueError('Unhandled geometry type: '+geo.GetGeometryName())

        ## Add geometry
        cellelementrefs = layer.addCellElement(ce)

        ## Add feature
        fields = ogrfeature.items()
        if nameattribute:
            name = fields[nameattribute]
        else:
            name = None
        feature = FeatureNormal(name=name, layerindex=map.getLayerIndex(layer),
                                objtype=11,
                                cellelementreflist=cellelementrefs)
        searchgroup.addFeature(feature)

        ogrfeature = ogrlayer.GetNextFeature()

        i+=1
        if i>2000:
            break

filename = 'shape/romania/roads.shp'

ds = ogr.Open(filename)

layer = ds.GetLayerByIndex(0)

map = Map(MapDirectory(), maptype=MapTypeImage)
map.open("w")

extent = layer.GetExtent()
map.bbox = ((extent[0], extent[2]), (extent[1], extent[3]))

## Add streets layer
streets = Layer(map, name="00_Streets", filename="00str", layertype=LayerTypePolyline)
streets.open(mode='w')
streetstyle = DetailMapLayerStyle()
streetstyle.style = 'US_STREET_LINE'
map.addLayer(streets, layerstyle = streetstyle)
map.getGroupByName('00_Roads').addLayer(streets)

importLayer(map, streets, map.getGroupByName('00_Roads'), layer, nameattribute='LABEL')

map.close()

map.writeImage('romania.imi')
