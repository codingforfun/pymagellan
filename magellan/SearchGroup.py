import struct
import string
import ConfigParser
import re
import DBUtil
from DBUtil import Row,AuxTableManager, sortHashFuncFast
from DBSchema import FieldStruct,FieldTypeLONGINT,FieldTypeSHORTINT,FieldTypeCHARACTER
import copy
import os
from sets import Set
import bisect

def textslot_cmp(x,y):
    if x == y:
        return 0
    if x == None:
        return -1
    if y == None:
        return 1
    else:
        return cmp((x & 0xffffff, x >> 24),(y & 0xffffff, y >> 24))

class Group(object):
    def __init__(self, map, name=None):
        self._layers = []
        self.map = map
        self.mode = None
        self._name = name
        self._features = []
        self.exportfields = []
        self.exportfieldtypes = []
        self.isopen = False
        self._searchable = False

    def __equal__(self, g):
        return isinstance(Group, g) and g.name == self.name
    def __hash__(self):
        return hash(self.name)

    @property
    def xfeatures(self):
        """Returns an iterator over all features in group"""
        for i in xrange(0,self.getFeatureCount()):
            yield self.getFeatureByIndex(i)

    @property
    def features(self):
        """Returns a sequence of all features in group"""
        if self.mode == 'r':
            return [self.getFeatureByIndex(i) for i in xrange(0,self.getFeatureCount())]
        else:
            return self._features

    @property
    def layers(self):
        return [self.map.getLayerByIndex(layer['number']) for layer in self._layers]

    def addLayer(self, layer):
        if not self.hasLayer(layer):
            self._layers.append({'number': self.map.getLayerIndex(layer), 'objtypes': []})
            
    def hasLayer(self, layer):
        layernum = self.map.getLayerIndex(layer)
        return layernum in [l['number'] for l in self._layers]

    def getFeatureByIndex(self, index):
        return self._features[index]
    
    def getFeatureByCellElement(self, cellelement, startindex=None, stopindex=None):
        if self.mode != 'r':
            return ValueError("Features can only be indexed by textslot when the group is opened in read-only")

        if cellelement.textslot in (0xff000000, None):
            return None

        if startindex==None:
            startindex=0
        if stopindex==None:
            stopindex=self.maintable.getRowCount()-1

        # For small intervals use linear search
        if stopindex-startindex+1 < 4:
            for i in range(startindex, stopindex+1):
                textslot = self.maintable.getCursor(i).asDict()[self.textslot_column]
                if textslot == cellelement.textslot:
                    return self.getFeatureByIndex(i)
            raise Exception("Textslot not found: 0x%x"%cellelement.textslot)

        midindex = (startindex+stopindex)/2

        midtextslot = self.maintable.getCursor(midindex).asDict()[self.textslot_column]

        if cellelement.textslot == midtextslot:
            return self.getFeatureByIndex(midindex)
        elif textslot_cmp(cellelement.textslot,midtextslot)<0:
            return self.getFeatureByCellElement(cellelement, startindex=startindex, stopindex=midindex-1)
        else:
            return self.getFeatureByCellElement(cellelement, startindex=midindex+1, stopindex=stopindex)

    def getFeatureExportFields(self): return self.exportfields
    def getFeatureExportFieldTypes(self): return self.exportfieldtypes

    def addFeature(self, feature):
        """Add feature to group. Return the index of the new feature"""
        if self.mode=='r':
            raise ValueError("Group is open as read-only")

        self._features.append(feature)
        return self._features.index(feature)

    def optimizeLayers(self):
        """Call the optimize function of each member layer and update cell element reference in all features"""

        cellrefremap = {}
        for layer in self.layers:
            cellrefremap[self.map.getLayerIndex(layer)] = layer.optimize()

        for feature in self.xfeatures:
            remapdict = cellrefremap[feature.layerindex]

            if len(remapdict) > 0:
                feature.cellelementrefs = tuple([remapdict[ceref] for ceref in feature.cellelementrefs])

    @property
    def name(self):
        return str(self._name)

    def set_searchable(self, v):
        self._searchable = v
    def get_searchable(self):
        return self._searchable
    searchable = property(get_searchable, set_searchable, doc='True if group is searchable')    


