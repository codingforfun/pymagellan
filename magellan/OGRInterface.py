import Cell
import osgeo.ogr as ogr
import Layer
import CellElement
import sys

type2ogrtype = { 'int': ogr.OFTInteger, 'string': ogr.OFTString }

class OGRExporter:
    type_to_ogr = { CellElement.CellElementPOI.typecode: ogr.wkbPoint,
                    CellElement.CellElementPoint.typecode: ogr.wkbPoint,
                    CellElement.CellElementLabel.typecode: ogr.wkbPoint,
                    CellElement.CellElementArea.typecode: ogr.wkbMultiPolygon,
                    CellElement.CellElementPolyline.typecode: ogr.wkbLineString,
                    CellElement.CellElementRouting.typecode: ogr.wkbLineString
                    }

    def __init__(self, map):
        self.map = map
        self.debug = True

    def import_group(self, group, datasource):
        if self.debug:
            print "Importing group "+group.name+"."
            layer_first={}
        
        # Create layers
        for layer in group.layers:
            self.import_layer(layer, datasource, group = group)
        group.close()

    def import_layer(self, layer, datasource, group = None):
        ## Create OGR Layer
        ogrlayer=datasource.CreateLayer(layer.getName(),geom_type=self.type_to_ogr[layer.getLayerType()])
       
        cellelementclass = Cell.cellElementTypeMap[layer.layertype]

        fieldnum = 0

        layerfields = cellelementclass.exportfields + ['numincell']

        for field in layerfields:
            ogrlayer.CreateField(ogr.FieldDefn(field, ogr.OFTString))
            fieldnum += 1

        dbfields = fieldnum

        if group:
            for field,fieldtype in zip(group.getFeatureExportFields(), group.getFeatureExportFieldTypes()):
                ogrlayer.CreateField(ogr.FieldDefn(field, type2ogrtype[fieldtype]))

        for cellelement in layer.getCellElements():
            # Insert cellelement
            f = ogr.Feature(feature_def=ogrlayer.GetLayerDefn())
            f.SetGeometryDirectly(ogr.CreateGeometryFromWkt(cellelement.wkt))

            excess = " ".join(["0x%02x"%ord(x) for x in cellelement.excess])

            for i, field in enumerate(layerfields):
                f.SetField(i, str(getattr(cellelement, field)))

            if group:
                groupfeature = group.getFeatureByCellElement(cellelement)

                if groupfeature != None:
                    for i,field in enumerate(groupfeature.exportToList(group)):
                        f.SetField(i+dbfields,field)

            ogrlayer.CreateFeature(f)

            f.Destroy()


