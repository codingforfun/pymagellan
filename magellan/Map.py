import struct
import string
import re
import copy
import os
import sys
import shutil
import DBUtil
from DBUtil import Database
from SearchGroup import Group, GroupNormal, GroupStreet, groupFactory, buildziprecord, buildmarinerecord
from POI import POIGroup, POILayerConfig, createPOITables, POILayerStyle
from Layer import Layer,LayerTypePOI,LayerStyle, DetailMapLayerStyle, LayerConfig
from CellElement import Rec
from Topo import Topo
from inifile import ConfigParserUpper, IniFileFilter
import mapdir
import numpy as N
import logging
from misc import cfg_readlist, cfg_writelist
import routing

def createMap(dir, **kvargs):
    return Map(mapdir.MapDirectory(dir), **kvargs)
def createMapImage(file, **kvargs):
    return Map(mapdir.Image(file), **kvargs)
def openMapFromImage(filename):
    return Map(mapdir.Image(filename))

def determine_path ():
    """Borrowed from wxglade.py"""
    try:
        root = __file__
        if os.path.islink (root):
            root = os.path.realpath (root)
        return os.path.dirname (os.path.abspath (root))
    except:
        print "I'm sorry, but something is wrong."
        print "There is no __file__ variable. Please contact the author."
        sys.exit ()

datadir = os.path.join(determine_path(), "data")

def encodeintlist(l):
    """Encode INI file list of integers

    >>> encodeintlist([3,2])
    '2 3 2'
    
    """
    return ' '.join(map(str, [len(l)]+l))
    
def decodeintlist(s):
    """Encode INI file list of integers

    >>> decodeintlist('2 3 2')
    [3, 2]
    
    """
    l = map(int, s.split(' '))
    assert(l[0]+1==len(l))
    return l[1:]    

## Constants
MapTypeNormal = None
MapTypeMarine = 'NAV_MARINE'
MapTypeStreetRoute = 'STR_ROUTE'

