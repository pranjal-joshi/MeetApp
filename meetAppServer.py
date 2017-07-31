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


###### Main server #########

PORT = 9404

DEBUG = True
NO_OF_CONNECTIONS = 0

activeUsers = []
connectionAlreadyExists = False
replaceCount = 0

class WSHandler(tornado.websocket.WebSocketHandler):

    def open(self):
        if DEBUG:
            global NO_OF_CONNECTIONS
            print "New connection: " + self.request.remote_ip
            NO_OF_CONNECTIONS += 1
            print "No of connections: " + str(NO_OF_CONNECTIONS)

    def on_message(self,message):
        global activeUsers
        if DEBUG:
            print message
            msg = ast.literal_eval(message)
            if msg['type'] == "onOpen":
                lenghtOfActiveUsers = len(activeUsers)
                connectionAlreadyExists = False
                for i in range(0,lenghtOfActiveUsers):
                    print activeUsers[i].keys()[0]
                    print msg['from']
                    if(activeUsers[i].keys()[0] == msg['from']):
                        tempDict = activeUsers[i]
                        tempDict[msg['from']] = self
                        activeUsers[i] = tempDict
                        print "Replacing exisiting socket connection."
                        connectionAlreadyExists = True
                        break
                if(not connectionAlreadyExists):
                    tempDict = {}
                    tempDict[msg['from']] = self
                    activeUsers.append(tempDict)
                    print activeUsers
                    print "New connection added."


    def on_error(self,error):
        print "Websocket error: " + str(error)
        self.close()

    def on_close(self):
        global NO_OF_CONNECTIONS
        print "Connection closed by " + self.request.remote_ip
        if NO_OF_CONNECTIONS > 0:
            NO_OF_CONNECTIONS -= 1
            print "No of connections: " + str(NO_OF_CONNECTIONS)


app = tornado.web.Application([(r'/',WSHandler),])

if __name__ == "__main__":
    try:
        os.system("clear")
        print "\n\r[ MeetApp ]"
        print "Started at: " + time.strftime("%d/%m/%y  %I:%M:%S %p")
        print "IP Address: " + str(os.popen("hostname -I").read())
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
