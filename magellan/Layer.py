import struct
import string
import ConfigParser
import re
import DBUtil
import copy
import os
import tempfile
import shutil
import numpy as N
from itertools import izip
import shelve
import logging

from Cell import CellInMemory, CellShelve, CellCommonShelve
from CellElement import Rec
from lrucache import LRUCache
from sets import Set
from rsttable import toRSTtable

import layerpacker

LayerTypePoint = 0xb
LayerTypePolygon = 0xc
LayerTypePolyline = 0xd
LayerTypeLabel = 0xf
LayerTypePOI = 0x10
LayerTypeRouting = 0x11

zoomlevels = [	50, 120, 250, 500, 1000, 2000, 4000, 8000, 16000, 30000,
                60000, 120000, 250000, 500000, 1000000, 2000000, 4000000 ]

bwcolors = [ 'BLACK', 'WHITE', 'DARK_GRAY', 'LIGHT_GRAY', 'GRAY' ]
colors = bwcolors + ['CYAN', 'RED', 'ORANGE', 'BLUE', 'GREEN', 'PAIL_GREEN', 'PAIL_YELLOW', 'YELLOW', 'DARK_RED', 'MAGENTA', 'BROWN', 'DARK_BLUE' ]

linestyles = [ 'US_INTERSTATE_HW_LINE', 'US_STATE_HW_LINE', 'US_STREET_LINE', 'US_RAIL_ROAD',
               'SINGLE_LINE', 'US_STREET_LINE', 'MSOLID_LINE','MDOT_LINE', 'MDASH_LINE', 
               'THICK_LINE', 'TRAIL_LINE', 'THICK_DASH_LINE', 'US_FEDERAL_HW_LINE', 
               'US_MAJOR_RD_LINE', 'DOT_LINE', 'STREAM_LINE', 'RIVER_LINE', 'DASH_LINE', 
               'US_UNPAVED_RD_LINE', 'US_RR_LINE', 'MCOMBO_LINE', 'MDEPTH_LINE']
pointstyles = ['NOTHING_POINT', 'SMALL_CITIES',
               'MEDIUM_CITIES', 'MAJOR_CITIES', 'LARGE_CITIES', 'AIRPORTS', 'TRAIN_STATION', 
               'BUS_STATION', 'FERRY_TERM', 'SMALL9', 'B11ARIAL', 'ARIAL11', 'LIGHT_HOUSE',
               'MCOMBO_POINT', 'MSOUNDING_POINT', 'MANNOT_POINT', 'FIXED_NAV_AID', 'FLOAT_BUOY'
               ]
fillstyles = ['SOLID_FILL', 'BOX_PATT', 'DOT_FILL', 'DASH_FILL', 'NO_FILL', 'SLANT_PATT', 'HEX_PATT', 'MCOMBO_AREA', 
              'MDEPTH_AREA' ]

styles = linestyles + pointstyles + fillstyles

LayerPurposeNormal = 20
LayerPurposeRoutingEdge = 2000
LayerPurposeTOD = 200
        
