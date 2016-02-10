"""
The osmrules module provides functions and classes for filtering of OSM data and
creation of Magellan GPS map objects based on a rule file in XML format.

The rule file syntax is described in doc/rules.txt

"""

from sets import Set

import magellan.Map as Map, magellan.Layer as Layer
from magellan.SearchGroup import GroupNormal, GroupStreet
from magellan.POI import POICategory, POISubCategory

try:
    ## python 2.5
    from xml.etree.cElementTree import ElementTree, Element, SubElement, dump, tostring
except:
    ## python 2.4
    from cElementTree import ElementTree, Element, SubElement, dump, tostring

layerTypeMap = {
  'polyline': Layer.LayerTypePolyline,
  'polygon': Layer.LayerTypePolygon,
  'point': Layer.LayerTypePoint
  }

class OSMMagRules(object):
    """Provides methods for OSM element filtering and creation of Magellan maps based on a rule file
    
    """
    
    def __init__(self, filename):
      self.filename = filename
      self.etree = ElementTree(file=filename)
      self.root = self.etree.getroot()

    def filterOSMElement(self, elementname, tags):
      """Find matching control statements for the given element name and tags.

      The result is an Element with matching statements as children

      >>> r = OSMMagRules('test/data/testrules.xml')
      >>> result = r.filterOSMElement('node', {'amenity': 'fuel'})
      >>> [e.tag for e in result]
      ['poi']

      """

      elements = applyRules(self.root.find("rules"), elementname, tags)

      if len(elements) == 0:
        return None

      result = Element('result')
      for element in elements:
        result.append(element)

      return result

    def createMap(self, mapobj = None, routable=False):
      """Create a Magellan map from rules"""
      if mapobj == None:
          if routable:
              maptype = Map.MapTypeStreetRoute
          else:
              maptype = None
          m = Map.Map(maptype=maptype)
      else:
          m = mapobj

      m.open("w")

      m.name = self.root.find("name").text

      routingedgelayers = []

      ## Create groups
      for groupelem in self.root.find("groups").findall("group"):
        ## Create group
        if groupelem.get("streetgroup") == 'true':
            g = GroupStreet(m, name=m.mapnumstr + '_' + groupelem.get("name"))
        else:
            g = GroupNormal(m, name=m.mapnumstr + '_' + groupelem.get("name"))
        
        try:
          m.addGroup(g)
        except ValueError:
          g = m.getGroupByName(g.name)

        if groupelem.get("searchgroup") and groupelem.get("searchgroup").lower() == 'true':
          g.searchable = True

        ## Load visibility presets
        visibilitypresets = {}
        for elem in self.root.findall('visibilitypresets/visibilitypreset'):
          visibilitypresets[elem.get('name')] = elem

        ## Add layers
        for layerelem in groupelem.find("layers").findall("layer"):
          l = Layer.Layer(m, m.mapnumstr + '_' + layerelem.get("name"), layerelem.get("filename"), 
                          layerTypeMap[layerelem.get("type")])
          layerstyle = Layer.DetailMapLayerStyle(color=layerelem.get("color"), 
                                            style=layerelem.get("style"))
          if layerelem.get("visibilitypreset"):
            if layerelem.get("visibilitypreset") not in visibilitypresets:
              raise ValueError("visibilitypreset=%s is referring to an undefined preset"%layerelem.get("visibilitypreset"))
            else:
              set_visibility(layerstyle, visibilitypresets[layerelem.get("visibilitypreset")])
          else:
            set_visibility(layerstyle, layerelem)

          ## Add routing layer
          if routable and layerelem.get("routingset"):
              routingedgelayers.append((l, int(layerelem.get("routingset"))))

          ## Set draw order priority
          if layerelem.get("draworder"):
            l.draworder = int(layerelem.get("draworder"))

          m.addLayer(l, layerstyle = layerstyle)
          g.addLayer(l)

          layerstyle.verify(l.name, m)

          l.open('w')



      ## Create POI categories
      if self.root.find("poicategories") != None:
        m.addPOIGroupAndLayer()

        group = m.getPOIGroup()

        poicategorieselem = self.root.find("poicategories")
        for catelem in poicategorieselem.findall("category"):
          name = catelem.get("name")

          cat = POICategory(name)

          ## Add attributes
          attributes = []
          if poicategorieselem.find('attributes'):
            attributes.extend(poicategorieselem.find('attributes').findall('attr'))
          if catelem.find('attributes'):
            attributes.extend(catelem.find('attributes').findall('attr'))

          cat.addField('POI Name')
          for attrelem in attributes:
            cat.addField(attrelem.get('name'))

          if catelem.find("subcategories"):
            for subcatelem in catelem.find("subcategories").findall("subcategory"):
              cat.addSubCategory(POISubCategory(subcatelem.get("name")))
          else:
            cat.addSubCategory(POISubCategory("NOSUB1000"))

          group.addCategory(cat, icon = catelem.get('icon'))
          
      ## Add routing edge layers
      for l, rset in routingedgelayers:
          m.addRoutingLayer(l, rset)


      return m

