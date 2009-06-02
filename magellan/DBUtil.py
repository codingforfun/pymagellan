import DBSchema
from DBSchema import FTFlagsCompressed
import os
import struct
import zlib
import tempfile
import shutil

def sortHashFunc(name):
    """Hash function used for indexing auxillary string tables and POI categories"""
    if name == None:
        return None
    b = ord(name.upper()[0])

    if (0x30 <= b) and (b <= 0x39):
        return b-0x30+1
    elif (0x41 <= b) and (b <= 0x5a):
        return b-0x41+12
    else:
        return 0

def sortHashFuncFast(name):
    """Quicker version of sortHashFunc()"""
    
    if name == None:
        return None
    else:
        return ord(name[0].translate(sorthashtable))

sorthashtable = ''.join([chr(sortHashFunc(chr(i))) for i in range(256)])

class Database(object):
    def __init__(self, mapdir, filename, mode='r', bigendian=False):
        self.compressed = False

        self.mapdir = mapdir
        
        self.path = os.path.dirname(filename)

        self._name = filename

        self.mode = mode

        self.bigendian = bigendian

        self._schema = DBSchema.DatabaseSchema()
        if mode in ['r', 'a']:
            dbd = self.mapdir.open(filename+".dbd","rb")
            try:
                self.schema.deSerialize(dbd.read(), self.bigendian)
            except DBSchema.InvalidDatabase:
                # If problems, try with the other endian
                self.bigendian = not self.bigendian
                dbd.seek(0)
                self.schema.deSerialize(dbd.read(), self.bigendian)

        self.files = []
        for i in range(0, len(self.schema.filetable)):
            if self.schema.filetable[i].ft_type == ord('d'):
                self.files.append(File(self, i))
            else:
                self.files.append(None)

        self.tables = [Table(self, i) for i in range(0, len(self.schema.recordtable))]
        self.sets = [Set(self, i) for i in range(0, len(self.schema.settable))]

        for file in self.files:
            if file != None:
                file.open(mode)


    ## Schema editing methods
    def addTable(self, name, filename, fieldstructlist):
        """Add table to database"""
        if self.mode in ['w','a']:
            self.schema.addRecordStruct(name=name, filename=filename,
                                        fieldstructlist=fieldstructlist,
                                        compressed=self.compressed)
            self._schemaUpdated()
            table = self.getTableByName(name)
            table.setMode('w')
            return table
    def addSet(self, name, owner, members, sortfields=None, order=DBSchema.SetSortOrderLast):
        """Add set to database schema.

        Arguments:
        name: Set name
        owner: Owner table
        memberlist: List of members (Table objects)
        sortfields: lists of sort field names for each member table (list of lists of integer)
        order: sort order

        """
        ## Create member list
        if sortfields != None:
            memberlist = []
            for mem, sortfieldnames in zip(members, sortfields):
                memberlist.append(DBSchema.MemberStruct(self.getTableIndex(mem),
                                                        [mem.getColumnIndex(field) for field in sortfieldnames]))
        else:
            memberlist = [DBSchema.MemberStruct(self.getTableIndex(mem), []) for mem in members]

        self._schema.addSet(name, self.getTableIndex(owner), memberlist, order)
        self._schemaUpdated()
        return self.getSetByName(name)

    @property
    def schema(self):
        """Return database schema"""
        return self._schema

    ## Table access methods
    def getTableNames(self):
        return [rt.name for rt in self.schema.recordtable]

    def getTableIndex(self, table):
        return self.tables.index(table)

    def getTableByIndex(self, index):
        return self.tables[index]

    def getTableByName(self, name):
        for t in self.tables:
            if t.name == name:
                return t
        raise ValueError("There is no table with name %s"%name)

    ## Set access methods
    def getSetNames(self):
        return [st.name for st in self.schema.settable]

    def getSets(self):
        return self.sets
    
    def getSetByIndex(self, index):
        return self.sets[index]

    def getSetByName(self, name):
        for i,s in enumerate(self.schema.settable):
            if s.name == name:
                return self.sets[i]

    # Low-level file access methods
    # TODO: could some of them be removed??
    def getFileIndex(self, file): return self.files.index(file)
    def getFileByIndex(self, index): return self.files[index]
    def readSlot(self, dbaddr):
        return self.files[dbaddr.filenum].readSlot(dbaddr.slot)
    def writeSlot(self, data, dbaddr=None):
        return self.files[dbaddr.filenum].writeSlot(data, dbaddr.slot)

    def close(self):
        ## Write schema
        if self.schema and self.mode in ('a','w'):
            dbd = self.mapdir.open(self._name + ".dbd", "wb")
            dbd.write(self.schema.serialize(self.bigendian))
            dbd.close()

        if self.files:
            for file in self.files:
                if file:
                    file.close()
            self.files = None

        del self.tables
        self.tables = None
        del self.sets
        self.sets = None
        self._schema = None

    ## Database properties
    @property
    def name(self):
        """Name of database"""
        return self._name

    ### Low-level data [un-]packing methods
    def unpack(self,types,data):
        if self.bigendian:
            structendian = '>'
        else:
            structendian = '<'
        return struct.unpack(structendian + types,data)

    def pack(self,types,*data):
        if self.bigendian:
            structendian = '>'
        else:
            structendian = '<'
        return apply(struct.pack, (structendian+types,) + data)

    def _schemaUpdated(self):
        """Internal method which updates the internal state when the schema has been
        changed"""
        self.tables = [Table(self, i) for i in range(0, len(self.schema.recordtable))]
        self.files = [File(self, i) for i in range(0, len(self.schema.filetable))]
        self.sets = [Set(self, i) for i in range(0, len(self.schema.settable))]

        
