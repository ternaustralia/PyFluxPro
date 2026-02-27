# the following line needed for unicode character in convert_anglestring
# -*- coding: latin-1 -*-
import ast
import constants as c
import copy
import datetime
import dateutil
import logging
import math
import meteorologicalfunctions as mf
import netCDF4
import numbers
import numpy
import pandas
import os
import platform
import pytz
import sys
import time
import tkinter,tkinter.simpledialog
import xlrd
import xlwt

logger = logging.getLogger("footprint_log")

def GetDateIndex(ldt,date,ts=30,default=0,match='exact'):
    """
    Purpose:
     Return the index of a date/datetime string in an array of datetime objects
    Usage:
     si = footprint_utils.GetDateIndex(ldt,date_str,ts=30,default=0,match='exact')
    where
     ldt      - array of datetime objects
     date_str - a date or date/time string in a format dateutils can parse
     ts       - time step for the data, optional (integer)
     default  - default value, optional (integer)
     match    - type of match (string) options are:
                "exact"            - finds the specified datetime and returns
                                     the index
                "startnextday"     - returns the index of the first time period
                                     in the next day
                "endpreviousday"   - returns the index of the last time period
                                     in the previous day
                "startnexthour"    - returns the index of the first time period
                                     in the next hour
                "endprevioushour"  - returns the index of the last time period
                                     in the previous hour
                "startnextmonth"   - returns the index of the first time period
                                     in the next month
                "endpreviousmonth" - returns the index of the last time period
                                     in the previous month
                NOTE: "startnextday" and "endpreviousday" can be used to pick
                    out time periods with an integer number of days
    Author: PRI
    Date: Back in the day
    """
    # trap default values of -1 since -1 + 1 = 0
    if default == -1:
        default = len(ldt)-1
    # is the input date a string?
    if isinstance(date, str):
        # if so, is it an empty string?
        if len(date) != 0:
            # if not empty, see if we can parse it
            try:
                date = dateutil.parser.parse(date)
                if (date>=ldt[0]) and (date<=ldt[-1]):
                    # date string parsed OK, is it within the datetime range of the data?
                    i = find_nearest_value(ldt, date)
                else:
                    # set to default if not within the datetime range of the data
                    i = default
            except:
                # set to default if parsing date string failed
                i = default
        else:
            # set to default if date string empty
            i = default
    elif isinstance(date, datetime.datetime):
        # the input date was a datetime object
        # check it is within the datetime range of the data
        if (date>=ldt[0]) and (date<=ldt[-1]):
            i = find_nearest_value(ldt, date)
        else:
            # set to default if not within the datetime range of the data
            i = default
    else:
        msg = " Unrecognised object passed in as date, returning default index"
        logger.warning(msg)
        i = default
    if match=="exact":
        # if an exact match is required, do nothing
        pass
    elif match=="startnextmonth":
        # get to the start of the next day
        while abs(ldt[i].hour+float(ldt[i].minute)/60-float(ts)/60)>c.eps:
            i = i + 1
        while ldt[i].day!=1:
            i = i + int(float(24)/(float(ts)/60))
    elif match=='startnextday':
        while abs(ldt[i].hour+float(ldt[i].minute)/60-float(ts)/60)>c.eps:
            i = i + 1
    elif match=="startnexthour":
        # check the time step value
        if int(ts)!=60:
            # if the time step is 60 then it is always the start of the next hour
            # we assume here that the time period ends on the datetime stamp
            while ldt[i].minute!=ts:
                # iterate until the minutes equal the time step
                i = i + 1
    elif match=='endpreviousmonth':
        while abs(ldt[i].hour+float(ldt[i].minute)/60)>c.eps:
            i = i - 1
        while ldt[i].day!=1:
            i = i - int(float(24)/(float(ts)/60))
    elif match=='endpreviousday':
        while abs(ldt[i].hour+float(ldt[i].minute)/60)>c.eps:
            i = i - 1
    elif match=="endprevioushour":
        # check the time step value
        if int(ts)!=60:
            # if the time step is 60 then it is always the end of the previous hour
            # we assume here that the time period ends on the datetime stamp
            while ldt[i].minute!=0:
                # iterate until the minutes equal 0
                i = i - 1
    else:
        logger.error("GetDateIndex: Unrecognised match option")
    return i

def GetSeriesasMA(ds,ThisOne,si=0,ei=-1,mode="truncate"):
    """
    Purpose:
     Returns a data series and the QC flag series from the data structure.
    Usage:
     data,flag,attr = footprint_utils.GetSeriesasMA(ds,label,si=0,ei=-1)
    where the arguments are;
      ds    - the data structure (dict)
      label - label of the data series in ds (string)
      si    - start index (integer), default 0
      ei    - end index (integer), default -1
    and the returned values are;
      data - values for the requested series in ds
             (numpy masked array, float64)
      flag - QC flag for the requested series in ds
             (numpy masked array, int32)
      attr - attribute dictionary for series
    Example:
     The code snippet below will return the incoming shortwave data values
     (Fsd) and the associated QC flag (f) as numpy masked arrays;
      ds = footprint_io.nc_read_series("HowardSprings_2011_L3.nc")
      Fsd,f,a = footprint_utils.GetSeriesasMA(ds,"Fsd")
    Author: PRI
    """
    Series,Flag,Attr = GetSeries(ds,ThisOne,si=si,ei=ei,mode=mode)
    Series,WasND = SeriestoMA(Series)
    return Series,Flag,Attr

def update_progress(progress):
    barLength = 50 # Modify this to change the length of the progress bar
    status = ""
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
        status = "error: progress var must be float\r\n"
    if progress < 0:
        progress = 0
        status = "Halt...\r\n"
    if progress >= 1:
        progress = 1
        status = "Done...\r\n"
    block = int(round(barLength*progress))
    progress = round(progress,2)
    text = "\rPercent: [{0}] {1}% {2}".format( "#"*block + "-"*(barLength-block), progress*100, status)
    sys.stdout.write(text)
    sys.stdout.flush()

