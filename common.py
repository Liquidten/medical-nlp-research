'''
Common
- For importing only
- Common operations and variables for interactive interpreter and scripts
- Recommended use: `from common import *`
- 17-06-18 - upgraded JSON ops to use jsonpickle
- 17-06-19 - added fix for handling numpy based data <https://github.com/jsonpickle/jsonpickle/issues/147>
'''


import pickle
import codecs
import sys
import re
import os
from random import shuffle
import math
import shutil
import json
import time
import pdb
#import jsonpickle
#import jsonpickle.ext.numpy as jsonpickle_numpy
#jsonpickle_numpy.register_handlers()
from zlib import adler32
from inspect import getmembers, getargvalues, currentframe
import requests
from threading import Timer
import random
import logging

import pexpect
from pexpect.replwrap import REPLWrapper
import yaml
import rpyc
import prettyparse
from dotenv import load_dotenv, find_dotenv, dotenv_values


baseDir = '/NLPShare/Alcohol/'
dataDir = baseDir + 'data/'
adeBaseDir = '/NLPShare/ADE/'
adeDataDir = '/NLPShare/ADE/data/'

ancNoteTypes = dataDir + 'anc_note_types.txt'
labNoteTypes = dataDir + 'lab_note_types.txt'
otherNoteTypes = dataDir + 'other_note_types.txt'
allNotes = dataDir + 'all_notes.json'
allDiags = dataDir + 'all_diags.json'
allNotesWithDiags = dataDir + 'all_notes_with_diags.json'
adeIrbNotes = adeBaseDir + 'irb_209962_note_08082017.txt'
adeIrbPtList = adeBaseDir + 'irb_209962_pt_list_08082017.txt'
adePtListCsv = adeBaseDir + 'PatientList_209962.csv'
adeAllNotes = adeDataDir + 'all_notes.json'
logFile = dataDir + 'logs.txt'
ripTest = '''>>> fp = 6
>>> fn = 10
>>> tp = 18
>>> tn = 70
>>> pre, rec, f1 = calcScores(tp, fp, fn, tn)
>>> pre
0.75
>>> rec
>>> f1'''
ripTest2 = '''>>> audits = []
>>> with open(dataDir + 'audit_mrns.txt') as fo:
...  audits = fo.read().split('\\n')
... 
>>> len(audits)
1510
>>> audits[0]
'MRN'
>>> audits[-1]
''
>>> audits.pop()
''
>>> audits.pop(0)
'MRN'
>>> len(audits)
1508'''
calls = 0
mimic_bin = '/NLPShare/Lib/Word2Vec/Models/mimic.bin'
dist = '/NLPShare/Lib/Word2Vec/word2vec/distance'

# 18-02-01 - setup logging
logger = logging.getLogger('lnlp')
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(logFile)
fh.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s (%(level)s): %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)


