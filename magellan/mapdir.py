import sys
import os
import string
import struct
import tempfile
import shutil

class InvalidImage(Exception):
	pass

def pad16(s):
	"""Pad to 16-bit boundary"""
	if len(s)%2 == 0:
		return s
	else:
		return s + chr(0)

def pad16len(n):
	"""Calculate length of 16-bit padded string with length n"""
	return n + (n % 2)

def copytree(src, dst, symlinks=0):
    names = os.listdir(src)
    for name in names:
        srcname = os.path.join(src, name)
        dstname = os.path.join(dst, name)
        try:
            if symlinks and os.path.islink(srcname):
                linkto = os.readlink(srcname)
                os.symlink(linkto, dstname)
            elif os.path.isdir(srcname):
                copytree(srcname, dstname, symlinks)
            elif name[-1] != '~':
		shutil.copy2(srcname, dstname)
        except (IOError, os.error), why:
            print "Can't copy %s to %s: %s" % (`srcname`, `dstname`, str(why))

class MapDirectory(object):
	""" Reading/writing interface to Magellan map directory

	>>> mapdir = MapDirectory("test/layerdata1")
	>>> inifile = mapdir.open("00map.ini")
	
	
	"""

	def __init__(self, dir=None, mode='r'):
		self.mode = mode
		self.temporary = False
		if dir == None:
			self.dir = tempfile.mkdtemp()
			self.temporary = True
		else:
			if mode == 'w':
				shutil.rmtree(dir)
			self.dir = dir
	def listdir(self, dir=''):
		return os.listdir(os.path.join(self.dir, dir))
	def copyfrom(self, src):
		"""Copy from another MapDirectory object"""
		copytree(src=src.dir, dst=self.dir)

	def open(self, name, mode="r"):
		if not os.path.exists(os.path.join(self.dir, name)):
			for filename in self.listdir():
				if filename.lower() == name.lower():
					name = filename
		return open(os.path.join(self.dir, name), mode)

	def exists(self, name):
		return os.path.exists(os.path.join(self.dir, name))
	def isfile(self, name):
		return os.path.isfile(os.path.join(self.dir, name))
	
	def write(self, dir):
		pass

	def copyfile(self, src, dst=''):
		"""Copy file to MapDirectory"""
		shutil.copy(src, os.path.join(self.dir, dst))
		self.dirty = True
		
	def __del__(self):
		if self.temporary:
			shutil.rmtree(self.dir)
	

class Image(MapDirectory):
	"""Reading/writing interface to Magellan GPS image files (.img/.imi)

	>>> imagefilename = "test/data/test.img"
	>>> image = Image(imagefilename)
	>>> tempdir = tempfile.mkdtemp()
	>>> outfilename = os.path.join(tempdir, "out.img")
	>>> image.write(outfilename)
	>>> refdata = open(imagefilename).read()
	>>> data = open(outfilename).read()
	>>> len(data)
	136796
	>>> data == refdata
	True
	
	"""
	def __init__(self, imagefilename, mode='r', bigendian=None):
		self.mode = mode
		self.filename = imagefilename
		self.dir = tempfile.mkdtemp()
		self.dirty = False
		if bigendian == None:
			if imagefilename[-3:] == "img":
				self.bigendian = True
			elif imagefilename[-3:] in ("imi", "mgi"):
				self.bigendian = False
			else:
				self.bigendian = False
		else:
			self.bigendian = bigendian

		if os.path.exists(imagefilename): 
			if mode in ('r','a'):
				extract_image(imagefilename, self.dir)
	def copyfrom(self, src):
		"""Copy from another MapDirectory object"""
		MapDirectory.copyfrom(self, src)
		self.dirty = True

	def listdir(self, dir=''):
		"""List files in image

		Return a list of files in image

		Example:

		>>> image = Image("test/test.img")
		>>> len(image.listdir())
		90
		
		"""
		return os.listdir(os.path.join(self.dir, dir))
		
	def open(self, name, mode="r"):
		"""Open file in image"""
		if mode == "w":
			self.dirty = True
		return MapDirectory.open(self, name, mode)

	def write(self, filename=None):
		"""Write image to file.

		If filename argument is supplied the image will be
		written to a new file.
		
		"""
		if filename == None:
			filename = self.filename
		write_image(filename, self.dir, self.bigendian)
		self.dirty = False
		
	def __del__(self):
		if self.dirty:
			self.write()
		shutil.rmtree(self.dir)

