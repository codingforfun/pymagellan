#!/usr/bin/env python
import sys
import magellan.mapdir as mapdir

def usage():
    print "Magellan image file extractor.\n";
    print "Usage: imgextract.py IMGFILE\n";
    sys.exit(2);

if len(sys.argv) != 2:
    usage()

imagefile = sys.argv[1]

mapdir.extract_image(imagefile, ".")
