#!/usr/bin/python

'''
 * Copyright (c) 2017.
 * Author: Pranjal P. Joshi
 * Application: MeetApp
 * All rights reserved.
 '''

import tornado.httpserver
import tornado.websocket
import tornado.ioloop
import tornado.web
import socket
import os
import json
import time
import sys
import ast
import MySQLdb as mdb
import pymysql.cursors
import threading
import datetime
import base64
from Crypto.Cipher import AES
from pyfcm import FCMNotification


###### Main server #########

##### STATIC_VARIABLES #####

PORT = 80
DEBUG = True
USE_PYMYSQL = False
PUSH_ENABLE = True
SHOW_RAW_MSGS = True
NO_OF_CONNECTIONS = 0
PONG_TIMEOUT = 10       # seconds
CONNECTION_CLOSE_TIMEOUT = 20 # Minutes
DB_NAME = "meetapp_server"
DB_USER = "root"
DB_PASSWD = "linux"
DB_NAME = "meetapp_server"
ANDROID_PACKAGE_NAME = 'com.cyberfox.meetapp'
FCM_KEY = "AAAAR9TOyxc:APA91bHqHw0U9vYdtdU-dOWijZR1lHSZHvIse42udNxWNgPc3syNg3im-fVpRBJE3qgCQq4vgVgwQr4LFugL33Ia4s8YddEyMYo7KDibOuoxl8LehlCHg40okxnIeIuD7ltfXlxZava1"

#### Global variables ####

activeUsers = []
onlineClientsNumbers = []
offlineClientNumbers = []
connectionAlreadyExists = False
replaceCount = 0

### JSON Data ###

push_open = {"pushType":"open"}

### Core functions ###

def initDB():
    print "Initializing MySQL database."
    db.execute("show databases")
    a = db.fetchall()
    a = str(a)
    if(a.find(DB_NAME) > 0):
        print "---> Database found.\n"
    else:
        print "---> Database not found. creating...\n"
        db.execute("create database %s" % DB_NAME)
        db.execute("use %s" % DB_NAME)
        db.execute("create table registration_table(_id BIGINT NOT NULL AUTO_INCREMENT, registered_number VARCHAR(20) NOT NULL, fcm_token VARCHAR(500) NOT NULL, PRIMARY KEY(_id))")
        db.execute("create table store_and_fwd_table(_id BIGINT NOT NULL AUTO_INCREMENT, arrive_timestamp VARCHAR(20), expire_timestamp VARCHAR(20), send_to VARCHAR(15), sent_from VARCHAR(15), message VARCHAR(4000), PRIMARY KEY(_id))")
        #con.commit()

def onOpen(msg,socket):
    if msg['type'] == "onOpen":
        lenghtOfActiveUsers = len(activeUsers)
        connectionAlreadyExists = False
        for i in range(0,lenghtOfActiveUsers):
            if(activeUsers[i].keys()[0] == msg['from']):
                tempDict = activeUsers[i]
                tempDict[msg['from']] = socket
                activeUsers[i] = tempDict
                connectionAlreadyExists = True
                if DEBUG:
                    print "Replacing exisiting connection : %s" % phoneNumberFormatter(msg['from'])
                break
        if(not connectionAlreadyExists):
            tempDict = {}
            tempDict[msg['from']] = socket
            activeUsers.append(tempDict)
            if DEBUG:
                print "New connection created : %s" % phoneNumberFormatter(msg['from'])
        # THIS WILL SYNC DATA ON CONNECTION
        checkIfOnline(phoneNumberFormatter(msg['from']))

def onRegisterUserRequest(req):
    if req['type'] == "register":
        number = str(req['from'])
        number = phoneNumberFormatter(number)
        fcm_token = str(req['fcm_token'])
        db.execute("use meetapp_server")
        db.execute("select _id from registration_table where registered_number=%s" % number)
        data = db.fetchall()
        if not data:
            db.execute("insert into registration_table(registered_number, fcm_token) values ('%s','%s')" % (number, fcm_token))
            #con.commit()
            if DEBUG:
                print "New user registered: %s" % number
        else:
            if DEBUG:
                print "User already exists: %s" % number

