#!/usr/bin/python
# -*- coding: utf-8  -*-
#
# By: André Costa, Wikimedia Sverige
# License: MIT
# 2014
#
# To do:
## output errors to log
## wrap in class to allow for communal variables (log, data, wpApi) and initialisation of communal variables (supported templates, scriptverison etc.)
## externalise project info
## resolve how to deal with credit/uploader/photographer
### rewsolve how to deal with templates in credit
## resolve how to deal with links (in description)
### should red links be treated differently.
'''
Script for harvesting metadata from Wikimedia Commons for the use in Europeana
'''

import codecs #might not be needed after testing
import ujson
import operator #only used by categoryStatistics
import WikiApi as wikiApi
from getpass import getpass #not needed if this is put into config file
from lxml import etree #for xml output

def testing(verbose=True, testing=True):
    #communal variables
    scriptname = u'EuropeanaScript'
    scriptversion = u'0.5'
    siteurl = 'https://commons.wikimedia.org'
    
    #testing parameters
    user = u'L_PBot' #=getpass(u'Username:')
    basecat = 'Category:Images from Wiki Loves Monuments 2013 in Sweden'
    
    #Connect to api
    wpApi = wikiApi.WikiApi.setUpApi(user=user, password=getpass(), site=siteurl, scriptidentify=u'%s/%s' %(scriptname,scriptversion)) 
    
    #based on some given category we retrieve all of the image infos
    if verbose: print u'Retrieving ImageInfo...'
    imageinfo = getImageInfos(basecat, wpApi, debug=False, verbose=verbose, testing=True)
    if not imageinfo:
        #if false/None is returned then information could not be retrieved
        print 'something bad happened'
        exit(1)
    
    #container for all the info, using pageid as its key
    if verbose: print u'Parsing ImageInfo...'
    counter = 0
    data = {}
    for k,v in imageinfo.iteritems():
        counter +=1
        if verbose and (counter%250)==0: print u'Parsed %d out of %d' %(counter, len(imageinfo))
        if not parseImageInfo(v, data):
            #if false is returned then something bad happened
            print 'something bad happened'
    
    #add data from description
    if verbose: print u'Retrieving content...'
    counter = 0
    unsupported = []
    for k in data.keys():
        counter +=1
        if verbose and (counter%100)==0: print u'Retrieved %d out of %d' %(counter, len(data))
        #get content for that pageID (can only retrieve one at a time)
        content = getContent(k,wpApi)
        if not content: #if fails then remove object from data
            print 'content could not be retrieved for PageId %d (%s), removing' %(k, data[k]['title'])
            unsupported.append(k)
        elif not parseContent(k, content, data):
            #if false is returned then object was not supported
            unsupported.append(k)
    
    #remove problematic entries
    for k in unsupported:
        del data[k]
    
    #output data incl. csv for follow-up
    outputCatStat(data, filename = u'categoryStatistics.csv')
    outputXML(data, filename = u'output.xml')
    outputCSV(data, filename = u'output.csv')

