from struct import unpack
import DBUtil
from DBUtil import AuxTableManager, Row, sortHashFunc
from DBSchema import FieldStruct, FieldTypeLONGINT,FieldTypeSHORTINT,FieldTypeCHARACTER,SetSortOrderAscending
import DBSchema
from SearchGroup import Group,Feature
from sets import Set
import Layer
import operator

POIIcons = ['AERIAL', 'AIRPORTS', 'AMUSEMENT', 'AMUSEMENT_PARK', 'ARCH', 'AREA', 'ARROYO', 'ATM', 'AUTO_CLUB', 'AUTO_REPAIR', 'BANK', 'BAR', 'BASIN', 'BEACH', 'BENCH', 'BEND', 'BOATING', 'BOX', 'BRIDGE', 'BUS_STATION', 'CAMPS', 'CAPE', 'CASINO', 'CITY_CENTER2', 'CLIFF', 'COMMUNITY_CENTER', 'CRATER', 'CROSS', 'DEFAULT', 'EXIT', 'FALLS', 'FERRY_TERM', 'FIRST_AID', 'FISHING', 'FIXED_NAV_AID', 'FLAT', 'FLOAT_BUOY', 'FOREST', 'FUEL', 'GAP', 'GARDENS', 'GAS_STATION', 'GEYSER', 'GLACIER', 'GOLF_COURSES', 'GUT', 'HARBOR', 'HOSPITAL', 'HOTEL', 'HOUSE', 'HUNT_FISH', 'ISTHMUS', 'LARGE_CITIES', 'LAVA', 'LEVEE', 'LIGHT_HOUSE', 'LOCALE', 'MAJOR_CITIES', 'MARINA', 'MEDIUM_CITIES', 'MINE', 'MUSEUM', 'OBSTRUCTION', 'OILFIELD', 'PARKS', 'PILLAR', 'PLUS', 'RAILWAY_STATION', 'RANGE', 'RAPIDS', 'RESERVE', 'RESORT', 'RESTAURANT', 'RESTUARANTS', 'RIDGE', 'ROCKS', 'RV_SERVICES', 'SCHOOL', 'SCUBA', 'SHOOTING', 'SHOPPING_CENTER', 'SIGHT_SEEING', 'SLOPE', 'SMALL_CITIES', 'SOUNDINGS', 'SPORT_ARENA', 'SPORTS_ARENA', 'SPRING', 'SUMMIT', 'SWAMP', 'TOURIST', 'TOURIST_OFFICE', 'TOWER', 'TRAIN_STATION', 'TRUCK_SERVICES', 'TUNNEL', 'UNIVERSITY', 'VALLEY', 'WELL', 'WINERIES', 'WINERY', 'WOODS', 'WRECK', 'ZOOS',
            'RENTACAR',  'BORDER_CROSSING',  'BUSINESS_FACILITY', '']

class POILayerStyle(Layer.LayerStyle):
    visiblerange = [(0,1),(0,1),(0,1),(0,1),(0,1)]
    labelrange = [(0,0),(0,0),(0,0),(0,0),(0,0)]
    hidebasemaprange = [(0,0),(0,0),(0,0),(0,0),(0,0)]
    color = 'BLACK'
    _style = 'NO_FILL'
    

