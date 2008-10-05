import numpy as N
from math import atan2
from sets import Set
import CellElement
import Layer
from Map import cfg_readlist, cfg_writelist

import osgeo.osr as osr

class RoutingConfig(object):
    """Routing configuration
    
    Attributes
    ----------

    routinglayers -- list of layer objects which are part of the routing network
    routingsets -- list of routing sets (the items are lists of layer objects)
               the routing sets defines partitions of the routinglayers with
               increasingly level of detail. The member of the first sets contains
               layers with fewer objects that goes longer distances like freeways
               and major roads and the last contains smaller streets.
               Example [[freeways, majorroads], [freeways, majorroads, roads, streets]]
    directions -- Dictionary keyed by layer objects that sets the direction of the traffic.
                  The values can be:
                  
                  ===== =======================================
                  Value Description
                  ===== ========================================
                  'N'   No direction
                  'F'   Traffic goes from first to last vertex
                  'B'   Traffic goes from last to first vertex
    
    routingedgelayers -- Routing edge layers. This is a read-only attribute
    alternatelayers -- Unknown
    speeds -- Dictionary of speed reduction keyed by layer object and the values are tuples of 
              numerator and denumerator of a fraction.
              Example: (5, 2) means 5/2
    
    nprimarylayers -- Unknown (the first n layers are primary which could mean that there are
                      routingedges for all objects in the layers)
    

    """
    
    def __init__(self):
        self.routinglayers = []
        self.routingsets = [[],[],[]] ## Minimum of 3 routing sets
        self.directions = {}
        self.routingedgelayers = []
        self.alternatelayers = []
        self.speeds = {}
        self.nprimarylayers = None

    def setupfromcfg(self, cfg, mapobj):
        """Read routing section from ini-file"""

        routinglaynums = map(int, cfg_readlist(cfg.get('ROUTING', 'ROUTING_GRP')))

        self.routinglayers = map(mapobj.getLayerByIndex, routinglaynums)
        
        routinglaynames = [l.name for l in self.routinglayers]

        routingsetlengths = map(int, cfg_readlist(cfg.get('ROUTING', 'ROUTING_SETS')))

        self.routingsets = [self.routinglayers[0:n] for n in routingsetlengths]

        self.directions = dict(zip(self.routinglayers, cfg.get('ROUTING', 'LAY_DIRS').split(' ')))

        routingedgelayernums = map(int, cfg.get('ROUTING', 'RDB_LAYERS').split(' '))
        
        self.routingedgelayers  = map(mapobj.getLayerByIndex, routingedgelayernums)

        alternatelaynums = map(int, cfg_readlist(cfg.get('ROUTING', 'ALT_LAYS')))
        
        self.alternatelayers = map(mapobj.getLayerByIndex, alternatelaynums)

        def getspeed(numden):
            return [int(cfg.get('ROUTING', 'SPEED_LAY_%s_%d'%(numden, idx))) for idx in routinglaynums]
        
        self.speeds = dict(zip(self.routinglayers, zip(getspeed('NUM'), getspeed('DEN'))))
        
        self.nprimarylayers = int(cfg.get('ROUTING', 'PRIM_LS_QTY'))
    
    def minset(self, layer):
        """Find minimum routing set the layer is a member of"""
        for i, rset in enumerate(self.routingsets):
            if layer in rset:
                return i

    def writecfg(self, cfg, mapobj):
        """Write routing section to ini-file

        >>> import Map, Layer, sys, inifile, ConfigParser
        >>> m = Map.Map()
        >>> rcfg = RoutingConfig()
        >>> f = m.addLayer(Layer.Layer(m, 'freeway', 'freeway', layertype = Layer.LayerTypePolyline))
        >>> rcfg.addRoutingLayer(m, f, 0)
        >>> r = m.addLayer(Layer.Layer(m, 'road', 'road', layertype = Layer.LayerTypePolyline))
        >>> rcfg.addRoutingLayer(m, r, 1)
        >>> s = m.addLayer(Layer.Layer(m, 'streets', 'streets', layertype = Layer.LayerTypePolyline))
        >>> rcfg.addRoutingLayer(m, s, 2)
        >>> cfg = ConfigParser.SafeConfigParser()
        >>> rcfg.writecfg(cfg, m)
        >>> cfg.write(sys.stdout)
        [ROUTING]
        alt_lays = 0 
        routing_grp = 3 0 2 4
        rdb_layers = 1 3 5
        speed_lay_den_0 = 1
        speed_lay_num_4 = 1
        speed_lay_den_2 = 1
        speed_lay_den_4 = 1
        speed_lay_num_0 = 1
        routing_sets = 3 1 2 3
        speed_lay_num_2 = 1
        lay_dirs = N N N
        <BLANKLINE>

        """

        if not cfg.has_section('ROUTING'):
            cfg.add_section('ROUTING')

        def layercmp(a,b):
            return cmp(self.minset(a), self.minset(b))

        ## Sort routing layers according to routing set membership
        self.routinglayers.sort(layercmp)

        routinglaynums = [mapobj.getLayerIndex(layer) for layer in self.routinglayers]
        cfg.set('ROUTING', 'ROUTING_GRP', cfg_writelist(routinglaynums))
        
        routingsetlengths = [len(rset) for rset in self.routingsets]
        cfg.set('ROUTING', 'ROUTING_SETS', cfg_writelist(routingsetlengths))

        cfg.set('ROUTING', 'LAY_DIRS',
                ' '.join([self.directions[layer] for layer in self.routinglayers]))

        for layer, speed in self.speeds.items():
            for i, numden in enumerate(('NUM', 'DEN')):
                cfg.set('ROUTING', 'SPEED_LAY_%s_%d'%(numden, mapobj.getLayerIndex(layer)), \
                        str(speed[i]))
        
        cfg.set('ROUTING', 'RDB_LAYERS', \
                ' '.join([str(mapobj.getLayerIndex(layer)) for layer in self.routingedgelayers]))

        cfg.set('ROUTING', 'ALT_LAYS',
                cfg_writelist(map(mapobj.getLayerIndex, self.alternatelayers)))

        if self.nprimarylayers == None:
            cfg.set('ROUTING', 'PRIM_LS_QTY', str(len(self.routinglayers)))
        else:
            cfg.set('ROUTING', 'PRIM_LS_QTY', str(self.nprimarylayers))

    def updateRoutingSets(self):
        """This will check for routing set inconsistencies and fix them"""
        for layer in self.routinglayers:
            for rset in self.routingsets[self.minset(layer):]:
                if layer not in rset:
                    rset.append(layer)

    def addRoutingLayer(self, mapobject, layer, routingsetnumber, direction = 'N', speed = (1, 1)):
        if layer.layertype != Layer.LayerTypePolyline:
            raise ValueError('Only polyline layers can be added to routing network')

        ## Add missing routing sets
        if routingsetnumber >= len(self.routingsets):
            for i in range(routingsetnumber - len(self.routingsets) + 1):
                self.routingsets.append([])

        self.updateRoutingSets()
                
        self.routinglayers.append(layer)

        for rset in self.routingsets[routingsetnumber:len(self.routingsets)]:
            rset.append(layer)

        self.createRoutingEdgeLayers(mapobject)

        self.directions[layer] = direction

        self.speeds[layer] = speed

    def addAlternateLayer(self, layer):
        self.alternatelayers.append(layer)        

    def createRoutingEdgeLayers(self, mapobject):
        if len(self.routingedgelayers) != len(self.routingsets):
            for i in range(len(self.routingedgelayers), len(self.routingsets)):
                name = 'Rte%d'%i
                filename = name.lower()
                layer = Layer.Layer(mapobject, name, filename, layertype = Layer.LayerTypeRouting)
                mapobject.addLayer(layer, Layer.RoutingLayerStyle())
                layer.open('w')
                self.routingedgelayers.append(layer)
                
    def build_routing_network(self, mapobj):
        """Build routing network from layers"""
        ## Find end-nodes
        
        ## Obtain the added layers in each routing set
        diffsets = N.diff([Set()] + map(Set, self.routingsets))
        nroutingsets = len(diffsets)
        
        ## Find all nodes in the routing network and calculate minimum
        ## routing set number of all nodes 
        nodes = {}
        for irset, layers in enumerate(diffsets):
            for layer in layers:
                for cellelement in layer.getCellElements():
                    coords = cellelement.coords
                    ## Iterate over start and end point
                    for coord in coords[0], coords[-1]:
                        if coord not in nodes:
                            nodes[coord] = irset
                        else:
                            nodes[coord] = min(irset, nodes[coord])

        def create_edge(iroutingset, layer, cellelement, ceref, istartvertex, iendvertex, 
                        startnode_edgenum, endnode_edgenum):
            routingedge = CellElement.CellElementRouting(coords = (cellelement.coords[istartvertex], cellelement.coords[iendvertex]),
                                                         layernumref = mapobj.getLayerIndex(layer),
                                                         cellnumref = ceref[0],
                                                         numincellref = ceref[1],
                                                         ivertices =  (istartvertex, iendvertex),
                                                         edgeindices = (startnode_edgenum, endnode_edgenum),
                                                         orientations = cellelement2orientations(cellelement, \
                                                                                                 istartvertex, iendvertex, layer),
                                                         distance = distance(cellelement, istartvertex, iendvertex, layer),
                                                         speedcat = None,
                                                         segmentflags = None,
                                                         bidirectional = False
                                                         )
            self.routingedgelayers[iroutingset].addCellElement(routingedge)
            
        ## Dictionary that keep track of the maximum edge number for each routing node
        nedges = {}
            
        ## Create routing edges
        for irset, laytuple in enumerate(zip(diffsets, self.routingedgelayers)):
            layers, edgelayer = laytuple
            for layer in layers:
                for cellelement, ceref in layer.getCellElementsAndRefs():
                    coords = cellelement.coords

                    ## Keep a list of start vertex per route set
                    istartvertex = nroutingsets * [0]
                    routingvertices = [0]

                    ## Iterate over vertices in polyline
                    for iendvertex in range(1, len(coords)):
                        ## Check if vertex is part of routing network
                        if coords[iendvertex] not in nodes:
                            continue

                        routingvertices.append(iendvertex)

                        if coords[iendvertex] not in nedges:
                            endvertex_edgeindex = 0
                        else:
                            endvertex_edgeindex = nedges[coords[iendvertex]]
                            
                        ## Iterate over routing sets that the cell elements belongs to
                        for irset2 in range(nodes[coords[iendvertex]], nroutingsets):
                            ## Get vertex index of routing edge start point
                            istart = istartvertex[irset2]

                            ## Calculate edge index for the start node of the routing edge
                            if coords[istart] not in nedges:
                                nedges_startvertex = 0
                            else:
                                nedges_startvertex = nedges[coords[istart]]

                            if istart > 0:
                                startvertex_edgeindex = nedges_startvertex + 1
                            else:
                                startvertex_edgeindex = nedges_startvertex

                            create_edge(irset2, layer, cellelement, ceref, istart, iendvertex, \
                                        startvertex_edgeindex, endvertex_edgeindex)

                            ## Update start vertex for this routing set
                            istartvertex[irset2] = iendvertex

                    ## Update nedges to include the created edges
                    for ivertex in routingvertices:
                        vertex = coords[ivertex]

                        if ivertex > 0 and ivertex < len(coords)-1:
                            nvertices = 2
                        else:
                            nvertices = 1
                        
                        if vertex in nedges:
                            nedges[vertex] += nvertices
                        else:
                            nedges[vertex] = nvertices

        ## If there is no alternate roads layer, create one
        if len(self.alternatelayers) == 0:
            altlay = Layer.Layer(mapobj, 'Alternate_RDS', 'altstr', layertype = Layer.LayerTypePolyline)
            mapobj.addLayer(altlay)
            self.addAlternateLayer(altlay)
            altlay.open('w')
            
    def __repr__(self):
        s = ''
        s += 'Routing layers: ' + str(self.routinglayers) + '\n'
        s += 'Routing sets: ' + str(self.routingsets) + '\n'
        s += 'Directions: ' + str(self.directions) + '\n'
        s += 'Routing edge layers: ' + str(self.routingedgelayers) + '\n'
        s += 'Alternate layers: ' + str(self.alternatelayers) + '\n'
        s += 'Speeds (numerator, denumerator): ' + str(self.speeds) + '\n'
        return s
    

