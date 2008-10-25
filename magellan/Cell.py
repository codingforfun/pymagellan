from CellElement import CellElementPOI, CellElementPoint, CellElementLabel, CellElementArea, CellElementPolyline, \
                        CellElementRouting, Rec
from copy import copy
import tempfile
import os
from misc import dump
import pickle
import shelve
import numpy as N
import layerpacker

cellElementTypeMap = { CellElementPOI.typecode: CellElementPOI,
                       CellElementPoint.typecode: CellElementPoint,
                       CellElementLabel.typecode: CellElementLabel,
                       CellElementArea.typecode: CellElementArea,
                       CellElementPolyline.typecode: CellElementPolyline,
                       CellElementRouting.typecode: CellElementRouting
                       }

class Cell(object):
    """Cell is an abstract class that represents a part of a layer and stores cell information and cell elements

    The bounding box is calculated from the layer bounding box and cell number
    """

    def __init__(self, layerobj, cellnum):
        self.layer = layerobj
        self.cellnum = cellnum
        self.setbbox()

    def __len__(self):
        raise NotImplementError

    def absToRelCoords(self, points):
        """Convert discrete absolute coordinates to cell relative discrete coordinates"""
        return list(N.array(points) - self._dbbox.c1)
        
#    [(((p-self.layer.bbox.c1)/scale).round()-self._dbbox.c1).astype(int) for p in points]
#        return [((p-self._dbbox.c1)/scale).round().astype(int) for p in points]

    def relToAbsCoords(self, points):
        """Convert relative (to cell) discrete to absolute continous coordinates"""
        return N.array(points) + self._dbbox.c1

    def setbbox(self):
        if self.layer._dbbox == None:
            self._dbbox = None
            self._bbox = None
        else:
            self._dbbox = self.layer.calc_cell_extents(self.cellnum)
            self._bbox = self._dbbox.tocontinous(self.layer.refpoint, self.layer.scale)

    @property
    def elements(self):
        """Return an iterator to the cell elements"""
        raise NotImplementError
    
    def getCellElements(self):
        """Return a list of cell elements"""
        raise NotImplementedError

    def getCellElement(self, cellelementnum):
        raise NotImplementedError

    def deSerialize(self, data):
        raise NotImplementedError

    def updateElement(self, i, element):
        raise NotImplementedError

    def serialize(self):
        raise NotImplementedError

    def addCellElement(self, cellelement):
        raise NotImplementedError

    def pop(self, cellelementnum):
        raise NotImplementedError

    @property
    def bboxrec(self):
        return self._dbbox.negY()

    def _serialize_cellelement(self, cellelement):
        cellelementdata = cellelement.serialize(self, self.layer.bigendian)

        size = len(cellelementdata)

        precisionspec = ord(cellelementdata[0])
        dsizes = [4,2,1,0]
        for bit in range(0,8,2):
            size -= dsizes[(precisionspec >> bit) & 0x3]

        size+=15+2

        data = self.layer.pack("H", size)
        data += cellelementdata

        return data

    def _deserialize(self, data):
        cellelements = []
        ncellelements, nskip = self.layer.unpack("2H",data)

        print ncellelements, nskip
        if nskip != 0:
            raise Exception('Layer is probably packed, cannot read')

        data = data[4:]

        if self.layer.map.debug:
            print "Cell#:%d ncellelements:%d"%(self.cellnum,ncellelements)

        for cellelementnum in range(0, ncellelements-nskip):
            cellelementsizespec, precisionspec = self.layer.unpack("HB",data)
            data = data[2:]

            # Calculate size of cellelement data
            size = cellelementsizespec-15-2

            dsizes = [4,2,1,0]
            for bit in range(0,8,2):
                size = size + dsizes[(precisionspec >> bit) & 0x3]

            cellelement = cellElementTypeMap[self.layer.layertype]()
            cellelement.deSerialize(self, data[0:size], self.layer.bigendian)
            cellelement.cellnum = self.cellnum
            cellelement.numincell = cellelementnum
            cellelements.append(cellelement)

            data = data[size:]

        return cellelements

    def checkcellelement(self, cellelement):
        if not isinstance(cellelement, cellElementTypeMap[self.layer.layertype]):
            raise ValueError('Incorrect element class %s, should be %s'%(cellelement.__class__.__name__, cellElementTypeMap[self.layer.layertype]))

