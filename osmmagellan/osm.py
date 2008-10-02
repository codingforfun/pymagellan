"""
The osm rule module provides functionality to convert OpenStreetMap XML-file to
a Magellan GPS image file
"""

import sys, os
from sets import Set
import operator

import xml
import urllib
from xml.sax import make_parser, handler
try:
    ## python 2.5
    from xml.etree.cElementTree import ElementTree, Element, SubElement, dump, tostring
except:
    ## python 2.4
    from cElementTree import ElementTree, Element, SubElement, dump, tostring

import char

import magellan.Map as Map, magellan.Layer as Layer
from magellan.SearchGroup import Feature,FeatureNormal,FeatureStreet
from magellan.CellElement import CellElementPolyline, CellElementArea, \
    CellElementPoint, CellElementPOI
from magellan.POI import POICategory, POISubCategory, FeaturePOI

class LoadOsm(handler.ContentHandler):
  """Parse an OSM file and add features to a Map"""

  def __init__(self, filename, rules, mapobj, nametags = None):
    """Initialise an OSM-file parser"""

    self.nodes = {}
    self.ways = []
    self.rules = rules
    self.map = mapobj
    self.poicount = 0
    self.nametags = nametags
    self.stop = False
      
    self.charmap = char.UnicodeTranslator()

    self.loadOsm(filename)

    ## Set copyright field
    self.map.copyrightholders = ('The map can be used freely under the terms of the Creative Commons Attribution-ShareAlike 2.0 license',)

  def loadOsm(self, filename):
    if(not os.path.exists(filename)):
      raise ValueError("No such data file %s" % filename)
    try:
      parser = make_parser()
      parser.setContentHandler(self)
      parser.parse(filename)
    except xml.sax._exceptions.SAXParseException:
      print "Error loading %s" % filename
    
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
      self.waynodes.append(int(attrs.get('ref')))
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

    cm = self.charmap

    for statement in matchingstatements:
      if statement.tag in ('polygon', 'polyline', 'point'):
        layer, group = self.map.getLayerAndGroupByName(self.map.mapnumstr + '_' + statement.get('layer'))

        objtype = statement.get('objtype') or 1
        if statement.tag == 'polyline':
          assert(layer.layertype == Layer.LayerTypePolyline)
          if len(self.waynodes) < 2:
            return
          cellelement = CellElementPolyline([self.nodes[ref] for ref in self.waynodes], 
                                            objtype=group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype))
        elif statement.tag == 'polygon':
          assert(layer.layertype == Layer.LayerTypePolygon)
          try:
            cellelement = CellElementArea(([self.nodes[ref] for ref in self.waynodes],), 
                                          objtype=group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype))
          except ValueError:
            return
        elif statement.tag == 'point':
          assert(layer.layertype == Layer.LayerTypePoint)
          cellelement = CellElementPoint(self.lastnodecoord, objtype = group.getObjtypeIndex(self.map.getLayerIndex(layer), objtype))

        cellelementrefs = layer.addCellElement(cellelement)

        name = self._findname(matchingstatements)        

        if name != None:
            feature = FeatureNormal(name=cm.translate(name), layerindex=self.map.getLayerIndex(layer),
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

        poice = CellElementPOI(self.lastnodecoord, categoryid=cat.id, subcategoryid=subcat.id)

        name = self._findname(matchingstatements)        

        if name != None:
          attributes = []
          for a in matchingstatements.findall('attr'):
            if a.get('k') in self.tags:
              attributes.append(cm.translate(self.tags[a.get('k')]))
            elif a.text:
              attributes.append(cm.translate(a.text.encode))
            else:
              attributes.append('')

          feature = FeaturePOI(poilayer.addCellElement(poice), [cm.translate(name)] + attributes, cat.id, subcat.id)
          poigroup.addFeature(feature)

  def _findname(self, matchingstatements):
    if self.nametags != None:
      for nametag in self.nametags:
        if nametag in self.tags:
          return self.tags[nametag]
    else:       
      nameelements = matchingstatements.findall('name')

      for nameelem in nameelements:
        if nameelem.get('k') in self.tags.keys():
          return self.tags[nameelem.get('k')]
        elif nameelem.text != None:
          return nameelem.text



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

if __name__ == "__main__":
    import doctest
    doctest.testmod()