class LayerStyle(object):
    """
    LayerStyle holds information about how a layer is displayed

    >>> ls = LayerStyle()
    >>> ls.inistr
    '0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 BLACK US_INTERSTATE_HW_LINE'
    >>> ls = LayerStyle('00_Freeways 00fwy 20 1 0 0 7 0 7 0 5 0 6 0 6 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 BLACK US_INTERSTATE_HW_LINE')
    >>> ls 
    >>> ls.inistr
    '0 7 0 7 0 5 0 6 0 6 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 0 5 BLACK US_INTERSTATE_HW_LINE'
    >>> ls = LayerStyle('00_Masas_de_Agua 00lay0 20 1 4 0 15 0 15 0 0 0 4 0 4 0 0 0 3 0 3 0 0 0 2 0 2 0 0 0 1 0 1 0 0  CYAN  SOLID_FILL')

    The visiblerange, labelrange and hidebasemaprange defines zoomlevel ranges for layer visibility, label visibility and basemap visibility respectively.
    There are 5 elements that corresponds to different detail levels (lowest, low, medium, high, highest)

    """
    visiblerange = [(0,0),(0,0),(0,0),(0,0),(0,0)]
    labelrange = [(0,0),(0,0),(0,0),(0,0),(0,0)]
    hidebasemaprange = [(0,0),(0,0),(0,0),(0,0),(0,0)]
    color = 'BLACK'
    validcolors = colors
    visible = True
    purpose = LayerPurposeNormal
    
    _style = 'US_INTERSTATE_HW_LINE'
    def __init__(self, layerinfostr=None, style=None, color=None):
        if layerinfostr:
            fields = re.split('\s+', layerinfostr)
            name = fields[0]
            filename = fields[1]

            if len(fields) > 2:
                unk1, unk2, groupindex = map(int, fields[2:5])
                fields = fields[5:]

                self.visiblerange=[]
                self.labelrange=[]
                self.hidebasemaprange=[]
                for zoomlevel in range(5):
                    self.visiblerange.append((int(fields[0]), int(fields[1])))
                    self.labelrange.append((int(fields[2]), int(fields[3])))
                    self.hidebasemaprange.append((int(fields[4]), int(fields[5])))
                    fields = fields[6:]

                self.color = fields[0]

                if self.color not in self.validcolors:
                    raise ValueError('Invalid color '+self.color)

                self._style = fields[1]
                if self._style not in styles:
                    raise ValueError('Invalid style '+self._style)

        else:
            if style:
                self._style = style
            if color:
                self.color = color

    @property
    def inistr(self):
        fields = []
        for zoomlevel in range(5):
            fields += [str(x) for x in self.visiblerange[zoomlevel]+self.labelrange[zoomlevel]+
                       self.hidebasemaprange[zoomlevel]]
        fields.append(self.color)
        fields.append(self._style)
        return ' '.join(fields)

    def setvisibilitystr(self, s):
        fields = re.split('\s+', s)

        self.visiblerange=[]
        self.labelrange=[]
        self.hidebasemaprange=[]
        for zoomlevel in range(5):
            self.visiblerange.append((int(fields[0]), int(fields[1])))
            self.labelrange.append((int(fields[2]), int(fields[3])))
            self.hidebasemaprange.append((int(fields[4]), int(fields[5])))
            fields = fields[6:]
    
    def setStyle(self, style):
        self._style = style
    def getStyle(self):
        return self._style

    def verify(self, layername, map):
        """Check consistency of layer style"""

        try:
            layer, group = map.getLayerAndGroupByName(layername)
        except:
            return

        if layer == None:
            raise Exception("Layer %s is not present in map"%self.name)

        for detaillevel in range(5):
            if len(self.visiblerange) > 5 or len(self.labelrange) > 5 or len(self.hidebasemaprange) > 5:
                raise Exception("The number of detail levels must be 5")
            for interval in (self.visiblerange[detaillevel], self.labelrange[detaillevel], self.hidebasemaprange[detaillevel]):
                if interval[0] > interval[1]:
                    raise Exception('Range should be given as (min,max)')
                for zoomlevel in interval:
                    zoomlevels[zoomlevel]

        if self.color not in colors:
            raise Exception("Illegal color: %s"%self.color)

        if self.style not in styles:
            raise Exception("Illegal style: %s"%self.style)

        if layer.layertype == LayerTypePolyline and self.style not in linestyles:
            raise Exception('style %s is not a line style'%self.style)
        if layer.layertype == LayerTypePoint and self.style not in pointstyles:
            raise Exception('style %s is not a point style'%self.style)
        if layer.layertype == LayerTypePolygon and self.style not in fillstyles:
            raise Exception('style %s is not a fill style'%self.style)

    style = property(getStyle, setStyle, doc='style')

    def __str__(self):
        def visrange(range):
            return str([zoomlevels[x] for x in range])
        s = ''

        data = []
        for detaillevel in range(5):
            row = []
            row.append(detaillevel)
            row.append(visrange(self.visiblerange[detaillevel]))
            row.append(visrange(self.labelrange[detaillevel]))
            row.append(visrange(self.hidebasemaprange[detaillevel]))
            data.append(row)
        s += toRSTtable([['Detail level', 'Visible range', 'Label visible range', 'Hide basemap range']]+data)
        return s

class RoutingLayerStyle(LayerStyle):
    purpose = LayerPurposeRoutingEdge
    visible = False

class DetailMapLayerStyle(LayerStyle):
    visiblerange = [(0,7),(0,6),(0,5),(0,5),(0,5)]
    labelrange = [(0,7),(0,6),(0,5),(0,5),(0,5)]
    hidebasemaprange = [(0,5),(0,5),(0,5),(0,5),(0,5)]


