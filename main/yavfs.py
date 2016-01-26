#!/usr/bin/python
# -*- coding: utf-8 -*-

import errno
import os
import stat
import sys
import urllib2

import fuse
from fuse import Fuse
import StringIO as sio
from StringIO import StringIO

import vk_api

fuse.fuse_python_api = (0, 2)

YAVFS_NULL = -1
YAVFS_NOTFOUND = -2

YAVFS_FILE = 0
YAVFS_DIR = 1
YAVFS_DYNDIR = 2
YAVFS_DYNFILE = 3

YAVFS_VKNULL=1

YAVFS_SIZE_FOLEN = -1

USER_FIELDS = 'photo_id,verified,sex,bdate,city,country,home_town,has_photo,photo_50,photo_100,photo_200_orig,photo_200,photo_400_orig,photo_max,photo_max_orig,online,lists,domain,has_mobile,contacts,site,education,universities,schools,status,last_seen,followers_count,common_count,occupation,nickname,relatives,relation,personal,connections,exports,wall_comments,activities,interests,music,movies,tv,books,games,about,quotes,can_post,can_see_all_posts,can_see_audio,can_write_private_message,can_send_friend_request,is_favorite,is_hidden_from_feed,timezone,screen_name,maiden_name,crop_photo,is_friend,friend_status,career,military,blacklisted,blacklisted_by_me'

AUTH_FILE = os.path.expanduser('~/.yavfs.auth')

#Класс с конфигурацией.
class ConfigYAVFS:
	def __init__(self):
		self.app = 4897361 #My app
		if os.path.exists(AUTH_FILE):
			authfile = open(AUTH_FILE)
			self.login = authfile.readline().strip()
			self.passwd = authfile.readline().strip()
		else:
			print u'Для работы YAVFS необходимо указать свои данные от аккаунта vk.com'
			print u'В противном случае программа не сможет получить доступ к профилю'
			self.login = raw_input('Логин> ').strip()
			self.passwd = raw_input('Пароль> ').strip()
			authfile = open(AUTH_FILE, 'w')
			authfile.write('%s\n%s\n'%(self.login, self.passwd))

#Класс определения файла/папки
class NodeYAVFS:
	def __init__(self, ftype, fname='', size = YAVFS_SIZE_FOLEN, **kwargs):
		self.ftype = ftype
		self.vktype = YAVFS_VKNULL
		self.vkid = 0
		self.dirlist = []
		self.dyndir = lambda: None
		self.dynfile = lambda: None
		self.fileobj = StringIO('')
		self.size = size
		for param, value in kwargs.iteritems():
			setattr(self, param, value)
		if self.size == YAVFS_SIZE_FOLEN:
			self.size = self.fileobj.len

#Класс, с помощью которого выпоняется поиск записи в хеше по пути
class PathYAVFS:
	def __init__(self):
		pass
	def find_path(self, path, dct):
		splitted = os.path.split(path)
		entry = YAVFS_NULL
		try: entry = dct[path]
		except: return YAVFS_NOTFOUND
		return entry

#Вспомогательный класс - структура stat.
class StatYAVFS(fuse.Stat):
	def __init__(self):
		fuse.Stat.__init__(self)
		self.st_mode = 0
		self.st_ino = 0
		self.st_dev = 0
		self.st_nlink = 0
		self.st_uid = 0
		self.st_gid = 0
		self.st_size = 0
		self.st_atime = 0
		self.st_mtime = 0
		self.st_ctime = 0

class DynamicYAVFS:
	def __init__(self, prt):
		self.prt = prt
	def user_friends_dyndir(self, node):
		uid = node.uid
		path = node.path
		realpath = node.realpath
		dirlist = []
		self.prt.user_friends[uid] = self.prt.vk.friends.get(user_id=uid, fields=USER_FIELDS)['items']
		for user in self.prt.user_friends[uid]:
			uname = user['first_name']+' '+user['last_name']
#			uname = str(user['id'])
			print 'Proccessing: ', uname
			self.prt.user_put_prof_to_fs(node.realpath, uname, uid=user['id'], userobj = user)
			dirlist += [uname]
		return dirlist
	def open_remote_file(self, node):
		node.fileobj = remote_open(node.remote_url)
		node.size = node.fileobj.info()['content-length']
		return node.fileobj, node.size

