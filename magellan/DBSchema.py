import operator
import struct
import os
from rsttable import toRSTtable

FTFlagsCompressed = 0x40

FieldTypeFLOAT = ord('f')
FieldTypeCHARACTER = ord('c')
FieldTypeLONGINT = ord('l')
FieldTypeREGINT = ord('i')
FieldTypeSHORTINT = ord('s')

FieldFlagUnsigned = 0x4

SetSortOrderFirst = ord('f')
SetSortOrderLast = ord('l')
SetSortOrderAscending = ord('a')
SetSortOrderDescending = ord('d')
SetSortOrderNext = ord('n')

class InvalidDatabase(Exception): pass

class DatabaseSchema:
    def __init__(self):
        self.mode = 'r'

        self.header = HeaderStruct()
        self.filetable = []
        self.recordtable = []
        self.fieldtable = []
        self.settable = []
        self.membertable = []
        self.sorttable = []
        self.keytable = []

    def deSerialize(self, data, bigendian):
        # Clear tables
        self.filetable=[]
        self.recordtable=[]
        self.fieldtable=[]
        self.settable=[]
        self.membertable=[]
        self.sorttable=[]
        self.keytable=[]

        # De-serialize header
        data = self.header.deSerialize(data, bigendian)

        # Make a sanity check
        if self.header.size_ft > 255:
            raise InvalidDatabase
        
        for (list, classref, size) in [(self.filetable, FileStruct, self.header.size_ft),
                                  (self.recordtable, RecordStruct, self.header.size_rt), 
                                  (self.fieldtable, FieldStruct, self.header.size_fd), 
                                  (self.settable, SetStruct, self.header.size_st), 
                                  (self.membertable, MemberStruct, self.header.size_mt), 
                                  (self.sorttable, SortStruct, self.header.size_srt), 
                                  (self.keytable, KeyStruct, self.header.size_kt)]:
            for i in range(size):
                o = classref()
                data = o.deSerialize(data, bigendian)
                list.append(o)

        # Deserialize name fields for some tables
        names = data.split('\n')
        for t in self.recordtable:
            t.name = names.pop(0)
        for t in self.fieldtable:
            t.name = names.pop(0)
        for t in self.settable:
            t.name = names.pop(0)

    def serialize(self, bigendian):
        ## Update header
        if len(self.filetable) > 0:
            self.header.page_size = max([fte.ft_pgsize for fte in self.filetable])
        self.header.size_ft = len(self.filetable)
        self.header.size_rt = len(self.recordtable)
        self.header.size_fd = len(self.fieldtable)
        self.header.size_st = len(self.settable)
        self.header.size_mt = len(self.membertable)
        self.header.size_srt = len(self.sorttable)
        self.header.size_kt = len(self.keytable)
        
        data = self.header.serialize(bigendian)

        for list in [self.filetable,
                     self.recordtable, 
                     self.fieldtable, 
                     self.settable, 
                     self.membertable, 
                     self.sorttable, 
                     self.keytable]:
            data += "".join([v.serialize(bigendian) for v in list])

        names = [t.name for t in self.recordtable]
        names += [t.name for t in self.fieldtable]
        names += [t.name for t in self.settable]
        data += "\n".join(names)
        
        return data

    def getRecordStructByName(self, name):
        for rs in self.recordtable:
            if rs.name == name:
                return rs

    def getFieldStructsByRecordStruct(self, recstruct):
        return self.fieldtable[recstruct.rt_fields: recstruct.rt_fields+recstruct.rt_fdtot]

    def getFieldNum(self, recstruct, fieldname):
        return recstruct.rt_fields + self.getFieldNamesByRecordStruct(recstruct).index(fieldname)

    def getFieldNamesByRecordStruct(self, recstruct):
        return [fds.name for fds in self.getFieldStructsByRecordStruct(recstruct)]

    def addFileStruct(self, filestruct):
        filestruct.ft_status = ord('c')
        filestruct.ft_slots = 0
        filestruct.ft_desc = 0

        filenum = len(self.filetable)

        self.filetable.append(filestruct)

        ## If compressed add the index table
        if filestruct.compressed:
            base, ext = os.path.splitext(filestruct.ft_name)
            filename = base + 'c' + ext
            compidx = FileStruct(ft_name=filename, ft_type=ord('c'), ft_slots=63,
                                 ft_slsize=8, ft_pgsize=512, ft_status = ord('c'))
            self.filetable.append(compidx)
        
        return filenum

    def removeFile(self, filenum):
        filestruct = self.file_table.pop(filenum)
        
    def addRecordStruct(self, name, filename, fieldstructlist, compressed=None):
        # Add file
        fs = FileStruct(ft_name=filename, compressed=compressed)
        filenum = self.addFileStruct(fs)

        recordnum = len(self.recordtable)

        # Add fields
        nsets = 0
        nmemb = 0
        firstfieldnum = len(self.fieldtable)
        for fieldstruct in fieldstructlist:
            fieldstruct.fd_rec = recordnum
            self.fieldtable.append(fieldstruct)
            
        # Add record
        r = RecordStruct(name = name,
                         rt_file = filenum,
                         rt_len = reduce(operator.add, [f.size() for f in fieldstructlist]),
                         rt_data = 6,
                         rt_fields = firstfieldnum,
                         rt_fdtot = len(fieldstructlist),
                         rt_flags = 0)

        recordnum = len(self.recordtable)
        
        self.recordtable.append(r)

        self.updateFieldSlotPtrs(recordnum)

        return recordnum

    def updateFieldSlotPtrs(self, recordnum):
        slotptr = 2+4
        
        sets = filter(lambda s: s.st_own_rt==recordnum, self.settable)
        members = filter(lambda m: m.mt_record==recordnum, self.membertable)

        # Update set ptrs
        for set in sets:
            set.st_own_ptr=slotptr
            slotptr += 3*4
        # Update member ptrs
        for member in members:
            member.mt_mem_ptr = slotptr
            slotptr += 3*4
            
        nsets = len(sets)
        nmembers = len(members)

        rec = self.recordtable[recordnum]
        slotptr = 2+4+nsets*3*4+nmembers*3*4
        rec.rt_data = slotptr
        for field in self.fieldtable[rec.rt_fields: rec.rt_fields+rec.rt_fdtot]:
            field.fd_ptr=slotptr
            slotptr += field.fd_len

        slotsize = slotptr

        # Update record sizes
        rec.rt_len = slotsize

        # Update slot size of file
        file = self.filetable[self.recordtable[recordnum].rt_file]
        ## round file slot size to word boundary
        file.ft_slsize = 2*((slotsize+1)/2)
        file.ft_slots = int(file.ft_pgsize-4)/file.ft_slsize


    def addSet(self, name, owner, memberlist, order=SetSortOrderLast):
        """Add set to database schema.

        name: Set name
        owner: Owner record index
        memberlist: List of MemberStruct objects

        """

        # Add set struct
        setfields = ['st_order','st_own_rt','st_own_ptr','st_members',
		 'st_memtot','st_flags' ]

        nsets = len(filter(lambda s: s.st_own_rt==owner, self.settable))

        self.settable.append(SetStruct(name = name,
                                       st_order = order,
                                       st_own_rt = owner, 
                                       st_members = len(self.membertable), 
                                       st_memtot = len(memberlist),
                                       st_flags = 0))
        setnum = nsets
        nsets+=1

        # Add set members and sort table entries
        sortfieldindex = len(self.sorttable)
        for member in memberlist:
            # Add sort fields to sort table
            if len(member.sortfields)>0:
                member.mt_sort_fld = len(self.sorttable)
                sorttableindex = len(self.sorttable)
                for sortfield in member.sortfields:
                    srt = SortStruct()
                    srt.se_fld = self.recordtable[member.mt_record].rt_fields+sortfield
                    srt.se_se = setnum
                    self.sorttable.append(srt)
                member.mt_sort_fld = sorttableindex
            else:
                member.mt_sort_fld=0

            self.membertable.append(member)

        # Update field slot pointers of owner record
        self.updateFieldSlotPtrs(owner)
        for member in memberlist:
            self.updateFieldSlotPtrs(member.mt_record)

    def __repr__(self):
        s = ""

        s += repr(self.header) + '\n'

        for l,c in [(self.filetable, FileStruct),
                    (self.recordtable, RecordStruct),
                    (self.fieldtable, FieldStruct),
                    (self.settable, SetStruct),
                    (self.membertable, MemberStruct),
                    (self.sorttable, SortStruct)
                    ]:
            s += c.__name__ + ":\n"
            s += toRSTtable([c.reprheader()] + [f.reprrow() for f in l])
            s+="\n"
        return s

    def check(self, verbose = False):
        """Database schema consistency check"""

    @property
    def recordnames(self):
        return [record.name for record in self.recordtable]