def createPOITables(db, poiprefix, compressed = False):
    schema = db.schema
    
    ## Add POI tables to database
    fieldlist = [FieldStruct(name='POICOUNT', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='SLOTFIRST', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='SLOTLAST', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='FIRSTCHSLOT', fd_type=FieldTypeLONGINT, fd_dim1=39),
                 FieldStruct(name='COMM_SLOT', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='NAME', fd_type=FieldTypeCHARACTER, fd_dim1=25),
                 FieldStruct(name='ID', fd_type=FieldTypeCHARACTER)]
    tCat = db.addTable("CATEG_INFO_", 
                filename = poiprefix+".dct", 
                fieldstructlist = fieldlist)

    fieldlist = [FieldStruct(name='COMM_SLOT', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='POICOUNT', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='FIRSTCHSLOT', fd_type=FieldTypeLONGINT, fd_dim1=39),
                 FieldStruct(name='NAME', fd_type=FieldTypeCHARACTER, fd_dim1=25, fd_flags=1),
                 FieldStruct(name='ID', fd_type=FieldTypeCHARACTER)]
    tSubCat = db.addTable("SUBCATG_INFO_", 
                          filename = poiprefix+".dsc", 
                          fieldstructlist = fieldlist)
    
    fieldlist = [FieldStruct(name='TEXT_SLOT', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='CELL_NUMBER', fd_type=FieldTypeLONGINT),
                 FieldStruct(name='NUMBER_IN_CELL', fd_type=FieldTypeSHORTINT),
                 FieldStruct(name='CATG_ID', fd_type=FieldTypeCHARACTER),
                 FieldStruct(name='SUBCAT_ID', fd_type=FieldTypeCHARACTER)]
    db.addTable("POIPOINT_", 
                filename = poiprefix+".dpo", 
                fieldstructlist = fieldlist)

    fieldlist = [FieldStruct(name='STR', fd_type=FieldTypeCHARACTER, fd_dim1=248, fd_dim2=1)]
    db.addTable("AUXTEXT_", 
                filename = poiprefix+".dtx", 
                fieldstructlist = fieldlist)

    fieldlist = [FieldStruct(name='NAME', fd_type=FieldTypeCHARACTER, fd_dim1=25),
                 FieldStruct(name='AUX_TYPE', fd_type=FieldTypeCHARACTER, fd_flags=0)]
    tPoiDescr = db.addTable("AUX_NAME_", 
                            filename = poiprefix+".dax", 
                            fieldstructlist = fieldlist)
    
    ## Add sets
    
    db.addSet("ALL_SUBCATG_",
              tCat,
              [tSubCat],
              [["NAME"]],
              order=SetSortOrderAscending)
    
    db.addSet("CATEG_AUX_", tCat, [tPoiDescr])

    db.addSet("SUBCATEG_AUX_", tSubCat, [tPoiDescr])

