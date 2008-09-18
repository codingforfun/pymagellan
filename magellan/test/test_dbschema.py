from Map import Map
from DBUtil import Database, AuxTableManager, Row
from mapdir import MapDirectory
import unittest
import tempfile
import shutil
import os
import random
from testutil import TempDir
import struct


from sets import Set


class DBSchemaTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1",keep=True)
        self.testdatadir = self.tempdir.dir

    def tearDown(self):
        del self.testdatadir

    def testOpen(self):
        db = Database(MapDirectory(self.testdatadir), "db00")

        table = db.getTableByName("R_GR0")

        for curs in table.getCursor(0):
            row = curs.getRow()

            aux = db.getTableByName("AUX_GR0")

            am = AuxTableManager(aux)

            index = row.asDict()['NAME_REF']&0xffffff
            offset = row.asDict()['NAME_REF']>>24

    def testAuxIndex(self):
        db = Database(MapDirectory(self.testdatadir), "db00")

        table = db.getTableByName("R_GR0")
        aux = db.getTableByName("AUX_GR0")

        rows = [x.getRow() for x in aux.getCursor(0)]
        index = rows[0].asDict()['NAME_BUF']

        n = len(index)/4
        index = struct.unpack('%dI'%n, index)

    def testAddData(self):
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        table = db.getTableByName("R_GR0")

        beforedata = [curs.getRow().asList() for curs in table.getCursor(0)]
            
        ## Add an empty row
        refrow = Row(table)
        refrow.setColumn(0,1)
        table.writeRow(refrow)

        refdata = refrow.asList()
        
        db.close()

        db = Database(MapDirectory(self.testdatadir),"db00")
        table = db.getTableByName("R_GR0")

        aux = db.getTableByName("AUX_GR0")
        am = AuxTableManager(aux)

        afterdata = [curs.getRow().asList() for curs in table.getCursor(0)]

        for curs in table.getCursor(0):
            row = curs.getRow()

            index = row.asDict()['NAME_REF']&0xffffff
            offset = row.asDict()['NAME_REF']>>24
            
        self.assertEqual(beforedata+[refdata], afterdata)

    def testCreateDatabase(self):
        mapdir = MapDirectory()
        db = Database(mapdir, "db00", 'w')