class DBStruct(object):
    fields = []
    printfields = None
    printsizes = []
    defaultvalues = {}
    hasname = False
    def __init__(self, **kvargs):
        
        ## Set default values
        for field in self.fields:
            if field in self.defaultvalues:
                self.__dict__[field] = self.defaultvalues[field]
            else:
                self.__dict__[field] = None

        if self.hasname:
            self.name = ''

        for k,v in kvargs.items():
            if self.hasname and k == 'name':
                self.name = v
                continue

            if not k in self.fields:
                raise ValueError('Invalid argument: %s'%k)
            
            kindex = self.fields.index(k)

            self.__dict__[k] = v

    def serialize(self, bigendian):
        if bigendian:
            prefix=">"
        else:
            prefix="<"
        return apply(struct.pack,[prefix+self.types]+[getattr(self,x) for x in self.fields])

    def deSerialize(self, data, bigendian):
        if bigendian:
            prefix=">"
        else:
            prefix="<"

        size = struct.calcsize(self.types)
            
        values = struct.unpack(prefix+self.types,data[0:size])
        # Construct dictionary with fieldnames as keys
        for i in range(len(self.fields)):
            value = values[i]
            if type(value) is str:
                value = value.split(chr(0))[0]
            setattr(self,self.fields[i],value)

        return data[size:]

    def structSize(self): return struct.calcsize(self.types)

    @classmethod
    def reprheader(self):
        """Return a list of field names suitable for printing a table header"""
        if self.printfields == None:
            fields = self.fields
        else:
            fields = self.printfields

        return fields

    def reprrow(self):
        """Return a list of field values suitable for printing a table"""
        if self.printfields == None:
            fields = self.fields
        else:
            fields = self.printfields

        return [getattr(self, f) for f in fields]

    def __repr__(self):
        return toRSTtable([self.reprheader(), self.reprrow()])
        