class LayerConfig(object):
    """Class that holds rendering information about a list of layers"""
    def __init__(self):
        self._layers = []     # List of layers
        self._layerstyle = {} # Dictionary that associate a list with layer drawing style to layer numbers

    @property
    def layers(self):
        return tuple(self._layers)

    def addLayer(self, layer, layerstyle=DetailMapLayerStyle()):
        laynum = len(self._layers)
        self._layers.append(layer)
        self._layerstyle[laynum] = layerstyle

    def getLayerNames(self):
        return [layer.getName() for layer in self._layers]

    def getLayerStyleByName(self, name):
        return self._layerstyle[self.getLayerIndex(self.getLayerByName(name))]

    def getLayerByName(self, name):
        for layer in self._layers:
            if layer.name == name:
                return layer

    def getLayerByIndex(self, index):
        return self._layers[index]

    def getLayerStyleByIndex(self, index):
        return self._layerstyle[index]

    def getLayerIndex(self, layer):
        return self._layers.index(layer)
    
    def setupfromcfg(self, cfg, map):
        """Read layer table from LAYER section in config file"""
        for i in range(0, cfg.getint("LAYERS","NUMBER")):
            values = string.split(cfg.get('LAYERS',str(i)), ' ')
            (lname,lfilename) = values[0:2]
            self._layerstyle[i] = LayerStyle(cfg.get('LAYERS',str(i)))
            lfilename = lfilename.lower()
            self._layers.append(Layer(map,lname,lfilename))

        ## Iterate over draw order list and write draw order priority to layer objects
        orderdraw = cfg.get('LAYERS','ORDERDRAW').split(" ")
        for i, layerindex in enumerate(orderdraw):
            self._layers[int(layerindex)].draworder = len(orderdraw) - i

    def getLayerAndGroupByName(self, name, map):
        return map.getLayerAndGroupByName(name)
            
    def writecfg(self, cfg, mapobj):
        ## Write layers
        if not cfg.has_section('LAYERS'):
            cfg.add_section('LAYERS')
        cfg.set('LAYERS','NUMBER',str(len(self._layers)))
        for i,layer in enumerate(self._layers):
 
            ## Get group index (not correct for base maps)
            layer, group = self.getLayerAndGroupByName(layer.name, mapobj)

            if group != None:
                groupindex = mapobj.getGroupIndex(group)
            else:
                groupindex = -1
            
            out=[layer.getName(), layer.getFileName(), str(self._layerstyle[i].purpose),
                 str(int(self._layerstyle[i].visible)), str(groupindex)]

            if self._layerstyle.has_key(i):
                out.append(self._layerstyle[i].inistr)
            cfg.set('LAYERS',str(i)," ".join(out))

        # Layer draw order
        draworder = range(len(self._layers))
        draworder.sort(lambda x,y: cmp(self._layers[y].draworder, self._layers[x].draworder))
        cfg.set('LAYERS', 'ORDERDRAW', " ".join(map(str, draworder)))

    @property
    def bboxrec(self):
        bboxrec = None
        for layer in self._layers:
            if bboxrec == None:
                bboxrec = layer.bboxrec
            else:
                bboxrec = bboxrec.union(layer.bboxrec)
        return bboxrec

    def close(self):
        for layer in self._layers:
            layer.close()
            del layer

        self._layers = []