class UMLSClient():

    def __init__(self, api_key='', cache_path='', adb={}):
        self._using = ''
        self.cache = {}

        if api_key:
            self._using = 'api'
            self._setup_online(api_key, cache_path)

        elif adb:
            self._using = 'arango'
            self._setup_offline(adb, cache_path)
        return

    def _setup_online(self, api_key, cache_path):
        self.api_key = api_key
        self.auth_uri="https://utslogin.nlm.nih.gov"
        self.auth_endpoint = "/cas/v1/api-key"
        self.service="http://umlsks.nlm.nih.gov"
        if not cache_path: cache_path = os.environ['HOME'] + '/umls_cache.json'
        self.cache_path = cache_path
        self.cache = {} if not os.path.exists(cache_path) else loadJson(cache_path)
        self.access_cnt = 0
        self.tgt = None
        self.st = None
        self._error = None
        self._conn = False
        return

    def _setup_offline(self, adb, cache_path):
        self._umls_mrconso = adb['UMLS_MRCONSO']
        self._umls_mrsty = adb['UMLS_MRSTY']
        self._umls_cache = adb['UMLS_CACHE']
        from arango import ArangoClient as AC
        clt_args = ['host', 'port', 'username', 'password']
        self._a_clt = AC(**{k[4:].lower(): v for k, v in zip(adb.keys(), adb.values()) if k[4:].lower() in clt_args})
        self._umls_db = self._a_clt.database(adb['UMLS_ADB'])
        return

    def save_cache(self):
        if self._using == 'api': saveJson(self.cache, self.cache_path)
        return

    def gettgt(self):
        """Wrap actual call to allow cache only operation"""

        try:
            self._gettgt()
            writeLog('Connection to UMLS service initialized!')
            self._conn = True

        except Exception as e:
            self._error = e
            writeLog('Unable to connect to UMLS service: {}'.format(repr(e)))

    def _gettgt(self):
        params = {'apikey': self.api_key}
        h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", "User-Agent":"python" }
        r = requests.post(self.auth_uri+self.auth_endpoint,data=params,headers=h)
        #response = fromstring(r.text)
        tgt = re_findall('action=.+cas', r.text, 0)[8:]
        if not tgt: raise Exception('UMLS authentication failed')
        self.tgt = tgt
        return tgt

    def getst(self, tgt=''):
        if not tgt: tgt = self.tgt or self.gettgt()
        params = {'service': self.service}
        h = {"Content-type": "application/x-www-form-urlencoded", "Accept": "text/plain", "User-Agent":"python" }
        r = requests.post(tgt, data=params,headers=h)
        st = r.text
        self.st = st
        return st

    def query_umls(self, identifier, tgt=None, source=None, version='current'):
        # get info from UMLS
        if not self._conn: return {}
        uri = "https://uts-ws.nlm.nih.gov"
        if not tgt: tgt = self.tgt or self.gettgt()
        content_endpoint = '/rest/content/%s/CUI/%s' % (version, identifier) if not source else '/rest/content/%s/source/%s/%s' % (str(version), str(source), identifier)
        query = {'ticket': self.getst(tgt)}
        r = requests.get(uri+content_endpoint,params=query)
        r.encoding = 'utf-8'
        items  = json.loads(r.text)
        jsonData = items["result"]
        if not 'cuis' in self.cache: self.cache['cuis'] = {}
        self.cache['cuis'][identifier] = jsonData
        self.access_cnt += 1
        if self.access_cnt >= 15: self.save_cache(); self.access_cnt = 0
        return jsonData

    def find_cui(self, identifier):
        # seek a cui in cache
        if self._using == 'arango': return self.query_adb({'cui': identifier})
        if self._using == 'api' and not 'cuis' in self.cache or not identifier in self.cache['cuis']:
            return self.query_umls(identifier)
        return self.cache['cuis'][identifier]

    def query_adb(self, query, fields=['cui', 'str']):
        """Return record for a given query in an Arango UMLS database.
        """
        adb_elements = ['_key', '_id', '_rev']
        umls_cache = self._umls_db.collection(self._umls_cache)
        res = umls_cache.find(query).batch()
        if res:
            return {
                k: v
                for k, v in zip(res[0].keys(), res[0].values())
                if not k in adb_elements
            }
        mrconso = self._umls_db.collection(self._umls_mrconso)
        #mrsty = self._umls_db.collection(self._umls_mrsty)

        try:
            res = mrconso.find(query).batch()

        except Exception as e:
            print(repr(e))
            if 'HTTP 404' in repr(e):
                print('Check to ensure collection exists and is spelt properly')
            pdb.post_mortem()
        res = [r for r in res if r['ispref'] == 'Y']
        if not res: return {}
        res = {
            'name' if k == 'str' else k: v
            for k, v in zip(res[0].keys(), res[0].values())
            if k in fields
        }
        umls_cache.insert(res)
        return res

class Distance():
    # Word2Vec distance wrapper by default

    def __init__(self, cmd='', prompt=None, rx=None):
        if not cmd: cmd = '{} {}'.format(dist, mimic_bin)
        if not prompt: prompt = 'Enter word or sentence (EXIT to break): '

        if isinstance(cmd, str):
            self._repl = REPLWrapper(cmd, prompt, None)

        else:
            self._repl = cmd
        self.nodes = []
        self.rx = rx if rx else '\s+(?P<Word>\S+)\t+.*'

    def find(self, words, num, max_levels=1, unique=True, level=0):
        first = self._repl.run_command(words, None).split('\n')[5:num+5]
        first = [re.match(self.rx, line).group('Word') for line in first]

        if level < max_levels:
            rest = [Distance(self._repl).find(first[idx], num, max_levels, level=level+1) for idx in range(len(first))]
            first.extend(rest)
            first = [word for sublist in first if isinstance(sublist, list) for word in sublist]
            if unique: first = list(set(first))
        return first

