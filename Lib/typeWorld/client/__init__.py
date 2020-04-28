# -*- coding: utf-8 -*-

import os, sys, json, platform, urllib.request, urllib.error, urllib.parse, traceback, time, base64, threading, ssl, certifi, logging, inspect
from time import gmtime, strftime

import typeWorld.api
from typeWorld.api import VERSION

from typeWorld.client.helpers import ReadFromFile, WriteToFile, MachineName, addAttributeToURL, OSName, Garbage

WIN = platform.system() == 'Windows'
MAC = platform.system() == 'Darwin'
LINUX = platform.system() == 'Linux'

MOTHERSHIP = 'https://api.type.world/v1'

# Google App Engine stuff
GOOGLE_PROJECT_ID = 'typeworld2'
if '/Contents/Resources' in __file__:
	GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'typeworld2-cfd080814f09.json'))
else:
	GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'typeworld2-cfd080814f09.json'))

if MAC:
	from AppKit import NSUserDefaults
	from typeWorld.client.helpers import nslog

class DummyKeyring(object):
	def __init__(self):
		self.passwords = {}

	def set_password(self, key, username, password):
		self.passwords[(key, username)] = password

	def get_password(self, key, username):
		if (key, username) in self.passwords:
			return self.passwords[(key, username)]

	def delete_password(self, key, username):
		if (key, username) in self.passwords:
			del self.passwords[(key, username)]

dummyKeyRing = DummyKeyring()
if 'TRAVIS' in os.environ:
	import tempfile
	tempFolder = tempfile.mkdtemp()

def urlIsValid(url):

	if not url.find('typeworld://') < url.find('+') < url.find('http') < url.find('//', url.find('http')):
		return False, 'URL is malformed.'

	if url.count('@') > 1:
		return False, 'URL contains more than one @ sign, so don’t know how to parse it.'

	found = False
	for protocol in typeWorld.api.PROTOCOLS:
		if url.startswith(protocol + '://'):
			found = True
			break
	if not found:
		return False, 'Unknown custom protocol, known are: %s' % (typeWorld.api.PROTOCOLS)

	if url.count('://') > 1:
		return False, 'URL contains more than one :// combination, so don’t know how to parse it.'


	return True, None


class URL(object):
	def __init__(self, url):
		self.customProtocol, self.protocol, self.transportProtocol, self.subscriptionID, self.secretKey, self.accessToken, self.restDomain = splitJSONURL(url)

	def unsecretURL(self):

		if self.subscriptionID and self.secretKey:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.subscriptionID) + ':' + 'secretKey' + '@' + str(self.restDomain)

		elif self.subscriptionID:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.subscriptionID) + '@' + str(self.restDomain)

		else:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.restDomain)


	def secretURL(self):

		if self.subscriptionID and self.secretKey:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.subscriptionID) + ':' + str(self.secretKey) + '@' + str(self.restDomain)

		elif self.subscriptionID:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.subscriptionID) + '@' + str(self.restDomain)

		else:
			return str(self.customProtocol) + str(self.protocol) + '+' + str(self.transportProtocol.replace('://', '//')) + str(self.restDomain)

def getProtocol(url):

	protocol = URL(url).protocol

	for ext in ('.py', '.pyc'):
		if os.path.exists(os.path.join(os.path.dirname(__file__), 'protocols', protocol + ext)):

			import importlib
			spec = importlib.util.spec_from_file_location('json', os.path.join(os.path.dirname(__file__), 'protocols', protocol + ext))
			module = importlib.util.module_from_spec(spec)
			spec.loader.exec_module(module)
			
			protocolObject = module.TypeWorldProtocol(url)

			return True, protocolObject

	return False, 'Protocol %s doesn’t exist in this app (yet).' % protocol


def performRequest(url, parameters, sslcontext = None):
	'''Perform request in a loop 10 times, because the central server’s instance might shut down unexpectedly during a request, especially longer running ones.'''


	if not sslcontext:
		sslcontext = ssl.create_default_context(cafile=certifi.where())

	success = False
	message = None
	data = urllib.parse.urlencode(parameters).encode('ascii')

	for i in range(10):
		try:
			response = urllib.request.urlopen(url, data, context=sslcontext)
			return True, response
		except:
			message = f'Response from {url} with parameters {parameters} after {i+1} tries: ' + traceback.format_exc().splitlines()[-1]

	return success, message


def splitJSONURL(url):

	customProtocol = 'typeworld://'
	url = url.replace(customProtocol, '')

	protocol = url.split('+')[0]
	url = url.replace(protocol + '+', '')

	url = url.replace('http//', 'http://')
	url = url.replace('https//', 'https://')
	url = url.replace('HTTP//', 'http://')
	url = url.replace('HTTPS//', 'https://')


	transportProtocol = None
	if url.startswith('https://'):
		transportProtocol = 'https://'
	elif url.startswith('http://'):
		transportProtocol = 'http://'

	urlRest = url[len(transportProtocol):]

	subscriptionID = ''
	secretKey = ''
	accessToken = ''

	# With credentials
	if '@' in urlRest:

		credentials, domain = urlRest.split('@')
		credentialParts = credentials.split(':')

		if len(credentialParts) == 3:
			subscriptionID, secretKey, accessToken = credentialParts

		elif len(credentialParts) == 2:
			subscriptionID, secretKey = credentialParts

		elif len(credentialParts) == 1:
			subscriptionID = credentialParts[0]

	# No credentials given
	else:
		domain = urlRest

	return customProtocol, protocol, transportProtocol, subscriptionID, secretKey, accessToken, domain

class Preferences(object):
	def __init__(self):
		self._dict = {}

	def get(self, key):
		if key in self._dict:
			return self._dict[key]

	def set(self, key, value):
		self._dict[key] = value
		self.save()

	def remove(self, key):
		if key in self._dict:
			del self._dict[key]

	def save(self): pass

	def dictionary(self):
		return self._dict

class JSON(Preferences):
	def __init__(self, path):
		self.path = path
		self._dict = {}

		if self.path and os.path.exists(self.path):
			self._dict = json.loads(ReadFromFile(self.path))

	def save(self):

		if not os.path.exists(os.path.dirname(self.path)): os.makedirs(os.path.dirname(self.path))
		WriteToFile(self.path, json.dumps(self._dict))

	def dictionary(self):
		return self._dict



class AppKitNSUserDefaults(Preferences):
	def __init__(self, name):
#		NSUserDefaults = objc.lookUpClass('NSUserDefaults')
		self.defaults = NSUserDefaults.alloc().initWithSuiteName_(name)
		self.values = {}


	def get(self, key):
		
		if key in self.values:
			return self.values[key]

		else:

			o = self.defaults.objectForKey_(key)

			if o:


				# print('TYPE of', key, ':', o.__class__.__name__)

				if 'Array' in o.__class__.__name__:
					o = list(o)

				elif 'Dictionary' in o.__class__.__name__:
					o = dict(o)
					# print('Converting TYPE of', key, ' to dict()')
					# o['_xzy'] = 'a'
					# del o['_xzy']

				elif 'unicode' in o.__class__.__name__:
					o = str(o)


				self.values[key] = o
				return self.values[key]

	def set(self, key, value):

#		self.defaults.setObject_forKey_(json.dumps(value), key)
		
		# if MAC:
		# 	print(type(value))
		# 	if type(value) == dict:
		# 		value = NSDictionary.alloc().initWithDictionary_(value)

		self.values[key] = value
		self.defaults.setObject_forKey_(value, key)

	def remove(self, key):
		if key in self.values:
			del self.values[key]

		if self.defaults.objectForKey_(key):
			self.defaults.removeObjectForKey_(key)

	def convertItem(self, item):

		if 'Array' in item.__class__.__name__ or type(item) in (list, tuple):
			_list = list(item)
			for i, _item in enumerate(_list):
				_list[i] = self.convertItem(_item)
			return _list

		elif 'Dictionary' in item.__class__.__name__ or type(item) == dict:
			d = dict(item)
			for k, v in d.items():
				d[k] = self.convertItem(v)

			return d

		elif 'unicode' in item.__class__.__name__:
			return str(item)


	def convertDict(self, d):

		d = dict(d)

		for k, v in d.items():        
			if 'Array' in v.__class__.__name__:
				_list = list(v)
				for _item in _list:
					d[k] = list(v)

			elif 'Dictionary' in v.__class__.__name__:
				d[k] = self.convertDict(v)

			elif 'unicode' in v.__class__.__name__:
				d[k] = str(v)

		return d


	def dictionary(self):

		d = self.defaults.dictionaryRepresentation()
		return self.convertItem(d)



