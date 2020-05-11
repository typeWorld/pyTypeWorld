# -*- coding: utf-8 -*-

import os
import typeworld.api
from ynlib.files import WriteToFile, ReadFromFile

docstrings = []

docstrings.extend(typeworld.api.RootResponse().docu())
docstrings.extend(typeworld.api.EndpointResponse().docu())
docstrings.extend(typeworld.api.InstallableFontsResponse().docu())
docstrings.extend(typeworld.api.InstallFontsResponse().docu())
docstrings.extend(typeworld.api.UninstallFontsResponse().docu())

docstring = ReadFromFile(os.path.join(os.path.dirname(__file__), 'docu.md'))


handles = []
for key in [x[0] for x in docstrings]:
	if not key in handles:
		handles.append(key)

classTOC = ''
for handle in handles:
	classTOC += '- [%s](#user-content-class-%s)<br />\n' % (handle, handle.lower())
classTOC += '\n\n'

docstring = docstring.replace('__classTOC__', classTOC)

for handle in handles:
	for className, string in docstrings:
		if handle == className:
			docstring += string
			docstring += '\n\n'
			break

if not 'TRAVIS' in os.environ:
	WriteToFile(os.path.join(os.path.dirname(__file__), 'README.md'), docstring)