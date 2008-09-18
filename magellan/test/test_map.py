from magellan.Map import Map, createMap, MapTypeImage, MapImage
import unittest
import os
from magellan.CellElement import CellElementPolyline
from magellan.SearchGroup import Feature,FeatureNormal,FeatureStreet, GroupNormal
from magellan.Layer import Layer,LayerTypePolyline, DetailMapLayerStyle
from sets import Set
from shapely.geometry import Point, LineString, Polygon
from testutil import TempDir
from magellan.mapdir import MapDirectory, Image

class CreateMapTest(unittest.TestCase):
    def setUp(self):
        self.testdatadir = TempDir()

    def tearDown(self):
        del self.testdatadir


    def testSimple(self):
        refmap = Map(MapDirectory('./layerdata8'))
        refmap.open('r')
        reflayer = refmap.getLayerByName('00_Trails_4WD')
        reflayer.open('r')
        
        map = Map(MapDirectory(self.testdatadir.dir), maptype=MapTypeImage)
        map.open("w")
        map.bbox = ((-18.04, 28.4), (-17.7, 28.89))
        map.bbox = refmap.bbox

        ## Add trails layer
        trails = Layer(map, name="00_Trails", filename="00trails", layertype=LayerTypePolyline)
        trails.open(mode='w')
        trailstyle = DetailMapLayerStyle()
        trailstyle.style = 'TRAIL_LINE'
        map.addLayer(trails, layerstyle = trailstyle)

        trailwkt = 'LINESTRING (-17.768953959275908 28.775591075650038,-17.768678531255482 28.7757692937809,-17.768346397466143 28.775890806142854,-17.767981860380281 28.775923209439377,-17.767779339777025 28.775923209439377,-17.767212282087907 28.775874604494597,-17.766669526871183 28.775777394605033,-17.766151074126846 28.775647781418947,-17.765438201603384 28.775388555046781,-17.764879244738399 28.775145530322874,-17.764514707652538 28.774943009719617,-17.764239279632111 28.77467568252332,-17.763040357660834 28.774238238020288,-17.762813534585188 28.774189633075505,-17.762513804092368 28.774222036372027,-17.762513804092368 28.774222036372027)'
        trail = CellElementPolyline(trails, wkt=trailwkt, objtype=11)
        cellelementrefs = trails.addCellElement(trail)
        print "cellelementrefs", cellelementrefs

        ## Add group
        roadsgroup = map.getGroupByName('00_Roads')
        roadsgroup.addLayer(trails)
        feature = FeatureNormal(name="Apstigen", layerindex=map.getLayerIndex(trails),
                                objtype=29,
                                cellelementreflist=cellelementrefs)
        roadsgroup.addFeature(feature)

        ## Add topo
        map.addTopo('layerdata8/00t0.blx')
#        map.mapdir.copyfile('layerdata8/topo3d.ini')
        map.close()
        
        map.writeImage('trails.imi')
        
        self.assertTrue('00map.ini' in os.listdir(self.testdatadir.dir))

        files = os.listdir(self.testdatadir.dir)
        expectedfiles = Set(('bmp2bit.ics', 'bmp4bit.ics', '00map.ini', 'add_maps.cfg', 'db00.dbd' ,
                             '00trails.lay', '00trails.clt',
                             'gr0.ext', 'gr0.clp', 'gr0.aux',
                             'gr1.ext', 'gr1.clp', 'gr1.aux',
                             'gr2.ext', 'gr2.clp', 'gr2.aux',
                             'gr3.ext', 'gr3.clp', 'gr3.aux',
                             '00z.dat', '00cn.dat',
                             '00t0.blx', 'topo3d.ini'))
        self.assertEqual(expectedfiles, Set(files))

        expectedinitfile = ""

        inifile = open(os.path.join(self.testdatadir.dir, '00map.ini'))

        print inifile.read()

        map = Map(MapDirectory(self.testdatadir.dir))
        map.open("r")
        roadsgroup = map.getGroupByName('00_Roads')
        roadsgroup.open('r')
        print "features: ", list(roadsgroup.getFeatures())
        trails = map.getLayerByName('00_Trails')
        trails.open('r')
        trails.check()
        print trails.cellnumbers
#        print repr(trails), repr(reflayer)
        
    def testCreateMapImage(self):
        imagefile = os.path.join(self.testdatadir.dir, 'test.imi')
        mi = MapImage(imagefile)
        mi.open('w')
        m = mi.createMap()
        mi.close()
        img = Image(imagefile)

        self.assertTrue('bmp4bit.ics' in img.listdir())
        self.assertTrue('add_maps.cfg' in img.listdir())
        self.assertTrue('00map.ini' in img.listdir())

class MapTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata8")
        self.testdatadir = str(self.tempdir)

    def tearDown(self):
        del self.testdatadir

    def testOpenForAppend(self):
        map = createMap(self.testdatadir)
        map.open(mode="a")
        map.close()
        map.writeImage('test8.imi')
        print map.getLayerNames()
        freeways = map.getLayerByName('00_Edificio')
        freeways.open('r')

        print freeways.nlevels
        print freeways.cellnumbers

        print repr(freeways)

class MapConsistency(unittest.TestCase):
    """Test map consistency of a range of maps"""
    mapimages =  ['Tenerife3D.imi', 'LPalma3D.imi', 'Omr8.imi', 'greece.img', 'NavarraGS.imi', 'fullpv.imi', 'gredos.imi', 'picoseu.imi',
                  'Balears2D.imi', 'AstTopo3D.imi', 'Gouda.imi',
                  'cuenca2.imi', 'lund.imi', 'romania.imi', 'out.imi',
                  'Eu_1_02.img'
                  ]
    def testLayerStyle(self):
        """Test layer style consistency"""
        try:
            for mapfile in self.mapimages:
                img = Image(os.path.join('.','images',mapfile))
                m = Map(img)
                m.open('r')

                for layername in m.getLayerNames():
                    style = m.getLayerStyleByName(layername)
                    style.verify(layername, m)
                m.close()
        finally:
            img.__del__()

if __name__ == "__main__":
    unittest.main()