class Layer(object):
    """
    Class Layer

     Description:

     Constructors:
              Layer(map, layername)

     Methods:
              IO operations
              --------------
              open(mode)                Opens a MapSend layer filepair
                                        .lay/.clt for read (mode='r') or
                                        write (mode='w').
              close()                   Closes an opened MapSend layer filepair

              read()                    Read index file and header of layer file

              write(outlayername)       Read contents of layer that is opened for
                                        read and write a copy of the layer to
                                        layer name outlayername.


    """
    def __init__(self, m, name, filename, layertype=None, nlevels=0,
                 fileidentifier=None):
        self.map = m

        ## Copy resolution and reference point from map
        self._scale = m.scale                           # [xscale, yscale]
        self._refpoint = m.refpoint                     # Reference point for conversion to discrete coordinates

        if m.bboxrec:
            self._dbbox = m.bboxrec.negY().todiscrete(self._refpoint, self._scale)
            self._bbox = self._dbbox.tocontinous(self._refpoint, self._scale)
            self.estimator = None
        else:
            self._bbox = None
            self._dbbox = None

            ## Create layer parameter estimator object
            self.estimator = LayerParamEstimator(self)

        if filename[0:len(m.mapnumstr)] != m.mapnumstr:
            filename = m.mapnumstr + filename

        if len(filename) > 8:
            raise Exception('Length of filename %s must not exceed 8'%filename)

        self.name = name
        self.filename = filename
        self.cellelementid = 0
        self.isopen = False

        self.clearCells()

        self.mode = None
        self.bigendian = m.bigendian
        self.writedrc = False         # Write DRC file needed by mapsend software

        self.nlevels = nlevels # Cell levels
        self.nobjects = 0
        self.category = 0 # 0=Normal layer, 1=Artificial layer
        self.fileidentifier = fileidentifier
        self.layertype = layertype

        ## Statistics from header
        self.firstcell = None
        self.lastcell = None

        ## Cell position in layer file (for use in read mode)
        self.cellfilepos = {}                          
        
        self.fhlay = None

        self.draworder = 0

        self.packed = False
        self.packer = None

    def __eq__(self, a):
        return isinstance(a, Layer) and self.name == a.name
    
    def __hash__(self):
        return hash(self.name)

    def clearCells(self):
        self.modifiedcells = {}        # Dictionary of modified cells keyed by cellnumber
        self.cellcache = LRUCache(size=32)
        self.cellfilepos = {}
        self.cellnumbers = []

    def setUnpackTable(self, filename):
        self.packed = True
        self.packer = layerpacker.LayerPacker(self.map.mapdir.open(filename).read())

    def open(self, mode):
        self.mode = mode
        if not self.isopen:
            if mode=='r' or mode=='a':
                try:
                    # First try open the layer as little endian
                    self.layerfilename = self.filename+".lay"
                    self.indexfilename = self.filename+".clt"
                    self.fhlay = self.map.mapdir.open(self.layerfilename,"r")
                    self.bigendian = False
                except IOError:
                    self.layerfilename = self.filename+".yal"
                    self.indexfilename = self.filename+".tlc"
                    self.fhlay = self.map.mapdir.open(self.layerfilename,"r")
                    self.bigendian = True
            elif mode=='w':
                if not self.bigendian:
                    self.layerfilename = self.filename+".lay"
                    self.indexfilename = self.filename+".clt"
                else:
                    self.layerfilename = self.filename+".yal"
                    self.indexfilename = self.filename+".tlc"
                self.fhlay = self.map.mapdir.open(self.layerfilename, "wb")

                if not self.map.inmemory:
                    self.shelffile = tempfile.mktemp()
                    self.shelf = shelve.open(self.shelffile)

            isopen=True

            if self.mode in ('r','a'):
                self.read_index()
                self.read_header()

    def optimize(self):
        """Optimize nlevels parameter and calculate bounding box

        This function only works when the cell is opened in write only mode
        without bounding box.

        The function works like this. A proper value for the nlevel parameter and a bounding box
        are first estimated.
        At the beginning there is only one cell but with the new nlevel value the number of cells
        may grow. Hence the cell elements might have to be placed in new cells.

        Returns a dictionary of mapping between old and new cellreferences
        
        """
        if self.mode == 'w' and self._bbox == None:
            remapdict = {}

            logging.debug("Optimizing layer "+self.name)

            dbboxrec = self.estimator.calculateDBBox()
            if dbboxrec:
                self.dbboxrec = dbboxrec

            ## Get nlevels estimate
            self.nlevels = self.estimator.calculateNlevels()

            ## Update the bounding box of cell 1
            self.getCell(1).setbbox()

            if self.nlevels > 0:
                cellelements = []
                cellelementrefs = []

                oldcell1 = self.getCell(1)

                self.clearCells()

                ## Loop over the elements in the old cell 1 
                ## The elements need to be accessed in reversed order, otherwise the cellelement numbers would change
                ## during the loop
                for i in range(len(oldcell1)-1,-1,-1):
                    ce = oldcell1.pop(i)
                    newcellrefs = self.addCellElement(ce)
                    remapdict[(oldcell1.cellnum, i)] = newcellrefs[0]

            return remapdict
        else:
            return {}

    def close(self):
        if (self.mode=='w') or (self.mode=='a') and len(self.modifiedcells)>0:

            ## Use estimator to calculate bounding box
            if self._bbox == None:
                self.optimize()
            
            tmplay = tempfile.NamedTemporaryFile('w')

            self.write_header(tmplay)

            ## The cells must be written in cell number order
            self.cellnumbers.sort()

            # Merge unchanged cells with modified cells
            for cellnum in self.cellnumbers:
                if cellnum in self.modifiedcells:
                    cell = self.modifiedcells[cellnum]
                    celldata = cell.serialize()
                    # Update index
                    self.cellfilepos[cellnum] = [tmplay.tell(), len(celldata)]
                    tmplay.write(celldata)
                else:
                    self.fhlay.seek(self.cellfilepos[cellnum][0])
                    celldata = self.fhlay.read(self.cellfilepos[cellnum][1])
                    self.cellfilepos[cellnum][0] = tmplay.tell()
                    tmplay.write(celldata)

            # Rewind and write the header again with the new cell index statistics
            tmplay.seek(0)
            self.write_header(tmplay)

            tmplay.flush()

            tmplay.seek(0) # This is needed in Windows as reported by ludwigmb
            shutil.copyfileobj(tmplay, self.fhlay)

            self.fhlay.close()

            # Create index file
            fhidx = self.map.mapdir.open(self.indexfilename,"wb")
            fhdrc = None
            if self.writedrc:
                fhdrc = self.map.mapdir.open(self.filename+".drc", "wb")

            if fhdrc:
                fhdrc.write( self.pack("I", len(self.cellnumbers)))


            for cellnum in self.cellnumbers:
                fhidx.write( self.pack("III", cellnum, self.cellfilepos[cellnum][0], self.cellfilepos[cellnum][1]) )
                if fhdrc:
                    fhdrc.write( self.pack("III", cellnum, self.cellfilepos[cellnum][0], self.cellfilepos[cellnum][1]) )
                
            fhidx.close()
            if fhdrc:
                fhdrc.close()
            
            self.fhlay.close()

        if self.mode == 'w' and not self.map.inmemory:
            os.unlink(self.shelffile)
        
        isopen=False

    def read_index(self):
        if self.mode in ['r','a']:
            fhidx = self.map.mapdir.open(self.indexfilename, "r")

            self.cellfilepos = {}
            self.cellnumbers = []
            while 1:
                data = fhidx.read(12)

                if len(data) == 0: break

                [cellnum,offset,cellsize] = self.unpack("3i",data)
                self.cellfilepos[cellnum] = [offset,cellsize]
                self.cellnumbers.append(cellnum)

    def read_header(self):
        self.dheader = self.fhlay.read(0x80)

        [self.category] = self.unpack("i", self.dheader[4:])
        [self.fileidentifier] = self.unpack("H", self.dheader[8:])

        tmp = self.unpack("4f", self.dheader[0xa:])
        self._bbox = Rec(N.array([tmp[0],tmp[2]]), 
                         N.array([tmp[1],tmp[3]]))

        [self.nlevels] = self.unpack("h", self.dheader[0x1a:])
        [self.nobjects] = self.unpack("i", self.dheader[0x1c:])

        [xscale] = self.unpack("d", self.dheader[0x20:])
        [yscale] = self.unpack("d", self.dheader[0x28:])

        self._scale = N.array([xscale, yscale])

        self._refpoint = N.array(self.unpack("2f", self.dheader[0x30:]))

        tmp = self.unpack("4i", self.dheader[0x38:])
        self._dbbox = Rec(N.array([tmp[0],tmp[1]]), 
                          N.array([tmp[2],tmp[3]]))

        [self.layertype] = self.unpack("b", self.dheader[0x48:])
        [unknown49] = self.unpack("b", self.dheader[0x49:])
        [self.largestcellsize] = self.unpack("i", self.dheader[0x4a:])
        [self.firstcell] = self.unpack("i", self.dheader[0x4e:])
        [self.lastcell] = self.unpack("i", self.dheader[0x52:])

        assert(unknown49, 0)

    def write_header(self, fh):
        header = "MHGO"
        header = header + self.pack("i", self.category)
        if self.fileidentifier == None:
            fileidentifier = 0xc000 | self.map.getLayerIndex(self)
        else:
            fileidentifier = self.fileidentifier

        header = header + self.pack("H", fileidentifier)

        header = header + self.pack("4f", self._bbox.minX(), self._bbox.maxX(),
                                    self._bbox.minY(), self._bbox.maxY())
        header = header + self.pack("h", self.nlevels)
        header = header + self.pack("i", self.nobjects)
        header = header + self.pack("d", self._scale[0])
        header = header + self.pack("d", self._scale[1])
        header = header + self.pack("f", self._refpoint[0])
        header = header + self.pack("f", self._refpoint[1])
        header = header + self.pack("4i", self._dbbox.minX(), self._dbbox.minY(), self._dbbox.maxX(), self._dbbox.maxY())

        header = header + self.pack("b", self.layertype)
        header = header + self.pack("b", 0)

        if len(self.cellfilepos)>0:
            largestcellsize = max([d[1] for d in self.cellfilepos.values()])
        else:
            largestcellsize = 0
        header = header + self.pack("i", largestcellsize)

        if len(self.cellnumbers) == 0:
            header = header + self.pack("i", 0) # First cell number
            header = header + self.pack("i", 0) # Last cell number
        else:
            header = header + self.pack("i", self.cellnumbers[0]) # First cell number
            header = header + self.pack("i", self.cellnumbers[-1]) # Last cell number
        
        header = header + chr(0)*(128-len(header))
                                    
        fh.write(header)
        return len(header)

    def unpack(self,types,data):
        if self.bigendian:
            prefix=">"
        else:
            prefix="<"
        return struct.unpack(prefix + types,
                             data[0:struct.calcsize(prefix+types)])

    def pack(self, types, *data):
        if self.bigendian:
            prefix=">"
        else:
            prefix="<"
        return struct.pack(prefix+types, *data)

    def markCellModified(self, cellnum):
        self.modifiedcells[cellnum] = self.getCell(cellnum)

    def getCells(self):
        for cn in self.cellnumbers:
            yield self.getCell(cn)
    
    def getCell(self, cellnum):
        if cellnum in self.modifiedcells:
            return self.modifiedcells[cellnum]
        
        if cellnum in self.cellcache:
            return self.cellcache[cellnum]

        # New cell
        if self.mode == 'w':
            if self.map.inmemory:
                cell = CellInMemory(self, cellnum)
            elif self.nlevels == 0:
                cell = CellShelve(self, cellnum)
            else:
                cell = CellCommonShelve(self, cellnum, self.shelf)
        else:
            cell = CellInMemory(self, cellnum)

        # Deserialize cell if present in the cell index
        if cellnum in self.cellfilepos:
            self.fhlay.seek(self.cellfilepos[cellnum][0])
            celldata = self.fhlay.read(self.cellfilepos[cellnum][1])

            if self.packed:
                celldata = self.packer.unpack(celldata)
            
            cell.deSerialize(celldata)
        
        self.cellcache[cellnum] = cell

        return cell

    def close_cell(self, cellnum):
        self.cellcache.pop(cellnum)

    def getCellElements(self):
        for c in self.getCells():
            for s in c.getCellElements():
                yield s
	
    def getCellElementsAndRefs(self):
        for c in self.getCells():
            for nincell, s in enumerate(c.getCellElements()):
                yield (s, (c.cellnum, nincell))
	
    def getCellElement(self, cellref):
        """Get cell element from a (cellnum, num_in_cell) pair """
        (cellnum, num_in_cell) = cellref
        
        if self.map.debug:
            print "Cellcache: "+str(self.cellcache.keys())
        cell = self.getCell(cellnum)
        try:
            cellelement = cell.getCellElement(num_in_cell)
        except IndexError:
            raise IndexError,"num_in_cell (%d) is outside the # of cellelements (%d) in cell %d, layer %s"%(num_in_cell,len(cell),cellnum, self.name)

        return cellelement
	
    def addCellElement(self, cellelem, cellnum = None):
        """Add cell element to layer. The element might be divided into smaller elements.
         Returns list of (cellnum,# in cell) pairs"""
        
        if self.mode in ('r', None):
            raise ValueError('Layer must be opened in write or append mode to add cell elements')

        if self._bbox != None:
            if cellnum == None:
                cellnum = max_cellno_containing_bbox(self._bbox,
                                                     cellelem.bboxrec(self).negY(),
                                                     self.nlevels)