def onDeleteAccountRequest(req):
    if(req['type'] == "deleteAccount"):
        number = phoneNumberFormatter(str(req['from']))
        fcm_token = str(req['fcm_token'])
        db.execute("use meetapp_server")
        db.execute("delete from registration_table where registered_number=%s" % number)
        #con.commit()

def onUpdateTokenRequest(req):
    if req['type'] == "tokenUpdate":
        number = str(req['from'])
        number = phoneNumberFormatter(number)
        token = str(req['fcm_token'])
        if number is None:
            number = "null"
        if token is None:
            token = "null"
        db.execute("use meetapp_server")
        db.execute("update registration_table set fcm_token='%s' where registered_number='%s'" % (token,number))
        #con.commit()
        if DEBUG:
            print "Token Updated. Token: " + token + " From: " + number

def onContactSyncRequest(req, socket):
    if req['type'] == "syncRequest":
        number = str(req['from'])
        total = int(req['total'])
        phonebook = req['phonebook']
        existingCount = 0
        syncedNumbers = {}
        db.execute("use meetapp_server")
        for i in range(1,total):
            checkThisNumber = str(phonebook[str(i)])
            checkThisNumber = phoneNumberFormatter(checkThisNumber)
            if not (checkThisNumber.find('*') > -1 or checkThisNumber.find('#') > -1):
                checkThisNumber = checkThisNumber[-10:]
                db.execute("select registered_number from registration_table where registered_number like '%{}%'".format(str(checkThisNumber)))
                data = db.fetchone()
                if data == None:
                    pass
                else:
                    if not USE_PYMYSQL:
                        if not data[0] in syncedNumbers.values():           # avoids duplicating of same number in json resp
                            if data[0] != number:                           # don't send syncer's number back to him --> NOT_TESTED <-- Change if ERROR---
                                existingCount += 1
                                syncedNumbers.update({str(existingCount):str(data[0])})
                    else:
                        if not data['registered_number'] in syncedNumbers.values():           # avoids duplicating of same number in json resp
                            if data['registered_number'] != number:                           # don't send syncer's number back to him --> NOT_TESTED <-- Change if ERROR---
                                existingCount += 1
                                syncedNumbers.update({str(existingCount):str(data['registered_number'])})

        resp = {'from':'server','existingCount':str(existingCount),'type':'syncResponse','syncedNumbers':syncedNumbers}
        resp = json.dumps(resp)
        if DEBUG:
            print resp
        socket.write_message(aes.encrypt(resp))

def onTripLocationUpdateReceive(req):
    if req['type'] == "locationUpdate":
        sender = getFullRegisteredNumberFrom(req['from'])
        send_to = getFullRegisteredNumberFrom(req['to'])
        req['from'] = "server"
        req['sender'] = sender
        req['type'] = "locationInfo"
        req = json.dumps(req)

        for i in range(0,len(activeUsers)):
            print activeUsers[i].keys()[0]
            if(activeUsers[i].keys()[0] == send_to):        # Dont do ping-pong.. send directly to receiver if online
                tempDict = activeUsers[i]
                socket = tempDict[send_to]
                try:
                    socket.write_message(aes.encrypt(req))
                except:
                    print "WARN: SOCKET_CLOSED"
                if DEBUG:
                    print "Sent locationUpdate to: ", send_to
                break
            else:
                pass

def onTripFinishRequest(req):
    if req['type'] == "tripFinish":
        sender = getFullRegisteredNumberFrom(req['from'])
        send_to = getFullRegisteredNumberFrom(req['to'])
        for i in range(0,len(activeUsers)):
            print activeUsers[i].keys()[0]
            if(activeUsers[i].keys()[0] == send_to):        # Dont do ping-pong.. send directly to receiver if online
                tempDict = activeUsers[i]
                socket = tempDict[send_to]
                req = json.dumps(req)
                try:
                    socket.write_message(aes.encrypt(req))
                except:
                    print "WARN: SOCKET_CLOSED"
                if DEBUG:
                    print "Sent locationUpdate to: ", send_to
                break
            else:
                pass