def getImageInfos(maincat, wpApi, debug=False, verbose=False, testing=False):
    '''given a single category this queries the MediaWiki api for the parsed content of that page'''
    #needs more error checking
    gcmlimit = 250 #250 how many images to ask about at once
    if testing:
        gcmlimit = 5
    
    #test that category exists and check number of entries
    #/w/api.php?action=query&prop=categoryinfo&format=json&titles=Category%3AImages%20from%20Wiki%20Loves%20Monuments%202013%20in%20Sweden
    jsonr = wpApi.httpGET("query", [('prop', 'categoryinfo'),
                                    ('titles', maincat.encode('utf-8'))
                                   ])
    if debug:
        print u'getImageInfos() categoryinfo for: %s' %maincat
        print jsonr
    jsonr = jsonr['query']['pages'].iteritems().next()[1]
    #check for error
    if 'missing' in jsonr.keys():
        print u'The category "%s" does not exist. Did you maybe forget the "Category:"-prefix?' %maincat
        return None
    total = jsonr['categoryinfo']['files']
    if verbose:
        print u'The category "%s" contains %d files and %d subcategories (the latter will not be checked)' %(maincat, total, jsonr['categoryinfo']['subcats'])
    
    #then start retrieving info
    #/w/api.php?action=query&prop=imageinfo&format=json&iiprop=user%7Curl%7Cmime%7Cextmetadata&iilimit=1&generator=categorymembers&gcmtitle=Category%3AImages%20from%20Wiki%20Loves%20Monuments%202013%20in%20Sweden&gcmprop=title&gcmnamespace=6&gcmlimit=50
    jsonr = wpApi.httpGET("query", [('prop', 'imageinfo'),
                                    ('iiprop', 'user|url|mime|extmetadata'),
                                    ('iilimit', '1'),
                                    ('generator', 'categorymembers'),
                                    ('gcmprop', 'title'),
                                    ('gcmnamespace', '6'),
                                    ('gcmlimit', str(gcmlimit)),
                                    ('gcmtitle', maincat.encode('utf-8'))
                                   ])
    if debug:
        print u'getImageInfos() imageinfo for: %s' %maincat
        print jsonr
    #store (part of) the json
    imageInfo = jsonr['query']['pages'] # a dict where pageId is the key
    
    #while continue get the rest
    counter = 0
    while('query-continue' in jsonr.keys()):
        counter += gcmlimit
        if verbose: 
            print u'Retrieved %d out of %d (roughly)' %(counter, total)
        jsonr = wpApi.httpGET("query", [('prop', 'imageinfo'),
                                        ('iiprop', 'user|url|mime|extmetadata'),
                                        ('iilimit', '1'),
                                        ('generator', 'categorymembers'),
                                        ('gcmprop', 'title'),
                                        ('gcmnamespace', '6'),
                                        ('gcmlimit', str(gcmlimit)),
                                        ('gcmcontinue',jsonr['query-continue']['categorymembers']['gcmcontinue']),
                                        ('gcmtitle', maincat.encode('utf-8'))
                                       ])
        #store (part of) json
        imageInfo.update(jsonr['query']['pages'])
        if testing:
            if counter >15: break #testing
    
    #sucessfully reached end
    return imageInfo

def getContent(pageId, wpApi, debug=False):
    '''given a pageId this queries the MediaWiki api for the parsed content of that page'''
    #/w/api.php?action=parse&format=json&pageid=27970534&prop=categories%7Ctemplates%7Cexternallinks
    jsonr = wpApi.httpGET("parse", [('prop', 'categories|templates|externallinks'),
                                    ('pageid', str(pageId))
                                   ])
    if debug:
        print u'getContent() pageId:%d \n' %pageId
        print jsonr
        
    #check for error
    if 'error' in jsonr.keys():
        print jsonr['error']['info']
        return None
    elif 'parse' in jsonr.keys():
        return jsonr['parse']
    else:
        print 'you should never get here'
        return None

