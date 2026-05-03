# Python modules
from collections import OrderedDict
import copy
import csv
import datetime
import inspect
import logging
import numbers
import os
import platform
import time
import traceback
# 3rd party modules
from configobj import ConfigObj
import cftime
import dateutil
import netCDF4
import numpy
import pandas
from pandas.errors import ParserError
import pytz
import xlwt
import xlsxwriter
from PyQt5 import QtWidgets
# PFP modules
from scripts import cfg
from scripts import constants as c
from scripts import meteorologicalfunctions as pfp_mf
#from scripts import pfp_ck
from scripts import pfp_log
from scripts import pfp_plot
from scripts import pfp_ts
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

class DataStructure(object):
    """
    This is the main data structure used throughout PyFluxPro.

    A data structure is used to hold all of the data and metadata used by
    PyFluxPro during data procssing.  It is basically a representation in
    Python of a netCDF file.

    Creating a data structure:
     A data structure can be created directly using;
      ds = pfp_io.Datastructure()

    Attributes of a data structure:
     ds.root["Attributes"] - a dictionary containing the global attributes read from
                           or written to a netCDF file.
     ds.root["Variables"] - a dictionary containing the variables read from or written to a
                            netCDF file.

    Variables in a data structure:
     Each variable in the ds.root["Variables"] dictionary is another dictionary that
     contains the data, the quality control flag and the attributes.
     For example, the air temperature variable (Ta) is stored in the data
     structure as follows;
      ds.root["Variables"]["Ta"]["Data"] - a 1D numpy array containing the data values
      ds.root["Variables"]["Ta"]["Flag"] - a 1D numpy array containing the quality
                                control flag values
      ds.root["Variables"]["Ta"]["Attr"] - a dictionary containing the variable attributes

    Reading a data structure from file:
     A data structure is returned when a netCDF file is read e.g.;
      ds = pfp_io.NetCDFRead(file_name)
      where file_name is the name of the netCDF file.

    Writing a data structure to file:
     A data structure can be written to a netCDF file using;
      pfp_io.NetCDFWrite(file_name, ds)
      where file_name is the name of the netCDF file to be created
            ds is the data structure to be written to the file

    Accessing variables in a data structure:
     Variables in a data structure can be accessed using the GetVariable
     helper function as follows;
      Ta = pfp_utils.GetVariable(ds, "Ta")
     where "Ta" is the label of the variable.
           ds is the data structure containing the variable.
           Ta is a dictionary containing the data, quality control flag
              and attributes for the air temperature.

    Useful functions:
     pfp_utils.GetVariable(ds, label)
     pfp_utils.CreateVariable(ds, variable)

    Date: Way back in the day
    Author: PRI
    """
    def __init__(self, groups=[], global_attributes={}):
        assert isinstance(groups, list), "groups must be list"
        assert isinstance(global_attributes, dict), "global_attributes must be dict"
        self.info = {"returncodes": {"value": 0,"message": "OK"},
                      "filepath": "", "groups": ["root"],
                      "mergeserieslist": [],
                      "averageserieslist": [],
                      "intermediate": []}
        self.root = {"Attributes": copy.deepcopy(global_attributes), "Variables": {}}
        if len(groups) != 0:
            for group in groups:
                setattr(self, group, {"Attributes": {}, "Variables": {}})
                self.info["groups"].append(group)

def CheckTimeStamps(dfs, l1_info, fix=True):
    """
    Purpose:
     Check the timestamps of the Excel worksheets or CSV file read at
     L1 for a range of anomalies.  The checks are:
      - timestamps that are non-integral with respect to the time step
      - duplicate timestamps
      - time steps less than the specified time step
      - time steps greater than 3 hours
      - time steps greater than 1 day
     If any timestamps that fail these checks are detected this function
     will print warning messages to the log window and produce 1 plot per
     worksheet showing a time series of the time step and a histogram
     of the the time step distribution.
    Usage:
    Side effects:
     If the optional argument fix=True, this function will delete rows
     with timestamps that are not an integral of the time step specified
     in the global attributes and rows with duplicate timestamps.
    Author: PRI
    Date: August 2023
    """
    ts = l1_info["read_excel"]["Global"]["time_step"]
    if isinstance(ts, str):
        if ts in ["daily", "weekly", "monthly", "yearly"]:
            # summary time steps, return without checking
            return
        elif ts in ["30", "60"]:
            ts = int(float(ts))
        else:
            msg = "  Time step must be one of '30', '60', 'daily','weekly', 'monthly', 'yearly'"
            logger.error(msg)
            return
    elif isinstance(ts, numbers.Number):
        ts = int(float(ts))
        if ts not in [30, 60]:
            msg = "  Time step must be either 30 or 60"
            logger.error(msg)
            return
    results = {}
    sheets = list(dfs.keys())
    msg = " Checking timestamps on sheets " + ",".join(sheets)
    logger.info(msg)
    for sheet in sheets:
        indices = checktimestamps_get_indices(dfs[sheet], l1_info)
        results[sheet] = indices
        if ((len(indices["non_monotonic"]) > 0) or
            (len(indices["non_integral"]) > 0) or
            (len(indices["duplicates"]) > 0) or
            (len(indices["greaterthan_3hours"]) > 0) or
            (len(indices["greaterthan_1day"]) > 0)):
            pfp_plot.checktimestamps_plots(dfs[sheet], sheet, l1_info)
        if fix and (len(indices["non_monotonic"]) == 0):
            dfs[sheet] = checktimestamps_drop_rows(dfs[sheet], indices)
        elif (len(indices["non_monotonic"]) > 0):
            msg = "  Timestamp does not increase monotonically on sheet " + sheet
            logger.error(msg)
            msg = "  Sheet " + sheet + " will not be processed!!!"
            logger.error(msg)
            dfs.pop(sheet)
        else:
            pass
    # check to see if any sheets remain to be processed
    sheets = list(dfs.keys())
    if len(sheets) == 0:
        msg = "No sheets or files to process after timestamp checks"
        logger.error(msg)
        raise RuntimeError(msg)
    lg = [results[s]["longest_gap"] for s in sheets]
    max_lg = max(lg)
    if max_lg != ts:
        if max_lg > 1440:
            value = round(max_lg/1440, 1)
            units = "days"
        else:
            value = int(max_lg)
            units = "minutes"
        msg = "  The longest gap is " + str(value) + " " + units + " on sheet "
        msg += sheets[lg.index(max_lg)]
        logger.info(msg)
    return

def checktimestamps_get_indices(df, l1_info):
    ts = int(l1_info["read_excel"]["Global"]["time_step"])
    indices = {}
    # timestamp from data frame index
    dt = df.index.values
    # time step in minutes
    ddt = numpy.diff(dt).astype('timedelta64[s]').astype(int)/60
    indices["non_monotonic"] = numpy.where(ddt < 0)[0]
    if len(indices["non_monotonic"]) > 0:
        msg = "  Number of negative time steps: " + str(len(indices["non_monotonic"]))
        logger.error(msg)
    dt_mod = numpy.mod(ddt, ts)
    indices["non_integral"] = numpy.where(dt_mod != 0)[0]
    if len(indices["non_integral"]) != 0:
        msg = "  Number of non-integral time steps: " + str(len(indices["non_integral"]))
        logger.warning(msg)
    indices["duplicates"] = numpy.where(ddt == 0)[0]
    if len(indices["duplicates"]) != 0:
        msg = "  Number of duplicate timestamps: " + str(len(indices["duplicates"]))
        logger.warning(msg)
    indices["lessthan_timestep"] = numpy.where((ddt > 0) & (ddt < ts))[0]
    if len(indices["lessthan_timestep"]) != 0:
        msg = "  Number of time steps less than " + str(ts) + " minutes: "
        msg += str(len(indices["lessthan_timestep"]))
        logger.warning(msg)
    indices["equalto_timestep"] = numpy.where(ddt == ts)[0]
    if len(indices["equalto_timestep"]) != 0:
        msg = "  Number of time steps equal to " + str(ts) + " minutes: "
        msg += str(len(indices["equalto_timestep"]))
        #logger.info(msg)
    indices["greaterthan_3hours"] = numpy.where(ddt >= 180)[0]
    if len(indices["greaterthan_3hours"]) != 0:
        msg = "  Number of gaps greater than 3 hours: " + str(len(indices["greaterthan_3hours"]))
        logger.warning(msg)
    indices["greaterthan_1day"] = numpy.where(ddt >= 1440)[0]
    if len(indices["greaterthan_1day"]) != 0:
        msg = "  Number of gaps greater than 1 day: " + str(len(indices["greaterthan_1day"]))
        logger.warning(msg)
    indices["longest_gap"] = numpy.max(ddt)
    return indices

def checktimestamps_drop_rows(df, indices):
    if len(indices["non_integral"]) != 0:
        n = len(indices["non_integral"])
        msg = " Removing " + str(n) + " rows with non-integral time steps"
        logger.info(msg)
        index_name = df.index.name
        df = df.reset_index()
        df = df.drop(indices["non_integral"])
        df.set_index(index_name, inplace=True)
    if len(indices["duplicates"]) != 0:
        n = len(indices["duplicates"])
        msg = " Removing " + str(n) + " rows with duplicate time steps"
        logger.info(msg)
        index_name = df.index.name
        df = df.reset_index()
        df = df.drop(indices["duplicates"])
        df.set_index(index_name, inplace=True)
    return df

def coerce_to_numeric(value):
    if isinstance(value, numbers.Number):
        return value
    else:
        return numpy.nan

def copy_datastructure(cf,ds_in):
    '''
    Return a copy of a data structure based on the following rules:
     1) if the netCDF file at the "copy_to" level does not exist
        then copy the existing data structure at the "input" level
        to create a new data structure at the "output" level.
    '''
    # assumptions that need to be checked are:
    #  - the start datetime of the two sets of data are the same
    #  - the end datetime of the L3 data is the same or after the
    #    end datetime of the the L4 data
    #    - if the end datetimes are the same then we are just re-processing something
    #    - if the end datetime for the L3 data is after the end date of the L4 data
    #      then more data has been added to this year and the user wants to gap fill
    #      the new data
    # modificatons to be made:
    #  - check the modification datetime of the L3 and L4 files:
    #     - if the L3 file is newer than the L4 file the disregard the "UseExistingOutFile" setting
    # get the output (L4) file name
    ct_filename = cf['Files']['file_path']+cf['Files']['out_filename']
    # if the L4 file does not exist then create the L4 data structure as a copy
    # of the L3 data structure
    if not os.path.exists(ct_filename):
        ds_out = copy.deepcopy(ds_in)
    # if the L4 file does exist ...
    if os.path.exists(ct_filename):
        # check to see if the user wants to use it
        if pfp_utils.get_keyvaluefromcf(cf,["Options"],"UseExistingOutFile",default="No")!='Yes':
            # if the user doesn't want to use the existing L4 data then create
            # the L4 data structure as a copy of the L3 data structure
            ds_out = copy.deepcopy(ds_in)
        else:
            # the user wants to use the data from an existing L4 file
            # get the netCDF file name at the "input" level
            outfilename = get_outfilenamefromcf(cf)
            # read the netCDF file at the "input" level
            ds_file = NetCDFRead(outfilename)
            if ds_file.info["returncodes"]["value"] != 0: return
            dt_file = ds_file.root["Variables"]['DateTime']['Data']
            sd_file = str(dt_file[0])
            ed_file = str(dt_file[-1])
            # create a copy of the data
            ds_out = copy.deepcopy(ds_in)
            dt_out = ds_out.root["Variables"]['DateTime']['Data']
            ts = ds_out.root["Attributes"]['time_step']
            # get the start and end indices based on the start and end dates
            si = pfp_utils.GetDateIndex(dt_out,sd_file,ts=ts,default=0,match='exact')
            ei = pfp_utils.GetDateIndex(dt_out,ed_file,ts=ts,default=-1,match='exact')
            # now replace parts of ds_out with the data read from file
            for ThisOne in list(ds_file.root["Variables"].keys()):
                # check to see if the L4 series exists in the L3 data
                if ThisOne in list(ds_out.root["Variables"].keys()):
                    # ds_out is the copy of the L3 data, now fill it with the L4 data read from file
                    ds_out.root["Variables"][ThisOne]['Data'][si:ei+1] = ds_file.root["Variables"][ThisOne]['Data']
                    ds_out.root["Variables"][ThisOne]['Flag'][si:ei+1] = ds_file.root["Variables"][ThisOne]['Flag']
                else:
                    # if it doesn't, create the series and put the data into it
                    ds_out.root["Variables"][ThisOne] = {}
                    ds_out.root["Variables"][ThisOne] = ds_file.root["Variables"][ThisOne].copy()
                    # check to see if we have to append data to make the copy of the L4 data now
                    # in the L3 data structure the same length as the existing L3 data
                    nRecs_file = int(ds_file.root["Attributes"]['nc_nrecs'])
                    nRecs_out = int(ds_out.root["Attributes"]['nc_nrecs'])
                    if nRecs_file < nRecs_out:
                        # there is more data at L3 than at L4
                        # append missing data to make the series the same length
                        nRecs_append = nRecs_out - nRecs_file
                        data = numpy.array([c.missing_value]*nRecs_append,dtype=numpy.float64)
                        flag = numpy.ones(nRecs_append,dtype=numpy.int32)
                        ds_out.root["Variables"][ThisOne]['Data'] = numpy.concatenate((ds_out.root["Variables"][ThisOne]['Data'],data))
                        ds_out.root["Variables"][ThisOne]['Flag'] = numpy.concatenate((ds_out.root["Variables"][ThisOne]['Flag'],flag))
                    elif nRecs_file > nRecs_out:
                        # tell the user something is wrong
                        logger.error('copy_datastructure: L3 file contains less data than L4 file')
                        # return an empty dictionary
                        ds_out = {}
                    else:
                        # nRecs_file and nRecs_out are equal so we do not need to do anything
                        pass
    return ds_out

def csv_read_parse_cf(cf):
    info = {"cf_ok":False}
    if "DateTime" not in cf["Variables"]:
        msg = "No [[DateTime]] section in control file ..."
        logger.error(msg)
        return info
    if "Function" not in cf["Variables"]["DateTime"]:
        msg = "No [[[Function]]] section in [[DateTime]] section ..."
        logger.error(msg)
        return info
    # get the filename, return if missing or doesn't exist
    csv_filename = get_infilenamefromcf(cf)
    if len(csv_filename)==0:
        msg = ' in_filename not found in control file'
        logger.error(msg)
        return info
    if not os.path.exists(csv_filename):
        msg = ' Input file '+csv_filename+' specified in control file not found'
        logger.error(msg)
        return info
    else:
        info["csv_filename"] = csv_filename

    # get the header row, first data row and units row
    opt = pfp_utils.get_keyvaluefromcf(cf,["Files"],"in_firstdatarow",default=2)
    info["first_data_row"] = int(opt)
    info["skip_header"] = info["first_data_row"]-1
    opt = pfp_utils.get_keyvaluefromcf(cf,["Files"],"in_headerrow",default=1)
    info["header_row"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf,["Files"],"in_unitsrow",default=-1)
    info["units_row"] = int(opt)
    # set the delimiters
    info["delimiters"] = [",", "\t"]

    # sniff the file to find out the dialect and the delimiter
    csv_file = open(info["csv_filename"],'r')
    # skip to the header row
    for i in range(0, info["first_data_row"]):
        line = csv_file.readline().strip()
        if i == info["header_row"]-1 or i == info["units_row"]-1:
            # sniff the CSV dialect
            info["dialect"] = csv.Sniffer().sniff(line, info["delimiters"])
        if i == info["header_row"]-1:
            info["header_line"] = line
            # header line from comma separated string to list
            info["header_list"] = info["header_line"].split(info["dialect"].delimiter)
        if i == info["units_row"]-1:
            info["units_line"] = line
            # units line from comma separated string to list
            info["units_list"] = info["units_line"].split(info["dialect"].delimiter)
    csv_file.close()
    # get a list of series to be read from CSV file and check
    # to make sure the requested variables are in the csv file,
    # dump them if they aren't
    csv_varnames = {}
    for item in list(cf["Variables"].keys()):
        if "csv" in list(cf["Variables"][item].keys()):
            opt = pfp_utils.get_keyvaluefromcf(cf, ["Variables", item, "csv"], "name", default="")
            if opt in info["header_line"]:
                csv_varnames[item] = str(opt)
            else:
                msg = "  "+str(opt)+" not found in CSV file, skipping ..."
                logger.error(msg)
                continue
        elif "xl" in list(cf["Variables"][item].keys()):
            opt = pfp_utils.get_keyvaluefromcf(cf, ["Variables", item, "xl"], "name", default="")
            if opt in info["header_line"]:
                csv_varnames[item] = str(opt)
            else:
                msg = "  "+str(opt)+" not found in CSV file, skipping ..."
                logger.error(msg)
                continue
        elif "Function" not in list(cf["Variables"][item].keys()):
            msg = " No csv or Function section in control file for "+item
            logger.info(msg)
            continue
    info["csv_varnames"] = csv_varnames
    info["var_list"] = list(csv_varnames.keys())
    info["csv_list"] = [csv_varnames[x] for x in info["var_list"]]
    info["col_list"] = [info["header_list"].index(item) for item in info["csv_list"]]

    # define the missing values and the value with which to fill them
    info["missing_values"] = "NA,N/A,NAN,NaN,nan,#NAME?,#VALUE!,#DIV/0!,#REF!,Infinity,-Infinity"
    info["filling_values"] = c.missing_value
    info["deletechars"] = set("""~!@#$%^&=+~|]}[{';: ?.>,<""")

    info["cf_ok"] = True

    return info

def csv_read_series(cf):
    """
    Purpose:
     Reads a CSV file and returns the data in a data structure.
    Usage:
     ds = csv_read_series(cf)
     where cf is a control file
           ds is a data structure
    Author: PRI
    Date: September 2015
    Mods: February 2018 (PRI) - rewrite
    """
    # get a data structure
    ds = DataStructure()
    # add the global atributes
    for gattr in list(cf['Global'].keys()):
        ds.root["Attributes"][gattr] = cf['Global'][gattr]
    # parse the control file
    info = csv_read_parse_cf(cf)
    # return with an empty data structure if parsing failed
    if not info["cf_ok"]:
        return ds
    # read the csv file using numpy's genfromtxt
    file_name = os.path.split(info["csv_filename"])
    msg = " Reading " + file_name[1]
    logger.info(msg)
    # read the CSV file
    data_array = numpy.genfromtxt(info["csv_filename"], delimiter=info["dialect"].delimiter,
                                  skip_header=info["skip_header"], names=info["header_line"],
                                  usecols=info["col_list"], missing_values=info["missing_values"],
                                  filling_values=info["filling_values"], deletechars=info["deletechars"],
                                  usemask=True, dtype=None)
    # get the variables and put them into the data structure
    # we'll deal with DateTime separately
    for item in ["DateTime"]:
        if item in info["var_list"]:
            info["var_list"].remove(item)
    # put the data into the data structure
    for label in info["var_list"]:
        csv_label = info["csv_varnames"][label]
        variable = {"Label":label}
        # make the flag
        flag = numpy.zeros(len(data_array[csv_label]), dtype=numpy.int32)
        # get the data
        try:
            data = numpy.array(data_array[info["csv_varnames"][label]], dtype=numpy.float64)
            idx = numpy.where(numpy.isfinite(data) == False)[0]
            data[idx] = numpy.float64(c.missing_value)
            flag[idx] = numpy.int32(1)
        except ValueError:
            data = data_array[info["csv_varnames"][label]]
        # set flag of missing data to 1
        missing = numpy.full_like(data, c.missing_value)
        idx = numpy.where(data == missing)[0]
        flag[idx] = numpy.int32(1)
        variable["Data"] = data
        variable["Flag"] = flag
        # make the attribute dictionary ...
        variable["Attr"] = {}
        for attr in list(cf["Variables"][label]["Attr"].keys()):
            variable["Attr"][attr] = cf["Variables"][label]["Attr"][attr]
        pfp_utils.CreateVariable(ds, variable)
    ## call the function given in the control file to convert the date/time string to a datetime object
    ## NOTE: the function being called needs to deal with missing date values and empty lines
    #function_string = cf["Variables"]["DateTime"]["Function"]["func"]
    #function_name = function_string.split("(")[0]
    #function_args = function_string.split("(")[1].replace(")","").split(",")
    #result = getattr(pfp_func_units,function_name)(ds, *function_args)
    # set some global attributes
    ds.root["Attributes"]['featureType'] = 'timeseries'
    ds.root["Attributes"]['csv_filename'] = info["csv_filename"]
    ds.root["Attributes"]['xl_datemode'] = str(0)
    s = os.stat(info["csv_filename"])
    t = time.localtime(s.st_mtime)
    ds.root["Attributes"]['csv_moddatetime'] = str(datetime.datetime(t[0],t[1],t[2],t[3],t[4],t[5]))
    ds.info["returncodes"] = {"value":0,"message":"OK"}
    return ds

def DataFrameToDataStructure(df, l1_info):
    """
    Purpose:
     Convert a pandas data frame to a PFP data structure and add the metadata
     from the control file.
    """
    msg = " Converting data frame to data structure"
    logger.info(msg)
    l1ire = l1_info["read_excel"]
    # create a data structure
    ds = DataStructure()
    # add the global attributes to the data structure
    ds.root["Attributes"] = copy.deepcopy(l1ire["Global"])
    # get the number of records in the data frame
    nrecs = len(df.index.values)
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    ones = numpy.ones(nrecs, dtype=numpy.int32)
    ds.root["Attributes"]["nc_nrecs"] = nrecs
    # put the datetime index into the data structure
    var = pfp_utils.CreateEmptyVariable("DateTime", nrecs)
    # convert from numpy.datetime[ns] to Python datetime
    var["Data"] = df.index.to_pydatetime()
    var["Flag"] = zeros
    var["Attr"] = {"long_name": "Datetime in local timezone",
                   "cf_role": "timeseries_id"}
    pfp_utils.CreateVariable(ds, var)
    # now do the other variables
    labels = list(df)
    for label in labels:
        var = pfp_utils.CreateEmptyVariable(label, nrecs)
        data = df[label].apply(coerce_to_numeric).to_numpy()
        # mask non-finite records
        mask = numpy.isfinite(data)
        var["Data"] = numpy.ma.masked_where(mask == False, data)
        # mask values == c.missing_value
        var["Data"] = numpy.ma.masked_values(var["Data"], c.missing_value)
        # set the QC flag to 1 for masked data
        mask = numpy.ma.getmaskarray(var["Data"])
        var["Flag"] = numpy.where(mask == False, zeros, ones)
        var["Attr"] = l1ire["Variables"][label]["Attr"]
        pfp_utils.CreateVariable(ds, var)
    return ds

