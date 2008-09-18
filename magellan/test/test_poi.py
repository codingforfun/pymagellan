from Map import Map, MapTypeImage, createMap
import unittest
import tempfile
import shutil
import os
from CellElement import CellElementPOI
from sets import Set
from Cell import Cell
from SearchGroup import Feature, GroupNormal
from copy import copy,deepcopy
from Layer import Layer, LayerTypePolyline
from POI import POIGroup, FeaturePOI, POICategory, POISubCategory
from testutil import TempDir
from mapdir import MapDirectory

def dump(x):
    return " ".join(["0x%02x "%ord(c) for c in x])

def areSorted(x):
    tmp=copy(x)
    tmp.sort()
    return tmp == x

class POITest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata6")
        self.testdatadir = str(self.tempdir)

    def tearDown(self):
        del self.testdatadir

    def testSimple(self):
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('r')

        poigroup = map.getPOIGroup()
        poigroup.open('r')

        f = poigroup.getFeatureByIndex(0)
        aux = f.getAuxAsDict(poigroup)
        print f,aux

    def testAddPOI(self):
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('a')

        poigroup = map.getPOIGroup()
        poilayer = map.getPOILayers()[0]
        poigroup.open('a')

        print "nlevels", poilayer.nlevels
        
        catman = poigroup.getCategoryManager()
        cat = catman.getCategory(1)
        subcat = cat.getSubCategory(1)

        # Save number of pois in category 1
        cat1count = cat.getPOICount()
        self.assertEqual(cat1count, 5)

        wkt="POINT (16.185 58.5912)"
        poi=CellElementPOI(poilayer, categoryid=1, subcategoryid=1, wkt=wkt)
        poi.discretizeGeometry(poilayer.getCell(1))
        feature = FeaturePOI(poilayer.addCellElement(poi), ['Apmacken', '', '', '', '', ''], 1, 1)
        
        expected = Set([f for f in poigroup.getFeatures()]) | Set([feature])

        poigroup.addFeature(feature)

        actual = Set([f for f in poigroup.getFeatures()])

        self.assertEqual(actual, expected, "feature not present in poi group in memory")

        map.close()

        # Verify that the category statistics are updated
        self.assertEqual(cat.getPOICount(), cat1count+1)
        
        map = Map()
        map.open(os.path.join(self.testdatadir, "00map.ini"))

        poigroup = map.getPOIGroup()

        poigroup.open()

        actual = Set([f for f in poigroup.getFeatures()])

        self.assertEqual(len(actual), len(expected))

        if actual!=expected:
            print "actual:",actual
            print "expected:",expected

#        expected.sort(lambda x,y: cmp(x.name.upper(), y.name.upper()))

        self.assertEqual(actual, expected, "feature was not added correctly after read back")

        self.assertTrue(areSorted([(f.getCategoryId(), f.getSubCategoryId())  for f in poigroup.getFeatures()]),
                        "Feature are not sorted")

        # Verify that the category statistics are updated
        cat = poigroup.getCategory(1)
        print poigroup.getCategories()
        subcat = cat.getSubCategory(1)
        self.assertEqual(cat.getPOICount(), cat1count+1)

        f = poigroup.getFeatureByIndex(0)
        aux = f.getAuxAsDict(poigroup)
        print f,aux

    def testCategories(self):
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('a')

        poigroup = map.getPOIGroup()

        poigroup.open('a')

        catman = poigroup.getCategoryManager()

        print catman.getCategories()

        poigroup.close()

    def testAddCategory(self):
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('a')
        poigroup = map.getPOIGroup()
        poilayer = map.getPOILayers()[0]
#        poilayer.open('a')
        poigroup.open('a')
        map.close()
        map.writeImage("test.imi")
        
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('a')
        
        poigroup = map.getPOIGroup()

        poigroup.open('a')

        cat = POICategory("Aerials")
        cat.addField("POI Name")
        subcat = cat.addSubCategory(POISubCategory("NOSUB1000"))

        expected = deepcopy(poigroup.getCategories())+[cat]

        poigroup.addCategory(cat)

#        cat.addField

        actual = poigroup.getCategories()

        if actual != expected:
            print 'actual:',actual
            print 'expected:',expected

        self.assertEqual(actual,expected)

        map.close()

        map = createMap(self.testdatadir)
        map.open()

        poigroup = map.getPOIGroup()

        poigroup.open('r')

        catman = poigroup.getCategoryManager()
        
        print catman.getCategories()

        self.assertTrue("Aerials" in [cat.getName() for cat in catman.getCategories()])

        actual = poigroup.getCategories()

        if actual != expected:
            print 'actual:',actual
            print 'expected:',expected

#        expected.sort(lambda x,y: cmp(x.name.upper(), y.name.upper()))

        self.assertEqual(actual,expected)

    def testAddCategoryAndPOI(self):
        pass

class POICreate(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1", keep=True)
        self.testdatadir = str(self.tempdir)

    def testSimple(self):
        map = Map(MapDirectory(self.testdatadir), maptype=MapTypeImage)
        map.open('a')

        map.addPOIGroupAndLayer()
        poigroup = map.getPOIGroup()

        cat = POICategory("Aerials")
        cat.addField("POI Name")
        subcat = cat.addSubCategory(POISubCategory("NOSUB1000"))

        expected = [cat]

        poigroup.addCategory(cat)

#        cat.addField

        actual = poigroup.getCategories()

        if actual != expected:
            print 'actual:',actual
            print 'expected:',expected

        self.assertEqual(actual,expected)

        # Close map and try it to open it again
        map.close()

        map = Map()

        map = createMap(self.testdatadir)
        map.open()

        poigroup = map.getPOIGroup()

        poigroup.open('r')

        catman = poigroup.getCategoryManager()
        
        print catman.getCategories()

        self.assertTrue("Aerials" in [cat.getName() for cat in catman.getCategories()])

        actual = poigroup.getCategories()

        if actual != expected:
            print 'actual:',actual
            print 'expected:',expected

        self.assertEqual(actual,expected, "categories were not read back correctly")

#        expected.sort(lambda x,y: cmp(x.name.upper(), y.name.upper()))


        
if __name__ == "__main__":
    unittest.main()
