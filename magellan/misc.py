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


