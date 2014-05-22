#!/usr/bin/python
# -*- coding: utf-8  -*-
#
# By: André Costa, Wikimedia Sverige
# License: MIT
#
'''
Script for harvesting metadata from Wikimedia Commons for the use in Europeana
'''

import codecs #might not be needed after testing
import ujson
import operator #only used by categoryStatistics

def testing():
    #based on some given category we retrieve all of the image infos
    imageinfo = getImageInfos('testcat')
    if not imageinfo:
        #if false/None is returned then information could not be retrieved
        print 'something bad happened'
        exit(1)
    
    #container for all the info, using pageid as its key
    data = {}
    for k,v in imageinfo['query']['pages'].iteritems():
        if not parseImageInfo(v, data):
            #if false is returned then something bad happened
            print 'something bad happened'
    
    #add data from description
    unsupported = []
    for k in data.keys():
        #get content for that pageID (can only retrieve one at a time)
        content = getContent(k)
        if not content: #if fails then remove object from data
            print 'content could not be retrieved for PageId %d (%s), removing' %(k, data[k]['title'])
            unsupported.append(k)
        elif not parseContent(k, content, data):
            #if false is returned then object was not supported
            print '%s did not contain a supported information tempalte' %data[k]['title']
            unsupported.append(k)
    
    #remove problematic entries
    for k in unsupported:
        del data[k]
    
    outputXML(data)
    print(u'-------------------------------')
    outputCatStat(data)

def getImageInfos(maincat):
    '''set up for testing only'''
    f=codecs.open('./mockJson/imageinfo2.json','r','utf-8')
    imageinfo = ujson.loads(f.read())
    f.close()
    return imageinfo
    
def getContent(pageId):
    '''set up for testing only'''
    if pageId == 27970534:
        f=codecs.open('./mockJson/content.json','r','utf-8')
        content = ujson.loads(f.read())
        f.close()
        return content['parse']
    return None

def parseImageInfo(imageJson, data):
    '''parse a single page in imageInfo reply from the API'''
    #Issues:
    ## Assumes Information template. Need to test with e.g artwork template and see what happens if there is no template
    ### For artwork. Title might be different, also artist/photographer.
    ## Does not deal with multiple licenses (see /w/api.php?action=query&prop=imageinfo&format=json&iiprop=commonmetadata%7Cextmetadata&iilimit=1&titles=File%3AKalmar%20cathedral%20Kalmar%20Sweden%20001.JPG)
    ## Is more content validation needed?
    commonsMetadataExtension = 1.2 # the version of the extention for which the script was designed
    pdMark = u'https://creativecommons.org/publicdomain/mark/1.0/'
    
    #outer info
    pageId = imageJson['pageid']
    title = imageJson['title'][len('File:'):].strip()
    
    #swithch to inner info
    imageJson = imageJson['imageinfo'][0]
    
    #checks prior to continuing
    if not imageJson['extmetadata']['CommonsMetadataExtension']['value'] == commonsMetadataExtension: #no guarantee that metadata is treated correctly if any other version
        #replace by something useful - would probably want to stop whole process
        print u'This uses a different version of the commonsMetadataExtension than the one the script was designed for. Expected: %s; Found: %s' %(commonsMetadataExtension, imageJson['extmetadata']['CommonsMetadataExtension']['value'])
        return False
    if not imageJson['mime'].split('/')[0].strip() == 'image': #check that it is really an image
        #replace by something useful - would probably only want to skip this image (or deal with it)
        print u'%s is not an image but a %s' %(title, imageJson['mime'].split('/')[0].strip())
        return False
    if pageId in data.keys(): #check if image already in dictionary
        #replace by something useful - probably means something larger went wrong
        print u'pageId (%s) already in data: old:%s new:%s' %(pageId, data[pageId]['title'], title)
        return False
    
    #Prepare data object, not sent directly to data[pageId] in case errors are discovered downstream
    obj = {'title':title, 'medialink':imageJson['url'].strip(), 'identifier':imageJson['descriptionurl'].strip(), 'mediatype':'IMAGE'}
    
    #listing potentially interesting fields
    user        = imageJson['user'] #as backup for later field
    obj['imageDescription'] = imageJson['extmetadata']['ImageDescription']['value'].strip() if u'ImageDescription' in imageJson['extmetadata'].keys() else None
    objectName  = imageJson['extmetadata']['ObjectName']['value'].strip() if u'ObjectName' in imageJson['extmetadata'].keys() else None
    datePlain   = imageJson['extmetadata']['DateTime']['value'].strip() if u'DateTime' in imageJson['extmetadata'].keys() else None
    dateDig     = imageJson['extmetadata']['DateTimeDigitized']['value'].strip() if u'DateTimeDigitized' in imageJson['extmetadata'].keys() else None
    dateOrig    = imageJson['extmetadata']['DateTimeOriginal']['value'].strip() if u'DateTimeOriginal' in imageJson['extmetadata'].keys() else None
    dateMeta    = imageJson['extmetadata']['DateTimeMetadata']['value'].strip() if u'DateTimeMetadata' in imageJson['extmetadata'].keys() else None
    licenseShortName = imageJson['extmetadata']['LicenseShortName']['value'].strip() if u'LicenseShortName' in imageJson['extmetadata'].keys() else None
    licenseurl  = imageJson['extmetadata']['LicenseUrl']['value'].strip() if u'LicenseUrl' in imageJson['extmetadata'].keys() else None
    artist      = imageJson['extmetadata']['Artist']['value'].strip() if u'Artist' in imageJson['extmetadata'].keys() else None
    credit      = imageJson['extmetadata']['Credit']['value'].strip() if u'Credit' in imageJson['extmetadata'].keys() else None #does this ever say something other than own work?
    #usageTerms = imageJson['extmetadata']['UsageTerms']['value'].strip() if u'UsageTerms' in imageJson['extmetadata'].keys() else None #does this ever say something other than license?
    copyrighted = imageJson['extmetadata']['Copyrighted']['value'].strip() if u'Copyrighted' in imageJson['extmetadata'].keys() else None #if PD
    
    #Post processing:
    ## comapare user with artist
    obj['uploader'] = None #Only contains a value if not included in artist
    if artist:
        obj['photographer'] = artist
        if not user in artist:
            obj['uploader'] = user
    elif user: #if only uploader is given
        obj['photographer'] = None
        obj['uploader'] = user
    else: #no indication of creator
        print u'%s did not have any information about the creator' %title
        return False
    
    ## Deal with licenses
    if licenseurl:
        if licenseurl.startswith(u'http://creativecommons.org/licenses/'):
            obj[u'copyright'] = licenseurl
        else:
            #Possibly add more triage here
            print u'%s did not have a CC-license URL and is not public Domain: %s (%s)' %(title, licenseurl, licenseShortName)
            return False
    else:
        if copyrighted == u'False':
            obj[u'copyright'] = pdMark
        else:
            #Possibly add more triage here
            print u'%s did not have a license URL and is not public Domain: %s' %(title, licenseShortName)
            return False
    
    ## isolate date giving preference to dateOrig
    if dateOrig: #the date as described in the description
        #format (timestamp is optional): <time class="dtstart" datetime="2013-08-26">26 August  2013</time>, 09:51:00
        if dateOrig.startswith(u'<time class="dtstart" datetime='):
            date = dateOrig.split('"')[3]
            if len(dateOrig.split('>,'))==2:
                date += dateOrig.split('>,')[1]
            obj['created'] = date
        elif u'<time' in dateOrig: #weird
            #Possibly add more triage here
            print u'%s did not have a recognised datestamp: %s' %(title, dateOrig)
            return False
        else: #just plain text
            print u'%s has plain text date: %s'%(title, dateOrig)
            obj['created'] = dateOrig
    elif dateDig and dateDig != u'0000:00:00 00:00:00':
        obj['created'] = dateDig
    elif datePlain and datePlain != u'0000:00:00 00:00:00':
        obj['created'] = datePlain
    elif dateMeta and dateMeta != u'0000:00:00 00:00:00':
        obj['created'] = dateMeta
    else:
        obj['created'] = u''

    ## check credit
    if credit and credit != u'<span class="int-own-work">Own work</span>':
        obj['credit'] = credit
    else:
        obj['credit'] = None
    
    ##If a proper objectName exists then overwrite title
    if objectName:
        obj['title'] = objectName
    
    #successfully reached the end
    data[pageId] = obj
    return True