def CalculateMoninObukhovLength(ds, fpinfo):
    """
    Purpose:
     Calculate the Monin Obukhov length.
    Usage:
     CalculateMoninObukhovLength(ds, fpinfo)
     where ds is a data structure
    Side effects:
     Creates a new series in the data structure containing the Monin-Obukhov length.
    Author: PRI
    Date: April 2018
    """
    logger.info(' Calculating Monin-Obukhov length')
    # create a variable dictionary for L
    nrecs = int(ds.globalattributes["nc_nrecs"])
    ldt = GetVariable(ds, "DateTime")
    L = create_empty_variable("L", nrecs, datetime=ldt["Data"])
    # create QC flags
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    ones = numpy.ones(nrecs, dtype=numpy.int32)
    # get the required meteorological variables
    Ta = GetVariable(ds, "Ta")
    ps = GetVariable(ds, "ps")
    vp = create_empty_variable("vp", nrecs, datetime=ldt["Data"])
    AH = GetVariable(ds, "AH")
    vp["Data"] = mf.vapourpressure(AH["Data"],Ta["Data"])
    # get the required fluxes
    ustar = GetVariable(ds, "ustar")
    Fh    = GetVariable(ds, "Fh")
    # calculate the density of dry air
    rho_dry = mf.densitydryair(Ta["Data"], ps["Data"], vp["Data"])
    # calculate virtual potential temperature
    Tp = mf.theta(Ta["Data"], ps["Data"])
    mr = mf.mixingratio(ps["Data"], vp["Data"])
    Tvp = mf.virtualtheta(Tp, mr)
    L["Data"] = -Tvp*rho_dry*c.Cp*(ustar["Data"]**3)/(c.g*c.k*Fh["Data"])
    # get the QC flag
    L["Flag"] = numpy.where(numpy.ma.getmaskarray(L["Data"]) == True, ones, zeros)
    # update the variable attributes
    L["Attr"]["units"] = "m"
    L["Attr"]["long_name"] = "Monin-Obukhov length"
    L["Attr"]["standard_name"] = "not defined"
    # put the Monin-Obukhov variable in the data structure
    CreateVariable(ds, L)
    return

def z0calc(zm,LM,U_meas,UStar):
    # aerodynamic roughness length
    # Psi functions according to Dyer (1974)
    # a) create positive and negative LM masks
    LMp = numpy.ma.masked_where(LM <  float(0),LM)
    LMn = numpy.ma.masked_where(LM >= float(0),LM)
    # Calculate z0 assuming logarithmic wind profile
    #          === functions are from Kormann and Meixner (2001) (Eqs. 31 to 35)
    #b) for stable conditions, linear
    FIp = 5.0 * zm/LMp
    # c) for unstable conditions
    zeta = (1.0-16.0*zm/LMn)**(0.25)
    FIn = -2.0*numpy.log(0.5*(1.0+zeta))-numpy.log(0.5*(1.0+zeta*zeta))+2.0*numpy.arctan(zeta)-0.5*c.Pi
    # d) put both parts together again
    #FI = numpy.ma.mask_or(FIp,FIn)
    # d1) fill positive and negative Fn masks
    FIp = numpy.ma.filled(FIp,float(0))
    FIn = numpy.ma.filled(FIn,float(0))
    FI  = FIp+FIn
    # e) determine
    alpha = U_meas * 0.4 / UStar - FI
    # f) finally calculate the roughness length
    ZNull = zm / numpy.exp(alpha)
    #!#            === functions derived from Leclerc and Foken 2015 book, page 61 after Hogstroem, 1988
    #!# b) for stable conditions, linear
    #!FIp = -6.0 * zm/LMp
    #!# c) for unstable conditions
    #!zeta = (1.0+19.3*zm/LMn)**0.25
    #!temp = 0.125*(1.0+zeta*zeta)*(1.0+zeta)*(1.0+zeta)
    #!FIn = numpy.log(temp)-2.0*numpy.arctan(zeta)+0.5*c.Pi
    #!# d) put both parts together again
    #!#FI = numpy.ma.mask_or(FIp,FIn,copy=True)
    #!# d1) fill positive and negative Fn masks
    #!FIp = numpy.ma.filled(FIp,float(0))
    #!FIn = numpy.ma.filled(FIn,float(0))
    #!FI  = FIp+FIn
    #!# e) determine
    #!alpha = U_meas * 0.4 / UStar + FI
    #!# f) finally calculate the roughness length
    #!ZNull = zm / numpy.exp(alpha)
    #!#            ===
    #set a lower limit for z0 to avoid numeric problems
    ZNull = numpy.ma.masked_where(ZNull<0.0001,ZNull)
    ZNull = numpy.ma.filled(ZNull,0.0001)
    return ZNull

#def BLH(ol, ustar, dt, lat, zm):
def BLH(ol, ustar, lat, zm):
    # --- if no boundary layer height available use Kljun et al., 2015 analytical solution for Habl
    #   blh for stable and neutral conditions - Nieuwstadt (1981)
    #            h = (L/3.8)*(-1 + (1 + 2.28*(ustar/(f*L)))^0.5)                          (Eq.1.1)
    #              with L = MOL, ustar - friction velocity, g = acceleration due to gravity and
    #                   f = 2 omega sin (phi) = Coriolis parameter
    #   blh for convective conditions (needs to be integrated due to near symmetric diurnal cycle
    #            of surface heat flux). The resulting rate of change for the boundary layer height
    #            is implicit in h and may be solved iteratively or using h(t_i) to determine the rate
    #            of change to yield h(t_i+1)
    #            at sunrise before Fh becomes positive - use Eq.1.1 for initial conditions
    #               then dh/dt = bar(w'Theta')_0 / gamma*[(h^2 / ((1+2*A)*h - 2*B*k*L))   (Eq.1.2)
    #                           + ((C * ustar^2 * T) / (gamma*g*[(1+A)*h - B*k*L]))]^(-1)
    #            gamma = gradient of potential temp above convective bl; ~0.01 K/m for typical midlatitude
    #                      (dh/dt quite sensitive to gamma)
    #            A = 0.2; B + 2.5; C = 8 (derived from similarity relations in cbl)
    #   so make sure H is availble from external sources, you really don't want to calculate it
    #A = 0.2
    #B = 2.5
    #C = 8
    #gamma = 0.01          # K/m
    omega = 0.000072921   # rad/s
    f = 2.0 * omega * numpy.sin(lat * numpy.pi / 180.)
    if ol > 0:    # stable
        Habl = (ol/3.8)*(-1 + 2.28*(ustar/(f*ol)))**0.5
    elif ol <= 0: # convective
        # here we need to model the data day by day
        Habl = (ol/3.8)*(-1 + 2.28*(ustar/(f*ol)))**0.5
    elif float(zm)/ol <= -15.5:
        # not valid in Kljun et al., 2015
        Habl = -9999
    return Habl