def nc_2xls(ncfilename, outputlist=None):
    # read the netCDF file
    ds = NetCDFRead(ncfilename,checktimestep=False)
    if ds.info["returncodes"]["value"] != 0: return
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    nCols = len(list(ds.root["Variables"].keys()))
    if outputlist!=None: nCols = len(outputlist)
    # xlwt seems to only handle 225 columns
    if nRecs<65535 and nCols<220:
        # write the variables to the Excel 97/2003 file
        xlsfilename= ncfilename.replace(".nc", ".xls")
        if os.path.isfile(xlsfilename):
            file_path = os.path.split(xlsfilename)
            xlsfilename = get_output_filename_dialog(file_path=file_path[0], ext="*.xls")
            if len(xlsfilename) == 0: return
        xl_write_series(ds, xlsfilename, outputlist=outputlist)
    else:
        # write the variables to the Excel 2010 file
        xlsxfilename= ncfilename.replace(".nc", ".xlsx")
        if os.path.isfile(xlsxfilename):
            file_path = os.path.split(xlsxfilename)
            xlsxfilename = get_output_filename_dialog(file_path=file_path[0], ext="*.xlsx")
            if len(xlsxfilename) == 0: return
        xlsx_write_series(ds, xlsxfilename, outputlist=outputlist)
    return

def PadDataStructure(ds_original, pad_to="whole_years"):
    """
    Purpose:
     Pad a data structure so that it starts and ends on a whole year,
     a whole month or a whole day.
     Only whole year is implemented at present.
    Usage:
    Side effects:
    Author: PRI
    Date: May 2022
    """
    # get the time step as a time delta object
    ts = int(ds_original.root["Attributes"]["time_step"])
    dts = datetime.timedelta(minutes=ts)
    # get the original datetime and the start and end year
    ldt_original = pfp_utils.GetVariable(ds_original, "DateTime")
    start_year = ldt_original["Data"][0].year
    end_year = ldt_original["Data"][-1].year
    # get the padding option
    if pad_to == "whole_years":
        # pad to whole years
        # get the start and end datetimes of the padded data structure
        start_date = datetime.datetime(start_year, 1, 1, 0, 0, 0) + dts
        end_date = datetime.datetime(end_year+1, 1, 1, 0, 0, 0)
    else:
        msg = "PadDataStructure: unrecognised pad_to option "
        msg += "(" + pad_to + ")"
        raise RuntimeError(msg)
    # create the padded data structure
    ds_padded = DataStructure()
    # copy over the global attributes
    for gattr in list(ds_original.root["Attributes"].keys()):
        ds_padded.root["Attributes"][gattr] = ds_original.root["Attributes"][gattr]
    # update the start and end datetime global attributes
    ds_padded.root["Attributes"]["time_coverage_start"] = start_date.strftime("%Y-%m-%d %H:%M")
    ds_padded.root["Attributes"]["time_coverage_end"] = end_date.strftime("%Y-%m-%d %H:%M")
    # greate a datetime series between the padded start and end datetimes
    dt_padded = numpy.array([d for d in pfp_utils.perdelta(start_date, end_date, dts)])
    # get the number of records
    nrecs_padded = len(dt_padded)
    # update the number of records global attribute
    ds_padded.root["Attributes"]["nc_nrecs"] = nrecs_padded
    # create the padded datetime variable
    ldt_padded = {"Label": "DateTime",
                  "Data": dt_padded,
                  "Flag": numpy.zeros(nrecs_padded),
                  "Attr": {"long_name": "Datetime in local timezone",
                           "units": "",
                           "calendar": "gregorian"}}
    # put the padded datetime variable into the padded datastructure
    pfp_utils.CreateVariable(ds_padded, ldt_padded)
    # generate the netCDF time variable
    pfp_utils.get_nctime_from_datetime(ds_padded)
    # get the indices of matching elements
    idx_original, idx_padded = pfp_utils.FindMatchingIndices(ldt_original["Data"],
                                                             ldt_padded["Data"])
    # get the variable labels in the original datastructure
    labels_original = list(ds_original.root["Variables"].keys())
    # remove DateTime and time labels, these are done separately
    for label in ["DateTime", "time"]:
        if label in labels_original:
            labels_original.remove(label)
    # loop over variables, copy to padded datastructure
    for label in labels_original:
        # read the original variable
        var_original = pfp_utils.GetVariable(ds_original, label)
        # create an empty variable
        var_padded = pfp_utils.CreateEmptyVariable(label, nrecs_padded)
        # copy contents from original to padded variable
        var_padded["Label"] = var_original["Label"]
        var_padded["Data"][idx_padded] = var_original["Data"][idx_original]
        var_padded["Flag"][idx_padded] = var_original["Flag"][idx_original]
        var_padded["Attr"] = var_original["Attr"]
        # put the variable into the padded datastructure
        pfp_utils.CreateVariable(ds_padded, var_padded)
    return ds_padded

def ReadCSVFile(l1_info):
    """
    Purpose:
     Read the requested CSV file.
    Usage:
    Side effects:
    Author: PRI
    Date: February 2021
    """
    l1ire = l1_info["read_excel"]
    # dictionary to hold pandas data frames
    dfs = {}
    # get the input file name, header row and first data row numbers
    file_names = l1ire["Files"]["in_filename"].split(",")
    in_header_rows = l1ire["Files"]["in_headerrow"].split(",")
    first_data_rows = l1ire["Files"]["in_firstdatarow"].split(",")
    all_csv_labels = []
    found_csv_labels = []
    for n, file_name in enumerate(file_names):
        msg = " Reading CSV file " + file_name
        logger.info(msg)
        file_uri = os.path.join(l1ire["Files"]["file_path"], file_name)
        header_row_number = int(in_header_rows[n]) - 1
        first_data_row = int(first_data_rows[n]) - 1
        # set up some pandas read_csv options
        skiprows = list(range(first_data_row))
        if header_row_number in skiprows:
            skiprows.remove(header_row_number)
        engine = "python"
        na_values = ["NAN"]
        # read the CSV file
        df = pandas.read_csv(file_uri, delimiter=",",
                             engine=engine, header=0,
                             skiprows=skiprows,
                             na_values=na_values,
                             skip_blank_lines=False)
        # check the requested variables are in the file
        headers = list(df)
        # list of csv variable names
        csv_labels = []
        # dictionary of csv to nc name mapping
        column_name_map = {}
        for nc_label in list(l1ire["Variables"].keys()):
            csv_label = l1ire["Variables"][nc_label]["csv"]["name"]
            all_csv_labels.append(csv_label)
            if csv_label in headers:
                csv_labels.append(csv_label)
                found_csv_labels.append(csv_label)
                column_name_map[csv_label] = nc_label
            else:
                pass
        # remove duplicate CSV labels
        csv_labels = list(set(csv_labels))
        # check for a timestamp
        # are we dealing with a FluxNet or AmeriFlux HH or WW file?
        if ("TIMESTAMP_END" in headers):
            # if so, we use the timestamp at the end of the period
            df["TIMESTAMP"] = pandas.to_datetime(df["TIMESTAMP_END"].astype("string"),
                                                 errors="raise")
        # are we dealing with a FluxNet or AmeriFlux DD, MM or YY file?
        elif ("TIMESTAMP" in headers):
            ndigits = len(str(df["TIMESTAMP"].values[0]))
            if ndigits == 8:
                # it's a DD file
                df["TIMESTAMP"] = pandas.to_datetime(df["TIMESTAMP"].astype("string"), errors="raise")
            elif ndigits == 6:
                # it's an MM file
                df["TIMESTAMP"] = pandas.to_datetime(df["TIMESTAMP"].astype("string"),
                                                     format="%Y%m", errors="raise")
            elif ndigits == 4:
                # it's a YY file
                df["TIMESTAMP"] = pandas.to_datetime(df["TIMESTAMP"].astype("string"),
                                                     format="%Y", errors="raise")
            else:
                msg = "  Unrecognised TIMESTAMP format in CSV file"
                logger.error(msg)
                raise RuntimeError(msg)
        # maybe an EddyPro output file?
        elif (("date" in headers) and ("time" in headers)):
            # date and time in separate columns, time at end of the period
            df["TIMESTAMP"] = pandas.to_datetime(df["date"].astype('string')+" "+df["time"].astype('string'),
                                                 errors="raise")
        # try and automatically find a timestamp
        else:
            # otherwise, try and automatically detect the datetime column
            df = df.apply(lambda col: pandas.to_datetime(col, dayfirst=True, errors='ignore')
                          if col.dtypes == object
                          else col,
                          axis=0)
        # check that we found a datetime column
        timestamps = list(df.select_dtypes(include=['datetime64']))
        if len(timestamps) < 1:
            msg = " Did not find a time stamp for file " + file_name + ", aborting ..."
            logger.error(msg)
            return {0: pandas.DataFrame()}
        elif len(timestamps) > 1:
            msg = " More than 1 time stamp found for file " + file_name + ", using " + timestamps[0]
            logger.warning(msg)
        else:
            pass
        # choose the first datetime column
        timestamp = timestamps[0]
        # set the data frame index to the time stamp
        df.set_index(timestamp, inplace=True)
        # round the datetime index to the nearest second
        df.index = df.index.round('1s')
        # drop columns except those wanted by the user
        df = df[csv_labels]
        # coerce all columns with dtype "object" to "float64"
        cols = df.columns[df.dtypes.eq(object)]
        df[cols] = df[cols].apply(pandas.to_numeric, errors='coerce')
        # rename the data frame columns
        dfs[file_name] = df.rename(columns=column_name_map)
    # check to see if any variables were not found in the CSV files
    for item in all_csv_labels:
        if item not in found_csv_labels:
            msg = " " + item + " not found in input files, skipped ..."
            logger.warning(msg)
    # return a dictionary to be compatible with ReadExcelWorkbook
    return dfs

def ReadExcelWorkbook(l1_info):
    """
    Purpose:
     Read the requested sheets and variables from the Excel workbook.
    Usage:
    Side effects:
     Returns a dictionary of pandas data frames, 1 entry per worksheet.
    Author: PRI
    Date: February 2021
    """
    l1ire = l1_info["read_excel"]
    # get the worksheets named in the control file
    labels = list(l1ire["Variables"].keys())
    nc_labels = [l for l in labels if "xl" in l1ire["Variables"][l]]
    xl_sheets_requested = [l1ire["Variables"][l]["xl"]["sheet"] for l in nc_labels]
    xl_sheets_requested = list(set(xl_sheets_requested))
    # get the input file extension
    file_extension = os.path.splitext(l1_info["read_excel"]["Files"]["in_filename"])
    # choose the Excel engine based on the file extension
    engine = "openpyxl"
    if file_extension[1].lower() == ".xls":
        engine = "xlrd"
    # get the Excel file name
    basename = os.path.basename(l1ire["Files"]["in_filename"])
    msg = " Reading Excel workbook " + basename
    logger.info(msg)
    file_name = os.path.join(l1ire["Files"]["file_path"],
                             l1ire["Files"]["in_filename"])
    # get the header and first data row
    header_row_number = int(l1ire["Files"]["in_headerrow"]) - 1
    first_data_row = int(l1ire["Files"]["in_firstdatarow"]) - 1
    skiprows = list(range(header_row_number+1, first_data_row))
    na_values = ["NAN"]
    # check that the requested sheets are available in the Excel file
    # open the Excel file
    xl_file = pandas.ExcelFile(file_name, engine=engine)
    # get the available sheets
    xl_sheets_available = xl_file.sheet_names
    # remove requested sheets that are not in the Excel file
    for xl_sheet in list(xl_sheets_requested):
        if xl_sheet not in xl_sheets_available:
            msg = " Sheet " + xl_sheet + " not in " + basename + ", skipping ..."
            logger.warning(msg)
            xl_sheets_requested.remove(xl_sheet)
    if len(xl_sheets_requested) == 0:
        msg = " No requested sheets found in " + basename
        logger.error(msg)
        raise RuntimeError(msg)
    # read the Excel file
    dfs = pandas.read_excel(xl_file, sheet_name=xl_sheets_requested,
                            engine=engine, header=header_row_number,
                            skiprows=skiprows,
                            na_values=na_values)
    xl_sheets_present = list(dfs.keys())
    l1ire["xl_sheets"] = {}
    # get the labels of variables in the netCDF file
    # need to add check for duplicate variables on multiple sheets
    nc_labels = [l for l in labels if "xl" in l1ire["Variables"][l]]
    for nc_label in nc_labels:
        xl_sheet = l1ire["Variables"][nc_label]["xl"]["sheet"]
        xl_label = l1ire["Variables"][nc_label]["xl"]["name"]
        if xl_sheet not in xl_sheets_present:
            msg = " Sheet " + xl_sheet + " (" + xl_label + ") not found in workbook, skipping "
            msg += nc_label + " ..."
            logger.warning(msg)
            del l1ire["Variables"][nc_label]
            continue
        if xl_sheet not in l1ire["xl_sheets"]:
            l1ire["xl_sheets"][xl_sheet] = {"DateTime": "", "xl_labels":{}, "nc_labels":{}}
        l1ire["xl_sheets"][xl_sheet]["xl_labels"][xl_label] = nc_label
        l1ire["xl_sheets"][xl_sheet]["nc_labels"][nc_label] = xl_label
    # check the requested variables are on the specified sheets
    for xl_sheet in list(l1ire["xl_sheets"].keys()):
        headers = list(dfs[xl_sheet])
        for xl_label in list(l1ire["xl_sheets"][xl_sheet]["xl_labels"].keys()):
            if xl_label not in headers:
                msg = " Variable " + xl_label + " not found on sheet " + xl_sheet + ", skipping ..."
                logger.warning(msg)
                nc_label = l1ire["xl_sheets"][xl_sheet]["xl_labels"][xl_label]
                del l1ire["xl_sheets"][xl_sheet]["xl_labels"][xl_label]
                del l1ire["xl_sheets"][xl_sheet]["nc_labels"][nc_label]
    df_names = sorted(list(dfs))
    for df_name in df_names:
        # get the column name of the timestamp
        timestamp = read_excel_workbook_get_timestamp(dfs, df_name, l1_info)
        if timestamp is None:
            continue
        # remove rows with no timestamp
        # time stamp as an array
        lts = dfs[df_name][timestamp].to_numpy()
        # boolean array of true/false if not a time
        idx = numpy.isnat(lts)
        # indices of recognised time stamps
        idx_ok = numpy.where(idx == False)[0]
        # drop rows with no time stamp
        dfs[df_name] = dfs[df_name].loc[dfs[df_name].index[idx_ok]]
        # set the data frame index to the time stamp
        dfs[df_name].set_index(timestamp, inplace=True)
        # round the datetime index to the nearest second
        dfs[df_name].index = dfs[df_name].index.round('1s')
        # drop columns except those wanted by the user
        dfs[df_name] = dfs[df_name][~dfs[df_name].index.duplicated(keep='first')]
        # drop columns except those wanted by the user
        dfs[df_name] = dfs[df_name][list(l1ire["xl_sheets"][df_name]["xl_labels"])]
        # coerce all columns with dtype "object" to "float64"
        cols = dfs[df_name].columns[dfs[df_name].dtypes.eq(object)]
        dfs[df_name][cols] = dfs[df_name][cols].apply(pandas.to_numeric, errors='coerce')
    # check to see if we have anything left to work with
    df_names = sorted(list(dfs))
    if len(df_names) < 1:
        msg = " No sheets to process in workbook " + l1ire["Files"]["in_filename"]
        logger.error(msg)
        raise RuntimeError(msg)
    # rename the pandas dataframe columns from the Excel variable names to the netCDF variable names
    # loop over the sheets in the Excel workbook
    for df_name in df_names:
        # create an empty dataframe with the index
        tmp = pandas.DataFrame(index=dfs[df_name].index)
        # loop over the netCDF variable names, done to allow variables with duplicate values
        for l in list(l1ire["xl_sheets"][df_name]["nc_labels"].keys()):
            tmp[l] = dfs[df_name][l1ire["xl_sheets"][df_name]["nc_labels"][l]].copy()
        # copy the new dataframe to the old name
        dfs[df_name] = tmp.copy()
    # discard empty data frames
    for key in list(dfs.keys()):
        if len(dfs[key]) == 0:
            dfs.pop(key)
    return dfs

def read_excel_workbook_get_timestamp(dfs, df_name, l1_info):
    """
    Purpose:
     Check to see if we can get a timestamp for this worksheet.
     The criteria for accepting a worksheet column as a timestamp are:
      - pandas must be able to convert it to a datetime
      - the time step must be the same as the global attribute
        time step
        - the time step is calculated as the mode of the differentiated
          timestamp column
      - if there are more than 1 columns that qualify, the first is chosen
    Usage:
    Side effects:
     The worksheet is deleted from the dictionary of data frames, dfs, if
     no timestamp is found.
    Author: PRI
    Date: Back in the day
    """
    # get the global attribute time step
    ts = int(l1_info["read_excel"]["Global"]["time_step"])
    # get the data frame for this worksheet
    df = dfs[df_name]
    # initialise logicals
    got_timestamp = False
    more_than_one = False
    # first check for columns that qualify
    if not got_timestamp:
        # get a list of columns where dtype is datetime64
        dt_columns = [c for c in df.columns if pandas.api.types.is_datetime64_dtype(df[c])]
        # check to see if there is more than 1
        if len(dt_columns) > 1:
            more_than_one = True
        # loop over candidate columns
        for dt_column in dt_columns:
            # try casting column as datetime
            try:
                df[dt_column] = pandas.to_datetime(df[dt_column])
                # get the time step for this column
                df_ts = df[dt_column].diff()
                # get the mode of the time step as minutes
                df_ts = df_ts.mode().values[0].astype('timedelta64[m]').astype(int)
                # is the data frame time step the same as the global attribute time step?
                if df_ts == ts:
                    # if yes then we have the timestamp column for this data frame
                    timestamp = dt_column
                    got_timestamp = True
                    # and exit the for loop
                    break
            except (ParserError, TypeError, ValueError):
                # pass silently on these errors
                pass
    if not got_timestamp:
        obj_columns = [c for c in df.columns[df.dtypes=='object']]
        if len(obj_columns) > 1:
            more_than_one = True
        for obj_column in obj_columns:
            try:
                df[obj_column] = pandas.to_datetime(df[obj_column])
                # get the time step for this column
                df_ts = df[obj_column].diff()
                # get the mode of the time step as minutes
                df_ts = df_ts.mode().values[0].astype('timedelta64[m]').astype(int)
                # is the data frame time step the same as the global attribute time step?
                if df_ts == ts:
                    # if yes then we have the timestamp column for this data frame
                    timestamp = obj_column
                    got_timestamp = True
                    # and exit the for loop
                    break
            except (ParserError, TypeError, ValueError):
                pass
    # check to see if we have a timestamp for this sheet
    if got_timestamp:
        if more_than_one:
            # if there was more than 1 timestamp, tell the user which one we are using
            msg = " Using column " + timestamp + " as the timestamp for sheet " + df_name
            logger.info(msg)
    else:
        # tell the user we couldn't find a timestamp for this sheet
        msg = "!!!!! Unable to find a timestamp for " + df_name + ", deleting sheet ..."
        logger.error("!!!!!")
        logger.error(msg)
        logger.error("!!!!!")
        # delete the sheet
        del dfs[df_name]
        del l1_info["read_excel"]["xl_sheets"][df_name]
        # set the timestamp to None
        timestamp = None
    return timestamp

def ReadInputFile(l1_info):
    """
    """
    l1ire = l1_info["read_excel"]
    # get the input file extension
    file_extension = os.path.splitext(l1ire["Files"]["in_filename"])
    # choose the appropriate routine depending on the file type
    if file_extension[1].lower() in [".xls", ".xlsx"]:
        l1ire["src"] = "xl"
        data = ReadExcelWorkbook(l1_info)
    elif file_extension[1].lower() in [".csv"]:
        l1ire["src"] = "csv"
        data = ReadCSVFile(l1_info)
    else:
        msg = " Unrecognised input file format (" + file_extension[1] + ")"
        logger.error(msg)
        l1_info["status"]["value"] = 1
        l1_info["status"]["message"] = msg
        data = {}
    if len(list(data.keys())) == 0:
        msg = "An error occurred reading the input file"
        logger.error(msg)
        raise RuntimeError(msg)
    return data