wgs84 = osr.SpatialReference()
wgs84.ImportFromEPSG(4326)

sweref99 = osr.SpatialReference()
sweref99.ImportFromEPSG(3006)

wgs84_to_sweref99 = osr.CoordinateTransformation(wgs84, sweref99)

def angle(p1, p2):
    """Calculate direction angle from p1 to p2 which are WGS84 (lon,lat) coordinates
    
    >>> angle([0., 0.], [1., 0])
    90.0
    >>> angle([0., 0.], [-1., 0])
    -90.0
    >>> angle([0., 0.], [0., 1])
    0.0
    >>> angle([0., 0.], [1., -1])
    135.0
    >>> angle([0., 0.], [0., -1])
    180.0
    >>> angle([0., 0.], [1., 1])
    45.0

    """
    p1,p2 = [N.array(wgs84_to_sweref99.TransformPoint(*p)) for p in (p1,p2)]
    v = p2-p1
    return atan2(v[0], v[1]) * 180 / N.pi

def cellelement2orientations(cellelement, istartvertex, iendvertex, layer):
    r = []
    n = len(cellelement.coords)
    for points in (layer.discrete2float(cellelement.coords[istartvertex:istartvertex+2]),
                   layer.discrete2float(cellelement.coords[iendvertex-n:iendvertex-n-2:-1])):
        r.append(angle2orientation(angle(*points)))
    return tuple(r)

