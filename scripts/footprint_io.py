# Python modules
from configobj import ConfigObj
from collections import OrderedDict
import ast
import copy
import csv
import datetime
import dateutil
import logging
import netCDF4
import numpy
import ntpath
import os
import pandas
import pdb
import platform
import sys
import time
import tkinter, tkinter.filedialog
import xlrd
import xlwt
import xlsxwriter
# PyFluxPro modules
#import footprint_cfg
import constants as c
import meteorologicalfunctions as mf
import footprint_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

class DataStructure(object):
    def __init__(self):
        self.series = {}
        self.globalattributes = {}
        self.globalattributes["Functions"] = ""
        self.mergeserieslist = []
        self.averageserieslist = []
        self.returncodes = {"value":0,"message":"OK"}

def load_controlfile(path='.',title='Choose a control file'):
    """
    Purpose:
     Returns a control file object.
    Usage:
     cf = footprint_io.load_controlfile([path=<some_path_to_a_controlfile>],[title=<some title>])
          where path [optional] is the path to a subdirectory
                title [optional] is a title for the file open dialog
                cf is a control file object
    Author: PRI
    Date: Back in the day
    """
    name = get_controlfilename(path=path,title=title)
    cf = get_controlfilecontents(name)
    return cf

def get_outfilenamefromcf(cf):
    path = footprint_utils.get_keyvaluefromcf(cf,["Files"],"file_path",default="")
    name = footprint_utils.get_keyvaluefromcf(cf,["Files"],"out_filename",default="")
    return str(path)+str(name)

def get_controlfilename(path='.',title='Choose a control file'):
    logger.info(' Choosing the control file ')
    root = tkinter.Tk(); root.withdraw()
    name = tkinter.filedialog.askopenfilename(parent=root,initialdir=path,title=title)
    root.destroy()
    return name

def get_controlfilecontents(ControlFileName,mode="verbose"):
    if mode!="quiet": logger.info(' Processing the control file ')
    if len(ControlFileName)!=0:
        cf = ConfigObj(ControlFileName)
        cf['controlfile_name'] = ControlFileName
    else:
        cf = ConfigObj()
    if "Files" in cf:
        if "plot_path" not in list(cf["Files"].keys()):
            cf["Files"]["plot_path"] = "plots/"
    return cf

def nc_open_write(ncFullName,nctype='NETCDF4'):
    """
    Purpose:
     Opens a netCDF file object for writing.  The opened netCDF file
     object is then passed as an argument to footprint_io.nc_write_series, where
     the actual writing of data occurs.
    Usage:
     nc_name = '../Sites/Whroo/Data/Processed/all/Whroo_L4.nc'
     nc_file = footprint_io.nc_open_write(nc_name)
     where nc_name is the ful file name of the netCDF to be written
           nc_file is the returned netCDF file object
    Author: PRI
    Date: Back in the day
    """
    file_name = os.path.split(ncFullName)
    logger.info("Opening netCDF file "+file_name[1])
    try:
        ncFile = netCDF4.Dataset(ncFullName,'w',format=nctype)
    except:
        logger.error(' Unable to open netCDF file '+ncFullName+' for writing')
        ncFile = ''
    return ncFile