class File:
    def __init__(self, db, index):
        self.index = index
        self.db = db
        self.fstruct = db.schema.filetable[index]
        self.fs = None
        self.tempfile = None
        self.lastpage = None
        self.pz = DBSchema.FilePageZeroStruct()
        self.open_state = False
        self.compressed = (self.fstruct.ft_flags & FTFlagsCompressed) != 0

        self.incomplete_page = ''

        self.cfile = None
        if self.compressed:
            self.cfile = File(db, index+1)

    @property
    def npages(self):
        """Number of pages"""
        return ((self.pz.next-1)+self.fstruct.ft_slots-1) / self.fstruct.ft_slots + 1
    

    @property
    def relslotnum(self):
        return (self.pz.next-1+self.fstruct.ft_slots) % self.fstruct.ft_slots

    @property
    def page(self):
        return (self.pz.next-1)/self.fstruct.ft_slots+1

    @property
    def name(self):
        return self.fstruct.ft_name
    
    def isOpen(self): return self.open_state
        
    def open(self, mode='r'):
        if not self.open_state:
            self.mode = mode

            filepath = os.path.join(self.db.path, self.fstruct.ft_name)
            self.fs = None

            if self.compressed:
                ## In write and append mode the file contents is written to
                ## a temporary file
                if mode in ['w','a']:
                    self.tempfile = tempfile.mkstemp()[1]
                    ## copy contents if file is opened in append mode
                    if mode == 'a':
                        srcfile = File(self.db, self.db.getFileIndex(self))
                        srcfile.open('r')
                        tmpfs = open(self.tempfile, 'w')

                        for pagenum in xrange(srcfile.npages):
                            data = srcfile.readPage(pagenum)
                            
                            tmpfs.write(data)
                        srcfile.close()
                        tmpfs.close()
                        self.fs = open(self.tempfile, 'r+b')
                    else:
                        self.fs = open(self.tempfile, 'w+b')
                elif mode == 'r':
                    self.cfile.open("r")

            if self.fs == None:
                if mode=='a':
                    self.fs = self.db.mapdir.open(filepath, 'r+b')
                elif mode == 'w':
                    self.fs = self.db.mapdir.open(filepath, 'w+b')
                else:
                    self.fs = self.db.mapdir.open(filepath, mode+'b')

            ## Read zero page
            if mode in ['r','a']:
                pzdata = self.fs.read(self.pz.structSize())
                self.pz.deSerialize(pzdata, self.db.bigendian)
            elif mode == 'w':
                self.pz = DBSchema.FilePageZeroStruct()
                self.writePage(self.padPagedata(self.pz.serialize(self.db.bigendian)), 0)
                self.incomplete_page = ''
            if mode == 'a':
                if self.relslotnum > 0:
                    end = self.relslotnum * self.fstruct.ft_slsize + 4
                    self.incomplete_page = self.readPage(self.page)[4:end]
                else:
                    self.incomplete_page = ""
            self.open_state = True

    def padPagedata(self, data):
        data = data[0:self.fstruct.ft_pgsize]
        data = data + (self.fstruct.ft_pgsize-len(data)) * chr(0)
        return data        

    def close(self):
        if self.open_state:

            # If opened for write, write back zeropage and unwritten slots
            if self.mode in ['a','w']:
                ## Write zeropage
                self.writePage(self.padPagedata(self.pz.serialize(self.db.bigendian)), 0)
                if self.relslotnum > 0:
                    self.writePage(struct.pack("i",0) +
                                   self.incomplete_page)

            if self.fstruct.ft_flags & FTFlagsCompressed:
                if self.tempfile != None:
                    filepath = os.path.join(self.db.path, self.fstruct.ft_name)
                    fsout = self.db.mapdir.open(filepath, "wb")
                    self.cfile.open("w")
                    
                    self.fs.seek(0)

                    data = self.fs.read(self.fstruct.ft_pgsize)
                    tpz = DBSchema.FilePageZeroStruct()
                    tpz.deSerialize(data, self.db.bigendian)
                    fsout.write(data) # Write page zero
                    for pagenum in xrange(self.npages-1):
                        data = self.fs.read(self.fstruct.ft_pgsize)
                        cdata = zlib.compress(data, 9)
                        assert len(cdata) < 2**16
                        self.cfile.writeSlot(self.db.pack("IHH", fsout.tell(), len(cdata), 0x2f))
                        fsout.write(cdata)

                    self.fs.close()
                    os.unlink(self.tempfile)
                    self.tempfile = None
                    fsout.close()
                    
                self.cfile.close()

            self.fs.close()

            self.open_state = False

    def readSlot(self, slot):
        if slot == 0:
            raise ValueError("There is no slot zero")
        if slot >= self.pz.next:
            raise ValueError, "Trying to read from an non-existent slot (%d)"%slot        
        page = ((slot-1)/self.fstruct.ft_slots)+1
        offset = self.fstruct.ft_slsize*((slot-1+self.fstruct.ft_slots) %
                                  self.fstruct.ft_slots)+4
        address = page * self.fstruct.ft_pgsize + offset

        data = self.readPage(page)

        return data[offset:offset+self.fstruct.ft_slsize]

    def readPage(self, pagenum):
        if pagenum >= self.npages:
            raise ValueError, "Trying to read from an non-existent page (%d/%d)"%(pagenum,self.npages)
        
        if self.compressed and self.mode == 'r' and pagenum>0:
            data = self.cfile.readSlot(pagenum)

            [newpos, size, tmp] = self.db.unpack("ihh", data)

            if newpos==0:
                raise ValueError, \
                      "Invalid compressed data position lookup file size=0x%x pagenum=0x%x"%(newpos,pagenum)

            self.fs.seek(newpos)
            cdata = self.fs.read(size)
            data = zlib.decompress(cdata)
                        
        else:
            if self.mode=='w' and self.page == pagenum:
                return self.db.pack("i",0) + self.incomplete_page
            self.fs.seek(pagenum * self.fstruct.ft_pgsize)
            data = self.fs.read(self.fstruct.ft_pgsize)

        return data

    def writePage(self, data, pagenum=None):
        if pagenum == None:
            pagenum = self.page    

        self.fs.seek(pagenum * self.fstruct.ft_pgsize)
           
        self.fs.write(self.padPagedata(data))

        return pagenum

    def writeSlot(self, data, slot=None):
        if slot == 0:
            raise ValueError("There is no slot zero")

        data = data[0:self.fstruct.ft_slsize]
        data = data + (self.fstruct.ft_slsize-len(data)) * chr(0)

        if slot != None:
            if slot >= self.pz.next:
                raise ValueError, "Trying to write to a non-existent slot (%d)"%slot        
            page = ((slot-1)/self.fstruct.ft_slots)+1
            offset = self.fstruct.ft_slsize*((slot-1+self.fstruct.ft_slots) %
                                      self.fstruct.ft_slots)+4
            if page < self.page:
                pagedata = self.readPage(page)
                pagedata = pagedata[0:offset]+data+pagedata[offset+len(data):]
                self.writePage(pagedata, page)
            else:
                self.incomplete_page = self.incomplete_page[0:offset-4] + data + self.incomplete_page[offset-4+len(data):]

            return slot
        else:
            self.incomplete_page += data

            pagenum = self.page
            
            self.pz.next += 1

            if self.relslotnum == 0:
                self.writePage(self.db.pack("i",0)+self.incomplete_page, pagenum)
                self.incomplete_page = ""

        return slot
        

    def getNextDBAddr(self):
        return DBAddress(self.index, self.pz.next)
    
    def __del__(self):
        try:
            self.close()
        finally:
            if self.tempfile:
                os.unlink(self.tempfile)