def read_eddypro_full(csvname):
    ds = DataStructure()
    csvfile = open(csvname,'r')
    csvreader = csv.reader(csvfile)
    n = 0
    adatetime = []
    us_data_list = []
    us_flag_list = []
    Fh_data_list = []
    Fh_flag_list = []
    Fe_data_list = []
    Fe_flag_list = []
    Fc_data_list = []
    Fc_flag_list = []
    for row in csvreader:
        if n==0:
            #header=row
            pass
        elif n==1:
            varlist=row
            us_data_col = varlist.index('u*')
            us_flag_col = varlist.index('qc_Tau')
            Fh_data_col = varlist.index('H')
            Fh_flag_col = varlist.index('qc_H')
            Fe_data_col = varlist.index('LE')
            Fe_flag_col = varlist.index('qc_LE')
            Fc_data_col = varlist.index('co2_flux')
            Fc_flag_col = varlist.index('qc_co2_flux')
        elif n==2:
            #unitlist=row
            pass
        else:
            adatetime.append(datetime.datetime.strptime(row[1]+' '+row[2],'%Y-%m-%d %H:%M'))
            us_data_list.append(float(row[us_data_col]))
            us_flag_list.append(float(row[us_flag_col]))
            Fh_data_list.append(float(row[Fh_data_col]))
            Fh_flag_list.append(float(row[Fh_flag_col]))
            Fe_data_list.append(float(row[Fe_data_col]))
            Fe_flag_list.append(float(row[Fe_flag_col]))
            Fc_data_list.append(float(row[Fc_data_col]))
            Fc_flag_list.append(float(row[Fc_flag_col]))
        n = n + 1
    nRecs = len(adatetime)
    ds.root["Attributes"]["nc_nrecs"] = nRecs
    ds.root["Variables"]['DateTime'] = {}
    ds.root["Variables"]['DateTime']['Data'] = adatetime
    pfp_utils.round_datetime(ds,mode="nearest_timestep")
    pfp_utils.get_ymdhmsfromdatetime(ds)

    variable = {"Label":"ustar"}
    variable["Data"] = numpy.array(us_data_list,dtype=numpy.float64)
    variable["Flag"] = numpy.array(us_flag_list,dtype=numpy.int32)
    variable["Attr"] = pfp_utils.make_attribute_dictionary()
    pfp_utils.CreateVariable(ds, variable)
    variable = {"Label":"Fh"}
    variable["Data"] = numpy.array(Fh_data_list,dtype=numpy.float64)
    variable["Flag"] = numpy.array(Fh_flag_list,dtype=numpy.int32)
    variable["Attr"] = pfp_utils.make_attribute_dictionary()
    pfp_utils.CreateVariable(ds, variable)
    variable = {"Label":"Fe"}
    variable["Data"] = numpy.array(Fe_data_list,dtype=numpy.float64)
    variable["Flag"] = numpy.array(Fe_flag_list,dtype=numpy.int32)
    variable["Attr"] = pfp_utils.make_attribute_dictionary()
    pfp_utils.CreateVariable(ds, variable)
    variable = {"Label":"Fco2"}
    variable["Data"] = numpy.array(Fc_data_list,dtype=numpy.float64)
    variable["Flag"] = numpy.array(Fc_flag_list,dtype=numpy.int32)
    variable["Attr"] = pfp_utils.make_attribute_dictionary()
    pfp_utils.CreateVariable(ds, variable)

    return ds

def write_tsv_reddyproc(cf):
    """
    Purpose:
     Write an input file for the REddyProc R scripts using data from an
     OzFlux-style netCDF file.
     REddyProc will only read tab separated value files, not comma separated
     value files.  The default extension for the output file is ".tsv".
    Usage:
     pfp_io.write_tsv_reddyproc(cfg)
     where cfg is a control file.
    Side effects:
     Produces a text file (tab separated values) in the same folder as the
     input file.
    Author: PRI
    Date: Back in the day
    """
    # get the file names
    file_path = cf["Files"]["file_path"]
    nc_name = cf["Files"]["in_filename"]
    ncFileName = os.path.join(file_path, nc_name)
    if not os.path.exists(ncFileName):
        msg = " netCDF file "+ncFileName+" not found"
        logger.warning(msg)
        return
    csv_name = cf["Files"]["out_filename"]
    csvFileName = os.path.join(file_path, csv_name)
    file_name = os.path.split(csvFileName)
    if not os.path.exists(file_name[0]):
        os.makedirs(file_name[0])
    # open the csv file
    csvfile = open(csvFileName,'w', newline='', encoding='utf-8')
    writer = csv.writer(csvfile,dialect='excel-tab')
    # read the netCDF file
    ds = NetCDFRead(ncFileName)
    if ds.info["returncodes"]["value"] != 0: return
    # get the datetime series
    dt = ds.root["Variables"]["DateTime"]["Data"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # get the start and end indices for whole days
    start_date = dt[0]
    end_date = dt[-1]
    si = pfp_utils.GetDateIndex(dt,str(start_date),ts=ts,default=0,match='startnextday')
    ei = pfp_utils.GetDateIndex(dt,str(end_date),ts=ts,default=len(dt)-1,match='endpreviousday')
    dt = dt[si:ei+1]
    # get the date and time data
    Year = numpy.array([d.year for d in dt])
    Ddd = numpy.array([d.timetuple().tm_yday + d.hour/float(24) + d.minute/float(1440) for d in dt])
    Hhh = numpy.array([d.hour + d.minute/float(60) for d in dt])
    # get the data
    data = OrderedDict()
    labels = list(cf["Variables"].keys())
    for label in labels:
        ncname = cf["Variables"][label]["name"]
        if ncname not in list(ds.root["Variables"].keys()):
            msg = "Series " + ncname + " not in netCDF file, skipping ..."
            logger.error(msg)
            labels.remove(label)
            continue
        data[label] = pfp_utils.GetVariable(ds, ncname, start=si, end=ei, out_type="-9999")
        fmt = cf["Variables"][label]["format"]
        if "." in fmt:
            numdec = len(fmt) - (fmt.index(".") + 1)
            strfmt = "{0:."+str(numdec)+"f}"
        else:
            strfmt = "{0:d}"
        data[label]["fmt"] = strfmt
    # adjust units as required
    # this could be done better, pete!
    for label in labels:
        if label == "NEE":
            if data[label]["Attr"]["units"] in ["mg/m^2/s","mgCO2/m^2/s"]:
                data[label]["Data"] = pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps(data[label]["Data"])
                data[label]["Attr"]["units"] = "umolm-2s-1"
            elif data[label]["Attr"]["units"]=='umol/m^2/s':
                data[label]["Attr"]["units"] = "umolm-2s-1"
            else:
                msg = " REddyProc output: unrecognised units for "+label+", returning ..."
                logger.error(msg)
                return 0
        if label == "LE" or label == "H" or label == "Rg":
            data[label]["Attr"]["units"] = "Wm-2"
        if label == "Tair" or label == "Tsoil":
            data[label]["Attr"]["units"] = "degC"
        if label == "rH" and data[label]["Attr"]["units"] in ["fraction","frac"]:
            idx = numpy.where(data[label]["Data"]!=c.missing_value)[0]
            data[label]["Data"][idx] = float(100)*data[label]["Data"][idx]
            data[label]["Attr"]["units"] = "percent"
        if label == "VPD" and data[label]["Attr"]["units"] == "kPa":
            idx = numpy.where(data[label]["Data"]!=c.missing_value)[0]
            data[label]["Data"][idx] = float(10)*data[label]["Data"][idx]
            data[label]["Attr"]["units"] = "hPa"
        if label == "Ustar":
            if data[label]["Attr"]["units"]=="m/s":
                data[label]["Attr"]["units"] = "ms-1"
    # write the variable names to the csv file
    row_list = ['Year','DoY','Hour']
    for item in labels:
        row_list.append(item)
    writer.writerow(row_list)
    # write the units line to the csv file
    units_list = ["-","-","-"]
    for item in labels:
        units_list.append(data[item]["Attr"]["units"])
    writer.writerow(units_list)
    # now write the data
    for i in range(len(Year)):
        data_list = ['%d'%(Year[i]),'%d'%(int(Ddd[i])),'%.1f'%(Hhh[i])]
        for series in labels:
            strfmt = data[series]["fmt"]
            if "d" in strfmt:
                data_list.append(strfmt.format(int(round(data[series]["Data"][i]))))
            else:
                data_list.append(strfmt.format(data[series]["Data"][i]))
        writer.writerow(data_list)
    # close the csv file
    csvfile.close()
    return 1

def smap_datetodatadictionary(ds, data_dict, nperday, ndays, si, ei):
    ldt = ds.root["Variables"]["DateTime"]["Data"][si:ei+1]
    # do the months
    month_1d = pfp_utils.GetVariable(ds, "Month", start=si, end=ei)
    data_dict["Mo"] = {}
    data_dict["Mo"]["data"] = numpy.reshape(month_1d["Data"], [ndays, nperday])[:,0]
    data_dict["Mo"]["fmt"] = "0"
    # do the days
    data_dict["Day"] = {}
    day_1d = pfp_utils.GetVariable(ds, "Day", start=si, end=ei)
    data_dict["Day"]["data"] = numpy.reshape(day_1d["Data"], [ndays, nperday])[:,0]
    data_dict["Day"]["fmt"] = "0"
    # day of the year
    data_dict["DOY"] = {}
    doy_1d = numpy.array([item.timetuple().tm_yday for item in ldt])
    data_dict["DOY"]["data"] = numpy.reshape(doy_1d,[ndays,nperday])[:,0]
    data_dict["DOY"]["fmt"] = "0"

def smap_docarbonfluxes(cf, ds, smap_label, si, ei):
    ncname = cf["Variables"][smap_label]["name"]
    var = pfp_utils.GetVariable(ds, ncname, start=si, end=ei)
    var["Data"] = var["Data"]*12.01*1800/1E6
    var["Data"] = numpy.ma.filled(var["Data"], float(-9999))
    return var

def smap_donetshortwave(ds, smap_label, si, ei):
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # do the net shortwave radiation
    Fsd = pfp_utils.GetVariable(ds, "Fsd", start=si, end=ei)
    Fsu = pfp_utils.GetVariable(ds, "Fsu", start=si, end=ei)
    # get the net shortwave radiation and convert to MJ/m2/day at the same time
    Fnsw = pfp_utils.CreateEmptyVariable("Fnsw", nrecs)
    Fnsw = ((Fsd["Data"] - Fsu["Data"])*ts*60)/1E6
    # now get the QC flag
    Fnsw["Flag"] = Fsd["Flag"] + Fsu["Flag"]
    Fnsw["Data"] = numpy.ma.filled(Fnsw["Data"], float(-9999))
    Fnsw["Attr"] = {"long_name": "Net shortwave radiation",
                    "units": "W/m^2",
                    "statistic_type": "average"}
    return Fnsw

def smap_dopressure(ds, smap_label, si, ei):
    ps = pfp_utils.GetVariable(ds, "ps", start=si, end=ei)
    ps["Data"] = ps["Data"]/float(1000)
    ps["Data"] = numpy.ma.filled(ps["Data"], float(-9999))
    return ps

def smap_doshortwave(ds, smap_label, si, ei):
    ts = int(float(ds.root["Attributes"]["time_step"]))
    Fsd = pfp_utils.GetVariable(ds, "Fsd", start=si, end=ei)
    Fsd["Data"] = (Fsd["Data"]*ts*60)/1E6
    Fsd["Data"] = numpy.ma.filled(Fsd["Data"], float(-9999))
    Fsd["Attr"] = {"long_name": "Shortwave radiation",
                    "units": "W/m^2",
                    "statistic_type": "average"}
    return Fsd

def smap_parseformat(fmt):
    if "." in fmt:
        numdec = len(fmt) - (fmt.index(".") + 1)
        strfmt = "{0:."+str(numdec)+"f}"
    else:
        strfmt = "{0:d}"
    return strfmt

def smap_qclabel(smap_label):
    if "_f" in smap_label:
        smap_qc_label=smap_label.replace("_f","_qc")
    else:
        smap_qc_label=smap_label+"_qc"
    return smap_qc_label

def smap_updatedatadictionary(cfvars, data_dict, var, smap_label, nperday, ndays):
    data_dict[smap_label] = {}
    if cfvars[smap_label]["daily"].lower() == "sum":
        data = numpy.ma.reshape(var["Data"], [ndays, nperday])
        data_dict[smap_label]["data"] = numpy.ma.sum(data, axis=1)
    elif cfvars[smap_label]["daily"].lower() == "average":
        data = numpy.ma.reshape(var["Data"], [ndays, nperday])
        data_dict[smap_label]["data"] = numpy.ma.average(data, axis=1)
    elif cfvars[smap_label]["daily"].lower() == "skip":
        data = numpy.reshape(var["Data"], [ndays, nperday])[:,0]
        data_dict[smap_label]["data"] = data
    else:
        msg = "  unrecognised option for daily (" + str(cfvars[smap_label]["daily"]) + ")"
        logger.warning(msg)
    data_dict[smap_label]["fmt"] = cfvars[smap_label]["format"]
    if cfvars[smap_label]["genqc"] == "True":
        smap_qc_label = smap_qclabel(smap_label)
        data_dict[smap_qc_label] = {}
        index_0 = numpy.where(var["Flag"] == 0)[0]
        index_not0 = numpy.where(var["Flag"] > 0)[0]
        var["Flag"][index_0] = numpy.int32(1)
        var["Flag"][index_not0] = numpy.int32(0)
        flag = numpy.ma.reshape(var["Flag"], [ndays, nperday])
        data_dict[smap_qc_label]["data"] = numpy.ma.sum(flag, axis=1)/float(nperday)
        data_dict[smap_qc_label]["fmt"] = "0.00"

def smap_write_csv(cf):
    cfvars = cf["Variables"]
    smap_list = list(cfvars.keys())
    ncFileName = get_infilenamefromcf(cf)
    csvFileName_base = get_outfilenamefromcf(cf)
    # read the netCDF file
    ds = NetCDFRead(ncFileName)
    if ds.info["returncodes"]["value"] != 0: return
    ts = int(float(ds.root["Attributes"]["time_step"]))
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    nperhr = int(float(60)/ts+0.5)
    nperday = int(float(24)*nperhr+0.5)
    dt = ds.root["Variables"]["DateTime"]["Data"]
    # get a list of years in the data file
    year_list = list(range(dt[0].year,dt[-1].year+1))
    years = numpy.array([item.year for item in dt])
    # loop over years in the data file
    data_dict = OrderedDict()
    for year in year_list:
        csvFileName = csvFileName_base+"_"+str(year)+"_SMAP.csv"
        # open the csv file
        csvfile = open(csvFileName,'w')
        # write the header lines
        writer = smap_writeheaders(cf,csvfile)
        # get the start and end datetime
        year_index = numpy.where(years==year)[0]
        # add the last record from this year
        year_index = numpy.append(year_index,year_index[-1]+1)
        sdate = dt[max([0,year_index[0]])]
        edate = dt[min([year_index[-1],nRecs-1])]
        si = pfp_utils.GetDateIndex(dt,str(sdate),ts=ts,default=0,match="startnextday")
        ei = pfp_utils.GetDateIndex(dt,str(edate),ts=ts,default=nRecs-1,match="endpreviousday")
        data_dict["DateTime"] = dt[si:ei+1]
        logger.info(" Writing "+str(data_dict["DateTime"][0])+" to "+ str(data_dict["DateTime"][-1]))
        ndays = len(data_dict["DateTime"])//nperday
        # put the month, day and DOY into the data dictionary
        smap_datetodatadictionary(ds,data_dict,nperday,ndays,si,ei)
        # first column in SMAP csv file will be the SMAP ID number
        smap_id = numpy.array([cf["General"]["SMAP_ID"]]*ndays)
        # loop over the data required, massage units if necessary and put the data into a dictionary for later use
        smap_list = ["Rn_f","Rs_f","PAR_f","Ta","VPD","Ts_f","PREC","SWC","NEE","GPP","Reco","PRESS","SNOWD"]
        for smap_label in smap_list:
            if smap_label in ["Mo", "Day", "DOY"]:
                continue
            if smap_label == "Rn_f":
                var = smap_donetshortwave(ds, smap_label, si, ei)
            elif smap_label == "Rs_f":
                var = smap_doshortwave(ds, smap_label, si, ei)
            elif smap_label == "PAR_f" or smap_label == "SNOWD":
                var = pfp_utils.CreateEmptyVariable(smap_label, len(data_dict["DateTime"]))
                var["Attr"] = {"long_name": smap_label, "units": "", "statistic_type": "average"}
                cfvars[smap_label]["daily"] = "skip"
            elif smap_label == "PRESS":
                var = smap_dopressure(ds, smap_label, si, ei)
            elif smap_label in ["GPP", "NEE", "Reco"]:
                var = smap_docarbonfluxes(cf, ds, smap_label, si, ei)
            else:
                var = pfp_utils.GetVariable(ds, cfvars[smap_label]["name"], start=si, end=ei)
            smap_updatedatadictionary(cfvars, data_dict, var, smap_label, nperday, ndays)
        # now loop over the days and write the data out
        for i in range(ndays):
            data_list = []
            data_list.append(smap_id[i])
            for smap_label in list(data_dict.keys()):
                if smap_label=="DateTime": continue
                strfmt = smap_parseformat(data_dict[smap_label]["fmt"])
                if "d" in strfmt:
                    data_list.append(strfmt.format(int(round(data_dict[smap_label]["data"][i]))))
                else:
                    data_list.append(strfmt.format(data_dict[smap_label]["data"][i]))
            writer.writerow(data_list)
        csvfile.close()

def smap_writeheaders(cf,csvfile):
    writer = csv.writer(csvfile)
    # write the header lines to the csv file
    series_list = list(cf["Variables"].keys())
    for item in cf["General"]:
        if item in ["SMAP_ID"]: continue
        writer.writerow([item,str(cf['General'][item])])
    # write the units and variable name header lines to the csv file
    units_list = ["-","-","-","-"]
    row_list = ['ID','Mo','Day','DOY']
    for smap_label in series_list:
        row_list.append(smap_label)
        units_list.append(cf["Variables"][smap_label]["units"])
        if cf["Variables"][smap_label]["genqc"]=="True":
            smap_qc_label = smap_qclabel(smap_label)
            row_list.append(smap_qc_label)
            units_list.append("-")
    writer.writerow(units_list)
    writer.writerow(row_list)
    return writer

def TruncateDataStructure(ds, info):
    """
    Purpose:
     Truncate a data structure.  The options are:
      (1) no truncation (No)
      (2) after the last good data record (First missing)
      (3) to last date of any imports (Imports)
    Usage:
     pfp_io.TruncateDataStructure(ds, info)
    Author: PRI
    Date: August 2023
    """
    opt = pfp_utils.get_keyvaluefromcf(info["cfg"], ["Options"], "Truncate", default="No")
    if opt.lower() == "no":
        return
    if ((opt.lower() == "first missing") and (info["cfg"]["level"].lower() == "l4")):
        for item in ["Variables", "Drivers", "Fluxes"]:
            if item in list(info["cfg"].keys()):
                break
        labels = sorted(list(info["cfg"][item].keys()))
        ts = int(ds.root["Attributes"]["time_step"])
        first_missing_dates = []
        for label in labels:
            var = pfp_utils.GetVariable(ds, label)
            idx = numpy.where(numpy.ma.getmaskarray(var["Data"]))[0]
            if len(idx) > 0:
                first_missing_dates.append(var["DateTime"][min(idx)])
            else:
                pass
        if len(first_missing_dates) > 0:
            msg = " Truncating data structure (" + opt + ")"
            logger.info(msg)
            first_missing_date = min(first_missing_dates)
            last_good_date = first_missing_date - datetime.timedelta(minutes=ts)
            msg = "  All variables truncated to " + last_good_date.strftime("%Y-%m-%d")
            logger.info(msg)
            labels = sorted(list(ds.root["Variables"].keys()))
            for label in labels:
                var = pfp_utils.GetVariable(ds, label, end=last_good_date)
                pfp_utils.CreateVariable(ds, var)
            dt = pfp_utils.GetVariable(ds, "DateTime")
            ds.root["Attributes"]["nc_nrecs"] = int(len(dt["Data"]))
            ds.root["Attributes"]["time_coverage_start"] = str(dt["Data"][0])
            ds.root["Attributes"]["time_coverage_end"] = str(dt["Data"][-1])
        else:
            pass
    elif opt.lower() == "to imports":
        if "ImportSeries" not in info:
            return
        ldt = pfp_utils.GetVariable(ds, "DateTime")
        import_labels = list(info["ImportSeries"].keys())
        start_dates = []
        end_dates = []
        for import_label in import_labels:
            start_dates.append(info["ImportSeries"][import_label]["start"])
            end_dates.append(info["ImportSeries"][import_label]["end"])
        start = max(start_dates)
        end = min(end_dates)
        if ((start > ldt["Data"][0]) or (end < ldt["Data"][-1])):
            msg = " Truncating data structure (" + opt + ")"
            logger.info(msg)
            msg = "  All variables truncated to " + start.strftime("%Y-%m-%d")
            msg += " and " + end.strftime("%Y-%m-%d")
            logger.info(msg)
            labels = sorted(list(ds.root["Variables"].keys()))
            # do DateTime last because it is used to pick dates by GetVariable()
            if "DateTime" in labels:
                labels.remove("DateTime")
            for label in labels:
                var = pfp_utils.GetVariable(ds, label, start=start, end=end)
                pfp_utils.CreateVariable(ds, var)
            dt = pfp_utils.GetVariable(ds, "DateTime", start=start, end=end)
            pfp_utils.CreateVariable(ds, dt)
            ds.root["Attributes"]["nc_nrecs"] = int(len(dt["Data"]))
            ds.root["Attributes"]["time_coverage_start"] = str(dt["Data"][0])
            ds.root["Attributes"]["time_coverage_end"] = str(dt["Data"][-1])
    else:
        msg = "Unrecognised truncate option (" + opt + "), no action taken ..."
        logger.warning(msg)
    return

def write_csv_ecostress(cf):
    """
    Purpose:
     Write the data structure to an ECOSTRESS CSV file.
    Usage:
    Side effects:
    Author: PRI
    Date: September 2018
    """
    # get the file names
    file_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "file_path", default="")
    if not os.path.isdir(file_path):
        msg = " Specified file path "+file_path+" doesn't exist ..."
        logger.error(msg)
        return 0
    in_filename = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "in_filename", default="")
    nc_file_name = os.path.join(file_path, in_filename)
    if not os.path.exists(nc_file_name):
        msg = " Specified input file "+nc_file_name+" not found ..."
        logger.error(msg)
        return 0
    out_filename = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "out_filename", default="")
    if len(out_filename) == 0:
        csv_file_name = nc_file_name.replace(".nc", "_ECOSTRESS.csv")
    else:
        csv_file_name = os.path.join(file_path, out_filename)
    # open the csv file
    csv_file = open(csv_file_name, 'w')
    csv_writer = csv.writer(csv_file)
    # read the netCDF file
    ds = NetCDFRead(nc_file_name)
    if ds.info["returncodes"]["value"] != 0: return 0
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs,dtype=numpy.int32)
    ones = numpy.ones(nRecs,dtype=numpy.int32)
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # get the datetime series
    dt = ds.root["Variables"]["DateTime"]["Data"]
    # get the data
    data = {}
    labels = cf["Variables"].keys()
    qc_labels = ["LHF", "SHF", "GHF", "GPP", "Ta", "T2", "VPD", "Rn"]
    for label in list(labels):
        ncname = cf["Variables"][label]["name"]
        if ncname not in list(ds.root["Variables"].keys()):
            # skip variable if name not in the data structure
            msg = " Variable for " + label + " (" + ncname
            msg += ") not found in data structure, skipping ..."
            logger.warning(msg)
            labels.remove(label)
            if label in qc_labels:
                qc_labels.remove(label)
        else:
            data[label] = pfp_utils.GetVariable(ds, ncname)
            fmt = cf["Variables"][label]["format"]
            if "E" in fmt or "e" in fmt:
                numdec = (fmt.index("E")) - (fmt.index(".")) - 1
                strfmt = "{:."+str(numdec)+"e}"
            elif "." in fmt:
                numdec = len(fmt) - (fmt.index(".") + 1)
                strfmt = "{0:."+str(numdec)+"f}"
            else:
                strfmt = "{0:d}"
            data[label]["Attr"]["fmt"] = strfmt
    # adjust units as required
    # GPP
    data["GPP"]["Data"] = pfp_mf.Fco2_gCpm2psfromumolpm2ps(data["GPP"]["Data"])
    data["GPP"]["Attr"]["units"] = "gC/m^2/s"
    # SWC
    data["SWC"]["Attr"]["units"] = "m^3/m^3"
    # add the QC flags for Fh, Fe, Fg, GPP, Ta, T2, VPD, Fn
    # for Fh, Fe, Fg, Fn, Ta, T2 and VPD QC flag is:
    #  a) 0 for observation
    #  b) 1 for gap filled high quality
    #  c) 2 for gap filled medium quality
    #  d) 3 for gap filled low quality
    for label in qc_labels:
        qc_label = label + "_qc"
        labels.insert(labels.index(label)+1, qc_label)
        data[qc_label] = {}
        data[qc_label]["Data"] = numpy.where(data[label]["Flag"] == 0, zeros, ones)
        data[qc_label]["Attr"] = {}
        data[qc_label]["Attr"]["fmt"] = "{0:d}"
        data[qc_label]["Attr"]["units"] = "-"
    # write the metadata to the CSV file
    msg = " Writing ECOSTRESS CSV file"
    logger.info(msg)
    if "General" in cf:
        for item in cf["General"]:
            csv_writer.writerow([item,str(cf['General'][item])])
        csv_writer.writerow("")
    # write the units row
    row_list = ["YYYYMMDDhhmm", "YYYYMMDDhhmm"]
    for label in labels:
        row_list.append(data[label]["Attr"]["units"])
    csv_writer.writerow(row_list)
    # write the variable names to the csv file
    row_list = ["TIME_START", "TIME_END"]
    for label in labels:
        row_list.append(label)
    csv_writer.writerow(row_list)
    # now write the data
    for i in range(len(dt)):
        # get the timestamp at the start and end of the period
        timestamp_end = dt[i].strftime("%Y%m%d%H%M")
        timestamp_start = (dt[i] - datetime.timedelta(minutes=ts)).strftime("%Y%m%d%H%M")
        data_list = [timestamp_start, timestamp_end]
        for label in labels:
            # convert from masked array to ndarray with -9999 for missing data
            data[label]["Data"] = numpy.ma.filled(data[label]["Data"], fill_value=float(-9999))
            strfmt = data[label]["Attr"]["fmt"]
            if "d" in strfmt:
                data_list.append(strfmt.format(int(round(data[label]["Data"][i]))))
            else:
                data_list.append(strfmt.format(data[label]["Data"][i]))
        csv_writer.writerow(data_list)
    # close the csv file
    csv_file.close()
    msg = " Finished writing ECOSTRESS CSV file"
    logger.info(msg)
    return 1

