import os
import tempfile
import shutil
from shutil import copy2

def dump(x):
    return " ".join(["0x%02x "%ord(c) for c in x])

class TempDir:
    def __init__(self, srcdir=None, keep=False):
        self.keep = keep
        self.dir = tempfile.mkdtemp()

        if srcdir:
            copytree(srcdir, self.dir)
        
    def __str__(self):
        return self.dir
    def __del__(self):
        if not self.keep:
            shutil.rmtree(self.dir)

def copytree(src, dst, symlinks=0):
    names = os.listdir(src)
    for name in names:
        if name == '.svn':
            continue
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks)
            else:
                copy2(srcname, dstname)
        except (IOError, os.error), why:
            print "Can't copy %s to %s: %s" % (`srcname`, `dstname`, str(why))