class SetMember:
    def __init__(self, set, index):
        self.set = set
        self.db = set.db
        self.mrec = set.db.schema.membertable[index]
        
    @property
    def table(self):
        return self.db.getTableByIndex(self.mrec.mt_record)

    @property
    def ptr(self):
        return self.mrec.mt_mem_ptr

    def __repr__(self):
        return str(self.mrec)


class Set:
    def __init__(self, db, setindex):
        self.db = db
        self.setindex = setindex

        self.srec = self.db.schema.settable[setindex]

        self.order = self.srec.st_order

        self.members = [SetMember(self, i)
                        for i in range(self.srec.st_members,
                                       self.srec.st_members+self.srec.st_memtot)]

    @property
    def name(self):
        return self.srec.name

    def getOwnerTable(self):
        return self.db.getTableByIndex(self.srec.st_own_rt)

    def getMemberCount(self):
        return len(self.members)

    def getMemberByIndex(self, index):
        return self.members[index]

    def getMemberByName(self, name):
        for m in self.members:
            if m.table.name == name:
                return m

    def getMembers(self):
        return self.members

    @property
    def ptr(self):
        """Get owner pointer"""
        return self.srec.st_own_ptr

    def __repr__(self):
        res = ["name: "+self.name]
        res += ["owner: "+str(self.getOwnerTable())]
        res += ["members: "+ str([m.table for m in self.getMembers()])]
        res += ["rec:"+str(self.srec)]
        res += ["order:"+chr(self.order)]
        return ",".join(res)