def points2orientationrange(p1, p2, scale):
    possibleorient = Set([])
    for step1 in [scale, -scale, N.array([-1, 1])*scale, N.array([1, -1])*scale]:
       for step2 in [scale, -scale, N.array([-1, 1])*scale, N.array([1, -1])*scale]:
           possibleorient.add(angle2orientation(angle(p1+step1/2, p2+step2/2)))
    return list(possibleorient)

def points2anglerange(p1, p2, scale):
    amin = 360.0
    amax = -360.0
    for step1 in [scale, -scale, N.array([-1, 1])*scale, N.array([1, -1])*scale]:
       for step2 in [scale, -scale, N.array([-1, 1])*scale, N.array([1, -1])*scale]:
           amin = min(amin, angle(p1+step1/2, p2+step2/2))
           amax = max(amax, angle(p1+step1/2, p2+step2/2))
    return amin,amax

def angle2orientation(angle):
    """Calculate orientation number used in CellElement.CellElementRouting
    
      ===== ===========
      angle value
      ===== ===========
      -135  1
      -90   0
      -45   7
      0     6
      45    5
      90    4
      135   3
      180   2

      >>> angle2orientation(-135)
      1
      >>> angle2orientation(-89.9)
      0
      >>> angle2orientation(-90)
      0
      >>> angle2orientation(-45)
      7
      >>> angle2orientation(0)
      6
      >>> angle2orientation(45)
      5
      >>> angle2orientation(90)
      4
      >>> angle2orientation(135)
      3
      >>> angle2orientation(180)
      2
      """
#    return (-int(N.floor(angle/45.0))-2)%8
#    return -(int(-angle/45) + 2)
    return int(N.round(-(angle-(-90)) * 8./360.0)) % 8

def distance(cellelement, start, end, layer):
    """Calculate distance of a CellElement""" 
    if not isinstance(cellelement, CellElement.CellElement):
        raise ValueError("CellElement expected")
    
    coords = [wgs84_to_sweref99.TransformPoint(*v) for v in layer.discrete2float(cellelement.coords[start:end+1])]
    return N.sum(N.sqrt(N.sum(N.diff(coords, axis=0)**2,axis=1)))
        
if __name__ == "__main__":
    import doctest
    doctest.testmod()