class CrunchClient():

    def __init__(self, user='', procs=1):
        self.user = user  # default user name
        self.servers = {}  # can connect to multiple servers
        self.connections = {}  # single use to trigger forking
        self.task_list = []
        self.working_list = []
        self.done_list = []
        self.work_load = 0
        self.complete = False
        self.procs = procs  # processes per CPU
        self._aborting = False
        self.disabled = False
        self._timers = 0
        self._checking = False
        self._max_processes = 0

    def reset_lists(self):
        self.task_list = self.working_list = self.done_list = []
        return True

    def get_results(self):
        return self.done_list

    def add_server(self, host='localhost', port=9999, name='', user=''):
        '''Add a connectable server to the server list.
        Takes server host, port, a name and a valid user on the system.
        Returns a string describing the result.'''
        if self.disabled: return
        cpus = 0
        try:
            c = rpyc.connect(host, port)
            cpus = c.root.cpu_count()
            #c.close()

        except ConnectionRefusedError:
            msg = 'No service found on host: "{}", port: {}'.format(host, port)
            print(msg)
            return msg

        except Exception as e:
            msg = 'Something broke: {}'.format(repr(e))
            print(msg)
            return msg
        name = name or host + port
        user = user or self.user or 'none'
        self.servers[name] = {'host': host, 'port': port, 'user': user, 'cpus': cpus}
        msg = 'Successfully created server "{}" on host: "{}", port: {}'.format(name, host, port)
        msg += ' with user "{}".'.format(user) if user else ' with default user'
        self._max_processes += int(cpus * self.procs)

        for idx in range(int(cpus * self.procs)):
            # initialize connections based on CPUs and process load
            conn = '{}:{}:{}'.format(name, idx, user)
            self.connections[conn] = [None, 'dead']
            #res = self.make_link(conn)
        return msg

    def make_link(self, c_name):
        '''create a connection'''
        if self.disabled: return
        status = 'dead'
        try:
            s_name = c_name.split(':')[0]  # server name
            host = self.servers[s_name]['host']
            port = self.servers[s_name]['port']
            conn = rpyc.connect(host, port)
            self.connections[c_name] = [conn, 'ready']
            status = 'ready'

        except Exception as e:
            msg = 'Something broke: {}'.format(repr(e))
            self.connections[c_name] = [None, 'dead']
            status = 'dead'
            print(msg)
            return False
        time.sleep(1.5)  # allow the new connection to settle
        return status

    def add_task(self, func, args=[], kwargs={}):
        if self.disabled: return
        self.task_list.append([func, args, kwargs])
        self.done_list.append(None)
        #self._timers += 1
        self.complete = False
        if not self.work_load: Timer(5, self._check_tasks).start()
        self.work_load += 1
        return True

    def _check_tasks(self, timer_called=True):
        if self.disabled or self.complete or self._checking: return
        self._checking = True
        if timer_called: self._timers -= 1
        if self._timers > 0: return  # other timer(s) running
        #pdb.set_trace()

        for idx, task in enumerate(self.working_list):
            # record and clean-up any completed tasks
            if not task['result'].ready: continue
            if self.done_list[task['idx']] is not None: raise ValueError('This should be empty!')
            self.done_list[task['idx']] = task['result'].value
            #self.task_list[task['idx']] = None
            #self.connections[task['conn']].close()
            print(task['result'].value)
            self.connections[task['conn']][1] = 'ready'
            print('Completed task #%d on %s' % (task['idx'], task['conn']))
            self.working_list.pop(idx)
            self.work_load -= 1

        for conn in self.connections:
            # find unused connection and...
            if self.connections[conn][1] is 'busy':
                try:
                    # make sure the connection is still live
                    self.connections[conn][0].ping()
                    continue

                except Exception:
                    print('Something\'s wrong with ', conn)
                    res = self.make_link(conn)
                    if not res == 'ready': continue  # currently unusable
            user = conn.split(':')[2]
            if self._aborting: continue
            if self.connections[conn][1] is 'dead': self.make_link(conn)
            if not self.connections[conn][1] is 'ready': continue

            for idx, pending in enumerate(self.task_list):
                # ... run the next pending task
                if len(self.working_list) >= self._max_processes or self.connections[conn][1] is 'busy': break
                if not pending: continue
                try:
                    c_run = self.connections[conn][0].root.run
                    async_run = rpyc.async(c_run)
                    task = {}
                    task['result'] = async_run(user, pending[0], pending[1], pending[2])
                    task['idx'] = idx
                    task['conn'] = conn
                    #task['detail'] = pending
                    self.working_list.append(task)
                    self.task_list[idx] = None
                    self.connections[conn][1] = 'busy'
                    print('Started task #%d on %s' % (task['idx'], task['conn']))

                except Exception as e:
                    print('Something broke while trying to run: %s' % repr(e))
                    self.connections[conn][1] = 'dead'
        Timer(5, self._check_tasks).start()
        print('Working on %d processes with a load of %d...' % (len(self.working_list), self.work_load))
        if not self.work_load: self.complete = True
        self._timers += 1
        self._checking = False

    def total_cpus(self, name='local'):
        # use to get both CPUs and check availavility
        cpus = 0

        try:
            cpus = self.servers[name][0].cpu_count()

        except EOFError as e:
            msg = 'Connection seems broken: {}'.format(str(e))
            print(msg)
            return 0
        return cpus

    def wait(self, secs=0, interval=5):
        # blocks until complete, set time elapsed or interrupted
        if self.disabled: return
        e_time = 0
        print('Entered wait phase.')

        try:
            while not self.complete:
                time.sleep(interval)
                e_time += interval
                if secs > 0 and e_time >= secs: break
                Timer(5, self._check_tasks).start()

        except Exception as e:
            print('Exception encountered while waiting: ' + repr(e))
            pdb.set_trace()
            return False
        return True

    def abort(self, wait=True):
        self._aborting = True
        if wait: return True

        for conn in self.connection:
            # close and kill
            self.connection[conn].close()
            self.connection[conn] = None
        return True