class POIGroup(Group):
    textslot_column = 'TEXT_SLOT'
    def __init__(self, map):
        Group.__init__(self, map)
        
        self.catman = POICategoryManager()

        self.sortcategories = False

        self.poiprefix = map.mapnumstr + "poi"

        self.exportfields += ['aux', 'categoryid', 'subcategoryid']
        self.exportfieldtypes += ['string', 'int', 'int']

    def initFromIni(self, inicfg, poicfg):
        pass

    def _initDB(self, db):
        maintablename = "POIPOINT_"

        # Create tables if opened in append mode
        if self.mode == "w" and not maintablename in db.getTableNames():
            createPOITables(db, self.poiprefix)

        # Open category manager
        self.catman.open(db, self.mode, poiprefix=self.poiprefix)

        self.auxtable = db.getTableByName("AUXTEXT_")
        self.maintable = db.getTableByName(maintablename)

        self.auxmanager = AuxTableManager(self.auxtable, endchar=chr(7), searchindex=False)

    def open(self, mode='r'):
        self.mode = mode

        self._initDB(self.map.getDB())
        
        for lay in self.map.getPOILayers():
            lay.open(self.mode)

        if self.mode == 'a':
            for i in range(0, self.maintable.getRowCount()):
                self.features.append(self._getFeatureByIndex(i))

    def _getFeatureByIndex(self, index):
        if index >= self.maintable.getRowCount():
            raise IndexError("index out of bounds")

        rec = self.maintable.getCursor(index).asDict()

        offset = rec['TEXT_SLOT']>>24
        index = rec['TEXT_SLOT']&0xffffff

        aux=self.auxmanager.lookupText(index, offset).split('\t')

        # List is terminated by a \t char so the aux will be one element too long
        aux = aux[:-1]

        categoryid = rec['CATG_ID']
        subcategoryid = rec['SUBCAT_ID']
        
        return FeaturePOI([(rec['CELL_NUMBER'], rec['NUMBER_IN_CELL']-1)], aux, categoryid, subcategoryid)

    def getFeatureCount(self):
        if self.mode=='r':
            return self.maintable.getRowCount()
        else:
            return len(self.features)

    def getCategoryManager(self):
        return self.catman

    def addCategory(self, category, icon='DEFAULT'):
        return self.catman.addCategory(category, icon=icon)

    def getCategory(self, categoryid):
        return self.catman.getCategory(categoryid)

    def getCategories(self):
        return self.catman.getCategories()

    def close(self):
        if self.mode in ['w','a']:
            self.maintable.clear()
            self.auxtable.clear()

            aux = AuxTableManager(self.auxtable, endchar=chr(7), searchindex=False)

            # sort categories, note that this will create new category ids
            # and the features have to be updated
            if self.sortcategories:
                cattrans, subcattrans = self.catman.sortCategories()

                # translate categories
                for f in self.features:
                    oldcatid = f.getCategoryId()
                    oldsubcatid = f.getSubCategoryId()

                    f.setCategoryId(cattrans[oldcatid])
                    f.setSubCategoryId(subcattrans[(oldcatid, oldsubcatid)])

            # Sort features on ids
            self.features.sort(lambda x,y: cmp((x.getCategoryId(), x.getSubCategoryId(), x.name.upper()), (y.getCategoryId(), y.getSubCategoryId(), y.name.upper())))


            # Clear category statistics
            for cat in self.catman.getCategories():
                cat.clearStatistics()
                for subcat in cat.getSubCategories():
                    subcat.clearStatistics()

            # Write features to database
            slot = 1
            for f in self.features:
                # Update category statistics
                cat=self.catman.getCategory(f.getCategoryId())
                subcat=cat.getSubCategory(f.getSubCategoryId())
                cat.updateFromPOI(slot,f.getAux()[0])
                subcat.updateFromPOI(slot,f.getAux()[0])
                
                textslot = aux.appendText('\t'.join(f.getAux())+'\t')

                # Update cell elements
                for ref, e in zip(f.cellelementrefs, f.getCellElements(self.map)):
                    e.textslot = textslot
                    e.setCategoryId(f.getCategoryId())
                    e.setSubCategoryId(f.getSubCategoryId())
                    layer = self.map.getPOILayers()[0]
                    layer.updateCellElement(ref, e)
                
                row = Row(self.maintable)
                row.setColumnUInt(self.maintable.getColumnIndex("TEXT_SLOT"), textslot)

                row.setColumnUInt(self.maintable.getColumnIndex("CATG_ID"), f.getCategoryId())
                row.setColumnUInt(self.maintable.getColumnIndex("SUBCAT_ID"), f.getSubCategoryId())
                
                cellelementrefs = f.getCellElementRefs()
                row.setColumnUInt(self.maintable.getColumnIndex("CELL_NUMBER"), cellelementrefs[0][0])
                row.setColumnUInt(self.maintable.getColumnIndex("NUMBER_IN_CELL"), cellelementrefs[0][1]+1)
                self.maintable.writeRow(row)

                slot+=1

        self.catman.close()

    def optimizeLayers(self):
        """Call the optimize function of each member layer and update cell element reference in all features"""

        cellrefremap = {}
        for layer in self.layers:
            remapdict = layer.optimize()

            for feature in self.xfeatures:
                if len(remapdict) > 0:
                    feature.cellelementrefs = tuple([remapdict[ceref] for ceref in feature.cellelementrefs])

    @property
    def layers(self):
        return self.map.getPOILayers()
            