#            assert cellelem.bboxrec(self).iscoveredby(self.bboxrec(self), xmargin=self._scale[0], ymargin=self._scale[1]), "CellElement is outside layer boundaries:" + \
#                   str(self.bboxrec(self)) + " cellelement:" + str(cellelem.bboxrec(self))
        else:
            if self.nlevels > 0:
                raise ValueError('Cannot add cell element to layer with nlevels>0 and no bounding box')
            cellnum = 1

            self.estimator.addCellElement(cellelem)
            
        cellelem.cellnum = cellnum
        
        cell = self.getCell(cellnum)

        # Check that cell element is contained by cell
        #assert cellelem.bboxrec(self).iscoveredby(cell.bboxrec(self), xmargin=self._scale[0], ymargin=self._scale[1])
        
        nincell = cell.addCellElement(cellelem)
        
        assert nincell < 2**16
        
        if not cell in self.modifiedcells:
            self.modifiedcells[cellnum] = cell
        if not cellnum in self.cellnumbers:
            self.cellnumbers.append(cellnum)

        self.nobjects += 1

        return [(cellnum, nincell)]

    def updateCellElement(self, cellelementref, cellelement):
        """the updateCellElement must be called when a cell element has been updated"""
        self.getCell(cellelementref[0]).updateElement(cellelementref[1], cellelement)

    def getName(self):
        return self.name

    def getFileName(self):
        return self.filename

    def getNObjects(self):
        return self.nobjects

    ## Bounding box property
    def get_bboxrec(self):
        if self._bbox:
            return self._bbox.negY()
        else:
            return None
    def set_bboxrec(self, rec):
        if self.mode == 'r':
            raise ValueError("Can't change boundary rectangle in read-only mode")

        rec = rec.negY()
        
        self._dbbox = rec.todiscrete(self._refpoint, self._scale)
        self._bbox = self._dbbox.tocontinous(self._refpoint, self._scale)

        # If in append mode all cell elements must be re-added to fit the new
        # cell boundaries
        if self.mode == 'a':
            cellelements = [e for e in self.getCellElements()]
            
            self.clearCells()

            for e in cellelements:
                self.addCellElement(e)            

    bboxrec = property(get_bboxrec, set_bboxrec, "Bounding box rectangle")

    def get_dbboxrec(self):
        if self._dbbox:
            return self._dbbox
        else:
            return None
    def set_dbboxrec(self, drec):
        if self.mode == 'r':
            raise ValueError("Can't change boundary rectangle in read-only mode")

        self._dbbox = drec.negY()
        self._bbox = self._dbbox.tocontinous(self._refpoint, self._scale)

        # If in append mode all cell elements must be re-added to fit the new
        # cell boundaries
        if self.mode == 'a':
            cellelements = [e for e in self.getCellElements()]
            
            self.clearCells()

            for e in cellelements:
                self.addCellElement(e)            

    dbboxrec = property(get_dbboxrec, set_dbboxrec, "Bounding box rectangle discrete coordinates")

    @property
    def refpoint(self): return self._refpoint
    @property
    def scale(self): return self._scale

    def getLayerType(self): return self.layertype    

    def calc_cell_extents(self, cellnum): 
        """
        Calculate discrete bounding box of a cell

        Note, the extents return is in the internal coordinates with negated Y-values
        """

        ## Calculate cell level
        level=0
        while cellnum > totcells_at_level(level):
           level=level+1

        n = 2**level             # Number of rows/cols 

        lbb = self._dbbox
        layerwidth = lbb.width
        layerheight = lbb.height
        layersize = N.array([layerwidth, layerheight])

        relcnum = cellnum - (totcells_at_level(level-1)+1)

        cellsize = layersize / n

        if relcnum < n*n:
            mincorner = N.array([relcnum % n, relcnum / n]) * cellsize
            maxcorner = mincorner + cellsize
        else:
            relcnum = relcnum-n*n
            mincorner = N.array([relcnum % (n + 1), relcnum / (n + 1)]) * cellsize - cellsize/2
            maxcorner = mincorner + layersize / n

            mincorner[N.where(mincorner < 0)] = 0
            maxcorner[0] = min(maxcorner[0], layerwidth)
            maxcorner[1] = min(maxcorner[1], layerheight)

        return Rec(mincorner + lbb.c1, maxcorner + lbb.c1)

    def layer_header_nok(self, pcnt):
        """Header check from magsendtool"""
	
 	pcnt /= 100.0
        rc = 0
        if abs(((self._bbox.maxY() -self._bbox.minY())/self._scale[1]) - (self._dbbox.maxY() - self._dbbox.minY())) > pcnt * (self._dbbox.maxY() - self._dbbox.minY()):
            rc |= 1
        if abs(((self._bbox.maxX() -self._bbox.minX())/self._scale[0]) - (self._dbbox.maxX() - self._dbbox.minX())) > pcnt * (self._dbbox.maxX() - self._dbbox.minX()):
            rc |= 2
        if self._refpoint[1] != 0.0 and abs(self._bbox.centerY() - self._refpoint[1])/self._scale[1] > 0.75:
            rc |= 4
        if self._refpoint[0] != 0.0 and abs(self._bbox.centerX() - self._refpoint[0])/self._scale[0] > 0.75:
            rc |= 8
 	return rc


    def check(self):
        version=1
        if self.layer_header_nok(0.1):
            version+=1
            if self.layer_header_nok(1.0):
                version+=1
                if self.layer_header_nok(5.0):
                    raise ValueError('Incorrect layer format rc=%d at 5%% error'%self.layer_header_nok(5.0))
        return version

    @property
    def ncells(self):
        """Return the number of cells in the layer"""
        return len(self.cellnumbers)

    @property
    def info(self):
        res = "Name: "+self.getName()+"\n"
        res += "Number of objects: "+str(self.getNObjects())+"\n"
        res += "Number of cells: "+str(len(self.cellnumbers))+"\n"
        res += "Reference point: "+str(self._refpoint)+"\n"
        res += "Scale: "+str(self._scale)+"\n"
        res += "Boundaries: "+str(self._bbox)+"\n"
        res += "Discrete Boundaries: "+str(self._dbbox)+"\n"
        if self.fileidentifier:
            res += "Identifier: 0x%x\n"%self.fileidentifier
        res += "# of levels: %d\n"%self.nlevels
        res += "category: %d\n"%self.category
        if self.layertype != None:
            res += "layertype: %d\n"%self.layertype
        res += 'reflat: %f\n'%self._refpoint[1]
        res += 'reflon: %f\n'%self._refpoint[0]
        if self.firstcell:
            res += 'first cell: %d\n'%self.firstcell
        if self.lastcell:
            res += 'last cell: %d\n'%self.lastcell
        return res


    def float2discrete(self, points):
        """Convert list of coordinates from floating point to discrete coordinates"""
        return ((N.array(points) - self.refpoint) / self.scale).round().astype(int)

    def discrete2float(self, points):
        """Convert list of coordinates from discrete to floating point coordinates"""
        return N.array(points) * self.scale + self.refpoint
    
    def __repr__(self):
        return self.__class__.__name__ + '(' + self.getName() + ')'

