import numpy as N
from misc import dump
import struct
from struct import pack
import wkt

def unpack(types, data):
    return struct.unpack(types,
                         data[0:struct.calcsize(types)])

bigendian2prefix = {True: '>', False: '<'}

# Class CellElement
#
# Description:
class CellElement(object):
    geometrytype = None
    typecode=0
    exportfields = ['cellnum', 'excessdump']

    ## Size estimation parameters
    kest = 1.3
    mest = 10.0

    def __init__(self, coords):
        self.cellnum = None
        self.excess = ""
        self._coords = coords
        
    def __eq__(self, x):
        return self.wkt ==  x.wkt
    def __hash__(self):
        return hash(self.wkt) ^ hash(self.excess)

    def istype(self,type):
        return type==typecode
    def deSerialize(self, cell, data, bigendian):
        return data
    def serialize(self, cell, bigendian):
        return None

    def estimate_size(self):
        """Estimate size of serialized data using a linear model"""
        return self.mest + self.kest * len(self.coords)

    @property
    def coords(self):
        return self._coords

    @property
    def bounds(self):
        """Return bounding box as minx,miny,maxx,maxy"""
        raise Exception('bounds is not implemented for class ' + self.__class__.__name__)
        
    @property
    def wkt(self):
        return wkt.precision_wkt(self, 5)

    @property
    def bboxrec(self):
        minx,miny,maxx,maxy = self.bounds
        return Rec(N.array([minx,miny]), N.array([maxx,maxy]))

    def discretizeGeometry(self, cell):
        if self.geometrytype=='LineString':
            vlist=[[p[0], -p[1]] for p in self._coords]
            vlist = cell.absToRelCoords(vlist)
            vlist = cell.relToAbsCoords(vlist)
            self._coords = tuple([(v[0],-v[1]) for v in vlist])
        elif self.geometrytype=='Point':
            [v]=cell.absToRelCoords([[self.x, -self.y]])
            [v]=cell.relToAbsCoords([v])
            self._coords = (v[0],-v[1])

    def setObjTypeIndex(self, objtypeindex):
        self.objtype = objtype

    @property
    def excessdump(self):
        return dump(self.excess)

    def __repr__(self):
        return self.__class__.__name__ + '(' + str(self._coords) + ')'

    def _deserialize_textslot(self, data, bigendian, onlyindex=False, last=True):
        prefix = bigendian2prefix[bigendian]
        
        if onlyindex:
            textslot = self.textslot
        else:
            textslot = unpack(prefix+"B", data)[0] << 24
            data = data[1:]

        if last:
            if len(data)==0:
                textslot = None
            elif len(data)==1:
                textslot |= ord(data[0])
            elif len(data)==2:
                textslot |= unpack(prefix+"H", data)[0]
            elif len(data)==3:
                textslot |= (unpack(prefix+"H", data)[0]<<8) | ord(data[2])
            else:
                raise ValueError("Excess data: "+str(data))
        else:
            if textslot == 0xfb000000:
                textslot = None
            elif textslot == 0xfc000000:
                textslot = unpack(prefix+"I",data)[0]
                data = data[4:]
            else:
                if len(data) >= 2:
                    textslot |= unpack(prefix+"H",data)[0]
                    data = data[2:]

        if textslot == 0xff000000:
            self.textslot = None
        else:
            self.textslot = textslot

        return data

    def _serialize_textslot(self, bigendian, onlyindex=False, last=True, allowbyteindex=False):
        """serialize a text slot

           If last is true the text slot is the final data in the cell element
        """
        prefix = bigendian2prefix[bigendian]
        
        if self.textslot == None:
            textslot = 0xff000000
        else:
            textslot = self.textslot

        data = ""
        if not onlyindex:
            data += pack(prefix+"B", textslot >> 24)

        if last:
            if allowbyteindex and (textslot & 0xffff00) == 0:
                data += chr(textslot&0xff)
            elif (textslot & 0xff0000) == 0:
                data += pack(prefix+"H", textslot & 0xffff)
            else:
                data += pack(prefix+"H", (textslot & 0xffff00)>>8)
                data += pack(prefix+"H", (textslot & 0xff))
        else:
            if textslot in [0xfb000000,0xfc000000] and (textslot & 0xff0000) != 0:
                data += pack(prefix+"I", textslot)
            elif textslot == 0xff000000:
                return ""
            else:
                data += pack(prefix+"H", textslot & 0xffff)
        return data

    def _serialize_textslotoffset(self, bigendian, last=True):
        prefix = bigendian2prefix[bigendian]
        
        if self.textslot == None:
            textslot = 0xff000000
        else:
            textslot = self.textslot

        if last:
            return pack(prefix+"B", textslot >> 24)
        else:
            if textslot in [0xfb000000,0xfc000000] or (textslot & 0xff0000) != 0:
                return chr(0xfc)
            elif textslot == 0xff000000:
                return chr(0xfb)
            else:
                return pack(prefix+"B", textslot >> 24)

    def _deserialize_bbox(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        # Extract bounding box extents (x,y coordinates and width,height)
        [bbprec] = unpack(prefix+"b",data)
        data = data[1:]

        bbox_x,data = self._decodecoord(bbprec & 0x3, data, bigendian)
        bbox_y,data = self._decodecoord((bbprec >> 2) & 0x3, data, bigendian)
        bbox_w,data = self._decodecoord((bbprec >> 4) & 0x3, data, bigendian)
        bbox_h,data = self._decodecoord((bbprec >> 6) & 0x3, data, bigendian)

        bbox = Rec(N.array([bbox_x,bbox_y]), \
                   N.array([bbox_x,bbox_y]) + N.array([bbox_w,bbox_h]))
        return bbox, data
    
    def _serialize_bbox(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        (minx,miny,maxx,maxy) = self.bounds
        # Negate sign of y-coordinate
        [c1,c2] = cell.absToRelCoords([[minx,-maxy],[maxx,-miny]])

        bbox = Rec(c1,c2)
        prec,data = self._encodecoord(bbox.c1[0], bigendian)

        tprec, tdata = self._encodecoord(bbox.c1[1], bigendian)
        prec = prec | (tprec << 2)
        data = data+tdata

        tprec, tdata = self._encodecoord(bbox.width, bigendian)
        prec = prec | (tprec << 4)
        data = data+tdata

        tprec, tdata = self._encodecoord(bbox.height, bigendian)
        prec = prec | (tprec << 6)
        data = data+tdata
        return pack(prefix+"B", prec) + data, bbox

    def _decodecoord(self, prec, data, bigendian):
        prefix = bigendian2prefix[bigendian]

        result=0

        dsizes=[4,2,1,0]
        refdatatype = [ "I", "H", "B", "" ]

        if prec < 3:
            [result] = unpack(prefix+refdatatype[prec], data)
            data = data[dsizes[prec]:]
        return result, data

    def _encodecoord(self, c, bigendian):
        prefix = bigendian2prefix[bigendian]
        if c < 0:
            raise ValueError("Absolute coordinates are always positive, c = %f"%c)
        if c == 0:
            prec=3
        elif c < 2.0**8:
            prec=2
        elif c < 2.0**16:
            prec=1
        elif c < 2.0**32:
            prec=0
        else:
            raise ValueError, "Coordinate value too large"
            
        refdatatype = [ "I", "H", "B", "" ]

        if prec != 3:
            data = pack(prefix+refdatatype[prec], int(c))
        else:
            data = ""

        return prec, data

class CellElementPointbase(CellElement):
    """Base class for CellElements with geomterty type Point

    >>> p = CellElementPointbase([0.5, 1])
    >>> p
    CellElementPointbase((0.5, 1.0))
    >>> p.wkt
    'POINT(0.50000 1.00000)'
    >>> CellElementPointbase()
    CellElementPointbase(None)
    
    """
    geometrytype = 'Point'

    def __init__(self, coords=None):
        super(CellElementPointbase, self).__init__(coords)
        if coords:
            self._coords = tuple(map(float, coords))

    @property
    def x(self):
        return self._coords[0]

    @property
    def y(self):
        return self._coords[1]

    @property
    def bounds(self):
        """Return bounding box as minx,miny,maxx,maxy

        >>> p = CellElementPointbase([0,1])
        >>> p.bounds
        (0.0, 1.0, 0.0, 1.0)
        """
        return tuple(self._coords) + tuple(self._coords)

class CellElementLineStringbase(CellElement):
    """Base class for CellElements with geomterty type LineString

    >>> l = CellElementLineStringbase([[0,1],[3,4],[4,5]])
    >>> l
    CellElementLineStringbase(((0.0, 1.0), (3.0, 4.0), (4.0, 5.0)))
    >>> l.wkt
    'LINESTRING(0.00000 1.00000,3.00000 4.00000,4.00000 5.00000)'
    
    """
    geometrytype = 'LineString'

    def __init__(self, coords=None):
        super(CellElementLineStringbase, self).__init__(coords)
        if coords:
            self._coords = tuple([tuple(map(float, c)) for c in coords])

    @property
    def bounds(self):
        """Return bounding box as minx,miny,maxx,maxy

        >>> l = CellElementLineStringbase([[0,1],[3,4],[4,5]])
        >>> l.bounds
        (0.0, 1.0, 4.0, 5.0)
        """
        coords = N.array(self._coords)
        return tuple(coords.min(0)) + tuple(coords.max(0))
        
class CellElementPOI(CellElementPointbase):
    typecode=16
    def __init__(self, coords=None, categoryid=None, subcategoryid=None, textslot=None):
        super(CellElementPOI, self).__init__(coords)
        self.categoryid = categoryid
        self.subcategoryid = subcategoryid
        self.textslot = textslot

    def __hash__(self):
        return CellElement.__hash__(self) ^ hash(self.categoryid) ^ hash(self.subcategoryid)
    def __eq__(self, x):
        return self.wkt ==  x.wkt and self.categoryid == x.categoryid and \
               self.subcategoryid == x.subcategoryid

    def deSerialize(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        bbox, data = self._deserialize_bbox(cell, data, bigendian)
        [p] = cell.relToAbsCoords([bbox.c1])
        self._coords = (p[0],-p[1])

        [self.categoryid] = unpack(prefix+"B", data)
        data = data[1:]
        [self.subcategoryid] = unpack(prefix+"B", data)
        data = data[1:]
        data = self._deserialize_textslot(data, bigendian)

    def serialize(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        data, bbox = self._serialize_bbox(cell, bigendian)

        data += pack(prefix+"B", self.categoryid)
        data += pack(prefix+"B", self.subcategoryid)

        data += self._serialize_textslot(bigendian, allowbyteindex=True)
        
        return data

    def setCategoryId(self, id):
        self.categoryid = id

    def setSubCategoryId(self, id):
        self.subcategoryid = id
    
class CellElementPoint(CellElementPointbase):
    """Point cell element class"""
    typecode=11
    def __init__(self, coords=None, objtype=0, textslot=None):
        super(CellElementPoint, self).__init__(coords)
        self.objtype = objtype
        self.textslot = textslot

    def __eq__(self, x):
        return self.wkt ==  x.wkt and self.objtype == x.objtype and self.textslot == x.textslot
    def __hash__(self):
        return hash(self.wkt) ^ hash(self.excess) ^ hash(self.objtype) ^ hash(self.textslot)

    def deSerialize(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        bbox, data = self._deserialize_bbox(cell, data, bigendian)
        
        [p] = cell.relToAbsCoords([bbox.c1])
        self._coords = (p[0], -p[1])

        self.textslot = unpack(prefix+"B", data)[0] << 24
        data = data[1:]

        [self.objtype] = unpack(prefix+"B", data)
        data = data[1:]

        data = self._deserialize_textslot(data, bigendian, onlyindex=True)

    def serialize(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        data, bbox = self._serialize_bbox(cell, bigendian)
        data += self._serialize_textslotoffset(bigendian)
        data += pack(prefix+"B", self.objtype)
        data += self._serialize_textslot(bigendian, onlyindex=True)
        return data

class CellElementLabel(CellElementPointbase):
    typecode=15

class CellElementArea(CellElement):
    """Area cell element

    >>> a = CellElementArea([[[0.0, 1.0],[3.0, 4.0],[4.0, 5.0]], [[0.5,1.5],[3.0,4.0],[4.0,4.0]]])
    >>> a
    CellElementArea((((0.0, 1.0), (3.0, 4.0), (4.0, 5.0)), ((0.5, 1.5), (3.0, 4.0), (4.0, 4.0))))
    >>> a.wkt
    'POLYGON((0.00000 1.00000,3.00000 4.00000,4.00000 5.00000),(0.50000 1.50000,3.00000 4.00000,4.00000 4.00000))'
    
    """
    geometrytype = 'Polygon'
    typecode=12

    def __iter__(self):
        return iter(self._coords)

    def __eq__(self, x):
        return self.wkt ==  x.wkt and self.objtype == x.objtype and self.textslot==x.textslot

    def __init__(self, coords=None, objtype=None, textslot=None):
        CellElement.__init__(self, coords)
        if coords:
            ## Stored as unclosed polygon
            newcoords = []
            for p in coords:
                if p[0] == p[-1]:
                    newcoords.append(p[0:-1])
                else:
                    newcoords.append(p)

                if len(p) <= 2:
                    raise ValueError('Area must at least contain 3 vertices')
            try:
                self._coords = tuple([tuple([tuple(map(float, c)) for c in p]) for p in newcoords])
            except:
                raise ValueError('coords should be in [[[a1x, a1y], [a2x, a2y], ...], [[b1x, b1y], [b2x, b2y], ...]] format ')
        self.objtype = objtype
        self.textslot = textslot
        self.cornerdata = []

    @property
    def bounds(self):
        """Return bounding box as minx,miny,maxx,maxy

        >>> area = CellElementArea([[[0,1],[3,4],[4,5]], [[-1,0],[1,0],[1,1]]])
        >>> area.bounds
        (-1.0, 0.0, 4.0, 5.0)
        """
        minimum = [N.array(p).min(0) for p in self._coords]
        maximum = [N.array(p).max(0) for p in self._coords]
        return tuple(N.array(minimum).min(0)) + tuple(N.array(maximum).max(0))

    def serialize(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        data, bbox = self._serialize_bbox(cell, bigendian)

        parts = [cell.absToRelCoords([[v[0], -v[1]] for v in part]) for part in \
                     self._coords]

        data += self._serialize_textslotoffset(bigendian, last=len(self.excess)==0)
        data += pack(prefix+"B", self.objtype)

        p = parts.pop(0)
        cdata, subpolytype, nvertices = self.encode_polygon(bbox, p, bigendian)
        adata = pack(prefix+"H", (len(parts)+1) | (subpolytype << 13))

        offset = nvertices + 1
        totalvertices = nvertices
        
        for p in parts:
            assert offset <= 0x1fff, "Too many subpolygons"
            tdata, subpolytype, nvertices = self.encode_polygon(bbox, p, bigendian)
            cdata += tdata
            adata = adata + pack(prefix+"H", offset |(subpolytype << 13))
            offset = offset + nvertices + 1
            totalvertices += nvertices

        data = data + pack(prefix+"H", totalvertices) + adata

        data = data + cdata
        
        # No corner data
        data = data + pack(prefix+"b", -1)

        textslotdata = self._serialize_textslot(bigendian, last=len(self.excess)==0, onlyindex=True)

        # Alignment
        if ((len(self.cornerdata)%2) == 0) and len(textslotdata) > 0:
            data += chr(0)

        data += textslotdata

        return data

    def deSerialize(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        bbox, data = self._deserialize_bbox(cell, data, bigendian)

        parts = []
        origdata = data
        
        self.textslot = unpack(prefix+"B", data)[0] << 24
        data = data[1:]
        [self.objtype] = unpack(prefix+"B", data)
        data = data[1:]

        nvertices = unpack(prefix+"H", data)[0]

        data = data[2:]

        [temp] = unpack(prefix+"H", data)
        data = data[2:]
        polytype = temp >> 13
        nsubpolys = temp & 0x1fff

        subpolytype = [polytype]
        subnvertices = []
        lastoffset = 0
        pointsum=0
        for sub in range(1,nsubpolys):
            [temp] = unpack(prefix+"H",data)
            data = data[2:]

            subpolytype.append(temp>>13)

            offset = temp & 0x1fff
            subnvertices.append(offset-lastoffset-1)
            pointsum = pointsum + offset - lastoffset - 1
            lastoffset = offset

        subnvertices.append(nvertices - pointsum)

        for nsub in range(nsubpolys):
            vlist = []
            ndelta = 0
            end = None
            if subpolytype[nsub] in [0,2]:
                if subpolytype[nsub] == 0:
                    position = bbox.c1 + \
                               N.array(unpack(prefix+"2I",data))
                    data = data[8:]
                else: 
                    position = bbox.c1 + \
                               N.array(unpack(prefix+"2H",data))
                    data = data[4:]

                ndelta = subnvertices[nsub] - 1

            elif subpolytype[nsub] in [3,4,5,6,7]:
                if subpolytype[nsub] == 6:
                    position = bbox.c1
                    ndelta = subnvertices[nsub]-1
                elif subpolytype[nsub] == 5:
                    position = bbox.c2
                    end = bbox.c1
                    ndelta = subnvertices[nsub]-2
                elif subpolytype[nsub] == 7:
                    position = N.array([bbox.c2[0], bbox.c1[1]])
                    end = N.array([bbox.c1[0], bbox.c2[1]])
                    ndelta = subnvertices[nsub]-2
                elif subpolytype[nsub] == 3:
                    position = bbox.c2
                    ndelta = subnvertices[nsub]-1
                elif subpolytype[nsub] == 4:
                    position = bbox.c1 + \
                          N.array(unpack(prefix+"2B",data))
                    data = data[2:]
                    ndelta = subnvertices[nsub]-1
            else:
                print dump(origdata)
                raise ValueError, "Unhandled subpoly type %d"%subpolytype[nsub]

            ## Add the difference encoded points
            delta = N.array(unpack(prefix + "%db"%(2*ndelta), data))
            data = data[2*ndelta:]

            delta = delta.reshape((ndelta, 2))

            vlist = N.concatenate([[position], delta]).cumsum(0)

            if end != None:
                vlist = N.concatenate([vlist, [end]])
                    
            parts.append( vlist )

        [self.cornerdatapresent] = unpack(prefix+"b",data)
        data = data[1:]

        if self.cornerdatapresent != -1:
            data = data[nvertices:]

        # Skip alignment
        if (len(data)%2) == 1:
            data = data[1:]

        if len(data) == 2:
            self.textslot = self.textslot | unpack(prefix+"H",data)[0]

        parts = [[(v[0],-v[1]) for v in cell.relToAbsCoords(part)] for part in parts]
        self._coords =tuple(parts)

    def encode_polygon(self, bbox, vlist, bigendian):
        prefix = bigendian2prefix[bigendian]

        nvertices = len(vlist)
        cdata = ""
        if N.alltrue(vlist[0] == bbox.c2) and \
             N.alltrue(vlist[-1] == bbox.c1):
            vlist.pop(-1)
            polytype = 5
        elif N.alltrue(vlist[0] == N.array([bbox.c2[0],bbox.c1[1]])) and \
             N.alltrue(vlist[-1] == N.array([bbox.c1[0],bbox.c2[1]])):
            vlist.pop(-1)
            polytype = 7
        elif N.alltrue(vlist[0] == bbox.c2):
            polytype = 3
        elif N.alltrue(vlist[0] == bbox.c1):
            polytype = 6
        else:
            idelta = vlist[0]-bbox.c1
            if (idelta[0] > 65535) or (idelta[1] > 65535):
                raise Exception("Cannot encode polygon")
                polytype = 0
                cdata = pack(prefix+"2i", *map(int,vlist[0]))
            elif (idelta[0] > 255) or (idelta[1] > 255):
                polytype = 2
                cdata = pack(prefix+"2H", *map(int,idelta))
            else:
                polytype = 4
                cdata = pack(prefix+"2B", *map(int, idelta))

        deltadata, newvertices = encodedeltaslow(vlist)

        cdata += deltadata
        nvertices += newvertices

        return cdata, polytype, nvertices

    def __repr__(self):
        args = [str(self._coords)]
        if self.objtype != None:
            args.append('objtype=%d'%self.objtype)
        if self.textslot != None:
            args.append('textslot=%d'%self.textslot)
        return self.__class__.__name__ + '(' + ','.join(args) + ')'

class CellElementPolyline(CellElementLineStringbase):
    """Polyline cell element

    Attributes 
    ----------
    
    unk -- Unknown but for roads it has something to do with its condition
    
    routingvertexindices -- List of indices 
    
    """
    typecode=13
    exportfields = CellElement.exportfields + ['unk', 'routingvertexindices']

    def __init__(self, coords=None, objtype=None, textslot=None):
        super(CellElementPolyline, self).__init__(coords)
        self.objtype = objtype
        self.textslot = textslot
        self.unk = None
        self.routingvertexindices = []

    def __eq__(self, x):
        return self.wkt ==  x.wkt and self.objtype == x.objtype and self.textslot == x.textslot
    def __hash__(self):
        return hash(self.wkt) ^ hash(self.excess) ^ hash(self.objtype) ^ hash(self.textslot)

    def __eq__(self, x):
        return CellElement.__eq__(self,x) and self.objtype==x.objtype

    def __hash__(self):
        return CellElement.__hash__(self) ^ hash(self.objtype)

    @property
    def distance(self):
        coords = N.array(self._coords)
        return N.sum(N.sqrt(N.sum(N.diff(coords, axis=0)**2,axis=1)))

    def deSerialize(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        bbox, data = self._deserialize_bbox(cell, data, bigendian)

        self.textslot = unpack(prefix+"B", data)[0] << 24
        data = data[1:]
        [self.objtype] = unpack(prefix+"B", data)
        data = data[1:]

        [temp] = unpack(prefix+"H", data)
        data = data[2:]
        polytype = temp >> 13
        nvertices = temp & 0x1fff

        vlist = []
        ndelta = 0
        end = None
        if polytype <= 2:
            position = bbox.c1
            if polytype == 0:
                position = N.array(unpack(prefix+"2i",data))
                data = data[8:]
            elif polytype == 1:
                position = bbox.c1 + N.array(unpack(prefix+"2H",data))
                data = data[4:]
            elif polytype == 2:
                position = bbox.c1 + N.array(unpack(prefix+"2B",data))
                data = data[2:]

            ndelta = nvertices - 1
        else:
            if polytype == 6:
                position = N.array([bbox.c1[0],bbox.c2[1]])
                end = N.array([bbox.c2[0],bbox.c1[1]])
                ndelta = nvertices-2
            elif polytype == 5:
                position = bbox.c2
                end = bbox.c1
                ndelta = nvertices-2
            elif polytype == 7:
                position = N.array([bbox.c2[0],bbox.c1[1]])
                end = N.array([bbox.c1[0],bbox.c2[1]])
                ndelta = nvertices-2
            elif polytype == 3:
                position = bbox.c1
                ndelta = nvertices-1
            elif polytype == 4:
                position = bbox.c1
                end = bbox.c2
                ndelta = nvertices-2

        ## Add the difference encoded points
        delta = N.array(unpack(prefix + "%db"%(2*ndelta), data))
        data = data[2*ndelta:]

        delta = delta.reshape((ndelta, 2))

        vlist = N.concatenate([[position], delta]).cumsum(0)

        if end != None:
            vlist = N.concatenate([vlist, [end]])

        self._coords = tuple([(v[0],-v[1]) for v in cell.relToAbsCoords(vlist)])

        data = self._deserialize_textslot(data, bigendian,
                                        last=False, onlyindex=True)

        ## Get routing information

        extrainfo = list(unpack('%dB'%len(data), data))

        if len(extrainfo) % 2 == 1:
            self.unk = extrainfo.pop(0)
        
        if len(extrainfo) > 0:
            self.routingvertexindices = []
            for i, byte in enumerate(reversed(extrainfo)):
                for biti in range(8):
                    if byte & (1 << biti):
                        self.routingvertexindices.append(8 * i + biti)

            assert(self.routingvertexindices[-1] < len(vlist))

    def serialize(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        data, bbox = self._serialize_bbox(cell, bigendian)

        vlist=[[p[0], -p[1]] for p in self._coords]

        vlist = cell.absToRelCoords(vlist)

        data += self._serialize_textslotoffset(bigendian, last=len(self.excess)==0)
        data += pack("B", self.objtype)

        nvertices = len(vlist)
        cdata = ""

        if N.alltrue(vlist[0] == bbox.c1) and \
           N.alltrue(vlist[-1] == bbox.c2):
            vlist.pop(-1)
            polytype = 4
        elif N.alltrue(vlist[0] == bbox.c2) and \
             N.alltrue(vlist[-1] == bbox.c1):
            vlist.pop(-1)
            polytype = 5
        elif N.alltrue(vlist[0] == N.array([bbox.c1[0],bbox.c2[1]])) and \
             N.alltrue(vlist[-1] == N.array([bbox.c2[0],bbox.c1[1]])):
            vlist.pop(-1)
            polytype = 6
        elif N.alltrue(vlist[0] == N.array([bbox.c2[0],bbox.c1[1]])) and \
             N.alltrue(vlist[-1] == N.array([bbox.c1[0],bbox.c2[1]])):
            vlist.pop(-1)
            polytype = 7
        elif N.alltrue(vlist[0] == bbox.c1):
            polytype = 3
        else:
            idelta = vlist[0]-bbox.c1
            if (idelta[0] > 65535) or (idelta[1] > 65535):
                polytype = 0
                cdata = pack(prefix+"2i", *map(int,vlist[0]))
            elif (idelta[0] > 255) or (idelta[1] > 255):
                polytype = 1
                cdata = pack(prefix+"2H", *map(int,idelta))
            else:
                polytype = 2
                cdata = pack(prefix+"2B", *map(int, idelta))

        deltadata, newvertices = encodedeltaslow(vlist)

        cdata += deltadata
        nvertices += newvertices

        data = data + \
               pack(prefix+"H", (polytype << 13) | nvertices)
        data = data + cdata

        data += self._serialize_textslot(bigendian, last=len(self.excess)==0, onlyindex=True)

        data += self.excess
        
        return data        

class CellElementRouting(CellElementLineStringbase):
    """Routing network edge

    Attributes
    ----------

    layernumref -- Layer index to referenced cell element
    ivertex -- Tuple of start and end point vertex indices in referenced cell element
    
    restrictions -- A vector of length 4 with turn restrictions where the items have the following order:
      [endpointrestr, startpointrestr, endpointrestr, startpointrestr]
      The meaning of the values are:

      ===== =====================================================
      value description
      ===== =====================================================
      3     up, down forbidden
      12    left, right forbidden
      
    orientations -- A tuple with the angles of the start and end points of the polyline
         
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

    segmentflags -- Bit mask
         
      ========= ===========
      roadflags value
      ========= ===========
      4         freeway
      8         roundabout

    segmenttype --

      ========== ===========
      segmettype value
      ========== ===========
      1          ramp
      4          ramp
  

    bidirectional -- True if traffic can go in both directions
    reversedir -- Traffic goes from second to first vertex
    nodeindices -- Tuple with edge indices for the first and second vertex

    """

    
    typecode=17
    exportfields = CellElement.exportfields + ['restrictions', 'distance', 'ivertices', 'cellnumref', 
                                               'numincellref', 'flagsh', 'unk1', 'unk2', 'orientations', 'edgeindices',
                                               'segmenttype', 'segmentflags' ]
    FlagBidirectional = 0x80    
    FlagForward = 0x40          ## The traffice direction is from point 1 to point 2
    
    def __init__(self, coords=None,
                 layernumref = None, cellnumref = None, numincellref = None,
                 ivertices = (None, None),
                 bidirectional=True, reversedir = False, edgeindices = (None, None),
                 orientations=(0,0),
                 segmentflags = None, speedcat = None, segmenttype = None, distance = 0):
        CellElement.__init__(self, coords)

        self.layernumref = layernumref
        self.cellnumref = cellnumref
        self.numincellref = numincellref
        self.ivertices = ivertices
        self.bidirectional = bidirectional
        self.reversedir = reversedir
        self.edgeindices = edgeindices
        self.segmentflags = segmentflags
        self.speedcat = speedcat
        self.segmenttype = segmenttype
        self.distance = int(distance)
        self.restrictions = (0,0,0,0)
        self.orientations = orientations
        self.unk1 = 0
        self.unk2 = 0

    def __eq__(self, x):
        return self.cellnum == x.cellnum and self.numincell == x.numincell and self.self.wkt ==  x.wkt
    def __hash__(self):
        return hash(self.wkt) ^ hash(self.excess) ^ hash(self.objtype) ^ hash(self.textslot)

    def __repr__(self):
        return self.__class__.__name__ + ' dist: %d, points: %d-%d, l:%s, c: %d, n: %d, bidir: %s, reverse: %s, edgeindices: %s, u1: %d, u2: %d, restrictions:%s, orientations:(%d,%d), excess: %s'%(
            self.distance, self.ivertices[0], self.ivertices[1], self.layernumref, self.cellnumref, self.numincellref, str(self.bidirectional), 
            str(self.reversedir), str(self.edgeindices), self.unk1, self.unk2, str(self.restrictions), self.orientations[0],
            self.orientations[1], dump(self.excess))

    @property
    def flagsh(self):
        flags = []
        if self.bidirectional:
            flags.append('bidir')
        if self.reversedir:
            flags.append('reverse')
        return ','.join(flags)

    def __eq__(self, x):
        return CellElement.__eq__(self,x)

    def __hash__(self):
        return CellElement.__hash__(self)

    def deSerialize(self, cell, data, bigendian):
        prefix = bigendian2prefix[bigendian]

        bbox, data = self._deserialize_bbox(cell, data, bigendian)

        (tmp1, tmp2) = unpack(prefix+'II', data[:8])
        data = data[8:]
        self.pointcorners = tmp1 >> 29
        self.unk1 = (tmp1 >> 24) & 0x1f
        self.distance = tmp1 & 0xffffff

        self.layernumref = (tmp2 >> 28) - 8
        self.unk2 = (tmp2 >> 24) & 0xf
        self.ivertices = ((tmp2 >> 13) & 0x7ff, tmp2 & 0x1fff)

        (self.cellnumref, self.numincellref) = unpack(prefix+'IH', data[:6])
        self.numincellref -= 1
        data = data[6:]

        self.restrictions = unpack(prefix+'BBBB', data[:4])
        data = data[4:]

        (tmp,) = unpack('B', data[:1])
        self.bidirectional = bool(tmp & 0x80)
        self.reversedir = bool(tmp & 0x40)
        self.edgeindices = tmp & 0x7, (tmp >> 3) & 0x7
        data = data[1:]
        
        (tmp,) = unpack(prefix+'B', data[:1])
        self.orientations = tmp & 0x7, (tmp >> 3) & 0x7
        data = data[1:]

        if self.pointcorners == 6:
            p1 = bbox.ur
            p2 = bbox.ll
        elif self.pointcorners == 4:
            p1 = bbox.ul
            p2 = bbox.lr
        elif self.pointcorners == 2:
            p1 = bbox.lr
            p2 = bbox.ul
        elif self.pointcorners == 0x0:
            p1 = bbox.ll
            p2 = bbox.ur
        else:
            raise Exception('Unexpected corner selection code: %d'%self.pointcorners)

        self._coords = tuple([(v[0],-v[1]) for v in cell.relToAbsCoords([p1, p2])])

        self.unknown2 = repr(self)

        if len(data) > 0:
            (tmp,) = unpack('B', data[-1])
            self.segmentflags, self.speedcat = tmp >> 4, tmp & 0xf
        if len(data) == 2:
            (tmp,) = unpack('B', data[0])
            self.segmenttype = tmp
            
    def serialize(self, cell, bigendian):
        prefix = bigendian2prefix[bigendian]
        
        data, bbox = self._serialize_bbox(cell, bigendian)

        p1, p2 = cell.absToRelCoords([[p[0], -p[1]] for p in self._coords])

        if (p1 == bbox.ur).all() and (p2 == bbox.ll).all():
            pointcorners = 6
        elif (p1 == bbox.ul).all() and (p2 == bbox.lr).all():
            pointcorners = 4
        elif (p1 == bbox.lr).all() and (p2 == bbox.ul).all():
            pointcorners = 2
        elif (p1 == bbox.ll).all() and (p2 == bbox.ur).all():
            pointcorners = 0
        else:
            raise Exception('Cannot determine pointcorners')

        data += pack(prefix + 'II',
             ((self.unk1 & 0x1f) << 24) | (pointcorners << 29) | (self.distance & 0xffffff),
             ((self.layernumref + 8) << 28) | (self.unk2 << 24) | (self.ivertices[0] << 13) | self.ivertices[1])

        data += pack(prefix + 'IH', self.cellnumref, self.numincellref+1)

        data += pack(prefix + 'BBBB', *self.restrictions)

        tmp = int(self.bidirectional) << 7 | int(self.reversedir) << 6 | self.edgeindices[1] << 3 | self.edgeindices[0]
        data += pack('B', tmp)

        data += pack('B', self.orientations[1] << 3 | self.orientations[0])

        if self.segmenttype != None:
            data += pack('B', self.segmenttype)

        if self.segmentflags != None and self.speedcat != None:
            data += pack('B', self.segmentflags << 4 | self.speedcat & 0xf)
        
        return data        


def BBoxRecFromVlist(vlist):
    minx=vlist[0][0]
    miny=vlist[0][1]
    maxx=minx
    maxy=miny
    for v in vlist[1:]:
        if v[0]<minx:
            minx=v[0]
        elif v[0]>maxx:
            maxx=v[0]
        if v[1]<miny:
            miny=v[1]
        elif v[1]>maxy:
            maxy=v[1]
    return Rec([minx,miny],[maxx,maxy])

class Rec(object):    
    def __init__(self, c1, c2):
        self.c1=N.array(c1)
        self.c2=N.array(c2)
    def __copy__(self):
        return Rec(self.c1, self.c2)
    def __str__(self):
        return "(%s,%s)-(%s,%s)" % \
               (str(self.c1[0]),str(self.c1[1]),str(self.c2[0]),str(self.c2[1]))
    def __repr__(self): return self.__str__()

    def __eq__(self, x):
        if isinstance(x,Rec):
            return N.alltrue(self.c1==x.c1) and N.alltrue(self.c2==x.c2)
        else:
            return False
    @property
    def height(self):
        return self.c2[1]-self.c1[1]
    @property
    def width(self):
        return self.c2[0]-self.c1[0]
    def scale(self, factor):
        return Rec(self.c1 * factor, self.c2 * factor)
    def negY(self):
        return Rec(N.array([self.c1[0], -self.c2[1]]), N.array([self.c2[0], -self.c1[1]]))

    @property
    def center(self):
        return (self.c1 + self.c2) / 2
    
    def centerX(self):
        return (self.c1[0]+self.c2[0])/2
    def centerY(self):
        return (self.c1[1]+self.c2[1])/2
    def minX(self):
        return self.c1[0]
    def maxX(self):
        return self.c2[0]
    def minY(self):
        return self.c1[1]
    def maxY(self):
        return self.c2[1]
    def translate(self, d):
        return Rec(self.c1 + d, self.c2 + d)
    def tointeger(self):
        return Rec(N.array([round(self.c1[0]), round(self.c1[1])]), N.array([round(self.c2[0]), round(self.c2[1])]))

    def todiscrete(self, refpoint, unit):
        """Return a discretized bounding box

        >>> rec = Rec((-1.2, -2.5), (1.2,4.5))
        >>> rec.todiscrete(0.0, 1.0)
        (-2,-3)-(2,5)
        >>> rec.todiscrete(N.array([-1.2, -2.5]), 1.0)
        (0,0)-(4,8)

        """
        
        newc1 = N.floor((self.c1 - refpoint) / unit).astype('int')
        newc2 = N.ceil((self.c2 - refpoint) / unit).astype('int')
        newrec = Rec(newc1, newc2)

        ## Make sure that the width and height is an even number
        newrec.c2 += N.array([newrec.width % 2, newrec.height % 2])
        
        return newrec

    def tocontinous(self, refpoint, unit):
        newc1 = self.c1 * unit + refpoint
        newc2 = self.c2 * unit + refpoint
        return Rec(newc1, newc2)
    
    def discretize(self, refpoint, unit):
        """Discretize the corners so they are a multiple of the given unit with regards to a reference point

        >>> rec = Rec((-1.2, -2.5), (1.2,4.5))
        >>> rec.discretize(0.0, 1.0)
        >>> rec
        (-2.0,-3.0)-(2.0,5.0)
        
        
        """
        c1 = (self.c1 - refpoint) / unit
        c2 = (self.c2 - refpoint) / unit

        self.c1 = N.floor(c1) * unit + refpoint
        self.c2 = N.ceil(c2) * unit + refpoint

    def toFloat32(self):
        c1 = N.array(unpack("2f", pack("2f", self.c1[0],self.c1[1])))
        c2 = N.array(unpack("2f", pack("2f", self.c2[0],self.c2[1])))
        return Rec(c1,c2)
    def union(self, a):
        return Rec(N.array([min(self.c1[0], a.c1[0]), min(self.c1[1], a.c1[1])]),
                   N.array([max(self.c2[0], a.c2[0]), max(self.c2[1], a.c2[1])]))
    def buffer(self, v):
        return Rec(self.c1-v,self.c2+v)
    def iscoveredby(self, rec2, xmargin=1e-6, ymargin=1e-6):
        return N.alltrue(rec2.c1 <= self.c1+xmargin) and N.alltrue(rec2.c2 >= self.c2-ymargin)

    s = property(maxY)
    n = property(minY)
    w = property(minX)
    e = property(maxX)        

    @property
    def ul(self): return N.array([self.minX(), self.maxY()])
    @property
    def ll(self): return N.array([self.minX(), self.minY()])
    @property
    def ur(self): return N.array([self.maxX(), self.maxY()])
    @property
    def lr(self): return N.array([self.maxX(), self.minY()])

def encodedeltaslow(vlist):
    r'''Encode a list of vertices as the difference between adjacents vertices.
       The result is a string of signed bytes: vlist[1][0]-vlist[0][0], vlist[1][1]-vlist[0][1], vlist[2][0]-vlist[1][0], ...

       If the differences exceed the range -128, 127 additional vertices are inserted.

       Returns codedstring, n
         where n is the number of inserted vertices

       >>> encodedeltaslow([N.array([1,1]), N.array([0,2]), N.array([0,3])])
       ('\xff\x01\x00\x01', 0)
       >>> encodedeltaslow([N.array([1,1]), N.array([0,2]), N.array([200., 2.])])
       ('\xff\x01\x7f\x00I\x00', 1)
       

       '''
    cdata = ""
    nvertices = 0
    position = vlist.pop(0)
    for nextvertex in vlist:
        done=0
        while not done:
            idelta,position,done = deltaint(position, nextvertex, 127)
            cdata = cdata + pack("2b", *idelta)
            if not done:
                nvertices = nvertices+1

    return cdata, nvertices

def encodedelta(vlist):
    r'''Encode a list of vertices as the difference between adjacents vertices.
       The result is a string of signed bytes: vlist[1][0]-vlist[0][0], vlist[1][1]-vlist[0][1], vlist[2][0]-vlist[1][0], ...

       If the differences exceed the range -128, 127 additional vertices are inserted.

       Returns codedstring, n
         where n is the number of inserted vertices

       >>> encodedelta([[1,1], [0,2], [200, 2], [200, -148]])
       ('\xff\x01\x7f\x00I\x00\x00\x81\x00\xe9', 2)
       >>> encodedelta([[1,1], [0,2], [0,3]])
       ('\xff\x01\x00\x01', 0)
       
       
       '''
    ninserted = 0

    vlist = N.array(vlist)
    
    delta = N.diff(vlist, axis=0)

    overflowrows = N.where(N.logical_or(delta > 127, delta < -127))[0]

    if len(overflowrows) > 0:
        insertrows = []
        insertvalues = []
        for row in overflowrows:
            position = vlist[row]
            nextvertex = vlist[row+1]
            done=0
            extendeddiffs = []
            while not done:
                idelta,position,done = deltaint(position, nextvertex, 127)
                extendeddiffs.append(idelta)

            delta[row] = extendeddiffs[0]
            insertvalues.extend(extendeddiffs[1:])
            n = len(extendeddiffs) - 1
            insertrows.extend(n * [row+1])

            ninserted += n
            
        delta = N.insert(delta, insertrows, insertvalues, axis=0)

    flatdelta = list(delta.flat)

    return pack("%db" % len(flatdelta), *flatdelta), ninserted

def deltaint(v1,v2,maxstep):
    delta = v2-v1
    if (abs(delta[0]) > maxstep) or (abs(delta[1]) > maxstep):
        if abs(delta[0]) > abs(delta[1]):
            delta = maxstep * delta/ abs(delta[0])
        else:
            delta = maxstep * delta / abs(delta[1])
        delta = N.array([round(delta[0]), round(delta[1])])
        done = 0
    else:
        done = 1
    return delta, v1+delta, done

if __name__ == "__main__":
    import doctest
    doctest.testmod()