class TypeWorldClientDelegate(object):

	def __init__(self):
		self.client = None

	def _fontWillInstall(self, font):
		try:
			self.fontWillInstall(font)
		except:
			self.client.log(traceback.format_exc())
	def fontWillInstall(self, font):
		assert type(font) == typeWorld.api.Font


	def _fontHasInstalled(self, success, message, font):
		try:
			self.fontHasInstalled(success, message, font)
		except:
			self.client.log(traceback.format_exc())
	def fontHasInstalled(self, success, message, font):
		assert type(font) == typeWorld.api.Font


	def _fontWillUninstall(self, font):
		try:
			self.fontWillUninstall(font)
		except:
			self.client.log(traceback.format_exc())
	def fontWillUninstall(self, font):
		assert type(font) == typeWorld.api.Font


	def _fontHasUninstalled(self, success, message, font):
		try:
			self.fontHasUninstalled(success, message, font)
		except:
			self.client.log(traceback.format_exc())
	def fontHasUninstalled(self, success, message, font):
		assert type(font) == typeWorld.api.Font


	def _subscriptionUpdateNotificationHasBeenReceived(self, subscription):
		try:
			self.subscriptionUpdateNotificationHasBeenReceived(subscription)
		except:
			self.client.log(traceback.format_exc())
	def subscriptionUpdateNotificationHasBeenReceived(self, subscription):
		assert type(subscription) == typeWorld.client.APISubscription
		subscription.update()


	def _userAccountUpdateNotificationHasBeenReceived(self):
		try:
			self.userAccountUpdateNotificationHasBeenReceived()
		except:
			self.client.log(traceback.format_exc())
	def userAccountUpdateNotificationHasBeenReceived(self):
		pass


	def _subscriptionWasDeleted(self, subscription):
		try:
			self.subscriptionWasDeleted(subscription)
		except:
			self.client.log(traceback.format_exc())
	def subscriptionWasDeleted(self, subscription):
		pass


	def _publisherWasDeleted(self, publisher):
		try:
			self.publisherWasDeleted(publisher)
		except:
			self.client.log(traceback.format_exc())
	def publisherWasDeleted(self, publisher):
		pass

	def _subscriptionWasAdded(self, subscription):
		try:
			self.subscriptionWasAdded(subscription)
		except:
			self.client.log(traceback.format_exc())
	def subscriptionWasAdded(self, subscription):
		pass

	def _subscriptionWasUpdated(self, subscription):
		try:
			self.subscriptionWasUpdated(subscription)
		except:
			self.client.log(traceback.format_exc())
	def subscriptionWasUpdated(self, subscription):
		pass

class APIInvitation(object):
	keywords = ()

	def __init__(self, d):
		for key in self.keywords:
			# if key in d:
			setattr(self, key, d[key])
			# else:
			# 	setattr(self, key, None)

class APIPendingInvitation(APIInvitation):
	keywords = ('url', 'ID', 'invitedByUserName', 'invitedByUserEmail', 'time', 'canonicalURL', 'publisherName', 'subscriptionName', 'logoURL', 'backgroundColor', 'fonts', 'families', 'foundries', 'website')

	def accept(self):
		return self.parent.acceptInvitation(self.ID)

	def decline(self):
		return self.parent.declineInvitation(self.ID)

class APIAcceptedInvitation(APIInvitation):
	keywords = ('url', 'ID', 'invitedByUserName', 'invitedByUserEmail', 'time', 'canonicalURL', 'publisherName', 'subscriptionName', 'logoURL', 'backgroundColor', 'fonts', 'families', 'foundries', 'website')

class APISentInvitation(APIInvitation):
	keywords = ('url', 'invitedUserName', 'invitedUserEmail', 'invitedTime', 'acceptedTime', 'confirmed')


class PubSubClient(object):

	def executeCondition(self):
		return self.pubSubExecuteConditionMethod == None or callable(self.pubSubExecuteConditionMethod) and self.pubSubExecuteConditionMethod()

	def pubSubSetup(self, direct = False):


		from google.cloud import pubsub_v1

		if self.__class__ == APIClient:
			client = self
		else:
			client = self.parent.parent

		if client.pubSubSubscriptions:
			print('Pub/Sub subscription setup for %s' % self)

			if not self.pubsubSubscription:

				self.pubSubSubscriber = pubsub_v1.SubscriberClient.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH)
				self.pubSubSubscriptionID = '%s-appInstance-%s' % (self.pubSubTopicID, client.anonymousAppID())
				self.topicPath = self.pubSubSubscriber.topic_path(GOOGLE_PROJECT_ID, self.pubSubTopicID)
				self.subscriptionPath = self.pubSubSubscriber.subscription_path(GOOGLE_PROJECT_ID, self.pubSubSubscriptionID)

				if self.executeCondition():
					if client.mode == 'gui' or direct:
						stillAliveThread = threading.Thread(target=self.pubSubSetup_worker)
						stillAliveThread.start()
					elif client.mode == 'headless':
						self.pubSubSetup_worker()


	def pubSubSetup_worker(self):

		import google.api_core

		if self.executeCondition():

			try:
				self.pubSubSubscriber.create_subscription(name=self.subscriptionPath, topic=self.topicPath)
				self.pubsubSubscription = self.pubSubSubscriber.subscribe(self.subscriptionPath, self.pubSubCallback)
				self.pubSubCallback(None)
			except google.api_core.exceptions.NotFound:
#				print('NotFound for %s' % self)
				pass
			# except google.api_core.exceptions.DeadlineExceeded:
			# 	print('DeadlineExceeded for %s' % self)
			except google.api_core.exceptions.AlreadyExists:
				self.pubsubSubscription = self.pubSubSubscriber.subscribe(self.subscriptionPath, self.pubSubCallback)

			if self.pubsubSubscription:
#				print('Pub/Sub subscription SUCCESSFUL for %s' % self)
				pass

	def pubSubDelete(self):

		if self.__class__ == APIClient:
			client = self
		else:
			client = self.parent.parent

		if client.pubSubSubscriptions:
			if self.executeCondition():

				if client.mode == 'gui': threading.Thread(target=self.pubSubDelete_worker).start()
				elif client.mode == 'headless': self.pubSubDelete_worker()

	def pubSubDelete_worker(self):

		import google.api_core

		# if not self.pubSubSubscriber:
		# 	self.pubSubSubscriber = pubsub_v1.SubscriberClient.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS_JSON_PATH)

		try:
			self.pubSubSubscriber.delete_subscription(self.subscriptionPath)
		except google.api_core.exceptions.NotFound:
			pass

	# def pubSubCallback(self, message):
	# 	'''Overwrite this one'''
	# 	raise NotImplementedError