def remote_open(url):
	hndl = urllib2.urlopen(url)
	if not (hndl.info().seekable): hndl.seek = lambda x: None
	return hndl

 #Основной класс виртуальной файловой системы
class YAVFS(Fuse):
	def __init__(self, *args, **kwargs):
		Fuse.__init__(self, *args, **kwargs)
		self.pathfinder = PathYAVFS()
		
		self.config = ConfigYAVFS()		

#		try:
		if(1):
			self.vk_sess = vk_api.VkApi(self.config.login, self.config.passwd, app_id = self.config.app)
			self.vk_sess.authorization()
			self.vk = self.vk_sess.get_api()
			self.users = {}
			self.user_friends = {}
			self.users['self'] = self.vk.users.get(fields=USER_FIELDS)[0]
			print "VK Auth ok."
			pass
#		except:
		else:
			sys.exit(-1)

		self.dyn = DynamicYAVFS(self)
		
		self.filedict = {
			'/': NodeYAVFS(YAVFS_DIR, '/', 
				dirlist = [
					'users'
				]
			),
			'/users': NodeYAVFS(YAVFS_DIR, '/users')
		}
		self.user_put_prof_to_fs('/users', 'self', uid='self')

	def populate_wall_dir(self, basepath, path, uid=None, wallobj=None):
		if not wallobj:
			wallobj = self.vk.wall.get(owner_id=uid, extended=1, fields=USER_FIELDS)
		realpath = basepath+'/'+path
		posts = wallobj['items']
		for user in wallobj['profiles']:
			self.users[user['id']] = user	
		wallstr = u''
		for post in posts:
			poster = self.users[post['from_id']]
			wallstr += post['post_type']+u'>>> '+(poster['first_name']+u' '+poster['last_name'])+u'\n'
			if len(post['text']):
				wallstr += post['text']+u'\n'
			wallstr += (u'_'*40)+u'\n'
		self.filedict[realpath] = NodeYAVFS(YAVFS_FILE, path,
			fileobj = StringIO(wallstr.encode('utf8')),
			path = path,
			realpath = realpath
		)
		self.filedict[basepath].dirlist += [path]

	def populate_albums_dir(self, basepath, path, uid=None, albumsobj=None):
		if not albumsobj:
			albumsobj = self.vk.photos.getAlbums(owner_id=uid, need_system=1)
		realpath = basepath+'/'+path
		dirlist = []
		for alb in albumsobj['items']:
			self.filedict[realpath+'/'+alb['title']] = NodeYAVFS(YAVFS_DYNDIR, path+'/'+alb['title'],
				dyndir = self.get_album,
				album = alb,
				path = alb['title'],
				realpath = realpath+'/'+alb['title']
			)
			dirlist += [alb['title']]
		self.filedict[realpath] = NodeYAVFS(YAVFS_DIR, path,
			dirlist = dirlist,
			path = path,
			realpath = realpath
		)
		self.filedict[basepath].dirlist += [path]

	def get_album(self, node):
		def findmax(photo):
			if 'photo_2560' in photo: return photo['photo_2560']
			if 'photo_1280' in photo: return photo['photo_1280']
			if 'photo_807' in photo: return photo['photo_807']
			if 'photo_604' in photo: return photo['photo_604']
			if 'photo_130' in photo: return photo['photo_130']
			if 'photo_75' in photo: return photo['photo_75']
		photos = self.vk.photos.get(owner_id=node.album['owner_id'], album_id=node.album['id'])['items']
		dirlist = []
		for photo in photos:
			name = str(photo['id'])+'.jpg'
			dirlist += [name]
			self.filedict[node.realpath+'/'+name] = NodeYAVFS(YAVFS_DYNFILE, name,
				dynfile = self.dyn.open_remote_file,
				remote_url = findmax(photo),
				path = node.path,
				realpath = node.realpath
			)
		node.dirlist = dirlist
		return dirlist

	def user_put_prof_to_fs(self, basepath, path, uid=None, userobj=None):
		if not userobj:
			if uid in self.users:
				userobj = self.users[uid]
				uid = userobj['id']
			else:
				userobj = self.vk.users.get(uid, fields=USER_FIELDS)[0]
		realpath = basepath+'/'+path
		self.filedict[realpath] = NodeYAVFS(YAVFS_DIR, path,
			dirlist = [
				'friends',
				'profile.txt',
				'photo.jpg',
			],
			uid = uid,
			path = path,
			realpath = realpath
		)
		
		profile_txt = StringIO()
		profile_txt.write((
			u'Профиль %s:\n' % (userobj['first_name']+' '+userobj['last_name'])
		).encode('utf8'))
		profile_txt.write((
			u'Тут типа пусто\n'
		).encode('utf8'))
		profile_txt.seek(0)
		self.filedict[realpath+'/profile.txt'] = NodeYAVFS(YAVFS_FILE, path+'/profile.txt',
			fileobj = profile_txt,
			uid = uid,
			path = path+'/profile.txt',
			realpath = realpath+'/profile.txt'
		)
		
		self.filedict[realpath+'/photo.jpg'] = NodeYAVFS(YAVFS_DYNFILE, path+'/photo.jpg',
			dynfile = self.dyn.open_remote_file,
			uid = uid,
			path = path+'/photo.jpg',
			realpath = realpath+'/photo.jpg',
			remote_url = userobj['photo_max']
		)
		
		self.filedict[realpath+'/friends'] = NodeYAVFS(YAVFS_DYNDIR, path+'/friends', 
			dyndir = self.dyn.user_friends_dyndir,
			uid = uid,
			path = path+'/friends',
			realpath = realpath+'/friends'
		)

		try: self.populate_wall_dir(realpath, 'wall.txt', uid=uid)
		except: pass
		try:self.populate_albums_dir(realpath, 'albums', uid=uid)
		except: pass
		self.filedict[basepath].dirlist += [path]

	def getattr(self, path, *a, **kw):
		path = path.decode('utf-8')
		st = StatYAVFS()
		elem = self.pathfinder.find_path(path, self.filedict)
		if elem == YAVFS_NOTFOUND: return -errno.ENOENT
		if elem.ftype == YAVFS_DYNFILE:
			st.st_mode = stat.S_IFREG | 0444
			elem.fileobj, size = elem.dynfile(elem)
			st.st_nlink = 1
			st.st_size = int(size)
