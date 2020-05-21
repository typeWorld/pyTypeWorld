# Import module
from typeworld.api import *

# Root of Response
root = RootResponse()

### EndpointResponse
endpoint = EndpointResponse()
endpoint.name.en = 'Font Publisher'
endpoint.canonicalURL = 'http://fontpublisher.com/api/'
endpoint.adminEmail = 'admin@fontpublisher.com'
endpoint.supportedCommands = [x['keyword'] for x in COMMANDS] # this API supports all commands

# Attach EndpointResponse to RootResponse
root.endpoint = endpoint

# Print API response as JSON
print(root.dumpJSON())