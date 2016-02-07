"""
The osm rule module provides functionality to convert OpenStreetMap XML-file 
to a Magellan GPS image file
"""
import os
import urllib
import tempfile
import xml
from xml.sax import make_parser, handler

import char
import coastline
import magellan.Layer as Layer
from magellan.CellElement import CellElementPolyline, CellElementArea, \
    CellElementPoint, CellElementPOI, RoutingAttributes, GeometryError
from magellan.POI import FeaturePOI
from magellan.SearchGroup import FeatureNormal
import struct
import logging

try:
    ## python 2.5
    from xml.etree.cElementTree import ElementTree, Element, SubElement, dump,\
        tostring
except:
    ## python 2.4
    from cElementTree import ElementTree, Element, SubElement, dump, tostring

class MapBuilder(object):
    def __init__(self, rules, mapobj, nametags = None, 
                 routable = False):
        self.rules = rules
        self.map = mapobj
        self.routable = routable
        self.nametags = nametags
        self.charmap = char.UnicodeTranslator()
        self.coastline = None

        ## Set copyright field
        self.map.copyrightholders = \
            ('The map can be used freely under the terms of the Creative Commons '
             'Attribution-ShareAlike 2.0 license',)
        
    def load(self):
        raise Exception('Not implemented')

    def add_element(self, statement, tags, coords):
      cm = self.charmap
      if statement.tag in ('polygon', 'polyline', 'point'):
        layer, group = self.map.getLayerAndGroupByName(\
            self.map.mapnumstr + '_' + statement.get('layer') )

        objtype = statement.get('objtype') or 1

        if statement.tag == 'polyline':
          assert(layer.layertype == Layer.LayerTypePolyline)
          if len(coords) < 2:
            return

          unk = None
          if self.routable:
              unk = 0
          cellelement = CellElementPolyline.fromfloat(layer, coords, \
                objtype=group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype), unk=None)

          if self.routable:
              routingelements = statement.findall("routing")

              ra = RoutingAttributes()
              ra.segmentflags = 0
              ra.speedcat = 0
              cellelement.routingattributes = ra

              for routing in statement.findall("routing"):
                  for key, value in routing.items():
                      if key == 'oneway':
                          ra.bidirectional = value != 'on'
                      elif key == 'freeway':
                          ra.freeway = (value == 'on')
                      elif key == 'speedcat':
                          ra.speedcat = int(value)
                      elif key == 'segmenttype':
                          ra.segmenttype = int(value)

              if 'junction' in tags and self.tags['junction'] == 'roundabout':
                  ra.roundabout = True
                  ra.bidirectional = False

              if 'oneway' in tags and tags['oneway'] == 'yes':
                  ra.bidirectional = False

        elif statement.tag == 'polygon':
            try:
                objtype = group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype)
                cellelement = CellElementArea.fromfloat(layer, (coords,), 
                                                        objtype=objtype)
            except GeometryError:
                logging.warning('Improper polygon found: ' + str(coords))
                return

        elif statement.tag == 'point':
          assert(layer.layertype == Layer.LayerTypePoint)
          cellelement = CellElementPoint.fromfloat(layer, coords[0],
                         objtype = group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype))
        cellelementrefs = layer.addCellElement(cellelement)

        name = self._findname(statement, tags)

        if hasname(name):
            feature = FeatureNormal(name=cm.translate(name), 
                                    layerindex=self.map.getLayerIndex(layer),
                                    objtype=objtype,
                                    cellelementreflist=cellelementrefs)
            group.addFeature(feature)

      elif statement.tag == 'poi':
        poigroup = self.map.getPOIGroup()
        poilayer = self.map.getPOILayers()[0]

        category = statement.get('category')
        subcategory = statement.get('subcategory') or 'NOSUB1000'

        cat = poigroup.catman.getCategoryByName(category)
        subcat = cat.getSubCategoryByName(subcategory)

        poice = CellElementPOI.fromfloat(poilayer, coords[0], categoryid=cat.id, subcategoryid=subcat.id)

        name = self._findname(statement, tags)

        if hasname(name):
          attributes = []
          for a in statement.findall('attr'):
            if a.get('k') in tags:
              attributes.append(cm.translate(tags[a.get('k')]))
            elif a.text:
              attributes.append(cm.translate(a.text.encode))
            else:
              attributes.append('')

          feature = FeaturePOI(poilayer.addCellElement(poice), [cm.translate(name)] + attributes, cat.id, subcat.id)
          poigroup.addFeature(feature)
      elif statement.tag == 'coastline':
          if len(coords) < 2:
              return

          if self.coastline == None:
              self.coastline = coastline.CoastLine()

          self.coastline.add(coords)
          self.coastlayername = statement.get('layer')

    def _findname(self, statement, tags):
        if self.nametags != None:
            for nametag in self.nametags:
                if nametag in tags:
                    return tags[nametag]
        else:       
            nameelements = statement.findall('name')

            for nameelem in nameelements:
                if nameelem.get('k') in tags.keys():
                    return tags[nameelem.get('k')]
                elif nameelem.text != None:
                    return nameelem.text

    def addCoastLinePolygon(self, bbox = None):
        if self.coastline:
            layer, group = self.map.getLayerAndGroupByName(\
                self.map.mapnumstr + '_' + self.coastlayername )

            assert(layer.layertype == Layer.LayerTypePolygon)

            for polygon in self.coastline.polygons(bbox):
                try:
                    objtype = group.getObjtypeIndex(self.map.getLayerIndex(layer), 1)
                    cellelement = CellElementArea.fromfloat(layer, polygon, 
                                                            objtype=objtype)
                except GeometryError:
                    logging.warning('Improper polygon found: ' + str(coords))
                    return

                layer.addCellElement(cellelement)
        else:
            logging.warning("No coastline features found")
            

