#!/usr/bin/python
__version__ = '0.1'

import BaseHTTPServer, select, socket, SocketServer, urlparse, re

debugging 			= True #Used for debugging
domainList 			= [] #Stores domain regexps
urlList 			= [] #Stores url regexps
contentList 		= [] #Stores content regexps
plainTextList 		= [] # Content types we can work with
oldContentType 		= "" #Stores old content type, useless maybe
currentContentType 	= "" #Stores current content type

logList = ['[+]','[x]','[!]','[>]','[<]'] 
LOG_STD = 0
LOG_ERR = 1
LOG_WAR = 2
LOG_INP = 3
LOG_OUT = 4

def log(data,type=0):
	if debugging:
		print logList[type], str(data)

def loadFile(file):
	stream = open(file,'r')
	content = stream.read()
	content = content[:len(content)-1].split('\n')
	return content

def loadExpressions():
	global domainList, urlList, contentList, plainTextList
	domainList = loadFile('regex/domain.rxp')
	urlList = loadFile('regex/url.rxp')
	contentList = loadFile('regex/content.rxp')
	plainTextList = loadFile('regex/text.rxp') #Not Regex
	
def patternMatches(pattern,text):
	if pattern != '' and re.match(pattern,text):
		return True
	else:
		return False

def isBannedPath(path):
	banned = False
	for pattern in urlList:
		if patternMatches(pattern,path):
			banned = True
			break
	return banned

def isBannedDomain(domain):
	banned = False
	for pattern in domainList:
		if patternMatches(pattern,domain):
			banned = True
			break
	return banned

def updateContentType(data):
	global currentContentType,oldContentType
	start = data.find("Content-Type:")
	end = data.find("\n",start+1)-1
	if start != -1 and end != -1:
		start += 14
		oldContentType = currentContentType
		currentContentType = data[start:end]
		colon = currentContentType.find(';')
		if colon != -1:
			currentContentType = currentContentType[:colon]

def removeContent(data):
	for regexp in contentList:
		data = re.sub(regexp,'',data)
	return data

#FIXME: Not working i belive the Content-Type needs to be cached first
def fixContent(data):
	try:
		tmp = data.split('\r\n\r\n',1)
		header = tmp[0]
		body = tmp[1]
		data = removeContent(body) # Filter
		data = header + '\r\n\r\n' + body
		return data
	except:
		data = removeContent(data) #Filter
		return data

class ProxyHandler (BaseHTTPServer.BaseHTTPRequestHandler):
	__base = BaseHTTPServer.BaseHTTPRequestHandler
	__base_handle = __base.handle

	server_version = 'TinyHTTPProxyFilter/' + __version__
	rbufsize = 0					    # self.rfile Be unbuffered

	def handle(self):
		(ip, port) =  self.client_address
		if hasattr(self, 'allowed_clients') and ip not in self.allowed_clients:
			self.raw_requestline = self.rfile.readline()
			if self.parse_request(): self.send_error(403)
		else:
			self.__base_handle()

	def _connect_to(self, netloc, soc):
		i = netloc.find(':')
		if i >= 0:
			host_port = netloc[:i], int(netloc[i+1:])
		else:
			host_port = netloc, 80
		try: soc.connect(host_port)
		except socket.error, arg:
			try: msg = arg[1]
			except: msg = arg
			self.send_error(404, msg)
			return 0
		return 1

	def do_CONNECT(self):
		soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			if self._connect_to(self.path, soc):
				self.wfile.write(self.protocol_version + ' 200 Connection established\r\n')
				self.wfile.write('Proxy-agent: %s\r\n' % self.version_string())
				self.wfile.write('\r\n')
				self._read_write(soc, 300)
		finally:
			soc.close()
			self.connection.close()

	def do_GET(self):
		(scm, netloc, path, params, query, fragment) = urlparse.urlparse(self.path, 'http')
		if scm != 'http' or fragment or not netloc:
			self.send_error(400, 'bad url %s' % self.path)
			return
		soc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			if self._connect_to(netloc, soc):
				#TODO TESTING
				bannedDomain = isBannedDomain(netloc)
				bannedPath = isBannedPath(path)
				if not bannedDomain:
					if not bannedPath:
						log('%s' % path,LOG_OUT)
						soc.send('%s %s %s\r\n' % (self.command,urlparse.urlunparse(('', '', path, params, query, '')),	self.request_version))
						self.headers['Connection'] = 'close'
						del self.headers['Proxy-Connection']
						for key_val in self.headers.items():
							soc.send('%s: %s\r\n' % key_val)
						soc.send('\r\n')
						self._read_write(soc)
					else:
						#FIXME: The client gets empty data
						#send dummy header/content?
						log('%s' % path,LOG_WAR)
				else:
					log('%s' % netloc,LOG_WAR)
		finally:
			soc.close()
			self.connection.close()

	def _read_write(self, soc, max_idling=25):
		iw = [self.connection, soc]
		ow = []
		count = 0
		while 1:
			count += 1
			(ins, _, exs) = select.select(iw, ow, iw, 3)
			if exs: break
			if ins:
				for i in ins:
					if i is soc:
						out = self.connection
					else:
						out = soc
					data = i.recv(8192)
					if data:
						updateContentType(data)
						if currentContentType in plainTextList:	x=1
						#TODO: Content Filter
						out.send(data)
						count = 0
			if count == max_idling: break

	do_HEAD = do_GET
	do_POST = do_GET
	do_PUT  = do_GET
	do_DELETE = do_GET

class ThreadingHTTPServer (SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer): pass

if __name__ == '__main__':
	from sys import argv
	if argv[1:] and argv[1] in ('-h', '--help'):
		print argv[0], '[port [allowed_client_name ...]]'
	else:
		if argv[2:]:
			allowed = []
			for name in argv[2:]:
				client = socket.gethostbyname(name)
				allowed.append(client)
			ProxyHandler.allowed_clients = allowed
			del argv[2:]
		loadExpressions()
		BaseHTTPServer.test(ProxyHandler, ThreadingHTTPServer)