def create_index_list(cf, fpinfo, date):
    """
    Create a list of indices of the datetime for the requested climatology
    Single  = only one element for Start and End, here range is index , index+1
            difficulty, the time for this single element is actually the timestep
            from previous to the named in the list (timestamp at end of interval
    Special = only one element for Start and End
    Hourly  = every timestep
    Daily   = get a climatology for each day, forget about the couple of hours
            before and after the first day, use
            GetDateIndex(ldt,date_str,ts=30,default=0,match='startnextday')
            GetDateIndex(ldt,date_str,ts=30,default=0,match='endpreviousday')
    Monthly =
    Annual  =
    """
    # Initialise List start and end dates
    list_StDate = []
    list_EnDate = []
    #import datetime
    climfreq = fpinfo["Climatology"]
    logger.info(f"Assessing start and end date of file as {climfreq} climatology")
    # firstly what climatology is requested
    if climfreq == 'Single':
        #list_StDate = []
        #list_EnDate = []
        if 'StartDate' in list(cf['Options'].keys()):
            xlStDate = cf['Options']['StartDate']
            list_StDate.append(GetDateIndex(date,xlStDate,ts=fpinfo["flux_period"],default=0,match='exact'))
        else:
            logger.error("No StartDate given. Define which time for footprint calculation in StartDate (DD/MM/YYYY hh:mm)")

        list_EnDate.append(list_StDate[0]+1)

    elif climfreq == 'Special':
        #list_StDate = []
        #list_EnDate = []
        if 'StartDate' in list(cf['Options'].keys()):
            xlStDate = cf['Options']['StartDate']
            print(xlStDate)
            list_StDate.append(GetDateIndex(date,xlStDate,ts=fpinfo["flux_period"],default=0,match='exact'))
        else:
            list_StDate.append(0)         # start from begin of file
        if 'EndDate' in list(cf['Options'].keys()):
            xlEnDate = cf['Options']['EndDate']
            list_EnDate.append(GetDateIndex(date,xlEnDate,ts=fpinfo["flux_period"],default=0,match='exact'))
        else:
            list_EnDate.append(len(date)-1) # run to end of file

    elif climfreq == 'Hourly':
        # if file is half hourly every single data is used
        if 'StartDate' in list(cf['Options'].keys()):
            xlStDate = cf['Options']['StartDate']
            firstIdx = GetDateIndex(date,xlStDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            firstIdx = 0         # start from begin of file
        if 'EndDate' in list(cf['Options'].keys()):
            xlEnDate = cf['Options']['EndDate']
            lastIdx = GetDateIndex(date,xlEnDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            lastIdx = len(date)-2 # run to end of file
        list_StDate = list(range(firstIdx,lastIdx))
        list_EnDate = list(range(firstIdx+1,lastIdx+1))
        #print('Start to End = ',list_StDate, list_EnDate)

    elif climfreq == 'Daily':
        if 'StartDate' in list(cf['Options'].keys()):
            xlStDate = cf['Options']['StartDate']
            firstIdx = GetDateIndex(date,xlStDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            firstIdx = 0         # start from begin of file
        if 'EndDate' in list(cf['Options'].keys()):
            xlEnDate = cf['Options']['EndDate']
            lastIdx = GetDateIndex(date,xlEnDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            lastIdx = len(date)-2 # run to end of file
        StDate = date[firstIdx]
        EnDate = date[lastIdx]
        sd = pandas.date_range(start=str(StDate), end=str(EnDate), freq='D', normalize=True)    # frequency daily
        ndays     = len(sd)
        #list_StDate = []
        #list_EnDate = []
        list_StDate.append(GetDateIndex(date,sd[0],ts=fpinfo["flux_period"],default=0,match='exact'))
        list_EnDate.append(GetDateIndex(date,sd[1],ts=fpinfo["flux_period"],default=-1,match='exact'))
        for i in range(1,ndays-1):
            list_StDate.append(GetDateIndex(date,sd[i],ts=fpinfo["flux_period"],default=0,match='exact') +1)
            list_EnDate.append(GetDateIndex(date,sd[i+1],ts=fpinfo["flux_period"],default=-1,match='exact'))
        test_i = GetDateIndex(date,sd[-1],ts=fpinfo["flux_period"],default=0,match='exact')
        if test_i < len(date)-2: # at least one value for the next day, so only midnight not allowed
            list_StDate.append(test_i+1)
            list_EnDate.append(len(date)-1)

    elif climfreq == 'Monthly':
        if 'StartDate' in list(cf['Options'].keys()):
            xlStDate = cf['Options']['StartDate']
            firstIdx = GetDateIndex(date,xlStDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            firstIdx = 0         # start from begin of file
        if 'EndDate' in list(cf['Options'].keys()):
            xlEnDate = cf['Options']['EndDate']
            lastIdx = GetDateIndex(date,xlEnDate,ts=fpinfo["flux_period"],default=0,match='exact')
        else:
            lastIdx = len(date)-2 # run to end of file
        StDate = date[firstIdx]
        EnDate = date[lastIdx]
        sm = pandas.date_range(start=str(StDate), end=str(EnDate), freq='MS', normalize=True)    # frequency monthly
        num_int = len(sm)
        #list_StDate = []
        #list_EnDate = []
        test_i = GetDateIndex(date,sm[0],ts=fpinfo["flux_period"],default=0,match='exact')
        if test_i > 0:
            list_StDate.append(0)
            list_EnDate.append(test_i)
            list_StDate.append(GetDateIndex(date,sm[0],ts=fpinfo["flux_period"],default=0,match='exact')+1)
            list_EnDate.append(GetDateIndex(date,sm[1],ts=fpinfo["flux_period"],default=-1,match='exact'))
        else:
            list_StDate.append(GetDateIndex(date,sm[0],ts=fpinfo["flux_period"],default=0,match='exact'))
            list_EnDate.append(GetDateIndex(date,sm[1],ts=fpinfo["flux_period"],default=-1,match='exact'))
        for i in range(1,num_int-1):
            list_StDate.append(GetDateIndex(date,sm[i],ts=fpinfo["flux_period"],default=0,match='exact')+1)
            list_EnDate.append(GetDateIndex(date,sm[i+1],ts=fpinfo["flux_period"],default=-1,match='exact'))
        test_i = GetDateIndex(date,sm[-1],ts=fpinfo["flux_period"],default=0,match='exact')
        if test_i < len(date)-2: # at least one value for the next day, so only midnight not allowed
            list_StDate.append(test_i+1)
            list_EnDate.append(len(date)-1)

    elif climfreq == 'Annual':
        # Find number of years in df
        StDate = date[0]
        EnDate = date[-1]
        logger.info(f'Start date is {str(StDate)} and End date is {str(EnDate)}')
        years_index = []
        #date.apply(lambda x: x.year)
        #for i in range(min(year),max(year)+1):
        for i in range(StDate.year,EnDate.year+1):
            years_index.append(i)
        num = len(years_index)
        years_index.append(max(years_index)+1)
        logger.info(f"{num} years found in netcdf file")

        #list_StDate = []
        #list_EnDate = []
        st = datetime.datetime(years_index[0],1,1,0,0)
        en = datetime.datetime(years_index[1],1,1,0,0)
        list_StDate.append(GetDateIndex(date,st,ts=fpinfo["flux_period"],default=0,match='exact'))
        list_EnDate.append(GetDateIndex(date,en,ts=fpinfo["flux_period"],default=-1,match='exact'))
        if num > 1:
            if num > 2:
                for i in range(1,num-1):
                    st = datetime.datetime(years_index[i],1,1,0,0)
                    en = datetime.datetime(years_index[i+1],1,1,0,0)
                    list_StDate.append(GetDateIndex(date,st,ts=fpinfo["flux_period"],default=0,match='exact')+1)
                    list_EnDate.append(GetDateIndex(date,en,ts=fpinfo["flux_period"],default=-1,match='exact'))
            st = datetime.datetime(years_index[num-1],1,1,0,0)
            en = datetime.datetime(years_index[num],1,1,0,0)
            test_is = GetDateIndex(date,st,ts=fpinfo["flux_period"],default=-1,match='exact')
            test_ie = GetDateIndex(date,en,ts=fpinfo["flux_period"],default=-1,match='exact')
            if test_ie - test_is > 2:
                list_StDate.append(test_is+1)
                list_EnDate.append(test_ie)
        logger.info(list_StDate)
        logger.info(list_EnDate)
    return list_StDate,list_EnDate

def get_keyvaluefromcf(cf,sections,key,default=None,mode="quiet"):
    """
    Purpose:
     General return a keyword value from a control file.
    Usage:
     keyval = footprint_utils.get_keyvaluefromcf(cf,sections,key,default=default)
     where
      cf is a control file object from ConfigObj
      sections is a list of sections and nested sub-sections to search
      key is the keyword
      default is a default value
    Example:
     ncOutFileName = footprint_utils.get_keyvaluefromcf(cf,["Files","Out"],"ncFileName",default="")
     The example above will return the value for ncFileName from the ["Files"]["Out"] sub-section
     in the control file.
    Author: PRI
    Date: February 2015
    """
    if len(sections)<1:
        msg = " get_keyvaluefromsections: no sections specified"
        if mode.lower()!="quiet": logger.info(msg)
    if sections[0] in cf:
        section = cf[sections[0]]
        if len(sections)>1:
            for item in sections[1:]:
                if item in section:
                    section = section[item]
                else:
                    msg = " get_keyvaluefromcf: Sub section "+item+" not found in control file, used default ("+str(default)+")"
                    if mode.lower()!="quiet": logger.info(msg)
                    value = default
        if key in section:
            value = section[key]
        else:
            msg = " get_keyvaluefromcf: Key "+key+" not found in section, used default ("+str(default)+")"
            if mode.lower()!="quiet": logger.info(msg)
            value = default
    else:
        msg = " get_keyvaluefromcf: Section "+sections[0]+" not found in control file, used default ("+str(default)+")"
        if mode.lower()!="quiet": logger.error(msg)
        value = default
    return value

def create_empty_variable(label, nrecs, datetime=[]):
    """
    Purpose:
     Returns an empty variable.  Data values are set to -9999, flag values are set to 1
     and default values for the attributes.
    Usage:
     variable = footprint_utils.create_empty_variable(label, nrecs)
     where label is the variable label
           nrecs is the number of elements in the variable data
    Author: PRI
    Date: December 2016
    """
    data = numpy.ones(nrecs, dtype=numpy.float64)*float(c.missing_value)
    flag = numpy.ones(nrecs, dtype=numpy.int32)
    attr = make_attribute_dictionary()
    variable = {"Label":label, "Data":data, "Flag":flag, "Attr":attr}
    if len(datetime) == nrecs:
        variable["DateTime"] = datetime
    return variable

def CreateVariable(ds,variable):
    """
    Purpose:
     Create a variable in the data structure.
     If the variable already exists in the data structure, data values, QC flags and
     attributes will be overwritten.
     This utility is the prefered method for creating or updating a data series because
     it implements a consistent method for creating series in the data structure.  Direct
     writes to the contents of the data structure are discouraged (unless PRI wrote the code:=P).
    Usage:
     Fsd = footprint_utils.GetVariable(ds,"Fsd")
      ... do something to Fsd here ...
      ... and don't forget to update the QC flag ...
      ... and the attributes ...
     footprint_utils.CreateVariable(ds,Fsd)
    Author: PRI
    Date: September 2016
    """
    label = variable["Label"]
    # create a temporary series to avoid premature overwrites
    ds.series["_tmp_"] = {}
    # put the data into the temporary series
    if numpy.ma.isMA(variable["Data"]):
        ds.series["_tmp_"]["Data"] = numpy.ma.filled(variable["Data"],
                                                     float(c.missing_value))
    else:
        ds.series["_tmp_"]["Data"] = numpy.array(variable["Data"])
    # copy or make the QC flag
    ds.series["_tmp_"]["Flag"] = numpy.array(variable["Flag"])
    # do the attributes
    ds.series["_tmp_"]["Attr"] = copy.deepcopy(variable["Attr"])
    # and copy the temporary series back to the original label
    ds.series[str(label)] = copy.deepcopy(ds.series['_tmp_'])
    # delete the temporary series
    del ds.series['_tmp_']

def GetVariable(ds, label, start=0, end=-1, mode="truncate", out_type="ma"):
    """
    Purpose:
     Returns a data variable from the data structure as a dictionary.
    Usage:
     data,flag,attr = footprint_utils.GetSeriesasMA(ds,label,si=0,ei=-1)
    where the arguments are;
      ds    - the data structure (dict)
      label - label of the data variable in ds (string)
      start - start date or index (integer), default 0
      end   - end date or index (integer), default -1
    and the returned values are;
     The data are returned as a dictionary;
      variable["label"] - variable label in data structure
      variable["data"] - numpy float64 masked array containing data
      variable["flag"] - numpy int32 array containing QC flags
      variable["attr"] - dictionary of variable attributes
    Example:
     The code snippet below will return the incoming shortwave data values
     (Fsd), the associated QC flag and the variable attributes;
      ds = footprint_io.nc_read_series("HowardSprings_2011_L3.nc")
      Fsd = footprint_utils.GetSeriesAsDict(ds,"Fsd")
    Author: PRI
    """
    nrecs = int(ds.globalattributes["nc_nrecs"])
    if end == -1:
        end = nrecs
    ts = int(ds.globalattributes["time_step"])
    ldt = ds.series["DateTime"]["Data"]
    si = get_start_index(ldt, start)
    ei = get_end_index(ldt, end)
    data,flag,attr = GetSeries(ds, label, si=si, ei=ei, mode=mode)
    if isinstance(data, numpy.ndarray):
        data, WasND = SeriestoMA(data)
    variable = {"Label":label,"Data":data,"Flag":flag,"Attr":attr,
                "DateTime":ldt[si:ei+1],"time_step":ts}
    return variable

def SeriestoMA(Series):
    """
    Convert a numpy ndarray to a masked array.
    Useage:
     Series, WasND = SeriestoMA(Series)
     where:
      Series (input)    is the data series to be converted.
      WasND  (returned) is a logical, True if the input series was an ndarray
      Series (output)   is the input series convered to a masked array.
    """
    WasND = False
    if Series.dtype == "float64":
        if not numpy.ma.isMA(Series):
            WasND = True
            Series = numpy.ma.masked_where(abs(Series-numpy.float64(c.missing_value)) < c.eps, Series)
    return Series, WasND

def MAtoSeries(Series):
    """
    Convert a masked array to a numpy ndarray with masked elements set to c.missing_value.
    Useage:
     Series, WasMA = MAtoSeries(Series)
     where:
      Series (input)    is the data series to be converted.
      WasMA  (returned) is a logical, True if the input series was a masked array.
      Series (output)   is the input series convered to an ndarray with c.missing_value values
                        for missing data.
    """
    WasMA = False
    if numpy.ma.isMA(Series):
        WasMA = True
        Series = numpy.ma.filled(Series,float(c.missing_value))
    return Series, WasMA

def file_exists(filename,mode="verbose"):
    if not os.path.exists(filename):
        if mode=="verbose":
            logger.error(' File '+filename+' not found')
        return False
    else:
        return True

def MakeEmptySeries(ds,ThisOne):
    nRecs = int(ds.globalattributes['nc_nrecs'])
    Series = float(c.missing_value)*numpy.ones(nRecs,dtype=numpy.float64)
    Flag = numpy.ones(nRecs,dtype=numpy.int32)
    Attr = MakeAttributeDictionary()
    return Series,Flag,Attr

def GetSeries(ds,ThisOne,si=0,ei=-1,mode="truncate"):
    """ Returns the data, QC flag and attributes of a series from the data structure."""
    # number of records
    if "nc_nrecs" in ds.globalattributes:
        nRecs = int(ds.globalattributes["nc_nrecs"])
    else:
        nRecs = len(ds.series[ThisOne]["Data"])
    # check the series requested is in the data structure
    if ThisOne in list(ds.series.keys()):
        # series is in the data structure
        if isinstance(ds.series[ThisOne]['Data'],list):
            # return a list if the series is a list
            Series = list(ds.series[ThisOne]['Data'])
        elif isinstance(ds.series[ThisOne]['Data'],numpy.ndarray):
            # return a numpy array if series is an array
            Series = ds.series[ThisOne]['Data'].copy()
        # now get the QC flag
        if 'Flag' in list(ds.series[ThisOne].keys()):
            # return the QC flag if it exists
            Flag = ds.series[ThisOne]['Flag'].copy()
        else:
            # create a QC flag if one does not exist
            Flag = numpy.zeros(nRecs,dtype=numpy.int32)
        # now get the attribute dictionary
        if "Attr" in list(ds.series[ThisOne].keys()):
            Attr = GetAttributeDictionary(ds,ThisOne)
        else:
            Attr = MakeAttributeDictionary()
    else:
        # make an empty series if the requested series does not exist in the data structure
        logger.warning("GetSeries: "+ThisOne+" not found, making empty series ...")
        Series,Flag,Attr = MakeEmptySeries(ds,ThisOne)
    # tidy up
    if ei==-1: ei = nRecs - 1
    if mode=="truncate":
        # truncate to the requested start and end indices
        si = max(0,si)                  # clip start index at 0
        ei = min(nRecs,ei)              # clip end index to nRecs
        Series = Series[si:ei+1]        # truncate the data
        Flag = Flag[si:ei+1]            # truncate the QC flag
    elif mode=="pad":
        # pad with missing data at the start and/or the end of the series
        if si<0 and ei>nRecs-1:
            # pad at the start
            Series = numpy.append(float(c.missing_value)*numpy.ones(abs(si),dtype=numpy.float64),Series)
            Flag = numpy.append(numpy.ones(abs(si),dtype=numpy.int32),Flag)
            # pad at the end
            Series = numpy.append(Series,float(c.missing_value)*numpy.ones((ei-(nRecs-1)),dtype=numpy.float64))
            Flag = numpy.append(Flag,numpy.ones((ei-(nRecs-1)),dtype=numpy.int32))
        elif si<0 and ei<=nRecs-1:
            # pad at the start, truncate the end
            Series = numpy.append(float(c.missing_value)*numpy.ones(abs(si),dtype=numpy.float64),Series[:ei+1])
            Flag = numpy.append(numpy.ones(abs(si),dtype=numpy.int32),Flag[:ei+1])
        elif si>=0 and ei>nRecs-1:
            # truncate at the start, pad at the end
            Series = numpy.append(Series[si:],float(c.missing_value)*numpy.ones((ei-(nRecs-1)),numpy.float64))
            Flag = numpy.append(Flag[si:],numpy.ones((ei-(nRecs-1)),dtype=numpy.int32))
        elif si>=0 and ei<=nRecs-1:
            # truncate at the start and end
            Series = Series[si:ei+1]
            Flag = Flag[si:ei+1]
        else:
            msg = 'GetSeries: unrecognised combination of si ('+str(si)+') and ei ('+str(ei)+')'
            raise ValueError(msg)
    elif mode=="mirror":
        # reflect data about end boundaries if si or ei are out of bounds
        if si<0 and ei>nRecs-1:
            # mirror at the start
            Series = numpy.append(numpy.fliplr([Series[1:abs(si)+1]])[0],Series)
            Flag = numpy.append(numpy.fliplr([Flag[1:abs(si)+1]])[0],Flag)
            # mirror at the end
            sim = 2*nRecs-1-ei
            eim = nRecs-1
            Series = numpy.append(Series,numpy.fliplr([Series[sim:eim]])[0])
            Flag = numpy.append(Flag,numpy.fliplr([Flag[sim:eim]])[0])
        elif si<0 and ei<=nRecs-1:
            # mirror at start, truncate at end
            Series = numpy.append(numpy.fliplr([Series[1:abs(si)+1]])[0],Series[:ei+1])
            Flag = numpy.append(numpy.fliplr([Flag[1:abs(si)+1]])[0],Flag[:ei+1])
        elif si>=0 and ei>nRecs-1:
            # truncate at start, mirror at end
            sim = 2*nRecs-1-ei
            eim = nRecs
            Series = numpy.append(Series[si:],numpy.fliplr([Series[sim:eim]])[0])
            Flag = numpy.append(Flag[si:],numpy.fliplr([Flag[sim:eim]])[0])
        elif si>=0 and ei<=nRecs-1:
            # truncate at the start and end
            Series = Series[si:ei+1]
            Flag = Flag[si:ei+1]
        else:
            msg = 'GetSeries: unrecognised combination of si ('+str(si)+') and ei ('+str(ei)+')'
            raise ValueError(msg)
    else:
        raise ValueError("GetSeries: unrecognised mode option "+str(mode))
    return Series,Flag,Attr

def GetAttributeDictionary(ds,ThisOne):
    attr = {}
    # if series ThisOne is in the data structure
    if ThisOne in list(ds.series.keys()):
        attr = ds.series[ThisOne]['Attr']
    else:
        attr = MakeAttributeDictionary()
    return copy.deepcopy(attr)

def get_datetimefromnctime(ds,time,time_units):
    """
    Purpose:
     Create a series of datetime objects from the time read from a netCDF file.
    Usage:
     footprint_utils.get_datetimefromnctime(ds,time,time_units)
    Side effects:
     Creates a Python datetime series in the data structure
    Author: PRI
    Date: September 2014
    """
    ts = int(ds.globalattributes["time_step"])
    nRecs = int(ds.globalattributes["nc_nrecs"])
    dt = netCDF4.num2date(time,time_units)
    ds.series[str("DateTime")] = {}
    ds.series["DateTime"]["Data"] = dt
    ds.series["DateTime"]["Flag"] = numpy.zeros(nRecs)
    ds.series["DateTime"]["Attr"] = {}
    ds.series["DateTime"]["Attr"]["long_name"] = "Datetime in local timezone"
    ds.series["DateTime"]["Attr"]["units"] = "None"

def get_datetimefromymdhms(ds):
    ''' Creates a series of Python datetime objects from the year, month,
    day, hour, minute and second series stored in the netCDF file.'''
    SeriesList = list(ds.series.keys())
    if ('Year' not in SeriesList or 'Month' not in SeriesList or 'Day' not in SeriesList or
        'Hour' not in SeriesList or 'Minute' not in SeriesList or 'Second' not in SeriesList):
        logger.info(' get_datetimefromymdhms: unable to find all datetime fields required')
        return
    logger.info(' Getting the date and time series')
    year = ds.series["Year"]["Data"].astype('int')
    month = ds.series["Month"]["Data"].astype('int')
    day = ds.series["Day"]["Data"].astype('int')
    hour = ds.series["Hour"]["Data"].astype('int')
    minute = ds.series["Minute"]["Data"].astype('int')
    second = ds.series["Second"]["Data"].astype('int')
    dt = [datetime.datetime(yr,mn,dy,hr,mi,se) for yr,mn,dy,hr,mi,se in zip(year,month,day,hour,minute,second)]
    ds.series["DateTime"] = {}
    ds.series["DateTime"]["Data"] = numpy.array(dt)
    ds.series["DateTime"]["Flag"] = numpy.zeros(len(dt))
    ds.series["DateTime"]["Attr"] = {}
    ds.series["DateTime"]["Attr"]["long_name"] = "Datetime in local timezone"
    ds.series["DateTime"]["Attr"]["units"] = "None"
    return

def round_datetime(ds,mode="nearest_timestep"):
    """
    Purpose:
     Round the series of Python datetimes to the nearest time based on mode
    Usage:
     footprint_utils.round_datetime(ds,mode=mode)
     where;
      mode = "nearest_second" rounds to the nearesy second
      mode = "nearest_timestep" rounds to the nearest time step
    Author: PRI
    Date: February 2015
    """
    # local pointer to the datetime series
    ldt = ds.series["DateTime"]["Data"]
    # check which rounding option has been chosen
    if mode.lower()=="nearest_timestep":
        # get the time step
        if "time_step" in ds.globalattributes:
            ts = int(ds.globalattributes["time_step"])
        else:
            ts = numpy.mean(get_timestep(ds)/60)
            ts = roundtobase(ts,base=30)
            ds.globalattributes["time_step"] = ts
        # round to the nearest time step
        rldt = [rounddttots(dt,ts=ts) for dt in ldt]
    elif mode.lower()=="nearest_second":
        # round to the nearest second
        rldt = [rounddttoseconds(dt) for dt in ldt]
    else:
        # unrecognised option for mode, return original datetime series
        logger.error(" round_datetime: unrecognised mode ("+str(mode)+")"+" ,returning original time series")
        rldt = ds.series["DateTime"]["Data"]
    # replace the original datetime series with the rounded one
    ds.series["DateTime"]["Data"] = numpy.array(rldt)
    return

def rounddttoseconds(dt):
    """
    Purpose:
     Round the time stamp to the nearest the nearest second.
    Usage:
    Author: PRI (probably stolen from StackOverFlow)
    Date: Back in the day
    """
    dt += datetime.timedelta(seconds=0.5)
    dt -= datetime.timedelta(seconds=dt.second % 1,microseconds=dt.microsecond)
    return dt

def CheckTimeStep(ds):
    """
    Purpose:
     Checks the datetime series in the data structure ds to see if there are
     any missing time stamps.
     This function returns a logical variable that is true if any gaps exist
     in the time stamp.
    Useage:
     has_gaps = CheckTimeSTep(ds)
     if has_gaps:
         <do something about missing time stamps>
    Author: PRI
    Date: April 2013
    """
    # set the has_gaps logical
    has_gaps = False
    # get the number of records
    nRecs = int(ds.globalattributes["nc_nrecs"])
    # get the time step
    ts = int(ds.globalattributes["time_step"])
    # time step between records in seconds
    dt = get_timestep(ds)
    # indices of elements where time step not equal to default
    index = numpy.where(dt!=ts*60)[0]
    # check to see if ww have any time step problems
    if len(index)!=0:
        has_gaps = True
        logger.warning(" CheckTimeStep: "+str(len(index))+" problems found with the time stamp")
    return has_gaps

def get_timestep(ds):
    """
    Purpose:
     Return an array of time steps in seconds between records
    Useage:
     dt = footprint_utils.get_timestep(ds)
    Author: PRI
    Date: February 2015
    """
    # local pointer to the Python datetime series
    ldt = ds.series["DateTime"]["Data"]
    # time step between records in seconds
    dt = numpy.array([(ldt[i]-ldt[i-1]).total_seconds() for i in range(1,len(ldt))])
    return dt

def make_attribute_dictionary(**kwargs):
    """
    Purpose:
     Make an empty attribute dictionary.
    Usage:
     attr_new = footprint_utils.make_attribute_dictionary(long_name = "some string",attr_exist)
     where long_name is an attribute to be written to the new attribute dictionary
           attr_exist is an existing attribute dictionary
    Author: PRI
    Date: Back in the day
    """
    default_list = ['ancillary_variables', 'height', 'instrument', 'serial_number',
                    'standard_name', 'long_name', 'units']
    attr = {}
    for item in kwargs:
        if isinstance(item, dict):
            for entry in item:
                attr[entry] = item[entry]
        else:
            attr[item] = kwargs.get(item, 'not defined')
        if item in default_list:
            default_list.remove(item)
    if len(default_list) != 0:
        for item in default_list:
            attr[item] = 'not defined'
    attr["missing_value"] = c.missing_value
    return copy.deepcopy(attr)

def get_start_index(ldt, start, mode="quiet"):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: October 2016
    """
    if isinstance(start, str):
        try:
            start = dateutil.parser.parse(start)
            if start >= ldt[0] and start <= ldt[-1]:
                si = numpy.where(ldt == start)[0][0]
            else:
                if mode == "verbose":
                    msg = "Requested start date not found, setting to first date"
                    logger.warning(msg)
                si = 0
        except ValueError as error:
            if mode == "verbose":
                msg = "Error parsing start date string, setting to first date"
                logger.warning(msg)
            si = 0
    elif isinstance(start, datetime.datetime):
        if start >= ldt[0] and start <= ldt[-1]:
            si = numpy.where(ldt == start)[0][0]
        else:
            if mode == "verbose":
                msg = "Requested start date not found, setting to first date"
                logger.warning(msg)
            si = 0
    elif (isinstance(start, numbers.Number)):
        si = max([0,int(start)])
    else:
        if mode == "verbose":
            msg = "Unrecognised type for start, setting to first date"
            logger.warning(msg)
        si = 0
    return si

def get_end_index(ldt, end, mode="quiet"):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: October 2016
    """
    if isinstance(end, str):
        try:
            end = dateutil.parser.parse(end)
            if end <= ldt[-1] and end >= ldt[0]:
                ei = numpy.where(ldt == end)[0][0]
            else:
                if mode == "verbose":
                    msg = "Requested end date not found, setting to last date"
                    logger.warning(msg)
                ei = len(ldt)
        except ValueError as error:
            if mode == "verbose":
                msg = "Error parsing end date string, setting to last date"
                logger.warning(msg)
            ei = len(ldt)
    elif isinstance(end, datetime.datetime):
        if end >= ldt[0] and end <= ldt[-1]:
            ei = numpy.where(ldt == end)[0][0]
        else:
            if mode == "verbose":
                msg = "Requested end date not found, setting to last date"
                logger.warning(msg)
            ei = len(ldt)
    elif (isinstance(end, numbers.Number)):
        ei = min([int(end), len(ldt)])
    else:
        if mode == "verbose":
            msg = "Unrecognised type for end date, setting to last date"
            logger.warning(msg)
        ei = len(ldt)
    return ei

def find_nearest_value(array, value):
    """
    Purpose:
     footprint_utils.bisection() gives the left bound of the interval of array containing
     value, this function gives the index of the closest value.
    """
    i = bisection(array, value)
    if i < len(array)-1:
        if abs(array[i+1]-value) <= abs(array[i]-value):
            i = i + 1
    return i

def bisection(array,value):
    '''Given an ``array`` , and given a ``value`` , returns an index j such that ``value`` is between array[j]
    and array[j+1]. ``array`` must be monotonic increasing. j=-1 or j=len(array) is returned
    to indicate that ``value`` is out of range below and above respectively.
    Stolen from https://stackoverflow.com/questions/2566412/find-nearest-value-in-numpy-array/2566508'''
    n = len(array)
    if (value < array[0]):
        return -1
    elif (value > array[n-1]):
        return n
    jl = 0# Initialize lower
    ju = n-1# and upper limits.
    while (ju-jl > 1):# If we are not yet done,
        jm=(ju+jl) >> 1# compute a midpoint with a bitshift
        if (value >= array[jm]):
            jl=jm# and replace either the lower limit
        else:
            ju=jm# or the upper limit, as appropriate.
        # Repeat until the test condition is satisfied.
    if (value == array[0]):# edge cases at bottom
        return 0
    elif (value == array[n-1]):# and top
        return n-1
    else:
        return jl

def FindIndicesOfBInA(a,b):
    """
    Purpose:
     Find the indices of elements in b that also occur in a.
     The routine is intended for use only with lists of Python datetime
     values.  This ensures the input series are monotonically increasing
     (though this is not a requirement) and contain no duplicates (which
     is required, or at least not handled).
    Limitations:
     Argument a is converted to a set to greatly speed the comparison
     of b elements with a.  This means that duplicates in a will be
     dropped and hence only 1 index will be returned for each value
     in b.
    Usage:
     indices = footprint_utils.FindIndicesOfBInA(a,b)
     where a is a list of Python datetime objects
           b is a list of Python datetime objects
           indices is a list of indices in b where the elements of b
                also occur in a
    Author: PRI
    Date: July 2015
    Comments: Replaces find_indices used up to V2.9.3.
    March 2018 - rewritten to handle numpy.ndarray and lists
    """
    if len(set(a))!=len(a):
        msg = " FindIndicesOfBInA: first argument contains duplicate values"
        logger.warning(msg)
    if isinstance(a, numpy.ndarray) and isinstance(b, numpy.ndarray):
        asorted = numpy.argsort(a)
        bpos = numpy.searchsorted(a[asorted], b)
        indices = asorted[bpos]
    elif isinstance(a, list) and isinstance(b, list):
        tmpset = set(a)
        indices = [i for i,item in enumerate(b) if item in tmpset]
    else:
        msg = " FindIndicesOfBInA: inputs must be both list or both numpy arrays"
        logger.warning(msg)
        indices = []
    return indices

def CreateSeries(ds,Label,Data,Flag,Attr):
    """
    Purpose:
     Create a series (1d array) of data in the data structure.
     If the series already exists in the data structure, data values and QC flags will be
     overwritten but attributes will be preserved.  However, the long_name and units attributes
     are treated differently.  The existing long_name will have long_name appended to it.  The
     existing units will be overwritten with units.
     This utility is the prefered method for creating or updating a data series because
     it implements a consistent method for creating series in the data structure.  Direct
     writes to the contents of the data structure are discouraged (unless PRI wrote the code:=P).
    Usage:
     Fsd,flag,attr = footprint_utils.GetSeriesasMA(ds,"Fsd")
      ... do something to Fsd here ...
     footprint_utils.CreateSeries(ds,"Fsd",Fsd,flag,attr)
    Author: PRI
    Date: Back in the day
    """
    ds.series['_tmp_'] = {}                       # create a temporary series to avoid premature overwrites
    # put the data into the temporary series
    if numpy.ma.isMA(Data):
        ds.series['_tmp_']['Data'] = numpy.ma.filled(Data,float(c.missing_value))
    else:
        ds.series['_tmp_']['Data'] = numpy.array(Data)
    # copy or make the QC flag
    if Flag is None:
        ds.series['_tmp_']['Flag'] = MakeQCFlag(ds,FList)
    else:
        ds.series['_tmp_']['Flag'] = Flag.astype(numpy.int32)
    # do the attributes
    ds.series['_tmp_']['Attr'] = {}
    if Label in list(ds.series.keys()):                 # check to see if the series already exists
        for attr in ds.series[Label]['Attr']:     # if it does, copy the existing attributes
            if attr in Attr and ds.series[Label]['Attr'][attr]!=Attr[attr]:
                ds.series['_tmp_']['Attr'][attr] = Attr[attr]
            else:
                ds.series['_tmp_']['Attr'][attr] = ds.series[Label]['Attr'][attr]
        for attr in Attr:
            if attr not in list(ds.series['_tmp_']['Attr'].keys()):
                ds.series['_tmp_']['Attr'][attr] = Attr[attr]
    else:
        for item in Attr:
            ds.series['_tmp_']['Attr'][item] = Attr[item]
    ds.series[str(Label)] = ds.series['_tmp_']     # copy temporary series to new series
    del ds.series['_tmp_']                        # delete the temporary series

def MakeAttributeDictionary(**kwargs):
    """
    Purpose:
     Make an attribute dictionary.
    Usage:
     attr_new = pfp_utils.MakeAttributeDictionary(long_name = "some string",attr_exist)
     where long_name is an attribute to be written to the new attribute dictionary
           attr_exist is an existing attribute dictionary
    Author: PRI
    Date: Back in the day
    """
    default_list = ["height", "instrument", "long_name", "serial_number",
                    "standard_name", "units", "valid_range", "group_name"]
    attr = {}
    for item in kwargs:
        if isinstance(item, dict):
            for entry in item: attr[entry] = item[entry]
        else:
            attr[item] = kwargs.get(item,"")
        if item in default_list: default_list.remove(item)
    if len(default_list)!=0:
        for item in default_list:
            if item == "valid_range":
                attr[item] = str(c.small_value)+","+str(c.large_value)
            else:
                attr[item] = ""
    attr["missing_value"] = c.missing_value
    return copy.deepcopy(attr)

def get_optionskeyaslogical(cf, key, default=False):
    returnValue = default
    if "Options" in cf:
        if key in cf["Options"]:
            returnValue = cf.get("Options").as_bool(key)
    return returnValue
