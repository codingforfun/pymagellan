#!/usr/bin/env python
import sys
import magellan.mapdir as mapdir

def usage():
    print "Magellan image file creator"
    print "Usage: imgextract.py IMGFILE SOURCEDIR\n";
    sys.exit(2);

if len(sys.argv) != 3:
    usage()

imagefile = mapdir.Image(sys.argv[1])
src = mapdir.MapDirectory(sys.argv[2])
imagefile.copyfrom(src)

