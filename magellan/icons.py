from struct import unpack, pack
from misc import dump
import itertools
import PIL.Image as Image
from Crypto.Cipher import Blowfish
import mapdir
import random
import numpy

def group(lst, n):
    """group([0,3,4,10,2,3], 2) => iterator
    
    Group an iterable into an n-tuples iterable. Incomplete tuples
    are discarded e.g.
    
    >>> ln)])
    ist(group(range(10), 3))
    [(0, 1, 2), (3, 4, 5), (6, 7, 8)]
    """
    return itertools.izip(*[itertools.islice(lst, i, None, n) for i in range(n)])

#
# bitfield manipulation
#

class bf(object):
    def __init__(self,value=0):
        self._d = value

    def __getitem__(self, index):
        return (self._d >> index) & 1 

    def __setitem__(self,index,value):
        value    = (value&1L)<<index
        mask     = (1L)<<index
        self._d  = (self._d & ~mask) | value

    def __getslice__(self, start, end):
        mask = 2L**(end - start) -1
        return (self._d >> start) & mask

    def __setslice__(self, start, end, value):
        mask = 2L**(end - start) -1
        value = (value & mask) << start
        mask = mask << start
        self._d = (self._d & ~mask) | value
        return (self._d >> start) & mask

    def __int__(self):
        return self._d

    
class IconTable(object):
    def __init__(self, imagedir, filename, bigendian = None):
        if imagedir.bigendian:
            self.endian = '>'
        else:
            self.endian = '<'

        if bigendian != None:
            self.bigendian = bigendian

        self.icons = {}

        self.loadics(imagedir, filename)

    def loadics(self, imagedir, filename):
        """Load ics-file

        >>> it = IconTable(mapdir.MapDirectory("test/layerdata8"), "bmp2bit.ics")
        >>> img = it.icons[0x104].getImage()
        >>> numpy.asarray(img)
        s
        >>> img.save('out.png')
        
#        >>> it.loadics("data/bmp2bit.ics")
        
        
        """
        file = imagedir.open(filename)

        version, n = unpack(self.endian + "32sI", file.read(32+4))

        offsets = {}
        self.imagedata = {}
        for i in range(n):
            id, offset = unpack(self.endian + "iI", file.read(8))
            offsets[id] = offset

        for id, offset in offsets.items():
            file.seek(offset)
            (id2, undef1, imageoffset, maskoffset, undef2, \
            width, height, undef3, bitsperpixel, undef3) = \
            unpack(self.endian + "iiIIiHHbbh", file.read(28))

            
            file.seek(imageoffset)
            data = file.read(width*height*bitsperpixel/8)
            file.seek(maskoffset)
            maskdata = file.read(width*height*bitsperpixel/8)

            self.icons[id] = Icon(id = id2, data = data, maskdata = maskdata,
                                  width = width, height = height,
                                  bitsperpixel = bitsperpixel)

            
#        icontable = [unpack("iI", data) for data in group(file.read(8*n), 8)]
            

        print version, n

    def getIcon(self, id):
        return self.icons[id]
        
    def getSecurityData(self):
        """Get security data

        """
        sd = SecurityData()
        sd.loadFromIconTable(self)

        return sd

    def __repr__(self):
        import rsttable

        rows = [['id', 'width', 'height', 'bpp']] + [[k,v.width, v.height, v.bitsperpixel] for k,v in self.icons.items()]
        
        return rsttable.toRSTtable(rows)
    
class SecurityData(object):
    """
    
    >>> it = IconTable(mapdir.MapDirectory("test/layerdata6"), "bmp4bit.ics")
    >>> # it = IconTable(mapdir.MapDirectory("/nfs/home/henrik/proj/magellan/explorist/omr8_ext/Omr8"), "bmp4bit.ics")
    >>> sdata = SecurityData()
    >>> sdata.loadFromIconTable(it)
    >>> sdata.writeToIconTable(it)
    >>> print sdata


    """
    signature = 0x1e0c076b
    keylen = 24
    def __init__(self):
        self.sdcardserial = ''
        self.serial = ''
        self.serial2 = ''
        self.last = 0
        self.first = 0x1
        self.second = 0x0
        self.third = 0x0
        

    def loadFromIconTable(self, icontable):
        keyicon = icontable.getIcon(0x7ffffff1)