class Cursor:
    def __init__(self, table, index):
        self.table = table
        self.index = index

    def __iter__(self):
	return self

    def next(self):
        if self.index == self.table.getRowCount():
            raise StopIteration
        else:
            self.index+=1
            return Cursor(self.table, self.index-1)

    def asList(self):
        return self.getRow().asList()

    def asDict(self):
        return self.getRow().asDict()

    def getSetItemCount(self, setmember):
        setptr = setmember.set.ptr

        data = self.getRow().data

        (setnmembers,setfirst,setlast) = self.table.db.unpack("III", data[setptr:setptr+12])

        return setnmembers

    def getSetItems(self, setmember):
        """Get a cursor to the items in a set member"""

        db = self.table.db

        ## Get member table
        membertable = setmember.table

        ownerptr = setmember.set.ptr
        data = self.getRow().data
        (setnmembers, setfirst, setlast) = db.unpack("III", data[ownerptr:ownerptr+12])
        
        if setnmembers==0:
            return []
        
        firstaddr = DBAddress.fromint(setfirst)
        lastaddr = DBAddress.fromint(setlast)

        assert(firstaddr.getFile(db) == membertable.getFile())
        assert(lastaddr.getFile(db) == membertable.getFile())

        return SetMemberCursor(membertable, firstaddr.slot-1, setmember, 
                               membertable, lastaddr.slot-1, setnmembers)

    def addSetItem(self, setmember, itemcursor):
        if self.table.mode != 'w':
            raise ValueError("Table must be opened in write mode")
        
        db = self.table.db
        
        slot = itemcursor.index + 1
        
        setptr = setmember.set.ptr

        data = self.getRow().data

        # Set owner data
        db = self.table.db
        (setnmembers,setfirst,setlast) = db.unpack("III", data[setptr:setptr+12])

        if setnmembers==0:
            setfirst=setlast=int(itemcursor._getDbAddress())
            setnmembers=1

            # Update member pointer of last member to point to new member
            itemcursor._setSetMemberData(setmember,newowner=self)
        else:
            last = SetMemberCursor(setmember.table, DBAddress.fromint(setlast).slot - 1, setmember)

            setlast = int(itemcursor._getDbAddress())
            setnmembers+=1

            # Update member pointer of last member to point to new member
            last._setSetMemberData(setmember,newnext=itemcursor)
            itemcursor._setSetMemberData(setmember,newowner=self, newprev=last)

        data = data[0:setptr] + db.pack("III", setnmembers,setfirst,setlast) + data[setptr+12:]

        self.table.getFile().writeSlot(data, self.index + 1)
        
    def getTable(self):
        return self.table

    def getRow(self):
        return Row(self.table, self.table.getFile().readSlot(self.index+1))

    def _setSetMemberData(self, setmember, newowner=None, newprev=None, newnext=None):
        data = self.getRow().data

        db = self.table.db

        memptr = setmember.ptr

        (owner, prev, next) = db.unpack("III", data[memptr:memptr+12])

        if newowner:
            owner = int(newowner._getDbAddress())
        if newprev:
            prev = int(newprev._getDbAddress())
        if newnext:
            next = int(newnext._getDbAddress())

        data = data[0:memptr] + db.pack("III", owner, prev, next)+data[memptr+12:]

        self.table.getFile().writeSlot(data, self.index + 1)
        
    def _getDbAddress(self):
        return DBAddress(self.table.getFile().index, self.index + 1)