class CSVWrapper():

    def __init__(self, src, args=[], kwargs={}):
        if not exists(src): return
        self.f_name = src
        self.val_list = []

        with open(src) as fo:
            _reader = csv.reader(fo, *args, **kwargs)
            self.delim = ','  # TODO: get from reader

            for row in _reader:
                self.val_list.append(row)

    def make_dict(self, key_idx=0):
        self.val_dict = {}

        for row in self.val_list:
            key = row.pop(key_idx)
            self.val_dict[key] = row
        return self.val_dict

    def save(self):

        with open(self.f_name, 'w') as fo:
            pass
        return True

class Group(dict):

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        [setattr(self, k, kwargs[k]) for k in kwargs]
        return

    def __call__(self, key, val={'': [None]}):
        neut = {'': [None]}
        if not key : return ValueError('No key given')
        if val == neut:
            if not hasattr(self, key):
                return ValueError('Key not found')

            else:
                val = dict.__getitem__(self, key)
                return val

            if isinstance(key, dict):
                [setattr(self, k, key[k]) for k in key]
                return True
        dict.__setitem__(self, key, val)
        setattr(self, key, val)
        return True

    def __getitem__(self, key):
        val = self.__call__(key)
        return val

    def __setitem__(self, key, val):
        self.__call__(key, val)
        return

    def to_dict(self):
        """Return a regular dict"""
        d = {k: v for k, v in zip(self.keys(), self.values())}
        return d

class MemoryClient():
    '''Holds objects for other processes
    Todo: Make dict interface'''

    def __init__(self, name, host='localhost', port=9998):
        self._host = host
        self._port = port
        self._name = name
        self.__conn = None
        self.__connect()

    def __call__(self, key, data=None):
        self.__connect()
        if self.__conn: return self.__conn.root.blob(self._name, key, data)
        return Exception('Something broke during the call.')

    def __connect(self):
        if self.__conn: return

        try:
            c = rpyc.connect(self._host, self._port)
            self.__conn = c

        except Exception as e:
            msg = 'Something broke: {}'.format(repr(e))
            print(msg)
            return msg

### For pickling operations

def loadPickle(fName):
    obj = None

    with open(fName, 'rb') as fo:
        obj = pickle.load(fo)
    return obj

def savePickle(obj, fName):

    with open(fName, 'wb') as fo:
        pickle.dump(obj, fo)
    return

### For command line operations

def readStdin():
    lines = []

    for line in sys.stdin.readlines():
        lines.append(line.strip())
    return lines

def writeStdout(lines, ofile=None):
    temp = None

    if not ofile == None:
        try:
            temp = sys.stdout
            sys.stdout = open(ofile, 'a')

        except Exception as e:
            print('Failed to use ' + ofile)

    for line in lines:
        sys.stdout.write(line)

    if not temp == None and not temp == sys.stdout:
        sys.stdout.close()
        sys.stdout = temp
    return

def writeStderr(lines):

    for line in lines:
        sys.stderr.write(line)
    return

def getCmdLine():
    return sys.argv

### For data search & manipulation

def pyCut(lines, delimiter=',', columns=['0'], errors='ignore'):
    '''
    Generator to cut lines based on column #s (1-based) and possibly rearrange order
    - Should work with strings and arrays
    - NB: may be broken by dynamically generated lists
    '''
    nline = None
    err = 0

    for line in lines:
        line = line.split(delimiter)

        try:

            for col in columns:

                if not ':' in col:
                    # simple base form
                    nline.append(line[int(col)])

                else:
                    splice = col.split(':')
                    nline.append(line[int(splice[0]) : int(splice[1])])
                    #raise Exception('Range splices not yet supported!')
            yield nline + '\n'  # should create a generator that returns individual lines

        except Exception as e:
            writeStderr(e.args)
            err += 1

def pyGrep(lines, pattern):
    pattern = re.compile(pattern)

    for line in lines:

        if not re.search(pattern, line) == None:
            yield line

def getFileList(path, recurse=False):

    for dirname, dirnames, filenames in os.walk(path):

        if not recurse:
            # TODO: move out of 'for'
            dirList = os.listdir(path)
            if not path[-1] == '/': path += '/'

            for fName in dirList:
                yield path + fName
            return
        # print path to all subdirectories first.
        #for subdirname in dirnames:
        #    print(os.path.join(dirname, subdirname))

        # print path to all filenames.
        for filename in filenames:
            print(os.path.join(dirname, filename))

