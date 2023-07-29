#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from setuptools import setup

import sys
sys.path.insert(0, '.')
import versioneer

setup(name='path_helpers',
         version=versioneer.get_version(),
         cmdclass=versioneer.get_cmdclass(),
         description='Helper class and functions for working with file path',
         author='Christian Fobel',
         author_email='christian@fobel.net',
         url='http://github.com/cfobel/path_helpers',
         license='MIT License',
         packages=['path_helpers'],
         classifiers=
         ['Development Status :: 5 - Production/Stable',
          'License :: OSI Approved :: MIT License',
          'Intended Audience :: Developers',
          'Operating System :: OS Independent',
          'Programming Language :: Python',
          'Topic :: Software Development :: Libraries :: Python Modules'])
