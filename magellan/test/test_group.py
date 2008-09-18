import unittest
import tempfile
import shutil
import os
from sets import Set
from copy import copy
from testutil import TempDir

from magellan.Map import Map, createMap
from magellan.CellElement import CellElementPolyline
from magellan.Cell import Cell
from magellan.SearchGroup import Feature,FeatureNormal,FeatureStreet, \
     GroupNormal
from magellan.Layer import Layer, LayerTypePolyline

def dump(x):
    return " ".join(["0x%02x "%ord(c) for c in x])

def areSorted(x):
    tmp=copy(x)
    tmp.sort()
    return tmp == x

class GroupNormalTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata2", keep=True)
        self.testdatadir = str(self.tempdir)

    def tearDown(self):
        del self.testdatadir

    def testSimple(self):
        map = createMap(self.testdatadir)
        map.open()

        roads = map.getGroupByName("00_Roads")

        roads.open('r')

        for i in range(0, roads.getFeatureCount()):
            feature = roads.getFeatureByIndex(i)
#            print feature


    def testAddFeature(self):
        map = createMap(self.testdatadir)
        map.open(mode='a')

        roads = map.getGroupByName("00_Roads")

        roads.open('a')

        streets, streetsgroup = map.getLayerAndGroupByName("00_Streets")

        nfeatures=roads.getFeatureCount()
        self.assertEqual(roads.getFeatureCount(), 29)
        
        newstreetwkt = "LINESTRING (16.185 58.5912, 16.186 58.5915)"
        newstreet = CellElementPolyline(streets, wkt=newstreetwkt)
        newstreet.discretizeGeometry(streets.getCell(1))
        cellelementrefs = streets.addCellElement(newstreet)

        feature = FeatureStreet(name="Apgatan",
                                layerindex=map.getLayerIndex(streets),
                                objtype=29,
                                cellelementreflist=cellelementrefs)

        roads.addFeature(feature)

        # Check that the # of features increased
        self.assertEqual(roads.getFeatureCount(), nfeatures+1)

        found=False
        for i in range(0, roads.getFeatureCount()):
            tmpfeature = roads.getFeatureByIndex(i)
            if tmpfeature == feature:
                print feature
                found = True
        self.assertTrue(found, "New feature not found")        

        names = [roads.getFeatureByIndex(i).name for i in range(0, roads.getFeatureCount())]

        self.assertTrue(areSorted(names), "Features are not sorted")

        print roads.layers

        # Re-open map and verify that the new feature is present
        map.close()
        del map
        del streets
        
        map = createMap(self.testdatadir)
        map.open()
        roads = map.getGroupByName("00_Roads")

        print roads.layers

        roads.open('r')

        found = False
        for i in range(0, roads.getFeatureCount()):
            tmpfeature = roads.getFeatureByIndex(i)
            print tmpfeature
            if tmpfeature.name == feature.name:
                streets, streetsgroup = map.getLayerAndGroupByName("00_Streets")
                if tmpfeature == feature:
                    found = True

        # Check that the # of features increased
        self.assertEqual(roads.getFeatureCount(), nfeatures+1)

        self.assertTrue(found, "New feature not found after re-opening the map")        
        names = [roads.getFeatureByIndex(i).name for i in range(0, roads.getFeatureCount())]
        self.assertTrue(areSorted(names), "Features are not sorted")
        
    def testAddGroup(self):
        map = createMap(self.testdatadir)
        map.open(mode='a')
        map.bigendian = True

        trailgroup = GroupNormal(map, name="00_Trails")

        map.addGroup(trailgroup)

        trailgroup.open("w")

        # Add trail layer and feature to new group
        trails = Layer(map, name="00_Trails", filename="00trails", layertype=LayerTypePolyline)
        trails.open(mode='w')
        map.addLayer(trails)

        trails.setXScale(1e-5)
        trails.setYScale(1e-5)

        trailgroup.addLayer(trails)
        
        newtrailwkt = "LINESTRING (16.185 58.5912, 16.186 58.5915)"
        newtrail = CellElementPolyline(trails, wkt=newtrailwkt)
        newtrail.discretizeGeometry(trails.getCell(1))
        cellelementrefs = trails.addCellElement(newtrail)
        feature = FeatureNormal(name="Apgatan", layerindex=map.getLayerIndex(trails),
                                objtype=29,
                                cellelementreflist=cellelementrefs)
        trailgroup.addFeature(feature)

        map.writeImage('trails.img')
        
        map.close()

        os.system("cat " +os.path.join(self.testdatadir, "00map.ini"))

        map = createMap(self.testdatadir)
        map.open('r')

        trailgroup = map.getGroupByName("00_Trails")

        trailgroup.open()
        
        print "Trails",trails

    def testOpenForAppend(self):
        ## Open for read-only and read features
        map = createMap(self.testdatadir)
        map.open()

        roads = map.getGroupByName("00_Roads")

        roads.open('r')

        reffeatures = [roads.getFeatureByIndex(i) for i in range(0, roads.getFeatureCount())]

        map.close()
        del map

        ## Open for append
        map = createMap(self.testdatadir)
        map.open('a')
        roads = map.getGroupByName("00_Roads")
        roads.open('a')
        map.close()
        del map

        ## Open for read-only again to see if the features are still there
        map = createMap(self.testdatadir)
        map.open()

        roads = map.getGroupByName("00_Roads")

        roads.open('r')

        features = [roads.getFeatureByIndex(i) for i in range(0, roads.getFeatureCount())]

        self.assertEqual(len(features), len(reffeatures))
                
        self.assertEqual(features, reffeatures)
        
if __name__ == "__main__":
    unittest.main()