def gridSearchAOR(p=None, construct='', results=[], doEval=False, funcList=[], resume=[]):
    # params is a list of dicts/lists of lists
    params = [{'methods': ['method1', 'method2']}, ['pos1arg1', 'pos1arg2'], ['pos2arg1', 'pos2arg2'],
              {'key1': ['a1-1', 'a1-2']}, {'key2': ['a2-1', 'a2-2']}] if p == None else p[:]

    if not params == []:
        # grab and process the first param
        param = params.pop(0)
        last_idx = 0

        if type(param) == type({}):
            # process dictionary
            kName = ''
            for key in param:
                kName = key

            for idx in range(len(param[kName])):
                result = None
                if idx < last_idx: idx = last_idx
                item = param[kName][idx]

                try:
                    if kName == 'methods':
                        # processing the methods
                        result = gridSearchAOR(params, item + '(', results, resume=resume)  # start constructing method call

                    else:
                        # processing named args

                        if type(item) == type('') and not item == 'False' and not item == 'True' and not item == 'None':
                            item = '\"%s\"' % item
                        result = gridSearchAOR(params, '%s %s=%s,' % (construct, kName, item), results, resume=resume)
                        #if result[-1] == ')' and not construct == '': return result

                    if construct == '' and not result == []:
                        # back on top
                        #results.append(result)
                        pass

                except KeyboardInterrupt:
                    raise

        elif type(param) == type([]):
            # process list, ie positional args

            for idx in range(len(param)):
                # processing positional args
                if idx < last_idx: idx = last_idx
                item = param[idx]

                try:
                    if type(item) == type('') and not item == 'False' and not item == 'True' and not item == 'None':
                        item = '\"%s\"' % item
                    result = gridSearchAOR(params, '%s %s,' % (construct, item), results, resume=resume)

                except KeyboardInterrupt:
                    raise

    else:
        # no more params to process
        result = construct[:-1] + ' )' # complete method call
        if not result in results: results.append(result)
        return result
    if not construct == '': return  # Only continue if we're at the top level
    if not doEval: return results

    for idx in range(len(results)):
        # evaluate them all
        print('Evaluating call #%d %s...' % (idx, results[idx]))

        try:
            results[idx] = [results[idx], eval(results[idx])]

        except Exception as e:
            print('Error in #%d, %s' % (idx, str(e.args)))
            results[idx] = [results[idx], str(e.args)]

    print('Grid search complete! Returning results.')
    return results

def getExpNum(tracker=''):
    # get and increment the experiement number on each call for autonaming
    tracking = loadJson(tracker) if os.path.exists(tracker) else {'exp_num': 0}
    expNum = tracking['exp_num']
    tracking['exp_num'] += 1
    saveJson(tracking, tracker)
    return expNum

def fileList(path, fullpath=False):
    nameList = os.listdir(path)

    if fullpath:

        for idx in range(len(nameList)):
            nameList[idx] = path + '/' + nameList[idx]
    return nameList

def get_file_list(path, fullpath=False):
    return fileList(path, fullpath)

def splitDir(srcDir, destDir, percentOut, random=True, test=False):
    content = fileList(srcDir, True)
    numOut = len(content) - math.ceil(percentOut / 100 * len(content))  # take from end
    if not os.path.exists(srcDir): raise Exception('Source dir %s doesn\'t exist!' % srcDir)
    ensureDirs(destDir)

    if random:
        shuffle(content)

    if test:
        print('Old dir: %s\n\nnew dir: %s' % (content[:numOut], content[numOut:]))

    else:

        for path in content[numOut:]:
            shutil.move(path, destDir)
    print('Moved %d of %d files to %s' % (len(content) - numOut, len(content), destDir))
    #return content[:numOut], content[numOut:]

def calcScores(tp=0, fp=0, fn=0, tn=0):
    '''Takes tp, fp, fn and tn, or a dict with them
       Returns p, r, f1'''
    if isinstance(tp, dict):
        fp = tp['fp']
        fn = tp['fn']
        tn = tp['tn']
        tp = tp['tp']
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    f1 = 2 * ((precision * recall) / (precision + recall))
    return precision, recall, f1

def loadJson(fName):
    obj = None

    with open(fName) as fo:
        obj = json.load(fo)
        #obj = jsonpickle.decode(fo.read())
    return obj

def saveJson(obj, fName):

    with open(fName, 'w') as fo:
        json.dump(obj, fo)
        #fo.write(jsonpickle.encode(obj))
    return

