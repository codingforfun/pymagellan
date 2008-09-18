from magellan.Map import Map, createMap, MapImage
import unittest
import tempfile
import shutil
import os
from magellan.CellElement import CellElementPolyline, CellElementArea, CellElementPoint, Rec
from magellan.Layer import Layer,LayerTypePolyline,LayerTypePoint
from sets import Set
from testutil import TempDir
import numpy as N

class myTestCase(unittest.TestCase):
    def assertSetsEqual(self, actual, expected):
        self.assertEqual(len(actual), len(expected))

        if actual != expected:
            print "difference:",actual.symmetric_difference(expected)
            print "actual: ",actual
            print "expected: ",expected
        
        self.assertEqual(actual, expected, "Cell elements do not match after read back")

class TestLayerBasic(myTestCase):
    def setUp(self):
        self.m = Map()

        self.m.scale = 1e-3
        self.m.bbox = ((-3.0, -4.0), (2.0, 1.0))

    def tearDown(self):
        self.m.close()

    def testcalc_cell_extents(self):
        layer = Layer(self.m, name="The Layer", filename="layer", layertype=LayerTypePoint, nlevels = 1)

        lbb = layer._bbox.todiscrete(layer.refpoint, layer.scale)

        self.assertEqual(lbb, Rec((-3000,-1000), (2000,4000)))

        self.assertEqual(layer.calc_cell_extents(1), lbb)

        self.assertEqual(layer.calc_cell_extents(2), Rec((-3000, -1000),(-500, 1500)))

class TestSimple(myTestCase):
    def setUp(self):
        self.tempdir = TempDir()

    def testAddPoint(self):
        outimage = os.path.join(self.tempdir.dir, 'test.imi')

        mi = MapImage(outimage)
        mi.open('w')
        
        m = mi.createMap()

        m.scale = 1e-3
        m.bbox = ((-3.0, -4.0), (2.0, 1.0))

        m.open("w")
        
        layer = Layer(m, name="The Layer", filename="layer", layertype=LayerTypePoint, nlevels = 1)
        m.addLayer(layer)
        layer.open("w")

        point = CellElementPoint((-1.5006, -3.5006))
        layer.addCellElement(point)

        cell = layer.getCell(point.cellnum)

        self.assertEqual(point.cellnum, 4)

        point.discretizeGeometry(layer.getCell(point.cellnum))

        self.assertAlmostEqual(point.x, -1.501)
        self.assertAlmostEqual(point.y, -3.501)

        mi.close()

        ## Read back
        mi = MapImage(outimage)
        mi.open('r')

        m = mi.maps[0]

class TestBBox(myTestCase):
    """Test to create map without a priori bounding box"""
    def setUp(self):
        self.tempdir = TempDir()
        self.outimage = os.path.join(self.tempdir.dir, 'test.imi')

        self.mi = MapImage(self.outimage)
        self.mi.open('w')
        
        self.m = self.mi.createMap()

        self.m.scale = 1e-3

    def tearDown(self):
        self.m.close()
        self.mi.close()

    def testCreateLayerSansBBox(self):
        m = self.m
        
        layer = Layer(m, name="The Layer", filename="layer", layertype=LayerTypePolyline)
        m.addLayer(layer)
        layer.open("w")

        line = CellElementPolyline(((16.185, 58.5912), (16.186, 58.5915)), objtype=2)
        layer.addCellElement(line)

        self.mi.close()

        ## Read back
        mi = MapImage(self.outimage)
        mi.open('r')

        m = mi.maps[0]