class CellInMemory(Cell):
    """Cell implementation that store its data in memory. This implementation is fast but has a big memory footprint for large cells"""
    def __init__(self, layerobj, cellnum):
        super(CellInMemory, self).__init__(layerobj, cellnum)
        self.cellelements = []

    def __len__(self):
        return len(self.cellelements)

    @property
    def elements(self):
        return self.cellelements

    def pop(self, cellelementnum):
        return self.cellelements.pop(cellelementnum)

    def getCellElements(self):
        """Return a list of cell elements"""
        return self.cellelements

    def getCellElement(self, cellelementnum):
        return self.cellelements[cellelementnum]

    def deSerialize(self, data):
        self.cellelements = self._deserialize(data)

    def updateElement(self, i, element):
        self.cellelements[i] = element

    def serialize(self):
        data = self.layer.pack("2H", len(self.cellelements), 0)

        for s in self.cellelements:
            data += self._serialize_cellelement(s)
            
        ## Align to word boundary
        if (len(data) % 2) != 0:
            data += chr(0)
            
        return data

    def addCellElement(self, cellelement):
        cellelement = copy(cellelement)
        cellelement.cellnum = self.cellnum
        self.cellelements.append(cellelement)
        return len(self.cellelements)-1


class CellTempfile(Cell):
    r'''Cell implementation that store its data in a temporary file.
    This implementation has a small memory footprint and an expensive read operation

    >>> import Map, Layer, CellElement
    >>> m = Map.Map()
    >>> m.bboxrec = Rec((0,0),(3,3))
    >>> l = m.addLayer(Layer.Layer(m, 'test', 'test', layertype=Layer.LayerTypePoint, nlevels=4))
    >>> l.open('w')
    >>> cell = CellTempfile(l, 0)
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([1,2]))
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([2,2]))
    >>> cell.getCellElements()
    [CellElementPoint((0.999999, 1.999998)), CellElementPoint((1.999998, 1.999998))]
    >>> cell.getCellElement(0)
    CellElementPoint((0.999999, 1.999998))
    >>> cell.getCellElement(1)
    CellElementPoint((2.0, 2.0))
    >>> dump(cell.serialize())
    '02 00 00 00 16 00 f0 07 b2 01 00 1e c8 06 00 ff 00 00 00 16 00 f0 0e 64 03 00 1e c8 06 00 ff 00 00 00'
    >>> m.close()

    '''
    def __init__(self, layerobj, cellnum):
        super(CellTempfile, self).__init__(layerobj, cellnum)

        self.tempfile = tempfile.TemporaryFile('w+', prefix='cell_%s_%06d'%(self.layer.name, cellnum))
        self.ncellelements = 0
        self.lastcellelement = None
        
    def getCellElements(self):
        """Read cell elements from file"""
        return self._deserialize(self.serialize())

    def getCellElement(self, cellelementnum):
        if cellelementnum == self.ncellelements-1 and self.lastcellelement != None:
            return self.lastcellelement
        return self.getCellElements()[cellelementnum]

    def deSerialize(self, data):
        self.tempfile.seek(0)
        self.tempfile.write(data)

    def serialize(self):
        self.tempfile.seek(0)
        data = self.layer.pack("2H", self.ncellelements, 0) + self.tempfile.read()

        ## Align to word boundary
        if (len(data) % 2) != 0:
            data += chr(0)
            
        return data

    def updateElement(self, i, element):
        raise Exception('CellTempfile does not implement updateElement')

    def addCellElement(self, cellelement):
        self.ncellelements += 1

        cellelement = copy(cellelement)
        cellelement.cellnum = self.cellnum

        self.tempfile.seek(0, os.SEEK_END)
        self.tempfile.write(self._serialize_cellelement(cellelement))

        self.lastcellelement = cellelement
        
        return self.ncellelements - 1

class CellShelve(Cell):
    '''Cell implementation that store its data in a shelve object
    This implementation has a small memory footprint and an fairly cheap read operation

    >>> import Map, Layer, CellElement
    >>> m = Map.Map()
    >>> m.bboxrec = Rec((0,0),(3,3))
    >>> l = m.addLayer(Layer.Layer(m, 'test', 'test', layertype=Layer.LayerTypePoint, nlevels=4))
    >>> l.open('w')
    >>> cell = CellShelve(l, 1)
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([1,2]))
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([2,2]))
    >>> cell.getCellElements()
    [CellElementPoint((1.0, 2.0)), CellElementPoint((2.0, 2.0))]
    >>> cell.getCellElement(0)
    CellElementPoint((1.0, 2.0))
    >>> cell.getCellElement(1)
    CellElementPoint((2.0, 2.0))
    >>> dump(cell.serialize())
    '02 00 00 00 16 00 f0 07 b2 01 00 08 b2 01 00 ff 00 00 00 16 00 f0 0e 64 03 00 08 b2 01 00 ff 00 00 00'
    >>> m.close()
    '''
    def __init__(self, layerobj, cellnum):
        super(CellShelve, self).__init__(layerobj, cellnum)

        self.tempfilename = tempfile.mktemp()
        self.cellelements = shelve.open(self.tempfilename)
        self.cellelementkeys = []
        self.maxkey = 0

    def __del__(self):
        os.unlink(self.tempfilename)

    def __len__(self):
        return len(self.cellelements)

    @property
    def elements(self):
        """Return an iterator to the cell elements"""
        for i in range(len(self.cellelements)):
            yield self.cellelements[self.cellelementkeys[i]]

    def pop(self, cellelementnum):
        key = self.cellelementkeys.pop(cellelementnum)
        return self.cellelements.pop(key)
        
    def getCellElements(self):
        """Read cell elements from file"""
        return list(self.elements)

    def getCellElement(self, cellelementnum):
        return self.cellelements[self.cellelementkeys[cellelementnum]]

    def deSerialize(self, data):
        for i,ce in enumerate(self._deserialize(data)):
            self.cellelements[str(i)] = ce

    def serialize(self):
        data = self.layer.pack("2H", len(self.cellelements), 0)

        for i in range(len(self.cellelementkeys)):
            data += self._serialize_cellelement(self.cellelements[self.cellelementkeys[i]])
        
        ## Align to word boundary
        if (len(data) % 2) != 0:
            data += chr(0)

        return data

    def updateElement(self, i, element):