def checkIfOnline(number):
    e164Number = number
    number = str(number[-10:])
    sendPingTo(number)
    startWaitForPongThread(number, e164Number)

def onPong(resp,socket):
    if(resp['type'] == "pong"):
        number = phoneNumberFormatter(str(resp['from']))
        for thread in threading.enumerate():
            #if thread.name == number:
            if(number.find(thread.name) > -1):
                thread.run = False
                sendToPonger(number,socket)

def sendToPonger(number,socket):
    db.execute("use meetapp_server")
    db.execute("select _id, message from store_and_fwd_table where send_to='%s'" % number)
    results = db.fetchall()
    for i in range(0,len(results)):
        if USE_PYMYSQL:
            _id = results[i]['_id']
            msg = results[i]['msg']
        else:
            _id = results[i][0]
            msg = results[i][1]
        socket.write_message(aes.encrypt(msg))
        db.execute("delete from store_and_fwd_table where _id=%d" % _id)
    #con.commit()
    if DEBUG:
        print "Sending stored messages to ponger: %s" % number


def sendPingTo(number):
    lenghtOfActiveUsers = len(activeUsers)
    for i in range(0,lenghtOfActiveUsers):
        #if(activeUsers[i].keys()[0] == str(number)):
        if(activeUsers[i].keys()[0].find(str(number)) > -1):
            number = str(activeUsers[i].keys()[0])
            tempDict = activeUsers[i]
            socket = tempDict[str(number)]
            pingFrame = {'from':'server','type':'ping'}
            socket.write_message(aes.encrypt(json.dumps(pingFrame)))
            if DEBUG:
                print "Sent ping to: " + str(number)

def registerAsOffline(number):
    if number in offlineClientNumbers:
        pass
    else:
        offlineClientNumbers.append(str(number))

def startWaitForPongThread(number,e164number):
    number = str(number)
    e164number = str(e164number)
    t = threading.Thread(target=waitingThread, name=number, args=(number,e164number,))
    t.start()

def waitingThread(number,e164number):
    if DEBUG:
        print "Started waiting thread for pong from: %s" % number
    t = threading.current_thread()
    timeCnt = 0
    while(timeCnt < PONG_TIMEOUT and getattr(t,'run',True)):
        time.sleep(1)
        timeCnt += 1
    print "TIME_CNT: " + str(timeCnt) + "\tPONG_TIMEOUT: " + str(PONG_TIMEOUT)
    if(timeCnt == PONG_TIMEOUT):
        registerAsOffline(number)
        if PUSH_ENABLE:
            pushOpenToDevice(e164number)
        if DEBUG:
            print "Waiting thread expired - Adding to offline list: %s" % number
    else:
        if number in offlineClientNumbers:
            offlineClientNumbers.remove(number)
        if DEBUG:
            print "Pong recived from: %s" % number

def onMeetingRequest(req):
    if(req['type'] == 'immidiet' or req['type'] == 'scheduled'):
        sent_from = phoneNumberFormatter(str(req['from']))
        send_to = getFullRegisteredNumberFrom(phoneNumberFormatter(str(req['to'])))
        msg = str(req)
        now = str(datetime.datetime.now().strftime("%d/%m/%y %I:%M:%S"))
        expiry = str(getMsgExpiryDate(datetime.datetime.now()))
        db.execute("use meetapp_server")
        db.execute("insert into store_and_fwd_table (arrive_timestamp, expire_timestamp, send_to, sent_from, message) values ('%s', '%s', '%s', '%s', \"%s\")" % (now, expiry, send_to, sent_from, msg))
        #con.commit()
        checkIfOnline(send_to)