class SetMemberCursor(Cursor):
    def __init__(self, table, index, setmember, lasttable=None, lastindex=None, n=None):
        Cursor.__init__(self, table, index)
        self.setmember = setmember
        self.first=True
        self.lasttable=lasttable
        self.lastindex=lastindex
        self.n = n
        self.count=0

    def next(self):
        
        db = self.table.db

        data = self.getRow().data
        memptr = self.setmember.ptr

        (owner, prev, next) = [DBAddress.fromint(x) for x in db.unpack('III', data[memptr:memptr+12])]

        assert(owner.getFile(db) == self.setmember.set.getOwnerTable().getFile())
        assert(prev.iszero() and prev.iszero() or prev.getFile(db) == self.setmember.table.getFile())
        assert(next.iszero() or next.getFile(db) == self.setmember.table.getFile())
        
        if self.first:
            self.first = False
            self.count += 1
            return self
        else:
            if not next.iszero():
                assert(next.getFile(db), self.setmember.table.getFile())

                self.index = next.slot - 1

                self.count+=1

                return self
            else:
                if not (self.table == self.lasttable and self.index==self.lastindex and self.count==self.n):
                    raise Exception("Set member chain corrupted")
                raise StopIteration

class Table(object):
    def __init__(self, db, index):
        self.index = index
        self.db = db

        self.rstruct = self.db.schema.recordtable[index]
        
        self._name = self.rstruct.name

    def __hash__(self, b):
        return hash(self.name)

    def __eq__(self, b):
        return cmp(self.name, b.name)==0

    def setMode(self, mode):
        """Set access mode for table. Possible values are 'r','w' and 'a' where 'r' is
        read-only, 'w' is write (will delete all existing rows) and  'a' is append """

        self.mode = mode

        if not mode in ['r','w','a']:
            raise ValueError("Invalid mode")

        if mode=='a':
            raise ValueError("Can't handle append mode yet")
        
        file = self.getFile()

        file.close()
        file.open(mode)

    @property
    def name(self):
        return self._name

    def ownerOfSets(self):
        "Find out which sets we are owners of"
        owned_sets = []
        for s in self.db.getSets():
            if s.getOwnerTable() == self:
                owned_sets.append(s)
        return owned_sets

    def getFile(self):
        return self.db.files[self.rstruct.rt_file]
        
    def getRowCount(self):
        return self.getFile().pz.next-1        

    def getColumnIndex(self, name):
        return self.db.schema.getFieldNamesByRecordStruct(self.rstruct).index(name)

    def getColumnNameByIndex(self, index):
        return self.db.schema.getFieldNamesByRecordStruct(self.rstruct)[index]

    def getColumnTypeByIndex(self, index):
        fs = self.db.schema.getFieldStructsByRecordStruct(self.rstruct)[index]
        type = chr(fs.fd_type)
        return type

    def getColumnDimensions(self, findex):
        fs = self.db.schema.getFieldStructsByRecordStruct(self.rstruct)[findex]
        return [fs.fd_dim1, fs.fd_dim2, fs.fd_dim3]
    
    def getColumnNames(self):
        return [fs.name for fs in self.db.schema.getFieldStructsByRecordStruct(self.rstruct)]

    def getCursor(self, n):
        "Return cursor at row n"
        return Cursor(self, n)

    def clear(self):
        """Delete all rows in table."""
        self.setMode('w')

    def writeRow(self, row, index=None):
        """Write row to table

        Returns a cursor object to the written row
        """
        rnum = self.db.getTableIndex(self)

        table_index = self.db.getTableIndex(self)
        assert table_index < 2**16
        slotdata = self.db.pack("H", table_index)

        if index == None:
            dbaddr = self.getFile().getNextDBAddr()
        else:
            dbaddr = DBAddress(self.rstruct.rt_file, index+1)
        # Write db address
        slotdata = slotdata + self.db.pack("I", int(dbaddr))

        # Write set pointers
        for set in self.db.schema.settable:
            if set.st_own_rt == rnum:
                slotdata = slotdata + self.db.pack("III", 0,0,0)

        # Write member pointers
        for memb in self.db.schema.membertable:
            if memb.mt_record == rnum:
                slotdata = slotdata + self.db.pack("III", 0,0,0)

        # Add data from row
        slotdata += row.data[len(slotdata):]

        if index != None:
            self.getFile().writeSlot(slotdata, index+1)
        else:
            self.getFile().writeSlot(slotdata)

        return Cursor(self, dbaddr.slot - 1)
        
    def __repr__(self):
        return self.name
        