class HeaderStruct(DBStruct):
    fields = ['version','page_size','size_ft','size_rt',
              'size_fd','size_st','size_mt','size_srt',
              'size_kt']
    types = "6sHHHHHHHH"
    printsizes = 9*[10]

    def __init__(self, **kvargs):
        DBStruct.__init__(self, **kvargs)
        self.version = 'V3.00'.ljust(6, chr(0x1a))
        self.page_size = 512
        self.size_ft = 0
        self.size_rt = 0
        self.size_fd = 0
        self.size_st = 0
        self.size_mt = 0
        self.size_srt = 0
        self.size_kt = 0


    def check(self):
        """Header consistency check

        >>> HeaderStruct().check()
        True
        """
        if not self.version.endswith(chr(0x1a)):
            raise InvalidHeader('Version string should end with chr(0x1a)')

        for s in (self.page_size, self.size_ft, self.size_rt, self.size_fd, self.size_st, self.size_mt, self.size_srt, self.size_kt):
            if s < 0 :
                raise InvalidHeader('Sizes should be >= 0')

        if self.page_size % 512 != 0:
            raise InvalidDatabase('Page size should be and integer power of 2')

        return True

class FilePageZeroStruct(DBStruct):
    fields = ['dchain','next','timestamp','cdate','bdate','version']
    types = "IIIII37s"
    printsizes = [10,10,10,10,10,20]

    def __init__(self, **kvargs):
        DBStruct.__init__(self, **kvargs)

        self.dchain=0
        self.next=1
        self.timestamp=0
        self.cdate=0
        self.bdate=0
        self.version = "Raima Database Manager 4.5 [Build 17]"
        

    def check(self):
        """Page zero consistency check

        >>> HeaderStruct().check()
        True
        """
        if not self.version.endswith(chr(0x1a)):
            raise InvalidHeader('Version string should end with chr(0x1a)')

        for s in (self.page_size, self.size_ft, self.size_rt, self.size_fd, self.size_st, self.size_mt, self.size_srt, self.size_kt):
            if s < 0 :
                raise InvalidHeader('Sizes should be >= 0')

        if self.page_size % 512 != 0:
            raise InvalidDatabase('Page size should be and integer power of 2')

        return True

    
