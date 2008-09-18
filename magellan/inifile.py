from ConfigParser import SafeConfigParser as ConfigParser

class IniFileFilter:
    def __init__(self, fh):
        self.fh = fh
    def readline(self):
        line = self.fh.readline()
        
        ## Filter out trailing padding byte
        if len(line) > 0 and line[-1] == chr(0xa):
            return line
        else:
            return ""

def cmpfunc(x,y):
    """Compare items with numbers in the end"""
    x = x[0]
    y = y[0]

    xnum = x[0].isdigit()
    ynum = y[0].isdigit()
    
    if xnum and not ynum:
        return 1
    if ynum and not xnum:
        return -1

    if xnum:
        x = int(x[0])
    if ynum:
        y = int(y[0])

    return cmp(x,y)    

class ConfigParserUpper(ConfigParser):
    def write(self, fp):
        """Write an .ini-format representation of the configuration state."""

        if self._defaults:
            fp.write("[%s]\r\n" % DEFAULTSECT)
            for (key, value) in self._defaults.items():
                fp.write("%s=%s\r\n" % (key, str(value).replace('\n', '\n\t')))
            fp.write("\r\n")
        for section in self._sections:
            fp.write("[%s]\r\n" % section)
            items = self._sections[section].items()
            items.sort(cmpfunc)
            for (key, value) in items:
                if key != "__name__":
                    fp.write("%s=%s\r\n" %
                             (key.upper(), str(value).replace('\n', '\n\t')))
            fp.write("\r\n")


class ConfigParserTopo(ConfigParser):
    def write(self, fp):
        """Write an .ini-format representation of the configuration state."""

        if self._defaults:
            fp.write("[%s]\r\n" % DEFAULTSECT)
            for (key, value) in self._defaults.items():
                fp.write("%s=%s\r\n" % (key, str(value).replace('\n', '\n\t')))
            fp.write("\r\n")
        for section in self._sections:
            fp.write("[%s]\r\n" % section)
            for (key, value) in self._sections[section].items():
                if key != "__name__":
                    fp.write("%s=%s\r\n" %
                             (key, str(value).replace('\n', '\n\t')))
            fp.write("\r\n")