## Some helper functions
def applyRules(rules, elem, tags):
  """Filter an OSM element according to the given rules"""
  result = []
  lastruleelem = None

  for ruleelem in rules.getchildren():
    if ruleelem.tag == 'rule':
      found = False
      if elem == ruleelem.get("e"):
        keys = ruleelem.get('k').split('|')
        values = ruleelem.get('v').split('|')

        for key in keys:
          if key in tags and (tags[key] in values or '*' in values) or \
                key == '~' and len(tags) == 0 or \
                '~' in values and key not in tags or \
                key == '*' and Set(tags.values()) & Set(values):
            found = True

        if found:
          return result + applyRules(ruleelem, elem, tags)
    elif ruleelem.tag == 'else':
      if lastruleelem and lastruleelem.tag == 'rule':
        return result + applyRules(ruleelem, elem, tags)
      else:
        raise ValueError('else clause must be preceeded by rule')
    else:
      result.append(ruleelem)

    lastruleelem = ruleelem

  return result
      

def set_visibility(layerstyle, element):
  """Set visibility fields of a layerstyle from xml elements"""

  def getranges(elem):
    ranges = [(int(zoomrange.get('from')), int(zoomrange.get('to'))) for zoomrange in elem.findall('range')]

    if len(ranges) != 5:
      raise ValueError('Exactly 5 detail levels should be used')

    return ranges

  layervisibility = element.find('layervisibility')
  if layervisibility:
    layerstyle.visiblerange = getranges(layervisibility)
    
  labelvisibility = element.find('labelvisibility')
  if labelvisibility:
    layerstyle.labelrange = getranges(labelvisibility)

  basemapvisibility = element.find('basemapvisibility')
  if basemapvisibility:
    layerstyle.hidebasemaprange = getranges(basemapvisibility)

def get_visibility(layerstyle, root):
  """Create layer visibility xml elements from layer style"""

  def getranges(rangelist, root):
    for r in rangelist:
      rangeelem = SubElement(root, 'range')
      rangeelem.set('from', str(r[0]))
      rangeelem.set('to', str(r[1]))

  layervisibility = SubElement(root, 'layervisibility')
  getranges(layerstyle.visiblerange, layervisibility)

  labelvisibility = SubElement(root, 'labelvisibility')
  getranges(layerstyle.labelrange, labelvisibility)

  basemapvisibility = SubElement(root, 'basemapvisibility')
  getranges(layerstyle.hidebasemaprange, basemapvisibility)


def createRulesFromMap(mapobj):
  """Create an elementtree of groups and layers from a map object"""

  reverseLayerTypemap = dict([(v,k) for k,v in layerTypeMap.items()])

  root = Element('osmmap')

  tree = ElementTree(root)

  groupselem = SubElement(root, 'groups')
  for group in mapobj.groups:
    groupelem = SubElement(groupselem, 'group')
    groupelem.set('name', group.name)

    layerselem = SubElement(groupelem, 'layers')
    for layer in group.layers:
      layer.open('r')
      layerelem = SubElement(layerselem, 'layer')
      layerelem.set('name', layer.name)
      layerelem.set('filename', layer.filename)
      layerelem.set('type', reverseLayerTypemap[layer.layertype])

      style = mapobj.getLayerStyle(layer)
      layerelem.set('style', style.style)
      layerelem.set('color', style.color)
      layerelem.set('draworder', str(layer.draworder))

      get_visibility(style, layerelem)
  return tree

def indent(s, n):
  """Indent string

  >>> indent("apa\\nrapa\\nbapa", 4)
  '    apa\\n    rapa\\n    bapa'
  
  """
  return '\n'.join([n*' ' + line for line in s.split('\n')])


if __name__ == "__main__":
    import doctest
    doctest.testmod()