class Row(object):
    def __init__(self, table, data=None):
        self.table = table
        self.data = data

        if data == None:
            self.data = chr(0)*table.rstruct.rt_len

    def check(self):
        assert(self.db.unpack("H", self.data[0:2]) == self.table.index)

    def __repr__(self):
        return self.__class__.__name__ + '(' + str(self.table) + ',' + str(self.asList()) + ')'
            
    def __eq__(self, x):
        return self.table == x.table and self.asList() == x.asList()

    def asList(self):
        res = []
        fieldstructs = self.table.db.schema.getFieldStructsByRecordStruct(self.table.rstruct)

        for fdstruct in fieldstructs:
            data = self.data[fdstruct.fd_ptr: fdstruct.fd_ptr+fdstruct.fd_len]
            value = self.table.db.unpack(fdstruct.getStructTypeString(),data)

            # Unpack returns a tuple
            if fdstruct.fd_dim1 == 0 or fdstruct.getStructTypeString()[-1]=='s' :
                value = value[0]

            res.append(value)
        return res

    def asDict(self):
        res = {}

        for k,v in zip(self.table.getColumnNames(), self.asList()):
            res[k]=v

        return res        

    def set(self, values):
        self.data = ""
        fieldstructs = self.table.db.schema.getFieldStructsByRecordStruct(self.table.rstruct)
        for fdstruct,value in zip(fieldstructs,values):
            data = self.table.db.pack(fdstruct.getStructTypeString(), value)
            self.data = self.data[0:fdstruct.fd_ptr]+data+self.data[fdstruct.fd_ptr+fdstruct.fd_len:]

    def setColumn(self, index, value):
        fdstruct = self.table.db.schema.getFieldStructsByRecordStruct(self.table.rstruct)[index]
        data = self.table.db.pack(fdstruct.getStructTypeString(), value)
        self.data = self.data[0:fdstruct.fd_ptr]+data+self.data[fdstruct.fd_ptr+fdstruct.fd_len:]

    def setColumnString(self,index,v):
        self.setColumn(index,v)
    def setColumnUInt(self, index, i):
        self.setColumn(index,i)
    def setColumnUIntVector(self, index, value):
        fdstruct = self.table.db.schema.getFieldStructsByRecordStruct(self.table.rstruct)[index]
        data = self.table.db.pack(fdstruct.getStructTypeString(), *value)
        self.data = self.data[0:fdstruct.fd_ptr]+data+self.data[fdstruct.fd_ptr+fdstruct.fd_len:]

    def __str__(self):
        return str(self.asDict())