# Class Map
class Map(object):
    formatversion = '1.01'

    defaultscale = N.array([9e-6, 9e-6])
    
    def __init__(self, mapdirobj = None, gpsimage = True, maptype = MapTypeNormal,
                 mapnumber=0, bigendian = False, inifile = None):
        self.gpsimage = gpsimage
        self.maptype = maptype
        self._mapnumber = mapnumber

        if mapdirobj == None:
            self.mapdir = mapdir.MapDirectory()
        else:
            if not isinstance(mapdirobj, mapdir.MapDirectory):
                raise ValueError("mapdirobj should be a MapDirectory object")
            self.mapdir = mapdirobj

        self.name = "Map"

        self.mode = None      # Open mode ['r','w','a']

        self.debug=False

        self.has_zip = True

        self.has_marine = (maptype == MapTypeStreetRoute)

        self._inifile = inifile

        self.inmemory = False ## If true all processing will be done in memory

        if maptype == MapTypeStreetRoute:
            self.routingcfg = routing.RoutingConfig()
        else:
            self.routingcfg = None

        ## Set endian
        self.bigendian = bigendian

        # Groups
        self._poigroup=None
        self.groups=[]
        self._searchgroups = [] ## Searchable group indices

        # Tables
        if maptype == MapTypeStreetRoute:
            self._ziptables = (0,1,0,0)
        else:
            self._ziptables = (0,0)
        self._marinetables = (0,1,0,1)

        ## Bounding box and bounding rect
        self._bboxrec = None
        self._boundrec = Rec((-198.316818, -99.475197), (198.316818,  99.475197))

        ## Resolution and reference point
        self._scale = self.defaultscale
        self._refpoint = N.array([0.0, 0.0])

        ## Config file
        self._cfg = ConfigParserUpper()
        self._initcfg()

        ## Layer and POI config
        self._laycfg = LayerConfig()
        self._poiconfig = POILayerConfig()
        
        ## Database
        self._db = None

        ## Other parameters
        otherparameters = (
            ## Name, default value, description
            ('startscale', 4500.0, 'Start scale'),
            ('laycolor', 0, 'Unknown'),
            ('copyrightholders', ['Unknown'], 'Copyright holders'),
            )

        ## Create properties for these parameters
        for param in otherparameters:
            setattr(self, '_' + param[0], param[1])
            getfunc = lambda self, val: self.set_parameter('_'+param[0])
            setfunc = lambda self, val: self.set_parameter('_'+param[0], val)
            setattr(self.__class__, param[0], property(getfunc, setfunc, doc=param[2]))

        ## Update config
        self._updatecfg()

    def set_scale(self, scale):
        """Set discrete unit as a xscale, yscale sequence"""
        try:
            self._scale = N.array(list(scale))
        except TypeError:
            self._scale = scale * N.ones((2))
            
    def get_scale(self):
        return self._scale
    scale = property(get_scale, set_scale, doc="Discretization unit vector")

    def set_refpoint(self, refpoint):
        self._refpoint = N.array(refpoint)
    def get_refpoint(self):
        return self._refpoint
    refpoint = property(get_refpoint, set_refpoint, doc="Reference point for the discretization process")

    def set_bbox(self, points):
        self.bboxrec = Rec(tuple(points[0]), tuple(points[1]))
    def get_bbox(self):
        bboxrec = self.bboxrec
        return ((bboxrec.minX(), bboxrec.minY()),
                (bboxrec.maxX(), bboxrec.maxY()))

    def set_parameter(self, parameter, value):
        if self.mode in ['r', 'a']:
            raise ValueError("Parameter %s can only be set in 'w' mode"%parameter)
        self.__dict__[parameter] = value
    def get_parameter(self, parameter):
        return self.__dict__[parameter]

    def set_bboxrec(self, rec):
        if self.mode in ['r', 'a']:
            raise ValueError("Bounding box can only be set in 'w' mode")
        if len(self.layers) > 0:
            raise ValueError("Set bounding box before defining layers")
        if isinstance(rec, Rec):
            self._bboxrec = rec.negY().toFloat32()
        else:
            raise ValueError("rec must be a Rec object")
    def get_bboxrec(self):
        if self._bboxrec == None:
            return None
        return self._bboxrec.negY()

    bbox = property(get_bbox, set_bbox, doc='Bounding box ((xmin,ymin),(xmax,ymax))')
    bboxrec = property(get_bboxrec, set_bboxrec, doc='Bounding box rectangle')
        
    def open(self, mode='r'):
        if self.mode != None:
            return None

        self.mode = mode

        if mode == 'w':
            if self.gpsimage:
                if self._inifile == None:
                    self._inifile = self.mapnumstr + 'map.ini'

                ## Create database
                self._db = Database(self.mapdir, 'db' + self.mapnumstr, mode, self.bigendian)

                ## Create zip table
                if self.has_zip:
                    buildziprecord(self._db,
                                   zipfilename = self.mapnumstr + 'z.dat',
                                   auxfilename = self.mapnumstr + 'cn.dat',
                                   extended = self.maptype == MapTypeStreetRoute)

                ## Create marine table
                if self.has_marine:
                    buildmarinerecord(self._db,
                                   filenameprefix = self.mapnumstr)

                ## Create basic groups
                if self.maptype == MapTypeStreetRoute:
                    roads = GroupStreet(self, name=self.mapnumstr + "_Roads")
                else:
                    roads = GroupNormal(self, name=self.mapnumstr + "_Roads")
                roads.searchable = True
                self.addGroup(roads)
                self.addGroup(GroupNormal(self, name=self.mapnumstr + "_Railroads"))
                self.addGroup(GroupNormal(self, name=self.mapnumstr + "_Hydrography"))
                self.addGroup(GroupNormal(self, name=self.mapnumstr + "_Parks"))

            else:
                if self._inifile == None:
                    self._inifile = 'map.ini'
        elif mode in ('r','a'):
            ## Find ini file
            if self._inifile == None:
                filelist = self.mapdir.listdir()
                possibleinifiles = ('map.ini', self.mapnumstr + 'map.ini', 'lay_info.ini')
                found = False
                for filename in possibleinifiles:
                    if filename in filelist:
                        self._inifile = filename
                        found = True
                        break
                if not found:
                    raise ValueError('Could not find ini-file')

            self._cfg.readfp(IniFileFilter(self.mapdir.open(self._inifile)))

            # Get map type
            self.maptype = self._cfg.get("MAP_INFO", "MAPTYPE")

            # Get bounding box
            bbox = map(float, self._cfg.get("MAP_INFO", "BND_BOX").split(" "))
            self._bboxrec = Rec([bbox[0],bbox[2]], [bbox[1], bbox[3]])

            # Get map name
            self.name = self._cfg.get('MAP_INFO', 'MAP_NAME')