def nc_read_series(ncFullName,checktimestep=True,fixtimestepmethod=""):
    """
    Purpose:
     Reads a netCDF file and returns the meta-data and data in a DataStructure.
     The returned data structure is an instance of footprint_io.DataStructure().
     The data structure consists of:
      1) ds.globalattributes
         A dictionary containing the global attributes of the netCDF file.
      2) ds.series
         A dictionary containing the variable data, meta-data and QC flag
         Each variable dictionary in ds.series contains;
         a) ds.series[variable]["Data"]
            A 1D numpy float64 array containing the variable data, missing
            data value is -9999.
         b) ds.series[variable]["Flag"]
            A 1D numpy int32 array containing the QC flag data for this variable.
         c) ds.series[variable]["Attr"]
            A dictionary containing the variable attributes.
    Usage:
     nc_name = footprint_io.get_filename_dialog(path="../Sites/Whroo/Data/Processed/")
     ds = footprint_io.nc_read_series(nc_name)
     where nc_name is the full name of the netCDF file to be read
           ds is the returned data structure
    Side effects:
     This routine checks the time step of the data read from the netCDF file
     against the value of the global attribute "time_step", see footprint_utils.CheckTimeStep.
     If a problem is found with the time step (duplicate records, non-integral
     time steps or gaps) then footprint_utils.FixTimeStep is called to repair the time step.
     Fixing non-integral timne steps requires some user input.  The options are to
     quit ([Q]), interpolate ([I], not implemented yet) or round ([R]).  Quitting
     causes the script to exit and return to the command prompt.  Interpolation
     is not implemented yet but will interpolate the data from the original time
     step to a regular time step.  Rounding will round any non-itegral time steps
     to the nearest time step.
    Author: PRI
    Date: Back in the day
    """
    logger.info(" Reading netCDF file "+ntpath.split(ncFullName)[1])
    netCDF4.default_encoding = 'latin-1'
    ds = DataStructure()
    # check to see if the requested file exists, return empty ds if it doesn't
    if ncFullName[0:4]!="http":
        if not footprint_utils.file_exists(ncFullName,mode="quiet"):
            logger.error(' netCDF file '+ncFullName+' not found')
            raise Exception("nc_read_series: file not found")
    # file probably exists, so let's read it
    ncFile = netCDF4.Dataset(ncFullName,'r')
    # disable automatic masking of data when valid_range specified
    ncFile.set_auto_mask(False)
    # now deal with the global attributes
    gattrlist = ncFile.ncattrs()
    if len(gattrlist)!=0:
        for gattr in gattrlist:
            ds.globalattributes[gattr] = getattr(ncFile,gattr)
    # get a list of the variables in the netCDF file (not their QC flags)
    varlist = [x for x in list(ncFile.variables.keys()) if "_QCFlag" not in x]
    for ThisOne in varlist:
        # skip variables that do not have time as a dimension
        dimlist = [x.lower() for x in ncFile.variables[ThisOne].dimensions]
        if "time" not in dimlist: continue
        # create the series in the data structure
        ds.series[str(ThisOne)] = {}
        # get the data and the QC flag
        data,flag,attr = nc_read_var(ncFile,ThisOne)
        ds.series[ThisOne]["Data"] = data
        ds.series[ThisOne]["Flag"] = flag
        ds.series[ThisOne]["Attr"] = attr
    ncFile.close()
    # make sure all values of -9999 have non-zero QC flag
    # NOTE: the following was a quick and dirty fix for something a long time ago
    #       and needs to be retired
    #footprint_utils.CheckQCFlags(ds)
    # get a series of Python datetime objects
    if "time" in list(ds.series.keys()):
        time,f,a = footprint_utils.GetSeries(ds,"time")
        footprint_utils.get_datetimefromnctime(ds,time,a["units"])
    else:
        footprint_utils.get_datetimefromymdhms(ds)
    # round the Python datetime to the nearest second
    footprint_utils.round_datetime(ds,mode="nearest_second")
    # check the time step and fix it required
    if checktimestep:
        if footprint_utils.CheckTimeStep(ds):
            footprint_utils.FixTimeStep(ds,fixtimestepmethod=fixtimestepmethod)
            # update the Excel datetime from the Python datetime
            footprint_utils.get_xldatefromdatetime(ds)
            # update the Year, Month, Day etc from the Python datetime
            footprint_utils.get_ymdhmsfromdatetime(ds)
    # tell the user when the data starts and ends
    ldt = ds.series["DateTime"]["Data"]
    msg = " Got data from "+ldt[0].strftime("%Y-%m-%d %H:%M:%S")+" to "+ldt[-1].strftime("%Y-%m-%d %H:%M:%S")
    logger.info(msg)
    return ds