def pesh(cmd, out=sys.stdout, shell='/bin/bash', debug=False):
    # takes command as a string or list
    result = ''
    if debug: print('DBG: cmd = \'%s\' & out = %s' % (cmd, str(out)))

    if out == False and type(out) == type(False):
        # run and forget; need multiprocess to prevent pexpect killing or blocking
        if debug: print('DBG: running in separate process')
        proc = Process(target=launch, args=([cmd, shell])).start()
        return 1
    child = pexpect.spawnu(shell, ['-c', cmd] if isinstance(cmd, str) else cmd)

    if not out == sys.stdout:
        result = out
        out = open(TMP_FILE, 'w')
    child.logfile = out
    child.expect([pexpect.EOF, pexpect.TIMEOUT])  # command complete and exited
    #sleep(5)

    if not result == False and child.isalive():
        # block until the child exits (normal behavior)
        # otherwise, don't wait for a return
        print('Waiting for child process...')
        child.wait()

    if out == sys.stdout:
        # output went to standard out or not waiting for child to end
        return 1
    out.close()
    lines = []

    with open(TMP_FILE) as fo:

        for line in fo:
            lines.append(line.strip())
    if debug: print('DBG: lines = %s' % str(lines))

    if type(result) == type(0):
        # get line specified by number, or last line
        if result < len(lines): return str(lines[result])

    if result == 'all':
        # all lines
        return lines

    if type(result) == type(''):
        # get line specified by pattern

        for line in lines:

            if result in line:  # TODO: make into regex match
                return line
        return None
    #raise Exception('Something went wrong in pesh')

def launch(cmd, shell='/bin/bash'):
    child = pexpect.spawnu(shell, ['-c', cmd] if type(cmd) == type('') else cmd, timeout=None)
    child.expect([pexpect.EOF, pexpect.TIMEOUT])

def currentTime():
    # 17-06-09
    return time.strftime("%Y-%m-%d_%H:%M:%S", time.localtime())

def current_time():
    return currentTime()

def writeLog(msg, print_=True, log=None):
    # 17-06-11
    global logFile
    if log: logFile = log

    with open(logFile, 'a') as lf:
        lf.write(msg + '\n')
    #logger.info(msg)
    if print_: print(msg)
    return

def ensureDirs(*paths):
    # 17-06-11

    for path in paths:

        if isinstance(path, list):

            for sub in path:
                if not os.path.exists(sub): os.makedirs(sub)

        else:
            if not os.path.exists(path): os.makedirs(path)
    return paths

def ensure_dirs(*paths):
    # 17-12-06 - snake_case name shim
    return ensureDirs(*paths)

def loadText(fName):
    # 17-06-12

    with open(fName) as f:
        return f.read()

def saveText(text, fName):
    # 17-06-12

    with open(fName, 'w') as f:
        return f.write(text)

def runInterpDump(text):
    # 17-06-15
    # run commands directly copied from the Python interpreter
    multiline = False
    cache = []
    results = []
    #pdb.set_trace()

    for line in text.split('\n'):
        results.append(line)
        if re.match('^>>>\s+$', line): continue

        if line.startswith('>>> ') and line.endswith(':'):
            # start a block
            multiline = True
            cache = [line[4:]]
            continue

        if re.match('^\.{3,3}\s+$', line):
            # end a block
            multiline = False

            try:
                exec('\n'.join(cache), globals())

            except Exception as e:
                results.append(str(e))
            cache = []
            continue

        if line.startswith('... '):
            cache.append(line[4:])
            continue

        if line.startswith('>>> '):
            # regular 1 line commands
            line = line[4:]
            result = None

            try:
                # handle as expression
                result = str(eval(line, globals()))

            except SyntaxError:
                # handle as statement(s)
                exec(line, globals())
                result = None  # change to captured

            except Exception as e:
                # it's all broken
                result = str(e)
            results.append(result)
    return '\n'.join(r for r in results if isinstance(r, str))

def hash_sum(data):
    # 17-07-07
    return adler32(bytes(data, 'utf-8'))

def members(itm, print_=True):
    # 17-07-08
    mems = []
    for mem in getmembers(itm):
        if print_: print(mem)
        mems.append(mem)
    return mems

def slack_post(text='', channel='', botName='', botIcon=''):
    # 17-07-31
    text = 'Testing webhook' if text == '' else text
    botName = 'lnlp-bot' if botName == '' else botName
    channel = '#general' if channel == '' else channel
    botIcon = ':robot_face:' if botIcon == '' else botIcon
    payload = {'text': text, 'username': botName, 'channel': channel}

    if '://' in botIcon:
        payload['icon_url'] = botIcon

    else:
        payload['icon_emoji'] = botIcon
    payload = json.dumps(payload)
    print('Posting to Slack...')
    cmd = 'curl -X POST --data-urlencode \'payload=%s\' %s' % (payload, os.environ['LNLP_SLACK_HOOK'])
    pesh(cmd)
    return

