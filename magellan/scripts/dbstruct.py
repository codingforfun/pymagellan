import sys
import os
from magellan.DBUtil import Database
from magellan.mapdir import MapDirectory
from magellan.rsttable import toRSTtable

dbname = sys.argv[1]
db = Database(MapDirectory(os.path.dirname(dbname)), os.path.basename(dbname))

## Print schema
print db.schema

## Print data
for table in db.tables:
    print 80*'='
    print table.name
    print 80*'='
    print
    print toRSTtable([table.getColumnNames()] + [row.asList() for i, row in enumerate(table.getCursor(0)) if i < 100])
    print
    