class GroupNormal(Group):
    textslot_column = 'NAME_REF'
    extrafields = []
    def __init__(self, map, name=None):
        Group.__init__(self, map, name=name)
        self.exportfields += ['name', 'objtype']
        self.exportfieldtypes += ['string', 'int']
    
    def initFromIni(self, inicfg):
        groupnumber = self.map.getGroupIndex(self)

        groupconfig = inicfg.get('GROUPS',str(groupnumber))
        tok = groupconfig.split(" ")
        self._name = tok[0]
        nlayers = int(tok[1])

        tok = tok[2:]

        self._layers=[]
        for i in range(0, nlayers):
            layer={}

            layer['number'] = int(tok.pop(0))

            objtypes=[]
            if tok[0]=='(':
                tok.pop(0)
                while tok[0] != ')':
                    objtypes.append(int(tok.pop(0)))
                tok.pop(0)

            layer['objtypes'] = objtypes
            
            self._layers.append(layer)

    def updateIni(self, inicfg):
        groupnumber = self.map.getGroupIndex(self)
        groupconfig = [self.name, str(len(self._layers))]

        for layer in self._layers:
            objtypelist = map(str, layer['objtypes'])
            if len(objtypelist) == 0:
                objtypelist = ['0']
            groupconfig += [str(layer['number'])] + ['('] + objtypelist + [')']

        inicfg.set('GROUPS',str(groupnumber), ' '.join(groupconfig))

    def _initDB(self, db):
        groupnumber = self.map.getGroupIndex(self)

        maintablename = "R_GR%d"%groupnumber
        addtablename = "RC_GR%d"%groupnumber
        auxtablename = "AUX_GR%d"%groupnumber
        # Create tables if opened in append mode
        if self.mode == "w" and not maintablename in db.getTableNames():

            # Build main table
            fields = [
                FieldStruct(name='NAME_REF', fd_type=FieldTypeLONGINT),
                FieldStruct(name='CELL_NUM', fd_type=FieldTypeLONGINT),
                FieldStruct(name='N_IN_C', fd_type=FieldTypeSHORTINT),
                FieldStruct(name='OBJ_TYPE', fd_type=FieldTypeCHARACTER)
                ] + self.extrafields
            db.addTable(name = maintablename,
                        filename = self.map.mapnumstr + "gr%d.ext"%groupnumber,
                        fieldstructlist = fields)

            # Build additional cells table
            fields = [
                FieldStruct(name='CELL_NUM', fd_type=FieldTypeLONGINT),
                FieldStruct(name='N_IN_C', fd_type=FieldTypeSHORTINT),
                ]
            db.addTable(name = addtablename,
                        filename = self.map.mapnumstr + "gr%d.clp"%groupnumber,
                        fieldstructlist = fields)

            # Build aux table
            fields = [
                FieldStruct(name='NAME_BUF', fd_type=FieldTypeCHARACTER, fd_dim1=248, fd_dim2=1)
                ]
            db.addTable(name = auxtablename,
                        filename = self.map.mapnumstr + "gr%d.aux"%groupnumber,
                        fieldstructlist = fields)

        self.maintable = db.getTableByName(maintablename)
        self.addtable = db.getTableByName(addtablename)
        self.auxtable = db.getTableByName(auxtablename)
        self.auxmanager = AuxTableManager(self.auxtable)
        
    def open(self, mode='r'):
        """Open group and read all the layers and database tables. If the group is opened in append mode ('a'), all
        features are read into the features attribute"""

        if not self.isopen:
            self.mode = mode

            self._initDB(self.map.getDB())

            for li in self._layers:
                self.map.getLayerByIndex(li['number']).open(mode)

            if self.mode == 'a':
                for i in range(0, self.maintable.getRowCount()):
                    self._insert(self._getFeatureByIndex(i))
            self.isopen = True
            
    def close(self):
        if self.isopen:
            if self.mode in ['w','a']:
                self.maintable.setMode('w')
                self.addtable.setMode('w')
                self.auxtable.setMode('w')

                aux = AuxTableManager(self.auxtable)

                # Write features to database
                addrow = 0
                for f in self.xfeatures:
                    textslot = aux.appendText(f.name, self.maintable.getRowCount()+1)

                    # Update cell elements
                    for ref, e in zip(f.cellelementrefs, f.getCellElements(self.map)):
                        e.textslot = textslot
                        layer = self.map.getLayerByIndex(f.layerindex)
                        layer.updateCellElement(ref, e)

                    row = Row(self.maintable)
                    row.setColumnUInt(self.maintable.getColumnIndex("NAME_REF"), textslot)

                    row.setColumnUInt(self.maintable.getColumnIndex("OBJ_TYPE"), f.getObjtypeIndex(self))

                    cellelementrefs = f.getCellElementRefs()
                    if len(cellelementrefs) == 1:
                        row.setColumnUInt(self.maintable.getColumnIndex("CELL_NUM"), cellelementrefs[0][0])
                        row.setColumnUInt(self.maintable.getColumnIndex("N_IN_C"), cellelementrefs[0][1]+1)
                    else:
                        row.setColumnUInt(self.maintable.getColumnIndex("CELL_NUM"), 0x80000000|(addrow+1) )
                        row.setColumnUInt(self.maintable.getColumnIndex("N_IN_C"), len(cellelementrefs))
                        for cref in cellelementrefs:
                            rowrc = Row(self.addtable)
                            rowrc.setColumnUInt(self.addtable.getColumnIndex("CELL_NUM"), cref[0])
                            rowrc.setColumnUInt(self.addtable.getColumnIndex("N_IN_C"), cref[1]+1)
                            self.addtable.writeRow(rowrc)
                            addrow+=1
                    self.maintable.writeRow(row)

            self.isopen = False            

    def getLayerAndObjtypeFromObjtypeIndex(self, objtypeindex):
        idx=0
        for l in self._layers:
            newidx = idx + len(l['objtypes'])
            if objtypeindex < newidx:
                return self.map.getLayerByIndex(l['number']), l['objtypes'][objtypeindex-idx]
            idx = newidx
            
        raise ValueError('Couldnt find objtypeindex %d '%objtypeindex + str(self._layers))

    def __str__(self):
        groupnumber = self.map.getGroupIndex(self)
        s=self.name+" (%d):\n"%groupnumber
        for l in self._layers:
            s=s+"layer#: "+str(l['number'])+"\n"
            s=s+"objtypes: "+str(l['objtypes'])+"\n"
        s+="Columns in main table: "+str(self.maintable.getColumnNames())+"\n"
        return s

    def getFeatureCount(self):
        if self.mode=='r':
            return self.maintable.getRowCount()
        else:
            return len(self._features)

    def getFeatureByIndex(self, index):
        if self.mode == 'r':
            return self._getFeatureByIndex(index)
        else:
            return self._features[index][1]
    
    def _getFeatureByIndex(self, index):
        if index >= self.maintable.getRowCount():
            raise IndexError("index out of bounds")

        rec = self.maintable.getCursor(index).asDict()

        namekey = rec['NAME_REF']

        objtype_index = rec['OBJ_TYPE']
        layer, objtype = self.getLayerAndObjtypeFromObjtypeIndex(objtype_index)
        
        nameindex = namekey & 0xffffff
        nameoffset = namekey >> 24
        name = self.auxmanager.lookupText(nameindex, nameoffset)
        
        cellelementrefs = []
        if rec['CELL_NUM'] & 0x80000000:
            for j in range(0,rec['N_IN_C']):
                 rcrow = (rec['CELL_NUM']&0xffffff)+j-1
                 rec2 = self.addtable.getCursor(rcrow).asDict()
                 cellelementrefs.append((rec2['CELL_NUM'],rec2['N_IN_C']-1))
        else:
            cellelementrefs.append((rec['CELL_NUM'], rec['N_IN_C']-1))

        return FeatureNormal(self.map.getLayerIndex(layer), cellelementrefs,
                             name, objtype)

    def addFeature(self, feature):
        """Add feature to group. Return the index of the new feature"""
        if self.mode=='r':
            raise ValueError("Group is open as read-only")

        # Get object type index and if it's not already present in the group
        # the objtype is added
        objtypeindex = feature.getObjtypeIndex(self)
        
        # Update objtypeindex
        for e in feature.getCellElements(self.map):
            e.objtype = objtypeindex

        self._insert(feature)

    def _insert(self, feature):
        ## Insert feature and keep the list sorted on name
        name = feature.name
        
        if name:
            item = (chr(sortHashFuncFast(name)) + name, feature)
            index = bisect.bisect_right(self._features, item)
            self._features.insert(index, item)
            return index

    def getObjtypeIndex(self, layernumber, objtype):
        idx=0
        objnumber_index = None
        for li in self._layers:
            if li['number'] == layernumber:
                if objtype in li['objtypes']:
                    return idx+li['objtypes'].index(objtype)
                else:
                    if self.mode == 'r':
                        raise ValueError("Objtype does not exists")
                    # Objtype is not used in this layer before, add it
                    li['objtypes'].append(objtype)
                    return idx+len(li['objtypes'])-1
            idx += len(li['objtypes'])