def parseContent(pageId, contentJson, data):
    '''parse a single parse reply from the API
       with the aim of identifying the institution links, non-maintanance categories and used templates.
       adds to data: categories (list), sourcelinks (list)
       returns: Boolean on whether the image desciption contains one of the supported templates
       '''
    #supported info templates - based on what is suppported by parseImageInfo
    infoTemplate = [u'Template:Information']
    
    #these should be externalised
    ##Format template name:tuple of url starts
    idTemplates = {u'Template:BBR':(u'http://kulturarvsdata.se/raa/bbr/html/',u'http://kulturarvsdata.se/raa/bbra/html/',u'http://kulturarvsdata.se/raa/bbrb/html/'), 
                   u'Template:Fornminne':(u'http://kulturarvsdata.se/raa/fmi/html/',), 
                   u'Template:K-Fartyg':(u'http://www.sjohistoriska.se/sv/Kusten-runt/Fartyg--batar/K-markning-av-fartyg/K-markta-fartyg/')
                  }
    
    #structure up info as simple lists
    templates = []
    for t in contentJson['templates']:
        if 'exists' in t.keys(): templates.append(t['*'])
    data[pageId][u'categories'] = []
    for c in contentJson['categories']:
        if not 'hidden' in c.keys(): data[pageId][u'categories'].append(c['*'].replace('_',' '))
    extLinks = contentJson['externallinks'] #not really needed
    
    #Checking that the information structure is supported
    supported = False
    for t in infoTemplate:
        if t in templates:
            supported = True
    
    #Isolate the source templates and identify the source links
    data[pageId][u'sourcelinks'] = []
    for k, v in idTemplates.iteritems():
        if k in templates:
            for e in extLinks:
                if e.startswith(v):
                    data[pageId][u'sourcelinks'].append(e)
    
    #successfully reached the end
    return supported

def outputXML(data):
    '''output the data in the desired format'''
    #for testing
    for k,v in data.iteritems():
        print u'%s' %k
        for kk, vv in v.iteritems():
            print u'\t%s: %s' %(kk,vv)

def outputCatStat(data):
    '''output the category statistics in the desired format'''
    
    allCats = {}
    for k,v in data.iteritems():
        for c in v['categories']:
            if c in allCats.keys():
                allCats[c] += 1
            else:
                allCats[c] = 1
    
    sorted_allCats = sortedDict(allCats)
    #for testing
    for k in sorted_allCats:
        print u'%d: %s' %(k[1], k[0])

def sortedDict(ddict):
    '''turns a dict into a sorted list'''
    sorted_ddict = sorted(ddict.iteritems(), key=operator.itemgetter(1), reverse=True)
    return sorted_ddict
#EoF
