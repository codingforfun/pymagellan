"""
The Topo module handles topographical map function for Magellan GPS maps
"""

import re
import os
from inifile import ConfigParserUpper, IniFileFilter
from inifile import ConfigParserTopo
from numpy import *
from Layer import zoomlevels

class BLXSet(object):
    """Class that describes how a set BLX topo files are rendered on the GPS unit"""
    screen_mesh = 10
    auto_step = 1
    _lowerscaleindex = 1
    _contourlevels = array([20, 20, 20, 40, 80]) # m
    _contourlevels_feet = array([20, 20, 20, 40, 80])*3 # feet
    _labelangle = 30
    label_mode = 2
    memory = [4,10,40,32]
    
    """BLXInfo holds information about a blx file and how it should be displayed"""
    def __init__(self, blxfiles = []):
        self.blxfiles = list(blxfiles)

    @property
    def contourlevels_feet(self): return self._contourlevels_feet

    @property
    def labelangle(self):
        """Lable angle for each scale"""
        try:
            return list(self._labelangle)
        except TypeError:
            return len(self._contourlevels) * [self._labelangle]

    def _set_contourlevels(self, contourlevels):
        if len(contourlevels) + self._lowerscaleindex - 1 > len(zoomlevels):
            raise ValueError("The number of contour levels must not exceed the total number of scales")
        self._contourlevels = array(contourlevels)
        self._contourlevels_feet = array(contourlevels) * 3.2808399
        self._contourlevels_feet = self._contourlevels_feet.round()
        
    def _get_contourlevels(self): return self._contourlevels
    contourlevels = property(_get_contourlevels, _set_contourlevels, doc="The contour line altitudes for different zoom levels")

    def _set_lowerscaleindex(self, value):
        if value < 1 or value > len(zoomlevels):
            raise ValueError("lowerscaleindex must be in range 1-%d"%len(zoomlevels))
        self._lowerscaleindex = value
    def _get_lowerscaleindex(self): return self._lowerscaleindex
    lowerscaleindex = property(_get_lowerscaleindex, _set_lowerscaleindex, doc="The index of the minimum zoom level that will have contours")

    def addblxfile(self, blxfile, mapdir = None, bigendian=False):
        """Add BLX file to set. If mapdir is supplied the file will be copied to the mapdir"""

        if bigendian:
            ext = '.xlb'
        else:
            ext = '.blx'

        ## The file name must follow the naming scheme XXt0.blx
        src = blxfile
        blxfile = '%02dt0%s'%(len(self.blxfiles), ext)

        if mapdir != None:
            mapdir.copyfile(src, blxfile)

        self.blxfiles.append(blxfile)

    def setupFromIni(self, cfg, section):
        nfiles, zoomlevels = map(int, cfg.get(section, 'total_blx_scale').split(' '))

        self.blxfiles = []
        for i in range(nfiles):
            self.blxfiles.append(cfg.get(section, str(i)))

        self.lowerscaleindex = int(cfg.get(section, 'lower_scale_index'))

        params = re.split('\s+', cfg.get(section, 'params'))
        self._contourlevels = []
        self._contourlevels_feet = []
        self._labelangle = []
        for zl in range(zoomlevels):
            self._contourlevels.append(int(params[zl*3]))
            self._contourlevels_feet.append(int(params[zl*3+1]))
            self._labelangle.append(int(params[zl*3+2]))

        self.screen_mesh = int(cfg.get(section, 'screen_mesh'))

        self.label_mode = int(cfg.get(section, 'label_mode'))

        self.auto_step = int(cfg.get(section, 'auto_step'))

        self.memory = map(int, re.split('\s+', cfg.get(section, 'memory')))

    def writeToIni(self, cfg, section):
        cfg.add_section(section)

        for i, blxfile in enumerate(self.blxfiles):
            cfg.set(section, str(i), blxfile)
            
        cfg.set(section, 'total_blx_scale', '%d %d'%(len(self.blxfiles), len(self._contourlevels)))
        cfg.set(section, 'lower_scale_index', str(self.lowerscaleindex))

        params = []
        params = ['%s %s %s'%(cl,contourlevels_feet,labelangle) \
                  for cl,contourlevels_feet,labelangle in
                  zip(self._contourlevels, self._contourlevels_feet, self.labelangle)]
        cfg.set(section, 'params', '  '.join(params))

        cfg.set(section, 'screen_mesh', str(self.screen_mesh))
        cfg.set(section, 'label_mode', str(self.label_mode))
        cfg.set(section, 'auto_step', str(self.auto_step))
        cfg.set(section, 'memory', ' '.join(map(str, self.memory)))

    def __repr__(self):
        s =  'files          : %s\n'%" ".join(self.blxfiles)
        s += 'lower scale idx:%d\n'%self.lowerscaleindex
        s += 'contour levels (m): '+str(self.contourlevels)+'\n'
        s += 'contour levels (feet): '+str(self.contourlevels_feet)+'\n'
        s += 'label angle          : '+str(self.labelangle)+'\n'
        s += 'auto_step      : '+str(self.auto_step)+'\n'
        s += 'label_mode     : '+str(self.label_mode)+'\n'
        s += 'screen_mesh    : '+str(self.screen_mesh)
        return s
        
                
class Topo(object):
    """
    Topo holds information about a set of BLX files

    >>> from Map import Map
    >>> from mapdir import MapDirectory
    >>> mapdir = MapDirectory('./test/layerdata8')
    >>> topo = Topo(mapdir)
    >>> topo.blxsets[0]
    files          : 00t0.blx
    lower scale idx:1
    contour levels (m): [20, 20, 20, 40, 80]
    contour levels (feet): [8, 12, 20, 40, 100]
    label angle          : [30, 30, 30, 30, 30]
    auto_step      : 1
    label_mode     : 2
    screen_mesh    : 10
    
    """
    def __init__(self, mapdir):
        self.mapdir = mapdir
        self.blxsets = []
        self.cfgfilename = None

        for cfgfilename in ('topo3d.ini',):
            if self.mapdir.exists(cfgfilename):
                cfgfile = mapdir.open(cfgfilename)
                if cfgfile:
                    self.cfgfilename = cfgfilename
                    break

        if self.cfgfilename:
            cfg = ConfigParserUpper()
            cfg.readfp(IniFileFilter(cfgfile))

            blxset = BLXSet()
            self.blxsets.append(blxset)

            blxset.setupFromIni(cfg, 'BLX0')
        else:
            self.blxsets = [BLXSet()]
        

    def addblx(self, blxfile, blxsetindex=0, bigendian=False):
        self.blxsets[blxsetindex].addblxfile(blxfile, self.mapdir, bigendian=bigendian)
        self.write()
        
    def write(self):
        cfg = ConfigParserTopo()

        for i,blxset in enumerate(self.blxsets):
            blxset.writeToIni(cfg, 'BLX%d'%i)

        cfgfilename = self.cfgfilename or 'topo3d.ini'
        cfgfile = self.mapdir.open(cfgfilename, 'w')

        cfg.write(cfgfile)
        

if __name__ == "__main__":
    import doctest
    doctest.testmod()