def write_csv_ep_biomet(cf):
    """
    Purpose:
     Write a biomet file for use with EddyPro.
    Usage:
     pfp_io.write_csv_ep_biomet(cf)
     where:
      cf - a control file object that specifies the input and output file
           names and the variable mapping to use.
    Author: PRI
    Date: August 2016
    """
    # get the file names
    ncFileName = get_infilenamefromcf(cf)
    if not pfp_utils.file_exists(ncFileName, mode="verbose"):
        return 0
    csvFileName = get_outfilenamefromcf(cf)
    if not pfp_utils.path_exists(os.path.dirname(csvFileName), mode="verbose"):
        return 0
    # open the csv file
    csvfile = open(csvFileName, "w", newline="")
    writer = csv.writer(csvfile)
    # read the netCDF file
    ds = NetCDFRead(ncFileName)
    if ds.info["returncodes"]["value"] != 0: return 0
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    # get the date and time data
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    Minute = numpy.array([dt.minute for dt in ldt["Data"]])
    Hour = numpy.array([dt.hour for dt in ldt["Data"]])
    Day = numpy.array([dt.day for dt in ldt["Data"]])
    Month = numpy.array([dt.month for dt in ldt["Data"]])
    Year = numpy.array([dt.year for dt in ldt["Data"]])
    # get the data
    data = ep_biomet_get_data(cf, ds)
    # check and adjust units if required
    # get a list of the EddyPro series to be output
    ep_series_list = list(data.keys())
    ep_series_list.sort()
    for ep_series in ep_series_list:
        # loop over the netCDF series names and check they exist in constants.units_synonyms dictionary
        in_name = data[ep_series]["name"]
        if in_name not in c.units_synonyms.keys():
            msg = "No entry for " + in_name + " in cfg.units_synonyms, skipping ..."
            logger.warning(msg)
            continue
        if (data[ep_series]["Attr"]["units"] not in c.units_synonyms[in_name] and
            ds.root["Variables"][in_name]["Attr"]["units"] not in c.units_synonyms[in_name]):
            msg = "Inconsistent units found for series " + ep_series + " and " + in_name
            logger.warning(msg)
    # write the variable names to the csv file
    row_list = ['TIMESTAMP_1']
    for item in ep_series_list:
        row_list.append(item)
    writer.writerow(row_list)
    # write the units line to the csv file
    units_list = ["yyyy-mm-dd HHMM"]
    for item in ep_series_list:
        units_list.append(data[item]["units"])
    writer.writerow(units_list)
    # now write the data
    for i in range(nrecs):
        # get the datetime string
        dtstr = '%d-%02d-%02d %02d%02d'%(Year[i],Month[i],Day[i],Hour[i],Minute[i])
        data_list = [dtstr]
        for ep_series in ep_series_list:
            strfmt = data[ep_series]["format"]
            if "d" in strfmt:
                data_list.append(strfmt.format(int(round(data[ep_series]["Data"][i]))))
            else:
                data_list.append(strfmt.format(data[ep_series]["Data"][i]))
        writer.writerow(data_list)
    # close the csv file
    csvfile.close()
    return 1

def ep_biomet_get_data(cfg, ds):
    data = {}
    ep_series_list = cfg["Variables"].keys()
    for ep_series in ep_series_list:
        in_name = cfg["Variables"][ep_series]["name"]
        if in_name not in ds.root["Variables"].keys():
            logger.error("Series " + in_name + " not in netCDF file, skipping ...")
            ep_series_list.remove(ep_series)
            continue
        data[ep_series] = copy.deepcopy(ds.root["Variables"][in_name])
        data[ep_series]["name"] = in_name
        data[ep_series]["units"] = cfg["Variables"][ep_series]["units"]
        fmt = cfg["Variables"][ep_series]["format"]
        if "." in fmt:
            numdec = len(fmt) - (fmt.index(".") + 1)
            strfmt = "{0:." + str(numdec) + "f}"
        else:
            strfmt = "{0:d}"
        data[ep_series]["format"] = strfmt
    return data

def write_csv_fluxnet(cf):
    # get the file names
    ncFileName = get_infilenamefromcf(cf)
    csvFileName = get_outfilenamefromcf(cf)
    # open the csv file
    csvfile = open(csvFileName,'w')
    writer = csv.writer(csvfile)
    # read the netCDF file
    ds = NetCDFRead(ncFileName)
    if ds.info["returncodes"]["value"] != 0: return 0
    ts = int(float(ds.root["Attributes"]["time_step"]))
    ts_delta = datetime.timedelta(minutes=ts)
    # get the datetime series
    dt = ds.root["Variables"]["DateTime"]["Data"]
    # check the start datetime of the series and adjust if necessary
    start_datetime = dateutil.parser.parse(str(cf["General"]["start_datetime"]))
    if dt[0]<start_datetime:
        # requested start_datetime is after the start of the file
        logger.info(" Truncating start of file")
        si = pfp_utils.GetDateIndex(dt,str(start_datetime),ts=ts,match="exact")
        for thisone in list(ds.root["Variables"].keys()):
            ds.root["Variables"][thisone]["Data"] = ds.root["Variables"][thisone]["Data"][si:]
            ds.root["Variables"][thisone]["Flag"] = ds.root["Variables"][thisone]["Flag"][si:]
        ds.root["Attributes"]["nc_nrecs"] = str(len(ds.root["Variables"]["DateTime"]["Data"]))
    elif dt[0]>start_datetime:
        # requested start_datetime is before the start of the file
        logger.info(" Padding start of file")
        dt_patched = [ldt for ldt in pfp_utils.perdelta(start_datetime, dt[0]-ts_delta, ts_delta)]
        data_patched = numpy.ones(len(dt_patched))*float(c.missing_value)
        flag_patched = numpy.ones(len(dt_patched))
        # list of series in the data structure
        series_list = list(ds.root["Variables"].keys())
        # ds.root["Variables"]["DateTime"]["Data"] is a list not a numpy array so we must treat it differently
        ds.root["Variables"]["DateTime"]["Data"] = dt_patched+ds.root["Variables"]["DateTime"]["Data"]
        ds.root["Variables"]["DateTime"]["Flag"] = numpy.concatenate((flag_patched,ds.root["Variables"]["DateTime"]["Flag"]))
        series_list.remove("DateTime")
        for thisone in series_list:
            ds.root["Variables"][thisone]["Data"] = numpy.concatenate((data_patched,ds.root["Variables"][thisone]["Data"]))
            ds.root["Variables"][thisone]["Flag"] = numpy.concatenate((flag_patched,ds.root["Variables"][thisone]["Flag"]))
        ds.root["Attributes"]["nc_nrecs"] = str(len(ds.root["Variables"]["DateTime"]["Data"]))
        # refresh the year, month, day etc arrays now that we have padded the datetime series
        #pfp_utils.get_ymdhmsfromdatetime(ds)
    # now check the end datetime of the file
    end_datetime = dateutil.parser.parse(str(cf["General"]["end_datetime"]))
    if dt[-1]>end_datetime:
        # requested end_datetime is before the end of the file
        msg = " Truncating end of file "+dt[-1].strftime("%Y-%m-%d %H:%M")+" "+end_datetime.strftime("%Y-%m-%d %H:%M")
        logger.info(msg)
        ei = pfp_utils.GetDateIndex(dt,str(end_datetime),ts=ts,match="exact")
        for thisone in list(ds.root["Variables"].keys()):
            ds.root["Variables"][thisone]["Data"] = ds.root["Variables"][thisone]["Data"][:ei+1]
            ds.root["Variables"][thisone]["Flag"] = ds.root["Variables"][thisone]["Flag"][:ei+1]
        ds.root["Attributes"]["nc_nrecs"] = str(len(ds.root["Variables"]["DateTime"]["Data"]))
    elif dt[-1]<end_datetime:
        # requested end_datetime is before the requested end date
        msg = " Padding end of file "+dt[-1].strftime("%Y-%m-%d %H:%M")+" "+end_datetime.strftime("%Y-%m-%d %H:%M")
        logger.info(msg)
        dt_patched = [ldt for ldt in pfp_utils.perdelta(dt[-1]+ts_delta, end_datetime, ts_delta)]
        data_patched = numpy.ones(len(dt_patched))*float(c.missing_value)
        flag_patched = numpy.ones(len(dt_patched))
        # list of series in the data structure
        series_list = list(ds.root["Variables"].keys())
        # ds.root["Variables"]["DateTime"]["Data"] is a list not a numpy array so we must treat it differently
        ds.root["Variables"]["DateTime"]["Data"] = ds.root["Variables"]["DateTime"]["Data"]+dt_patched
        ds.root["Variables"]["DateTime"]["Flag"] = numpy.concatenate((ds.root["Variables"]["DateTime"]["Flag"],flag_patched))
        series_list.remove("DateTime")
        for thisone in series_list:
            ds.root["Variables"][thisone]["Data"] = numpy.concatenate((ds.root["Variables"][thisone]["Data"],data_patched))
            ds.root["Variables"][thisone]["Flag"] = numpy.concatenate((ds.root["Variables"][thisone]["Flag"],flag_patched))
        ds.root["Attributes"]["nc_nrecs"] = str(len(ds.root["Variables"]["DateTime"]["Data"]))
        # refresh the year, month, day etc arrays now that we have padded the datetime series
        #pfp_utils.get_ymdhmsfromdatetime(ds)
    if ts==30:
        nRecs_year = 17520
        nRecs_leapyear = 17568
    elif ts==60:
        nRecs_year = 8760
        nRecs_leapyear = 8784
    else:
        logger.error(" Unrecognised time step ("+str(ts)+")")
        return 0
    if (int(ds.root["Attributes"]["nc_nrecs"])!=nRecs_year) & (int(ds.root["Attributes"]["nc_nrecs"])!=nRecs_leapyear):
        logger.error(" Number of records in file does not equal "+str(nRecs_year)+" or "+str(nRecs_leapyear))
        msg = str(len(ds.root["Variables"]["DateTime"]["Data"]))+" "+str(ds.root["Variables"]["DateTime"]["Data"][0])
        msg = msg+" "+str(ds.root["Variables"]["DateTime"]["Data"][-1])
        logger.error(msg)
        return 0
    # get the date and time data
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    Day = numpy.array([dt.day for dt in ldt])
    Month = numpy.array([dt.month for dt in ldt])
    Year = numpy.array([dt.year for dt in ldt])
    Hour = numpy.array([dt.hour for dt in ldt])
    Minute = numpy.array([dt.minute for dt in ldt])
    # get the data
    data = {}
    series_list = list(cf["Variables"].keys())
    for series in series_list:
        ncname = cf["Variables"][series]["name"]
        if ncname not in list(ds.root["Variables"].keys()):
            logger.error("Series "+ncname+" not in netCDF file, skipping ...")
            series_list.remove(series)
            continue
        data[series] = ds.root["Variables"][ncname]
        fmt = cf["Variables"][series]["format"]
        if "." in fmt:
            numdec = len(fmt) - (fmt.index(".") + 1)
            strfmt = "{0:."+str(numdec)+"f}"
        else:
            strfmt = "{0:d}"
        data[series]["fmt"] = strfmt
    #adjust units if required
    for series in series_list:
        if series=="FC" and data[series]["Attr"]["units"]=='mg/m^2/s':
            data[series]["Data"] = pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps(data[series]["Data"])
            data[series]["Attr"]["units"] = "umol/m^2/s"
        if series=="CO2" and data[series]["Attr"]["units"]=='mg/m^3':
            CO2 = data["CO2"]["Data"]
            TA = data["TA"]["Data"]
            PA = data["PA"]["Data"]
            data[series]["Data"] = pfp_mf.co2_ppmfrommgCO2pm3(CO2,TA,PA)
            data[series]["Attr"]["units"] = "umol/mol"
        if series=="H2O" and data[series]["Attr"]["units"]=='g/m^3':
            H2O = data["H2O"]["Data"]
            TA = data["TA"]["Data"]
            PA = data["PA"]["Data"]
            data[series]["Data"] = pfp_mf.h2o_mmolpmolfromgpm3(H2O,TA,PA)
            data[series]["Attr"]["units"] = "mmol/mol"
        if series=="RH" and data[series]["Attr"]["units"] in ["fraction","frac"]:
            data[series]["Data"] = float(100)*data[series]["Data"]
            data[series]["Attr"]["units"] = "percent"
    # write the general information to csv file
    for item in cf["General"]:
        writer.writerow([item,str(cf['General'][item])])
    # write the variable names to the csv file
    row_list = ['DateTime','Year','Month','Day','HHMM']
    for item in series_list:
        row_list.append(item)
    writer.writerow(row_list)
    # write the units line to the csv file
    units_list = ["-","-","-","-","-"]
    for item in series_list:
        units_list.append(data[item]["Attr"]["units"])
    writer.writerow(units_list)
    # now write the data
    for i in range(len(Year)):
        # get the datetime string
        dtstr = '%02d/%02d/%d %02d:%02d'%(Day[i],Month[i],Year[i],Hour[i],Minute[i])
        hrmn = '%02d%02d'%(Hour[i],Minute[i])
        data_list = [dtstr,'%d'%(Year[i]),'%02d'%(Month[i]),'%02d'%(Day[i]),hrmn]
        for series in series_list:
            strfmt = data[series]["fmt"]
            if "d" in strfmt:
                data_list.append(strfmt.format(int(round(data[series]["Data"][i]))))
            else:
                data_list.append(strfmt.format(data[series]["Data"][i]))
        writer.writerow(data_list)
    # close the csv file
    csvfile.close()
    return 1

def write_csv_oneflux(cfg):
    """
    """
    ok = True
    # get the file names
    nc_uri = get_infilenamefromcf(cfg)
    if not pfp_utils.file_exists(nc_uri, mode="verbose"):
        ok = False
        return ok
    ds = NetCDFRead(nc_uri)
    ts = int(float(ds.root["Attributes"]["time_step"]))
    dt = pfp_utils.GetVariable(ds, "DateTime")
    ts_delta = datetime.timedelta(minutes=ts)
    start_year = (dt["Data"][0] - ts_delta).year
    end_year = (dt["Data"][-1] - ts_delta).year
    years = range(start_year, end_year+1)
    if "General" not in cfg:
        cfg["General"] = {}
    for year in years:
        msg = " Converting year: " + str(year)
        logger.info(msg)
        cfg["General"]["year"] = str(year)
        if not write_csv_oneflux_year(cfg, ds):
            ok = False
            return ok
    return ok

def write_csv_oneflux_year(cfg, ds):
    """
    Purpose:
     Write ONEFlux CSV files, one calendar year per file.
    Author: PRI
    Date: Back in the day
    """
    ok = True
    time_resolution = {30: "halfhourly", 60: "hourly"}
    ds_labels = sorted(list(ds.root["Variables"].keys()))
    ts = int(ds.root["Attributes"]["time_step"])
    ts_delta = datetime.timedelta(minutes=ts)
    # get the start and end dates
    year = int(cfg["General"]["year"])
    start = datetime.datetime(year, 1, 1, 0, 0, 0) + ts_delta
    end = datetime.datetime(year+1, 1, 1, 0, 0, 0)
    # datetime array from start to end at ts
    cdt = numpy.array([d for d in pfp_utils.perdelta(start, end, ts_delta)])
    nrecs = len(cdt)
    # dictionary for data
    data = {"DateTime": {"data": numpy.array(cdt), "format": ""}}
    dt = pfp_utils.GetVariable(ds, "DateTime")
    ldt = dt["Data"]
    indainb, indbina = pfp_utils.FindMatchingIndices(cdt, ldt)
    # ONEFlux variable labels
    of_labels = sorted(list(cfg["Variables"].keys()))
    # loop over the ONEFlux variables and put data in the data dictionary
    for of_label in of_labels:
        # label of the variable in the PFP data structure
        ds_label = cfg["Variables"][of_label]["name"]
        # dictionary to hold data for this variable
        data[of_label] = {}
        # initialise with missing data values
        data[of_label]["data"] = numpy.full(nrecs, float(-9999))
        # format of the CSV output specified in control file
        fmt = cfg["Variables"][of_label]["format"]
        if "." in fmt:
            numdec = len(fmt) - (fmt.index(".") + 1)
            strfmt = "{0:."+str(numdec)+"f}"
        else:
            strfmt = "{0:d}"
        data[of_label]["format"] = strfmt
        # get the variable from the PFP data structure
        var = pfp_utils.GetVariable(ds, ds_label)
        # check to see if the MAD filter was used for this variable
        if "MAD filter" in var["Attr"]:
            msg = "  MAD filter applied to " + ds_label + ", checking for unfiltered variable"
            logger.info(msg)
            # check to see if the unfiltered variable is in the PFP data structure
            if ds_label + "_notMAD" in ds_labels:
                # if it is, then use it
                msg = "   Using unfiltered variable " + ds_label + "_notMAD"
                logger.info(msg)
                var = pfp_utils.GetVariable(ds, ds_label + "_notMAD")
            else:
                # if it isn't, then warn the user
                msg = "   Unfiltered variable (" +  ds_label + "_notMAD" + ") not found, skipping ..."
                logger.error(msg)
                continue
        # check the units
        if var["Attr"]["units"] != cfg["Variables"][of_label]["units"]:
            var = pfp_utils.convert_units_func(ds, var, cfg["Variables"][of_label]["units"])
        data[of_label]["data"][indainb] = var["Data"][indbina]
    fluxnet_id = ds.root["Attributes"]["site_name"]
    if "fluxnet_id" in ds.root["Attributes"]:
        if len(ds.root["Attributes"]["fluxnet_id"]) == 6:
            fluxnet_id = ds.root["Attributes"]["fluxnet_id"]
    # get the UTC offset from the time zone name
    # original code - bad Peter, naughty Peter, shameful Peter!
    #time_zone = ds.root["Attributes"]["time_zone"]
    #now = datetime.datetime.now(pytz.timezone(time_zone))
    #utc_offset = now.utcoffset().total_seconds()/60/60
    # 20251211 code - all hail Cacilia The Mighty Bug Finder!
    time_zone = ds.root["Attributes"]["time_zone"]
    offsets = pfp_utils.get_utc_offset(ldt[0], time_zone)
    utc_offset = offsets["standard_offset"].total_seconds()/60/60
    # get the tower height
    tower_height = pfp_utils.strip_non_numeric(str(ds.root["Attributes"]["tower_height"]))
    # get the data path and CSV name
    data_path = os.path.split(ds.info["filepath"])[0]
    csv_name = fluxnet_id + "_qcv_" + str(year) + ".csv"
    csv_uri = os.path.join(data_path, csv_name)
    # open the csv file
    csv_file = open(csv_uri, 'w')
    writer = csv.writer(csv_file)
    # write the header lines
    writer.writerow(["site", fluxnet_id])
    writer.writerow(["year", str(year)])
    writer.writerow(["lat", str(ds.root["Attributes"]["latitude"])])
    writer.writerow(["lon", str(ds.root["Attributes"]["longitude"])])
    writer.writerow(["timezone", str(utc_offset)])
    writer.writerow(["htower", "{:%Y%m%d%H%M}".format(start), str(tower_height)])
    writer.writerow(["timeres", time_resolution[ts]])
    writer.writerow(["sc_negl", str(1)])
    writer.writerow(["notes", "Prepared by PyFluxPro"])
    # write the data
    header = ["TIMESTAMP_START","TIMESTAMP_END"]
    for of_label in of_labels:
        header.append(of_label)
    writer.writerow(header)
    for n in range(nrecs):
        timestamp_start = "{:%Y%m%d%H%M}".format(data["DateTime"]["data"][n]-ts_delta)
        timestamp_end = "{:%Y%m%d%H%M}".format(data["DateTime"]["data"][n])
        data_list = [timestamp_start, timestamp_end]
        for of_label in of_labels:
            strfmt = data[of_label]["format"]
            if "d" in strfmt:
                data_list.append(strfmt.format(int(round(data[of_label]["data"][n]))))
            else:
                data_list.append(strfmt.format(data[of_label]["data"][n]))
        writer.writerow(data_list)
    # close the CSV file
    csv_file.close()
    return ok

