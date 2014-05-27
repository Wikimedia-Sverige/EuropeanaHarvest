EuropeanaHarvester
=================

A script for harvesting metadata from Wikimedia Commons for the use in Europeana

Given a (set of) categories on Commons along with templates and matching 
patterns for external links in a json file (see examples in projects folder); 
it queries the Commons API for metadata about the images and follows up 
by investigating the templates used and external links on each filepage. 
The resulting information is outputted to an xml file, per Europeana specifications.

Additionally the data is outputed (along with a few unused fields) as a 
csv to allow for easier analysis/post-processing together with an analysis 
of used categories and a logfile detailing potential problems in the data.

Usage: ```python Europeana.py filename option``` where:

* ```filename``` (required): the (unicode)string relative pathname to the json file for the project
* ```option``` (optional): if set to:
  * ```verbose```: toggles on verbose mode with additional output to the terminal
  *  ```test```: toggles on testing (a verbose and limited run)


Relies on WikiApi which is based on PyCJWiki Version 1.31 (C) by [Smallman12q](https://en.wikipedia.org/wiki/User_talk:Smallman12q) GPL, see http://www.gnu.org/licenses/.
