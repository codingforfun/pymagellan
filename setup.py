from distutils.core import setup
import glob
import os

setup(name='pymagellan',
      version='0.0',
      description='Python package for reading and writing Magellan GPS maps',
      author='Henrik Johansson',
      author_email='henjo2006@gmail.com',
      url='',
      packages=['magellan', 'osmmagellan'],
      package_data = { 'magellan': ['data/*'] },
      scripts=[os.path.join('magellan', 'scripts', 'imgextract.py'),
               os.path.join('magellan', 'scripts', 'imgcreate.py'),
               os.path.join('magellan', 'scripts', 'mag2ogr.py'),
               os.path.join('osmmagellan', 'osmmag.py')
               ]
     )