def get_controlfilecontents(cfg_file_uri, mode="verbose"):
    """
    Purpose:
     Open a control fie and return its contents.
    Author: PRI
    Date: Back in the day
    """
    if mode != "quiet":
        logger.info(" Processing the control file")
    try:
        cfg = ConfigObj(cfg_file_uri, indent_type="    ", list_values=False)
    except Exception:
        raise RuntimeError("Unable to open control file")
    return cfg

def get_ncdtype(Series):
    sd = Series.dtype.name
    dt = 'f'
    if sd=='float64': dt = 'd'
    if sd=='int32': dt = 'i'
    if sd=='int64': dt = 'l'
    return dt

def get_filename_dialog(file_path='.', title='Choose a file', ext="*.*"):
    """
    Purpose:
     Put up a file open dialog and let the user browse to open a file
    Usage:
     fname = pfp_io.get_filename_dialog(path=<path_to_file>,title=<tile>)
     where path  - the path to the file location, optional
           title - the title for the file open dialog, optional
    Returns:
     fname - the full file name including path, string
    Author: PRI
    Date: Back in the day
    """
    file_name = QtWidgets.QFileDialog.getOpenFileName(caption=title, directory=file_path, filter=ext)[0]
    return str(file_name)

def get_output_filename_dialog(file_path=".", title="Choose an output file ...", ext="*.*"):
    file_name = QtWidgets.QFileDialog.getSaveFileName(caption=title, directory=file_path, filter=ext)[0]
    return str(file_name)

def get_infilenamefromcf(cf):
    path = pfp_utils.get_keyvaluefromcf(cf,["Files"],"file_path",default="")
    path = os.path.join(str(path), "")
    name = pfp_utils.get_keyvaluefromcf(cf,["Files"],"in_filename",default="")
    return str(path)+str(name)

def get_outfilenamefromcf(cfg):
    """
    Purpose:
     Return the output file name from a control file.
    Author: PRI
    Date: Back in the day
    """
    # check to see what type of control file we have
    if cfg["level"] in ["concatenate"]:
        # concatenation control files use a different syntax
        out_file_uri = pfp_utils.get_keyvaluefromcf(cfg, ["Files", "Out"], "ncFileName")
    else:
        # everything else gets here
        path = pfp_utils.get_keyvaluefromcf(cfg, ["Files"], "file_path")
        name = pfp_utils.get_keyvaluefromcf(cfg, ["Files"], "out_filename")
        out_file_uri = os.path.join(path, name)
    return out_file_uri

def get_seriesstats(cf,ds):
    # open an Excel file for the flag statistics
    out_filename = get_outfilenamefromcf(cf)
    xl_filename = out_filename.replace(".nc", "_FlagStats.xls")
    file_name = os.path.split(xl_filename)
    logger.info(" Writing flag stats to " + file_name[1])
    xlFile = xlwt.Workbook()
    xlFlagSheet = xlFile.add_sheet("Flag")
    # get the flag statistics
    bins = numpy.arange(-0.5, 23.5)
    xlRow = 5
    xlCol = 1
    for Value in bins[:len(bins)-1]:
        xlFlagSheet.write(xlRow, xlCol, int(Value+0.5))
        xlCol = xlCol + 1
    xlRow = xlRow + 1
    xlCol = 0
    dsVarNames = sorted(ds.root["Variables"].keys())
    for ThisOne in dsVarNames:
        var = pfp_utils.GetVariable(ds, ThisOne)
        hist, bin_edges = numpy.histogram(var["Flag"], bins=bins)
        xlFlagSheet.write(xlRow, xlCol, ThisOne)
        xlCol = xlCol + 1
        for Value in hist:
            xlFlagSheet.write(xlRow, xlCol, float(Value))
            xlCol = xlCol + 1
        xlCol = 0
        xlRow = xlRow + 1
    xlFile.save(xl_filename)

def load_controlfile(path='.', title='Choose a control file'):
    """
    Purpose:
     Returns a control file object.
    Usage:
     cf = pfp_io.load_controlfile([path=<some_path_to_a_controlfile>],[title=<some title>])
          where path [optional] is the path to a subdirectory
                title [optional] is a title for the file open dialog
                cf is a control file object
    Author: PRI
    Date: Back in the day
    """
    name = get_filename_dialog(file_path=path, title=title, ext="*.*")
    cf = get_controlfilecontents(name)
    return cf

def NetCDFConcatenate(info):
    """
    Purpose:
     Concatenate multiple single year files in a single, multiple year file.
    Usage:
     pfp_io.NetCDFConcatenate(info)
    Called by:
     pfp_top_level.do_file_concatenate()
    Calls:
     pfp_io.netcdf_concatenate_read_input_files(info)
     pfp_utils.GetVariable()
     pfp_io.netcdf_concatenate_create_ds_out(data, dt_out, chrono_files, labels)
    Side effects:
    Author: PRI
    Date: November 2019
    """
    inc = info["NetCDFConcatenate"]
    # read the input files (data is an OrderedDict)
    data = netcdf_concatenate_read_input_files(info)
    # get the file names in data
    file_names = list(data.keys())
    # get the earliest start time, the latest end time and a list of unique variable names
    for file_name in file_names:
        # get the start and end times
        dt = pfp_utils.GetVariable(data[file_name], "DateTime")
        inc["time_coverage_start"].append(dt["Data"][0])
        inc["time_coverage_end"].append(dt["Data"][-1])
        inc["labels"] = inc["labels"] + list(data[file_name].root["Variables"].keys())
    # get a list of unique variable names and remove unwanted labels
    inc["labels"] = list(set(inc["labels"]))
    # get a list of files with start times in chronological order
    inc["chrono_files"] = [f for d, f in sorted(zip(inc["time_coverage_start"], inc["in_file_names"]))]
    # remove depreacted variables
    netcdf_concatenate_remove_depreacted(info)
    # check units for each variable are consistent across all files to be concatenated
    netcdf_concatenate_check_units_standard_name(data, info)
    # create the output data structure from the input files
    ds_out = netcdf_concatenate_create_ds_out(data, info)
    # truncate the start and the end of the output data structure
    ds_out = netcdf_concatenate_truncate(ds_out, info)
    # get the maximum gap length (in hours) from the control file
    pfp_ts.InterpolateOverMissing(ds_out, inc["labels"], max_length_hours=inc["MaxGapInterpolate"],
                                  int_type="Akima")
    # make sure we have all of the humidities
    pfp_ts.CalculateHumidities(ds_out)
    # and make sure we have all of the meteorological variables
    pfp_ts.CalculateMeteorologicalVariables(ds_out, info)
    # check units of Fc and convert if necessary
    Fc_list = ["Fco2", "Sco2_single", "Sco2_profile", "Sco2_storage"]
    pfp_utils.CheckUnits(ds_out, Fc_list, "umol/m^2/s", convert_units=True)
    # appply the Fco2 storage term if requested
    netcdf_concatenate_apply_sco2_storage(ds_out, info)
    ## use the MAD filer if requested
    #netcdf_concatenate_apply_mad_filter(ds_out, info)
    ## check for MAD filtered variables, revert to no MAD if requested
    #netcdf_concatenate_check_mad_filter(ds_out, info)
    # check missing data and QC flags are consistent
    pfp_utils.CheckQCFlags(ds_out)
    # update the coverage statistics
    pfp_utils.get_coverage_individual(ds_out)
    pfp_utils.get_coverage_groups(ds_out)
    # remove intermediate series
    pfp_ts.RemoveIntermediateSeries(ds_out, info)
    # keep only a subset of variables
    netcdf_concatenate_keep_subset(ds_out, info)
    # rename if output file is the same as one of the input files
    netcdf_concatenate_rename_output(data, inc["out_file_name"])
    logger.info(" Writing data to " + os.path.split(inc["out_file_name"])[1])
    # write the concatenated data structure to file
    NetCDFWrite(inc["out_file_name"], ds_out, ndims=inc["NumberOfDimensions"])
    return

def netcdf_concatenate_apply_sco2_storage(ds, info):
    """
    Purpose:
     Add the storage term to the EC CO2 flux.
    Usage:
    Side effects:
    Author: PRI
    Date: January 2024
    """
    if info["NetCDFConcatenate"]["ApplyFco2Storage"].lower() != "yes":
        return
    # sanity checks
    labels = sorted(list(ds.root["Variables"].keys()))
    if "Fco2" not in labels:
        msg = " Fco2 not in data structure, can't apply storage term"
        logger.warning(msg)
        return
    Fco2 = pfp_utils.GetVariable(ds, "Fco2")
    # has Fco2 already been corrected for storage?
    descr_attrs = [a for a in Fco2["Attr"] if a[0:11] == "description"]
    for descr_attr in descr_attrs:
        if "corrected for storage" in descr_attr.lower():
            msg = " Fco2 already corrected for storage"
            logger.warning(msg)
            return
    if "Sco2_single" not in labels:
        pfp_ts.CalculateSco2SinglePoint(ds)
    labels = sorted(list(ds.root["Variables"].keys()))
    for sco2_label in ["Sco2", "Sco2_storage", "Sco2_profile", "Sco2_single"]:
        if sco2_label in labels:
            msg = " Using " + sco2_label + " as CO2 flux storage term"
            Sco2 = pfp_utils.GetVariable(ds, sco2_label)
            break
    # check the units
    if Fco2["Attr"]["units"] != Sco2["Attr"]["units"]:
        msg = " Units of Fco2 (" + Fco2["Attr"]["units"] + ") and Sco2 ("
        msg += Sco2["Attr"]["units"] + " are different"
        logger.warning(msg)
        return
    # do the business
    descr_level = "description_" + str(ds.root["Attributes"]["processing_level"])
    msg = " Adding storage term " + Sco2["Label"] + " to " + Fco2["Label"]
    logger.info(msg)
    fco2_mask = numpy.ma.getmaskarray(Fco2["Data"])
    sco2_mask = numpy.ma.getmaskarray(Sco2["Data"])
    Fco2["Data"] = Fco2["Data"] + Sco2["Data"]
    idx = numpy.where((fco2_mask==False) & (sco2_mask==True))[0]
    Fco2["Flag"][idx] = int(25)
    tmp = "corrected for storage using " + Sco2["Label"]
    pfp_utils.append_to_attribute(Fco2["Attr"], {descr_level: tmp})
    pfp_utils.CreateVariable(ds, Fco2)
    return

def netcdf_concatenate_rename_output(data, out_file_name):
    """
    Purpose:
     Check to see if the output name is the same as 1 of the input file name
     and if so, rename the input file to prevent overwriting.
    Usage:
    Side effects:
     An input file with the same name as the output file will be renamed to
     include the start and end date in the file name.
    Author: PRI
    Date: July 2021
    """
    file_names = list(data.keys())
    if out_file_name in file_names:
        ds = data[out_file_name]
        start = ds.root["Variables"]["DateTime"]["Data"][0].strftime("%Y%m%d")
        end = ds.root["Variables"]["DateTime"]["Data"][-1].strftime("%Y%m%d")
        rename_part = "_" + start + "_" + end + ".nc"
        output_file_rename = out_file_name.replace(".nc", rename_part)
        msg = " Renaming " + os.path.split(out_file_name)[1] + " to "
        msg += os.path.split(output_file_rename)[1]
        logger.info(msg)
        os.rename(out_file_name, output_file_rename)
    return

def netcdf_concatenate_remove_depreacted(info):
    inc = info["NetCDFConcatenate"]
    items = ["xlDateTime", "DateTime", "Year", "Month", "Day",
             "Hour", "Minute", "Second", "Hdh", "Ddd", "time"]
    for item in items:
        if item in inc["labels"]:
            inc["labels"].remove(item)
    return

def netcdf_concatenate_check_units_standard_name(data, info):
    """
    Purpose:
     Check the units and standard_name for each variable across all files being
     concatenated.
    Usage:
    Side effects:
     Variables that do not have consistent units or standard_name across all files
    being concatenated are removed from the list of variables to be concatenated.
    Author: PRI
    Date: June 2021
    """
    inc = info["NetCDFConcatenate"]
    for label in sorted(list(inc["labels"])):
        units = []
        standard_name = []
        for f in inc["chrono_files"]:
            if label not in list(data[f].root["Variables"].keys()):
                continue
            if "units" in list(data[f].root["Variables"][label]["Attr"].keys()):
                u = data[f].root["Variables"][label]["Attr"]["units"]
                units.append(u)
            if standard_name in list(data[f].root["Variables"][label]["Attr"].keys()):
                s = data[f].root["Variables"][label]["Attr"]["standard_name"]
                standard_name.append(s)
        units_set = list(set(units))
        standard_name_set = list(set(standard_name))
        if len(units_set) > 1:
            msg = " " + label + " units not consistent "
            msg += str(units_set)
            logger.warning(msg)
            for f in inc["chrono_files"]:
                if label in list(data[f].root["Variables"].keys()):
                    msg = os.path.basename(f) + ": "
                    msg += data[f].root["Variables"][label]["Attr"]["units"]
                else:
                    msg = os.path.basename(f) + ": " + label + " not found"
                logger.warning(msg)
            msg = " Variable " + label + " not concatenated"
            logger.warning(msg)
            inc["labels"].remove(label)
        if len(standard_name_set) > 1:
            msg = " " + label + " standard_name not consistent "
            msg += str(standard_name_set)
            logger.warning(msg)
            for f in inc["chrono_files"]:
                if label in list(data[f].root["Variables"].keys()):
                    msg = os.path.basename(f) + ": "
                    msg += data[f].root["Variables"][label]["Attr"]["standard_name"]
                else:
                    msg = os.path.basename(f) + ": " + label + " not found"
                logger.warning(msg)
            msg = "  Variable " + label + " not concatenated"
            logger.warning(msg)
            inc["labels"].remove(label)
    return

def netcdf_concatenate_check_valid_range(data, info):
    """
    Purpose:
     Set the valid_range variable attribute to the minimum and maximum of
     the valid_range for the variable across all files.
    """
    inc = info["NetCDFConcatenate"]
    for label in sorted(list(inc["labels"])):
        valid_min = []
        valid_max = []
        for f in inc["chrono_files"]:
            if label not in list(data[f].root["Variables"].keys()):
                continue
            valid_range = pfp_utils.string_to_list(data[f].root["Variables"][label]["Attr"]["valid_range"])
            valid_min.append(valid_range[0])
            valid_max.append(valid_range[1])
    return

def netcdf_concatenate_create_ds_out(data, info):
    """
    Purpose:
     Create the concatenated data structure from individual year data structures.
    Usage:
     ds_out = netcdf_concatenate_create_ds_out(data, info)
     where;
      data is a dictionary of data structures with the netCDF file names as the keys.
      info is the settings dictionary from pfp_compliance.ParseConcatenateControlFile()
    Side effects:
    Author: PRI
    Date: November 2019
    """
    logger.info(" Creating the output data structure")
    inc = info["NetCDFConcatenate"]
    # get the file names in data
    file_names = list(data.keys())
    # get the time step
    ts = int(float(data[file_names[0]].root["Attributes"]["time_step"]))
    tsd = datetime.timedelta(minutes=ts)
    level = data[file_names[0]].root["Attributes"]["processing_level"]
    # get a continuous time variable
    nsd = min(inc["time_coverage_start"])
    xed = max(inc["time_coverage_end"])
    dt_out = numpy.array([r for r in pfp_utils.perdelta(nsd, xed, tsd)])
    nrecs = len(dt_out)
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    # get the output data structure
    ds_out = DataStructure()
    ds_out.root["Attributes"]["nc_nrecs"] = nrecs
    ds_out.root["Attributes"]["time_step"] = ts
    ds_out.root["Attributes"]["processing_level"] = level
    # create the DateTime variable
    dt = {"Data": dt_out, "Flag": zeros,
          "Attr": {"long_name": "Datetime in local timezone", "units": "None"},
          "Label": "DateTime"}
    pfp_utils.CreateVariable(ds_out, dt)
    # create the netCDF time variable
    pfp_utils.get_nctime_from_datetime(ds_out)
    # make the empty variables
    attr_out = {}
    for label in inc["labels"]:
        ds_out.root["Variables"][label] = pfp_utils.CreateEmptyVariable(label, nrecs, out_type="ndarray")
        attr_out[label] = []
    # now loop over the files in chronological order
    dt_out = pfp_utils.GetVariable(ds_out, "DateTime")
    for n, file_name in enumerate(inc["chrono_files"]):
        # copy the global attributes
        for gattr in data[file_name].root["Attributes"]:
            ds_out.root["Attributes"][gattr] = data[file_name].root["Attributes"][gattr]
        # get the time from the input file
        dt_in = pfp_utils.GetVariable(data[file_name], "DateTime")
        # find the indices of matching times
        indsa, indsb = pfp_utils.FindMatchingIndices(dt_out["Data"], dt_in["Data"])
        # loop over the variables
        for label in inc["labels"]:
            dout = ds_out.root["Variables"][label]
            if label in list(data[file_name].root["Variables"].keys()):
                din = data[file_name].root["Variables"][label]
                # copy input data to output variable
                # NOTE: using direct read from and write to the data structures here,
                #       not recommended but 10x faster than pfp_utils.GetVariable().
                #dout["Data"][indsa] = din["Data"][indsb]
                #dout["Flag"][indsa] = din["Flag"][indsb]
                # 13/3/2022 PRI only copy input data to output data when input data
                #               is not missing
                dout["Data"][indsa] = numpy.where(din["Data"][indsb] != c.missing_value,
                                                  din["Data"][indsb],
                                                  dout["Data"][indsa])
                dout["Flag"][indsa] = numpy.where(din["Data"][indsb] != c.missing_value,
                                                  din["Flag"][indsb],
                                                  dout["Flag"][indsa])
                attr_out[label].append(din["Attr"])
    # copy the variable attributes but only if they don't already exist
    netcdf_concatenate_variable_attributes(ds_out, attr_out, info)
    # update the global attributes
    ds_out.root["Attributes"]["nc_nrecs"] = nrecs
    return ds_out

def netcdf_concatenate_keep_subset(ds_out, info):
    """
    Purpose:
     Delete variables from the data structure except for those specified in the
     SeriesToKeep option.
    Usage:
    Author: PRI
    Date: January 2023
    """
    inc = info["NetCDFConcatenate"]
    if "SeriesToKeep" not in inc:
        return
    msg = " Removing variables not listed in SeriesToKeep"
    logger.info(msg)
    inc_labels = inc["SeriesToKeep"]
    inc_labels.append("DateTime")
    labels = list(ds_out.root["Variables"].keys())
    # any variable that is not included is excluded
    exc_labels = [l for l in labels if l not in inc_labels]
    # except for variables ending in "_notMAD" because these must be preserved
    # for use in the input files for ONEFlux
    exc_labels = [l for l in exc_labels if l[-7:] != "_notMAD"]
    for label in exc_labels:
        pfp_utils.DeleteVariable(ds_out, label)
    return