#        self.checkcellelement(element)
        self.cellelements[str(i)] = element

    def addCellElement(self, cellelement):
#        self.checkcellelement(cellelement)
        key = str(self.maxkey)
        self.maxkey += 1
        self.cellelements[key] = cellelement
        self.cellelementkeys.append(key)
        return len(self.cellelementkeys)-1


class CellCommonShelve(Cell):
    r'''Cell implementation that store its data in a common shelve object for all cells in a layer
    This implementation has a small memory footprint and an fairly cheap read operation and
    is better if there are many shelves. The elements are keyed by their cellnumber so there are
    no collisions between cells.

    >>> import Map, Layer, CellElement
    >>> m = Map.Map()
    >>> m.bboxrec = Rec((0,0),(3,3))
    >>> l = m.addLayer(Layer.Layer(m, 'test', 'test', layertype=Layer.LayerTypePoint, nlevels=4))
    >>> l.open('w')
    >>> tempfilename = tempfile.mktemp()
    >>> shelf = shelve.open(tempfilename)
    >>> cell = CellCommonShelve(l, 1, shelf)
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([1,2]))
    >>> ce = cell.addCellElement(CellElement.CellElementPoint([2,2]))
    >>> cell.getCellElements()
    [CellElementPoint((1.0, 2.0)), CellElementPoint((2.0, 2.0))]
    >>> cell.getCellElement(0)
    CellElementPoint((1.0, 2.0))
    >>> cell.getCellElement(1)
    CellElementPoint((2.0, 2.0))
    >>> dump(cell.serialize())
    '02 00 00 00 16 00 f0 07 b2 01 00 08 b2 01 00 ff 00 00 00 16 00 f0 0e 64 03 00 08 b2 01 00 ff 00 00 00'
    >>> shelf.keys()
    ['1/0', '1/1']
    >>> os.unlink(tempfilename)
    >>> m.close()
    '''
    def __init__(self, layerobj, cellnum, shelf):
        super(CellCommonShelve, self).__init__(layerobj, cellnum)
        self.cellelements = shelf
        self.cellelementkeys = []
        self.maxkey = 0

    def __len__(self):
        return len(self.cellelementkeys)

    @property
    def elements(self):
        """Return an iterator to the cell elements"""
        for i in range(len(self.cellelementkeys)):
            yield self.cellelements[self.cellelementkeys[i]]

    def pop(self, cellelementnum):
        key = self.cellelementkeys.pop(cellelementnum)
        return self.cellelements.pop(key)
        
    def getCellElements(self):
        """Read cell elements from file"""
        return list(self.elements)

    def getCellElement(self, cellelementnum):
        return self.cellelements[self.cellelementkeys[cellelementnum]]

    def deSerialize(self, data):
        for ce in self._deserialize(data):
            self.addCellElement(ce)

    def serialize(self):
        data = self.layer.pack("2H", len(self), 0)

        for e in self.elements:
            data += self._serialize_cellelement(e)
        
        ## Align to word boundary
        if (len(data) % 2) != 0:
            data += chr(0)

        return data

    def updateElement(self, i, element):
#        self.checkcellelement(element)
        self.cellelements[self.cellelementkeys[i]] = element

    def addCellElement(self, cellelement):
#        self.checkcellelement(cellelement)
        key = self._key(self.maxkey)
        self.maxkey += 1
        self.cellelements[key] = cellelement
        self.cellelementkeys.append(key)
        return len(self.cellelementkeys)-1

    def _key(self, cellelementnum):
        return '%d/%d'%(self.cellnum, cellelementnum) 

if __name__ == "__main__":
    import doctest
    doctest.testmod()