def onMeetingRequestResponse(resp):
    if(resp['type'] == 'meetingRequestResponse'):
        sent_from = phoneNumberFormatter(str(resp['from']))
        send_to = getFullRegisteredNumberFrom(phoneNumberFormatter(str(resp['to'])))
        msg  = str(resp)
        msg = ast.literal_eval(msg)
        msg['to'] = send_to
        msg = json.dumps(msg)
        msg = str(msg).replace("\"","\'")
        now = str(datetime.datetime.now().strftime("%d/%m/%y %I:%M:%S"))
        expiry = str(getMsgExpiryDate(datetime.datetime.now()))
        db.execute("use meetapp_server")
        db.execute("insert into store_and_fwd_table (arrive_timestamp, expire_timestamp, send_to, sent_from, message) values ('%s', '%s', '%s', '%s', \"%s\")" % (now, expiry, send_to, sent_from, msg))
        #con.commit()
        checkIfOnline(send_to)

def pushOpenToDevice(number):
    fcm_token = getFCMIdOfUser(number)
    result = fcm.notify_single_device(registration_id=fcm_token, data_message=push_open, restricted_package_name=ANDROID_PACKAGE_NAME)
    if DEBUG:
        print "Sent open push to: " + number


##### WebSocketHandler class #####

class WSHandler(tornado.websocket.WebSocketHandler):

    def open(self):
        global NO_OF_CONNECTIONS
        NO_OF_CONNECTIONS += 1
        self.timeout = tornado.ioloop.IOLoop.current().add_timeout(datetime.timedelta(minutes=CONNECTION_CLOSE_TIMEOUT), self.timeout_close)
        if DEBUG:
            print "New connection: " + self.request.remote_ip
            print "No of connections: " + str(NO_OF_CONNECTIONS)

    def on_message(self,message):
        global activeUsers

        msg = aes.decrypt(message)
        msg = ast.literal_eval(msg)

        onOpen(msg,self)
        onRegisterUserRequest(msg)
        onContactSyncRequest(msg,self)
        onPong(msg,self)
        onMeetingRequest(msg)
        onMeetingRequestResponse(msg)
        onTripLocationUpdateReceive(msg)
        onTripFinishRequest(msg)
        onUpdateTokenRequest(msg)
        onDeleteAccountRequest(msg)

        if SHOW_RAW_MSGS:
            print msg

    def on_error(self, error):
        print "Websocket error: " + str(error)
        self.close()

    def on_close(self):
        global NO_OF_CONNECTIONS
        if NO_OF_CONNECTIONS > 0:
            NO_OF_CONNECTIONS -= 1
            if DEBUG:
                print "No of connections: " + str(NO_OF_CONNECTIONS)
                print "Connection closed by " + self.request.remote_ip

    def timeout_close(self):
        global NO_OF_CONNECTIONS
        NO_OF_CONNECTIONS -= 1
        if DEBUG:
            print "Connection timeout - Closing -->: %s" % self.request.remote_ip
            print "No. of open connections: %d" % NO_OF_CONNECTIONS
        self.close()

class MeetAppSecurity:

	def __init__(self):
		self.key = "MeetAppSecretKey"
		self.iv = "alohomora2unlock"
		self.block_size = AES.block_size

	def pad(self,plain_text):
		number_of_bytes_to_pad = self.block_size - len(plain_text) % self.block_size
		ascii_string = chr(number_of_bytes_to_pad)
		padding_str = number_of_bytes_to_pad * ascii_string
		padded_plain_text =  plain_text + padding_str
		return padded_plain_text

	def unpad(self,s):
		return s[0:-ord(s[-1])]

	def encrypt(self,raw):
		cipher = AES.new(self.key, AES.MODE_CBC, self.iv)
		raw = self.pad(raw)
		e = cipher.encrypt(raw)
		return base64.b64encode(e)

	def decrypt(self,enc):
		decipher = AES.new(self.key, AES.MODE_CBC, self.iv)
		enc = base64.b64decode(enc)
		return self.unpad(decipher.decrypt(enc))


class MeetAppDatabase():
    con = None
    cursor = None

    def connect(self):
        self.con = mdb.connect(host="localhost",user=DB_USER,passwd=DB_PASSWD,db=DB_NAME)
        self.cursor = self.con.cursor()

    def execute(self, query):
        try:
            self.cursor.execute(query)
            self.con.commit()
        except (mdb.OperationalError, AttributeError):
            print "Database Exception -- Reconnecting..."
            self.connect()
            self.cursor.execute(query)
            self.con.commit()

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()



