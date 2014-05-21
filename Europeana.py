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
    f=codecs.open('./mockJson/imageinfo2.json','r','utf-8')
    imageinfo = ujson.loads(f.read())
    f.close()
    
    #hack for checking all categories (should be a calss variable)
    allcats = {}
    
    #container for all the info, using pageid as its key
    data = {}
    for k,v in imageinfo['query']['pages'].iteritems():
        if not parseImageInfo(v, data, allcats):
            #if false is returned then something bad happened
            print 'something bad happened'
    
    #add data from description
    for k,v in content['query']['pages'].iteritems():
        if not parseContent(v, data):
            #if false is returned then something bad happened
            print 'something bad happened'
    
    outputXML(data)
    print(u'-------------------------------')
    outputCatStat(allcats)

def parseImageInfo(imageJson, data, allcats):
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
    categories  = imageJson['extmetadata']['Categories']['value'].split('|') if u'Categories' in imageJson['extmetadata'].keys() else []
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
    
    ## filter out maintanance categories - and produce some sort of category dump/count
    obj[u'categories'] = filterCategories(categories, allcats)
    
    #successfully reached the end
    data[pageId] = obj
    return True

def filterCategories(catList, allcats):
    '''filter out maintanance categories and create basic category statistics'''
    #These should be created on initialisation from an external file
    catFilter = (u'Images by', u'Images from', u'Media with', u'Media created by', u'Uploaded via', u'CC-BY-', u'GFDL', u'CC-PD-'
                 u'Uploaded with', u'Featured pictures', u'Self-published work', u'License migration redundant', 
                 u'Protected buildings in Sweden with known IDs')
    
    newList= []
    
    for c in catList:
        filtered = False
        if c.startswith(catFilter): filtered = True
        #add to stats
        if c in allcats.keys():
            allcats[c]['count']+=1
        else:
            allcats[c] = {'count':1, 'filtered':filtered}
        
        #add to new list
        if not filtered:
            newList.append(c)
    
    return newList

def parseContent(contentJson, data):
    '''parse a single revisions/content reply from the API
       with the aim of identifying the institution link along with additional descriptions'''
    pageId = contentJson['pageid']
    
    #check if the pageID exists in data.keys()
    if not pageId in data.keys():
        #Possibly add more triage here
        print u'The content pageId for %s was not found amongst the imageInfo pageIds. Either the page was updated inbetween or the object was skipped due to some error' %contentJson['title']
        return False
    
    #swithch to inner info
    contentJson = contentJson['revisions'][0]

def outputXML(data):
    '''output the data in the desired format'''
    #for testing
    for k,v in data.iteritems():
        print u'%s' %k
        for kk, vv in v.iteritems():
            print u'\t%s: %s' %(kk,vv)

def outputCatStat(data):
    '''output the category statistics in the desired format'''
    #for testing
    for k,v in data.iteritems():
        txt = u'[_]'
        if v['filtered']: txt = u'[F]'
        print u'%s %s: %d' %(txt, k, v['count'])
#EoF
