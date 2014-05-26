#!/usr/bin/python
# -*- coding: utf-8  -*-
#
# By: André Costa, Wikimedia Sverige
# License: MIT
# 2014
#
# To do:
## resolve how to deal with credit/uploader/photographer
### rewsolve how to deal with templates in credit
## resolve how to deal with links (in description)
### should red links be treated differently.
## make sure no more TODOs
# Known issues:
## Does not deal with multiple licenses (see /w/api.php?action=query&prop=imageinfo&format=json&iiprop=commonmetadata%7Cextmetadata&iilimit=1&titles=File%3AKalmar%20cathedral%20Kalmar%20Sweden%20001.JPG)
## Only supports Template:Information
'''
Script for harvesting metadata from Wikimedia Commons for the use in Europeana
'''

import codecs, ujson
import datetime #for timestamps  in log
import operator #only used by categoryStatistics
import WikiApi as wikiApi
from lxml import etree #for xml output

class EuropeanaHarvester(object):
    def versionInfo(self):
        '''Version specific variables'''
        self.scriptversion = u'0.6'
        self.scriptname = u'EuropeanaScript'
        self.infoTemplate = [u'Template:Information',] #supported info templates - based on what is suppported by parseImageInfo
        self.commonsMetadataExtension = 1.2 # the version of the extention for which the script was designed
    
    def loadVariables(self):
        '''semi-stable variables which are not project specific'''
        self.dudCategories = ('Media needing categories',) #non-hidden maintanance categories, matched with startswith()
        self.cc0Length = 200 #max alowed length of description field (for Europeana to claim CC0 on metadata
        self.creditFilterStrings = [u'<span class="int-own-work">Own work</span>',] #used for credits
        self.gcmlimit = 250 #Images to process per API request in ImageInfo
        self.logFilename = u'EuropeanaHarvester.log'
    
    def loadProject(self, project):
        '''open projectfile and load variables
           returns None on success otherwise it returns an error message'''
        #Projectfile must be uft-8 encoded json and correctly formated
        
        #load file
        try:
            f = codecs.open(project, 'r', 'utf-8')
            jsonr = ujson.load(f)
            f.close()
        except IOError, e:
            return u'Error opening project file: %s' %e
        except ValueError, e: 
            return u'Error processing project file as json. Are you sure it is valid?: %s' %e
        
        #set project parameters
        ##name
        p = u'project-name'
        if not p in jsonr.keys():
            return u'No "%s" in project file' %p
        elif (type(jsonr[p]) != str) and (type(jsonr[p]) != unicode):
            return u'Parameter "%s" in project file must be a (unicode)string' %p
        self.projName = jsonr[p]
        
        ##output-pattern
        p = u'output-pattern'
        if not p in jsonr.keys():
            return u'No "%s" in project file' %p
        elif (type(jsonr[p]) != str) and (type(jsonr[p]) != unicode):
            return u'Parameter "%s" in project file must be a (unicode)string' %p
        self.output = jsonr[p]
        
        ##base-categories
        p = u'base-categories'
        formaterror = u'Parameter "%s" in project file must be a list of (unicode)strings' %p
        if not p in jsonr.keys():
            return u'No "%s" in project file' %p
        elif type(jsonr[p]) != list:
            return formaterror
        for s in jsonr[p]:
            if (type(s) != str) and (type(s) != unicode):
                return formaterror
            if not s.startswith(u'Category:'):
                return u'Category names must include "Category:"-prefix'
        self.baseCats = jsonr[p]
        
        ##id-templates
        self.idTemplates = {}
        p = u'id-templates'
        formaterror = u'Parameter "%s" in project file must be a dictionary with template names as keys and lists of (unicode)strings as values' %p
        if not p in jsonr.keys():
            return u'No "%s" in project file' %p
        elif type(jsonr[p]) != dict:
            return formaterror
        for k, v in jsonr[p].iteritems():
            if not k.startswith(u'Template:'):
                return u'Template names must include "Template:"-prefix'
            if type(v) != list:
                return formaterror
            for s in v:
                if (type(s) != str) and (type(s) != unicode):
                    return formaterror
            self.idTemplates[k] = tuple(v)
        
        #success
        return None
    
    def __init__(self, project, test=False):
        '''Sets up environment, loads project file, triggers run/test
           Requires one parameter:
           project: the (unicode)string relative pathname to the project json file'''
        self.versionInfo()
        self.loadVariables()
        self.log = codecs.open(self.logFilename, 'a', 'utf-8')
        self.data = {} #container for all the info, using pageid as its key
        projError = self.loadProject(project)
        if projError:
            self.log.write(u'Error loading project file: %s\n' %projError)
            exit(1)
        
        #confirm succesful load to log together with timestamp
        self.log.write(u'-----------------------\n%s: Successfully loaded "%s" run.\n' %(datetime.datetime.utcnow(), self.projName))
        
        #Connect to api
        scriptidentify = u'%s/%s' %(self.scriptname,self.scriptversion)
        ##look for config file
        try:
            import config
            self.wpApi = wikiApi.WikiApi.setUpApi(user=config.user, password=config.password, site=config.siteurl, scriptidentify=scriptidentify) 
        except ImportError:
            from getpass import getpass #not needed if config file exists
            siteurl = 'https://commons.wikimedia.org'
            self.wpApi = wikiApi.WikiApi.setUpApi(user=getpass(u'Username:'), password=getpass(), site=siteurl, scriptidentify=scriptidentify)
        
        #Create output files (so that any errors occur before the actual run)
        try:
            self.fStat = codecs.open(u'%s-CategoryStatistics.csv' %self.output, 'w', 'utf-8')
            self.fXML  = codecs.open(u'%s.xml' %self.output, 'w', 'utf-8')
            self.fCSV  = codecs.open(u'%s.csv' %self.output, 'w', 'utf-8')
        except IOError, e:
            bla
        
        #ready to run
        
        #run
        if test:
            runError = self.run(verbose=True, testing=True, debug=False)
        else:
            runError = self.run(verbose=False)
        
        if runError:
            self.log.write(u'Error during run: %s\n' %runError)
            exit(1)
        
        #confirm sucessful ending to log together with timestamp
        self.log.write(u'%s: Successfully reached end of run.\n' %datetime.datetime.utcnow())
        self.log.close()
    
    def run(self, verbose=False, testing=False, debug=False):
        '''Runs through the specified categories, sets up a dict with the imageinfo for each image
           then checks the parsed content for each image page to identify any of the specified id-templates
           and if found stores the associate sourcelink.
        '''
        #Retrieve all ImageInfos
        imageInfo={}
        for basecat in self.baseCats:
            if verbose:
                print u'Retrieving ImageInfo for %s...' %basecat
            getImageInfosError = self.getImageInfos(basecat, imageInfo=imageInfo, debug=debug, verbose=verbose, testing=testing)
            if getImageInfosError:
                self.log.write(u'Terminatiing: Error retrieving imageInfos: %s\n' %getImageInfosError)
                #at this point we most likely do not want to continue
                if verbose: 
                    print u'Terminated prematurely, please check log file'
                return u'Terminate'
        
        #parse all ImageInfos
        if verbose:
            print u'Parsing ImageInfo...'
        counter = 0
        for k,v in imageInfo.iteritems():
            counter +=1
            if verbose and (counter%250)==0:
                print u'parsed %d out of %d' %(counter, len(imageInfo))
            errorType, errorMessage = self.parseImageInfo(v)
            if errorType != None:
                if errorType: #critical
                    self.log.write(u'Terminating: error parsing imageInfos: %s\n' %errorMessage)
                    if verbose:
                        print u'Terminated prematurely, please check log file'
                    return u'Terminate'
                else: #minor
                    self.log.write(u'Skipping: error parsing imageInfos: %s\n' %errorMessage)
        
        #add data from content
        if verbose:
            print u'Retrieving content...'
        counter = 0
        unsupported = []
        for k in self.data.keys():
            counter +=1
            if verbose and (counter%100)==0:
                print u'Retrieved %d out of %d' %(counter, len(self.data))
            #get content for that pageID (can only retrieve one at a time)
            content, getContentError = self.getContent(k)
            if not getContentError:
                getContentError = self.parseContent(k, content)
                if not getContentError:
                    continue
            #only reached if encountered error
            self.log.write(u'Error retrieving/parsing content for PageId %d (%s), removing from dataset: %s\n' %(k, self.data[k]['title'], getContentError))
            unsupported.append(k)
        
        #remove problematic entries
        for k in unsupported:
            del self.data[k]
        
        #output data and close filewriters
        self.outputCatStat(f = self.fStat)
        self.outputXML(f = self.fXML)
        self.outputCSV(f = self.fCSV)
        if verbose:
            print u'Wrote to %s.xml, %s.csv and %s-CategoryStatistics.csv' %(self.output,self.output,self.output)
        
        #success
        if verbose:
            print u'Successfully reached end of run'
        return None
    
    def getImageInfos(self, maincat, imageInfo={}, debug=False, verbose=False, testing=False):
        '''given a single category this queries the MediaWiki api for the parsed content of that page
           returns None on success otherwise an error message.'''
        #TODO needs more error handling (based on api replies)
        #TODO Consider killing debug/testing
        #Allows overriding gcmlimit for testing
        gcmlimit = self.gcmlimit
        if testing:
            gcmlimit = 5
        
        #test that category exists and check number of entries
        #/w/api.php?action=query&prop=categoryinfo&format=json&titles=Category%3AImages%20from%20Wiki%20Loves%20Monuments%202013%20in%20Sweden
        jsonr = self.wpApi.httpGET("query", [('prop', 'categoryinfo'),
                                        ('titles', maincat.encode('utf-8'))
                                       ])
        if debug:
            print u'getImageInfos() categoryinfo for: %s\n%s' %(maincat, jsonr)
        jsonr = jsonr['query']['pages'].iteritems().next()[1]
        #check for error
        if 'missing' in jsonr.keys():
            return u'The category "%s" does not exist' %maincat
        total = jsonr['categoryinfo']['files']
        if verbose:
            print u'The category "%s" contains %d files and %d subcategories (the latter will not be checked)' %(maincat, total, jsonr['categoryinfo']['subcats'])
        
        #then start retrieving info
        #/w/api.php?action=query&prop=imageinfo&format=json&iiprop=user%7Curl%7Cmime%7Cextmetadata&iilimit=1&generator=categorymembers&gcmtitle=Category%3AImages%20from%20Wiki%20Loves%20Monuments%202013%20in%20Sweden&gcmprop=title&gcmnamespace=6&gcmlimit=50
        jsonr = self.wpApi.httpGET("query", [('prop', 'imageinfo'),
                                        ('iiprop', 'user|url|mime|extmetadata'),
                                        ('iilimit', '1'),
                                        ('generator', 'categorymembers'),
                                        ('gcmprop', 'title'),
                                        ('gcmnamespace', '6'),
                                        ('gcmlimit', str(gcmlimit)),
                                        ('gcmtitle', maincat.encode('utf-8'))
                                       ])
        if debug:
            print u'getImageInfos() imageinfo for: %s\n%s' %(maincat, jsonr)
        #store (part of) the json
        imageInfo.update(jsonr['query']['pages']) # a dict where pageId is the key
        
        #while continue get the rest
        counter = 0
        while('query-continue' in jsonr.keys()):
            counter += gcmlimit
            if verbose: 
                print u'Retrieved %d out of %d (roughly)' %(counter, total)
            jsonr = self.wpApi.httpGET("query", [('prop', 'imageinfo'),
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
            if testing and counter >15:
                break #shorter runs for testing
        
        #sucessfully reached end
        return None
    
    def getContent(self, pageId, debug=False):
        '''given a pageId this queries the MediaWiki api for the parsed content of that page
           returns tuple (content, errorInfo) where errorInfo is None on success'''
        #/w/api.php?action=parse&format=json&pageid=27970534&prop=categories%7Ctemplates%7Cexternallinks
        jsonr = self.wpApi.httpGET("parse", [('prop', 'categories|templates|externallinks'),
                                        ('pageid', str(pageId))
                                       ])
        if debug:
            print u'getContent() pageId:%d \n%s' %(pageId, jsonr)
            
        #check for error
        if 'error' in jsonr.keys():
            return (None, jsonr['error']['info'])
        elif 'parse' in jsonr.keys():
            return (jsonr['parse'], None)
        else:
            return (None, u'API parse reply did not contain "error"-key but also not "parse"-key. Unexpected and probably means something went really wrong')
    
    def parseImageInfo(self, imageJson):
        '''parse a single page in imageInfo reply from the API
           returns: tuple (error-type, errorMessage) where:
           * a successful test returns (None,None)
           * a critical error (stopping the program) returns (True, Message)
           * a minor error (skip this item) returns (False, Message)
        '''
        #Issues:
        ## Is more content validation needed?
        ## Filter out more credit stuff
        ## filter out more description stuff
        pdMark = u'https://creativecommons.org/publicdomain/mark/1.0/'
        
        #outer info
        pageId = imageJson['pageid']
        title = imageJson['title'][len('File:'):].strip()
        
        #swithch to inner info
        imageJson = imageJson['imageinfo'][0]
        
        #checks prior to continuing
        if not imageJson['extmetadata']['CommonsMetadataExtension']['value'] == self.commonsMetadataExtension: #no guarantee that metadata is treated correctly if any other version
            #would probably want to stop whole process
            return (True, u'This uses a different version of the commonsMetadataExtension than the one the script was designed for, terminating. Expected: %s; Found: %s' %(self.commonsMetadataExtension, imageJson['extmetadata']['CommonsMetadataExtension']['value']))
        if not imageJson['mime'].split('/')[0].strip() == 'image': #check that it is really an image
            #would probably only want to skip this image (or deal with it)
            return (False, u'%s is not an image but a %s, skipping' %(title, imageJson['mime'].split('/')[0].strip()))
        if pageId in self.data.keys(): #check if image already in dictionary
            #would probably only want to skip this image (or deal with it)
            return (False, u'pageId (%s) already in data, skipping: old:%s new:%s' %(pageId, self.data[pageId]['title'], title))
        
        #Prepare data object, not sent directly to data[pageId] in case errors are discovered downstream
        obj = {'title':title, 'medialink':imageJson['url'].strip(), 'identifier':imageJson['descriptionurl'].strip(), 'mediatype':'IMAGE'}
        
        #listing potentially interesting fields
        user        = imageJson['user'] #as backup for later field. Note that this is the latest uploader, not necessarily the original one.
        obj['description'] = self.descriptionFiltering(imageJson['extmetadata']['ImageDescription']['value'].strip()) if u'ImageDescription' in imageJson['extmetadata'].keys() else None
        obj['credit'] = self.creditFiltering(imageJson['extmetadata']['Credit']['value'].strip()) if u'Credit' in imageJson['extmetadata'].keys() else None #send straight to filtering
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
            return (False, u'%s did not have any information about the creator, skipping' %title)
        
        ## Deal with licenses
        if licenseurl:
            if licenseurl.startswith(u'http://creativecommons.org/licenses/'):
                obj[u'copyright'] = licenseurl
            else:
                return (False, u'%s did not have a CC-license URL and is not public Domain, skipping: %s (%s)' %(title, licenseurl, licenseShortName))
        else:
            if copyrighted == u'False':
                obj[u'copyright'] = pdMark
            else:
                return (False, u'%s did not have a license URL and is not public Domain, skipping: %s' %(title, licenseShortName))
        
        ## isolate date giving preference to dateOrig
        if dateOrig: #the date as described in the description
            #format (timestamp is optional): <time class="dtstart" datetime="2013-08-26">26 August  2013</time>, 09:51:00
            if dateOrig.startswith(u'<time class="dtstart" datetime='):
                date = dateOrig.split('"')[3]
                if len(dateOrig.split('>,'))==2:
                    date += dateOrig.split('>,')[1]
                obj['created'] = date
            elif u'<time' in dateOrig: #weird
                return (False, u'%s did not have a recognised datestamp: %s' %(title, dateOrig))
            else: #just plain text
                self.log.write(u'%s has plain text date: %s\n'%(title, dateOrig))
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
        self.data[pageId] = obj
        return (None, None)
    
    def parseContent(self, pageId, contentJson):
        '''parse a single parse reply from the API
           with the aim of identifying the institution links, non-maintanance categories and used templates.
           adds to data: categories (list), sourcelinks (list)
           returns: None on success otherwise an error message
           '''
        #structure up info as simple lists
        templates = []
        for t in contentJson['templates']:
            if 'exists' in t.keys(): templates.append(t['*'])
        self.data[pageId][u'categories'] = []
        for c in contentJson['categories']:
            if not 'hidden' in c.keys() and not 'missing' in c.keys():
                if not unicode(c['*']).startswith(self.dudCategories):
                    self.data[pageId][u'categories'].append(unicode(c['*']).replace('_',' ')) #unicode since some names are interpreted as longs
        extLinks = contentJson['externallinks'] #not really needed
        
        #Checking that the information structure is supported
        supported = False
        for t in self.infoTemplate:
            if t in templates:
                supported = True
        if not supported:
            return u'Does not contain a supported information template'
        
        #Isolate the source templates and identify the source links
        self.data[pageId][u'sourcelinks'] = []
        for k, v in self.idTemplates.iteritems():
            if k in templates:
                for e in extLinks:
                    if e.startswith(v):
                        self.data[pageId][u'sourcelinks'].append(e)
        
        #successfully reached the end
        return None
    
    def outputCSV(self, f):
        '''output the data as a csv for an easy overview. Also allows outputting more fields than are included in xml'''
        f.write(u'#mediatype|created|medialink|uploader|sourcelinks|identifier|categories|copyright|title|photographer|usageTerms|credit|description\n')
        for k,v in self.data.iteritems():
            for kk, vv in v.iteritems():
                if vv is None:
                    v[kk] = ''
                if kk in ['sourcelinks', 'categories']:
                    v[kk] = ';'.join(v[kk])
                v[kk] = v[kk].replace('|','!').replace('\n',u'¤')
            f.write(u'%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s\n' %(v['mediatype'], v['created'], v['medialink'], v['uploader'], v['sourcelinks'], v['identifier'], v['categories'], v['copyright'], v['title'], v['photographer'], v['usageTerms'], v['credit'], v['description']))
        f.close()
    
    def outputXML(self, f):
        '''output the data as xml acording to the desired format'''
        NSMAP = {"dc" : 'dummy'} #lxml requieres namespaces to be declared, Europeana want's them stripped (se latter replacement)
        
        f.write(u"<?xml version='1.0' encoding='UTF-8'?>\n") #proper declaration does not play nice with unicode
        
        for k,v in self.data.iteritems():
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
    
    def outputCatStat(self, f):
        '''output the category statistics in the desired format'''
        allCats = {}
        for k,v in self.data.iteritems():
            for c in v['categories']:
                if c in allCats.keys():
                    allCats[c] += 1
                else:
                    allCats[c] = 1
        
        sorted_allCats = EuropeanaHarvester.sortedDict(allCats)
        
        #outputting
        f.write(u'#frequency|category\n')
        for k in sorted_allCats:
              f.write(u'%d|%s\n' %(k[1], k[0]))
        f.close()
    
    def descriptionFiltering(self, description):
        '''given a description string this filters out any tags which likely indicate templates'''
        filtertags = ['div', 'table']
        
        for t in filtertags:
            #replace all occurences of tag
            description = self.stripTag(description, t)
            if len(description.strip()) == 0:
                return None
            #next tag
        #all tags checked
        
        #truncate at cc0Length characters and elipse with ...
        if len(description) > self.cc0Length:
            description = u'%s...' %description[:(self.cc0Length-3)]
            
        return description.strip()
    
    def creditFiltering(self, credit, templateFilter=False):
        '''given a credit string this filters out strings known to be irrelevant
           returns: None if nothing relevant is left otherwise remaining text'''
        for f in self.creditFilterStrings:
            credit = credit.replace(f,'')
            if len(credit.strip()) == 0:
                return None
        
        #More advanced - do similar filtering as for descriptions
        if templateFilter:
            filtertags = ['div', 'table']
            for t in filtertags:
                credit = self.stripTag(credit, t)
                if len(credit.strip()) == 0:
                    return None
        return credit.strip()
    
    def stripTag(self, text, t):
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
                    self.log.write('missmatched tags, aborting search for %s tag\n' %t)
                    break
                else:
                    text = text[:sp]+text[ep+len('</%s>' %t):] #strip out this occurence of the tag
        return text
    
    @staticmethod
    def sortedDict(ddict):
        '''turns a dict into a sorted list of tuples'''
        sorted_ddict = sorted(ddict.iteritems(), key=operator.itemgetter(1), reverse=True)
        return sorted_ddict

if __name__ == '__main__':
    import sys
    argv = sys.argv[1:]
    if len(argv) == 1:
        EuropeanaHarvester(argv[0], test=False)
    elif len(argv) == 2:
        if argv[1] in ['True', 'true', 'test', 'Test']:
            test = True
        else:
            test = False
        EuropeanaHarvester(argv[0], test=test)
    else:
        print '''Usage: python Europeana.py filename test
        filename (required):\t the (unicode)string relative pathname to the json file for the project
        test (optional):\t if set (to "test" or "True") this toggles on testing (a verbose and limited run)'''
#EoF