class POICategory:
    fieldinfo_setname='CATEG_AUX_'
    def __init__(self, name):
        self.name = name
        self.id = None
        self.subcategories = []
        self.subcategorydict = {}
        self.fieldnames = []
        self.fieldtypes = []
        self.first_char_slots = 39*[0]
        self.firstslot = 0
        self.lastslot = 0
        self.poicount = 0

    def __eq__(self,x):
        return self.name==x.name and \
               self.subcategories == x.subcategories and \
               self.fieldnames == x.fieldnames and \
               self.fieldtypes == x.fieldtypes

    def setupFromCursor(self, db, cursor):
        # Set name
        row = cursor.asDict()
        self.name = row['NAME'].split(chr(0))[0]
        id = int(row['ID'])
        self.id = id
        
        # Set field descriptions
        fieldinfo_set = db.getSetByName(self.fieldinfo_setname)
        for fcurs in cursor.getSetItems(fieldinfo_set.getMemberByIndex(0)):
            self.fieldtypes.append(fcurs.asDict()['AUX_TYPE'])
            self.fieldnames.append(fcurs.asDict()['NAME'].split(chr(0))[0])
        self.poicount = row['POICOUNT']
        self.first_char_slots = row['FIRSTCHSLOT']
        
        # Get sub categories
        all_subcatg = db.getSetByName('ALL_SUBCATG_')
        self.subcategories = cursor.getSetItemCount(all_subcatg.getMemberByIndex(0)) * [None]
        for subcatcursor in cursor.getSetItems(all_subcatg.getMemberByIndex(0)):
            subcat = POISubCategory(None)
            subcatid = subcat.setupFromCursor(db, subcatcursor)
            self.addSubCategory(subcat, subcatid)

        if 'SLOTFIRST' in row:
            self.firstslot = row['SLOTFIRST']
            self.lastslot = row['SLOTLAST']

        return id

    def addToTable(self, id, db, cattable):
        row = Row(cattable)
        row.setColumnUInt(cattable.getColumnIndex('ID'), id)
        row.setColumnString(cattable.getColumnIndex('NAME'), self.name)
        row.setColumnUInt(cattable.getColumnIndex('POICOUNT'),self.poicount)
        row.setColumnUInt(cattable.getColumnIndex('COMM_SLOT'), 0)
        row.setColumnUIntVector(cattable.getColumnIndex('FIRSTCHSLOT'), self.first_char_slots)
        if 'SLOTFIRST' in cattable.getColumnNames():
            row.setColumnUInt(cattable.getColumnIndex('SLOTFIRST'), self.firstslot)
            row.setColumnUInt(cattable.getColumnIndex('SLOTLAST'), self.lastslot)

        catcursor = cattable.writeRow(row)

        # Add subcategories
        all_subcatg = db.getSetByName('ALL_SUBCATG_')
        subcatmember = all_subcatg.getMemberByIndex(0)
        subcattable = subcatmember.table
        for subcatindex,subcat in enumerate(self.subcategories):
            subcatid = subcatindex+1
            subcatcursor = subcat.addToTable(subcatid, db, subcattable)
            catcursor.addSetItem(subcatmember, subcatcursor)

        # Add fields
        fieldinfo_set = db.getSetByName(self.fieldinfo_setname)
        fieldinfomember = fieldinfo_set.getMemberByIndex(0)
        fieldtable = fieldinfomember.table
        for name,type in zip(self.fieldnames, self.fieldtypes):
            fieldrow = Row(fieldtable)
            fieldrow.setColumnString(fieldtable.getColumnIndex('NAME'), name)
            fieldrow.setColumnUInt(fieldtable.getColumnIndex('AUX_TYPE'), type)
            fieldcursor = fieldtable.writeRow(fieldrow)
            catcursor.addSetItem(fieldinfomember, fieldcursor)
                    
        return catcursor
        
    def getFieldNames(self): return self.fieldnames
    def getFieldTypes(self): return self.fieldtypes

    def getName(self): return self.name

    def clearStatistics(self):
        self.firstslot = 0
        self.lastslot = 0
        self.poicount = 0
        self.first_char_slots = 39*[0]

    def updateFromPOI(self, slot, name):
        if self.firstslot == 0:
            self.firstslot = slot
        self.lastslot = max(self.lastslot, slot)
        if self.first_char_slots[sortHashFunc(name)] == 0:
            self.first_char_slots[sortHashFunc(name)]=slot
        self.poicount+=1

    def setLastPOI(self, name, slot):
        self.slotlast = slot
    
    def __repr__(self):
        return str(self.name)+" (" + str(self.getPOICount()) +") " + str(self.fieldnames) +  str(self.fieldtypes) +"\n"+ "".join(["  "+str(sc) for sc in self.subcategories])

    def addSubCategory(self, subcat, id=None):
        if id != None and id != len(self.subcategories)+1:
            self.subcategories[id-1]=subcat
            subcat.id = id
        else:
            subcat.id = len(self.subcategories) + 1
            self.subcategories.append(subcat)

        self.subcategorydict[subcat.name] = subcat

        return subcat

    def addField(self, name, type=1):
        self.fieldnames.append(name)
        self.fieldtypes.append(type)

    def getSubCategory(self, id):
        return self.subcategories[id-1]

    def getSubCategoryByName(self, name):
        return self.subcategorydict[name]

    def getSubCategories(self):
        return self.subcategories

    def getSubCategoryIds(self):
        return range(1,len(self.subcategories)+1)

    def getPOICount(self):
        return self.poicount

    def setCategoryId(self, id):
        self.id = id

