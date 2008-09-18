#!/usr/bin/env python
import magellan.Map as Map
import osmmagellan.osmrules as osmrules
import sys
from optparse import OptionParser, BadOptionError, OptionValueError
import os

version = '0.0'

def main():
    parser = OptionParser(usage='usage: %prog [options] mapimage.imi',
                          version=version,
                          prog='magrules',
                          description='magrules creates a osmmag XML rule file from a Magellan map image file')

    (options, imagefiles) = parser.parse_args()

    if len(imagefiles) == 0:
        parser.print_usage()
        sys.exit()

    mi = Map.MapImage(imagefiles[0])

    mi.open('r')
    
    mapnumber = 0

    m = mi.maps[mapnumber]

    m.open()

    osmrules.createRulesFromMap(m).write(sys.stdout)
               
if __name__ == "__main__":
    main()
