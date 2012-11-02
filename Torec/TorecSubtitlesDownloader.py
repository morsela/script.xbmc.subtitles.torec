import cookielib
import zipfile
import urllib
import urllib2
import time
import os
import sys
import re
import zlib
from BeautifulSoup import BeautifulSoup

from utilities import *

class SubtitleOption(object):
    def __init__(self, name, id):
        self.name = name
        self.id = id
        
    def __repr__(self):
        return "%s" % (self.name)
    
class SubtitlePage(object):
    def __init__(self, id, name, data):
        self.id = id
        self.name = name
        self.options = self._parseOptions(data)
        
    def _parseOptions(self, data):
        subtitleSoup = BeautifulSoup(data)
        subtitleOptions = subtitleSoup("div", {'class' : 'download_box' })[0].findAll("option")
        return map(lambda x: SubtitleOption(x.string.strip(), x["value"]), subtitleOptions)

    def __str__(self):
        log(__name__ ,self.name)
        for option in self.options:
            log(__name__ ,option)
        
class FirefoxURLHandler():
    def __init__(self):
        cj = cookielib.CookieJar()
        self.opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
        self.opener.addheaders = [('Accept-Encoding','gzip, deflate'),
                                  ('Accept-Language', 'en-us,en;q=0.5'),
                                  ('Pragma', 'no-cache'),
                                  ('Cache-Control', 'no-cache')]
    
    def request(self, url, data=None, ajax=False):
        if (data != None):
            data = urllib.urlencode(data)
        if (ajax == True):
            self.opener.addheaders += [('X-Requested-With', 'XMLHttpRequest')]
  
        resp = self.opener.open(url, data)
        data = resp.read()
        
        if (len(data) != 0):
            try:
                data = zlib.decompress(data, 16+zlib.MAX_WBITS)
            except zlib.error:
                pass
        
        return (data, resp.headers)
    

class TorecSubtitlesDownloader:
    DEFAULT_SEPERATOR = " "
    BASE_URL = "http://www.torec.net"
    SUBTITLE_PATH = "sub.asp?sub_id="

    def __init__(self):
        self.urlHandler = FirefoxURLHandler()
        
    def searchMovieName(self, movieName):
        data = self.urlHandler.request("%s/ssearch.asp" % self.BASE_URL, {"search" : movieName})[0]
        match = re.search('sub\.asp\?sub_id=(\w+)', data)
        if (match is None):
            return None
          
        id = match.groups()[0]
        subtitleData = self.urlHandler.request("%s/%s%s" % (self.BASE_URL, self.SUBTITLE_PATH, id))[0]
        return SubtitlePage(id, movieName, subtitleData)
        
    def findChosenOption(self, name, subtitlePage):
        name = name.split(self.DEFAULT_SEPERATOR)
        # Find the most likely subtitle (the subtitle which adheres to most of the movie properties)
        maxLikelihood = 0
        chosenOption = None
        for option in subtitlePage.options:
            subtitleName = self.sanitize(option.name).split(" ")
            subtitleLikelihood = 0
            for token in subtitleName:
                if token in name:
                    subtitleLikelihood += 1
                if (subtitleLikelihood > maxLikelihood):
                    maxLikelihood = subtitleLikelihood
                    chosenOption = option

        return chosenOption
        
    def _requestSubtitle(self, subID):
        params = {"sub_id" : subID}
        return self.urlHandler.request("%s/ajax/sub/guest_time.asp" % self.BASE_URL, params, ajax=True)[0]
        
    def getDownloadLink(self, subID, optionID, persist=True):        
        requestID = self._requestSubtitle(subID)
        
        params = {"sub_id" : subID, "code": optionID, "sh" : "yes", "guest" : requestID, "timewaited" : "16"}

        for i in xrange(16):
            data = self.urlHandler.request("%s/ajax/sub/download.asp" % self.BASE_URL, params, ajax=True)[0]
            if (len(data) != 0 or not persist):
                break
            time.sleep(1)
            
        return (data)
        
    def download(self, downloadLink):
        (data, headers) = self.urlHandler.request("%s%s" % (self.BASE_URL, downloadLink))
        fileName = re.search("filename=(.*)", headers["content-disposition"]).groups()[0]
        return (data, fileName)
        
    def saveData(self, fileName, data, shouldUnzip=True):
        log(__name__ ,"Saving to %s (size %d)" % (fileName, len(data)))
        # Save the downloaded zip file
        with open( fileName,"wb") as f:
            f.write(data)
        
        if shouldUnzip:
            # Unzip the zip file
            zip = zipfile.ZipFile(fileName, "r")
            zip.extractall(os.path.dirname(fileName))
            zip.close()
            # Remove the unneeded zip file
            os.remove(fileName)
            
    def sanitize(self, name):
        return re.sub('[\.\[\]\-]', self.DEFAULT_SEPERATOR, name.upper())

    def getSubtitleMetaData(self, movieName):
        sanitizedName = self.sanitize(movieName)
        log(__name__ , "Searching for %s" % sanitizedName)
        susbtitlePage = self.searchMovieName(sanitizedName)
        if susbtitlePage is None:
            log(__name__ ,"Couldn't find relevant subtitle page")
            return
            
        log(__name__ , "Found relevant meta data")
        return susbtitlePage
        
    def getSubtitleData(self, movieName, resultSubtitleDirectory):
        susbtitlePage = self.getSubtitleMetaData(movieName)
        # Try to choose the most relevant option according to the file name
        chosenOption = self.findChosenOption(susbtitlePage.name, susbtitlePage)
        if chosenOption != None:
            log(__name__ ,"Found the subtitle type - %s" % chosenOption)
        else:
            
            log(__name__ ,"No suitable subtitle found!")
            log(__name__ ,"Available options are:")
            options = enumerate(susbtitlePage.options, start=1)
            for num, option in options:
                log(__name__ ,"\t(%d) %s" % (num, option))
                
            choice = int(raw_input("What subtitle do you want to download? "))
            while (choice < 0 or choice > len(susbtitlePage.options)):
                log(__name__ ,"bad choice")
                choice = int(raw_input("What subtitle do you want to download? "))
        
            chosenOption = susbtitlePage.options[choice-1]

        # Retrieve the download link and download the subtitle
        downloadLink = self.getDownloadLink(susbtitlePage.id, chosenOption.id)
        if (downloadLink == ""):
            log(__name__ ,"Download Unsuccessful!")
            return
        
        (subtitleData, subtitleName) = self.download(downloadLink)
        
        resultSubtitlePath = os.path.join(resultSubtitleDirectory, subtitleName)
        self.saveData(resultSubtitlePath, subtitleData)