def netcdf_concatenate_variable_attributes(ds_out, attr_out, info):
    """
    Purpose:
     Update the variable attributes of the concatenated data structure with the following rules:
      - attributes "units" and "standard_name" are checked in netcdf_concatenate_check_units()
        and if there are any inconsistencies across file, the variable is not conatenated
      - by definition then, the variable attribues "units" and "standard_name" have the same
        value across all files by the time we reach here and so they are not checked
      - attributes "height", "instrument", "long_name", "statistic_type" are concatenated
        for each variable across all files, any inconsistencies are flagged to the user
        by a warning message
      - the "valid_range" attribute is separated into "valid_min" and "valid_max", the minimum
        value of "valid_min" and the maximum value of "valid_max" are found and these are
        then used to define a new "valid_range".
    Usage:
     data = netcdf_concatenate_variable_attributes(ds_out, attr_out, info)
     where;
      ds_out is the output data structure
      attr_out is a dictionary of attribute values from each variable from each file
      info is the settings dictionary returned by
              pfp_compliance.ParseConcatenateControlFile(cf)
    Side effects:
    Author: PRI
    Date: November 2019
          June 2021 - rewrite as part of DSA compliance phase 1
    """
    # local pointer to the info dictionary
    inc = info["NetCDFConcatenate"]
    # final attributes dictionary
    attr_final = {}
    # variable labels to be used
    labels = list(attr_out.keys())
    # loop over variables and define entries in attr_final
    for label in labels:
        # define the dictionary
        attr_final[label] = {}
        # add "valid_min" and "valid_max"
        attr_final[label]["valid_min"] = []
        attr_final[label]["valid_max"] = []
        # add the other attributes defined in pfp_compliance.ParseConcatenateControlFile()
        for attr in inc["attributes"]:
            attr_final[label][attr] = []
    # loop over variables and append the attribute values for each variable across all
    # files to a single list
    for label in labels:
        for attrs in attr_out[label]:
            for attr in attrs:
                if attr in inc["attributes"]:
                    if attr == "valid_range":
                        # "valid_range" is split into "valid_min" and "valid_max"
                        valid_min = pfp_utils.string_to_list(attrs[attr])[0]
                        valid_max = pfp_utils.string_to_list(attrs[attr])[1]
                        attr_final[label]["valid_min"].append(valid_min)
                        attr_final[label]["valid_max"].append(valid_max)
                    else:
                        # all other attributes are appended as is
                        attr_final[label][attr].append(attrs[attr])
    # loop over variables and concatenate the variable attributes
    for label in labels:
        # loop over the attributes defined in pfp_compliance.ParseConcatenateControlFile()
        for attr in inc["attributes"]:
            if attr == "valid_range":
                # deal with "valid_range"
                if ((len(attr_final[label]["valid_min"]) == 0) or
                    (len(attr_final[label]["valid_max"]) == 0)):
                    # skip if "valid_min" and "valid_max" not defined for this variable
                    continue
                else:
                    # build new "valid_range" from minimum of "valid_min" and maximum
                    # of "valid_max"
                    valid_min = min(attr_final[label]["valid_min"])
                    valid_max = max(attr_final[label]["valid_max"])
                    valid_range = valid_min + "," + valid_max
                    ds_out.root["Variables"][label]["Attr"]["valid_range"] = valid_range
            else:
                # get a list of unique values for this variable attribute across all files
                attrs = list(set(attr_final[label][attr]))
                # check if there is more than 1 value for all other attributes
                if len(attrs) == 0:
                    # skip if attribute not defined for this variable
                    continue
                elif len(attrs) > 1:
                    # warn the user if there is more than value for this variable attribute
                    msg = " More than 1 value for attribute '" + attr + "' found for " + label
                    logger.warning(msg)
                else:
                    pass
                # update the variable attribute in the data structure
                ds_out.root["Variables"][label]["Attr"][attr] = ",".join(attrs)
    return

def netcdf_concatenate_read_input_files(info):
    """
    Purpose:
     Read the list of input files given in info and return a dictionary
     of data structures.
     The files do not need to be in chronological order.
    Usage:
     data = netcdf_concatenate_read_input_files(info)
     where;
      info is the settings dictionary returned by
              pfp_compliance.ParseConcatenateControlFile(cf)
      data is a dictionary of data structures with the netCDF file
              names as the keys.
    Side effects:
    Author: PRI
    Date: November 2019
    """
    data = OrderedDict()
    file_name = info["NetCDFConcatenate"]["in_file_names"][0]
    data[file_name] = NetCDFRead(file_name)
    if data[file_name].info["returncodes"]["value"] != 0:
        return data
    ts0 = int(float(data[file_name].root["Attributes"]["time_step"]))
    level0 = data[file_name].root["Attributes"]["processing_level"]
    for file_name in info["NetCDFConcatenate"]["in_file_names"][1:]:
        ds = NetCDFRead(file_name)
        if ds.info["returncodes"]["value"] != 0:
            return data
        tsn = int(float(ds.root["Attributes"]["time_step"]))
        leveln = ds.root["Attributes"]["processing_level"]
        if ((tsn == ts0) and (leveln == level0)):
            data[file_name] = ds
        else:
            path, name = os.path.split(file_name)
            if (tsn == ts0):
                msg = " Time stamp wrong for " + name
                msg += ", expected " + str(ts0) + ", got " + str(tsn)
            elif (leveln == level0):
                msg = " Level wrong for " + name
                msg += ", expected " + str(level0) + ", got " + str(leveln)
            else:
                msg = " Unknown error concatenating " + name
            logger.warning(msg)
    return data

def netcdf_concatenate_truncate(ds_in, info):
    """
    Purpose:
     Truncate the start and end of the data structure by removiong times when
     there is less than a specified threshold of selected data available.
    Usage:
     ds_out = pfp_io.netcdf_concatenate_truncate(ds, info)
     where ds is the input data structure
           info is the settings dictionary from pfp_compliance.ParseConcatenateControlFile()
           ds_out is the truncated data structure
    Author: PRI
    Date: November 2019
    """
    inc = info["NetCDFConcatenate"]
    if inc["Truncate"] != "Yes":
        return ds_in
    # copy the input data structure
    ds_out = copy.deepcopy(ds_in)
    # get the datetime
    ldt = pfp_utils.GetVariable(ds_out, "DateTime")
    nrecs = int(ds_out.root["Attributes"]["nc_nrecs"])
    cidx = numpy.zeros(nrecs)
    if inc["SeriesToCheck"][0].lower() == "all":
        inc["SeriesToCheck"] = sorted(list(ds_out.root["Variables"].keys()))
    for item in list(inc["SeriesToCheck"]):
        if item not in list(ds_out.root["Variables"].keys()):
            inc["SeriesToCheck"].remove(item)
            continue
        var = pfp_utils.GetVariable(ds_out, item)
        idx = numpy.where(numpy.ma.getmaskarray(var["Data"]) == False)[0]
        cidx[idx] = cidx[idx] + 1
    cidx = cidx/float(len(inc["SeriesToCheck"]))
    # find the first and last element where more than 50% data is present
    threshold = float(inc["TruncateThreshold"])/float(100)
    idx = numpy.where(cidx >= threshold)[0]
    si = idx[0]
    if si != 0:
        msg = " Start date truncated from " + str(ldt["Data"][0]) + " to " + str(ldt["Data"][si])
        logger.info(msg)
    ei = idx[-1]
    if ei != nrecs-1:
        msg = " End date truncated from " + str(ldt["Data"][-1]) + " to " + str(ldt["Data"][ei])
        logger.info(msg)
    # now loop over the data series and truncate
    for item in list(ds_out.root["Variables"].keys()):
        ds_out.root["Variables"][item]["Data"] = ds_out.root["Variables"][item]["Data"][si:ei+1]
        ds_out.root["Variables"][item]["Flag"] = ds_out.root["Variables"][item]["Flag"][si:ei+1]
    # update the relevent global attributes
    ds_out.root["Attributes"]["time_coverage_start"] = ldt["Data"][si]
    ds_out.root["Attributes"]["time_coverage_end"] = ldt["Data"][ei]
    ds_out.root["Attributes"]["nc_nrecs"] = len(ds_out.root["Variables"]["DateTime"]["Data"])
    return ds_out

def MergeDataFrames(dfs, l1_info):
    """
    Purpose:
     Merge several data frames into a single data frame.
     pfp_io.ReadExcelWorkbook() returns one pandas data frame per worksheet in the
     workbook.  This routine combines these data frames into a single data frame
     that spans all of the times on the worksheets.
    Usage:
     df = pfp_io.MergeDataFrames(dfs, l1_info)
     where dfs is a dictionary of pandas data frames
           l1_info is the information dictionary created from the L1 control file
           df is a single pandas data frame containing all data from the data frames
              in dfs.
    Side effects:
     Returns a pandas data frame.
    Author: PRI
    DaMergeDataFrameste: Back in the day
    """
    # get a list of data frame names
    df_names = list(dfs)
    # merge data frames
    if len(df_names) > 1:
        msg = " Merging into a single data frame"
        logger.info(msg)
        # get the earliest start and latest end time
        start = min(dfs[df_names[0]].index.values)
        end = max(dfs[df_names[0]].index.values)
        for df_name in df_names[1:]:
            start = min([min(dfs[df_name].index.values), start])
            end = max([max(dfs[df_name].index.values), end])
        # get the timestep as a string pandas will recognise
        ts = str(int(l1_info["read_excel"]["Global"]["time_step"])) + "min"
        # create a pandas datetime range
        dt = pandas.date_range(start, end, freq=ts)
        # create an empty data frame
        df = pandas.DataFrame({'DateTime': dt})
        # set the datetime as the index
        df = df.set_index("DateTime")
        # list of data frames
        frames = [df] + [dfs[s] for s in sorted(list(dfs.keys()))]
        # merge the data frames on columns (axis=1)
        df = pandas.concat(frames, axis=1)
    else:
        df = dfs[df_names[0]]
    return df

def MergeDataStructures(ds_dict, l1_info):
    """
    Purpose:
     Merge multiple data structures into a single data structure.
     Merging is done on the time axis as follows:
      1) find the earliest start time
      2) find the latest end time
      3) construct a datetime series between the earliest start datetime
         and the latest end datetime at the time step interval
      4) create the datetime series in the merged data structure
      5) insert the data from each individual data structure into
         the merged data structure by matching the datetimes
    Usage:
    Side effects:
     Returns a new data structure with the contents of the individual
     data structures passed in as ds_dict.
    Author: PRI
    Date: February 2020
    """
    msg = " Merging " + str(list(ds_dict.keys()))
    logger.info(msg)
    l1ire = l1_info["read_excel"]
    # data structure to hold all data
    ds = DataStructure()
    ds.root["Attributes"] = copy.deepcopy(l1ire["Global"])
    # get the earliest start datetime and the latest datetime
    start = []
    end = []
    for item in list(ds_dict.keys()):
        start.append(ds_dict[item].root["Variables"]["DateTime"]["Data"][0])
        end.append(ds_dict[item].root["Variables"]["DateTime"]["Data"][-1])
    start = min(start)
    end = max(end)
    # put the datetime into the data structure
    ts = int(float(ds.root["Attributes"]["time_step"]))
    dts = datetime.timedelta(minutes=ts)
    # generate an aray of datetime from start to end with spacing of ts
    dt = numpy.array([d for d in pfp_utils.perdelta(start, end, dts)])
    nrecs = len(dt)
    var = pfp_utils.CreateEmptyVariable("DateTime", nrecs)
    var["Label"] = "DateTime"
    var["Data"] = dt
    var["Flag"] = numpy.zeros(len(var["Data"]), dtype=numpy.int32)
    var["Attr"] = {"long_name": "Datetime in local timezone",
                   "cf_role": "timeseries_id",
                   "units": "days since 1899-12-31 00:00:00"}
    pfp_utils.CreateVariable(ds, var)
    # update the global attributes
    ds.root["Attributes"]["time_coverage_start"] = str(dt[0])
    ds.root["Attributes"]["time_coverage_end"] = str(dt[-1])
    ds.root["Attributes"]["nc_nrecs"] = len(dt)
    # put the data into the data structure
    dt1 = pfp_utils.GetVariable(ds, "DateTime")
    for item in list(ds_dict.keys()):
        #print item
        # get the datetime for this worksheet
        dtn = pfp_utils.GetVariable(ds_dict[item], "DateTime")
        # remove duplicate timestamps
        dtn_unique, index_unique = numpy.unique(dtn["Data"], return_index=True)
        # restore the original order of the unique timestamps
        dtn_sorted = dtn_unique[numpy.argsort(index_unique)]
        # check to see if there were duplicates
        if len(dtn_sorted) < len(dtn["Data"]):
            n = len(dtn["Data"]) - len(dtn_sorted)
            msg = str(n) + " duplicate time stamps were removed for sheet " + item
            logger.warning(msg)
        # get the indices where the timestamps match
        idxa, idxb = pfp_utils.FindMatchingIndices(dt1["Data"], dtn_sorted)
        # check that all datetimes in ds_dict[item] were found in ds
        if len(idxa) != len(dtn_sorted):
            no_match = 100*(len(dtn_sorted) - len(idxa))//len(dtn_sorted)
            msg = str(no_match) + "% of time stamps for " + item + " do not match"
            logger.warning(msg)
        labels = list(ds_dict[item].root["Variables"].keys())
        if "DateTime" in labels:
            labels.remove("DateTime")
        for label in labels:
            var1 = pfp_utils.CreateEmptyVariable(label, nrecs)
            varn = pfp_utils.GetVariable(ds_dict[item], label)
            var1["Data"][idxa] = varn["Data"][idxb]
            var1["Flag"][idxa] = varn["Flag"][idxb]
            var1["Attr"] = varn["Attr"]
            pfp_utils.CreateVariable(ds, var1)
    return ds

def ncsplit_run(split_gui):
    infilename = split_gui.info["input_file_path"]
    outfilename = split_gui.info["output_file_path"]
    startdate = split_gui.info["startdate"]
    enddate = split_gui.info["enddate"]
    msg = " Splitting " + os.path.basename(infilename) + " between "
    msg = msg + startdate + " and " + enddate
    logger.info(msg)
    msg = " Output to " + os.path.basename(outfilename)
    logger.info(msg)
    # read the input file into the input data structure
    #ds_in = split_gui.ds
    ds_in = NetCDFRead(infilename)
    if ds_in.info["returncodes"]["value"] != 0: return
    ts = int(float(ds_in.root["Attributes"]["time_step"]))
    ldt_in = ds_in.root["Variables"]["DateTime"]["Data"]
    ldt_in_flag = ds_in.root["Variables"]["DateTime"]["Flag"]
    # create the output data structure
    ds_out = DataStructure()
    # copy the global attributes
    for item in list(ds_in.root["Attributes"].keys()):
        ds_out.root["Attributes"][item] = ds_in.root["Attributes"][item]
    # get the indices of the start and end datetimes
    si = pfp_utils.GetDateIndex(ldt_in,startdate,ts=ts,default=0,match="exact")
    ei = pfp_utils.GetDateIndex(ldt_in,enddate,ts=ts,default=len(ldt_in),match="exact")
    # get a list of the series in ds_in
    series_list = [item for item in list(ds_in.root["Variables"].keys()) if "_QCFlag" not in item]
    # remove the Python datetime series
    for item in ["DateTime","DateTime_UTC"]:
        if item in series_list: series_list.remove(item)
    # loop over the series
    for item in series_list:
        var = pfp_utils.GetVariable(ds_in, item, start=si, end=ei)
        pfp_utils.CreateVariable(ds_out, var)
    # deal with the Python datetime series
    ldt_out = ldt_in[si:ei+1]
    ldt_out_flag = ldt_in_flag[si:ei+1]
    ds_out.root["Variables"]["DateTime"] = {}
    ds_out.root["Variables"]["DateTime"]["Data"] = ldt_out
    ds_out.root["Variables"]["DateTime"]["Flag"] = ldt_out_flag
    ds_out.root["Variables"]["DateTime"]["Attr"]= ds_in.root["Variables"]["DateTime"]["Attr"]
    # update the number of records global attribute
    ds_out.root["Attributes"]["nc_nrecs"] = len(ldt_out)
    # update the start and end datetime global attribute
    ds_out.root["Attributes"]["time_coverage_start"] = str(ldt_out[0])
    ds_out.root["Attributes"]["time_coverage_end"] = str(ldt_out[-1])
    # write the output data structure to a netCDF file
    NetCDFWrite(outfilename, ds_out)
    msg = " Finished splitting " + os.path.basename(infilename)
    logger.info(msg)

def nc_read_groups(nc_file):
    """
    Purpose:
     Read a netCDF4 file that contains groups and return a data structure with
     the same groups.
    Usage:
    Side effects:
    Author: PRI
    Date: July 2022
    """
    groups = list(nc_file.groups.keys())
    msg = " Reading netCDF file with groups"
    logger.info(msg)
    # disable automatic masking of data when valid_range specified
    nc_file.set_auto_mask(False)
    ds = DataStructure(groups=groups)
    ds.info["filepath"] = nc_file.filepath()
    # now deal with the global attributes
    gattrs = nc_file.ncattrs()
    if len(gattrs) != 0:
        for gattr in gattrs:
            ds.root["Attributes"][gattr] = getattr(nc_file, gattr)
    for grp in groups:
        group = getattr(ds, grp)
        labels = sorted(list(nc_file[grp].variables.keys()))
        for item in ["latitude", "longitude"]:
            if item in labels:
                labels.remove(item)
        for label in labels:
            data, flag, attr = nc_read_var(nc_file[grp], label)
            var = {"Label": label, "Data": data, "Flag": flag, "Attr": attr}
            pfp_utils.CreateVariable(ds, var, group=grp)
        # get the Python datetime from the netCDF time
        nrecs = len(group["Variables"]["time"]["Data"])
        dt = cftime.num2date(group["Variables"]["time"]["Data"],
                             group["Variables"]["time"]["Attr"]["units"],
                             only_use_cftime_datetimes=False,
                             only_use_python_datetimes=True)
        calendar = "gregorian"
        if "calendar" in group["Variables"]["time"]["Attr"]:
            calendar = group["Variables"]["time"]["Attr"]["calendar"]
        var = {"Label": "DateTime", "Data": dt, "Flag": numpy.zeros(nrecs),
               "Attr": {"long_name": "Datetime in local timezone", "units": "",
                        "calendar": calendar}}
        pfp_utils.CreateVariable(ds, var, group=grp)
        # get the group attributes
        gattrs = nc_file[grp].ncattrs()
        # trap legacy L6 summary files with no group attributes
        if len(gattrs) > 0:
            # group attributes present
            for gattr in gattrs:
                group["Attributes"][gattr] = getattr(nc_file[grp], gattr)
        else:
            # group attributes not present so we deduce them from ncfile
            group["Attributes"]["nc_nrecs"] = nrecs
            if grp.lower() in ["daily", "monthly", "annual"]:
                ts = grp.lower()
            else:
                ts = ds.root["Attributes"]["time_step"]
            group["Attributes"]["time_step"] = ts
    nc_file.close()
    ds.info["returncodes"]["value"] = 0
    ds.info["returncodes"]["message"] = "netCDF file read OK"
    return ds

def nc_read_series(nc_file, checktimestep=True, fixtimestepmethod="round"):
    """
    Purpose:
     Reads a netCDF file and returns the meta-data and data in a DataStructure.
     The returned data structure is an instance of pfp_io.DataStructure().
     The data structure consists of:
      1) ds.root["Attributes"]
         A dictionary containing the global attributes of the netCDF file.
      2) ds.root["Variables"]
         A dictionary containing the variable data, meta-data and QC flag
         Each variable dictionary in ds.root["Variables"] contains;
         a) ds.root["Variables"][variable]["Data"]
            A 1D numpy float64 array containing the variable data, missing
            data value is -9999.
         b) ds.root["Variables"][variable]["Flag"]
            A 1D numpy int32 array containing the QC flag data for this variable.
         c) ds.root["Variables"][variable]["Attr"]
            A dictionary containing the variable attributes.
    Usage:
     nc_name = pfp_io.get_filename_dialog(path="../Sites/Whroo/Data/Processed/")
     ds = pfp_io.nc_read_series(nc_name)
     where nc_name is the full name of the netCDF file to be read
           ds is the returned data structure
    Side effects:
     This routine checks the time step of the data read from the netCDF file
     against the value of the global attribute "time_step", see pfp_utils.CheckTimeStep.
     If a problem is found with the time step (duplicate records, non-integral
     time steps or gaps) then pfp_utils.FixTimeStep is called to repair the time step.
     Fixing non-integral timne steps requires some user input.  The options are to
     quit ([Q]), interpolate ([I], not implemented yet) or round ([R]).  Quitting
     causes the script to exit and return to the command prompt.  Interpolation
     is not implemented yet but will interpolate the data from the original time
     step to a regular time step.  Rounding will round any non-itegral time steps
     to the nearest time step.
    Author: PRI
    Date: Back in the day
    """
    logger.info(" Reading netCDF file " + os.path.basename(nc_file.filepath()))
    # disable automatic masking of data when valid_range specified
    nc_file.set_auto_mask(False)
    # get an instance of a PFP data structure
    ds = DataStructure()
    ds.info["filepath"] = nc_file.filepath()
    # now deal with the global attributes
    gattrlist = nc_file.ncattrs()
    if len(gattrlist) != 0:
        for gattr in gattrlist:
            ds.root["Attributes"][gattr] = getattr(nc_file, gattr)
    if "processing_level" not in ds.root["Attributes"]:
        if "nc_level" in ds.root["Attributes"]:
            ds.root["Attributes"]["processing_level"] = ds.root["Attributes"]["nc_level"]
        else:
            msg = "  No processing level in global attributes, set to unknown"
            logger.warning(msg)
            ds.root["Attributes"]["processing_level"] = "unknown"
    # get a list of the variables in the netCDF file (not their QC flags)
    varlist = [x for x in list(nc_file.variables.keys()) if "_QCFlag" not in x]
    for ThisOne in varlist:
        # skip variables that do not have time as a dimension
        dimlist = [x.lower() for x in nc_file.variables[ThisOne].dimensions]
        if "time" not in dimlist: continue
        # create the series in the data structure
        ds.root["Variables"][str(ThisOne)] = {}
        # get the data and the QC flag
        data, flag, attr = nc_read_var(nc_file, ThisOne)
        ds.root["Variables"][ThisOne]["Data"] = data
        ds.root["Variables"][ThisOne]["Flag"] = flag
        ds.root["Variables"][ThisOne]["Attr"] = attr
    # get a series of Python datetime objects
    labels = list(ds.root["Variables"].keys())
    if "time" in labels:
        pfp_utils.get_datetime_from_nctime(ds)
    elif (("Year" in labels) and ("Month" in labels) and ("Day" in labels) and
          ("Hour" in labels) and ("Minute" in labels) and ("Second" in labels)):
        pfp_utils.get_datetime_from_ymdhms(ds)
    elif "xlDateTime" in labels:
        pfp_utils.get_datetime_from_xldatetime(ds)
    else:
        msg = "Unable to find any datetime data in netCDF file"
        logger.error(msg)
        raise RuntimeError(msg)
    nc_file.close()
    # check to see if we have the "nc_nrecs" global attribute
    if "nc_nrecs" not in list(ds.root["Attributes"].keys()):
        ds.root["Attributes"]["nc_nrecs"] = str(len(ds.root["Variables"]["DateTime"]["Data"]))
    # round the Python datetime to the nearest second
    pfp_utils.round_datetime(ds, mode="nearest_second")
    # check the time step and fix it required
    if checktimestep:
        if pfp_utils.CheckTimeStep(ds):
            pfp_utils.FixTimeStep(ds, fixtimestepmethod=fixtimestepmethod)
    # tell the user when the data starts and ends
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    msg = "  Got data from " + ldt[0].strftime("%Y-%m-%d %H:%M:%S")
    msg += " to " + ldt[-1].strftime("%Y-%m-%d %H:%M:%S")
    logger.info(msg)
    ds.info["returncodes"]["value"] = 0
    ds.info["returncodes"]["message"] = "netCDF file read OK"
    return ds

