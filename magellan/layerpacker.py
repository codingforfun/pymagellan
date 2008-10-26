from struct import unpack
from copy import copy

class OutOfData(Exception):
    pass

class Table(object):
    def __init__(self, data, bigendian = False):
        if bigendian:
            prefix = '>'
        else:
            prefix = '<'

        if data:
            self.decode(data, prefix)

    def decode(self, data, prefix):
        self.data = data


        self.headerdata = data[0:0x1c]
        self.decode_header(self.headerdata, prefix)
        data = data[0x1c:]

        table_sizes = (256, self.header[2], self.header[6], self.header[6],
                           self.header[1], self.header[1]-0x100, self.header[4])
        table_datatypes = ('B', 'B', 'I', 'H', 'H', 'H', 'B')
        datatypelen = {'B': 1, 'H': 2, 'I': 4}
        
        tables = []
        for tablesize, type in zip(table_sizes, table_datatypes):
            tables.append(unpack(prefix + '%d%s'%(tablesize, type),
                                 data[0:datatypelen[type] * tablesize]))
            data = data[datatypelen[type] * tablesize:]

        assert len(data) == 0
        
        (self.table1, self.table11c, self.table120, self.table124, self.table128, self.table12c, self.table130) = tables
        
    def decode_header(self, data, prefix):
        self.header = unpack(prefix + '7I', data)

        self.table2len = self.header[1]
        
        assert self.header[0] == 1
        
    def __repr__(self):
        s = []
        s.append('length: %d'%len(self.data))
        s.append('header: (%d) '%len(self.header) + '\n' + str(['0x%x'%x for x in self.header]))
#        s.append('table1: %d'%len(self.table1) + '\n' + str(self.table1))
        return '\n\n'.join(s)
        
class LayerPacker(object):
    def __init__(self, tabledata):
        
        self.table = Table(tabledata)
        
    def unpack(self, data):
        data = map(ord, data)

        out = []

        V10 = 32 - self.table.header[5]
        Vc = 9 - self.table.header[5]
        
        V14 = 34 - self.table.header[6] - self.table.header[5]
        
        dataword = sum([byte << (24-8*i) for i, byte in enumerate(data[0:4])])

        shiftedword = dataword
        data = data[4:]        

        bit = 0
        while True:
            nconsumedbits = Vc

            tmpdata = self.table.table1[shiftedword >> 24]
                
            if tmpdata < 0xfe:
                out.append(self.table.table128[tmpdata])
                nconsumedbits = self.table.table11c[tmpdata]
            else:
                if tmpdata == 0xfe:
                    nconsumedbits = self.table.header[3]

                while shiftedword >= self.table.table120[nconsumedbits]:
                    nconsumedbits += 1
                nconsumedbits -= 1

                tmpdata = shiftedword - self.table.table120[nconsumedbits]

                tmpdata >>= (V10 - nconsumedbits)

                tmpdata += self.table.table124[nconsumedbits]
                
                tmpdata2 = self.table.table128[tmpdata]

                nconsumedbits += self.table.header[5]

                if tmpdata2 <= 0xff:
                    out.append(tmpdata2 & 0xff)
                else:
                    ## end of data
                    if tmpdata2 == 0x100:
                        break
                    else:
                        tmpdata2 -= 0x101
                        di = self.table.table12c[tmpdata2]
                        tmpdata = self.table.table12c[tmpdata2+1]
                        out += self.table.table130[di:tmpdata]

            bit += nconsumedbits
            if bit >= V14:
                if bit > 7:
                    for i in range(bit // 8):
                        dataword <<= 8
                        if len(data) == 0:
                            break
                            raise OutOfData('Input data is incomplete')
                        dataword += data.pop(0)
                    
                    bit -= 8 * (bit >> 3)

            shiftedword = (dataword << bit) & 0xffffffff
            
        return ''.join(map(chr, out))

if __name__ == '__main__':
    print Table(open('hdecode_dreu2.tbl').read())
#    print
#    print Table('others.tbl')
#    print Table('streets.tbl')
#    print Table('rte.tbl')