class AuxTableManager(object):
    def __init__(self, table, endchar=chr(0), searchindex=True):
        self.table = table
        self.endchar = endchar
        self.rowlen = table.getColumnDimensions(0)[0]
        self.outtext = ""
        self.slotnum = 0
        self.has_searchindex = searchindex

        self.index = (self.rowlen/4)*[0]
        self.lasttext = None

    def appendText(self, text, refslot = None):
        """Append a string to an aux-table.
           Returns textslot as 0xooiiiiii where oo is the offset and iiiiii is the row index."""

        ## Reserve space for search index
        if self.slotnum == 0 and self.has_searchindex:
            row = Row(self.table)
            self.table.writeRow(row)
            self.slotnum += 1

        ## Update index
        if text != self.lasttext and refslot != None:
            self.index[sortHashFuncFast(text)] = refslot
            self.lasttext = text
        
        offset = len(self.outtext)
        textslot =  (offset << 24) | self.slotnum
        
        self.outtext += text+self.endchar

        if len(self.outtext) >= self.rowlen:
            row = Row(self.table)
            row.setColumnString(0, self.outtext[0:self.rowlen])
            self.outtext = self.outtext[self.rowlen:]
            self.table.writeRow(row)
            self.slotnum += 1

        return textslot

    def lookupText(self, index, offset, maxlen=None):
        if offset == 0xff:
            return ""

        [data] = self.table.getCursor(index).getRow().asList()

        try:
            [data2] = self.table.getCursor(index).getRow().asList()
        except ValueError:
            data2 = ""

        data =  data + data2

        data = data[offset: ]

        length=None
        if self.endchar != None:
            length = data.find(self.endchar)
        elif maxlen != None:
            if length!=None:
                length = min(length,maxlen)
            else:
                length = maxlen
        else:
            return None
        
        data = data[:length]

        return data

    def flush(self):
        if len(self.outtext)>0:
            row = Row(self.table)
            row.setColumnString(0, self.outtext)
            self.table.writeRow(row)
            self.outtext = ''

        if self.has_searchindex:
            self.writeIndex()

    def writeIndex(self):
        if self.slotnum > 0:
            row = Row(self.table)
            row.setColumnString(0, self.table.db.pack('%dI'%len(self.index), *self.index))
            self.table.writeRow(row, 0)

    def __del__(self):
        self.flush()

class DBAddress(object):
    def __init__(self, filenum, slot):
        self.filenum = filenum
        self.slot = slot

    @classmethod
    def fromint(cls, addr):
        filenum = addr >> 24
        slot = addr & 0xffffff
        return cls(filenum, slot)

    def getFile(self, db):
        return db.getFileByIndex(self.filenum)

    def iszero(self):
        return self.slot == 0 and self.filenum == 0

    def __int__(self):
        return (self.filenum << 24) | self.slot

    def __repr__(self):
        return '%d:%d'%(self.filenum, self.slot)