#        print keyicon
        dataicon = icontable.getIcon(0x7ffffff0)
#        print dataicon

        cipher = Blowfish.new(keyicon.data)

        data = cipher.decrypt(dataicon.data)

        print ["0x%x (%c)"%(ord(x),x) for x in data]
        fields = unpack(">IiiI12s20s12sI", data)

        signature = fields[3]
        
        if signature != self.signature:
            raise ValueError("Invalid signature 0x%x"%signature)


        self.first = fields[0]
        self.second = fields[1]
        self.third = fields[2]
        self.sdcardserial = fields[4].split(chr(0))[0]
        self.serial = fields[5].split(chr(0))[0]
        self.serial2 = fields[6].split(chr(0))[0]

        self.last = fields[-1]

        print "serial:", self.serial
        print "sdcardserial:", self.sdcardserial

    def writeToIconTable(self, icontable):
        key = [random.randrange(0,255) for i in range(self.keylen)]

        data = pack("<IiiIIII32sI", self.first, -1, -1, self.signature, 0,0,0, self.serial, self.last)

    def __repr__(self):
        return 'sdcardserial: %s\n'%self.sdcardserial + \
               'serial: %s\n'%self.serial + \
               'serial2: %s\n'%self.serial2 + \
               'first: 0x%x\n'%self.first + \
               'second: 0x%x\n'%self.second + \
               'third: 0x%x\n'%self.third + \
               'last: 0x%x\n'%self.last

class Icon(object):
    def __init__(self, data='', maskdata='', id=None, bitsperpixel=8, width=0, height=1):
        self.id = id
        self.bitsperpixel = bitsperpixel 
        self.width = width
        self.height = height
        self.data = data
        self.maskdata = maskdata

    def getImage(self):
        ## Create pil image
        image = Image.new("P", (self.width, self.height))

        if self.bitsperpixel == 2:
            palette = []
            for i in range(3,-1,-1):
                palette.extend([i*255/3, i*255/3, i*255/3])
        elif self.bitsperpixel == 4:
            palette = []
            for i in range(15,-1,-1):
                palette.extend([i*255/15, i*255/15, i*255/15])
            
        
        
        def imgdataAsArray(data, width, height, bitsperpixel):
            pixels = []
            for x in data:
                b = bf(ord(x))
                for bit in range(8,0,-bitsperpixel):
                    pixels.append(b[bit-bitsperpixel:bit])
            
            img = numpy.array(pixels, dtype=numpy.uint8).reshape((width, height)).T
                
            return img


        img = imgdataAsArray(self.data, self.width, self.height, self.bitsperpixel)
        maskimg = imgdataAsArray(self.maskdata, self.width, self.height, self.bitsperpixel)

#        print img, mas
        image = Image.fromarray(img, 'P')

        image.putpalette(palette)

        return image
        
#            image.putdata(imagedata[id])
#            print dump(imagedata[id])
#            print dump(maskdata)
        
        return image

    def __repr__(self):
        return 'id: 0x%x\n'%id + \
            'bits per pixel: %d\n'%self.bitsperpixel + \
            'width: %d\n'%self.width + \
            'height: %d\n'%self.height
            

if __name__ == "__main__":
    import doctest
    doctest.testmod()

    ## Dump all
    it = IconTable(mapdir.MapDirectory("test/layerdata4"), "bmp4bit.ics")
    
    for id, icon in it.icons.items():
        if id < 10000:
            try:
                icon.getImage().save('icons/icon%x.png'%id)
            except:
                pass