#### Helper functions ####

def phoneNumberFormatter(number):                   # Phone number string cleaner
    number = str(number)
    number = number.replace(" ","")
    number = number.replace(")","")
    number = number.replace("(","")
    number = number.replace("-","")
    number = number.replace("_","")
    return number

def getMsgExpiryDate(datetime):                     # store_and_fwd expiry calculator
    try:
        datetime = datetime.replace(month=(datetime.month+1))
    except:
        datetime = datetime.replace(year=datetime.year+1,month=1)
    return datetime.strftime("%d/%m/%y %H:%M:%S")

def reasignAutoIncrementOfStoreAndFwd():            # auto_increment maintainer
    db.execute("use meetapp_server")
    db.execute("alter table store_and_fwd_table drop _id")
    db.execute("alter table store_and_fwd_table auto_increment=1")
    db.execute("alter table store_and_fwd_table add _id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST")
    #con.commit()

def reasignAutoIncrementOfRegistrationTable():
    db.execute("use meetapp_server")
    db.execute("alter table registration_table drop _id")
    db.execute("alter table registration_table auto_increment=1")
    db.execute("alter table registration_table add _id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY FIRST")


def getFullRegisteredNumberFrom(number):            # Gives country_code + number for given only number
    number = str(number[-10:])
    db.execute("use meetapp_server")
    db.execute("select registered_number from registration_table where registered_number like '%{}%'".format(str(number)))
    result = db.fetchone()
    if USE_PYMYSQL:
        result = result['registered_number']
    if DEBUG:
        print "NUMBER: " + str(number)
        print "RESULT: " + str(result)
    try:
        return result[0]
    except:
        return None

def getFCMIdOfUser(number):
    number = phoneNumberFormatter(number)
    db.execute("use meetapp_server")
    db.execute("select fcm_token from registration_table where registered_number=%s" % number)
    result = db.fetchone()
    try:
        if USE_PYMYSQL:
            return result['fcm_token']
        else:
            return result[0]
    except Exception as q:
        raise q



#### Main program ####

### Database connection ###
try:
    if not USE_PYMYSQL:
        print "Using MySQLdb..."
        #con = mdb.connect("localhost",DB_USER,DB_PASSWD)
        #con.ping(True)
        #db = con.cursor()
        db = MeetAppDatabase()
    else:
        print "Using PyMySQL..."
        con = pymysql.connect(host="localhost",
                        user="root",
                        password="linux",
                        db="meetapp_server",
                        charset="utf8mb4",
                        cursorclass=pymysql.cursors.DictCursor)
        db = con.cursor()
except Exception as e:
    raise e
    sys.exit("Error connecting MySQL database")

### FCM Push service ###
try:
    fcm = FCMNotification(api_key=FCM_KEY)
except Exception as e:
    raise e
    Sys.exit("Failed to init FCM PUSH SERVICE")


app = tornado.web.Application([
        (r'/',WSHandler),
        ])

if __name__ == "__main__":
    try:
        os.system("clear")
        ### Security constructor ###
        aes = MeetAppSecurity()
        print "\n\r[ MeetApp ]"
        print "Started at: " + time.strftime("%d/%m/%y  %I:%M:%S %p")
        print "IP Address: " + str(os.popen("hostname -I").read())
        if USE_PYMYSQL:
            print "Using PyMySQL..."
        else:
            print "Using MySQLdb..."
        initDB()
        reasignAutoIncrementOfStoreAndFwd()
        reasignAutoIncrementOfRegistrationTable()
        try:
            http_server = tornado.httpserver.HTTPServer(app)
            http_server.listen(PORT)
            myIP = socket.gethostbyname(socket.gethostname())
            print "Starting tornado socket server at %s:%s\n" % (str(os.popen("hostname -I").read().replace('\n','')),PORT)
            tornado.ioloop.IOLoop.instance().start()
        except Exception as e:
            raise e
            sys.exit("\noops! Tornado exception occured!")
    except(KeyboardInterrupt):
        sys.exit("KeyboardInterrupt.. exiting..")