class POISubCategory(POICategory):
    fieldinfo_setname='SUBCATEG_AUX_'

class POICategoryManager:
    def __init__(self):
        self._categories = []
        self._categorydict = {}
        
        self.mode = 'r'
        self.db = None
        self.icons = {}
        self.maxid = 0

    def getCategories(self):
        return self._categories

    def getCategory(self, id):
        return self._categories[id-1]

    def getCategoryByName(self, name):
        return self._categorydict[name]

    def addCategory(self, category, icon = 'DEFAULT'):
        category.id = len(self._categories) + 1
        
        self._categories.append(category)
        self._categorydict[category.name] = category

        self.setIcon(category.id, icon)

        return category
    
    def setIcon(self, catid, icon):
        if icon not in POIIcons:
            raise Exception('Invalid icon %s'%icon)

        self.icons[catid] = icon
    
    def open(self, db, mode='r', poiprefix="poi"):
        self.mode = mode
        self.db = db
        if mode in ['r','a']:
            self.tCat = db.getTableByName("CATEG_INFO_")
            self.tSubCat = db.getTableByName("SUBCATG_INFO_")
            self.tPoiDescr = db.getTableByName("AUX_NAME_")

            id = 1
            for cursor in self.tCat.getCursor(0):
                cat = POICategory(None)
                if cat.setupFromCursor(db, cursor) != id:
                    raise Exception('Categories need to be stored in id order')
                self._categories.append(cat)
                id += 1
        elif mode == 'w':
            # If tables exists clear their contents and if not
            # create new tables in the database schema
            if 'CATEG_INFO_' not in db.getTableNames():
                createPOITables(db, poiprefix)
                
            self.tCat = db.getTableByName("CATEG_INFO_")
            self.tSubCat = db.getTableByName("SUBCATG_INFO_")
            self.tPoiDescr = db.getTableByName("AUX_NAME_")

    def close(self):
        if self.mode in ['w','a']:
            self.tCat.clear()
            self.tSubCat.clear()
            self.tPoiDescr.clear()
            
            for catindex,cat in enumerate(self._categories):
                catid = catindex+1
                cat.addToTable(catid, self.db, self.tCat)

    def sortCategories(self):
        cattranslation = {}
        subcattranslation = {}

        # Update category ids
        catid=1
        for cat in self._categories:
            cat.id = catid
            subcatid = 1
            for subcat in cat.getSubCategories():
                subcat.id = subcatid
                subcatid += 1
            catid += 1

        # Sort on name
        self._categories.sort(lambda x,y: cmp(x.name.upper(), y.name.upper()))

        catid=1
        for cat in self._categories:
            cattranslation[cat.id]=catid

            cat.subcategories.sort(lambda x,y: cmp(x.name.upper(), y.name.upper()))
            
            subcatid = 1
            for subcat in cat.getSubCategories():
                subcattranslation[(cat.id,subcat.id)]=subcatid
                subcatid += 1
            catid += 1
 
        # Update category ids
        catid=1
        for cat in self.categories:
            cat.id = catid
            subcatid = 1
            for subcat in cat.getSubCategories():
                subcat.id = subcatid
                subcatid += 1
            catid += 1

        return cattranslation, subcattranslation
        