class GroupStreet(GroupNormal):
    extrafields = [
        FieldStruct(name='FLD0', fd_type=FieldTypeLONGINT),
        FieldStruct(name='FLD1', fd_type=FieldTypeLONGINT),
        FieldStruct(name='FLD2', fd_type=FieldTypeLONGINT)
        ]
    def __init__(self, map, name=None):
        GroupNormal.__init__(self, map, name=name)
        self.exportfields += ['streetNumBeg', 'streetNumEnd']
        self.exportfieldtypes += ['int', 'int']
        
    def _initDB(self, db):
        GroupNormal._initDB(self, db)

        self.citytable = db.getTableByName("C_R")
        self.ziptable = db.getTableByName("Z_R")

    def _getFeatureByIndex(self, index):
        feature = GroupNormal._getFeatureByIndex(self, index)

        rec = self.maintable.getCursor(index).asDict()

        zipindex = rec['FLD0']

        streetNumBeg = rec['FLD1']
        streetNumEnd = rec['FLD2']

        return FeatureStreet(feature.layerindex, feature.getCellElementRefs(),
                             feature.name, feature.getObjtype(),
                             streetNumBeg=streetNumBeg, streetNumEnd=streetNumEnd)

class Feature(object):
    """Class that holds information about a list of cell element references and
       data attributes associated with them."""

    __slots__ = ('cellelementrefs', 'layerindex', 'attributes')
    
    def __init__(self, layerindex, cellelementreflist, **kw):
        """Create an instance of a feature given a name, an object type and a list of cell elements."""
        self.cellelementrefs = tuple(cellelementreflist)
        self.layerindex = layerindex
        self.attributes = kw

        if 'name' in self.attributes and len(self.attributes['name']) == 0:
            print self.attributes
            raise Exception('Name must not be empty')            

    def __eq__(self, x):
        return self.layerindex == x.layerindex and \
               self.attributes == x.attributes and \
               Set(self.cellelementrefs) == Set(x.cellelementrefs)

    def __hash__(self):
        return hash(self.layerindex) ^ \
               hash(tuple(self.attributes.keys())) ^ \
               hash(tuple(self.attributes.values())) ^ \
               hash(self.cellelementrefs)

    @property
    def name(self):
        return self.attributes['name']

    def getCellElements(self, map):
        layer = map.getLayerByIndex(self.layerindex)
        return [layer.getCellElement(ceref) for ceref in self.cellelementrefs]
    def getCellElementRefs(self):
        return self.cellelementrefs

    def setCellElementRefs(self, cellelementreflist):
        self.cellelementrefs = tuple(cellelementreflist)

    def importFromList(self,l, group):
        for f,v,t in zip(group.exportfields,l,group.exportfieldtypes):
            self.attributes[f] = v
    def exportToList(self,group):
        return [self.attributes[f] for f in group.exportfields]

    def __repr__(self):
        return self.__class__.__name__ + '(' + ",".join([str(x) for x in (self.layerindex, self.cellelementrefs, self.attributes)])+')'