def nc_read_var(ncFile,ThisOne):
    """ Reads a variable from a netCDF file and returns the data, the QC flag and the variable
        attribute dictionary.
    """
    # check the number of dimensions
    nDims = len(ncFile.variables[ThisOne].shape)
    if nDims not in [1,3,4]:
        msg = "nc_read_var: unrecognised number of dimensions ("+str(nDims)
        msg = msg+") for netCDF variable "+ ThisOne
        raise Exception(msg)
    if nDims==1:
        # single dimension
        data = ncFile.variables[ThisOne][:]
        # netCDF4 returns a masked array if the "missing_variable" attribute has been set
        # for the variable, here we trap this and force the array in ds.root["Variables"] to be ndarray
        if numpy.ma.isMA(data): data,dummy = pfp_utils.MAtoSeries(data)
        # check for a QC flag
        if ThisOne+'_QCFlag' in list(ncFile.variables.keys()):
            # load it from the netCDF file
            flag = ncFile.variables[ThisOne+'_QCFlag'][:]
        else:
            # create an empty flag series if it does not exist
            nRecs = numpy.size(data)
            flag = numpy.zeros(nRecs,dtype=numpy.int32)
        # trap non-finite values and set them to c.missing_value
        if not numpy.isfinite(data).all():
            idx = numpy.where(numpy.isfinite(data) == False)[0]
            data[idx] = numpy.float64(c.missing_value)
            idx = numpy.where((numpy.isfinite(data) == False) & (flag == 0))[0]
            flag[idx] = numpy.int32(8)
    elif nDims==3:
        # 3 dimensions
        data = ncFile.variables[ThisOne][:,0,0]
        # netCDF4 returns a masked array if the "missing_variable" attribute has been set
        # for the variable, here we trap this and force the array in ds.root["Variables"] to be ndarray
        # may not be needed after adding ncFile.set_auto_mask(False) in nc_read_series().
        if numpy.ma.isMA(data): data,dummy = pfp_utils.MAtoSeries(data)
        # check for a QC flag
        if ThisOne+'_QCFlag' in list(ncFile.variables.keys()):
            # load it from the netCDF file
            flag = ncFile.variables[ThisOne+'_QCFlag'][:,0,0]
        else:
            # create an empty flag series if it does not exist
            nRecs = numpy.size(data)
            flag = numpy.zeros(nRecs,dtype=numpy.int32)
        # trap non-finite values and set them to c.missing_value
        if not numpy.isfinite(data).all():
            idx = numpy.where(numpy.isfinite(data) == False)[0]
            data[idx] = numpy.float64(c.missing_value)
            idx = numpy.where((numpy.isfinite(data) == False) & (flag == 0))[0]
            flag[idx] = numpy.int32(8)
    elif nDims==4:
        # 4 dimensions, this is specific to ERA5T data where 0 is ERA5 and 1 is ERA5T data
        data0 = ncFile.variables[ThisOne][:,0,0,0]
        data1 = ncFile.variables[ThisOne][:,1,0,0]
        data = numpy.ma.where(data0.mask == False,data0,data1)
        # netCDF4 returns a masked array if the "missing_variable" attribute has been set
        # for the variable, here we trap this and force the array in ds.root["Variables"] to be ndarray
        # may not be needed after adding ncFile.set_auto_mask(False) in nc_read_series().
        if numpy.ma.isMA(data): data,dummy = pfp_utils.MAtoSeries(data)
        # check for a QC flag
        if ThisOne+'_QCFlag' in list(ncFile.variables.keys()):
            # load it from the netCDF file
            flag = ncFile.variables[ThisOne+'_QCFlag'][:,0,0]
        else:
            # create an empty flag series if it does not exist
            nRecs = numpy.size(data)
            flag = numpy.zeros(nRecs,dtype=numpy.int32)
        # trap non-finite values and set them to c.missing_value
        if not numpy.isfinite(data).all():
            idx = numpy.where(numpy.isfinite(data) == False)[0]
            data[idx] = numpy.float64(c.missing_value)
            idx = numpy.where((numpy.isfinite(data) == False) & (flag == 0))[0]
            flag[idx] = numpy.int32(8)
    # force float32 to float64
    if data.dtype=="float32": data = data.astype(numpy.float64)
    # check for Year, Month etc as int64, force to int32 if required
    if ThisOne in ["Year","Month","Day","Hour","Minute","Second"]:
        if data.dtype=="int64": data = data.astype(numpy.int32)
    # get the variable attributes
    vattrlist = ncFile.variables[ThisOne].ncattrs()
    attr = {}
    if len(vattrlist) != 0:
        for vattr in vattrlist:
            va = getattr(ncFile.variables[ThisOne], vattr)
            if isinstance(va, numpy.ndarray):
                attr[vattr] = ",".join([str(i) for i in va])
            else:
                attr[vattr] = va
    return data, flag, attr

def ds_update(ds):
    """
    Purpose:
     Update the contents of a data structure.
     This is where we can change variable names, attributes etc if we change
     some aspect of netCDF files.  For example, V3.3.0 used for ODW2021
     used "standard deviation" as a statistic type.  This changed to
     "statistic_type" in V3.3.1.
     This routine updates a data structure if required.  If the data structure
     is modified, the original netCDF file is overwritten with the modified
     data structure.
    Usage:
    Side effects:
     The original netCDF file is overwritten if the data structure is changed.
    Author: PRI
    Date: November 2021
    """
    ds_changed = False
    # update global attributes
    # trap old files using nc_level and rename to processing_level
    if "nc_level" in ds.root["Attributes"]:
        ds.root["Attributes"]["processing_level"] = ds.root["Attributes"]["nc_level"]
        ds_changed = True
    # get a list of the variables in the data structure
    labels = list(ds.root["Variables"].keys())
    # loop over the variables in the data structure
    for label in labels:
        # get the variable
        variable = pfp_utils.GetVariable(ds, label)
        # check "statistic_type" is present
        variable_changed = ds_update_statistic_type(variable)
        # check to see if this variable has been changed
        if variable_changed:
            # write the variable to the data structure if it has changed
            pfp_utils.CreateVariable(ds, variable)
            ds_changed = True
    # check to see if the data structure has changed
    if ds_changed:
        # write the changed data structure to file
        file_name = os.path.basename(ds.info["filepath"])
        msg = "  Saving updated file " + file_name
        logger.info(msg)
        NetCDFWrite(ds.info["filepath"], ds)
    return ds

def ds_update_statistic_type(variable):
    """
    Purpose:
     Update the statistic_type attribute of a variable.
    Usage:
    Author: PRI
    Date: November 2021
    """
    variable_changed = False
    if variable["Label"] not in ["time", "DateTime"]:
        if "statistic_type" not in variable["Attr"]:
            # set the statistic_type attribute
            variable_changed = True
            if "Precip" in variable["Label"]:
                variable["Attr"]["statistic_type"] = "sum"
            elif variable["Label"][-3:] == "_Sd":
                variable["Attr"]["statistic_type"] = "standard_deviation"
            elif variable["Label"][-3:] == "_Vr":
                variable["Attr"]["statistic_type"] = "variance"
            else:
                variable["Attr"]["statistic_type"] = "average"
        # replace "standard deviation" with "standard_deviation"
        else:
            if variable["Attr"]["statistic_type"] == "standard deviation":
                variable["Attr"]["statistic_type"] = "standard_deviation"
                variable_changed = True
    else:
        pass
    return variable_changed

def NetCDFRead(nc_file_uri, checktimestep=True, fixtimestepmethod="round", update=False):
    """
    Purpose:
     Wrapper for the pfp_io.nc_read_series() routine so we have a nice name
     to use.  Over time, pfp_io.nc_read_series() will be rewritten and
     eventualy deprecated.
    Usage:
     ds = pfp_io.NetCDFRead(nc_file_uri)
     where nc_file_uri is a netCDF file name or URL pointing to a netCDF file
           ds is a PFP data structure
    Author: PRI
    Date: June 2021
    """
    if not os.path.isfile(nc_file_uri):
        msg = nc_file_uri + " not found"
        logger.error(msg)
        raise RuntimeError(msg)
    # file probably exists, so let's read it
    nc_file = netCDF4.Dataset(nc_file_uri, "r")
    if len(nc_file.groups.keys()) == 0:
        ds = nc_read_series(nc_file,
                            checktimestep=checktimestep,
                            fixtimestepmethod=fixtimestepmethod)
    else:
        ds = nc_read_groups(nc_file)
    if update:
        ds = ds_update(ds)
    return ds

def NetCDFWrite(nc_file_path, ds, nc_type='NETCDF4', outputlist=None, ndims=3):
    """
    Purpose:
     Wrapper for the pfp_io.nc_write_series() routine so we have a nice name
     to use.  Over time, pfp_io.nc_write_series() will be rewritten and
     eventualy deprecated.
    Usage:
     pfp_io.NetCDFWrite(nc_file_uri, ds)
     where nc_file_uri is a netCDF file name or URL pointing to a netCDF file
           ds is a PFP data structure
    Author: PRI
    Date: June 2021
    """
    file_name = os.path.split(nc_file_path)
    msg = " Writing netCDF file " + file_name[1]
    logger.info(msg)
    try:
        nc_file = netCDF4.Dataset(nc_file_path, "w", format=nc_type)
        groups = list(vars(ds))
        if "info" in groups:
            groups.remove("info")
        if len(groups) == 1:
            # write the global attributes to the netCDF file
            nc_write_globalattributes(nc_file, ds)
            nc_write_series(nc_file, ds, outputlist=None, ndims=3)
        elif len(groups) > 1:
            # write the global attributes to the netCDF file
            nc_write_globalattributes(nc_file, ds)
            for group in groups:
                dsg = getattr(ds, group)
                if len(dsg["Variables"]) == 0:
                    continue
                nc_group = nc_file.createGroup(group)
                nc_write_group(nc_group, ds, group)
        nc_file.close()
    except Exception:
        msg = " Unable to write netCDF file " + file_name[1]
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
        nc_file.close()
        return
    return

def nc_open_write(ncFullName, nctype='NETCDF4', mode="verbose"):
    """
    Purpose:
     Opens a netCDF file object for writing.  The opened netCDF file
     object is then passed as an argument to pfp_io.nc_write_series, where
     the actual writing of data occurs.
    Usage:
     nc_name = '../Sites/Whroo/Data/Processed/all/Whroo_L4.nc'
     nc_file = pfp_io.nc_open_write(nc_name)
     where nc_name is the ful file name of the netCDF to be written
           nc_file is the returned netCDF file object
    Author: PRI
    Date: Back in the day
    """
    file_name = os.path.split(ncFullName)
    if mode != "quiet":
        logger.info(" Opening netCDF file " + file_name[1])
    try:
        ncFile = netCDF4.Dataset(ncFullName, "w", format=nctype)
    except:
        logger.error(" Unable to open netCDF file " + file_name[1] + " for writing")
        ncFile = None
    return ncFile

