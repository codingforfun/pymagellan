from osgeo import gdal
from osgeo.gdalconst import GA_ReadOnly
from math import floor, ceil
import logging

class Extent(object):
    def __init__(self, west, south, east, north):
        self.west = west
        self.south = south
        self.east = east
        self.north = north

    @property
    def width(self):
        return abs(self.east - self.west)

    @property
    def height(self):
        return abs(self.north - self.south)

    def __contains__(self, b):
        if not isinstance(b, Extent):
            return False
        return b.west >= self.west and b.south >= self.south and b.east <= self.east and b.north <= self.north

    def __repr__(self):
        return "(%0.4f %0.4f)-(%0.4f %0.4f)"%(self.west, self.south, self.east, self.north)

def convert2blx(src, dest, bbox, bigendian=False, zscale=1):
    """Convert a GDAL source cropped to the given bounding box to a BLX file

    Parameters
    ----------
    src       GDAL compatible data source
    dest      BLX filename
    bbox      Bounding box (minlon, minlat, maxlon, maxlat)
    bigendian True if big-endian BLX (.xlb)
    zscale    Vertical quantization step. Higher values give higher compression
              and lower resolution

    Example:
    
    >>> convert2blx("test/dem/sweden.tif", "lund.blx", (13.004623199999999,55.610084499999999,13.555224900000001,55.793481),\
       bigendian=False)

    
    """
    srcdataset = gdal.Open(src, GA_ReadOnly )

    bands = srcdataset.RasterCount

    if bands != 1:
        raise ValueError("DEM data set must have exactly one band")
    srcband = srcdataset.GetRasterBand(1)

    xsize = srcdataset.RasterXSize
    ysize = srcdataset.RasterYSize

    geotransform = srcdataset.GetGeoTransform()
    projection = srcdataset.GetProjection()

    north = geotransform[3]
    south = geotransform[3]+geotransform[5]*ysize
    east = geotransform[0]+geotransform[1]*xsize
    west = geotransform[0]

    psizex = geotransform[1]
    psizey = geotransform[5]

    

    srcextent = Extent(west,south,east,north)

    logging.debug("Input (%s):\n" % src +
                  "  Driver: %s/%s\n"%(srcdataset.GetDriver().ShortName, srcdataset.GetDriver().LongName) +
                  "  Size: %dx%dx%d\n"%(xsize, ysize, bands) +
                  "  Projection: %s\n"%projection +
                  "  NSEW: %s\n"%str((north, south, east, west)))
        
    # CHECK: Is there better way how to test that given file is in EPSG:4326?
    #spatialreference = SpatialReference(wkt=projection)
    #if spatialreference.???() == 4326:
    if projection == None or not projection.endswith('AUTHORITY["EPSG","4326"]]'):
        raise ValueError("DEM data must be in the EPSG:4326 reference system (not in %s)"%projection)

    destextent = Extent(*bbox)

    if not destextent in srcextent:
        raise ValueError("Bounding box must be within the extent of the source data set")

    ## Calculate source window in pixels. Round to an even multiple of 8 since the BLX format requires it
    ## The origin is in the north-west
    srcwin = Extent(int(128 * floor((destextent.west - srcextent.west) / psizex / 128)),
                    int(128 * ceil((destextent.south - srcextent.north) / psizey / 128)),
                    int(128 * ceil((destextent.east - srcextent.west) / psizex / 128)),
                    int(128 * floor((destextent.north - srcextent.north) / psizey / 128)))

    ## Calculate the adjusted destination extent
    destextentmod = Extent(psizex * srcwin.west + srcextent.west,
                           psizey * srcwin.south + srcextent.north,
                           psizex * srcwin.east + srcextent.west,
                           psizey * srcwin.north + srcextent.north)

    # GRR, BLX DRIVER DOESN'T HAVE CREATE() !!!
    # so we have to create temporary file in memmory...
    tempdriver = gdal.GetDriverByName( 'MEM' )
    tmp = tempdriver.Create('', srcwin.width, srcwin.height, eType=gdal.GDT_Int16)
    tmpband = tmp.GetRasterBand(1)

    if srcband.GetNoDataValue():
        tmpband.SetNoDataValue(srcband.GetNoDataValue())

    ## Create destination dataset
    blxdriver = gdal.GetDriverByName('blx')

    if blxdriver == None:
        raise Exception('GDAL library does not have BLX support')

    ## Read raster from read window
    data = srcdataset.ReadRaster(srcwin.west, srcwin.north, srcwin.width, srcwin.height, srcwin.width, srcwin.height)
    
    ## Set transform
    destgeotransform = [destextentmod.west, psizex, geotransform[2],
                       destextentmod.north, geotransform[4], psizey]
    tmp.SetGeoTransform(destgeotransform)

    ## Write raster to destination
    tmp.WriteRaster(0, 0, srcwin.width, srcwin.height, data)

    ## Set up options
    options = ['ZSCALE=%d'%zscale]
    if bigendian:
        options.append('BIGENDIAN=YES')
    
    
    ## Copy data
    dstdataset = blxdriver.CreateCopy(dest, tmp, strict=0, options=options)

if __name__ == "__main__":
    import doctest
    doctest.testmod()