#            self.date = self._cfg.get('MAP_INFO', 'MAP_DATE')

            self._laycfg.setupfromcfg(self._cfg, self)
            
            # Find database path
            dbname = self._cfg.get("LAYERS","DB_NAME")
            dbname = re.sub('\\\\', os.sep, dbname)

            # Since Windows is case insensitive, try to match the path case insensitive
            plist=dbname.split(os.sep)
            for i in range(0,len(plist)-2):
                path=os.sep.join(plist[0:i+1])
                if len(path)>0:
                    hits=[d for d in self.mapdir.listdir(path) if d.lower() == plist[i+1].lower()]
                    if len(hits)==0:
                        raise ValueError("Couldnt find database")
                    plist[i+1]=hits[0]
            dbname = os.sep.join(plist)

            if dbname:
                self._db = Database(self.mapdir, dbname, self.mode, self.bigendian)

            # Read groups
            if self.debug:
                print "Groups:"
            for i in range(0,self._cfg.getint("GROUPS","NUMBER")):
                thegroup = groupFactory(self, i, self._cfg, self._db)
                self.groups.append(thegroup)
                thegroup.initFromIni(self._cfg)

            # Read POI file and POI layers
            if self._cfg.has_section("POI"):
                poi_ini = self._cfg.get("POI","POI_CONFIG")
                self.poicfg = ConfigParserUpper()
                if self.mapdir.isfile(poi_ini):
                    self.poicfg.readfp(IniFileFilter(self.mapdir.open(poi_ini)))

                    if self.poicfg.has_section("LAYERS"):
                        self._poigroup = POIGroup(self)

                    self._poiconfig.setupfromcfg(self.poicfg, self)

            # Read routing info
            if self.maptype == MapTypeStreetRoute:
                self.routingcfg = routing.RoutingConfig()
                self.routingcfg.setupfromcfg(self._cfg, self)

    def calculatebbox(self):
        """Calculate total bounding box rectangle from layers"""

        def layerbboxunion(a, b):
            if a == None and b == None:
                return None
            elif a == None:
                return b
            elif b == None:
                return a
            else:
                return a.union(b)

        return reduce(layerbboxunion, [layer.bboxrec for layer in self.layers + self._poiconfig.layers], None)

    def close(self):
        if self.mode == None:
            return
        
        write = self.mode in ['a','w']

        
        ## Optimize layers in groups
        logging.info('Optimizing cell structure of normal layers')
        remaininglayers = list(self.layers + self._poiconfig.layers)
        if self.groups != None:
            for group in self.groups:
                group.optimizeLayers()
                for layer in group.layers:
                    remaininglayers.remove(layer)

        ## Create routing layers and build routing network
        if self.maptype == MapTypeStreetRoute:
            if self.mode == 'w':
                logging.info('Building routing network')
                self.routingcfg.build_routing_network(self)
                
            elif self.mode == 'a':
                raise Exception('Updating of routing network not implemented')

            ## Copying routing data file
            self.mapdir.copyfile(os.path.join(datadir, 'routing.dat'))


        ## Optimize remaining layers
        if self.maptype == MapTypeStreetRoute:
            logging.info('Optimizing cell structure of routing layers')
        for layer in remaininglayers:
            layer.optimize()

        ## Update ini file
        if write:
            if self._bboxrec == None:
                bbox = self.calculatebbox()
                if bbox == None:
                    raise ValueError("None of the layers contain a bounding box")

                self._bboxrec = bbox.negY()
                
            self._updatecfg()        

        ## Copy bounding box from map for layers without one
        logging.info('Closing map')
        for layer in self.layers + self._poiconfig.layers:
            if layer.bboxrec == None:
                layer.bboxrec = self.bboxrec

        # Close groups and update INI file
        if self.groups != None:
            for group in self.groups:
                group.close()
        self.groups = None

        # Close poi group and poi layers
        if self._poigroup != None:
            self._poigroup.close()
            if write:
                if self._cfg.has_section("POI"):
                    poiconfig = self._cfg.get("POI","POI_CONFIG")
                    self.poicfg.write(self.mapdir.open(poiconfig, "wb"))

            self._poiconfig.close()


        # Close layers
        self._laycfg.close()
        
        # Write ini file
        if write:
            # Convert section keys to uppercase
            self._cfg.write(self.mapdir.open(self._inifile, "wb"))

        self.poicfg = None
        
        if self._db != None:
            self._db.close()
            del self._db
            self._db = None

        self.mode = None

    def getGroupByIndex(self, index):
        return self.groups[index]

    def getGroupByName(self, name):
        for group in self.groups:
            if group.name == name:
                return group

    def getGroupNames(self):
        return [group.name for group in self.groups]

    def getGroupIndex(self, group):
        if group in self.groups:
            return self.groups.index(group)    
        elif group == self._poigroup:
            return 0
        else:
            raise Exception('Group is not registered')

    def addGroup(self, group):
        if group.name in [g.name for g in self.groups]:
            raise ValueError("Group already added")
        
        if self._poigroup:
            raise ValueError('Normal groups cannot be added after POI groups')

        groupnum = len(self.groups)
        self.groups.append(group)
        group.open('w')
        
    def getLayerByIndex(self, index):
        return self._laycfg.getLayerByIndex(index)

    def getLayerStyle(self, layer):
        return self._laycfg.getLayerStyleByIndex(self.getLayerIndex(layer))
    
    def getLayerIndex(self, layer):
        return self._laycfg.getLayerIndex(layer)

    def getLayerAndGroupByName(self, name):
        """Get layer by name and the group it belongs to"""
        for group in self.groups:
            for layer in group.layers:
                if layer.name == name:
                    return layer, group
        layer = self._laycfg.getLayerByName(name)

        if layer != None:
            return layer, None
        else:
            raise ValueError("Layer %s not found"%name)

    @property
    def layers(self):
        return self._laycfg.layers

    def addLayer(self, layer, layerstyle = DetailMapLayerStyle()):
        self._laycfg.addLayer(layer, layerstyle = layerstyle)
        return layer

    def addPOIGroupAndLayer(self):
        if self.mode == 'r':
            raise ValueError("Can't add POI layer in read-only mode")

        if self._poigroup == None:
            # Create POI config file
            self.poicfg = ConfigParserUpper()

            self._cfg.set("POI","POI_CONFIG", self.mapnumstr + "poi.cfg")

            # Create POI group
            poigroup = POIGroup(self)
            poigroup.open('w')

            self._poigroup = poigroup

            # Create POI Layer
            layer=Layer(self, "poi", "poi", layertype=LayerTypePOI,
                        fileidentifier=0xc0f0)
            layer.open('w')

            self._poiconfig.addLayer(layer, layerstyle=POILayerStyle())

    def getDB(self):
        return self._db

    def getPOIGroup(self):
        return self._poigroup

    def getPOILayers(self):
        return self._poiconfig.layers

    def writeToMapDir(self, mapdir):
        mapdir.copyfrom(self.mapdir)
        
    def writeImage(self, filename):
        image = mapdir.Image(filename, mode='w', bigendian=self.bigendian)
        self.writeToMapDir(image)
        return image

    def addRoutingLayer(self, layer, routingsetnumber, direction = 'N', speed = (1, 1)):
        if self.maptype != MapTypeStreetRoute:
            raise ValueError('Map is not of type street route')
        self.routingcfg.addRoutingLayer(self, layer, routingsetnumber, direction = 'N', speed = (1, 1))
       
    def _updatecfg(self):
        """Update cfg data"""

        ## Map info
        self._cfg.set('MAP_INFO', 'VERSION', str(self.formatversion))
        if self.bigendian:
            byteorder = 'M'
        else:
            byteorder = 'I'
        self._cfg.set('MAP_INFO', 'BYTE_ORDER', byteorder)
        self._cfg.set('MAP_INFO', 'IS_ADD', str(0))
        self._cfg.set('MAP_INFO', 'MAP_NAME', self.name)
        self._cfg.set('MAP_INFO', 'START_SCALE', str(self._startscale))

        ## Color 4 bits
        self._cfg.set('COLORS4BITS', 'LAY_COLOR', str(self._laycolor))

        ## Write groups
        self._cfg.set('GROUPS','NUMBER',str(len(self.groups)))
        for group in self.groups:
            group.updateIni(self._cfg)
        self._cfg.set('GROUPS', 'SEARCH_GROUPS', encodeintlist([i for i,g in enumerate(self.groups) if g.searchable]))
            
        ## Write tables
        if self.has_zip:
            self._cfg.set('TABLES','ZIP_TABLE', ' '.join(map(str, self._ziptables)))
        else:
            self._cfg.set('TABLES','ZIP_TABLE', '-1')
        if self.has_marine:
            self._cfg.set('TABLES','MARINE_TABLE', ' '.join(map(str, self._marinetables)))

        ## Write layers
        self._laycfg.writecfg(self._cfg, self)

        ## Write POI info
        if self._poigroup != None:
            self._poiconfig.writecfg(self.poicfg, self)
            self._cfg.set('LAYERS', 'POI_INDEX', str(len(self.groups)))
        else:
            self._cfg.set('POI','POI_CONFIG','')
            self._cfg.set('LAYERS', 'POI_INDEX', str(-1))

        if self._db:
            self._cfg.set('LAYERS', 'DB_NAME', self._db.name)
            
        if self.maptype:
            self._cfg.set('MAP_INFO', 'MAPTYPE', self.maptype)

        ## Write routing config
        if self.maptype == MapTypeStreetRoute:
            self.routingcfg.writecfg(self._cfg, self)

        # Write bounding box and bounding rectangle
        bboxrec = self.bboxrec
        if bboxrec:
            self._cfg.set('MAP_INFO', 'BND_BOX', " ".join(map(str,[bboxrec.c1[0],bboxrec.c2[0],-bboxrec.c1[1],-bboxrec.c2[1]])) )
        if self._boundrec:
            self._cfg.set('LIMITRECTANGLE', 'BOUNDRECT', " ".join(map(str,[self._boundrec.c1[0],self._boundrec.c2[0],
                                                                           self._boundrec.c1[1],self._boundrec.c2[1]])) )
        
        ## Copyright holders
        for i,layer in enumerate(self._copyrightholders):
            self._cfg.set('COPYRIGHT', str(i+1), layer)

    def _initcfg(self):
        """Populate the ini file"""
        self._cfg.add_section('MAP_INFO')
        self._cfg.add_section('GROUPS')
        self._cfg.add_section('LAYERS')
        self._cfg.add_section('TABLES')
        self._cfg.add_section('POI')
        self._cfg.add_section('LIMITRECTANGLE')
        self._cfg.add_section('COPYRIGHT')
        self._cfg.add_section('COLORS4BITS')

    @property
    def mapnumstr(self):
        return '%02d'%self._mapnumber

    @property
    def inifilename(self):
        return self._inifile

    def __del__(self):
        self.close()

