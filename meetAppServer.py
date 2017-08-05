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
import threading
import datetime


###### Main server #########

##### STATIC_VARIABLES #####

PORT = 9404
DEBUG = True
SHOW_RAW_MSGS = False
NO_OF_CONNECTIONS = 0
PONG_TIMEOUT = 30       # seconds
DB_NAME = "meetapp_server"
DB_USER = "root"
DB_PASSWD = "linux"

#### Global variables ####

activeUsers = []
onlineClientsNumbers = []
offlineClientNumbers = []
connectionAlreadyExists = False
replaceCount = 0


### Database connection ###
try:
    con = mdb.connect("localhost",DB_USER,DB_PASSWD)
    db = con.cursor()
except:
    sys.exit("Error connecting MySQL database")


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
        db.execute("create table registration_table(_id BIGINT NOT NULL AUTO_INCREMENT, registered_number VARCHAR(20) NOT NULL, PRIMARY KEY(_id))")
        db.execute("create table store_and_fwd_table(_id BIGINT NOT NULL AUTO_INCREMENT, arrive_timestamp VARCHAR(20), expire_timestamp VARCHAR(20), send_to VARCHAR(15), sent_from VARCHAR(15), message VARCHAR(4000), PRIMARY KEY(_id))")
        con.commit()

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
        db.execute("use meetapp_server")
        db.execute("select _id from registration_table where registered_number=%s" % number)
        data = db.fetchall()
        if not data:
            db.execute("insert into registration_table(registered_number) values ('%s')" % number)
            con.commit()
            if DEBUG:
                print "New user registered: %s" % number
        else:
            if DEBUG:
                print "User already exists: %s" % number

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
            db.execute("select registered_number from registration_table where registered_number='%s'" % checkThisNumber)
            data = db.fetchone()
            if data == None:
                pass
            else:
                existingCount += 1
                syncedNumbers.update({str(existingCount):str(data[0])})
        resp = {'from':'server','existingCount':str(existingCount),'type':'syncResponse','syncedNumbers':syncedNumbers}
        if DEBUG:
            print resp
        socket.write_message(resp)

def checkIfOnline(number):
    sendPingTo(number)
    startWaitForPongThread(number)

def onPong(resp,socket):
    if(resp['type'] == "pong"):
        number = phoneNumberFormatter(str(resp['from']))
        for thread in threading.enumerate():
            if thread.name == number:
                thread.run = False
                sendToPonger(number,socket)

def sendToPonger(number,socket):
    db.execute("use meetapp_server")
    db.execute("select _id, message from store_and_fwd_table where send_to='%s'" % number)
    results = db.fetchall()
    for i in range(0,len(results)):
        _id = results[i][0]
        msg = results[i][1]
        socket.write_message(msg)
        db.execute("delete from store_and_fwd_table where _id=%d" % _id)
    con.commit()
    if DEBUG:
        print "Sending stored messages to ponger: %s" % number


def sendPingTo(number):
    lenghtOfActiveUsers = len(activeUsers)
    for i in range(0,lenghtOfActiveUsers):
        if(activeUsers[i].keys()[0] == str(number)):
            tempDict = activeUsers[i]
            socket = tempDict[str(number)]
            pingFrame = {'from':'server','type':'ping'}
            socket.write_message(json.dumps(pingFrame))
            if DEBUG:
                print "Sent ping to: " + str(number)

def registerAsOffline(number):
    if number in offlineClientNumbers:
        pass
    else:
        offlineClientNumbers.append(str(number))

def startWaitForPongThread(number):
    number = str(number)
    t = threading.Thread(target=waitingThread, name=number, args=(number,))
    t.start()

def waitingThread(number):
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
        send_to = phoneNumberFormatter(str(req['to']))
        msg = str(req)
        now = str(datetime.datetime.now().strftime("%d/%m/%y %I:%M:%S"))
        expiry = str(getMsgExpiryDate(datetime.datetime.now()))
        db.execute("use meetapp_server")
        db.execute("insert into store_and_fwd_table (arrive_timestamp, expire_timestamp, send_to, sent_from, message) values ('%s', '%s', '%s', '%s', \"%s\")" % (now, expiry, send_to, sent_from, msg))
        con.commit()
        checkIfOnline(send_to)


##### WebSocketHandler class #####

class WSHandler(tornado.websocket.WebSocketHandler):

    def open(self):
        global NO_OF_CONNECTIONS
        NO_OF_CONNECTIONS += 1
        if DEBUG:
            print "New connection: " + self.request.remote_ip
            print "No of connections: " + str(NO_OF_CONNECTIONS)

    def on_message(self,message):
        global activeUsers

        msg = ast.literal_eval(message)

        onOpen(msg,self)
        onRegisterUserRequest(msg)
        onContactSyncRequest(msg,self)
        onPong(msg,self)
        onMeetingRequest(msg)

        if SHOW_RAW_MSGS:
            print message

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


#### Helper functions ####

def phoneNumberFormatter(number):
    number = str(number)
    number = number.replace(" ","")
    number = number.replace(")","")
    number = number.replace("(","")
    number = number.replace("-","")
    number = number.replace("_","")
    return number

def getMsgExpiryDate(datetime):
    try:
        datetime = datetime.replace(month=(datetime.month+1))
    except:
        datetime = datetime.replace(year=datetime.year+1,month=1)
    return datetime.strftime("%d/%m/%y %H:%M:%S")

# TODO: Implement pong receive and do things on pong repsponse -- stop timer/timeout login on pong receive to determine online/offline state


#### Main program ####
app = tornado.web.Application([(r'/',WSHandler),])

if __name__ == "__main__":
    try:
        os.system("clear")
        print "\n\r[ MeetApp ]"
        print "Started at: " + time.strftime("%d/%m/%y  %I:%M:%S %p")
        print "IP Address: " + str(os.popen("hostname -I").read())
        initDB()
        try:
            http_server = tornado.httpserver.HTTPServer(app)
            http_server.listen(PORT)
            myIP = socket.gethostbyname(socket.gethostname())
            print "Starting tornado socket server at %s:%s" % (str(os.popen("hostname -I").read().replace('\n','')),PORT)
            tornado.ioloop.IOLoop.instance().start()
        except:
            sys.exit("\noops! Tornado exception occured!")
    except(KeyboardInterrupt):
        sys.exit("KeyboardInterrupt.. exiting..")
