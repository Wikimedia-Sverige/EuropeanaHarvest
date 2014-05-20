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
import json

def parseImageInfo(imageJson):
    
#EoF