class LayerParamEstimator(object):
    """Class that gather statistics and estimates parameters such as nlevels and bounding box"""
    maxcellelements = 2000
    maxcelldatasize = 100000
    maxnlevels = 10
    
    def __init__(self, layer):
        self.layer = layer
        self.data = []  ## List of cell element size estimates and bounding boxes 
                        ## stored as tuples (bbox, datasize) 

        self.verbose = False

        self.dbboxmin, self.dbboxmax = layer.float2discrete((N.array([180.0, 90.0]), N.array([-180.0, -90.0])))
        
    def addCellElement(self, cellelement):
        bbox = cellelement.dbboxrec

        self.dbboxmin = N.minimum(bbox.c1, self.dbboxmin)
        self.dbboxmax = N.maximum(bbox.c2, self.dbboxmax)
        
        self.data.append((bbox, cellelement.estimate_size()))

    def calculateNlevels(self):
        """Calculate number of cell levels"""

        ## Start at level zero
        ## Split size estimates into cells using a dictionary keyed by cell number
        sizeestimates = { 1: self.data }

        def checkcells(sizeestimates):
            """Return true if all cells are ok"""
            for cellnum, cellelementinfolist in sizeestimates.items():
                if len(cellelementinfolist) > self.maxcellelements:
                    logging.debug('Max cell elements exceeded for layer %s. cellnum=%d, # of cell elements=%d'%(self.layer.name, cellnum, len(cellelementinfolist)))
                    return False
                cellsize = 0
                for cellelementinfo in cellelementinfolist:
                    cellsize += cellelementinfo[1]

                if cellsize > self.maxcelldatasize:
                    if self.verbose:
                        logging.debug('Max cell data size exceeded. cellnum=%d, datasize=%d'%(cellnum, cellsize))
                    
                    return False
            return True
                    
        for nlevels in range(self.maxnlevels):
            if checkcells(sizeestimates):
                logging.debug('nlevels=%d for layer %s'%(nlevels, self.layer.name))
                return nlevels

            for cellnum, cellelementinfolist in sizeestimates.items():
                for i in xrange(len(cellelementinfolist)-1,-1,-1):
                    newcellnum = max_cellno_containing_bbox(self.layer._bbox, cellelementinfolist[i][0], nlevels)

                    ## If cell is updated move the item to the new cell
                    if newcellnum != cellnum:
                        cellelementinfo = cellelementinfolist.pop(i)
                        if newcellnum in sizeestimates:
                            sizeestimates[newcellnum].append(cellelementinfo)
                        else:
                            sizeestimates[newcellnum] = [cellelementinfo]

        raise Exception('Could not determine number of cell levels of layer'%self.layer.name +
                        ', try increasing maxnlevels' )


    def calculateDBBox(self):
        """Calculate estimated bounding box of layer in discrete coordinates"""
        if N.alltrue(self.dbboxmin == self.layer.float2discrete((N.array([180.0, 90.0]),))):
            return None

        dbbox = Rec(self.dbboxmin, self.dbboxmax)
         
        if self.verbose:
            print "Estimated discretebbox", dbbox
        
        return dbbox