class FileStruct(DBStruct):
    fields = ['ft_name','ft_desc','ft_status','ft_type',
		  'ft_slots','ft_slsize','ft_pgsize','ft_flags']
    defaultvalues = {
        'ft_name': None,
        'ft_desc': 0,
        'ft_status': 0, 
        'ft_slsize': 0,
        'ft_type': ord('d'),
        'ft_pgsize': 512,
        'ft_flags': 0
        }

    types = "48sHBBHHHH"
    printsizes = [20,10,10,10,10,10,10,10]
    printfields = None
    hasname = False
    
    def __init__(self, compressed=False, **kvargs):
        DBStruct.__init__(self, **kvargs)

        if self.ft_slsize!=0 and self.ft_slots == None:
            self.ft_slots = int(self.ft_pgsize)/int(self.ft_slsize)
        if compressed:
            self.ft_flags |= FTFlagsCompressed
        
    @property
    def compressed(self):
        return bool(self.ft_flags & FTFlagsCompressed)


class RecordStruct(DBStruct):
    fields = ['rt_file','rt_len','rt_data',
              'rt_fields','rt_fdtot','rt_flags']
    types = "HHHHHH"
    printfields = ['name']+fields
    printsizes = [20,10,10,10,10,10,10]
    hasname = True

class FieldStruct(DBStruct):
    fields = ['fd_key','fd_type','fd_len',
              'fd_dim1','fd_dim2','fd_dim3',
              'fd_keyfile','fd_keyno',
              'fd_ptr','fd_rec','fd_flags']
    defaultvalues = {
        'fd_type': None,
        'fd_dim1': 0,
        'fd_dim2': 0,
        'fd_dim3': 0,
        'fd_key': ord('n'),
        'fd_keyfile': 0,
        'fd_keyno': 0,
        'fd_flags': 0
        }
    types = "BBHH3HHHHH"
    printfields = ['name']+fields
    printsizes = [20,8,8,8,8,8,8,8,8,8,8]

    typemap = { FieldTypeCHARACTER: 'b',
                FieldTypeLONGINT: 'i',
                FieldTypeSHORTINT: 'h' }
    hasname = True

    def __init__(self, **kvargs):
        DBStruct.__init__(self, **kvargs)

        # Always unsigned
        if 'fd_flags' not in kvargs and \
                (self.fd_type in [FieldTypeLONGINT, FieldTypeSHORTINT] or \
                (self.fd_type == FieldTypeCHARACTER) and self.fd_dim1 == 0):
            self.fd_flags |= FieldFlagUnsigned

        if self.fd_type != None:
            self.fd_len = self.size()
        else:
            self.fd_len = None
        
    def getStructTypeString(self):
        typechar = self.typemap[self.fd_type]
        if self.fd_flags & FieldFlagUnsigned:
            typechar = typechar.upper()

        if chr(self.fd_type) == 'c' and self.fd_dim1 > 0:
            return str(self.fd_dim1)+'s'
        elif self.fd_dim1==0:
            return typechar
        elif self.fd_dim1>0:
            return str(self.fd_dim1)+typechar
        
    def size(self):
        sizemap = {FieldTypeLONGINT: 4, FieldTypeSHORTINT: 2, FieldTypeCHARACTER: 1}
        if self.fd_dim1==0 and self.fd_dim2==0:
            return sizemap[self.fd_type]
        elif self.fd_dim2==0:
            return self.fd_dim1*sizemap[self.fd_type]
        else:
            return self.fd_dim1*self.fd_dim2*sizemap[self.fd_type]

class SetStruct(DBStruct):
    fields = ['st_order','st_own_rt','st_own_ptr','st_members',
		 'st_memtot','st_flags' ]
    types = "HHHHHH"
    printfields = ['name']+fields
    printsizes = [20,8,8,8,8,8,8]
    hasname = True

class MemberStruct(DBStruct):
    fields = ['mt_record','mt_mem_ptr','mt_sort_fld','mt_totsf']
    types = "HHHH"
    printsizes = [8,8,8,8]
    
    def __init__(self, recordnum=None, sort_fieldindex_list=None):
        DBStruct.__init__(self)
        if recordnum!=None and sort_fieldindex_list != None:
            self.sortfields = sort_fieldindex_list
            self.mt_record=recordnum
            self.mt_totsf=len(sort_fieldindex_list)

class SortStruct(DBStruct):
    fields = ['se_fld','se_se']
    types = "HH"

class KeyStruct(DBStruct):
    fields = ['kt_key','kt_field','kt_ptr','kt_sort']
    types = "HHHH"

if __name__ == "__main__":
    import doctest
    doctest.testmod()