class LayerTestSimple(myTestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1")
        self.testdatadir = str(self.tempdir)

    def tearDown(self):
        del self.testdatadir

    def testSimple(self):
        map = createMap(self.testdatadir)
        map.open("a")

        streets,group = map.getLayerAndGroupByName("00_Streets")
        streets.open("a")

        expected = Set([CellElementPolyline(((16.1757486998903914, 58.5899908940009482), (16.1770312736989581, 58.5901528940066783), (16.1780288311056211, 58.5902788940111350)), objtype=3),
                        CellElementPolyline(((16.1770312736989581, 58.5901528940066783), (16.1766037490961025, 58.5908908940327819), (16.1764612408951507, 58.5911788940429688)), objtype=3),
                        CellElementPolyline(((16.1749649047851562, 58.5906388940238685), (16.1766037490961025, 58.5908908940327819), (16.1779575770051451, 58.5910528940385120)), objtype=3)])

        cell = streets.getCell(1)
        actual = Set([ce for ce in streets.getCellElements()])
        
        self.assertEqual(actual, expected)
        
class LayerTestAppend(myTestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata2")
        self.testdatadir = str(self.tempdir)

    def tearDown(self):
        del self.testdatadir

    def testAppendNonePolyline(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")

        streets,group = map.getLayerAndGroupByName("00_Streets")
        streets.open("a")
        expected = Set([ce for ce in streets.getCellElements()])
        streets.markCellModified(1)
        streets.close()
        del streets

        map = createMap(self.testdatadir)
        map.open()

        streets, group = map.getLayerAndGroupByName("00_Streets")
        streets.open("r")

        actual = Set([ce for ce in streets.getCellElements()])

        self.assertEqual(len(actual), len(expected))
        
        self.assertEqual(actual, expected)

    def testAppendNoneArea(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")

        parks, group = map.getLayerAndGroupByName("00_Parks")
        parks.open("a")
        expected = Set([ce for ce in parks.getCellElements()])
        parks.markCellModified(1)
        parks.close()
        del parks

        map = createMap(self.testdatadir)
        map.open()

        parks, group = map.getLayerAndGroupByName("00_Parks")
        parks.open("r")

        actual = Set([ce for ce in parks.getCellElements()])

        self.assertEqual(len(actual), len(expected))
        
        self.assertEqual(actual, expected)
    
    def testAppendStreet(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")

        streets, group = map.getLayerAndGroupByName("00_Streets")
        streets.open("a")

        actual = Set([ce for ce in streets.getCellElements()])
        expected = actual.copy()
        
        # Add a new street
        newstreet = CellElementPolyline(((16.185, 58.5912), (16.186, 58.5915)), objtype=2)
        newstreet.discretizeGeometry(streets.getCell(1))
        streets.addCellElement(newstreet)
        expected.add(newstreet)

        actual = Set([ce for ce in streets.getCellElements()])

        # Test if the new streets exists in the layer object
        self.assertEqual(actual, expected)
        
        # Test if the new street was written to file
        streets.close()
        del streets
        del map

        map = createMap(self.testdatadir)
        map.open()

        streets, group = map.getLayerAndGroupByName("00_Streets")
        streets.open("r")

#        actual = Set([ce.serialize(cell) for ce in streets.getCellElements()])
#        expected = Set([ce.serialize(cell) for ce in expected])
        actual = Set([ce for ce in streets.getCellElements()])
        expected = Set([ce for ce in expected])

        self.assertEqual(len(actual), len(expected))

        if actual != expected:
            for m in actual:
                if m.objtype == 2:
                    print streets.scale[0]
                    print m
                    print newstreet
                    print m==newstreet
        
        self.assertEqual(actual, expected, "Cell elements don't match after read back")

    def testAppendStreetGrow(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")

        streets, group = map.getLayerAndGroupByName("00_Streets")
        streets.open("a")

        # Add a new street
        newstreet = CellElementPolyline(((16.175, 58.5901), (16.176, 58.5905)), objtype=2)

        newbbox = newstreet.bboxrec.union(streets.bboxrec)
        newbbox = newbbox.buffer(streets.scale)
        
        streets.bboxrec = newbbox

        actual = Set([ce for ce in streets.getCellElements()])
        expected = actual.copy()
        
        newstreet.discretizeGeometry(streets.getCell(1))
#        streets.addCellElement(newstreet)
#        expected.add(newstreet)

        actual = Set([ce for ce in streets.getCellElements()])

        # Test if the new streets exists in the layer object
        self.assertEqual(actual, expected)
        
        # Test if the new street was written to file
        streets.close()
        del streets
        del map

        map = createMap(self.testdatadir)
        map.open(mode="a")

        streets, group = map.getLayerAndGroupByName("00_Streets")
        streets.open("r")

#        actual = Set([ce.serialize(cell) for ce in streets.getCellElements()])
#        expected = Set([ce.serialize(cell) for ce in expected])
        actual = Set([ce for ce in streets.getCellElements()])

        self.assertEqual(len(actual), len(expected))

        if actual != expected:
            print "difference:",actual.symmetric_difference(expected)
            print "actual: ",actual
            print "expected: ",expected

        
        self.assertEqual(actual, expected, "Cell elements don't match after read back")

    def testAppendPolygon(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")

        parks, group = map.getLayerAndGroupByName("00_Parks")
        parks.open("a")

        # Add a new park
        park = (((16.1837837893217511,58.5911206585042237),(16.1834987729198474,58.5916966585245973),(16.1834275188193715,58.5918046585284173),(16.1833562647188955,58.5918586585303274),(16.1843538221255585,58.5919486585335108),(16.1843894491757965,58.5911746585061337),(16.1844963303265104,58.5911206585042237),(16.1837837893217511,58.5911206585042237)),)
        newpark = CellElementArea(park, objtype=13)

        newbbox = newpark.bboxrec.union(parks.bboxrec)
        newbbox = newbbox.buffer(parks.scale)
        
#        parks.setBBoxRec(newbbox)

        actual = Set([ce for ce in parks.getCellElements()])
        expected = actual.copy()
        
        newpark.discretizeGeometry(parks.getCell(1))
        parks.addCellElement(newpark)
        expected.add(newpark)

        actual = Set([ce for ce in parks.getCellElements()])

        # Test if the new parks exists in the layer object
        self.assertEqual(actual, expected)
        
        # Test if the new street was written to file
        parks.close()
        del parks
        del map

        map = createMap(self.testdatadir)
        map.open(mode="a")

        parks, group = map.getLayerAndGroupByName("00_Parks")
        parks.open("r")

#        actual = Set([ce.serialize(cell) for ce in parks.getCellElements()])
#        expected = Set([ce.serialize(cell) for ce in expected])
        actual = Set([ce for ce in parks.getCellElements()])


class LayerTestAdd(myTestCase):
    def setUp(self):
        self.tempdir = TempDir()
        self.testdatadir = str(self.tempdir)
        self.map = createMap(self.testdatadir)
        self.map.open(mode="w")
        self.map.bbox = ((16.179984999999999, 58.591113999999997), (16.186159, 58.596420000000002))
        self.map.scale = N.array([1e-5, 1e-5])

    def testAddPolylineLayer(self):
        trails = Layer(self.map, name="Trails", filename="trails", layertype=LayerTypePolyline)
        trails.open(mode='w')
        self.map.addLayer(trails)

        # Add a new trail
        newtrail = CellElementPolyline(((16.185, 58.5912), (16.186, 58.5915)), objtype=0)
        newtrail.discretizeGeometry(trails.getCell(1))
        trails.addCellElement(newtrail)

        self.map.close()

        map = createMap(self.testdatadir)
        map.open()

        trails, group = map.getLayerAndGroupByName("Trails")

        trails.open('r')

        actual = Set(trails.getCellElements())

        expected = Set([newtrail])
        
        self.assertSetsEqual(actual, expected)

    def testAddPointLayer(self):

        points = Layer(self.map, name="Points", filename="points", layertype=LayerTypePoint)
        points.open(mode='w')
        self.map.addLayer(points)

        # Add a new point
        newpoint = CellElementPoint((16.185, 58.5912), objtype=10)
        newpoint.discretizeGeometry(points.getCell(1))
        points.addCellElement(newpoint)

        self.map.close()

        map = createMap(self.testdatadir)
        map.open()

        points, group = map.getLayerAndGroupByName("Points")

        points.open('r')

        actual = Set(points.getCellElements())

        expected = Set([newpoint])
        
        self.assertSetsEqual(actual, expected)
        
if __name__ == "__main__":
    unittest.main()