###############################################################################
# Helper functions 


def max_cellno_containing_bbox(layerbbox, bbox, maxlevels):
    """Calculate the maximum cellnumber that contains the bbox.
    Note the bbox is assumed to have negated Y coordinates
    
    >>> max_cellno_containing_bbox(Rec((0,0),(1.0, 1.0)), Rec((0,0),(1.0, 1.0)), 2)
    1
    >>> max_cellno_containing_bbox(Rec((0,0),(1.0, 1.0)), Rec((0.8,0.8),(0.9,0.9)), 1)
    5
    >>> max_cellno_containing_bbox(Rec((0,0),(1.0, 1.0)), Rec((0.3, 0.3),(0.7,0.7)), 1)
    10
    >>> max_cellno_containing_bbox(Rec((0,0),(1.0, 1.0)), Rec((0.9, 0.9),(1.0,1.0)), 1)
    14
    >>> max_cellno_containing_bbox(Rec((0,0),(1.0, 1.0)), Rec((0.8,0.8),(0.9,0.9)), 2)
    30

    """
    bboxinc=bbox.translate(-layerbbox.c1)
    shifted = 0
    for n in range(maxlevels, -1, -1):
        cellw = layerbbox.width / (2**n)
        cellh = layerbbox.height / (2**n)
        if bboxinc.width > cellw or bboxinc.height > cellh:
            continue

        if (bboxinc.c2[0] % cellw) < (bboxinc.c1[0] % cellw) or \
           (bboxinc.c2[1] % cellh) < (bboxinc.c1[1] % cellh):
            bbt = bboxinc.translate(N.array([cellw/2, cellh/2]))
            if (bbt.c2[0] % cellw) < (bbt.c1[0] % cellw) or \
               (bbt.c2[1] % cellh) < (bbt.c1[1] % cellh):
                continue
            shifted = 1
        break

    col = (bboxinc.c1[0]+0.5*cellw*shifted) / cellw
    row = (bboxinc.c1[1]+0.5*cellh*shifted) / cellh

    col = max(int(col), 0)
    row = max(int(row), 0)

    cellnum = 1 + totcells_at_level(n-1) + \
              col + (2**n + shifted)*row + shifted * 4**n

    return cellnum

# Function totcells_at_level(n)
#
# Description:  Function that calculates the number of cells at level n
def totcells_at_level(n):
    if n>=0:
        # The function was simplified using Maple
        return (-17+2*4**(n+1)+6*2**(n+1)+3*n)/3
    else:
        return 0
    
FILTER=''.join([(len(repr(chr(x)))==3) and chr(x) or '.' for x in range(256)])

def dump(src, length=8):
    N=0; result=''
    while src:
       s,src = src[:length],src[length:]
       hexa = ' '.join(["%02X"%ord(x) for x in s])
       s = s.translate(FILTER)
       result += "%04X   %-*s   %s\n" % (N, length*3, hexa, s)
       N+=length
    return result

if __name__ == "__main__":
    import doctest
    doctest.testmod()