class FeaturePOI(Feature):
    def __init__(self, cellelementrefs, aux, categoryid, subcategoryid):
        """Create an instance of a feature given a name, an object type and a list of cell elements."""
        Feature.__init__(self, 0, cellelementrefs,
                         aux=tuple(aux), categoryid=categoryid, subcategoryid=subcategoryid)
#    def __hash__(self):
#        return hash(self.categoryid) ^ hash(self.cellelements) ^ hash(self.categoryid) ^ hash(self.subcategoryid)

    def getAux(self):
        return self.attributes['aux']

    @property
    def name(self):
        return self.attributes['aux'][0]

    def getAuxAsDict(self, poigroup):
        catman = poigroup.getCategoryManager()
        cat=catman.getCategory(self.getCategoryId())
        subcat=cat.getSubCategory(self.getSubCategoryId())
        fieldnames=cat.getFieldNames()+subcat.getFieldNames()
        if len(fieldnames)!=len(self.getAux()):
            raise ValueError("Aux fields doesn't match category")
        return dict(zip(fieldnames, self.getAux()))

    def setAux(self, aux):
        self.attributes['aux'] = aux

    def getCategoryId(self): return self.attributes['categoryid']
    def getSubCategoryId(self): return self.attributes['subcategoryid']

    def getCellElements(self, map):
        layer = map.getPOILayers()[0]
        return [layer.getCellElement(ceref) for ceref in self.cellelementrefs]
        
    def setCategoryId(self, id):
        self.attributes['categoryid'] = id
    def setSubCategoryId(self, id):
        self.attributes['subcategoryid'] = id

    def __repr__(self):
        return "FeaturePOI(%s,%d,%d)"%(self.getAux()[0],self.getCategoryId(), self.getSubCategoryId())

class POILayerConfig(Layer.LayerConfig):
    def __init__(self):
        Layer.LayerConfig.__init__(self)

    def writecfg(self, cfg, mapobj):
        Layer.LayerConfig.writecfg(self, cfg, mapobj)
        
        group = mapobj.getPOIGroup()

        icons = group.catman.icons
        cfg.set('LAYERS', 'POI_CAT2ICON', 
                ' '.join([str(len(icons))] + reduce(operator.__add__, [[str(i), icon] for i,icon in icons.items()], [])))

    def setupfromcfg(self, cfg, mapobj):
        Layer.LayerConfig.setupfromcfg(self, cfg, mapobj)

        group = mapobj.getPOIGroup()
        
        if group:
            cat2icon = cfg.get('LAYERS','POI_CAT2ICON').split(" ")

            n = int(cat2icon.pop(0))

            if n != len(cat2icon) / 2:
                raise Exception('Corrupt POI config')

            for i in range(n):
                id = int(cat2icon.pop(0))
                icon = cat2icon.pop(0)
                group.catman.setIcon(id, icon)

    def getLayerAndGroupByName(self, name, map):
        return self._layers[0], map.getPOIGroup()