#			st.st_size = 0
		if elem.ftype == YAVFS_FILE:
			st.st_mode = stat.S_IFREG | 0444
			st.st_nlink = 1
			st.st_size = elem.size
		elif elem.ftype in (YAVFS_DIR, YAVFS_DYNDIR):
			st.st_mode = stat.S_IFDIR | 0444
			st.st_nlink = 2
		print st.st_size
		return st
	def readdir(self, path, *a, **kw):
		path = path.decode('utf-8')
		elem = self.pathfinder.find_path(path, self.filedict)
		if elem == YAVFS_NOTFOUND: return -errno.ENOENT
		if not (elem.ftype in (YAVFS_DIR, YAVFS_DYNDIR) ):
			pass
		dirlist = ['.', '..']
		if elem.ftype == YAVFS_DIR:
			dirlist += elem.dirlist
		elif elem.ftype == YAVFS_DYNDIR:
			dirlist += elem.dyndir(elem)
		entr = []
		for dirname in dirlist:
			print 'Adding: '+dirname
			entr += [fuse.Direntry(dirname.encode('utf-8'))]
		return entr
	def open(self, path, mode, *a, **kw):
		path = path.decode('utf-8')
		elem = self.pathfinder.find_path(path, self.filedict)
		if elem.ftype == YAVFS_DYNFILE:
			elem.fileobj, size = elem.dynfile(elem)
		if elem == YAVFS_NOTFOUND: return -errno.ENOENT
		filehandle = elem.fileobj
		return filehandle
	def read(self, path, size, offset=0, filehandle=None):
		path = path.decode('utf-8')
		elem = self.pathfinder.find_path(path, self.filedict)
		if elem == YAVFS_NOTFOUND: return -errno.ENOENT
		filehandle.seek(offset)
		return filehandle.read(size)


usage='YAVFS ' + fuse.Fuse.fusage
fs = YAVFS(version="%prog " + fuse.__version__,usage=usage,dash_s_do='setsingle')
fs.parse(errex=1)
fs.main()