def commit_me(tracker='', name='', path=''):
    # 17-08-01 Commit after each change
    if not name: name = sys.argv[0]
    if not name: return  # prob running pure interactive session
    if name.startswith('./'): name = name[2:]
    if not path: path = '%s/%s' % (os.getcwd(), name)
    last_dir = os.getcwd()
    os.chdir(os.path.dirname(path))
    p_hash = hash_sum(path)
    f_hash = hash_sum(loadText(path))
    t_name = 'commit_me_%s' % (p_hash)
    tracking = loadJson(tracker) if os.path.exists(tracker) else {t_name: f_hash}
    if t_name in tracking and tracking[t_name] == f_hash: return
    c_msg = '%s: auto-commit %s with hash %s' % (currentTime(), path, f_hash)
    pesh('git add %s' % (name))
    pesh('git commit -m "%s"' % (c_msg))
    os.chdir(last_dir)
    tracking[t_name] = f_hash
    saveJson(tracking, tracker)
    return f_hash

def get_path_from_func(func):
    # 17-08-01
    return func.__globals__['__file__']

def path_name_prefix(pref, path):
    # 17-08-01
    return '%s/%s%s' % (os.path.dirname(path), pref, path.split('/')[-1])

def cc_to_sc(name):
    # 17-08-12 - convert camelCase to snake_case
    s = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s).lower()

def str_to_dict(s, main_sep='&', map_sep='=', use_re=False):
    # 17-08-01 - initial
    # -12 - update to support regex
    # -09-11 - default if no value for a key
    final = {}
    items = s.split(main_sep) if not use_re else re.split(main_sep, s)

    for item in items:
        item = item.split(map_sep) if not use_re else re.split(map_sep, item)
        final[item[0]] = item[1] if len(item) == 2 else None
    return final

def re_findall(pat, s_, idx=None):
    # 17-08-15 - re.findall replacement that does what's expected
    res = []
    pos = 0

    while True:
        match = re.search(pat, s_)
        if not match: break
        rnge = match.span()
        res.append(s_[rnge[0]:rnge[1]])
        pos = rnge[1]
        s_ = s_[pos:]
    if len(res) >= 1 and isinstance(idx, int): return res[idx]
    return res

def re_index(match, s_):
    # 17-08-17 -

    if isinstance(s_, dict):
        for pat in s_:
            if not re.match(pat, match): continue
            return s_[pat]

    if isinstance(s_, list):
        for idx in range(len(s_)):
            if not re.match(s_[idx], match): continue
            return s_[idx]
    return None

def get_env(key):
    return os.environ[key]

def load_yaml(src):

    with open(src) as fo:
        return yaml.load(fo)

def save_yaml(obj, f_name=None):
    # saves to a file or returns string
    text = yaml.dump(obj)
    if not f_name: return text

    with open(f_name, 'w') as fo:
        fo.write(text)
    return True

def confusion_matrix_(data, pred_f, true_f, table=False):
    '''Takes data as an iterable and 2 functions
       - pred_f returns a boolean prediction
       - act_f returns the boolean actual
       - table (opt) determines if results should be returned in a dict or table
       Returns matrix values'''
    tp = tn = fp = fn = 0

    for e in data:
        if pred_f(e) and true_f(e): tp += 1
        if pred_f(e) and not true_f(e): fp += 1
        if not pred_f(e) and true_f(e): fn += 1
        if not (pred_f(e) or true_f(e)): tn += 1
    return {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn} if not table else [[tp, fp][fn, tn]]

def is_primitive(item, primitives=None):
    # 17-12-06
    if not primitives: primitives = [int, float, bool, str]
    return type(item) in primities

def make_one_hot(seq, classes=[0, 1], hot=1, rest=0):
    '''Do one-hot conversion
    - seq must be a list or compatible'''
    if not isinstance(seq, list): seq = list(seq)
    new_seq = [[rest] * len(classes) for _ in range(len(seq))]
    for pos, cls in enumerate(classes):
        for idx in range(len(seq)):
            if seq[idx] == cls:
                new_seq[idx][pos] = hot
    return new_seq

def get_args(usage):
    """Parse command line args and return parsed args"""
    args = prettyparse.create_parser(usage).parse_args()
    return args

def get_log(name, level='WARNING', format=''):
    if not format: format = '%(asctime)s: %(message)s'
    logging.basicConfig(format=format, level=getattr(logging, level.upper(), 'WARNING'))
    return logging.getLogger(name)

def gen_ip_report(names, preds, y_test, probs):
    """Generate individual predictions report"""
    report = 'mrn,pred,gold,prob'
    body = '\n'.join(['{},{},{},{}'.format(name, pred, y, prob)
                        for name, pred, y, prob in zip(names, preds, y_test, probs)])
    report += '\n' + body
    return report

