#!/usr/bin/python
# -*- coding: utf-8  -*-
#
# By: André Costa, Wikimedia Sverige
# License: MIT
#
'''
Script for harvesting metadata from Wikimedia Commons for the use in Europeana
'''

import codecs #might not be needed afterwards
import ujson

def testing():
    #load two example files to simulate api response
    f=codecs.open('./mockJson/content.json','r','utf-8')
    content = ujson.loads(f.read())
    f.close()
    f=codecs.open('./mockJson/imageinfo.json','r','utf-8')
    imageinfo = ujson.loads(f.read())
    f.close()
    
    #container for all the info, using pageid as its key
    data = {}
    for k,v in imageinfo['query']['pages'].iteritems():
        if not parseImageInfo(v, data):
            #if false is returned then something bad happened
            print 'something bad happened'
    
    #add data from description
    
    outputXML(data)

def parseImageInfo(imageJson, data):
    '''parse a single page in imageInfo reply from the API'''
    
    #outer info
    pageId = imageJson['pageid']
    title = imageJson['title'][len('File:'):]
    
    #swithch to inner info
    imageJson = imageJson['imageinfo'][0]
    
    #check that it is really an image
    if not imageJson['mime'].split('/')[0] == 'image':
        #replace by something useful
        print u'%s is not an image but a %s' %(title, imageJson['mime'].split('/')[0])
        return False
    #check if image already in dictionary
    if pageId in data.keys():
        #replace by something useful
        print u'pageId (%s) already in data: old:%s new:%s' %(pageId, data[pageId]['title'], title)
        return False
    
    #Prepare data object
    data[pageId] = {'title':title, 'medialink':imageJson['url'], 'descurl':imageJson['descriptionurl'], 'mediatype':'IMAGE'}
    
    user    = imageJson['url'] #as backup for later field
    
    #successfully reached the end
    return True

def parseContent(contentJson, data):
    '''parse a single revisions/content reply from the API
       with the aim of identifying the institution link along with additional descriptions'''
   
   #check if the pageID exists in data.keys()
   #if not then page has been updated since
    

def outputXML(data):
    '''output the data in the desired format'''
    #for testing
    for k,v in data.iteritems():
        print u'%s' %k
        for kk, vv in v.iteritems():
            print u'\t%s: %s' %(kk,vv)
    
#EoF