def nc_read_var(ncFile,ThisOne):
    """ Reads a variable from a netCDF file and returns the data, the QC flag and the variable
        attribute dictionary.
    """
    # check the number of dimensions
    nDims = len(ncFile.variables[ThisOne].shape)
    if nDims not in [1,3]:
        msg = "nc_read_var: unrecognised number of dimensions ("+str(nDims)
        msg = msg+") for netCDF variable "+ ThisOne
        raise Exception(msg)
    if nDims==1:
        # single dimension
        data = ncFile.variables[ThisOne][:]
        # netCDF4 returns a masked array if the "missing_variable" attribute has been set
        # for the variable, here we trap this and force the array in ds.series to be ndarray
        if numpy.ma.isMA(data): data,dummy = footprint_utils.MAtoSeries(data)
        # check for a QC flag
        if ThisOne+'_QCFlag' in list(ncFile.variables.keys()):
            # load it from the netCDF file
            flag = ncFile.variables[ThisOne+'_QCFlag'][:]
        else:
            # create an empty flag series if it does not exist
            nRecs = numpy.size(data)
            flag = numpy.zeros(nRecs,dtype=numpy.int32)
    elif nDims==3:
        # 3 dimensions
        data = ncFile.variables[ThisOne][:,0,0]
        # netCDF4 returns a masked array if the "missing_variable" attribute has been set
        # for the variable, here we trap this and force the array in ds.series to be ndarray
        # may not be needed after adding ncFile.set_auto_mask(False) in nc_read_series().
        if numpy.ma.isMA(data): data,dummy = footprint_utils.MAtoSeries(data)
        # check for a QC flag
        if ThisOne+'_QCFlag' in list(ncFile.variables.keys()):
            # load it from the netCDF file
            flag = ncFile.variables[ThisOne+'_QCFlag'][:,0,0]
        else:
            # create an empty flag series if it does not exist
            nRecs = numpy.size(data)
            flag = numpy.zeros(nRecs,dtype=numpy.int32)
    # force float32 to float64
    if data.dtype=="float32": data = data.astype(numpy.float64)
    # check for Year, Month etc as int64, force to int32 if required
    if ThisOne in ["Year","Month","Day","Hour","Minute","Second"]:
        if data.dtype=="int64": data = data.astype(numpy.int32)
    # get the variable attributes
    vattrlist = ncFile.variables[ThisOne].ncattrs()
    attr = {}
    if len(vattrlist)!=0:
        for vattr in vattrlist:
            attr[vattr] = getattr(ncFile.variables[ThisOne],vattr)
    return data,flag,attr

def ImportSeries(cf,ds):
    # check to see if there is an Imports section
    if "Imports" not in list(cf.keys()): return
    # number of records
    nRecs = int(ds.globalattributes["nc_nrecs"])
    # get the start and end datetime
    ldt = ds.series["DateTime"]["Data"]
    start_date = ldt[0]
    end_date = ldt[-1]
    # loop over the series in the Imports section
    for label in list(cf["Imports"].keys()):
        import_filename = footprint_utils.get_keyvaluefromcf(cf,["Imports",label],"file_name",default="")
        if import_filename=="":
            msg = " ImportSeries: import filename not found in control file, skipping ..."
            logger.warning(msg)
            continue
        var_name = footprint_utils.get_keyvaluefromcf(cf,["Imports",label],"var_name",default="")
        if var_name=="":
            msg = " ImportSeries: variable name not found in control file, skipping ..."
            logger.warning(msg)
            continue
        ds_import = nc_read_series(import_filename)
        ts_import = ds_import.globalattributes["time_step"]
        ldt_import = ds_import.series["DateTime"]["Data"]
        #dtime = nc.num2date(time[:],time.units,only_use_cftime_datetimes=False,only_use_python_datetimes=True)
        si = footprint_utils.GetDateIndex(ldt_import,str(start_date),ts=ts_import,default=0,match="exact")
        ei = footprint_utils.GetDateIndex(ldt_import,str(end_date),ts=ts_import,default=len(ldt_import)-1,match="exact")
        data = numpy.ma.ones(nRecs)*float(c.missing_value)
        flag = numpy.ma.ones(nRecs)
        data_import,flag_import,attr_import = footprint_utils.GetSeriesasMA(ds_import,var_name,si=si,ei=ei)
        ldt_import = ldt_import[si:ei+1]
        index = footprint_utils.FindIndicesOfBInA(ldt_import,ldt)
        data[index] = data_import
        flag[index] = flag_import
        footprint_utils.CreateSeries(ds,label,data,flag,attr_import)

