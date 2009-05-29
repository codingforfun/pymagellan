#!/usr/bin/env python

import magellan.Map as Map
import osmmagellan.osm as osm
from osmmagellan.osmrulesfast import OSMMagRules as OSMMagRules
#from osmmagellan.osmrulesfast import OSMMagRulesFast as OSMMagRules

import sys
from optparse import OptionParser, BadOptionError, OptionValueError
import tempfile
import os
import logging

version = '0.0'

def osmmag(outfile, osmfiles = [], bbox=None, topo=None, name=None, 
           inmemory=True, rulefile=None,
           nametaglist = None, bigendian = False,
           topostartscale = None, topointervals = None,
           routable = False,
           scale = None,
           fromdb = False,
           download = False):
           
    logging.info('Loading rules: %s'%rulefile)
        
    rules = OSMMagRules(rulefile)

    if outfile:
        mi = Map.MapImage(outfile, bigendian = bigendian)

        mi.open("w")

        tempfiles = []

        try:
            ## Download region if bounding box is supplied
            if download:
                logging.info('Downloading region with bounding box ' + str(bbox))

                if len(osmfiles) == 1:
                    filename = args.pop(0)
                else:
                    filename = tempfile.mktemp(".xml")
                    tempfiles.append(filename)

                osm.downloadOsm(bbox, filename)
                osmfiles = [filename]

            if routable:
                logging.info('Creating routable map')
                maptype = Map.MapTypeStreetRoute
            else:
                maptype = Map.MapTypeNormal

            m = rules.createMap(mi.createMap(maptype=maptype), 
                                routable = routable)

            m.inmemory = inmemory

            if scale:
                m.scale = scale

            ## Read data
            logging.info('Reading osm data and creating map')
            if fromdb:
                import sqlbuilder
                data = sqlbuilder.MapBuilderSQL(rules, m, bbox, 
                                                nametags = nametaglist, 
                                                routable = routable, 
                                                dbhost = 'localhost',
                                                dbname = 'osm',
                                                dbuser = 'osm',
                                                dbpass = None)
                data.load()
                
                ## Add coastline
                logging.info('Create hydro polygons from coastline')
                data.addCoastLinePolygon()
            else:
                for osmfile in osmfiles:
                    data = osm.LoadOsm(osmfile, rules, m, nametags = nametaglist, 
                                       routable = routable, inmemory = inmemory)
                    data.load()

                    ## Add coastline
                    logging.info('Create hydro polygons from coastline')
                    data.addCoastLinePolygon()

            if name:
                m.name = name
            else:
                m.name = "OpenStreetMap derived map generated by osmmag V%s"\
                    %version
            m.close()

            ## Add topo
            if topo:
                import osmmagellan.dem as dem

                logging.info('Adding topo')

                bbox = m.bbox[0] + m.bbox[1]

                blxfile = tempfile.mktemp(".blx")

                tempfiles.append(blxfile)

                dem.convert2blx(topo, blxfile, bbox, bigendian=bigendian)
                mi.addTopo(blxfile)

                if topostartscale:
                    mi.topo.blxsets[0].lowerscaleindex = topostartscale
                if topointervals:
                    mi.topo.blxsets[0].contourlevels = topointervals

        finally:
            for filename in tempfiles:
                if os.path.exists(filename):
                    os.unlink(filename)

        mi.close()


def parseIntList(option, opt_str, value, parser):
    try:
        setattr(parser.values, option.dest, map(int, value.split(',')))
    except:
        raise OptionValueError('invalid argument of ' + opt_str)

def parseStringList(option, opt_str, value, parser):
    try:
        setattr(parser.values, option.dest, value.split(','))
    except:
        raise OptionValueError('invalid argument of ' + opt_str)

def main():

    usage = 'usage: %prog [options] [file1.osm] [file2.osm] [...]'
    parser = OptionParser(usage=usage,
                          version=version,
                          prog='osmmag',
                          description='OpenStreetmap to Magellan map converter, '
                                      'by Henrik Johansson (henjo2006@gmail.com)')

    parser.add_option('-o', '--output', dest='output',
                      help='output Magellan GPS image file', metavar='FILE')

    parser.add_option('-n', '--name', dest='name', 
                      help='name of the generated map', metavar='NAME')

    parser.add_option('-r', '--rules', dest='rulefile', 
                      help='map generation rule file', metavar='FILE')

    parser.add_option('--download', dest='download', action='store_true',
                      default = False,
                      help='download data from OSM servers')

    parser.add_option('-b', '--bbox', dest='bbox', type='float', nargs=4, 
                      metavar='minLon minLat maxLon maxLat',
                      help='bounding box used for download and database access')

    parser.add_option('-q', '--quantization', dest='scale', type='float', 
                      nargs=2, metavar='lonstep, latstep',
                      help='quantization step used when the floating point '
                      'coordinates are converted to integer. '
                      'Default value is ' + str(tuple(Map.Map.defaultscale)))

    parser.add_option('-t', '--topo', dest='topo', metavar='FILE',
                      help='add topographical information from FILE which is a '
                           'georeferenced raster file in WGS84 reference system '
                           'that is supported by GDAL')

    parser.add_option('--topostartscale', dest='topostartscale', metavar='INDEX',
                      type='int',
                      help='index to first scale level that will contain '
                            'topo contours')

    parser.add_option('--topointervals', dest='topointervals', 
                      metavar='L0,L1,...', type='string',
                      action='callback', callback=parseIntList,
                      help='topo contour intervals for each scale level')

    parser.add_option('--name-tag-list', dest='nametaglist', 
                      metavar='nametag1,nametag2...', type='string',
                      action='callback', callback=parseStringList,
                      help='Specify the tag that will be used to supply the name.'
                           ' Useful for language variations. '
                           'You can supply a list and the first one will be used.'
                           'eg. --name-tag-list=name:en,int_name,name')

    parser.add_option('-v', '--verbose', action='store_true', dest='verbose', 
                      default=False,
                      help='Verbose output')

    parser.add_option('--big-endian', action='store_true', dest='bigendian', 
                      default=False,
                      help='Write big-endian image')

    parser.add_option('-d', '--disk', dest='inmemory', action='store_false', 
                      default=True,
                      help='Preserve memory by storing geometries on disk')

    parser.add_option('--from-database', dest='fromdb', 
                      action='store_true', 
                      default=False,
                      help='Read from a PostgreSQL (osmosis schema)')
    
    parser.add_option('--routable', dest='routable', action='store_true', 
                      default=False,
                      help='Create routable map')

    (options, osmfiles) = parser.parse_args()

    if not options.fromdb and len(osmfiles) == 0 and options.bbox == None:
        parser.print_usage()
        sys.exit()

    if options.verbose:
        loglevel = logging.INFO
    else:
        loglevel = logging.WARNING

    logging.basicConfig(format='%(levelname)s %(message)s', level=loglevel)
        
    osmmag(options.output,
           osmfiles=osmfiles,
           download=options.download,
           bbox=options.bbox,
           name=options.name,
           rulefile=options.rulefile,
           nametaglist=options.nametaglist,
           inmemory=options.inmemory,
           topo=options.topo,
           topostartscale=options.topostartscale,
           topointervals=options.topointervals,
           routable=options.routable,
           scale=options.scale,
           bigendian=options.bigendian,
           fromdb=options.fromdb
           )            
               
if __name__ == "__main__":
    main()
