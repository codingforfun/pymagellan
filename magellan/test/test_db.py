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


class DBTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1",keep=True)
        self.testdatadir = self.tempdir.dir

    def tearDown(self):
        del self.testdatadir

    def testSimple(self):
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
        db.close()

        self.assertTrue('db00.dbd' in mapdir.listdir())

#        os.system('prdbd '+os.path.join(mapdir.dir, 'db00'))

        db = Database(mapdir, "db00", 'r')

        db.close()
        
        
class TableTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata2",keep=True)
        self.testdatadir = self.tempdir.dir

    def tearDown(self):
        del self.testdatadir

    def testOpenForAppend(self):
        random.seed(0)
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        table = db.getTableByName("R_GR0")

        databefore = [curs.getRow() for curs in table.getCursor(0)]
        rowcountbefore = table.getRowCount()

        self.assertEqual(rowcountbefore, 29)

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        table = db.getTableByName("R_GR0")

        dataafter = [curs.getRow() for curs in table.getCursor(0)]
        rowcountafter = table.getRowCount()

        self.assertEqual(rowcountbefore, rowcountafter)
        self.assertEqual(len(databefore), len(dataafter))
        self.assertEqual(databefore, dataafter)

    def testAddRows(self):
        random.seed(0)
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        table = db.getTableByName("R_GR0")

        rows = [curs.getRow() for curs in table.getCursor(0)]

        data = ["".join([chr(random.randint(0,255)) for i in xrange(table.rstruct.rt_len)]) for j in xrange(5)]

        newrows = [Row(table, data=d ) for d in data]

        for row in newrows:
            table.writeRow(row)

        self.assertEqual(table.getRowCount(), 29+5)

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        table = db.getTableByName("R_GR0")

        rowsafter = [curs.getRow() for curs in table.getCursor(0)]
        
        self.assertEqual(table.getRowCount(), 29+5)

        self.assertEqual(rows+newrows, rowsafter)

class FileTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = TempDir("./layerdata1",keep=False)
        self.testdatadir = self.tempdir.dir

    def tearDown(self):
        del self.testdatadir

    def testListFiles(self):
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')

    def testOpenAppend(self):
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        f = db.getFileByIndex(4)
        nslotsbefore = f.pz.next-1

        self.assertEqual(nslotsbefore, 3)
        
        slotdatabefore = [f.readSlot(i+1) for i in range(nslotsbefore)]

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        nslots = f.pz.next-1

        self.assertEqual(nslots, nslotsbefore)
        
        slotdata = [f.readSlot(i+1) for i in range(nslots)]

        self.assertEqual(len(slotdata), len(slotdatabefore))
        if slotdata != slotdatabefore:
            print "Equal elements", [a==b for a,b in zip(slotdatabefore, slotdata)]
        self.assertEqual(slotdata, slotdatabefore)

    def testOpenWrite(self):
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        f.close()
        f.open('w')
        nslotsbefore = f.pz.next-1

        self.assertEqual(nslotsbefore, 0)
        
        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        nslots = f.pz.next-1

        self.assertEqual(nslots, 0)

    def testWritePage(self):
        random.seed(0)
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        f = db.getFileByIndex(4)
        npages = f.npages
        pagesize = f.fstruct.ft_pgsize

        writtendata = "".join([chr(random.randint(0,255)) for i in xrange(pagesize)])
#        import pdb
#        pdb.set_trace()
        ## Override incomplete page
        f.writePage(writtendata,1)

        ## Update pz.next so that the incomplete_page buffer won't overwrite the written page
        f.pz.next = f.fstruct.ft_slots*f.page+1
        assert(f.page == 2)
        assert(f.relslotnum == 0)

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        self.assertEqual(f.readPage(1), writtendata)

    def testWriteSlot(self):
        random.seed(0)
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        f = db.getFileByIndex(4)
        nslots = f.pz.next-1

        slotdatabefore = [f.readSlot(i+1) for i in range(nslots)]

        slotsize = f.fstruct.ft_slsize
        writtendata = "".join([chr(random.randint(0,255)) for i in xrange(slotsize)])
        slot = 2
        f.writeSlot(writtendata, slot)

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        slotdata = [f.readSlot(i+1) for i in range(nslots)]

        slotdataexpected = slotdatabefore
        slotdataexpected[slot-1] = writtendata
        
        self.assertEqual(slotdataexpected, slotdata)

    def testWriteNewSlot(self):
        random.seed(0)
        db = Database(MapDirectory(self.testdatadir), "db00", 'a')
        f = db.getFileByIndex(4)
        nslots = f.pz.next-1

        slotdatabefore = [f.readSlot(i+1) for i in range(nslots)]

        slotsize = f.fstruct.ft_slsize
        writtendata = "".join([chr(random.randint(0,255)) for i in xrange(slotsize)])

        f.writeSlot(writtendata)

        db.close()

        ## Read back
        db = Database(MapDirectory(self.testdatadir), "db00", 'r')
        f = db.getFileByIndex(4)
        nslots = f.pz.next-1
        slotdata = [f.readSlot(i+1) for i in range(nslots)]

        slotdataexpected = slotdatabefore + [writtendata]
        
        self.assertEqual(len(slotdataexpected), len(slotdata))
        if slotdataexpected != slotdata:
            print "Equal elements", [a==b for a,b in zip(slotdataexpected, slotdata)]
        self.assertEqual(slotdataexpected, slotdata)

                
            
if __name__ == "__main__":
    unittest.main()