def gen_ip_report_2(ip_detail):
    """Generate individual predictions report with multiple folds"""
    num_folds = len(ip_detail)
    report = 'mrn,gold,{}'.format(','.join(['pred_{},prob_{}'.format(idx, idx) for idx in range(num_folds)]))
    #entry_template = 'MRN,GLD,{}'.format(''.join(['FLD{}'.format(idx) for idx in num_folds]))
    patients = {}

    for idx, fold in enumerate(ip_detail):

        for patient in zip(*fold):

            if not patient[0] in patients:
                patients[patient[0]] = [patient[2]] + (['-'] * 2 * num_folds)  # mrn and gold

            patients[patient[0]][idx * 2 + 1] = patient[1]  # pred
            patients[patient[0]][idx * 2 + 2] = patient[3]  # prob
    body = '\n'.join([','.join([mrn] + [str(itm) for itm in patients[mrn]]) for mrn in patients])
    report += '\n' + body
    return report

def mirror_dir_split(src_dir, dest_dir, mirror_dir, test=False):
    """Split a folder based on another folder"""
    if not os.path.exists(src_dir): raise OSError(f'Source dir {src_dir} does not exist!')
    if not os.path.exists(mirror_dir): raise OSError(f'Mirror dir {src_dir} does not exist!')
    content = get_file_list(src_dir, True)
    mirror = get_file_list(mirror_dir, True)
    ensure_dirs(dest_dir)
    cnt = 0

    for path in mirror:
        candidate = os.path.join(src_dir, path.split(os.path.sep)[-1])

        if candidate in content:
            if not test: shutil.move(candidate, dest_dir)
            cnt += 1
    print(f'Moved {cnt} of {len(content)} files from {src_dir} to {dest_dir}')

def merge_dirs(dest_dir, *src_dirs, test=False):
    """Merge multiple folders into a single destination"""
    if isinstance(src_dirs, str): src_dirs = [src_dirs]
    if False in [isinstance(d, str) and os.path.exists(d) for d in src_dirs]:
        raise OSError('One or more of the specified source folders does not exist')
    ensure_dirs(dest_dir)
    cnt = 0

    for src_dir in src_dirs:

        for src in get_file_list(src_dir, True):
            dest = os.path.join(dest_dir, src.split(os.path.sep)[-1])

            with open(src) as s, open(dest, 'a') as d:
                if not os.path.exists(dest): cnt += 1
                d.write(s.read())
    print(f'Merged {cnt} files from {", ".join(src_dirs)} into {dest_dir}')
    return

def get_separated_values_file_iterator(path, sep=',', headers=[], filter_='^[.*]', encoding='utf-8'):
    """Return a generic iterator for processing large structured text files.

    Text file types include CSV, TSV, RRF, etc which are structured with one record per line
    and fields separated by a separator charactor(s). This iterator is mainly for handling
    very large files which probably won't hold in memory all at once very well.

    Arguments:
    path (str) -- path to text file.

    Keyword arguments:
    sep (str) -- values separator (default: ",").
    headers (list|str) -- used as fields (columns) headers (optional, default: []).
        length must match the length of each record (row) in the file; if not the record will not
          be processed.
    filter_ (str) -- regex filter that excludes matched records (default: "^[.*]").
    encoding (str) -- encoding used to open the file (default: "utf-8").

    Returns:
    an iterator that yields:
        a record as a list if headers not given
        a record with associated header as a dict otherwise
    """
    if not os.path.exists(path): raise OSError(f'"{path}" does not exist')
    if not isinstance(sep, str): raise ValueError('Values separator "sep" must be a string')
    if isinstance(headers, str) and sep in headers: headers = headers.split(sep)
    if not isinstance(headers, list):
        raise ValueError('"headers" must be a list or string with valid separators')
    if not isinstance(filter_, str): raise ValueError('"filter_" must be a string')

    with codecs.open(path, encoding=encoding) as fo:

        for line in fo:
            if re.match(filter_, line): continue
            line = line.strip()
            if line.endswith(sep): line = line[:-len(sep)]
            record = line.split(sep)

            if headers:
                if len(headers) is not len(record): continue
                record = dict(zip(headers, record))
            yield record

def get_umls_client(mode='api', dotenv=True, extra={}):
    """Return a UMLS client setup for online API or offline ArangoDB access."""
    if not extra and dotenv: extra = dotenv_values(find_dotenv())
    clt = None

    try:
        if mode == 'api': clt = UMLSClient(**extra)
        if mode == 'arango': clt =  UMLSClient(adb=extra)

    except Exception as e:
        print(repr(e))
        pdb.post_mortem()
    return clt


if __name__ == '__main__':
    print('This is a library module not meant to be run directly!')
commit_me(dataDir + 'tracking.json', 'common.py')
