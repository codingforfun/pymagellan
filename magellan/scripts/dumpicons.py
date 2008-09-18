#!/usr/bin/env python
import magellan.icons as icons
import magellan.mapdir as mapdir
import sys
import os

def usage():
    print "Usage: dumpicons imagefile destdir"

def main():

    if len(sys.argv) != 3:
        usage()
        exit

    ## Dump all
    it = icons.IconTable(mapdir.Image(sys.argv[1], bigendian=False), "bmp4bit.ics")
    
    for id, icon in it.icons.items():
        print id
        if id < 10000:
            try:
                icon.getImage().save(os.path.join(sys.argv[2],'icon%x.png'%id))
            except:
                pass


main()
