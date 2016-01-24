#!/usr/bin/env python
# -*- coding: utf-8 -*-
# vim: ts=2 sw=2 et ai

###############################################################################
# Copyright (c) 2012,2013 Andreas Vogel andreas@wellenvogel.net
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
###############################################################################
VERSION="1.0.2"
import os
import sys
import logging
import optparse
import time
import struct
import math
hasGDAL=1
try:
  import gdal
  import osr
  #raise Exception
except:
  hasGDAL=0
  
info="""
 read atlases created by mobile atlas creator (png and worldfile pwx) and use img2kap to convert them to bsb files
   """
WHITELISTGDAL=(".png",".tiff")
WHITELISTDIRECT=(".png",)


def log(txt):
  logging.info(time.strftime("%Y/%m/%d-%H:%M:%S ",time.localtime())+txt)

def warn(txt):
  logging.warn(time.strftime("%Y/%m/%d-%H:%M:%S ",time.localtime())+txt)


def isInWhitelist(fname,whitelist):
  for be in whitelist:
    if fname.upper().endswith(be.upper()):
      return True
  return False


#-------------------------------------
#read a directory recursively and return the list of files
def readDir(dir,whitelist):
  
  rt=[]
  for f in os.listdir(dir):
  
    path=os.path.join(dir,f)
    if os.path.isfile(path):
      if isInWhitelist(path,whitelist):
        rt.append(path)
      else:
        log("ignore unknown file "+path)  
    elif os.path.isdir(path):
      rt.extend(readDir(path,whitelist))
    else:
      pass
  return rt
#read all charts into a list
def readCharts(args, whitelist):
  chartlist=[]
  for arg in args:
    
    if (os.path.isfile(arg)):
      if isInWhitelist(arg,whitelist):
        fname=os.path.abspath(arg)
        chartlist.append(fname)
      else:
        log("ignore unknown file "+arg)
    elif (os.path.isdir(arg)):
      fname=os.path.abspath(arg)
      chartlist.extend(readDir(fname,whitelist))
    else:
      warn("file/dir "+arg+" not found")
  return chartlist
  
#------------------------------------
def convertChartListGDAL(chartlist):
  
  for chart in chartlist:
  
    dataset = gdal.Open( chart, gdal.GA_ReadOnly )
    if dataset is None:
      warn("gdal cannot handle file "+chart)
      continue
    else:
      log("chart "+chart+" succcessfully opened")
    inosr=osr.SpatialReference()
    outosr=osr.SpatialReference()
    llosr=osr.SpatialReference()
    outosr.SetWellKnownGeogCS("WGS84")
    inosr.ImportFromWkt(dataset.GetProjection())
    if not inosr.IsSameGeogCS(outosr):
      warn(chart+" is not in WGS84, cannot convert")
      continue
    llosr.CopyGeogCSFrom(inosr)
    transformer=osr.CoordinateTransformation(inosr,llosr)
    geotr=dataset.GetGeoTransform()
    (ullon,ullat,z)=transformer.TransformPoint(geotr[0],geotr[3],0)
    (lrlon,lrlat)=gdal.ApplyGeoTransform(geotr,dataset.RasterXSize,dataset.RasterYSize)
    log("raster: ullat=%f ullon=%f lrlat=%f lrlon=%f"% (geotr[3],geotr[0],lrlat,lrlon))
    (lrlon,lrlat,z)=transformer.TransformPoint(lrlon,lrlat,0)
    cmd="imgkap.exe %s %f %f %f %f"% (chart,ullat,ullon,lrlat,lrlon)
    log("running "+cmd)
    os.system(cmd)

#from gdal2tiles.py
#convert meters (world file) to lat/lon
#we strictly assume WGS84 here (no check)
def metersToLonLat(mx,my):
  originShift = 2 * math.pi * 6378137 / 2.0
  lon = (mx / originShift) * 180.0
  lat = (my / originShift) * 180.0
  lat = 180 / math.pi * (2 * math.atan( math.exp( lat * math.pi / 180.0)) - math.pi / 2.0)
  return lon,lat
      
#------------------------------------
def convertChartListDirect(chartlist):
  
  for chart in chartlist:
    log("direct "+chart)
    f=open(chart, "rb")
    if f is None:
      warn("unable to read file "+chart)
      continue
    buf=f.read(24) #read header
    if len(buf) != 24:
      warn("unable to read 24 header bytes for "+chart)
      f.close()
      continue
    (h,png,d1,il,it,pixelw,pixelh)=struct.unpack('!B3s4sI4sII',buf)
    f.close()
    if png != "PNG" or it != "IHDR":
      warn("invalid png header for "+chart+" ignore this one")
      continue
    log(chart+" w="+str(pixelw)+", h="+str(pixelh))
    (base,ext)=os.path.splitext(chart)
    wfile=base+".pgw"
    if not os.path.exists(wfile):
      warn("world file "+wfile+" not found, cannot handle "+chart)
      continue
    content=None
    with open(wfile) as f:
      content = f.readlines()
    if len(content)<6:
      warn("not enoungh lines in "+wfile+" ignore "+chart)
    mppx=float(content[0])
    mppy=float(content[3])
    #not sure why mobac has added/subtracted half a pixel here - but we rely on gdal
    ulx=float(content[4])-0.5*mppx
    uly=float(content[5])-0.5*mppy
    lrx=ulx+mppx*pixelw
    lry=uly+mppy*pixelh
    if ulx > lrx:
      warn("invalid chart format - upper left x %f is larger than lower right x %f, ignore chart %s" % (ulx,lrx,chart))
      continue
    if uly < lry:
      warn("invalid chart format - upper left y %f is lower than lower right y %f, ignore chart %s" % (uly,lry,chart))
      continue
    log(chart+" raster: ullat=%f ullon=%f lrlat=%f lrlon=%f"% (uly,ulx,lry,lrx))
    (ullon,ullat)=metersToLonLat(ulx, uly)
    (lrlon,lrlat)=metersToLonLat(lrx, lry)
    cmd="imgkap.exe %s %f %f %f %f"% (chart,ullat,ullon,lrlat,lrlon)
    log("running "+cmd)
    os.system(cmd)
      
 
def main(argv):
  
  usage="usage: %(prog)s [-n] [-d] [-q] indir|infile..." % { "prog": sys.argv[0]}
  
  parser = optparse.OptionParser(
        usage = usage,
        version="1.0",
        description='read gdal compatible raster maps or png files for bsb creation')
  parser.add_option("-q", "--quiet", action="store_const", 
        const=0, default=1, dest="verbose")
  parser.add_option("-d", "--debug", action="store_const", 
        const=2, dest="verbose")
  parser.add_option("-n", "--nogdal", action="store_const", 
        const=1, dest="nogdal")
  (options, args) = parser.parse_args(argv[1:])
  logging.basicConfig(level=logging.DEBUG if options.verbose==2 else 
      (logging.ERROR if options.verbose==0 else logging.INFO))
  if (len(args) < 1):
    print(usage)
    sys.exit(1)
  log("%s version %s"%(sys.argv[0],VERSION))
  if not hasGDAL == 1 and not options.nogdal==1:
    log("WARNIG: no gdal found, falling back to png only handling")
    options.nogdal=1
  if (not options.nogdal == 1):
    log("running with GDAL")
    cl=readCharts(args, WHITELISTGDAL)
    convertChartListGDAL(cl)
  else:
    warn("running without GDAL - charts must be in WGS84 - no check for this")
    cl=readCharts(args, WHITELISTDIRECT)
    convertChartListDirect(cl)
  log("done")


if __name__ == "__main__":
    main(sys.argv)