def extract_image(filename, destdir, endian='<'):
	"""Extract Magellan image file to a directory"""
	
	if filename[-3:] == "img":
		endian = ">"
	elif filename[-3:] in ("imi", "mgi"):
		endian = "<"

	file = open(filename)

	n1,n2 = struct.unpack(endian + "ii", file.read(8))

	if n1 != n2:
		raise InvalidImage

	files = []
	for i in range(n1):
		fname, ext, start, size = struct.unpack(endian + "9s7sii",
							file.read(0x18))
		fname = fname[0:fname.find(chr(0))]
		ext = ext[0:ext.find(chr(0))]

		filename = fname + "." + ext

		files.append((filename, start, size))

	for filename, start, size in files:
		file.seek(start)
		data = file.read(size)

		outfile = open(os.path.join(destdir, filename), "w")
		outfile.write(data)


def write_image(imgfile, source_dir, bigendian=None):
	global checksum, cks_pos
	
	files_list = os.listdir(source_dir)
	
	# Remove file names starting with a dot, as they are hidden.
	files_list = reduce(lambda l, f: l + (f[0] != '.') * [f,], files_list, [])

	if bigendian == None:
		s = " ".join(files_list)
		yals_found = s.find(".yal") >= 0
		lays_found = s.find(".lay") >= 0
	else:
		lays_found = not bigendian
		yals_found = bigendian
		
	if not yals_found and not lays_found:
		raise Exception("Neither .yal nor .lay files found -- can't generate map image.")
	elif yals_found and lays_found:
		raise Exception("Both .yal and .lay files found -- can't generate map image.")
	elif yals_found:
		endian = ">"
		signature = ""
	else:
		endian = "<"
		signature = "MAGELLAN"

	output = open(imgfile, "wb")

	checksum = [0, 0]
	cks_pos = 0
	def update_checksum(s):
		global checksum, cks_pos
		for c in s:
			checksum[cks_pos] ^= ord(c)
			cks_pos = 1 - cks_pos


	n = len(files_list)
	s = struct.pack(endian + "ii", n, n)
	update_checksum(s)	# Must be 0 anyway
	output.write(s)
	start = 8 + n * 24 + (signature != "") * 32

	for file_name in files_list:
		stats = os.stat(os.path.join(source_dir, file_name))
		dot = string.rfind(file_name, ".")
		if dot == -1:
			dot = 8
			ext = ""
		else:
			ext = file_name[dot+1 : dot+4]
		fname = file_name[ : min(dot, 8)]
		s = struct.pack(endian + "9s7sii", fname, ext, start, pad16len(stats.st_size))
		update_checksum(s)
		output.write(s)
		start += pad16len(stats.st_size)

	if signature:
		s = struct.pack("BB30s", checksum[0], checksum[1], signature)
		update_checksum(s)
		output.write(s)

	for file_name in files_list:
		s = open(os.path.join(source_dir, file_name), "rb").read()
		s = pad16(s)
		update_checksum(s)
		output.write(s)

	update_checksum(signature)
	output.write(signature)

	s = (start & 1) * "\0" + chr(checksum[0]) + chr(checksum[1])
	output.write(s)

	output.close()

if __name__ == "__main__":
##	extract_image("test/test.imi", "./apa")
##	img = ImageReader("test/test.imi")
	
	import doctest
	doctest.testmod()
