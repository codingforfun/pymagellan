# -*- coding: latin-1 -*-
import os
import glob
import re

"""
Conversion between unicode and latin-1
"""


def determine_path ():
    """Borrowed from wxglade.py"""
    try:
        root = __file__
        if os.path.islink (root):
            root = os.path.realpath (root)
        return os.path.dirname (os.path.abspath (root))
    except:
        print "I'm sorry, but something is wrong."
        print "There is no __file__ variable. Please contact the author."
        sys.exit ()
datadir = os.path.join(determine_path(), "data")

class UnicodeTranslator(object):
    """Class that loads a unicode to latin-1 translation table and perform translations

    >>> ut = UnicodeTranslator()
    >>> ut.translate(u'Timi\u0219oara')
    'Timisoara'
    
    """
    def __init__(self, tablepath = os.path.join(datadir, 'chars', 'ascii')):
        self.charmap = {}
        self.loadtable(tablepath)
        
    def loadtable(self, tablepath):
        """Load table"""
        for filename in glob.glob(os.path.join(tablepath, 'row*.trans')):
            for line in open(filename).readlines():
                ## Remove comment
                line = line.split('#')[0]
                ## Strip linefeed
                line.strip()

                line = re.split(r'\s+', line)

                if len(line) >= 2 and line[0][0:2] == 'U+':
                    char, replacement = line[0:2]
                    charnum = int(char[2:], 16)
                    self.charmap[charnum] = unicode(replacement)
                
    def translate(self, s):
        s = s.translate(self.charmap)
        return s.encode("iso-8859-1", "replace")

if __name__ == "__main__":
    import doctest
    doctest.testmod()