def parseImageInfo(imageJson, data):
    '''parse a single page in imageInfo reply from the API'''
    #Issues:
    ## Assumes Information template. Need to test with e.g artwork template and see what happens if there is no template
    ### For artwork. Title might be different, also artist/photographer.
    ## Does not deal with multiple licenses (see /w/api.php?action=query&prop=imageinfo&format=json&iiprop=commonmetadata%7Cextmetadata&iilimit=1&titles=File%3AKalmar%20cathedral%20Kalmar%20Sweden%20001.JPG)
    ## Is more content validation needed?
    ## Filter out more credit stuff
    ## filter out more description stuff
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
    user        = imageJson['user'] #as backup for later field. Note that this is the latest uploader, not necessarily the original one.
    obj['description'] = descriptionFiltering(imageJson['extmetadata']['ImageDescription']['value'].strip()) if u'ImageDescription' in imageJson['extmetadata'].keys() else None
    obj['credit'] = creditFiltering(imageJson['extmetadata']['Credit']['value'].strip()) if u'Credit' in imageJson['extmetadata'].keys() else None #send straight to filtering
    objectName  = imageJson['extmetadata']['ObjectName']['value'].strip() if u'ObjectName' in imageJson['extmetadata'].keys() else None
    datePlain   = imageJson['extmetadata']['DateTime']['value'].strip() if u'DateTime' in imageJson['extmetadata'].keys() else None
    dateDig     = imageJson['extmetadata']['DateTimeDigitized']['value'].strip() if u'DateTimeDigitized' in imageJson['extmetadata'].keys() else None
    dateOrig    = imageJson['extmetadata']['DateTimeOriginal']['value'].strip() if u'DateTimeOriginal' in imageJson['extmetadata'].keys() else None
    dateMeta    = imageJson['extmetadata']['DateTimeMetadata']['value'].strip() if u'DateTimeMetadata' in imageJson['extmetadata'].keys() else None
    licenseShortName = imageJson['extmetadata']['LicenseShortName']['value'].strip() if u'LicenseShortName' in imageJson['extmetadata'].keys() else None
    licenseurl  = imageJson['extmetadata']['LicenseUrl']['value'].strip() if u'LicenseUrl' in imageJson['extmetadata'].keys() else None
    artist      = imageJson['extmetadata']['Artist']['value'].strip() if u'Artist' in imageJson['extmetadata'].keys() else None
    obj['usageTerms'] = imageJson['extmetadata']['UsageTerms']['value'].strip() if u'UsageTerms' in imageJson['extmetadata'].keys() else None #does this ever contain anything useful?
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
    
    #maintanance categories which are not hidden - only start of categorynames
    dudCats = ('Media needing categories',)
    
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
        if not 'hidden' in c.keys() and not 'missing' in c.keys():
            if not unicode(c['*']).startswith(dudCats):
                data[pageId][u'categories'].append(unicode(c['*']).replace('_',' ')) #unicode since some names are interpreted as longs
    extLinks = contentJson['externallinks'] #not really needed
    
    #Checking that the information structure is supported
    supported = False
    for t in infoTemplate:
        if t in templates:
            supported = True
    if not supported:
        print '%s did not contain a supported information template' %data[k]['title']
        return False
    
    #Isolate the source templates and identify the source links
    data[pageId][u'sourcelinks'] = []
    for k, v in idTemplates.iteritems():
        if k in templates:
            for e in extLinks:
                if e.startswith(v):
                    data[pageId][u'sourcelinks'].append(e)
    
    #successfully reached the end
    return True

def outputCSV(data, filename):
    '''output the data as a csv for an easy overview. Also allows outputting more fields than are included in xml'''
    #for testing
    f = codecs.open(filename, 'w', 'utf-8')
    f.write(u'#mediatype|created|medialink|uploader|sourcelinks|identifier|categories|copyright|title|photographer|usageTerms|credit|description\n')
    for k,v in data.iteritems():
        for kk, vv in v.iteritems():
            if vv is None:
                v[kk] = ''
            if kk in ['sourcelinks', 'categories']:
                v[kk] = ';'.join(v[kk])
            v[kk] = v[kk].replace('|','!').replace('\n',u'¤')
        f.write(u'%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' %(v['mediatype'], v['created'], v['medialink'], v['uploader'], v['sourcelinks'], v['identifier'], v['categories'], v['copyright'], v['title'], v['photographer'], v['usageTerms'], v['credit'], v['description']))
    f.close()
    print u'Created %s' %filename