class MapImage(object):
    """Map image suitable for use with a Magellan GPS. A MapImage object may contain several maps (Map objects).

    >>> mi = MapImage("./test/images/canarias.imi")
    >>> mi.open()
    >>> len(mi.maps)
    1

    """
    def __init__(self, filename = None, mapdirobj = None, bigendian = False, maps = []):
        self._filename = filename

        if mapdirobj != None and not isinstance(mapdirobj, mapdir.MapDirectory):
            raise ValueError("mapdirobj should be a MapDirectory object")

        self.mapdir = mapdirobj
            

        self._maps = list(maps)
        self._bigendian = bigendian

        self._topo = None

        self.mode = None

    @property
    def topo(self): return self._topo
    
    def addTopo(self, blxfile):
        if self._topo == None:
            self._topo = Topo(self.mapdir)
        self._topo.addblx(blxfile, bigendian=self._bigendian)

    def createMap(self, *args, **kvargs):
        """Create a new map and return the new Map object"""

        if self.mode in ('a', 'w'):
            m = Map(self.mapdir, mapnumber = len(self._maps), bigendian=self._bigendian, **kvargs)
            m.open('w')
            self._maps.append(m)
            return self._maps[-1]

    @property
    def maps(self):
        return tuple(self._maps)

    def open(self, mode='r'):
        self.mode = mode

        if self.mapdir == None:
            self.mapdir = mapdir.Image(self._filename, mode = mode)

        if mode == 'w':
            ## Copy data files
            for file in ["bmp2bit.ics", "bmp4bit.ics"]:
                self.mapdir.copyfile(os.path.join(datadir, file))

        elif mode in ('r', 'a'):
            addmapscfg = self.mapdir.open('add_maps.cfg')
            columns = re.split('\s+', addmapscfg.readline())

            n = int(columns[0])

            for inifile in columns[1:n+1]:
                m = Map(self.mapdir, bigendian=self._bigendian, inifile=inifile)
                m.open(mode)
                self._maps.append(m)

    def writeconfig(self):
        ## Create add_maps.cfg
        addmapscfg = self.mapdir.open('add_maps.cfg', 'w')
        addmapscfg.write(cfg_writelist([m.inifilename for m in self._maps]) + '\n')
        addmapscfg.close()

    def close(self):
        self.writeconfig()
        
        ## Close maps
        for m in self._maps:
            m.close()

        ## Write topo
        if self._topo:
            self._topo.write()

        ## Write image
        self.mapdir.write()

if __name__ == "__main__":
    import doctest
    doctest.testmod()