class APIClient(PubSubClient):
	"""\
	Main Type.World client app object. Use it to load repositories and install/uninstall fonts.
	"""

	def __init__(self, preferences = None, secretTypeWorldAPIKey = None, delegate = None, mothership = MOTHERSHIP, mode = 'headless', pubSubSubscriptions = False, online = True):

		try:
			self._preferences = preferences or Preferences()
			# if self:
			# 	self.clearPendingOnlineCommands()
			self._publishers = {}
			self._subscriptionsUpdated = []
			self.onlineCommandsQueue = []
			self._syncProblems = []
			self.secretTypeWorldAPIKey = secretTypeWorldAPIKey
			self.delegate = delegate or TypeWorldClientDelegate()
			self.delegate.client = self
			self.mothership = mothership
			self.mode = mode # gui or headless
			self.pubSubSubscriptions = pubSubSubscriptions
			self._isSetOnline = online

			if self._isSetOnline:
				self.sslcontext = ssl.create_default_context(cafile=certifi.where())

			# For Unit Testing
			self.testScenario = None

			self._systemLocale = None
			self._online = {}

			# Pub/Sub
			if self.pubSubSubscriptions:

				# In App
				self.pubsubSubscription = None
				self.pubSubTopicID = 'user-%s' % self.user()
				self.pubSubExecuteConditionMethod = self.user
				self.pubSubSetup()

			erg

		except:
			self.handleTraceback(submit = False, sourceMethod = getattr(self, sys._getframe().f_code.co_name))


	def pubSubCallback(self, message):
		try:
			self.delegate._userAccountUpdateNotificationHasBeenReceived()

			if message:
				message.ack()
				self.set('lastPubSubMessage', int(time.time()))

		except:
			self.handleTraceback()


	# def clearPendingOnlineCommands(self):
	# 	commands = self.get('pendingOnlineCommands') or {}
	# 	commands['acceptInvitation'] = []
	# 	commands['declineInvitation'] = []
	# 	commands['downloadSubscriptions'] = []
	# 	commands['linkUser'] = []
	# 	commands['syncSubscriptions'] = []
	# 	commands['unlinkUser'] = []
	# 	commands['uploadSubscriptions'] = []
	# 	self.set('pendingOnlineCommands', commands)

	def get(self, key):
		try:
			return self._preferences.get('world.type.guiapp.' + key) or self._preferences.get(key)
		except:
			self.parent.parent.handleTraceback()

	def set(self, key, value):
		try:
			self._preferences.set('world.type.guiapp.' + key, value)
		except:
			self.parent.parent.handleTraceback()

	def remove(self, key):
		try:
			self._preferences.remove('world.type.guiapp.' + key)
			self._preferences.remove(key)
		except:
			self.parent.parent.handleTraceback()


	def performRequest(self, url, parameters):

		try:
			parameters['clientVersion'] = VERSION
			if self.testScenario == 'simulateFaultyClientVersion':
				parameters['clientVersion'] = 'abc'
			elif self.testScenario == 'simulateNoClientVersion':
				del parameters['clientVersion']

			if self._isSetOnline:
				if self.testScenario:
					parameters['testScenario'] = self.testScenario
				if self.testScenario == 'simulateCentralServerNotReachable':
					url = 'https://api.type.worlddd/api'
				return performRequest(url, parameters, self.sslcontext)
			else:
				return False, 'APIClient is set to work offline as set by: APIClient(online=False)'

		except:
			self.handleTraceback()

	def pendingInvitations(self):
		try:
			_list = []
			if self.get('pendingInvitations'):
				for invitation in self.get('pendingInvitations'):
					invitation = APIPendingInvitation(invitation)
					invitation.parent = self
					_list.append(invitation)
			return _list
		except:
			self.handleTraceback()

	def acceptedInvitations(self):
		try:
			_list = []
			if self.get('acceptedInvitations'):
				for invitation in self.get('acceptedInvitations'):
					invitation = APIAcceptedInvitation(invitation)
					invitation.parent = self
					_list.append(invitation)
			return _list
		except:
			self.handleTraceback()

	def sentInvitations(self):
		try:
			_list = []
			if self.get('sentInvitations'):
				for invitation in self.get('sentInvitations'):
					invitation = APISentInvitation(invitation)
					invitation.parent = self
					_list.append(invitation)
			return _list
		except:
			self.handleTraceback()

	def secretSubscriptionURLs(self):
		try:

			_list = []

			for publisher in self.publishers():
				for subscription in publisher.subscriptions():
					_list.append(subscription.protocol.secretURL())

			return _list

		except:
			self.handleTraceback()

	def unsecretSubscriptionURLs(self):
		try:
			_list = []

			for publisher in self.publishers():
				for subscription in publisher.subscriptions():
					_list.append(subscription.protocol.unsecretURL())

			return _list
		except:
			self.handleTraceback()

	def timezone(self):
		try:
			return strftime("%z", gmtime())
		except:
			self.handleTraceback()

	def syncProblems(self):
		return self._syncProblems

	def addMachineIDToParameters(self, parameters):
		try:
			machineModelIdentifier, machineHumanReadableName, machineSpecsDescription = MachineName()

			if machineModelIdentifier:
				parameters['machineModelIdentifier'] = machineModelIdentifier

			if machineHumanReadableName:
				parameters['machineHumanReadableName'] = machineHumanReadableName

			if machineSpecsDescription:
				parameters['machineSpecsDescription'] = machineSpecsDescription

			import platform
			parameters['machineNodeName'] = platform.node()

			osName = OSName()
			if osName:
				parameters['machineOSVersion'] = osName


			return parameters

		except:
			self.handleTraceback()


	def online(self, server = None):
		try:

			if self.testScenario == 'simulateNotOnline':
				return False

			if 'GAE_DEPLOYMENT_ID' in os.environ:
				return True


			if not server:
				server = 'type.world'

			import urllib.request
			try:
				host='http://' + server
				urllib.request.urlopen(host) #Python 3.x
				return True
			except:
				return False		
		except:
			self.handleTraceback()



	def appendCommands(self, commandName, commandsList = ['pending']):
		try:

			# Set up data structure
			commands = self.get('pendingOnlineCommands')
			if not self.get('pendingOnlineCommands'):
				commands = {}
			# Init empty
			if not commandName in commands: 
				commands[commandName] = []
			if commandName in commands and len(commands[commandName]) == 0: # set anyway if empty because NSObject immutability
				commands[commandName] = []
			self.set('pendingOnlineCommands', commands)

			# Add commands to list
			commands = self.get('pendingOnlineCommands')
			if type(commandsList) in (str, int):
				commandsList = [commandsList]
			for commandListItem in commandsList:
				if not commandListItem in commands[commandName]:
					commands[commandName] = list(commands[commandName])
					commands[commandName].append(commandListItem)
			self.set('pendingOnlineCommands', commands)

		except:
			self.handleTraceback()

	def performCommands(self):
		try:

			success, message = True, None
			self._syncProblems = []

			if self.online():

				commands = self.get('pendingOnlineCommands') or {}

				if 'unlinkUser' in commands and commands['unlinkUser']:
					success, message = self.performUnlinkUser()

					if success:
						commands['unlinkUser'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('unlinkUser finished successfully')

					else:
						self.log('unlinkUser failure:', message)
						self._syncProblems.append(message)


				if 'linkUser' in commands and commands['linkUser']:
					success, message = self.performLinkUser(commands['linkUser'][0])

					if success:
						commands['linkUser'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('linkUser finished successfully')

					else:
						self.log('linkUser failure:', message)
						self._syncProblems.append(message)

				if 'syncSubscriptions' in commands and commands['syncSubscriptions']:
					success, message = self.performSyncSubscriptions(commands['syncSubscriptions'])

					if success:
						commands['syncSubscriptions'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('syncSubscriptions finished successfully')

					else:
						self.log('syncSubscriptions failure:', message)
						self._syncProblems.append(message)


				if 'uploadSubscriptions' in commands and commands['uploadSubscriptions']:
					success, message = self.perfomUploadSubscriptions(commands['uploadSubscriptions'])

					if success:
						commands['uploadSubscriptions'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('uploadSubscriptions finished successfully')

					else:
						self.log('uploadSubscriptions failure:', message)
						self._syncProblems.append(message)

				if 'acceptInvitation' in commands and commands['acceptInvitation']:
					success, message = self.performAcceptInvitation(commands['acceptInvitation'])

					if success:
						commands['acceptInvitation'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('acceptInvitation finished successfully')

					else:
						self.log('acceptInvitation failure:', message)
						self._syncProblems.append(message)

				if 'declineInvitation' in commands and commands['declineInvitation']:
					success, message = self.performDeclineInvitation(commands['declineInvitation'])

					if success:
						commands['declineInvitation'] = []
						self.set('pendingOnlineCommands', commands)
						self.log('declineInvitation finished successfully')

					else:
						self.log('declineInvitation failure:', message)
						self._syncProblems.append(message)

				if 'downloadSubscriptions' in commands and commands['downloadSubscriptions']:
					success, message = self.performDownloadSubscriptions()

					if success:
						commands['downloadSubscriptions'] = []
						self.set('pendingOnlineCommands', commands)
	#					self.log('downloadSubscriptions finished successfully')

					else:
						self.log('downloadSubscriptions failure:', message)
						self._syncProblems.append(message)

				if self._syncProblems:
					return False, self._syncProblems[0]
				else:
					return True, None

			else:

				self._syncProblems.append('#(response.notOnline)')
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)']

		except:
			self.handleTraceback()

	def uploadSubscriptions(self, performCommands = True):
		try:

			self.appendCommands('uploadSubscriptions', self.secretSubscriptionURLs() or ['empty'])
			self.appendCommands('downloadSubscriptions')

			success, message = True, None
			if performCommands:
				success, message = self.performCommands()
			return success, message

		except:
			self.handleTraceback()

	def perfomUploadSubscriptions(self, oldURLs):

		try:

			userID = self.user()

			if userID:

				self.set('lastServerSync', int(time.time()))

				self.log('Uploading subscriptions: %s' % oldURLs)

				parameters = {
					'command': 'uploadUserSubscriptions',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'subscriptionURLs': ','.join(oldURLs),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			# Success
			return True, None
		except:
			self.handleTraceback()

	def downloadSubscriptions(self, performCommands = True):

		try:
			if self.user():
				self.appendCommands('downloadSubscriptions')

				if performCommands: return self.performCommands()
				else: return True, None
			else:
				return True, None

		except:
			self.handleTraceback()

	def performDownloadSubscriptions(self):
		try:
			userID = self.user()

			if userID:

				self.set('lastServerSync', int(time.time()))

				parameters = {
					'command': 'downloadUserSubscriptions',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'userTimezone': self.timezone(),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				return self.executeDownloadSubscriptions(response)

			return True, None
		except:
			self.handleTraceback()


	def executeDownloadSubscriptions(self, response):
		try:
			oldURLs = self.secretSubscriptionURLs()

			# print('executeDownloadSubscriptions():', response)

			# Uninstall all protected fonts when app instance is reported as revoked
			if response['appInstanceIsRevoked']:
				success, message = self.uninstallAllProtectedFonts()
				if not success:
					return False, message

			# Add new subscriptions
			for url in response['subscriptions']:
				if not url in oldURLs:
					success, message, publisher, subscription = self.addSubscription(url, updateSubscriptionsOnServer = False)

					if success: self.delegate._subscriptionWasAdded(subscription)

					if not success: return False, 'Received from self.addSubscription() for %s: %s' % (url, message)

			def replace_item(obj, key, replace_value):
				for k, v in obj.items():
					if v == key:
						obj[k] = replace_value
				return obj

			# Invitations
			self.set('acceptedInvitations', [replace_item(x, None, '') for x in response['acceptedInvitations']])
			self.set('pendingInvitations', [replace_item(x, None, '') for x in response['pendingInvitations']])
			self.set('sentInvitations', [replace_item(x, None, '') for x in response['sentInvitations']])

			# import threading
			# preloadThread = threading.Thread(target=self.preloadLogos)
			# preloadThread.start()

			# Delete subscriptions
			for publisher in self.publishers():
				for subscription in publisher.subscriptions():
					if not subscription.protocol.secretURL() in response['subscriptions']:
						subscription.delete(updateSubscriptionsOnServer = False)

			# Success

			self.pubSubSetup(direct = True)

			return True, None
		except:
			self.handleTraceback()

	def acceptInvitation(self, ID):
		try:
			userID = self.user()
			if userID:
				self.appendCommands('acceptInvitation', [ID])

			return self.performCommands()
		except:
			self.handleTraceback()


	def performAcceptInvitation(self, IDs):
		try:
			userID = self.user()
	#		oldURLs = self.secretSubscriptionURLs()

			if userID:

				self.set('lastServerSync', int(time.time()))

				parameters = {
					'command': 'acceptInvitations',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'subscriptionIDs': ','.join([str(x) for x in IDs]),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				# Success
				return self.executeDownloadSubscriptions(response)
		except:
			self.handleTraceback()


	def declineInvitation(self, ID):
		try:

			userID = self.user()
			if userID:
				self.appendCommands('declineInvitation', [ID])

			return self.performCommands()

		except:
			self.handleTraceback()

	def performDeclineInvitation(self, IDs):
		try:
			userID = self.user()
	#		oldURLs = self.secretSubscriptionURLs()

			if userID:

				self.set('lastServerSync', int(time.time()))

				parameters = {
					'command': 'declineInvitations',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'subscriptionIDs': ','.join([str(x) for x in IDs]),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				# Success
				return self.executeDownloadSubscriptions(response)
		except:
			self.handleTraceback()


	def syncSubscriptions(self, performCommands = True):
		try:
			self.appendCommands('syncSubscriptions', self.secretSubscriptionURLs() or ['empty'])

			if performCommands:
				return self.performCommands()
			else:
				return True, None
		except:
			self.handleTraceback()

	def performSyncSubscriptions(self, oldURLs):
		try:
			userID = self.user()

			# print('performSyncSubscriptions: %s' % userID)

			if userID:

				self.set('lastServerSync', int(time.time()))

				parameters = {
					'command': 'syncUserSubscriptions',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'subscriptionURLs': ','.join(oldURLs),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				# Add new subscriptions
				for url in response['subscriptions']:
					if not url in oldURLs:
						success, message, publisher, subscription = self.addSubscription(url, updateSubscriptionsOnServer = False)

						if not success: return False, message

				# Success
				return True, len(response['subscriptions']) - len(oldURLs)

			return True, None

		except:
			self.handleTraceback()


	def user(self):
		try:
			return self.get('typeWorldUserAccount') or ''
		except:
			self.handleTraceback()

	def userKeychainKey(self, ID):
		try:
			return 'https://%s@%s.type.world' % (ID, self.anonymousAppID())
		except:
			self.handleTraceback()

	def secretKey(self, userID = None):
		try:
			keyring = self.keyring()
			if keyring:
				return keyring.get_password(self.userKeychainKey(userID or self.user()), 'secretKey')
		except:
			self.handleTraceback()

	def userName(self):
		try:
			keyring = self.keyring()
			if keyring:
				return keyring.get_password(self.userKeychainKey(self.user()), 'userName')
		except:
			self.handleTraceback()

	def userEmail(self):
		try:
			keyring = self.keyring()
			if keyring:
				return keyring.get_password(self.userKeychainKey(self.user()), 'userEmail')

		except:
			self.handleTraceback()

	def createUserAccount(self, name, email, password1, password2):
		try:
			if self.online():

				if not name or not email or not password1 or not password2:
					return False, '#(RequiredFieldEmpty)'

				if password1 != password2:
					return False, '#(PasswordsDontMatch)'

				parameters = {
					'command': 'createUserAccount',
					'name': name,
					'email': email,
					'password': password1,
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				# success
				return self.linkUser(response['anonymousUserID'], response['secretKey'])

			else:
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)']

		except:
			self.handleTraceback()


	def deleteUserAccount(self, email, password):
		try:

			if self.online():

				# Required parameters
				if not email or not password:
					return False, '#(RequiredFieldEmpty)'

				# Unlink user first
				if self.userEmail() == email:
					success, message = self.performUnlinkUser()
					if not success:
						return False, message

				parameters = {
					'command': 'deleteUserAccount',
					'email': email,
					'password': password,
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

				# success

				return True, None

			else:
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)']
		except:
			self.handleTraceback()

	def logInUserAccount(self, email, password):
		try:
			if not email or not password:
				return False, '#(RequiredFieldEmpty)'

			parameters = {
				'command': 'logInUserAccount',
				'email': email,
				'password': password,
			}

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())

			if response['response'] != 'success':
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			# success
			return self.linkUser(response['anonymousUserID'], response['secretKey'])
		except:
			self.handleTraceback()

	def linkUser(self, userID, secretKey):
		try:
			# Set secret key now, so it doesn't show up in preferences when offline
			keyring = self.keyring()
			if keyring:
				keyring.set_password(self.userKeychainKey(userID), 'secretKey', secretKey)
				assert self.secretKey(userID) == secretKey

			self.appendCommands('linkUser', userID)
			self.syncSubscriptions(performCommands = False)
			self.downloadSubscriptions(performCommands = False)

			return self.performCommands()
		except:
			self.handleTraceback()


	def performLinkUser(self, userID):
		try:

			parameters = {
				'command': 'linkTypeWorldUserAccount',
				'anonymousAppID': self.anonymousAppID(),
				'anonymousUserID': userID,
				'secretKey': self.secretKey(userID),
			}

			parameters = self.addMachineIDToParameters(parameters)

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())


			if response['response'] != 'success':
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			# Success
			self.set('typeWorldUserAccount', userID)
			assert userID == self.user()

			# Pub/Sub
			self.pubSubTopicID = 'user-%s' % self.user()
			self.pubSubSetup()

			keyring = self.keyring()
			if keyring:
				if 'userEmail' in response:
					keyring.set_password(self.userKeychainKey(userID), 'userEmail', response['userEmail'])
				if 'userName' in response:
					keyring.set_password(self.userKeychainKey(userID), 'userName', response['userName'])

			return True, None

		except:
			self.handleTraceback()


	def linkedAppInstances(self):
		try:
			if not self.user():
				return False, 'No user'

			parameters = {
				'command': 'userAppInstances',
				'anonymousAppID': self.anonymousAppID(),
				'anonymousUserID': self.user(),
				'secretKey': self.secretKey(),
			}

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())

			if response['response'] != 'success':
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]


			class AppInstance(object):
				pass


			# Success
			instances = []

			for serverInstance in response['appInstances']:

				instance = AppInstance()

				for key in serverInstance:
					setattr(instance, key, serverInstance[key])

				instances.append(instance)

			return True, instances
		except:
			self.handleTraceback()


	def revokeAppInstance(self, anonymousAppID):
		try:
			if not self.user():
				return False, 'No user'

			parameters = {
				'command': 'revokeAppInstance',
				'anonymousAppID': anonymousAppID,
				'anonymousUserID': self.user(),
				'secretKey': self.secretKey(),
			}

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())

			if response['response'] != 'success':
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			return True, None
		except:
			self.handleTraceback()


	def reactivateAppInstance(self, anonymousAppID):
		try:

			if not self.user():
				return False, 'No user'

			parameters = {
				'command': 'reactivateAppInstance',
				'anonymousAppID': anonymousAppID,
				'anonymousUserID': self.user(),
				'secretKey': self.secretKey(),
			}

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())

			if response['response'] != 'success':
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			return True, None
		except:
			self.handleTraceback()


	def unlinkUser(self):
		try:
			self.appendCommands('unlinkUser')
			return self.performCommands()
		except:
			self.handleTraceback()


	def uninstallAllProtectedFonts(self, dryRun = False):
		try:
			# Uninstall all protected fonts
			for publisher in self.publishers():
				for subscription in publisher.subscriptions():

					success, installabeFontsCommand = subscription.protocol.installableFontsCommand()
					if not success:
						return False, 'No installabeFontsCommand'

					fontIDs = []

					for foundry in installabeFontsCommand.foundries:
						for family in foundry.families:
							for font in family.fonts:

								# Dry run from central server: add all fonts to list
								if dryRun and font.protected:
									fontIDs.append(font.uniqueID)

								# Run from local client, add only actually installed fonts
								elif not dryRun and font.protected and subscription.installedFontVersion(font.uniqueID):
									fontIDs.append(font.uniqueID)
					
					if fontIDs:
						success, message = subscription.removeFonts(fontIDs, dryRun = dryRun, updateSubscription = False)
						if not success:
							return False, message

			return True, None
		except:
			self.handleTraceback()


	def performUnlinkUser(self):
		try:
			userID = self.user()

			success, response = self.uninstallAllProtectedFonts()
			if not success:
				return False, response

			parameters = {
				'command': 'unlinkTypeWorldUserAccount',
				'anonymousAppID': self.anonymousAppID(),
				'anonymousUserID': userID,
				'secretKey': self.secretKey(),
			}

			success, response = self.performRequest(self.mothership, parameters)
			if not success:
				return False, response

			response = json.loads(response.read().decode())

			continueFor = ['userUnknown']
			if response['response'] != 'success' and not response['response'] in continueFor:
				return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			self.set('typeWorldUserAccount', '')
			self.remove('acceptedInvitations')
			self.remove('pendingInvitations')
			self.remove('sentInvitations')

			# Success
			self.pubSubTopicID = 'user-%s' % self.user()
			self.pubSubDelete()

			keyring = self.keyring()
			keyring.delete_password(self.userKeychainKey(userID), 'secretKey')
			keyring.delete_password(self.userKeychainKey(userID), 'userEmail')
			keyring.delete_password(self.userKeychainKey(userID), 'userName')


			# Success
			return True, None

		except:
			self.handleTraceback()


	def systemLocale(self):
		try:

			if not self._systemLocale:
				if MAC:
					from AppKit import NSLocale
					self._systemLocale = str(NSLocale.preferredLanguages()[0].split('_')[0].split('-')[0])
				else:
					import locale
					self._systemLocale = locale.getdefaultlocale()[0].split('_')[0]

			return self._systemLocale
		except:
			self.handleTraceback()

	def locale(self):
		try:

			'''\
			Reads user locale from OS
			'''

			if self.get('localizationType') == 'systemLocale':
				_locale = [self.systemLocale()]
			elif self.get('localizationType') == 'customLocale':
				_locale = [self.get('customLocaleChoice') or 'en']
			else:
				_locale = [self.systemLocale()]

			if not 'en' in _locale:
				_locale.append('en')

			return _locale
		except:
			self.handleTraceback()

	def expiringInstalledFonts(self):
		try:
			fonts = []
			for publisher in self.publishers():
				for subscription in publisher.subscriptions():
					fonts.extend(subscription.expiringInstalledFonts())
			return fonts
		except:
			self.handleTraceback()

	def amountOutdatedFonts(self):
		try:
			amount = 0
			for publisher in self.publishers():
				amount += publisher.amountOutdatedFonts()
			return amount
		except:
			self.handleTraceback()


	def keyring(self):
		try:

			if MAC:

				import keyring
	#			from keyring.backends.OS_X import Keyring
				keyring.core.set_keyring(keyring.core.load_keyring('keyring.backends.OS_X.Keyring'))
				return keyring

			elif WIN:

				if 'TRAVIS' in os.environ:
					keyring = dummyKeyRing
					return keyring

				import keyring
	#			from keyring.backends.Windows import WinVaultKeyring
				keyring.core.set_keyring(keyring.core.load_keyring('keyring.backends.Windows.WinVaultKeyring'))
				return keyring

			elif LINUX:

				try:
					import keyring
	#				from keyring.backends.kwallet import DBusKeyring
					keyring.core.set_keyring(keyring.core.load_keyring('keyring.backends.kwallet.DBusKeyring'))
				except:
					keyring = dummyKeyRing

	#			if not 'TRAVIS' in os.environ: assert usingRealKeyring == True
				return keyring
		except:
			self.handleTraceback()

	def handleTraceback(self, file = None, submit = True, sourceMethod = None):

		payload = f'''\
Version: {typeWorld.api.VERSION}
{traceback.format_exc()}
'''

		# Remove path parts to make tracebacks identical (so they don't re-surface)

		def removePathPrefix(snippet, file):
			clientPathPrefix = file[:file.find(snippet)]
			print(snippet, file, clientPathPrefix)
			return payload.replace(clientPathPrefix, '')

		if file:
			payload = removePathPrefix('app.py', file)
		else:
			payload = removePathPrefix('typeWorld/client/', __file__)


		supplementary = {
			'os': OSName(),
			'file': file or __file__,
			'preferences': self._preferences.dictionary()
		}
		if sourceMethod:
			supplementary['sourceMethodSignature'] = str(sourceMethod) + str(inspect.signature(sourceMethod))

		supplementary['stack'] = []
		for s in inspect.stack():
			supplementary['stack'].append({
				'frame': str(s.frame),
				'filename': str(s.filename),
				'lineno': str(s.lineno),
				'function': str(s.function),
				'code_context': str(s.code_context),
				})

		parameters = {
			'command': 'handleTraceback',
			'payload': payload,
			'supplementary': json.dumps(supplementary),
		}

		# Submit to central server
		if submit:
			def handleTracebackWorker(self):

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					self.log('handleTraceback() error on server, step 1: %s' % response)

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					self.log('handleTraceback() error on server, step 2: %s' % response)


			handleTracebackThread = threading.Thread(target=handleTracebackWorker, args=(self, ))
			handleTracebackThread.start()


		# Log
		if sourceMethod:
			self.log(payload + '\nMethod signature:\n' + supplementary['sourceMethodSignature'])
		else:
			self.log(payload)


	def log(self, *arg):
		string = 'Type.World: %s' % ' '.join(map(str, arg))
		if MAC:
			nslog(string)
		else:
			logging.debug(string)


	def prepareUpdate(self):
		self._subscriptionsUpdated = []

	def allSubscriptionsUpdated(self):
		try:

			for publisher in self.publishers():
				for subscription in publisher.subscriptions():
					if subscription.stillUpdating(): return False

			return True
		except:
			self.handleTraceback()


	def resourceByURL(self, url, binary = False, update = False): # , username = None, password = None
		'''Caches and returns content of a HTTP resource. If binary is set to True, content will be stored and return as a bas64-encoded string'''
		try:
			resources = self.get('resources') or {}

			if url not in resources or update:

				if self.testScenario:
					url = addAttributeToURL(url, 'testScenario=%s' % self.testScenario)

				request = urllib.request.Request(url)
				# if username and password:
				# 	base64string = base64.b64encode(b"%s:%s" % (username, password)).decode("ascii")
				# 	request.add_header("Authorization", "Basic %s" % base64string)   

				try:
					response = urllib.request.urlopen(request, context=self.sslcontext)
				except:
					return False, traceback.format_exc().splitlines()[-1], None


				content = response.read()
				if binary:
					content = base64.b64encode(content).decode()
				else:
					content = content.decode()

				resources[url] = response.headers['content-type'] + ',' + content
				self.set('resources', resources)

				return True, content, response.headers['content-type']

			else:

				response = resources[url]
				mimeType = response.split(',')[0]
				content = response[len(mimeType)+1:]

				return True, content, mimeType
		except:
			self.handleTraceback()




	# def readGitHubResponse(self, url, username = None, password = None):

	# 	d = {}
	# 	d['errors'] = []
	# 	d['warnings'] = []
	# 	d['information'] = []

	# 	json = ''

	# 	try:


	# 		request = urllib.request.Request(url)
	# 		if username and password:
	# 			base64string = base64.b64encode(b"%s:%s" % (username, password)).decode("ascii")
	# 			request.add_header("Authorization", "Basic %s" % base64string)   
	# 		response = urllib.request.urlopen(request, context=self.sslcontext)

	# 		if response.getcode() == 404:
	# 			d['errors'].append('Server returned with error 404 (Not found).')
	# 			return None, d

	# 		if response.getcode() == 401:
	# 			d['errors'].append('User authentication failed. Please review your username and password.')
	# 			return None, d

	# 		if response.getcode() != 200:
	# 			d['errors'].append('Resource returned with HTTP code %s' % response.code)

	# 		# if not response.headers['content-type'] in acceptableMimeTypes:
	# 		# 	d['errors'].append('Resource headers returned wrong MIME type: "%s". Expected is %s.' % (response.headers['content-type'], acceptableMimeTypes))
	# 		# 	self.log('Received this response with an unexpected MIME type for the URL %s:\n\n%s' % (url, response.read()))

	# 		if response.getcode() == 200:

	# 			json = response.read()

	# 	except:
	# 		exc_type, exc_value, exc_traceback = sys.exc_info()
	# 		for line in traceback.format_exception_only(exc_type, exc_value):
	# 			d['errors'].append(line)
	# 		self.handleTraceback()

	# 	return json, d


	# def addAttributeToURL(self, url, key, value):
	# 	if not key + '=' in url:
	# 		if '?' in url:
	# 			url += '&' + key + '=' + value
	# 		else:
	# 			url += '?' + key + '=' + value
	# 	else:
	# 		url = re.sub(key + '=(\w*)', key + '=' + value, url)

	# 	return url

	def anonymousAppID(self):
		try:
			anonymousAppID = self.get('anonymousAppID')

			if anonymousAppID == None or anonymousAppID == {}:
				import uuid
				anonymousAppID = str(uuid.uuid1())
				self.set('anonymousAppID', anonymousAppID)


			return anonymousAppID
		except:
			self.handleTraceback()


	def rootCommand(self, url):
		try:
			# Check for URL validity
			success, response = urlIsValid(url)
			if not success:
				return False, response

			# Get subscription
			success, protocol = getProtocol(url)
			# Get Root Command
			return protocol.rootCommand(testScenario = self.testScenario)
		except:
			self.handleTraceback()


	def addSubscription(self, url, username = None, password = None, updateSubscriptionsOnServer = True, JSON = None, secretTypeWorldAPIKey = None):
		'''
		Because this also gets used by the central Type.World server, pass on the secretTypeWorldAPIKey attribute to your web service as well.
		'''
		try:
			self._updatingProblem = None

			# Check for URL validity
			success, response = urlIsValid(url)
			if not success:
				return False, response, None, None

			# Get subscription
			success, message = getProtocol(url)
			if success:
				protocol = message
				protocol.client = self
			else:
				return False, message, None, None

			# Initial rootCommand
			success, message = self.rootCommand(url)
			if success:
				rootCommand = message
			else:
				return False, message, None, None

			if not updateSubscriptionsOnServer and protocol.url.accessToken:
				return False, 'Accessing a subscription with an access token requires the subscription to be synched to the server afterwards, but `updateSubscriptionsOnServer` is set to False.', None, None

			if not self.user() and protocol.url.accessToken:
				return False, 'Accessing a subscription with an access token requires the app to be linked to a Type.World user account.', None, None

			# Change secret key
			if protocol.unsecretURL() in self.unsecretSubscriptionURLs():
				protocol.setSecretKey(protocol.url.secretKey)
				publisher = self.publisher(rootCommand.canonicalURL)
				subscription = publisher.subscription(protocol.unsecretURL(), protocol)

			else:
				# Initial Health Check
				success, response = protocol.aboutToAddSubscription(anonymousAppID = self.anonymousAppID(), anonymousTypeWorldUserID = self.user(), accessToken = protocol.url.accessToken, secretTypeWorldAPIKey = secretTypeWorldAPIKey or self.secretTypeWorldAPIKey, testScenario = self.testScenario)
				if not success:
					if type(response) == typeWorld.api.MultiLanguageText or type(response) == list and response[0].startswith('#('):
						message = response
					else:
						message = response # 'Response from protocol.aboutToAddSubscription(): %s' % 
						if message == ['#(response.loginRequired)', '#(response.loginRequired.headline)']:
							self._updatingProblem = ['#(response.loginRequired)', '#(response.loginRequired.headline)']
					return False, message, None, None

				publisher = self.publisher(rootCommand.canonicalURL)
				subscription = publisher.subscription(protocol.unsecretURL(), protocol)

				# Success
				subscription.save()
				publisher.save()
				subscription.stillAlive()

			if updateSubscriptionsOnServer:
				success, message = self.uploadSubscriptions()
				if not success:
					return False, message, None, None # 'Response from client.uploadSubscriptions(): %s' % 

			protocol.subscriptionAdded()


			return True, None, self.publisher(rootCommand.canonicalURL), subscription

		except:
			self.handleTraceback()

			# Outdated (for now)
			# elif url.startswith('typeworldgithub://'):


			# 	url = url.replace('typeworldgithub://', '')
			# 	# remove trailing slash
			# 	while url.endswith('/'):
			# 		url = url[:-1]
				
			# 	if not url.startswith('https://'):
			# 		return False, 'GitHub-URL needs to start with https://', None, None

			# 	canonicalURL = '/'.join(url.split('/')[:4])
			# 	owner = url.split('/')[3]
			# 	repo = url.split('/')[4]
			# 	path = '/'.join(url.split('/')[7:])


			# 	commitsURL = 'https://api.github.com/repos/%s/%s/commits?path=%s' % (owner, repo, path)


			# 	publisher = self.publisher(canonicalURL)
			# 	publisher.set('type', 'GitHub')

			# 	if username and password:
			# 		publisher.set('username', username)
			# 		publisher.setPassword(username, password)

			# 	allowed, message = publisher.gitHubRateLimit()
			# 	if not allowed:
			# 		return False, message, None, None

			# 	# Read response
			# 	commits, responses = publisher.readGitHubResponse(commitsURL)

			# 	# Errors
			# 	if responses['errors']:
			# 		return False, '\n'.join(responses['errors']), None, None

			# 	success, message = publisher.addGitHubSubscription(url, commits), None
			# 	publisher.save()

			# 	return success, message, self.publisher(canonicalURL), None


		# except:

		# 	exc_type, exc_value, exc_traceback = sys.exc_info()
		# 	return False, traceback.format_exc(), None, None


	# def currentPublisher(self):
	# 	if self.get('currentPublisher') and self.get('currentPublisher') != 'None' and self.get('currentPublisher') != 'pendingInvitations':
	# 		publisher = self.publisher(self.get('currentPublisher'))
	# 		return publisher

	def publisher(self, canonicalURL):
		try:
			if canonicalURL not in self._publishers:
				e = APIPublisher(self, canonicalURL)
				self._publishers[canonicalURL] = e

			if self.get('publishers') and canonicalURL in self.get('publishers'):
				self._publishers[canonicalURL].exists = True

			return self._publishers[canonicalURL]
		except:
			self.handleTraceback()

	def publishers(self):
		try:
			if self.get('publishers'):
				return [self.publisher(canonicalURL) for canonicalURL in self.get('publishers')]
			else:
				return []
		except:
			self.handleTraceback()


class APIPublisher(object):
	"""\
	Represents an API endpoint, identified and grouped by the canonical URL attribute of the API responses. This API endpoint class can then hold several repositories.
	"""

	def __init__(self, parent, canonicalURL):
		self.parent = parent
		self.canonicalURL = canonicalURL
		self.exists = False
		self._subscriptions = {}


		self._updatingSubscriptions = []


	def folder(self):
		try:
			if WIN:
				return os.path.join(os.environ['WINDIR'], 'Fonts')

			elif MAC:

				from os.path import expanduser
				home = expanduser("~")


				rootCommand = self.subscriptions()[0].protocol.rootCommand()[1]
				title = rootCommand.name.getText()

				folder = os.path.join(home, 'Library', 'Fonts', 'Type.World App')

				return folder

			else:
				import tempfile
				return tempfile.gettempdir()
		except:
			self.parent.handleTraceback()


	def stillUpdating(self):
		try:
			return len(self._updatingSubscriptions) > 0
		except:
			self.parent.handleTraceback()


	def updatingProblem(self):
		try:

			problems = []

			for subscription in self.subscriptions():
				problem = subscription.updatingProblem()
				if problem and not problem in problems: problems.append(problem)

			if problems: return problems

		except:
			self.parent.handleTraceback()


	# def gitHubRateLimit(self):

	# 	limits, responses = self.readGitHubResponse('https://api.github.com/rate_limit')

	# 	if responses['errors']:
	# 		return False, '\n'.join(responses['errors'])

	# 	limits = json.loads(limits)

	# 	if limits['rate']['remaining'] == 0:
	# 		return False, 'Your GitHub API rate limit has been reached. The limit resets at %s.' % (datetime.datetime.fromtimestamp(limits['rate']['reset']).strftime('%Y-%m-%d %H:%M:%S'))

	# 	return True, None


	# def readGitHubResponse(self, url):

	# 	if self.get('username') and self.getPassword(self.get('username')):
	# 		return self.parent.readGitHubResponse(url, self.get('username'), self.getPassword(self.get('username')))
	# 	else:
	# 		return self.parent.readGitHubResponse(url)

	def name(self, locale = ['en']):

		try:
			rootCommand = self.subscriptions()[0].protocol.rootCommand()[1]
			if rootCommand:
				return rootCommand.name.getTextAndLocale(locale = locale)
		except:
			self.parent.handleTraceback()

	# def getPassword(self, username):
	# 	keyring = self.parent.keyring()
	# 	return keyring.get_password("Type.World GitHub Subscription %s (%s)" % (self.canonicalURL, username), username)

	# def setPassword(self, username, password):
	# 	keyring = self.parent.keyring()
	# 	keyring.set_password("Type.World GitHub Subscription %s (%s)" % (self.canonicalURL, username), username, password)

	# def resourceByURL(self, url, binary = False, update = False):
	# 	'''Caches and returns content of a HTTP resource. If binary is set to True, content will be stored and return as a bas64-encoded string'''

	# 	# Save resource
	# 	resourcesList = self.get('resources') or []
	# 	if not url in resourcesList:
	# 		resourcesList.append(url)
	# 		self.set('resources', resourcesList)

	# 	if self.get('username') and self.getPassword(self.get('username')):
	# 		return self.parent.resourceByURL(url, binary = binary, update = update, username = self.get('username'), password = self.getPassword(self.get('username')))
	# 	else:
	# 		return self.parent.resourceByURL(url, binary = binary, update = update)

	def amountInstalledFonts(self):
		try:
			return len(self.installedFonts())
		except:
			self.parent.handleTraceback()

	def installedFonts(self):
		try:
			l = []

			for subscription in self.subscriptions():
				for font in subscription.installedFonts():
					if not font in l:
						l.append(font)

			return l
		except:
			self.parent.handleTraceback()

	def amountOutdatedFonts(self):
		try:
			return len(self.outdatedFonts())
		except:
			self.parent.handleTraceback()

	def outdatedFonts(self):
		try:
			l = []

			for subscription in self.subscriptions():
				for font in subscription.outdatedFonts():
					if not font in l:
						l.append(font)

			return l
		except:
			self.parent.handleTraceback()

	# def currentSubscription(self):
	# 	if self.get('currentSubscription'):
	# 		subscription = self.subscription(self.get('currentSubscription'))
	# 		if subscription:
	# 			return subscription

	def get(self, key):
		try:
			preferences = dict(self.parent.get(self.canonicalURL) or self.parent.get('publisher(%s)' % self.canonicalURL) or {})
			if key in preferences:

				o = preferences[key]

				if 'Array' in o.__class__.__name__: o = list(o)
				elif 'Dictionary' in o.__class__.__name__: o = dict(o)

				return o
		except:
			self.parent.handleTraceback()

	def set(self, key, value):
		try:
			preferences = dict(self.parent.get(self.canonicalURL) or self.parent.get('publisher(%s)' % self.canonicalURL) or {})
			preferences[key] = value
			self.parent.set('publisher(%s)' % self.canonicalURL, preferences)
		except:
			self.parent.handleTraceback()


	# def addGitHubSubscription(self, url, commits):

	# 	self.parent._subscriptions = {}

	# 	subscription = self.subscription(url)
	# 	subscription.set('commits', commits)
	# 	self.set('currentSubscription', url)
	# 	subscription.save()

	# 	return True, None


	def subscription(self, url, protocol = None):
		try:

			if url not in self._subscriptions:

				# Load from DB
				loadFromDB = False

				if not protocol:
					success, message = getProtocol(url)
					if success:
						protocol = message
						loadFromDB = True

				e = APISubscription(self, protocol)
				if loadFromDB:
					protocol.loadFromDB()

				self._subscriptions[url] = e

			if self.get('subscriptions') and url in self.get('subscriptions'):
				self._subscriptions[url].exists = True

			return self._subscriptions[url]
		except:
			self.parent.handleTraceback()

	def subscriptions(self):
		try:
			return [self.subscription(url) for url in self.get('subscriptions') or []]
		except:
			self.parent.handleTraceback()

	def update(self):
		try:

			self.parent.prepareUpdate()

			changes = False

			if self.parent.online():

				for subscription in self.subscriptions():
					success, message, change = subscription.update()
					if change: changes = True
					if not success:
						return success, message, changes

				return True, None, changes

			else:
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)'], False
		except:
			self.parent.handleTraceback()

	def save(self):
		try:
			publishers = self.parent.get('publishers') or []
			if not self.canonicalURL in publishers:
				publishers.append(self.canonicalURL)
			self.parent.set('publishers', publishers)
		except:
			self.parent.handleTraceback()

	def resourceByURL(self, url, binary = False, update = False):
		'''Caches and returns content of a HTTP resource. If binary is set to True, content will be stored and return as a bas64-encoded string'''

		try:
			response = self.parent.resourceByURL(url, binary, update)

			# Save resource
			if response[0] == True:
				resourcesList = self.get('resources') or []
				if not url in resourcesList:
					resourcesList.append(url)
					self.set('resources', resourcesList)

			return response
		except:
			self.parent.handleTraceback()


	def delete(self):
		try:
			for subscription in self.subscriptions():
				subscription.delete(calledFromParent = True)

			# Resources
			resources = self.parent.get('resources') or {}
			for url in self.get('resources') or []:
				if url in resources:
					del resources[url]
			self.parent.set('resources', resources)

			self.parent.remove('publisher(%s)' % self.canonicalURL)
			publishers = self.parent.get('publishers')
			publishers.remove(self.canonicalURL)
			self.parent.set('publishers', publishers)
			# self.parent.set('currentPublisher', '')
			
			self.parent.delegate._publisherWasDeleted(self)

			self.parent._publishers = {}
		except:
			self.parent.handleTraceback()



class APISubscription(PubSubClient):
	"""\
	Represents a subscription, identified and grouped by the canonical URL attribute of the API responses.
	"""

	def __init__(self, parent, protocol):
		try:
			self.parent = parent
			self.exists = False
			self.secretKey = None
			self.protocol = protocol
			self.protocol.subscription = self
			self.protocol.client = self.parent.parent
			self.url = self.protocol.unsecretURL()

			self.stillAliveTouched = None
			self._updatingProblem = None

			# Pub/Sub
			if self.parent.parent.pubSubSubscriptions:
				self.pubsubSubscription = None
				self.pubSubTopicID = 'subscription-%s' % urllib.parse.quote_plus(self.protocol.unsecretURL())
				self.pubSubExecuteConditionMethod = None
				self.pubSubSetup()

		except:
			self.parent.parent.handleTraceback()


	def uniqueID(self):
		try:
			uniqueID = self.get('uniqueID')

			if uniqueID == None or uniqueID == {}:
				import uuid
				uniqueID = Garbage(10)
				self.set('uniqueID', uniqueID)

			return uniqueID
		except:
			self.parent.parent.handleTraceback()

	def pubSubCallback(self, message):
		try:
			self.parent.parent.delegate._subscriptionUpdateNotificationHasBeenReceived(self)
			if message:
				message.ack()
				self.set('lastPubSubMessage', int(time.time()))
		except:
			self.parent.parent.handleTraceback()


	def announceChange(self):
		try:
			userID = self.user()

			if userID:

				self.set('lastServerSync', int(time.time()))

				parameters = {
					'command': 'updateSubscription',
					'anonymousAppID': self.anonymousAppID(),
					'anonymousUserID': userID,
					'subscriptionURL': self.protocol.url.secretURL(),
					'secretKey': self.secretKey(),
				}

				success, response = self.performRequest(self.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] != 'success':
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			# Success
			return True, None
		except:
			self.parent.parent.handleTraceback()

	def hasProtectedFonts(self):
		try:
			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						if font.protected:
							return True

			return False
		except:
			self.parent.parent.handleTraceback()


	def stillAlive(self):

		try:
			def stillAliveWorker(self):

				# Register endpoint

				parameters = {
					'command': 'registerAPIEndpoint',
					'url': 'typeworld://%s+%s' % (self.protocol.url.protocol, self.parent.canonicalURL.replace('://', '//')),
				}

				success, response = self.parent.parent.performRequest(self.parent.parent.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())


			# Touch only once
			if not self.parent.parent.user():
				if not self.stillAliveTouched:

					stillAliveThread = threading.Thread(target=stillAliveWorker, args=(self, ))
					stillAliveThread.start()

					self.stillAliveTouched = time.time()			
		except:
			self.parent.parent.handleTraceback()


	def inviteUser(self, targetEmail):
		try:

			if self.parent.parent.online():

				if not self.parent.parent.userEmail():
					return False, 'No source user linked.'

				parameters = {
					'command': 'inviteUserToSubscription',
					'targetUserEmail': targetEmail,
					'sourceUserEmail': self.parent.parent.userEmail(),
					'subscriptionURL': self.protocol.secretURL(),
				}

				success, response = self.parent.parent.performRequest(self.parent.parent.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] == 'success':
					return True, None
				else:
					return False, ['#(response.%s)' % response['response'], '#(response.%s.headline)' % response['response']]

			else:
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)']
		except:
			self.parent.parent.handleTraceback()



		# if response['response'] == 'invalidSubscriptionURL':
		# 	return False, 'The subscription URL %s is invalid.' % subscription.protocol.secretURL()

		# elif response['response'] == 'unknownTargetEmail':
		# 	return False, 'The invited user doesn’t have a valid Type.World user account as %s.' % email

		# elif response['response'] == 'invalidSource':
		# 	return False, 'The source user could not be identified or doesn’t hold this subscription.'

		# elif response['response'] == 'success':
		# 	return True, None


	def revokeUser(self, targetEmail):
		try:

			if self.parent.parent.online():

				parameters = {
					'command': 'revokeSubscriptionInvitation',
					'targetUserEmail': targetEmail,
					'sourceUserEmail': self.parent.parent.userEmail(),
					'subscriptionURL': self.protocol.secretURL(),
				}

				success, response = self.parent.parent.performRequest(self.parent.parent.mothership, parameters)
				if not success:
					return False, response

				response = json.loads(response.read().decode())

				if response['response'] == 'success':
					return True, None
				else:
					return False, response['response']

			else:
				return False, ['#(response.notOnline)', '#(response.notOnline.headline)']
		except:
			self.parent.parent.handleTraceback()

	def invitationAccepted(self):
		try:

			if self.parent.parent.user():
				acceptedInvitations = self.parent.parent.acceptedInvitations()
				if acceptedInvitations:
					for invitation in acceptedInvitations:
						if self.protocol.unsecretURL() == invitation.url:
							return True

		except:
			self.parent.parent.handleTraceback()

	def stillUpdating(self):
		try:
			return self.url in self.parent._updatingSubscriptions
		except:
			self.parent.parent.handleTraceback()


	def name(self, locale = ['en']):
		try:

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			return installabeFontsCommand.name.getText(locale) or '#(Unnamed)'
		except:
			self.parent.parent.handleTraceback()

	def resourceByURL(self, url, binary = False, update = False):
		'''Caches and returns content of a HTTP resource. If binary is set to True, content will be stored and return as a bas64-encoded string'''
		try:
			response = self.parent.parent.resourceByURL(url, binary, update)

			# Save resource
			if response[0] == True:
				resourcesList = self.get('resources') or []
				if not url in resourcesList:
					resourcesList.append(url)
					self.set('resources', resourcesList)

			return response
		except:
			self.parent.parent.handleTraceback()



	def familyByID(self, ID):
		try:
			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					if family.uniqueID == ID:
						return family
		except:
			self.parent.parent.handleTraceback()

	def fontByID(self, ID):
		try:
			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						if font.uniqueID == ID:
							return font
		except:
			self.parent.parent.handleTraceback()

	def amountInstalledFonts(self):
		try:
			return len(self.installedFonts())
		except:
			self.parent.parent.handleTraceback()

	def installedFonts(self):
		try:
			l = []
			# Get font

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						if self.installedFontVersion(font.uniqueID):
							if not font in l:
								l.append(font)
			return l
		except:
			self.parent.parent.handleTraceback()

	def expiringInstalledFonts(self):
		try:
			l = []
			# Get font

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						if self.installedFontVersion(font.uniqueID) and font.expiry:
							if not font in l:
								l.append(font)
			return l
		except:
			self.parent.parent.handleTraceback()

	def amountOutdatedFonts(self):
		try:
			return len(self.outdatedFonts())
		except:
			self.parent.parent.handleTraceback()

	def outdatedFonts(self):
		try:
			l = []

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			# Get font
			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						installedFontVersion = self.installedFontVersion(font.uniqueID)
						if installedFontVersion and installedFontVersion != font.getVersions()[-1].number:
							if not font in l:
								l.append(font.uniqueID)
			return l
		except:
			self.parent.parent.handleTraceback()

	def installedFontVersion(self, fontID = None, font = None):
		try:

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			folder = self.parent.folder()

			if not font:
				for foundry in installabeFontsCommand.foundries:
					for family in foundry.families:
						for font in family.fonts:
							if font.uniqueID == fontID:
								for version in font.getVersions():
									path = os.path.join(folder, self.uniqueID() + '-' + font.filename(version.number))
									if os.path.exists(path):
										return version.number
			else:
				for version in font.getVersions():
					path = os.path.join(folder, self.uniqueID() + '-' + font.filename(version.number))
					if os.path.exists(path):
						return version.number
		except:
			self.parent.parent.handleTraceback()

	# def fontIsOutdated(self, fontID):

	# 	success, installabeFontsCommand = self.protocol.installableFontsCommand()

	# 	for foundry in installabeFontsCommand.foundries:
	# 		for family in foundry.families:
	# 			for font in family.fonts:
	# 				if font.uniqueID == fontID:

	# 					installedVersion = self.installedFontVersion(fontID)
	# 					return installedVersion and installedVersion != font.getVersions()[-1].number



	def removeFonts(self, fonts, dryRun = False, updateSubscription = True):
		try:
			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			uninstallTheseProtectedFontIDs = []
			uninstallTheseUnprotectedFontIDs = []

			folder = self.parent.folder()

			fontIDs = []

			for fontID in fonts:

				fontIDs.append(fontID)

				path = None
				for foundry in installabeFontsCommand.foundries:
					for family in foundry.families:
						for font in family.fonts:
							if font.uniqueID == fontID:
								if self.installedFontVersion(font.uniqueID):
									path = os.path.join(folder, self.uniqueID() + '-' + font.filename(self.installedFontVersion(font.uniqueID)))
									break

				if not path and not dryRun:
					return False, 'Font path couldn’t be determined (preflight)'

				if font.protected:

					self.parent.parent.delegate._fontWillUninstall(font)

					# Test for permissions here
					if not dryRun:
						try:
							if self.parent.parent.testScenario == 'simulatePermissionError':
								raise PermissionError
							else:
								if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
								f = open(path + '.test', 'w')
								f.write('test')
								f.close()
								os.remove(path + '.test')
						except PermissionError:
							self.parent.parent.delegate._fontHasInstalled(False, "Insufficient permission to uninstall font.", font)
							return False, "Insufficient permission to uninstall font."

						assert os.path.exists(path + '.test') == False

					uninstallTheseProtectedFontIDs.append(fontID)

				else:
					uninstallTheseUnprotectedFontIDs.append(fontID)




			# Server access
			# Protected fonts
			if uninstallTheseProtectedFontIDs:
				success, payload = self.protocol.removeFonts(uninstallTheseProtectedFontIDs, updateSubscription = updateSubscription)

				if success:

					# Security check
					if set([x.uniqueID for x in payload.assets]) - set(fontIDs) or set(fontIDs) - set([x.uniqueID for x in payload.assets]):
						return False, 'Incoming fonts’ uniqueIDs mismatch with requested font IDs.'

					# Process fonts
					for incomingFont in payload.assets:

						proceed = ['unknownInstallation'] # 

						if incomingFont.response in proceed:
							pass

						elif incomingFont.response == 'error':
							return False, incomingFont.errorMessage

						# Predefined response messages
						elif incomingFont.response != 'error' and incomingFont.response != 'success':
							return False, ['#(response.%s)' % incomingFont.response, '#(response.%s.headline)' % incomingFont.response]

						if incomingFont.response == 'success':

							path = None
							for foundry in installabeFontsCommand.foundries:
								for family in foundry.families:
									for font in family.fonts:
										if font.uniqueID == incomingFont.uniqueID:
											if self.installedFontVersion(font.uniqueID):
												path = os.path.join(folder, self.uniqueID() + '-' + font.filename(self.installedFontVersion(font.uniqueID)))
												break

							if not path and not dryRun:
								return False, 'Font path couldn’t be determined (deleting protected fonts)'

							if not dryRun:
								os.remove(path)
								# print('Actually deleted font %s' % path)

							self.parent.parent.delegate._fontHasUninstalled(True, None, font)


				else:
					self.parent.parent.delegate._fontHasUninstalled(False, payload, font)
					return False, payload

			# Unprotected fonts
			if uninstallTheseUnprotectedFontIDs:

				for fontID in uninstallTheseUnprotectedFontIDs:

					path = None
					for foundry in installabeFontsCommand.foundries:
						for family in foundry.families:
							for font in family.fonts:
								if font.uniqueID == fontID:
									if self.installedFontVersion(font.uniqueID):
										path = os.path.join(folder, self.uniqueID() + '-' + font.filename(self.installedFontVersion(font.uniqueID)))
										break

					if not path and not dryRun:
						return False, 'Font path couldn’t be determined (deleting unprotected fonts)'

					if not dryRun:
						os.remove(path)

					self.parent.parent.delegate._fontHasUninstalled(True, None, font)

			return True, None
		except:
			self.parent.parent.handleTraceback()




	def installFonts(self, fonts):
		try:

			# Terms of Service
			if self.get('acceptedTermsOfService') != True:
				return False, ['#(response.termsOfServiceNotAccepted)', '#(response.termsOfServiceNotAccepted.headline)']

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			installTheseFontIDs = []
			protectedFonts = False

			folder = self.parent.folder()

			fontIDs = []

			for fontID, version in fonts:

				fontIDs.append(fontID)

				path = None
				font = None
				for foundry in installabeFontsCommand.foundries:
					for family in foundry.families:
						for font in family.fonts:
							if font.uniqueID == fontID:
								path = os.path.join(folder, self.uniqueID() + '-' + font.filename(version))
								if font.protected:
									protectedFonts = True
								break
				assert path
				# print('path', path)
				assert font
				# print('font', font)

				self.parent.parent.delegate._fontWillInstall(font)

				# Test for permissions here
				try:
					if self.parent.parent.testScenario == 'simulatePermissionError':
						raise PermissionError
					else:
						if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
						f = open(path + '.test', 'w')
						f.write('test')
						f.close()
						os.remove(path + '.test')
				except PermissionError:
					self.parent.parent.delegate._fontHasInstalled(False, "Insufficient permission to install font.", font)
					return False, "Insufficient permission to install font."

				assert os.path.exists(path + '.test') == False

				installTheseFontIDs.append(fontID)

			# Server access
			success, payload = self.protocol.installFonts(fonts, updateSubscription = protectedFonts)		

			if success:

				# Security check
				if set([x.uniqueID for x in payload.assets]) - set(fontIDs) or set(fontIDs) - set([x.uniqueID for x in payload.assets]):
					return False, 'Incoming fonts’ uniqueIDs mismatch with requested font IDs.'

				# Process fonts
				for incomingFont in payload.assets:

					if incomingFont.response == 'error':
						return False, incomingFont.errorMessage

					# Predefined response messages
					elif incomingFont.response != 'error' and incomingFont.response != 'success':
						return False, ['#(response.%s)' % incomingFont.response, '#(response.%s.headline)' % incomingFont.response]

					if incomingFont.response == 'success':

						path = None
						for foundry in installabeFontsCommand.foundries:
							for family in foundry.families:
								for font in family.fonts:
									if font.uniqueID == incomingFont.uniqueID:
										path = os.path.join(folder, self.uniqueID() + '-' + font.filename(version))
										break
						assert path

						if not os.path.exists(os.path.dirname(path)): os.makedirs(os.path.dirname(path))
						f = open(path, 'wb')
						f.write(base64.b64decode(incomingFont.data))
						f.close()
						# print('Actually wrote font %s to disk' % path)

						self.parent.parent.delegate._fontHasInstalled(True, None, font)

				# Ping
				self.stillAlive()

				return True, None


			else:
				self.parent.parent.delegate._fontHasInstalled(False, payload, font)
				return False, payload

		except:
			self.parent.parent.handleTraceback()


		# elif self.parent.get('type') == 'GitHub':

		# 	allowed, message = self.parent.gitHubRateLimit()
		# 	if allowed:

		# 		# Get font
		# 		for foundry in self.foundries():
		# 			for family in foundry.families():
		# 				for font in family.fonts():
		# 					if font.uniqueID == fontID:

		# 						for commit in json.loads(self.get('commits')):
		# 							if commit['commit']['message'].startswith('Version: %s' % version):
		# 								# print('Install version %s, commit %s' % (version, commit['sha']))

		# 								owner = self.url.split('/')[3]
		# 								repo = self.url.split('/')[4]
		# 								urlpath = '/'.join(self.url.split('/')[7:]) + '/fonts/' + font.postScriptName + '.' + font.format


		# 								url = 'https://api.github.com/repos/%s/%s/contents/%s?ref=%s' % (owner, repo, urlpath, commit['sha'])
		# 								# print(url)
		# 								response, responses = self.parent.readGitHubResponse(url)
		# 								response = json.loads(response)


		# 								# Write file
		# 								path = font.path(version, folder)

		# 								# Create folder if it doesn't exist
		# 								if not os.path.exists(os.path.dirname(path)):
		# 									os.makedirs(os.path.dirname(path))

		# 								f = open(path, 'wb')
		# 								f.write(base64.b64decode(response['content']))
		# 								f.close()

		# 								return True, None
		# 	else:
		# 		return False, message



		# return False, 'No font was found to install.'


	def update(self):
		try:
			self.parent._updatingSubscriptions.append(self.url)


			if self.parent.parent.online(self.protocol.url.restDomain.split('/')[0]):

				self.stillAlive()

				success, message, changes = self.protocol.update()

				# elif self.parent.get('type') == 'GitHub':

				# 	owner = self.url.split('/')[3]
				# 	repo = self.url.split('/')[4]
				# 	path = '/'.join(self.url.split('/')[7:])

				# 	commitsURL = 'https://api.github.com/repos/%s/%s/commits?path=%s/fonts' % (owner, repo, path)

				# 	# Read response
				# 	commits, responses = self.parent.readGitHubResponse(commitsURL)
				# 	self.set('commits', commits)

				if not success:
					return success, message, changes

				if self.url in self.parent._updatingSubscriptions:
					self.parent._updatingSubscriptions.remove(self.url)
				self._updatingProblem = None
				self.parent.parent._subscriptionsUpdated.append(self.url)

				if changes:
					self.save()

				# Success
				self.parent.parent.delegate._subscriptionWasUpdated(self)

				return True, None, changes

			else:
				self.parent._updatingSubscriptions.remove(self.url)
				self.parent.parent._subscriptionsUpdated.append(self.url)
				self._updatingProblem = ['#(response.serverNotReachable)', '#(response.serverNotReachable.headline)']
				return False, self._updatingProblem, False

		except:
			self.parent.parent.handleTraceback()

	def updatingProblem(self):
		try:
			return self._updatingProblem
		except:
			self.parent.parent.handleTraceback()

	def get(self, key):
		try:
			preferences = dict(self.parent.parent.get('subscription(%s)' % self.protocol.unsecretURL()) or {})
			if key in preferences:

				o = preferences[key]

				if 'Array' in o.__class__.__name__:
					o = list(o)

				elif 'Dictionary' in o.__class__.__name__:
					o = dict(o)

				return o
		except:
			self.parent.parent.handleTraceback()

	def set(self, key, value):
		try:

			preferences = dict(self.parent.parent.get('subscription(%s)' % self.protocol.unsecretURL()) or {})
			preferences[key] = value
			self.parent.parent.set('subscription(%s)' % self.protocol.unsecretURL(), preferences)
		except:
			self.parent.parent.handleTraceback()

	def save(self):
		try:
			subscriptions = self.parent.get('subscriptions') or []
			if not self.protocol.unsecretURL() in subscriptions:
				subscriptions.append(self.protocol.unsecretURL())
			self.parent.set('subscriptions', subscriptions)

			self.protocol.save()
		except:
			self.parent.parent.handleTraceback()


	def delete(self, calledFromParent = False, updateSubscriptionsOnServer = True):
		try:
			self.parent.parent.log('Deleting %s, updateSubscriptionsOnServer: %s' % (self, updateSubscriptionsOnServer))

			success, installabeFontsCommand = self.protocol.installableFontsCommand()

			# Delete all fonts
			for foundry in installabeFontsCommand.foundries:
				for family in foundry.families:
					for font in family.fonts:
						self.removeFonts([font.uniqueID])

			# Key
			try:
				self.protocol.deleteSecretKey()
			except:
				pass


			self.pubSubDelete()

			# Resources
			resources = self.parent.parent.get('resources') or {}
			for url in self.get('resources') or []:
				if url in resources:
					resources.pop(url)
			self.parent.parent.set('resources', resources)


			# New
			self.parent.parent.remove('subscription(%s)' % self.protocol.unsecretURL())

			# Subscriptions
			subscriptions = self.parent.get('subscriptions')
			subscriptions.remove(self.protocol.unsecretURL())
			self.parent.set('subscriptions', subscriptions)
			self.parent._subscriptions = {}


			# # currentSubscription
			# if self.parent.get('currentSubscription') == self.protocol.unsecretURL():
			# 	if len(subscriptions) >= 1:
			# 		self.parent.set('currentSubscription', subscriptions[0])

			self.parent._subscriptions = {}

			if len(subscriptions) == 0 and calledFromParent == False:
				self.parent.delete()

			self.parent.parent.delegate._subscriptionWasDeleted(self)

			if updateSubscriptionsOnServer:
				self.parent.parent.uploadSubscriptions()

		except:
			self.parent.parent.handleTraceback()
