import struct

def dump(x):
    return " ".join(["%02x"%ord(c) for c in x])

def unpack(types, bigendian, data):
    if bigendian:
        prefix=">"
    else:
        prefix="<"
    return struct.unpack(prefix + types,
                         data[0:struct.calcsize(self.endian+types)])

def pack(types, bigendian, *data):
    if bigendian:
        prefix=">"
    else:
        prefix="<"
    return struct.pack(prefix+types, *data)

def cfg_readlist(str):
    """Read ini-file style list
    
    >>> cfg_readlist('3 a bb cc')
    ['a', 'bb', 'cc']

    """
    l = str.split(' ')
    
    n = int(l[0])
    
    if n != len(l[1:]):
        raise ValueError('Incorrect list')
    
    return l[1:]

def cfg_writelist(l):
    """Read ini-file style list
    
    >>> cfg_writelist(['a', 'bb', 'cc'])
    '3 a bb cc'
    >>> cfg_writelist(['a', 1, 'cc'])
    '3 a 1 cc'

    """
    return '%d '%len(l) + ' '.join(map(str,l))
    

if __name__ == "__main__":
    import doctest
    doctest.testmod()