class FeatureNormal(Feature):
    def __init__(self, layerindex, cellelementreflist, name, objtype):
        Feature.__init__(self, layerindex, cellelementreflist, name=name,
                         objtype=objtype)
    def getObjtype(self): return self.attributes['objtype']
    def getObjtypeIndex(self, group):
        return group.getObjtypeIndex(self.layerindex, self.getObjtype())

class FeatureStreet(FeatureNormal):
    def __init__(self, layerindex, cellelementreflist, name, objtype,
                 zipcode=0,streetNumBeg=0, streetNumEnd=0):
        Feature.__init__(self, layerindex, cellelementreflist, name=name,
                         objtype=objtype,
                         streetNumBeg=streetNumBeg, streetNumEnd=streetNumEnd
                         )
    def importFromList(l, group):
        (self.attributes['name'], self.attributes['objtype']) = l

def groupFactory(map, groupnumber, inicfg, db):
    maintable = db.getTableByName("R_GR%d"%groupnumber)

    if len(maintable.getColumnNames()) == 7:
        return GroupStreet(map)
    else:
        return GroupNormal(map)

def buildziprecord(db, zipfilename = 'z.dat', auxfilename = 'cn.dat'):
    """Create zip tables in database"""
    if not ('Z_R' in db.getTableNames() or 'C_R' in db.getTableNames()):
        # Build zip table
        fields = [
            FieldStruct(name='ZIP_CODE', fd_type=FieldTypeLONGINT),
            FieldStruct(name='C_REF', fd_type=FieldTypeLONGINT),
            ]
        db.addTable(name='Z_R',
                    filename=zipfilename,
                    fieldstructlist=fields)

        # Build aux table
        fields = [
            FieldStruct(name='CITY_BUF', fd_type=FieldTypeCHARACTER, fd_dim1=248, fd_dim2=1)
            ]
        db.addTable(name='C_R', filename=auxfilename,
                    fieldstructlist=fields)