class LoadOsm(handler.ContentHandler, MapBuilder):
  """Parse an OSM file and add features to a Map"""
  def __init__(self, filename, rules, mapobj, nametags = None, 
               routable = False, inmemory = True):
      MapBuilder.__init__(self, rules, mapobj, nametags, routable)

      if inmemory:
          self.nodes = {}
      else:
          import bsddb
          class NodeDictionary(object):
              def __init__(self):
                  self.db = bsddb.hashopen(None, 'c')
                  
              def __getitem__(self, key):
                  return struct.unpack('dd', self.db[struct.pack('L',key)])

              def __setitem__(self, key, value): 
                  self.db[struct.pack('L',key)] = struct.pack('dd', *value)

          self.nodes = NodeDictionary()

      self.ways = []
      self.poicount = 0
      self.stop = False
      self.filename = filename

  def load(self):
    if(not os.path.exists(self.filename)):
      raise ValueError("No such data file %s" % self.filename)
    try:
      parser = make_parser()
      parser.setContentHandler(self)

      parser.parse(self.filename)
    except xml.sax._exceptions.SAXParseException:
      print "Error loading %s" % self.filename

  def startElement(self, name, attrs):
    """Handle XML elements"""
    if name in('node','way','relation'):
      self.tags = {}
      self.waynodes = []
      if name == 'node':
        """Nodes need to be stored"""
        id = int(attrs.get('id'))
        lat = float(attrs.get('lat'))
        lon = float(attrs.get('lon'))
        self.nodes[id] = (lon,lat)
        self.lastnodecoord = (lon, lat)

    elif name == 'nd':
      """Nodes within a way -- add them to a list"""
      nodeid = int(attrs.get('ref'))
      if nodeid in self.nodes:
          self.waynodes.append(nodeid)
      else:
          logging.warning('Ignoring undefined node %d in way'%nodeid)

    elif name == 'tag':
      """Tags - store them in a hash"""
      k,v = (attrs.get('k'), attrs.get('v'))
      if not k in ('created_by'):
        self.tags[k] = v
  
  def endElement(self, name):
    """Handle ways in the OSM data"""
    
    if name not in ('node','way','relation'):
      return

    matchingstatements = self.rules.filterOSMElement(name, self.tags)

    if matchingstatements == None:
      return

    if name == 'way':
        coords = [self.nodes[ref] for ref in self.waynodes]
    elif name == 'node':
        coords = [self.lastnodecoord]
    elif name == 'relation':
        logging.warning("Ignoring unsupported element type 'relation'")
        return

    for statement in matchingstatements:
        self.add_element(statement, self.tags, coords)

def downloadOsm(bbox, filename):
  """Download OSM data from www.informationfreeway.org of given bounding box

  @param bbox Bounding box list [left, bottom, right, top]

  @param filename Filename where the data will be written

  """
  url = "http://api.openstreetmap.org/api/0.5/map?bbox=%f,%f,%f,%f"%bbox
#  url = "http://www.informationfreeway.org/api/0.5/*[bbox=%f,%f,%f,%f]"%bbox
  print url
  print urllib.urlretrieve(url, filename)

## Some helper functions

def notnone(*args):
  """Return first element among arguments that is not None"""
  for a in args:
    if a != None:
      return a
  return None

def hasname(name):
    return name != None and len(name) > 0

if __name__ == "__main__":
    import doctest
    doctest.testmod()
