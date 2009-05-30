from xml.etree.ElementTree import XMLTreeBuilder, Element
from pyPgSQL import PgSQL

import osm

class SQLBuilder(object):
    """Parse a rule file and build OSM PostgreSQL queries"""
    def __init__(self, box_way_list=None, box_node_list=None):
        self.rulestack = []
        self.result = []
        self.box_way_list = box_way_list
        self.box_node_list = box_node_list        

    def start(self, tag, attrib):   # Called for each opening tag.
        if tag == 'rule':
            self.rulestack.append(attrib)
        elif tag in ('polygon', 'polyline', 'point', 'poi'):
            self.statement = Element(tag, **attrib)

    def end(self, tag):             # Called for each closing tag.
        if tag in ('polygon', 'polyline', 'point', 'poi'):
            ## Check that all nested rules has the same element
            element = self.rulestack[0]['e']
            for attrib in self.rulestack[1:]:
                if attrib['e'] != element:
                    raise ValueError('Nested rules must refer to same element')
                
            if element == 'way':
                query = self._make_query('way_tags', 'way_id',
                                         self.box_way_list)
            elif element == 'node':
                query = self._make_query('node_tags', 'node_id',
                                         self.box_node_list)

            self.result.append((self.statement, element, query))

        if tag == 'rule':
            self.rulestack.pop()

    def data(self, data):
        pass            # We do not need to do anything with data.
    def close(self):    # Called when all data has been parsed.
        return self.maxDepth

    def _make_query(self, table, id, box_list):
        query = 'SELECT %s ' \
            'FROM %s '%(id, table)

        if box_list != None:
            query += 'INNER JOIN %s ON %s.%s = %s.id '%(box_list, 
                                                        table, id,
                                                        box_list)
            
        if len(self.rulestack) > 0:
            query += 'WHERE '
            conditions = []
            for attrib in self.rulestack:
                keys = [repr(s) for s in attrib['k'].split('|')]

                if attrib['v'] == '~':
                    conditions.append('k NOT IN (%s)'%', '.join(keys))
                else:
                    if '*' not in attrib['k']:
                        conditions.append('k IN (%s)'%', '.join(keys))

                    if attrib['v'] != '*':
                        values = [repr(s) for s in attrib['v'].split('|')]
                        conditions.append('v IN (%s)'%', '.join(values))

            query += ' AND '.join(conditions)

        return query

def build_sql_queries(filename, bbox=None):
    target = SQLBuilder(box_node_list='box_node_list',
                        box_way_list='box_way_list')
    init_queries = []

    ## If bounding box is given, create a temporary table and
    ## store all matching nodes there
    if bbox != None:
        ## Create tables
        init_queries.append("CREATE TEMPORARY TABLE box_node_list "
                            "(id bigint PRIMARY KEY) ON COMMIT DROP")
        init_queries.append("CREATE TEMPORARY TABLE box_way_list "
                            "(id bigint PRIMARY KEY) ON COMMIT DROP")
        
        ## Fill them
        bbox_sql = "GeomFromEWKT('POLYGON((%f %f,%f %f,%f %f,%f %f,%f %f))')"%\
            (bbox[0],bbox[1],bbox[2],bbox[1],bbox[2],bbox[3],bbox[0],bbox[3],
             bbox[0],bbox[1])

        srid = "find_srid('','nodes','geom')"

        init_queries.append("INSERT INTO box_node_list SELECT id FROM nodes "
                            "WHERE (geom && SetSRID(%s,%s) )"%(bbox_sql,srid))

        init_queries.append("INSERT INTO box_way_list "
                            "SELECT wn.way_id FROM way_nodes wn "
                            "INNER JOIN box_node_list n ON wn.node_id = n.id "
                            "GROUP BY wn.way_id")

    parser = XMLTreeBuilder(target=target)

    parser.feed(open(filename).read())

    return init_queries, target.result

class MapBuilderSQL(osm.MapBuilder):
    def __init__(self, rules, mapobj, bbox,
                 nametags = None, 
                 routable = False, dbhost = 'localhost',
                 dbname = 'osm',
                 dbuser = 'osm',
                 dbpass = None):
        
        self.dbname = dbname
        self.dbhost = dbhost
        self.dbuser = dbuser
        self.dbpass = dbpass

        self.bbox = bbox

        super(MapBuilderSQL, self).__init__(rules, mapobj, nametags, routable)
        
    
    def load(self):
        self.connect()

        init_queries, rules = build_sql_queries(self.rules.filename, self.bbox)

        for query in init_queries:
            cursor = self.dbh.cursor()
            cursor.execute(query)

        for rule in rules:
            statement, element, query = rule
            
            cursor = self.dbh.cursor()
            cursor.execute(query)

            if element == 'way':
                for way in cursor.fetchall():
                    ## Get tags
                    query = "SELECT k, v FROM way_tags " \
                            "WHERE way_id = %s"%way[0]

                    cursor_tags = self.dbh.cursor()
                    cursor_tags.execute(query)

                    tags = dict(cursor_tags.fetchall())

                    ## Get node coordinates
                    query = "SELECT X(nodes.geom), Y(nodes.geom) " \
                            "FROM nodes, way_nodes " \
                            "WHERE nodes.id = way_nodes.node_id AND "\
                            "   way_nodes.way_id = %s " \
                            "ORDER BY way_nodes.sequence_id"%way[0]

                    cursor_way_nodes = self.dbh.cursor()
                    cursor_way_nodes.execute(query)

                    coords = [tuple(coord) for coord in cursor_way_nodes.fetchall()]
                    
                    ## Add element
                    self.add_element(statement, tags, coords)
            elif element == 'node':
                for node in cursor.fetchall():
                    ## Get tags
                    query = "SELECT k, v FROM node_tags " \
                            "WHERE node_id = %s"%node[0]

                    cursor_tags = self.dbh.cursor()
                    cursor_tags.execute(query)

                    tags = dict(cursor_tags.fetchall())

                    ## Get node coordinate
                    query = "SELECT X(nodes.geom), Y(nodes.geom) FROM nodes " \
                            "WHERE id = %s"%node[0]

                    cursor_way_nodes = self.dbh.cursor()
                    cursor_way_nodes.execute(query)

                    coords = [tuple(coord) for coord in cursor_way_nodes.fetchall()]

                    ## Add element
                    self.add_element(statement, tags, coords)

    def connect(self):
        """ Connect to the database"""
        if len(self.dbhost):
            self.dbh = PgSQL.connect(database=self.dbname, host=self.dbhost, 
                                     user=self.dbuser, password=self.dbpass,
                                     client_encoding="utf-8",
                                     unicode_results=1)
        else:
            self.dbh = PgSQL.connect(database=self.dbname, 
                                     user=self.dbuser, 
                                     password=self.dbpass,
                                     client_encoding="utf-8",
                                     unicode_results=1)
            
if __name__ == "__main__":
    import doctest
    doctest.testmod()

    print build_sql_queries('data/osmmagrules.xml', bbox = [10,20,30,40])