def outputXML(data, filename):
    '''output the data as xml acording to the desired format'''
    NSMAP = {"dc" : 'dummy'} #lxml requieres namespaces to be declared, Europeana want's them stripped (se latter replacement)
    
    f = codecs.open(filename, 'w', 'utf-8')
    f.write(u"<?xml version='1.0' encoding='UTF-8'?>\n") #proper declaration does not play nice with unicode
    
    for k,v in data.iteritems():
        dc = etree.Element('{dummy}dc', nsmap=NSMAP)
        
        #identifier - mandatory
        child = etree.Element('identifier')
        child.text = v['identifier']
        dc.append(child)
        
        #sourcelink - optional, multiple
        for s in v['sourcelinks']:
            child = etree.Element('sourcelink')
            child.text = s
            dc.append(child)
        
        #title - mandatory
        child = etree.Element('title')
        child.text = v['title']
        dc.append(child)
        
        #photographer - mandatory
        child = etree.Element('photographer')
        child.text = v['photographer']
        dc.append(child)
        
        #creator - optional
        if 'creator' in v.keys() and v['creator']:
            child = etree.Element('creator')
            child.text = v['creator']
            dc.append(child)
        
        #created - optional
        if 'created' in v.keys() and v['created']:
            child = etree.Element('created')
            child.text = v['created']
            dc.append(child)
        
        #description - optional
        if 'description' in v.keys() and v['description']: 
            child = etree.Element('description')
            child.text = v['description']
            dc.append(child)
        
        #category - optional, multiple
        for c in v['categories']:
            child = etree.Element('category')
            child.text = c
            dc.append(child)
        
        #link - mandatory (same as identifier)
        child = etree.Element('link')
        child.text = v['identifier']
        dc.append(child)
        
        #medialink - mandatory
        child = etree.Element('medialink')
        child.text = v['medialink']
        dc.append(child)
        
        #copyright - mandatory
        child = etree.Element('copyright')
        child.text = v['copyright']
        dc.append(child)
        
        #type - mandatory
        child = etree.Element('type')
        child.text = v['mediatype']
        dc.append(child)
        
        #end of single dc-element
        f.write(etree.tostring(dc, pretty_print=True, encoding='unicode').replace(u' xmlns:dc="dummy"',''))
    
    #end of all dc-elements
    f.close()
    print u'Created %s' %filename

def outputCatStat(data, filename):
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
    f = codecs.open(filename, 'w', 'utf-8')
    f.write(u'#frequency|category\n')
    for k in sorted_allCats:
          f.write(u'%d|%s\n' %(k[1], k[0]))
    f.close()
    print u'Created %s' %filename

def creditFiltering(credit):
    '''given a credit string this filters out strings known to be irrelevant
       returns: None if nothing relevant is left otherwise remaining text'''
    #Should be externalised
    filterstrings = [u'<span class="int-own-work">Own work</span>',]
    for f in filterstrings:
        credit = credit.replace(f,'')
        if len(credit.strip()) == 0:
            return None
    
    #More advanced
    ##Consider doing the same tag filtering as for descriptions
    return credit.strip()

def descriptionFiltering(description):
    '''given a description string this filters out any tags which likely indicate templates'''
    filtertags = ['div', 'table']
    maxChars = 200 #max alowed length of description field
    
    for t in filtertags:
        #replace all occurences of tag
        description = stripTag(description, t)
        if len(description.strip()) == 0:
            return None
        #next tag
    #all tags checked
    
    #truncate at maxChars characters and elipse with ...
    if len(description) > maxChars:
        description = u'%s...' %description[:(maxChars-3)]
        
    return description.strip()

#static helper functions
def stripTag(text, t):
    '''given a string and a tag this strips out all occurences of this tag from the text
       assumes tag starts with "<tag" and ends "</tag>"
       returns stripped text'''
    if text.find('<%s' %t) >=0:
        #find all occurences of this tag
        startpos = []
        sp = text.find('<%s' %t)
        while sp >=0:
            startpos.append(sp)
            sp = text.find('<%s' %t, sp+1)
        #find the matching end tags
        while len(startpos)>0:
            sp=startpos.pop() #gets the last one
            ep=text.find('</%s>' %t,sp+1) #get endposition
            if ep<0:
                print 'missmatched tags, aborting search for %s tag' %t
                break
            else:
                text = text[:sp]+text[ep+len('</%s>' %t):] #strip out this occurence of the tag
    return text

def sortedDict(ddict):
    '''turns a dict into a sorted list of tuples'''
    sorted_ddict = sorted(ddict.iteritems(), key=operator.itemgetter(1), reverse=True)
    return sorted_ddict
#EoF