def nc_write_globalattributes(nc_file, ds, flag_defs=True):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: Back in the day
    """
    # check to see if we have a DataStructure or a dictionary
    if isinstance(ds, DataStructure):
        # get a local dictionary from a DataStructure
        lds = {"globalattributes": ds.root["Attributes"],
               "variables": ds.root["Variables"]}
    elif isinstance(ds, dict):
        # check to see if 'globalattributes' and 'variables' in dictionary
        if (("globalattributes" in ds) and ("variables" in ds)):
            lds = {"globalattributes": ds["globalattributes"],
                   "variables": ds["variables"]}
        else:
            msg = "Dict doesn't contain expected contents "
            msg += "'globalattributes' or 'variables'"
            logger.error(msg)
            raise RuntimeError(msg)
    else:
        msg = "Expected DataStructure or dictionary for 'ds'"
        msg += ", got " + type(ds)
        logger.error(msg)
        raise RuntimeError(msg)
    lds["globalattributes"]["pyfluxpro_version"] = str(cfg.version_name)+' '+str(cfg.version_number)
    if "DateTime" in lds["variables"]:
        ldt = lds["variables"]["DateTime"]["Data"]
        lds["globalattributes"]["time_coverage_start"] = str(ldt[0])
        lds["globalattributes"]["time_coverage_end"] = str(ldt[-1])
    t = time.localtime()
    lds["globalattributes"]["date_created"] = str(datetime.datetime(t[0],t[1],t[2],t[3],t[4],t[5]))
    gattrs = sorted(list(lds["globalattributes"].keys()))
    flags = []
    attrs = []
    for item in gattrs:
        if "Flag" in item:
            flags.append(item)
        else:
            attrs.append(item)
    for item in attrs:
        if isinstance(lds["globalattributes"][item], str):
            attr = lds["globalattributes"][item].encode('ascii', 'ignore')
        else:
            attr = str(lds["globalattributes"][item])
        setattr(nc_file, item, attr)
    if flag_defs:
        for item in flags:
            if isinstance(lds["globalattributes"][item], str):
                attr = lds["globalattributes"][item].encode('ascii', 'ignore')
            else:
                attr = str(lds["globalattributes"][item])
            setattr(nc_file, item, attr)
    return

def nc_write_group(nc_obj, ds, group):
    """
    Purpose:
     Write the L6 summary statistics (daily, monthly, annual and cumulative)
     to a single netCDF file with different groups for each time period.
    Usage:
    Author: PRI
    Date: January 2018
    """
    dsr = getattr(ds, "root")
    dsg = getattr(ds, group)
    # sanity check
    if "Attributes" not in list(dsg.keys()):
        msg = " Data structure group " + group + " has no 'Attributes'"
        logger.error(msg)
        raise RuntimeError(msg)
    if "Variables" not in list(dsg.keys()):
        msg = " Data structure group " + group + " has no 'Variables'"
        logger.error(msg)
        raise RuntimeError(msg)
    # write the group attributes
    gattrs = sorted(list(dsg["Attributes"].keys()))
    for gattr in gattrs:
        setattr(nc_obj, gattr, dsg["Attributes"][gattr])
    # write the group variables
    gvars = sorted(list(dsg["Variables"].keys()))
    if len(gvars) == 0:
        return
    dt = dsg["Variables"]["DateTime"]["Data"]
    nrecs = len(dt)
    # and give it dimensions of time, latitude and longitude
    nc_obj.createDimension("time", nrecs)
    nc_obj.createDimension("latitude", 1)
    nc_obj.createDimension("longitude", 1)
    dims = ("time", "latitude", "longitude")
    # write the time variable to the netCDF object
    nc_time_units = "days since 1800-01-01 00:00:00.0"
    nc_time = pfp_utils.get_nctime_from_datetime_data(dt, nc_time_units=nc_time_units)
    nc_var = nc_obj.createVariable("time", "d", ("time",))
    nc_var[:] = nc_time
    nc_var.setncattr("long_name", "time")
    nc_var.setncattr("standard_name", "time")
    nc_var.setncattr("units", nc_time_units)
    # write the latitude and longitude variables to the group
    nc_var = nc_obj.createVariable("latitude", "d", ("latitude",))
    nc_var[:] = float(dsr["Attributes"]["latitude"])
    nc_var.setncattr('long_name', 'latitude')
    nc_var.setncattr('standard_name', 'latitude')
    nc_var.setncattr('units', 'degrees north')
    nc_var = nc_obj.createVariable("longitude", "d", ("longitude",))
    nc_var[:] = float(dsr["Attributes"]["longitude"])
    nc_var.setncattr('long_name', 'longitude')
    nc_var.setncattr('standard_name', 'longitude')
    nc_var.setncattr('units', 'degrees east')
    # get a list of variables to write to the netCDF file
    labels = sorted([l for l in list(dsg["Variables"].keys()) if l not in ["DateTime", "time"]])
    # write the variables to the netCDF file object
    for label in labels:
        nc_var = nc_obj.createVariable(label, "d", dims)
        nc_var[:, 0, 0] = dsg["Variables"][label]["Data"].tolist()
        for attr_key in dsg["Variables"][label]["Attr"]:
            if attr_key not in ["format"]:
                attr_value = dsg["Variables"][label]["Attr"][attr_key]
                nc_var.setncattr(attr_key, attr_value)
    return

def nc_write_series(ncFile, ds, outputlist=None, ndims=3):
    """
    Purpose:
     Write the contents of a data structure to a netCDF file.
    Usage:
     nc_file = pfp_io.nc_open_write(nc_name)
     pfp_io.nc_write_series(nc_file,ds)
     where nc_file is a netCDF file object returned by pfp_io.nc_open_write
           ds is a data structure
    Author: PRI
    Date: Back in the day
    """
    # we specify the size of the Time dimension because netCDF4 is slow to write files
    # when the Time dimension is unlimited
    nRecs = int(ds.root["Attributes"]['nc_nrecs'])
    ncFile.createDimension("time",nRecs)
    if ndims==3:
        ncFile.createDimension("latitude",1)
        ncFile.createDimension("longitude",1)
        dims = ("time","latitude","longitude")
    else:
        dims = ("time",)
    if outputlist is None:
        outputlist = list(ds.root["Variables"].keys())
    else:
        for ThisOne in outputlist:
            if ThisOne not in list(ds.root["Variables"].keys()):
                logger.warning(" Requested series "+ThisOne+" not found in data structure")
                outputlist.remove(ThisOne)
        if len(outputlist)==0: outputlist = list(ds.root["Variables"].keys())
    # can't write an array of Python datetime objects to a netCDF file
    # actually, this could be written as characters
    for ThisOne in ["DateTime","DateTime_UTC"]:
        if ThisOne in outputlist: outputlist.remove(ThisOne)
    # Update the time variable from the Python datetime
    pfp_utils.get_nctime_from_datetime(ds)
    ldt = pfp_utils.GetVariable(ds, "time")
    ncVar = ncFile.createVariable("time","d",("time",))
    ncVar[:] = numpy.ma.getdata(ldt["Data"])
    for item in ldt["Attr"]:
        setattr(ncVar, item, ldt["Attr"][item])
    if "time" in outputlist: outputlist.remove("time")
    # now write the latitude and longitude variables
    if "latitude" not in ds.root["Attributes"]: ndims = 1
    if "longitude" not in ds.root["Attributes"]: ndims = 1
    if ndims==3:
        if "latitude" not in outputlist:
            ncVar = ncFile.createVariable("latitude","d",("latitude",))
            ncVar[:] = pfp_utils.convert_anglestring(str(ds.root["Attributes"]["latitude"]))
            setattr(ncVar,'long_name','latitude')
            setattr(ncVar,'standard_name','latitude')
            setattr(ncVar,'units','degree_north')
        if "longitude" not in outputlist:
            ncVar = ncFile.createVariable("longitude","d",("longitude",))
            ncVar[:] = pfp_utils.convert_anglestring(str(ds.root["Attributes"]["longitude"]))
            setattr(ncVar,'long_name','longitude')
            setattr(ncVar,'standard_name','longitude')
            setattr(ncVar,'units','degree_east')
    # now make sure the date and time series are not in outputlist
    datetimelist = ['xlDateTime','Year','Month','Day','Hour','Minute','Second','Hdh','Ddd']
    for ThisOne in datetimelist:
        if ThisOne in outputlist:
            outputlist.remove(ThisOne)
    # write everything else to the netCDF file
    for ThisOne in sorted(outputlist):
        nc_write_var(ncFile,ds,ThisOne,dims)
    # write the coordinate reference system (crs) variable
    if "crs" not in outputlist:
        ncVar = ncFile.createVariable("crs","i",())
        setattr(ncVar,"grid_mapping_name","latitude_longitude")
        setattr(ncVar,"long_name","WGS 1984 datum")
        setattr(ncVar,"longitude_of_prime_meridian","0.0")
        setattr(ncVar,"semi_major_axis","6378137.0")
        setattr(ncVar,"inverse_flattening","298.257223563")
    # write the station_name variable
    site_name = ds.root["Attributes"]["site_name"]
    site_name = site_name.rstrip().lstrip().replace(" ", "")
    ncFile.createDimension("name_strlen", len(site_name))
    ncVar = ncFile.createVariable("station_name", "c", ("name_strlen",))
    ncVar[:] = site_name
    setattr(ncVar, "long_name", "station name")
    setattr(ncVar, "cf_role", "timeseries_id")
    return

def nc_write_var(ncFile, ds, ThisOne, dim):
    """
    Purpose:
     Function to write data from a series in the data structure to a netCDF variable.
    Usage:
     nc_write_var(ncFile,ds,ThisOne,("time","latitude","longitude"))
      where ncFile is a netCDF file object
            ds is the data structure
            ThisOne is the label of a series in ds
            ("time","latitude","longitude") is the dimension tuple
    Author: PRI
    Date: August 2014
    """
    # get the data type of the series in ds
    dt = get_ncdtype(ds.root["Variables"][ThisOne]["Data"])
    # create the netCDF variable
    try:
        ncVar = ncFile.createVariable(ThisOne, dt, dim)
    except RuntimeError:
        msg = "Error writing variable to netCDF file: "+ThisOne
        raise Exception(msg)
    # different writes to the variable depending on whether it is 1D or 3D
    if len(dim) == 1:
        ncVar[:] = ds.root["Variables"][ThisOne]["Data"].tolist()
    elif len(dim) == 3:
        ncVar[:, 0, 0] = ds.root["Variables"][ThisOne]["Data"].tolist()
    else:
        msg = "Unrecognised dimension request for netCDF variable: "+ThisOne
        raise RuntimeError(msg)
    # write the attributes
    vattrs = sorted(list(ds.root["Variables"][ThisOne]["Attr"].keys()))
    for item in vattrs:
        if item not in ["_FillValue", "missing_value", "valid_max", "vaild_min", "valid_range"]:
            attr = str(ds.root["Variables"][ThisOne]["Attr"][item])
            ncVar.setncattr(item, attr)
    # write the valid_range attribute
    if dt == "d":
        if "valid_range" in ds.root["Variables"][ThisOne]["Attr"]:
            try:
                valid_range = [float(l) for l in ds.root["Variables"][ThisOne]["Attr"]["valid_range"].split(",")]
                ncVar.setncattr("valid_range", valid_range)
            except Exception:
                msg = " Unable to write valid_range attribute for " + ThisOne
                msg+= ", skipping ..."
                logger.warning(msg)
    else:
        if "valid_range" in ds.root["Variables"][ThisOne]["Attr"]:
            try:
                valid_range = [int(l) for l in ds.root["Variables"][ThisOne]["Attr"]["valid_range"].split(",")]
                ncVar.setncattr("valid_range", valid_range)
            except Exception:
                msg = " Unable to write valid_range attribute for " + ThisOne
                msg+= ", skipping ..."
                logger.warning(msg)
    # get the data type of the QC flag
    dt = get_ncdtype(ds.root["Variables"][ThisOne]["Flag"])
    # create the variable
    ncVar = ncFile.createVariable(ThisOne+"_QCFlag", dt, dim)
    # write 1D or 3D
    if len(dim)==1:
        ncVar[:] = ds.root["Variables"][ThisOne]["Flag"].tolist()
    elif len(dim)==3:
        ncVar[:, 0, 0] = ds.root["Variables"][ThisOne]["Flag"].tolist()
    else:
        msg = "Unrecognised dimension request for netCDF variable: "+ThisOne
        raise RuntimeError(msg)
    # set the attributes
    ncVar.setncattr("long_name", ThisOne+"QC flag")
    ncVar.setncattr("units", "1")
    return

def xl_open_write(xl_name):
    xl_filename = os.path.basename(xl_name)
    msg = " Opening " + xl_filename + " for writing"
    logger.info(msg)
    try:
        xl_file = xlwt.Workbook()
    except:
        msg = " Unable to open Excel file " + xl_name + " for writing"
        logger.error(msg)
        xl_file = ""
    return xl_file

def xl_check_cf_section(cf, label):
    """
    Purpose:
     Helper logical for checking L1 control file entries.
    Usage:
    Author: PRI
    Date: March 2017
    """
    result = False
    cf_label = cf["Variables"][label]
    if "xl" in list(cf_label.keys()):
        if "xl" in list(cf_label.keys()):
            if "sheet" in list(cf_label["xl"].keys()):
                result = True
            else:
                logger.error("  Key 'sheet' not found in control file entry for "+label)
                result = False
    return result

def xl_write_AlternateStats(ds, l4_info):
    l4a = l4_info["GapFillFromAlternate"]
    file_name = os.path.split(l4a["info"]["xl_file_name"])
    logger.info(' Writing alternate fit statistics to ' + file_name[1])
    # open the Excel file
    xlfile = xlwt.Workbook()
    # list of outputs to write to the Excel file
    date_list = ["startdate", "enddate"]
    # loop over the series that have been gap filled using alternate data
    d_xf = xlwt.easyxf(num_format_str='dd/mm/yyyy hh:mm')
    label_list = sorted(l4a["outputs"].keys())
    for label in label_list:
        # get the list of values to output with the start and end dates removed
        output_list = list(l4a["outputs"][label]["results"].keys())
        for item in date_list:
            if item in output_list: output_list.remove(item)
        # add a sheet with the series label
        xlResultsSheet = xlfile.add_sheet(label)
        xlRow = 9
        xlCol = 0
        for dt in date_list:
            xlResultsSheet.write(xlRow, xlCol, dt)
            for item in l4a["outputs"][label]["results"][dt]:
                xlRow = xlRow + 1
                xlResultsSheet.write(xlRow, xlCol, item, d_xf)
            xlRow = 9
            xlCol = xlCol + 1
        for output in output_list:
            xlResultsSheet.write(xlRow, xlCol, output)
            # convert masked array to ndarray
            output_array = numpy.ma.filled(l4a["outputs"][label]["results"][output], float(c.missing_value))
            for item in output_array:
                xlRow = xlRow + 1
                # xlwt under Anaconda seems to only allow float64!
                xlResultsSheet.write(xlRow, xlCol, numpy.float64(item))
            xlRow = 9
            xlCol = xlCol + 1
    xlfile.save(l4a["info"]["xl_file_name"])

def xl_write_SOLOStats(ds, l5_info):
    if "GapFillUsingSOLO" not in list(l5_info.keys()):
        return
    # local pointer to l5_info outputs
    l5io = l5_info["GapFillUsingSOLO"]["outputs"]
    # get the output file name
    out_filename = get_outfilenamefromcf(l5_info["cfg"])
    # get the Excel file name
    xl_filename = out_filename.replace('.nc', '_SOLOStats.xls')
    xl_name = os.path.split(xl_filename)
    logger.info(' Writing SOLO statistics to ' + xl_name[1])
    # open the Excel file
    xlfile = xlwt.Workbook()
    # list of outputs to write to the Excel file
    date_list = ["startdate", "middate", "enddate"]
    # loop over the series that have been gap filled using ACCESS data
    d_xf = xlwt.easyxf(num_format_str='dd/mm/yyyy hh:mm')
    outputs = list(l5io.keys())
    outputs.sort()
    for output in outputs:
        # get the list of values to output with the start and end dates removed
        stats = list(l5io[output]["results"].keys())
        for item in date_list:
            if item in outputs:
                outputs.remove(item)
        # add a sheet with the series output
        xlResultsSheet = xlfile.add_sheet(output)
        xlRow = 10
        xlCol = 0
        for dt in date_list:
            xlResultsSheet.write(xlRow, xlCol, dt)
            for item in l5io[output]["results"][dt]:
                xlRow = xlRow + 1
                xlResultsSheet.write(xlRow, xlCol, item, d_xf)
            xlRow = 10
            xlCol = xlCol + 1
            # remove startdate and enddate from the list of outputs
            stats.remove(dt)
        for stat in stats:
            xlResultsSheet.write(xlRow, xlCol, stat)
            # convert masked array to ndarray
            output_array = numpy.ma.filled(l5io[output]["results"][stat], float(c.missing_value))
            for item in output_array:
                xlRow = xlRow + 1
                # xlwt under Anaconda seems to only allow float64!
                xlResultsSheet.write(xlRow, xlCol, numpy.float64(item))
            xlRow = 10
            xlCol = xlCol + 1
    xlfile.save(xl_filename)

def xl_write_ISD_timesteps(xl_file_path, data):
    """
    Purpose:
     Writes a dictionary to a worksheet in an Excel workbook.
     This routine has 2 arguments,an Excel worksheet instance and
     a dictionary of data to be written out.  The dictionary
     format needs to be:
      data[site][year]["mean"]
      data[site][year]["stdev"]
      data[site][year]["mode"]
    Usage:
     pfp_io.xl_write_ISD_timesteps(xl_file_path, data)
      where xl_file_path is an Excel workbook file name
            data         is a dictionary as defined above
    Side effects:
     Writes to an Excel worksheet instance.
    Called by:
    Calls:
    Author: PRI
    Date: August 2017
    """
    # get a workbook
    xl_book = xlwt.Workbook()
    # get a list of the sheets to add
    site_list = list(data.keys())
    year_list = list(data[site_list[0]].keys())
    stat_list = list(data[site_list[0]][year_list[0]].keys())
    # loop over the statistics
    for stat in stat_list:
        # add a worksheet for the statistics
        xl_sheet = xl_book.add_sheet(stat)
        # write the header line
        for col, year in enumerate(year_list):
            xl_sheet.write(0,col+1,year)
        # write the data, one row per site, one column per year
        for row, site in enumerate(site_list):
            xl_sheet.write(row+1,0,site)
            for col, year in enumerate(year_list):
                xl_sheet.write(row+1,col+1,data[site][year][stat])
    # save the workbook
    xl_book.save(xl_file_path)

    return

def xl_write_data(xl_sheet, dsg, labels=None, xlCol=0):
    """
    Purpose:
     Writes a dictionary to a worksheet in an Excel workbook.
     This routine has 2 arguments,an Excel worksheet instance and
     a dictionary of data to be written out.  The dictionary
     format needs to be:
      1) data["DateTime"]["Data"]   - a list of Python datetimes, these will
                                      be written tp the first column of the
                                      worksheet
         data["DateTime"]["units"]  - units of the date time eg "Days", "Years"
         data["DateTime"]["format"] - a format string for xlwt.easyxf eg "dd/mm/yyy"
      2) data[variable]["Data"]     - a numpy array of data values
         data[variable]["units"]    - units of the data
         data[variable]["format"]   - an xlwt.easyxf format string eg "0.00" for 2 decimal places
         There can be multiple variables but each must follow the above template.
    Usage:
     pfp_io.xl_write_data(xl_sheet, data)
      where xl_sheet is an Excel worksheet instance
            data     is a dictionary as defined above
    Side effects:
     Writes to an Excel worksheet instance
    Called by:
    Calls:
    Author: PRI
    Date: June 2015
    """
    #xlCol = 0
    # write the data to the xl file
    if labels is None:
        labels = list(dsg["Variables"].keys())
    xl_sheet.write(1, xlCol, dsg["Variables"]["DateTime"]["Attr"]["units"])
    nrows = len(dsg["Variables"]["DateTime"]["Data"])
    d_xf = xlwt.easyxf(num_format_str=dsg["Variables"]["DateTime"]["Attr"]["format"])
    for j in range(nrows):
        xl_sheet.write(j+2, xlCol, dsg["Variables"]["DateTime"]["Data"][j], d_xf)
    if "DateTime" in labels:
        labels.remove("DateTime")
    labels.sort()
    for item in labels:
        xlCol = xlCol + 1
        xl_sheet.write(0, xlCol, dsg["Variables"][item]["Attr"]["units"])
        xl_sheet.write(1, xlCol, item)
        d_xf = xlwt.easyxf(num_format_str=dsg["Variables"][item]["Attr"]["format"])
        if numpy.ma.isMA(dsg["Variables"][item]["Data"]):
            tmp = numpy.ma.filled(dsg["Variables"][item]["Data"],fill_value=c.missing_value)
        else:
            tmp = dsg["Variables"][item]["Data"]
        for j in range(nrows):
            xl_sheet.write(j+2, xlCol, tmp[j], d_xf)
    return

def xl_write_series(ds, xlfullname, outputlist=None):
    if "nc_nrecs" in list(ds.root["Attributes"].keys()):
        nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    else:
        variablelist = list(ds.root["Variables"].keys())
        nRecs = len(ds.root["Variables"][variablelist[0]]["Data"])
    # open the Excel file
    msg = " Opening and writing Excel file " + os.path.basename(xlfullname) + " (xlwt)"
    logger.info(msg)
    xlfile = xlwt.Workbook(encoding="latin-1")
    # set the datemode
    if "xl_datemode" not in ds.root["Attributes"]:
        if platform.system() == "darwin":
            ds.root["Attributes"]["xl_datemode"] = 0
        else:
            ds.root["Attributes"]["xl_datemode"] = 1
    xlfile.dates_1904 = int(ds.root["Attributes"]["xl_datemode"])
    # add sheets to the Excel file
    xlAttrSheet = xlfile.add_sheet("Attr")
    xlDataSheet = xlfile.add_sheet("Data")
    xlFlagSheet = xlfile.add_sheet("Flag")
    # write the global attributes
    msg = " Writing the global attributes to the Excel file"
    logger.info(msg)
    xlcol = 0
    xlrow = 0
    xlAttrSheet.write(xlrow, xlcol, "Global attributes")
    xlrow = xlrow + 1
    globalattrlist = list(ds.root["Attributes"].keys())
    globalattrlist.sort()
    for ThisOne in sorted([x for x in globalattrlist if "Flag" not in x]):
        xlAttrSheet.write(xlrow, xlcol, ThisOne)
        xlAttrSheet.write(xlrow, xlcol+1, str(str(ds.root["Attributes"][ThisOne]).encode("ascii", "ignore")))
        xlrow = xlrow + 1
    for ThisOne in sorted([x for x in globalattrlist if "Flag" in x]):
        xlAttrSheet.write(xlrow, xlcol, ThisOne)
        xlAttrSheet.write(xlrow, xlcol+1, str(str(ds.root["Attributes"][ThisOne]).encode("ascii", "ignore")))
        xlrow = xlrow + 1
    # write the variable attributes
    logger.info(" Writing the variable attributes to the Excel file")
    xlrow = xlrow + 1
    xlAttrSheet.write(xlrow, xlcol, "Variable attributes")
    xlrow = xlrow + 1
    xlcol_varname = 0
    xlcol_attrname = 1
    xlcol_attrvalue = 2
    variablelist = list(ds.root["Variables"].keys())
    if outputlist is None:
        outputlist = variablelist
    else:
        for ThisOne in outputlist:
            if ThisOne not in variablelist:
                logger.warning(" Requested series " + ThisOne + " not found in data structure")
                outputlist.remove(ThisOne)
        if len(outputlist) == 0:
            outputlist = variablelist
    outputlist.sort()
    for ThisOne in ["DateTime", "DateTime_UTC"]:
        if ThisOne in outputlist: outputlist.remove(ThisOne)
    for ThisOne in outputlist:
        xlAttrSheet.write(xlrow, xlcol_varname, ThisOne)
        attributelist = list(ds.root["Variables"][ThisOne]["Attr"].keys())
        attributelist.sort()
        for Attr in attributelist:
            xlAttrSheet.write(xlrow, xlcol_attrname, Attr)
            xlAttrSheet.write(xlrow, xlcol_attrvalue, str(ds.root["Variables"][ThisOne]["Attr"][Attr]))
            xlrow = xlrow + 1
    # write the Excel date/time to the data and the QC flags as the first column
    if "xlDateTime" not in ds.root["Variables"]:
        pfp_utils.get_xldatefromdatetime(ds)
    xlDateTime = pfp_utils.GetVariable(ds, "xlDateTime", out_type="-9999")
    logger.info(" Writing the datetime to the Excel file")
    d_xf = xlwt.easyxf(num_format_str="dd/mm/yyyy hh:mm")
    xlDataSheet.write(2, xlcol, "xlDateTime")
    for j in range(nRecs):
        xlDataSheet.write(j+3, xlcol, xlDateTime["Data"][j], d_xf)
        xlFlagSheet.write(j+3, xlcol, xlDateTime["Data"][j], d_xf)
    # remove xlDateTime from the list of variables to be written to the Excel file
    if "xlDateTime" in outputlist:
        outputlist.remove("xlDateTime")
    # now start looping over the other variables in the xl file
    xlcol = xlcol + 1
    # loop over variables to be output to xl file
    for ThisOne in outputlist:
        # put up a progress message
        msg = " Writing " + ThisOne + " into column " + str(xlcol) + " of the Excel file"
        logger.info(msg)
        # write the units and the variable name to the header rows in the xl file
        attrlist = list(ds.root["Variables"][ThisOne]["Attr"].keys())
        if "long_name" in attrlist:
            longname = ds.root["Variables"][ThisOne]["Attr"]["long_name"]
        elif "Description" in attrlist:
            longname = ds.root["Variables"][ThisOne]["Attr"]["Description"]
        else:
            longname = None
        if "units" in attrlist:
            units = ds.root["Variables"][ThisOne]["Attr"]["units"]
        elif "Units" in attrlist:
            units = ds.root["Variables"][ThisOne]["Attr"]["Units"]
        else:
            units = None
        xlDataSheet.write(0, xlcol, longname)
        xlDataSheet.write(1, xlcol, units)
        xlDataSheet.write(2, xlcol, ThisOne)
        # loop over the values in the variable series (array writes don't seem to work)
        for j in range(nRecs):
            xlDataSheet.write(j+3, xlcol, float(ds.root["Variables"][ThisOne]["Data"][j]))
        # check to see if this variable has a quality control flag
        if "Flag" in list(ds.root["Variables"][ThisOne].keys()):
            # write the QC flag name to the xls file
            xlFlagSheet.write(2, xlcol, ThisOne)
            # specify the format of the QC flag (integer)
            d_xf = xlwt.easyxf(num_format_str="0")
            # loop over QC flag values and write to xls file
            for j in range(nRecs):
                xlFlagSheet.write(j+3, xlcol, int(ds.root["Variables"][ThisOne]['Flag'][j]), d_xf)
        # increment the column pointer
        xlcol = xlcol + 1
    xlfile.save(xlfullname)

def xlsx_write_series(ds, xlsxfullname, outputlist=None):
    if "nc_nrecs" in list(ds.root["Attributes"].keys()):
        nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    else:
        variablelist = list(ds.root["Variables"].keys())
        nRecs = len(ds.root["Variables"][variablelist[0]]["Data"])
    # open the Excel file
    msg = " Opening and writing Excel file " + os.path.basename(xlsxfullname) + " (xlsxwriter)"
    logger.info(msg)
    if "xl_datemode" not in ds.root["Attributes"]:
        if platform.system() == "darwin":
            ds.root["Attributes"]["xl_datemode"] = 0
        else:
            ds.root["Attributes"]["xl_datemode"] = 1
    if int(ds.root["Attributes"]["xl_datemode"]) == 1:
        xlfile = xlsxwriter.Workbook(xlsxfullname, {"date_1904": True, "nan_inf_to_errors": True})
    else:
        xlfile = xlsxwriter.Workbook(xlsxfullname, {"date_1904": False, "nan_inf_to_errors": True})
    # add sheets to the Excel file
    xlAttrSheet = xlfile.add_worksheet("Attr")
    xlDataSheet = xlfile.add_worksheet("Data")
    xlFlagSheet = xlfile.add_worksheet("Flag")
    # write the global attributes
    logger.info(" Writing the global attributes to the Excel file")
    xlcol = 0
    xlrow = 0
    xlAttrSheet.write(xlrow, xlcol, "Global attributes")
    xlrow = xlrow + 1
    globalattrlist = list(ds.root["Attributes"].keys())
    globalattrlist.sort()
    for ThisOne in sorted([x for x in globalattrlist if "Flag" not in x]):
        xlAttrSheet.write(xlrow, xlcol, ThisOne)
        xlAttrSheet.write(xlrow, xlcol+1, str(ds.root["Attributes"][ThisOne]))
        xlrow = xlrow + 1
    for ThisOne in sorted([x for x in globalattrlist if "Flag" in x]):
        xlAttrSheet.write(xlrow, xlcol, ThisOne)
        xlAttrSheet.write(xlrow, xlcol+1, str(ds.root["Attributes"][ThisOne]))
        xlrow = xlrow + 1
    # write the variable attributes
    logger.info(" Writing the variable attributes to the Excel file")
    xlrow = xlrow + 1
    xlAttrSheet.write(xlrow, xlcol, "Variable attributes")
    xlrow = xlrow + 1
    xlcol_varname = 0
    xlcol_attrname = 1
    xlcol_attrvalue = 2
    variablelist = list(ds.root["Variables"].keys())
    if outputlist is None:
        outputlist = variablelist
    else:
        for ThisOne in outputlist:
            if ThisOne not in variablelist:
                logger.warning(" Requested series " + ThisOne + " not found in data structure")
                outputlist.remove(ThisOne)
        if len(outputlist) == 0:
            outputlist = variablelist
    outputlist.sort()
    for ThisOne in ["DateTime", "DateTime_UTC"]:
        if ThisOne in outputlist: outputlist.remove(ThisOne)
    for ThisOne in outputlist:
        xlAttrSheet.write(xlrow, xlcol_varname, ThisOne)
        attributelist = list(ds.root["Variables"][ThisOne]["Attr"].keys())
        attributelist.sort()
        for Attr in attributelist:
            xlAttrSheet.write(xlrow, xlcol_attrname, Attr)
            xlAttrSheet.write(xlrow, xlcol_attrvalue, str(ds.root["Variables"][ThisOne]["Attr"][Attr]))
            xlrow = xlrow + 1
    # write the Excel date/time to the data and the QC flags as the first column
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    logger.info(" Writing the datetime to the Excel file")
    dt_format = xlfile.add_format({"num_format": "dd/mm/yyyy hh:mm"})
    xlDataSheet.write(2, xlcol, "xlDateTime")
    xlFlagSheet.write(2, xlcol, "xlDateTime")
    for j in range(nRecs):
        xlDataSheet.write_datetime(j+3, xlcol, ldt[j], dt_format)
        xlFlagSheet.write_datetime(j+3, xlcol, ldt[j], dt_format)
    # remove xlDateTime from the list of variables to be written to the Excel file
    if "xlDateTime" in outputlist: outputlist.remove("xlDateTime")
    # now start looping over the other variables in the xl file
    xlcol = xlcol + 1
    # loop over variables to be output to xl file
    for ThisOne in outputlist:
        # put up a progress message
        logger.info(" Writing " + ThisOne + " into column " + str(xlcol) + " of the Excel file")
        # write the units and the variable name to the header rows in the xl file
        attrlist = list(ds.root["Variables"][ThisOne]["Attr"].keys())
        if "long_name" in attrlist:
            longname = ds.root["Variables"][ThisOne]["Attr"]["long_name"]
        elif "Description" in attrlist:
            longname = ds.root["Variables"][ThisOne]["Attr"]["Description"]
        else:
            longname = None
        if "units" in attrlist:
            units = ds.root["Variables"][ThisOne]["Attr"]["units"]
        elif "Units" in attrlist:
            units = ds.root["Variables"][ThisOne]["Attr"]["Units"]
        else:
            units = None
        xlDataSheet.write(0, xlcol, longname)
        xlDataSheet.write(1, xlcol, units)
        xlDataSheet.write(2, xlcol, ThisOne)
        # loop over the values in the variable series (array writes don't seem to work)
        for j in range(nRecs):
            xlDataSheet.write(j+3, xlcol, float(ds.root["Variables"][ThisOne]["Data"][j]))
        # check to see if this variable has a quality control flag
        if "Flag" in list(ds.root["Variables"][ThisOne].keys()):
            # write the QC flag name to the Excel file
            xlFlagSheet.write(2, xlcol, ThisOne)
            # specify the format of the QC flag (integer)
            flag_format = xlfile.add_format({"num_format": "0"})
            # loop over QC flag values and write to xl file
            for j in range(nRecs):
                xlFlagSheet.write(j+3, xlcol, int(ds.root["Variables"][ThisOne]["Flag"][j]), flag_format)
        # increment the column pointer
        xlcol = xlcol + 1

    xlfile.close()
