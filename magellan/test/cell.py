from Map import Map
import unittest
import tempfile
import shutil
import os
from CellElement import CellElementPolyline
from sets import Set
from shapely.geometry import Point, LineString, Polygon
from Cell import Cell

def dump(x):
    return " ".join(["0x%02x "%ord(c) for c in x])

def getCellElementRawData(layer, cellnum, nincell):
    layer.fhlay.seek(layer.cellfilepos[cellnum][0])
    data = layer.fhlay.read(layer.cellfilepos[cellnum][1])
    
    # Extract # of cellelements in cell
    ncellelements, nskip = layer.unpack("2H",data)
    data = data[4:]

    if layer.map.debug:
        print "Cell#:%d ncellelements:%d"%(cellnum,ncellelements)

    for cellelementnum in range(0,ncellelements-nskip):
        cellelementsizespec, precisionspec = layer.unpack("HB",data)

        data = data[2:]

        # Calculate size of cellelement data
        size = cellelementsizespec-15-2

        dsizes = [4,2,1,0]
        for bit in range(0,8,2):
            size = size + dsizes[(precisionspec >> bit) & 0x3]

        if cellelementnum == nincell:
            return data[0:size]

        data = data[size:]

class TempDir:
    def __init__(self, srcdir):
        self.dir = tempfile.mkdtemp()

        shutil.copytree(srcdir,os.path.join(self.dir,os.path.basename(srcdir)))
        
    def __str__(self):
        return self.dir
    def __del__(self):
        shutil.rmtree(self.dir)

class CellElementTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1")
        self.testdatadir = os.path.join(str(self.tempdir),"layerdata1")

    def tearDown(self):
        del self.testdatadir

    def testPolylineSerialize(self):
        map = Map()
        map.open(os.path.join(self.testdatadir, "00map.ini"))

        streets = map.getLayerByName("00_Streets")
        streets.open("r")

        cell = streets.getCell(1)

        street = cell.getCellElements()[0]

        expected = getCellElementRawData(streets, 1, 0)


        actual = street.serialize(cell)

        if actual != expected:
            print "Expected:", dump(expected)
            print "Actual:  ", dump(actual)

        outstreet = CellElementPolyline(streets)
        outstreet.deSerialize(cell, actual)

        self.assertEqual(street,outstreet)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(actual, expected)
        

if __name__ == "__main__":
    unittest.main()
