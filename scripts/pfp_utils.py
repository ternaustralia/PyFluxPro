# the following line needed for unicode character in convert_anglestring
# -*- coding: latin-1 -*-
# standard modules
import copy
import datetime
import logging
import numbers
import os
import platform
import sys
import time
# third party modules
import cftime
import dateutil
import numpy
import pytz
import xlrd
# PFP modules
from scripts import constants as c
from scripts import meteorologicalfunctions as pfp_mf

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

def append_to_attribute(attr, to_add):
    """
    """
    # sanity check
    assert isinstance(attr, dict), "Expected a dictionary, got " + str(type(attr))
    assert isinstance(to_add, dict), "Expected a dictionary, got " + str(type(to_add))
    # do the business
    for key in sorted(list(to_add.keys())):
        if key not in attr:
            # add the key to the attribute dictionary
            val = to_add[key]
            attr[key] = val[0].upper() + val[1:]
        else:
            # append the key value to the attribute
            val = to_add[key]
            attr[key] += ", " + val
    return

def append_string(attr, string_to_add, caps=True):
    """
    Purpose:
     Format the input attribute string and add it to the attribute.
    Usage:
    Side effects:
    Author: PRI
    Date: November 2018
    """
    if len(attr) == 0:
        if caps:
            attr = string_to_add[:1].upper() + string_to_add[1:]
        else:
            attr = string_to_add
    else:
        attr += ", " + string_to_add
    return attr

def bp(fx,tao):
    """
    Function to calculate the b and p coeficients of the Massman frequency correction.
    """
    bp = 2 * c.Pi * fx * tao
    return bp

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

def string_to_list(input_string):
    """ Convert a string containing items separated by commas into a list."""
    #input_string = "".join(input_string.split())
    if "," in input_string:
        output_list = [i.lstrip().rstrip() for i in input_string.split(",")]
    else:
        output_list = [input_string.lstrip().rstrip()]
    return output_list

def cfkeycheck(cf,Base='Variables',ThisOne=[],key=[]):
    if len(ThisOne) == 0:
        return
    if len(key) == 0:
        if Base in list(cf.keys()) and ThisOne in list(cf[Base].keys()):
            return ThisOne in list(cf[Base].keys())
        else:
            return
    else:
        if Base in list(cf.keys()) and ThisOne in list(cf[Base].keys()):
            return key in list(cf[Base][ThisOne].keys())
        else:
            return

def get_optionskeyaslogical(cf, key, default=False):
    returnValue = default
    if "Options" in cf:
        if key in cf["Options"]:
            returnValue = cf.get("Options").as_bool(key)
    return returnValue

def CheckFco2Units(ds, new_units, convert_units=True):
    """
    Purpose:
     Check the CO2 flux units.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2020
    """
    # list of supported CO2 flux units
    ok_units = ["mg/m^2/s", "mgCO2/m^2/s", "umol/m^2/s"]
    # list of CO2 flux variables ("Fco2") with allowed units
    labels = list(ds.root["Variables"].keys())
    Fco2_list = [l for l in labels if l[0:4] == "Fco2"]
    for label in list(Fco2_list):
        if "units" not in ds.root["Variables"][label]["Attr"]:
            Fco2_list.remove(label)
            continue
        if ds.root["Variables"][label]["Attr"]["units"] not in ok_units:
            Fco2_list.remove(label)
            continue
    # check the units of Fc and convert if necessary
    CheckUnits(ds, Fco2_list, "umol/m^2/s", convert_units=True)
    return

def CheckQCFlags(ds):
    """
    Purpose:
     Make sure that all values of -9999 in a data series have a non-zero QC flag value.
    Usage:
     pfp_utils.CheckQCFlags(ds)
    Author: PRI
    Date: August 2014
    """
    msg = " Checking missing data and QC flags are consistent"
    logger.info(msg)
    labels = [label for label in list(ds.root["Variables"].keys()) if label not in ["DateTime"]]
    # force any values of -9999 with QC flags of 0 to have a QC flag of 8
    for label in labels:
        var = GetVariable(ds, label)
        condition = numpy.ma.getmaskarray(var["Data"]) & (numpy.mod(var["Flag"],10) == 0)
        idx = numpy.ma.where(condition == True)[0]
        if len(idx)!=0:
            msg = " "+label+": "+str(len(idx))+" missing values with flag = 0 (forced to 8)"
            logger.warning(msg)
            var["Flag"][idx] = numpy.int32(8)
            CreateVariable(ds, var)
    # force all values != -9999 to have QC flag = 0, 10, 20 etc
    for label in labels:
        var = GetVariable(ds, label)
        condition = (numpy.ma.getmaskarray(var["Data"]) == False) & (numpy.mod(var["Flag"],10) != 0)
        idx = numpy.where(condition == True)[0]
        if len(idx)!=0:
            msg = " "+label+": "+str(len(idx))+" non-missing values with flag != 0"
            logger.warning(msg)
    return

def CheckTimeStep(ds, mode="quiet"):
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
    # get the time step
    try:
        ts = int(float(ds.root["Attributes"]["time_step"]))
    except:
        if mode != "quiet":
            msg = " CheckTimeStep: 'time_step' is not a number, skipping check ..."
            logger.error(msg)
        return False
    # time step between records in seconds
    dt = get_timestep(ds)
    # indices of elements where time step not equal to default
    index = numpy.where(dt!=ts*60)[0]
    # check to see if ww have any time step problems
    if len(index)!=0:
        has_gaps = True
        msg = " CheckTimeStep: " + str(len(index)) + " problems found with the time stamp"
        logger.warning(msg)
    return has_gaps

def CheckUnits(ds, label, units, convert_units=False):
    """
    Purpose:
     General units checking and conversion.
    Usage:
     pfp_utils.CheckUnits(ds,label,units,convert_units=True)
     where ds is a data structure
           label (string) is the label of the series for which the units
                          are to be checked
           units (string) is the required units
           convert_units (logical, optional) is True to force conversion to
                        required units
    Author: PRI
    Date: January 2016
    """
    if isinstance(label, str):
        label_list = [label]
    elif isinstance(label, list):
        label_list = label
    else:
        msg = " CheckUnits: input label "+label+" must be a string or a list"
        logger.error(msg)
        return
    for label in label_list:
        if label not in list(ds.root["Variables"].keys()):
            continue
        variable = GetVariable(ds, label)
        if variable["Attr"]["units"] != units and convert_units:
            msg = " Units for "+label+" converted from "+variable["Attr"]["units"]+" to "+units
            logger.info(msg)
            variable = convert_units_func(ds, variable, units)
            CreateVariable(ds, variable)
        else:
            if not convert_units:
                msg = " Units mismatch but conversion disabled"
                logger.warning(msg)
    return

def contiguous_regions(condition):
    """
    Purpose:
     Finds contiguous True regions of the boolean array "condition". Returns
     a 2D array where the first column is the start index of the region and the
     second column is the end index.
    Author: Joe Kington (via StackOverflow)
    Date: September 2014
    """
    # Find the indicies of changes in "condition"
    d = numpy.diff(condition)
    idx, = d.nonzero()
    # We need to start things after the change in "condition". Therefore,
    # we'll shift the index by 1 to the right.
    idx += 1
    if condition[0]:
        # If the start of condition is True prepend a 0
        idx = numpy.r_[0, idx]
    if condition[-1]:
        # If the end of condition is True, append the length of the array
        idx = numpy.r_[idx, condition.size] # Edit
    # Reshape the result into two columns
    idx.shape = (-1,2)
    return idx

def ConvertCO2Units(cf, ds):
    """
    Purpose:
     Convert CO2 concentration units as required.
    Usage:
    Side effects:
     The units of any CO2 concentrations in the data structure are converted to the units
     specified in the [Options] section of the control file.
    Author: PRI
    Date: Back in the day
    """
    # list of supported CO2 flux units
    units_list = ["mg/m^3", "mg^2/m^6", "mgCO2/m^3", "mgCO2^2/m^6",
                  "mmol/m^3", "umol/m^3", "umol/mol"]
    # get the CO2 units requested by the user
    CO2_units_out = get_keyvaluefromcf(cf, ["Options"], "CO2Units", default="umol/mol")
    # get a list of CO2 series
    labels = ds.root["Variables"].keys()
    CO2_labels = [l for l in labels if l[0:3] == "CO2" and ds.root["Variables"][l]["Attr"]["units"] in units_list]
    # do the units conversion
    # separate averages and standard deviations
    for label in CO2_labels:
        CO2_in = GetVariable(ds, label)
        # skip if the old and new units are the same
        if CO2_in["Attr"]["units"] == CO2_units_out:
            continue
        # check if we have a standard deviation or a variance
        CO2_units_in = CO2_in["Attr"]["units"]
        if (label[-3:] == "_Sd"):
            if (CO2_units_out == "umol/mol"):
                if (CO2_units_in in ["mg/m^3"]):
                    # the only conversion allowed for standard deviations is mg/m^3 to mmol/m^3 ...
                    # ... and we will only do it if the user has requested umol/mol for CO2
                    msg = " Converting " + label + " from " + CO2_in["Attr"]["units"] + " to mmol/m^3"
                    logger.info(msg)
                    CO2_out = convert_units_func(ds, CO2_in, "mmol/m^3")
                    CreateVariable(ds, CO2_out)
                else:
                    continue
        elif (label[-3:] == "_Vr"):
            if (CO2_units_out == "umol/mol"):
                if (CO2_units_in in ["mg^2/m^6"]):
                    # the only conversion allowed for variances is mg^2/m^6 to mmol^2/m^6
                    msg = " Converting " + label + " from " + CO2_in["Attr"]["units"] + " to mmol^2/m^6"
                    logger.info(msg)
                    CO2_in["Data"] = numpy.ma.sqrt(CO2_in["Data"])
                    CO2_in["Attr"]["units"] = "mg/m^3"
                    CO2_out = convert_units_func(ds, CO2_in, "mmol/m^3")
                    CO2_out["Data"] = CO2_out["Data"]*CO2_out["Data"]
                    CO2_out["Attr"]["units"] = "mmol^2/m^6"
                    CreateVariable(ds, CO2_out)
                else:
                    continue
        elif ((CO2_units_in in ["mg/m^3"]) and (CO2_units_out == "umol/mol")):
            # assume we have an average and do the units conersion
            msg = " Converting " + label + " from " + CO2_in["Attr"]["units"]
            msg += " to " + CO2_units_out
            logger.info(msg)
            CO2_out = convert_units_func(ds, CO2_in, CO2_units_out)
            CreateVariable(ds, CO2_out)
        else:
            msg = " Unrecognised conversion for " + label
            msg += " (" + CO2_units_in + " to " + CO2_units_out + ")"
            logger.error(msg)
    return

def ConvertFco2Units(cf, ds):
    """
    Purpose:
     Convert CO2 flux units as required.
    Usage:
    Side effects:
     The units of any CO2 flux in the data structure are converted to the units specified
     in the [Options] section of the control file.
    Author: PRI
    Date: Back in the day
    """
    descr_level = "description_" + str(ds.root["Attributes"]["processing_level"])
    # list of supported CO2 flux units
    units_list = ["mg/m^2/s", "umol/m^2/s"]
    # get the Fco2 units requested by the user
    units_out = get_keyvaluefromcf(cf, ['Options'], "Fco2Units", default="umol/m^2/s")
    # get a list of Fco2 and Sco2 variables
    labels = list(ds.root["Variables"].keys())
    Fco2_labels = [l for l in labels if l[0:4] == "Fco2"]
    Sco2_labels = [l for l in labels if l[0:4] == "Sco2"]
    labels = Fco2_labels + Sco2_labels
    for label in list(labels):
        if "units" not in ds.root["Variables"][label]["Attr"]:
            labels.remove(label)
            continue
        if ds.root["Variables"][label]["Attr"]["units"] not in units_list:
            labels.remove(label)
            continue
    # convert units of Fco2 and Sco2 as required
    for label in labels:
        # get the Fco2 or Sco2 variable
        var = GetVariable(ds, label)
        units_in = var["Attr"]["units"]
        # check to see if we need to convert units
        if units_in == units_out:
            # nothing to see here, folks
            continue
        # if we get here, we need to convert units
        logger.info(" Converting " + label + " from " + units_in + " to " + units_out)
        if units_out == "umol/m^2/s" and units_in == "mg/m^2/s":
            var["Data"] = pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps(var["Data"])
            append_to_attribute(var["Attr"], {descr_level: "converted to umol/m^2/s"})
            var["Attr"]["units"] = units_out
            var["Attr"]["standard_name"] = "surface_upward_mole_flux_of_carbon_dioxide"
            CreateVariable(ds, var)
        elif units_out == "mg/m^2/s" and units_in == "umol/m^2/s":
            var["Data"] = pfp_mf.Fco2_mgCO2pm2psfromumolpm2ps(var["Data"])
            append_to_attribute(var["Attr"], {descr_level: "converted to mg/m^2/s"})
            var["Attr"]["units"] = units_out
            # standard_name not defined when units are mg/m^2/s
            if "standard_name" in var["Attr"]:
                var["Attr"].pop("standard_name")
            CreateVariable(ds, var)
        else:
            logger.info('  Unrecognised input or output units for '+label)
    return

def convert_units_func(ds, variable, new_units, mode="quiet"):
    """
    Purpose:
     Generic routine for changing units.
     Nothing is done if the original units are the same as the requested units.
    Usage:
     new_variable = pfp_utils.convert_units_func(ds, old_variable, new_units)
     where;
      new_variable is a copy of old_variable converted to new_units
      ds is a data structure
      old_variable is a variable in the original units
      new_units are the units of the new data
    Author: PRI
    Date: July 2015
    """
    old_units = variable["Attr"]["units"]
    if old_units == new_units:
        if mode != "quiet":
            # old units same as new units, nothing to do ...
            msg = " New units same as old ones, skipping ..."
            logger.warning(msg)
        return variable
    # check the units and the long_name are something we understand
    co2_info = {"units": ["umol/m^2/s", "gC/m^2", "mg/m^3", "mgCO2/m^3", "umol/mol",
                          "mg/m^2/s", "mgCO2/m^2/s", "mmol/m^3"],
                "long_name": ["co2", "carbon dioxide", "ecosystem respiration",
                              "gross primary productivity", "net ecosystem exchange",
                              "net ecosystem productivity"]}
    h2o_info = {"units": ["g/m^3", "kg/m^3", "mmol/mol", "%", "percent", "frac",
                          "fraction", "kg/kg", "mmol/m^3", "kg/m^2/s", "kg/m^2"],
                "long_name": ["h2o", "humidity", "vapour", "evapo", "transpiration"]}
    t_info = {"units": ["degC", "K"], "long_name": ["temperature"]}
    ps_info = {"units": ["Pa", "hPa", "kPa"], "long_name": ["pressure"]}
    sws_info = {"units": ["%", "percent", "frac", "m^3/m^3", "kg/m^2"], "long_name": ["soil"]}
    ok_units = co2_info["units"] + h2o_info["units"]
    ok_units += t_info["units"] + ps_info["units"]
    ok_units += sws_info["units"]
    # parse the original units
    label = variable["Label"]
    if old_units not in ok_units:
        msg = " Unrecognised units (" + old_units + ") in " + label
        logger.error(msg)
    elif new_units not in ok_units:
        msg = " Unrecognised units requested (" + new_units + ")"
        msg += " for variable " + label
        logger.error(msg)
    elif (new_units in co2_info["units"] and old_units in co2_info["units"]):
        doit = False
        for item in co2_info["long_name"]:
            if item in variable["Attr"]["long_name"].lower():
                doit = True
        if doit:
            variable = convert_units_co2(ds, variable, new_units, co2_info)
    elif (new_units in h2o_info["units"] and old_units in h2o_info["units"]):
        doit = False
        for item in h2o_info["long_name"]:
            if item in variable["Attr"]["long_name"].lower():
                doit = True
        if doit:
            variable = convert_units_h2o(ds, variable, new_units, h2o_info)
    elif (new_units in t_info["units"] and old_units in t_info["units"]):
        doit = False
        for item in t_info["long_name"]:
            if item in variable["Attr"]["long_name"].lower():
                doit = True
        if doit:
            variable = convert_units_t(ds, variable, new_units, t_info)
    elif (new_units in ps_info["units"] and old_units in ps_info["units"]):
        doit = False
        for item in ps_info["long_name"]:
            if item in variable["Attr"]["long_name"].lower():
                doit = True
        if doit:
            variable = convert_units_ps(ds, variable, new_units, ps_info)
    elif (new_units in sws_info["units"] and old_units in sws_info["units"]):
        doit = False
        for item in sws_info["long_name"]:
            if item in variable["Attr"]["long_name"].lower():
                doit = True
        if doit:
            variable = convert_units_soil(ds, variable, new_units, sws_info)
    else:
        msg = "Unrecognised units combination " + old_units + " and " + new_units
        logger.error(msg)
        variable = variable
    return variable

def convert_units_co2(ds, variable, new_units, co2_info):
    """
    Purpose:
     General purpose routine to convert from one set of CO2 concentration units
     to another.
     Conversions supported are:
      umol/m^2/s to g/m^2 (per time step)
      g/m^2 (per time step) to umol/m^2/s
      mg/m^3 to umol/mol
      mgCO2/m^3 to umol/mol
      umol/mol to mg/m^3
      mg/m^2/s to umol/m^2/s
      mgCO2/m2/s to umol/m^2/s
    Usage:
     new_data = pfp_utils.convert_units_co2(ds, variable, new_units, co2_info)
      where ds is a data structure
            variable (dictionary) is a variable dictionary
            new_units (string) is the new units
            co2_info is a dictionary of CO2 units and long name possibilities defined in
                     pfp_utils.convert_units_func()
    Author: PRI
    Date: January 2016
    """
    # get the current units and the timestep
    old_units = variable["Attr"]["units"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # now check the units and see what we have to convert
    if old_units == "umol/m^2/s" and new_units == "gC/m^2":
        # convert the data
        variable["Data"] = pfp_mf.Fco2_gCpm2fromumolpm2ps(variable["Data"], ts)
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.Fco2_gCpm2fromumolpm2ps, ts=ts)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.Fco2_gCpm2fromumolpm2ps, ts=ts)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        if "standard_name" in list(variable["Attr"].keys()):
            variable["Attr"].pop("standard_name")
    elif old_units == "gC/m^2" and new_units == "umol/m^2/s":
        # convert the data
        variable["Data"] = pfp_mf.Fco2_umolpm2psfromgCpm2(variable["Data"], ts=ts)
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.Fco2_umolpm2psfromgCpm2, ts=ts)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.Fco2_umolpm2psfromgCpm2, ts=ts)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        variable["Attr"]["standard_name"] = "surface_upward_mole_flux_of_carbon_dioxide"
    elif old_units in ["mg/m^2/s", "mgCO2/m^2/s"] and new_units == "umol/m^2/s":
        # convert the data
        variable["Data"] = pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps(variable["Data"])
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.Fco2_umolpm2psfrommgCO2pm2ps)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        variable["Attr"]["standard_name"] = "surface_upward_mole_flux_of_carbon_dioxide"
    elif old_units == "umol/m^2/s" and new_units in ["mg/m^2/s", "mgCO2/m^2/s"]:
        # convert the data
        variable["Data"] = pfp_mf.Fco2_mgCO2pm2psfromumolpm2ps(variable["Data"])
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.Fco2_mgCO2pm2psfromumolpm2ps)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.Fco2_mgCO2pm2psfromumolpm2ps)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        if "standard_name" in list(variable["Attr"].keys()):
            variable["Attr"].pop("standard_name")
    elif old_units in ["mg/m^3", "mgCO2/m^3"] and new_units == "umol/mol":
        Ta = GetVariable(ds, "Ta")
        ps = GetVariable(ds, "ps")
        # convert the data
        variable["Data"] = pfp_mf.co2_ppmfrommgCO2pm3(variable["Data"], Ta["Data"], ps["Data"])
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.co2_ppmfrommgCO2pm3, Ta=Ta, ps=ps)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.co2_ppmfrommgCO2pm3, Ta=Ta, ps=ps)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mole_fraction_of_carbon_dioxide_in_air"
    elif old_units == "umol/mol" and new_units in ["mg/m^3", "mgCO2/m^3"]:
        Ta = GetVariable(ds, "Ta")
        ps = GetVariable(ds, "ps")
        variable["Data"] = pfp_mf.co2_mgCO2pm3fromppm(variable["Data"], Ta["Data"], ps["Data"])
        # convert the rangecheck attributes
        convert_units_co2_attributes_rangecheck(variable, pfp_mf.co2_mgCO2pm3fromppm, Ta=Ta, ps=ps)
        # convert the valid_range attribute
        convert_units_co2_attributes_validrange(variable, pfp_mf.co2_mgCO2pm3fromppm, Ta=Ta, ps=ps)
        # update the variable attributes to the new units
        variable["Attr"]["units"] = new_units
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mass_concentration_of_carbon_dioxide_in_air"
    elif old_units in ["mg/m^3", "mgCO2/m^3"] and new_units == "mmol/m^3":
        variable["Data"] = variable["Data"] / (float(1000)*float(c.Mco2))
        variable["Attr"]["units"] = new_units
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mole_concentration_of_carbon_dioxide_in_air"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / (float(1000)*float(c.Mco2))) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / (float(1000)*float(c.Mco2))) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    else:
        msg = " Unrecognised conversion from " + old_units + " to " + new_units
        logger.error(msg)
    return variable

def convert_units_co2_attributes_rangecheck(CO2, func, Ta=None, ps=None, ts=None):
    """
    Purpose:
     Convert the rangecheck_lower and rangecheck_upper
     variable attributes from the old units to the new units.
    Usage:
    Author: PRI
    Date: June 2021
    """
    month = numpy.array([d.month for d in CO2["DateTime"]])
    nrecs = len(month)
    for item in ["rangecheck_lower", "rangecheck_upper"]:
        if item not in CO2["Attr"]:
            continue
        limit = string_to_list(CO2["Attr"][item])
        CO2["Attr"][item] = ""
        limit = numpy.array([float(i) for i in limit])
        if len(limit) == 1:
            # 1 limit for whole data set
            data = numpy.ma.array(numpy.full(nrecs, limit[0]))
            if Ta is None and ps is None:
                if ts is None:
                    tmp = func(data)
                else:
                    tmp = func(data, ts)
            else:
                tmp = func(data, Ta["Data"], ps["Data"])
            if item == "rangecheck_lower":
                new_limit = numpy.amin(tmp)
            else:
                new_limit = numpy.amax(tmp)
            CO2["Attr"][item] = str(round2significant(new_limit, 5))
        elif len(limit) == 12:
            # 1 limit for each month
            new_attr = []
            for m in range(len(limit)):
                idx = numpy.where(month == m+1)[0]
                data = numpy.ma.array(numpy.full(len(idx), limit[m]))
                if Ta is None and ps is None:
                    if ts is None:
                        tmp = func(data)
                    else:
                        tmp = func(data, ts)
                else:
                    tmp = func(data, Ta["Data"][idx], ps["Data"][idx])
                if numpy.ma.count(tmp) == 0:
                    new_limit = -9999
                else:
                    if item == "rangecheck_lower":
                        new_limit = numpy.amin(tmp)
                    else:
                        new_limit = numpy.amax(tmp)
                new_attr.append(str(round2significant(new_limit, 5)))
            CO2["Attr"][item] = ",".join(new_attr)
        else:
            # rangecheck_lower is the wrong length
            msg = "Variable attribute " + item + " is the wrong length"
            logger.error(msg)
    return

def convert_units_co2_attributes_validrange(CO2, func, Ta=None, ps=None, ts=None):
    """
    Purpose:
     Convert the valid_range variable attributes from the
     old units to the new units.
    Usage:
    Author: PRI
    Date: June 2021
    """
    if "valid_range" not in CO2["Attr"]:
        return
    nrecs = len(CO2["DateTime"])
    old_valid_range = string_to_list(CO2["Attr"]["valid_range"])
    old_valid_range = [float(i) for i in old_valid_range]
    new_valid_range = []
    data = numpy.ma.array(numpy.full(nrecs, old_valid_range[0]))
    if Ta is None and ps is None:
        if ts is None:
            tmp = func(data)
        else:
            tmp = func(data, ts)
    else:
        tmp = func(data, Ta["Data"], ps["Data"])
    new_valid_range.append(str(round2significant(numpy.amin(tmp), 5)))
    data = numpy.ma.array(numpy.full(nrecs, old_valid_range[1]))
    if Ta is None and ps is None:
        if ts is None:
            tmp = func(data)
        else:
            tmp = func(data, ts)
    else:
        tmp = func(data, Ta["Data"], ps["Data"])
    new_valid_range.append(str(round2significant(numpy.amax(tmp), 5)))
    CO2["Attr"]["valid_range"] = ",".join(new_valid_range)
    return

def convert_units_h2o(ds, variable, new_units, h2o_info):
    """
    Purpose:
     General purpose routine to convert from one set of H2O concentration units
     to another.
     Conversions supported are:
      g/m^3 to mmol/mol
      mmol/mol to g/m^3
      fraction/frac to %/percent
      %/percent to frac/fraction
    Usage:
     variable = pfp_utils.convert_units_h2o(ds, variable, new_units, h2o_info)
      where ds is a data structure
            variable (dictionary) is a variable dictionary
            new_units (string) is the new units
            variable is a new variable with data converted to new_units
            h2o_info is defined in pfp_utils.convert_units_func()
    Author: PRI
    Date: January 2016
    """
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    series_list = list(ds.root["Variables"].keys())
    ok_units = h2o_info["units"]
    old_units = variable["Attr"]["units"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    if ((old_units not in ok_units) or (new_units not in ok_units)):
        msg = " Unrecognised conversion from " + old_units + " to " + new_units
        logger.error(msg)
        return variable
    if old_units == "kg/m^2/s" and new_units == "kg/m^2":
        variable["Data"] = pfp_mf.ET_kgpm2fromkgpm2ps(variable["Data"], ts)
        variable["Attr"]["units"] = new_units
        # no standard_name for ET in units of kg/m^2/timestep
        if "standard_name" in list(variable["Attr"].keys()):
            variable["Attr"].pop("standard_name")
    elif old_units == "mmol/mol" and new_units == "g/m^3":
        # this routine may be called before Ta and ps have been created by
        # merging variables as specified in the control file
        if "Ta" in series_list:
            Ta = GetVariable(ds, "Ta")
        else:
            # if Ta doesn't exist, create it by merging anything that starts with "Ta" or "Tv"
            t_list = [t for t in series_list if t[0:2] in ["Ta", "Tv"]]
            Ta = MergeVariables(ds, "Ta", t_list)
        if "ps" in series_list:
            ps = GetVariable(ds, "ps")
        else:
            # if ps doesn't exist, create it by merging anything that starts with "ps"
            p_list = [p for p in series_list if p[0:2] in ["ps"]]
            ps = MergeVariables(ds, "ps", p_list)
        variable["Data"] = pfp_mf.h2o_gpm3frommmolpmol(variable["Data"], Ta["Data"], ps["Data"])
        variable["Attr"]["units"] = new_units
        # standard_name for mass concentration of water vapour
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mass_concentration_of_water_vapor_in_air"
        month = GetVariable(ds, "Month")
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            attr_out = convert_units_h2o_lower_gpm3(attr_in, Ta["Data"], ps["Data"], month["Data"])
            variable["Attr"]["rangecheck_lower"] = str(attr_out)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            attr_out = convert_units_h2o_upper_gpm3(attr_in, Ta["Data"], ps["Data"], month["Data"])
            variable["Attr"]["rangecheck_lower"] = str(attr_out)
    elif old_units == "g/m^3" and new_units == "mmol/mol":
        if "Ta" in series_list:
            Ta = GetVariable(ds, "Ta")
        else:
            # if Ta doesn't exist, create it by merging anything that starts with "Ta" or "Tv"
            t_list = [t for t in series_list if t[0:2] in ["Ta", "Tv"]]
            Ta = MergeVariables(ds, "Ta", t_list)
        if "ps" in series_list:
            ps = GetVariable(ds, "ps")
        else:
            # if ps doesn't exist, create it by merging anything that starts with "ps"
            p_list = [p for p in series_list if p[0:2] in ["ps"]]
            ps = MergeVariables(ds, "ps", p_list)
        variable["Data"] = pfp_mf.h2o_mmolpmolfromgpm3(variable["Data"], Ta["Data"], ps["Data"])
        variable["Attr"]["units"] = new_units
        # standard_name for mole fraction of water vapour requires units of "1" not mmol/mol
        # but we use mmol/mol, so standard_name disabled for this quantity
        if "standard_name" in list(variable["Attr"].keys()):
            variable["Attr"].pop("standard_name")
        month = GetVariable(ds, "Month")
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            attr_out = convert_units_h2o_lower_mmolpmol(attr_in, Ta["Data"], ps["Data"], month["Data"])
            variable["Attr"]["rangecheck_lower"] = str(attr_out)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            attr_out = convert_units_h2o_upper_mmolpmol(attr_in, Ta["Data"], ps["Data"], month["Data"])
            variable["Attr"]["rangecheck_lower"] = str(attr_out)
    elif ((old_units == "kg/m^3") and (new_units == "g/m^3")):
        variable["Data"] = variable["Data"] * float(1000)
        variable["Attr"]["units"] = new_units
        # standard_name for mass concentration of water vapour
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mass_concentration_of_water_vapor_in_air"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(1000)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(1000)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif ((old_units == "mmol/m^3") and (new_units == "g/m^3")):
        variable["Data"] = variable["Data"] * float(c.Mv)
        variable["Attr"]["units"] = new_units
        # standard_name for mass concentration of water vapour
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mass_concentration_of_water_vapor_in_air"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(c.Mv)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(c.Mv)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif ((old_units == "g/m^3") and (new_units == "mmol/m^3")):
        variable["Data"] = variable["Data"] / float(c.Mv)
        variable["Attr"]["units"] = new_units
        # standard_name for mole concentration of water vapour
        if variable["Label"][-3:] not in ["_Sd", "_Vr"]:
            variable["Attr"]["standard_name"] = "mole_concentration_of_water_vapor_in_air"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / float(c.Mv)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / float(c.Mv)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif ((old_units in ["frac", "fraction"]) and (new_units in ["%", "percent"])):
        # no change to standard_name
        variable["Data"] = variable["Data"] * float(100)
        variable["Attr"]["units"] = new_units
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(100)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(100)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif ((old_units in ["%", "percent"]) and (new_units in ["frac", "fraction"])):
        # no change to standard_name
        variable["Data"] = variable["Data"] / float(100)
        variable["Attr"]["units"] = new_units
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / float(100)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l / float(100)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    else:
        msg = " Unrecognised conversion from " + old_units + " to " + new_units
        logger.error(msg)
        variable["Data"] = numpy.ma.array(numpy.full(nrecs, c.missing_value))
    return variable

def convert_units_h2o_lower_gpm3(attr_in, Ta, ps, month):
    nrecs = len(Ta)
    limits = parse_rangecheck_limits(attr_in)
    if len(limits) == 1:
        lwr = numpy.ma.array(numpy.full(nrecs, float(limits[0])))
        lwr = pfp_mf.h2o_gpm3frommmolpmol(lwr, Ta, ps)
        attr_out = str(numpy.ma.min(lwr))
    elif len(limits) == 12:
        lwr = numpy.zeros(nrecs)
        attr_list = []
        # set lwr to monthly limits
        for m, l in enumerate(limits):
            idx = numpy.where(month == m+1)[0]
            lwr[idx] = float(l)
            # convert lwr to new units
            lwr[idx] = pfp_mf.h2o_gpm3frommmolpmol(lwr[idx], Ta[idx], ps[idx])
            attr_list.append(numpy.ma.min(lwr[idx]))
        attr_out = ','.join(str(x) for x in attr_list)
    return attr_out

def convert_units_h2o_upper_gpm3(attr_in, Ta, ps, month):
    nrecs = len(Ta)
    limits = parse_rangecheck_limits(attr_in)
    if len(limits) == 1:
        upr = numpy.ma.array(numpy.full(nrecs, float(limits[0])))
        upr = pfp_mf.h2o_gpm3frommmolpmol(upr, Ta, ps)
        attr_out = str(numpy.ma.max(upr))
    elif len(limits) == 12:
        upr = numpy.zeros(nrecs)
        attr_list = []
        # set upr to monthly limits
        for m, l in enumerate(limits):
            idx = numpy.where(month == m+1)[0]
            upr[idx] = float(l)
            # convert upr to new units
            upr[idx] = pfp_mf.h2o_gpm3frommmolpmol(upr[idx], Ta[idx], ps[idx])
            attr_list.append(numpy.ma.max(upr[idx]))
        attr_out = ','.join(str(x) for x in attr_list)
    return attr_out

def convert_units_h2o_lower_mmolpmol(attr_in, Ta, ps, month):
    nrecs = len(Ta)
    limits = parse_rangecheck_limits(attr_in)
    if len(limits) == 1:
        lwr = numpy.ma.array(numpy.full(nrecs, float(limits[0])))
        lwr = pfp_mf.h2o_mmolpmolfromgpm3(lwr, Ta, ps)
        attr_out = str(numpy.ma.min(lwr))
    elif len(limits) == 12:
        lwr = numpy.zeros(nrecs)
        attr_list = []
        # set lwr to monthly limits
        for m, l in enumerate(limits):
            idx = numpy.where(month == m+1)[0]
            lwr[idx] = float(l)
            # convert lwr to new units
            lwr[idx] = pfp_mf.h2o_mmolpmolfromgpm3(lwr[idx], Ta[idx], ps[idx])
            attr_list.append(numpy.ma.min(lwr[idx]))
        attr_out = ','.join(str(x) for x in attr_list)
    return attr_out

def convert_units_h2o_upper_mmolpmol(attr_in, Ta, ps, month):
    nrecs = len(Ta)
    limits = parse_rangecheck_limits(attr_in)
    if len(limits) == 1:
        upr = numpy.ma.array(numpy.full(nrecs, float(limits[0])))
        upr = pfp_mf.h2o_mmolpmolfromgpm3(upr, Ta, ps)
        attr_out = str(numpy.ma.max(upr))
    elif len(limits) == 12:
        upr = numpy.zeros(nrecs)
        attr_list = []
        # set upr to monthly limits
        for m, l in enumerate(limits):
            idx = numpy.where(month == m+1)[0]
            upr[idx] = float(l)
            # convert upr to new units
            upr[idx] = pfp_mf.h2o_mmolpmolfromgpm3(upr[idx], Ta[idx], ps[idx])
            attr_list.append(numpy.ma.max(upr[idx]))
        attr_out = ','.join(str(x) for x in attr_list)
    return attr_out

def convert_units_soil(ds, variable, new_units, sws_info):
    """
    Purpose:
     General purpose routine to convert soil moisture from one set of units
     to another.
     Conversions supported are:
      frac (0 to 1) to percent (0 to 100)
      percent (0 to 100) to frac (0 to 1)
      kg/m^2 to m^3/m^3
     Note: m^3/m^3 is treated as an alias for frac
    Usage:
     new_data = pfp_utils.convert_units_soil(ds, variable, new_units, sws_info)
      where ds is a data structure
            variable is a variable dictionary (pfp_utils.GetVariable())
            new_units (string) is the new units
            sws_info is defined in pfp_utils.convert_units_func()
    Author: PRI
    Date: April 2020 (during the COVID-19 lock down)
    """
    # do the business
    if ((variable["Attr"]["units"] in ["%", "percent"]) and
        (new_units in ["frac", "m^3/m^3"])):
        variable["Data"] = variable["Data"]/float(100)
        variable["Attr"]["units"] = new_units
    elif ((variable["Attr"]["units"] in ["frac", "m^3/m^3"]) and
        (new_units in ["%", "percent"])):
        variable["Data"] = variable["Data"]*float(100)
        variable["Attr"]["units"] = new_units
    elif ((variable["Attr"]["units"] in ["kg/m^2"]) and
        (new_units in ["frac", "m^3/m^3"])):
        variable["Data"] = variable["Data"]/float(100)
        variable["Attr"]["units"] = new_units
    else:
        msg = " Unrecognised conversion from " + variable["Attr"]["units"]
        msg += " to " + new_units
        logger.error(msg)
    return variable

def convert_units_t(ds, variable, new_units, t_info):
    """
    Purpose:
     General purpose routine to convert from one set of temperature units
     to another.
     Conversions supported are:
      degC to K
      K to degC
    Usage:
     new_data = pfp_utils.convert_units_t(ds, variable, new_units)
      where ds is a data structure
            variable is a variable dictionary (pfp_utils.GetVariable())
            new_units (string) is the new units
            t_info is defined in pfp_utils.convert_units_func()
    Author: PRI
    Date: January 2016
    """
    if variable["Attr"]["units"] == "degC" and new_units == "K":
        variable["Data"] = variable["Data"] + c.C2K
        variable["Attr"]["units"] = "K"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l + c.C2K) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l + c.C2K) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif variable["Attr"]["units"] == "K" and new_units == "degC":
        variable["Data"] = variable["Data"] - c.C2K
        variable["Attr"]["units"] = "degC"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l + c.C2K) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l + c.C2K) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    else:
        msg = " Unrecognised conversion from " + variable["Attr"]["units"] + " to " + new_units
        logger.error(msg)
    return variable

def convert_units_ps(ds, variable, new_units, ps_info):
    """
    Purpose:
     General purpose routine to convert from one set of pressure units
     to another.
     Conversions supported are:
      Pa to kPa
      hPa to kPa
    Usage:
     new_data = pfp_utils.convert_units_ps(ds, variable, new_units, ps_info)
      where ds is a data structure
            variable is a variable dictionary (pfp_utils.GetVariable())
            new_units (string) is the new units
            ps_info is defined in pfp_utils.convert_units_func()
    Author: PRI
    Date: February 2018
    """
    if variable["Attr"]["units"] == "Pa" and new_units == "kPa":
        variable["Data"] = variable["Data"]/float(1000)
        variable["Attr"]["units"] = "kPa"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l/float(1000)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l/float(1000)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif variable["Attr"]["units"] == "hPa" and new_units == "kPa":
        variable["Data"] = variable["Data"]/float(10)
        variable["Attr"]["units"] = "kPa"
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l/float(10)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l/float(10)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    elif variable["Attr"]["units"] == "kPa" and new_units == "hPa":
        variable["Data"] = variable["Data"] * float(10)
        variable["Attr"]["units"] = new_units
        if "rangecheck_lower" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_lower"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(10)) for l in limits]
            variable["Attr"]["rangecheck_lower"] = ','.join(str(l) for l in limits)
        if "rangecheck_upper" in variable["Attr"]:
            attr_in = variable["Attr"]["rangecheck_upper"]
            limits = parse_rangecheck_limits(attr_in)
            limits = [(l * float(10)) for l in limits]
            variable["Attr"]["rangecheck_upper"] = ','.join(str(l) for l in limits)
    else:
        msg = " Unrecognised conversion from " + variable["Attr"]["units"] + " to " + new_units
        logger.error(msg)
    return variable

def convert_anglestring(anglestring):
    """
    Purpose:
     Attempt to convert an angle string to a float.
    Usage:
     a = pfp_utils.convert_anglestring(astr)
     Acceptable input formats:
      astr = '''34 12' 24" S'''
      astr = '''34 12 24S'''
      astr = '''34 12'24.123"S''
      astr = '''34.123 S'''
      astr = '''-34.123'''
    """
    quadlist = ["N", "E", "S", "W"]
    direction = {'N':1, 'S':-1, 'E': 1, 'W':-1}
    # replace the degrees, minutes and seconds symbols with spaces
    new = anglestring.replace(r'\B0', ' ').replace('\'', ' ').replace('"', ' ').strip()
    try:
        # simple casting may work, who knows?
        anglefloat = float(new)
    except ValueError:
        try:
            # check there is a space between the quadrant letter (assumed to be one of N, E, W or S)
            # and the next character to the left
            # find out which of N, E, S, or W is in the string
            found_quadletter = False
            for item in quadlist:
                if item in new:
                    found_quadletter = True
                    quadletter = item
            if found_quadletter:
                # now get the index of this character in the string
                i=new.index(quadletter)
                # check that the next character to the left is a space character
                if new[i-1] != " ": new = new[0:i]+" "+new[i:]
                # now split the string on space characters
                new = new.split()
                # get the quadrant letter
                new_dir = new.pop()
                # make sure we have 3 parts
                new.extend([0,0,0])
                anglefloat = (float(new[0])+float(new[1])/60.0+float(new[2])/3600.0) * direction[new_dir]
            else:
                anglefloat = float(c.missing_value)
        except:
            anglefloat = float(c.missing_value)
    # return with the string converted to a float
    return anglefloat

def convert_csv_string_to_list(input_string):
    """ Convert a string containing items separated by commas into a list."""
    input_string = "".join(input_string.split())
    if "," in input_string:
        output_list = input_string.split(",")
    else:
        output_list = [input_string]
    return output_list

def convert_WSWDtoUV(WS, WD):
    """
    Purpose:
     Convert wind speed and direction to U and V conponents.
     This routine follows the meteorological convention:
      - wind direction is positive going clockwise from north
      - U is positive towards east
      - V is positive towards north
    Usage:
     U, V = pfp_utils.convert_WSWDtoUV(WS, WD)
    Author: PRI
    Date: February 2015
    """
    nrecs = len(WS["Data"])
    # create variables of 1s and 0s for QC flags
    f0 = numpy.zeros(nrecs, dtype=numpy.int32)
    f1 = numpy.ones(nrecs, dtype=numpy.int32)
    # create empty variables for U and V
    U = CreateEmptyVariable("u", nrecs)
    V = CreateEmptyVariable("v", nrecs)
    # get the components from the wind speed and direction
    U["Data"] = -WS["Data"]*numpy.sin(numpy.radians(WD["Data"]))
    V["Data"] = -WS["Data"]*numpy.cos(numpy.radians(WD["Data"]))
    # set components to 0 when WS is less than 0.01
    U["Data"] = numpy.ma.where(WS["Data"] < 0.01, numpy.float64(0), U["Data"])
    V["Data"] = numpy.ma.where(WS["Data"] < 0.01, numpy.float64(0), V["Data"])
    # now set the QC flag
    U["Flag"] = numpy.where(numpy.ma.getmaskarray(U["Data"]) == True, f1, f0)
    V["Flag"] = numpy.where(numpy.ma.getmaskarray(V["Data"]) == True, f1, f0)
    # update the variable attributes
    U["Attr"]["long_name"] = "U component of wind velocity, positive east"
    U["Attr"]["units"] = "m/s"
    V["Attr"]["long_name"] = "V component of wind velocity, positive north"
    V["Attr"]["units"] = "m/s"
    # copy the datetime if it is available
    if "DateTime" in list(WS.keys()):
        U["DateTime"] = copy.deepcopy(WS["DateTime"])
        V["DateTime"] = copy.deepcopy(WS["DateTime"])
    elif "DateTime" in list(WD.keys()):
        U["DateTime"] = copy.deepcopy(WD["DateTime"])
        V["DateTime"] = copy.deepcopy(WD["DateTime"])
    return U, V

def convert_UVtoWSWD(U, V):
    """
    Purpose:
     Convert U and V conponents to wind speed and direction
     This routine follows the meteorological convention:
      - wind direction is positive going clockwise from north
      - U is positive towards east
      - V is positive towards north
    Usage:
     WS, WD = pfp_utils.convert_UVtoWSWD(U, V)
    Author: PRI
    Date: February 2015
    """
    nrecs = len(U["Data"])
    # create variables of 1s and 0s for QC flags
    f0 = numpy.zeros(nrecs)
    f1 = numpy.ones(nrecs)
    # create empty variables for WS and WD
    WS = CreateEmptyVariable("Ws", nrecs)
    WD = CreateEmptyVariable("Wd", nrecs)
    # get the wind speed and direction from the components
    WD["Data"] = float(270) - (numpy.degrees(numpy.ma.arctan2(V["Data"], U["Data"])))
    WD["Data"] = numpy.ma.mod(WD["Data"], 360)
    WS["Data"] = numpy.ma.sqrt(U["Data"]*U["Data"] + V["Data"]*V["Data"])
    # mask WD when the WS is less than 0.01
    WD["Data"] = numpy.ma.masked_where(WS["Data"] < 0.01, WD["Data"])
    # now set the QC flag
    WS["Flag"] = numpy.where(numpy.ma.getmaskarray(WS["Data"]) == True, f1, f0)
    WD["Flag"] = numpy.where(numpy.ma.getmaskarray(WD["Data"]) == True, f1, f0)
    # update the variable attributes
    WS["Attr"]["long_name"] = "Wind speed"
    WS["Attr"]["units"] = "m/s"
    WD["Attr"]["long_name"] = "Wind direction"
    WD["Attr"]["units"] = "degrees"
    # copy the datetime if it is available
    if "DateTime" in list(U.keys()):
        WS["DateTime"] = copy.deepcopy(U["DateTime"])
        WD["DateTime"] = copy.deepcopy(U["DateTime"])
    elif "DateTime" in list(V.keys()):
        WS["DateTime"] = copy.deepcopy(V["DateTime"])
        WD["DateTime"] = copy.deepcopy(V["DateTime"])
    return WS, WD

def CopyVariable(var_in):
    """
    Purpose:
     Make a copy of a variable.
    Usage:
     variable_copy = pfp_utils.CopyVariable(variable)
    Author: PRI
    Date: October 2018
          September 2020 - bad Peter, original code returned a view, not a copy
          June 2021 - copy.deepcopy() is slow, we know what should be in var
                      so make use of that knowledge
    """
    if not isinstance(var_in, dict):
        msg = "  CopyVariable: input variable is not a dictionary"
        logger.error(msg)
        raise TypeError(msg)
    var_out = {}
    for item in list(var_in.keys()):
        if isinstance(var_in[item], str):
            var_out[item] = var_in[item]
        elif isinstance(var_in[item], int):
            var_out[item] = var_in[item]
        elif isinstance(var_in[item], float):
            var_out[item] = var_in[item]
        elif isinstance(var_in[item], dict):
            var_out[item] = copy.deepcopy(var_in[item])
        elif isinstance(var_in[item], numpy.ma.core.MaskedArray):
            var_out[item] = var_in[item].copy()
        elif isinstance(var_in[item], numpy.ndarray):
            var_out[item] = var_in[item].copy()
        else:
            msg = "Unrecognised object in variable"
            logger.error(msg)
    return var_out

def CreateDatetimeRange(start,stop,step=datetime.timedelta(minutes=30)):
    '''
    Purpose:
     Create a series of datetimes between the "start" and "stop" datetimes
     and with a time step of "step".
    Useage:
     dt = ds.root["Variables"]['DateTime']['Data']
     ts = ds.root["Attributes"]['time_step']
     dt_evenlyspaced = CreateDatetimeRange(dt[0],dt[-1],step=datetime.timedelta(minutes=ts))]
    Author: PRI
    Date: December 2013
    '''
    result = []
    while start<stop:
        result.append(start)
        start = start + step
    return result

def CreateEmptyVariable(label, nrecs, datetime=None, out_type="ma", attr=None):
    """
    Purpose:
     Returns an empty variable.  Data values are set to -9999, flag values are set to 1
     and default values for the attributes.
    Usage:
     variable = pfp_utils.CreateEmptyVariable(label, nrecs)
     where label is the variable label
           nrecs is the number of elements in the variable data
    Author: PRI
    Date: December 2016
    """
    data = numpy.ones(nrecs, dtype=numpy.float64)*float(c.missing_value)
    if out_type == "ma":
        data = numpy.ma.array(data, mask=True, copy=True)
    flag = numpy.ones(nrecs, dtype=numpy.int32)
    attr_new = make_attribute_dictionary(attr=attr)
    variable = {"Label": label, "Data": data, "Flag": flag, "Attr": attr_new}
    if datetime is None:
        pass
    elif isinstance(datetime, numpy.ndarray):
        if len(datetime) == nrecs:
            variable["DateTime"] = datetime
    elif isinstance(datetime, list):
        if len(datetime) == nrecs:
            variable["DateTime"] = numpy.array(datetime)
    else:
        msg = " Unrecognised type for datetime: " + type(datetime)
        logger.warning(msg)
    return variable

def CreateVariable(ds, var_in, group="root", over_write=True):
    """
    Purpose:
     Create a variable in the data structure.
     If the variable already exists in the data structure, data values, QC flags and
     attributes will be overwritten.
     This utility is the prefered method for creating or updating a data series because
     it implements a consistent method for creating series in the data structure.  Direct
     writes to the contents of the data structure are discouraged (unless PRI wrote the code:=P).
    Usage:
     Fsd = pfp_utils.GetVariable(ds,"Fsd")
      ... do something to Fsd here ...
      ... and don't forget to update the QC flag ...
      ... and the attributes ...
     pfp_utils.CreateVariable(ds,Fsd)
    Author: PRI
    Date: September 2016
    Modifications:
     June 2021 - copy the variable before adding to the data structure otherwise
                 the contents of the input variable will be changed
     July 2022 - added ability to handle groups
    """
    group = getattr(ds, group)
    gvars = group["Variables"]
    variable = CopyVariable(var_in)
    label = variable["Label"]
    labels = sorted(list(group["Variables"]))
    if label in labels and not over_write:
        msg = " Variable " + label + " already exists in data structure, not over written"
        logger.warning(msg)
        return
    # convert masked array to ndarray
    if numpy.ma.isMA(variable["Data"]):
        variable["Data"] = numpy.ma.filled(variable["Data"], float(c.missing_value))
    # coerce to numpy.float64
    if numpy.issubdtype(variable["Data"].dtype, numpy.float64):
        # already float64
        pass
    elif numpy.issubdtype(variable["Data"].dtype, 'O'):
        # datetime series have a dtype of object
        pass
    elif ((numpy.issubdtype(variable["Data"].dtype, numpy.integer)) or
          (numpy.issubdtype(variable["Data"].dtype, numpy.float32))):
        # coerce to float64
        variable["Data"] = numpy.array(variable["Data"], dtype=numpy.float64)
    else:
        msg = " Variable " + label + " has unrecognised dtype " + variable["Data"].dtype
        msg += ", skipping ..."
        logger.error(msg)
        return
    # create the series
    gvars[label] = {"Data": variable["Data"],
                    "Flag": variable["Flag"],
                    "Attr": variable["Attr"]}
    return

def csv_string_to_list(input_string):
    """ Convert a string containing items separated by commas into a list."""
    if "," in input_string:
        output_list = input_string.split(",")
    else:
        output_list = [input_string]
    return output_list

def DeleteVariable(ds, variable):
    """
    Purpose:
     Delete a variable from the data structure.
    Usage:
     Fsd = pfp_utils.GetVariable(ds, Fsd)
     pfp_utils.DeleteVariable(ds, Fsd)
    Author: PRI
    Date: November 2019
    """
    if isinstance(variable, str):
        label = variable
    elif isinstance(variable, dict):
        label = variable["Label"]
    else:
        msg = " DeleteVariable: argument must be a variable dictionary or label"
        logger.warning(msg)
        return
    if label in list(ds.root["Variables"].keys()):
        del ds.root["Variables"][label]
    else:
        msg = " DeleteVariable: variable (" + label + ") not found in data structure"
        logger.warning(msg)
    return

def file_exists(filename, mode="quiet"):
    if not os.path.exists(filename):
        if mode != "quiet":
            logger.error(" File " + filename + " not found")
        return False
    else:
        return True

def find_nearest_value(array, value):
    """
    Purpose:
     pfp_utils.bisection() gives the left bound of the interval of array containing
     value, this function gives the index of the closest value.
    """
    i = bisection(array, value)
    if i < len(array)-1:
        if abs(array[i+1]-value) <= abs(array[i]-value):
            i = i + 1
    return i

def FindMatchingIndices(a, b):
    """
    Purpose:
     Find the indices of elements in a that match elements in b and
     vice versa.
     inds_a - the indices of elements in a that match elements in b
     inds_b - the indices of elements in b that match elements in a
    Usage:
    Side effects:
    Author: PRI but taken from Stackoverflow
    Date: Back in the day.
    """
    a1=numpy.argsort(a)
    b1=numpy.argsort(b)
    # use searchsorted:
    sort_left_a=a[a1].searchsorted(b[b1], side='left')
    sort_right_a=a[a1].searchsorted(b[b1], side='right')
    sort_left_b=b[b1].searchsorted(a[a1], side='left')
    sort_right_b=b[b1].searchsorted(a[a1], side='right')
    # which values of b are also in a?
    inds_b=(sort_right_a-sort_left_a > 0).nonzero()[0]
    # which values of a are also in b?
    inds_a=(sort_right_b-sort_left_b > 0).nonzero()[0]
    return inds_a, inds_b

def RemoveDuplicateRecords(ds):
    """ Remove duplicate records."""
    # the ds.root["Variables"]["DateTime"]["Data"] series is actually a list
    for item in ["DateTime","DateTime_UTC"]:
        if item in list(ds.root["Variables"].keys()):
            ldt = GetVariable(ds, item)
            # ldt_nodups is returned as an ndarray
            ldt_nodups, idx_nodups = numpy.unique(ldt["Data"], return_index=True)
            # and put it back into the data structure
            ds.root["Variables"][item]["Data"] = ldt_nodups
            ds.root["Variables"][item]["Flag"] = ldt["Flag"][idx_nodups]
    # get a list of the series in the data structure
    series_list = [item for item in list(ds.root["Variables"].keys()) if '_QCFlag' not in item]
    # remove the DateTime
    for item in ["DateTime","DateTime_UTC"]:
        if item in series_list: series_list.remove(item)
    # loop over the series in the data structure
    for ThisOne in series_list:
        var = GetVariable(ds, ThisOne)
        var["Data"] = var["Data"][idx_nodups]
        var["Flag"] = var["Flag"][idx_nodups]
        CreateVariable(ds, var)
    ds.root["Attributes"]["nc_nrecs"] = len(ds.root["Variables"]["DateTime"]["Data"])

def FixNonIntegralTimeSteps(ds,fixtimestepmethod=""):
    """
    Purpose:
     Fix time steps that are not an integral number of the default time step.
     The default time step is read from the "time_step" global attribute which is read from
     the L1 control file and written to the L1 netCDF file.
     The most common cause of non-integral time steps is drift in logger time stamp or
     rounding errors in Excel's treatment of datetimes.
    Usage:
     FixNonIntegralTimeSteps(ds)
    Called By: CheckTimeStep
    Author: PRI
    Date: February 2015
    To do:
     Implement [I]nterpolate
    """
    ts = int(float(ds.root["Attributes"]["time_step"]))
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    dt_diffs = numpy.array([(ldt[i]-rounddttots(ldt[i],ts=ts)).total_seconds() for i in range(1,len(ldt))])
    logger.info(" Maximum drift is "+str(numpy.max(dt_diffs))+" seconds, minimum drift is "+str(numpy.min(dt_diffs))+" seconds")
    ans = fixtimestepmethod
    if ans=="": ans = input("Do you want to [Q]uit, [I]nterploate or [R]ound? ")
    if ans.lower()[0]=="q":
        msg = "Quiting ..."
        logger.error(msg)
        sys.exit()
    if ans.lower()[0]=="i":
        msg = "Interpolation to regular time step not implemented yet ..."
        logger.error(msg)
        return
    if ans.lower()[0]=="r":
        logger.info(" Rounding to the nearest time step")
        ldt_rounded = numpy.array([rounddttots(dt,ts=ts) for dt in ldt])
        rdt = numpy.array([(ldt_rounded[i]-ldt_rounded[i-1]).total_seconds() for i in range(1,len(ldt))])
        logger.info(" Maximum time step is now "+str(numpy.max(rdt))+" seconds, minimum time step is now "+str(numpy.min(rdt)))
        # replace the existing datetime series with the datetime series rounded to the nearest time step
        ds.root["Variables"]["DateTime"]["Data"] = ldt_rounded
    ds.root["Attributes"]['nc_nrecs'] = len(ds.root["Variables"]["DateTime"]["Data"])

def FixTimeGaps(ds):
    """
    Purpose:
     Fix gaps in datetime series found by CheckTimeStep.
    Useage:
     has_gaps = CheckTimeStep(ds)
     if has_gaps:
         FixTimeGaps(ds)
    Author: PRI
    Date: April 2013
    Modified:
     September 2014 - rewrite for clarity and efficiency
     February 2015 - and again ...
     July 2021 - rewrite to use GetVariable, CreateEmptyVariable, CreateVariable
                 and FindMatchingIndices
    """
    ts = int(float(ds.root["Attributes"]["time_step"]))
    delta = datetime.timedelta(minutes=ts)
    ldt_gaps = GetVariable(ds, "DateTime")
    # generate a datetime list from the start datetime to the end datetime
    ldt_start = ldt_gaps["Data"][0]
    ldt_end = ldt_gaps["Data"][-1]
    nogaps = numpy.array([dt for dt in perdelta(ldt_start, ldt_end, delta)])
    nRecs = len(nogaps)
    # update the global attribute containing the number of records
    ds.root["Attributes"]['nc_nrecs'] = nRecs
    # create a new (empty) datetime variable
    ldt_nogaps = CreateEmptyVariable("DateTime", nRecs)
    ldt_nogaps["Data"] = nogaps
    ldt_nogaps["Flag"] = numpy.zeros(nRecs, dtype=numpy.int32)
    ldt_nogaps["Attr"] = ldt_gaps["Attr"]
    CreateVariable(ds, ldt_nogaps)
    # find the indices of the no-gap data in the original data
    idx_ainb, idx_bina = FindMatchingIndices(ldt_nogaps["Data"], ldt_gaps["Data"])
    # get a list of series in the data structure
    labels = list(ds.root["Variables"].keys())
    # remove the datetime-related series from data structure
    for label in ["DateTime", "DateTime_UTC"]:
        if label in labels:
            labels.remove(label)
    # now loop over the rest of the series in the data structure
    for label in labels:
        var_gaps = GetVariable(ds, label)
        var_nogaps = CreateEmptyVariable(label, nRecs)
        var_nogaps["Data"][idx_ainb] = var_gaps["Data"][idx_bina]
        var_nogaps["Flag"][idx_ainb] = var_gaps["Flag"][idx_bina]
        var_nogaps["Attr"] = var_gaps["Attr"]
        CreateVariable(ds, var_nogaps)
    return

def FixTimeStep(ds,fixtimestepmethod="round"):
    """
    Purpose:
     Fix problems with the time stamp.
    Useage:
     pfp_utils.FixTimeStep(ds,fixtimestepmethod=fixtimestepmethod)
    Author: PRI
    Date: April 2013
    Modified:
     February 2015 - split check and fix functions into different routines
     July 2021 - tidy up the syntax
    """
    # get the number of records
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    # get the time step
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # time step between records in seconds
    dt = get_timestep(ds)
    dtmin = numpy.min(dt)
    dtmax = numpy.max(dt)
    if dtmin < ts*60:
        # duplicate or overlapping times found
        msg = " FixTimeStep: duplicate or overlapping times found, removing ..."
        logger.info(msg)
        RemoveDuplicateRecords(ds)
        # get the time tep in seconds
        dt = get_timestep(ds)
        # this is how we rounded to nearest int in the good old days ...
        ts_min = int((numpy.min(dt)/60) + 0.5)
        ts_max = int((numpy.max(dt)/60) + 0.5)
        msg = "  After RemoveDuplicateRecords: min ts=" + str(ts_min)
        msg += ", max ts=" + str(ts_max)
        logger.info(msg)
    if ((numpy.min(numpy.mod(dt, ts*60)) != 0) or
        (numpy.max(numpy.mod(dt, ts*60)) != 0)):
        # non-integral time steps found
        # indices of elements where time step not equal to default
        dt_mod = numpy.mod(dt,ts*60)
        index = numpy.where((numpy.min(dt_mod) != 0) or (numpy.max(dt_mod) !=0 ))[0]
        msg = " FixTimeStep: Non-integral time steps found " + str(len(index))
        msg += " times out of " + str(nRecs)
        logger.info(msg)
        msg = " FixTimeStep: Maximum time step was " + str(numpy.max(dt))
        msg += " seconds, minimum time step was " + str(numpy.min(dt))
        logger.info(msg)
        FixNonIntegralTimeSteps(ds,fixtimestepmethod=fixtimestepmethod)
        dt = get_timestep(ds)
        ts_min = int((numpy.min(dt)/60) + 0.5)
        ts_max = int((numpy.max(dt)/60) + 0.5)
        msg = "  After FixNonIntegralTimeSteps: min ts=" + str(ts_min)
        msg += ", max ts=" + str(ts_max)
        logger.info(msg)
    if dtmax > ts*60:
        # time gaps found
        msg = " FixTimeStep: one or more time gaps found, inserting times ..."
        logger.info(msg)
        FixTimeGaps(ds)
        dt = get_timestep(ds)
        ts_min = int((numpy.min(dt)/60) + 0.5)
        ts_max = int((numpy.max(dt)/60) + 0.5)
        msg = "  After FixTimeGaps: min ts=" + str(ts_min) + ", max ts=" + str(ts_max)
        logger.info(msg)

def GetAverageSeriesKeys(cf, label, section="Variables"):
    """
    Purpose:
     Get the AverageSeries Source key from the control file.
    Usage:
    Author: PRI
    Date: Back in the day
    """
    if len(section)==0:
        section = "Variables"
    src_list = []
    got_source = False
    for key in list(cf[section][label]['AverageSeries'].keys()):
        if key.lower() == "source":
            got_source = True
            src_string = cf[section][label]['AverageSeries'][key]
            if "," in src_string:
                src_list = src_string.split(",")
            else:
                src_list = [src_string]
    if not got_source:
        msg = "  GetAverageSeriesKeys: "
        msg += "key 'source' not in control file AverageSeries section for " + label
        logger.error()
    return src_list

def GetcbTicksFromCF(cf,ThisOne):
    '''
    Get colour bar tick labels from the control file.
    '''
    if ThisOne in list(cf['Variables'].keys()):
        if 'Ticks' in list(cf['Variables'][ThisOne].keys()):
            Ticks = eval(cf['Variables'][ThisOne]['Ticks'])
        else:
            msg = 'GetcbTicksFromCF: Ticks key not in control file for '+str(ThisOne)
            logger.warning(msg)
    else:
        msg = 'GetcbTicksFromCF: '+str(ThisOne)+' not in control file'
        logger.warning(msg)
    return Ticks

def GetRangesFromCF(cf,ThisOne, mode="verbose"):
    '''
    Get lower and upper range limits from the control file.
    '''
    if ThisOne in list(cf['Variables'].keys()):
        if 'lower' in list(cf['Variables'][ThisOne].keys()):
            lower = float(cf['Variables'][ThisOne]['lower'])
        else:
            if mode.lower()!="quiet":
                msg = "GetRangesFromCF: lower key not in control file for "+str(ThisOne)
                logger.info(msg)
            lower = None
        if 'upper' in list(cf['Variables'][ThisOne].keys()):
            upper = float(cf['Variables'][ThisOne]['upper'])
        else:
            if mode.lower()!="quiet":
                msg = "GetRangesFromCF: upper key not in control file for "+str(ThisOne)
                logger.info(msg)
            upper = None
    else:
        if mode.lower()!="quiet":
            msg = "GetRangesFromCF: "+str(ThisOne)+" not in control file"
            logger.info(msg)
        lower, upper = None
    return lower, upper

def GetDateIndex(ldt, date, ts=30, default=0, match='exact'):
    """
    Purpose:
     Return the index of a date/datetime string in an array of datetime objects
    Usage:
     si = pfp_utils.GetDateIndex(ldt,date_str,ts=30,default=0,match='exact')
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
    if (isinstance(date, numbers.Number)):
        i = date
    elif isinstance(date, str):
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

def GetGlobalAttributeValue(cf,ds,ThisOne):
    if ThisOne not in list(ds.root["Attributes"].keys()):
        if ThisOne in list(cf['General'].keys()):
            ds.root["Attributes"][ThisOne] = cf['General'][ThisOne]
        else:
            logger.error('  GetGlobalAttributeValue: global attribute '+ThisOne+' was not found in the netCDF file or in the control file')
            ds.root["Attributes"][ThisOne] = None
    return ds.root["Attributes"][ThisOne]

def GetMergeSeriesKeys(cf, ThisOne, section="Variables"):
    """
    Purpose:
     Get the MergeSeries Source key from the contro file.
    Usage:
    Author: PRI
    Date: Back in the day
    """
    if len(section)==0:
        section = 'Variables'
    src_list = []
    got_source = False
    for key in list(cf[section][ThisOne]['MergeSeries'].keys()):
        if key.lower() == "source":
            got_source = True
            src_string = cf[section][ThisOne]['MergeSeries'][key]
            if "," in src_string:
                src_list = src_string.split(",")
            else:
                src_list = [src_string]
    if not got_source:
        msg = "  GetMergeSeriesKeys: "
        msg += "key 'source' not in control file MergeSeries section for " + ThisOne
        logger.error(msg)
    return src_list

def GetPlotTitleFromCF(cf, nFig):
    if 'Plots' in cf:
        if str(nFig) in cf['Plots']:
            if 'Title' in cf['Plots'][str(nFig)]:
                Title = str(cf['Plots'][str(nFig)]['Title'])
            else:
                msg = 'GetPlotTitleFromCF: Variables key not in control file for plot '+str(nFig)
                logger.warning(msg)
        else:
            msg = 'GetPlotTitleFromCF: '+str(nFig)+' key not in Plots section of control file'
            logger.warning(msg)
    else:
        msg = 'GetPlotTitleFromCF: Plots key not in control file'
        logger.warning(msg)
    return Title

def GetPlotVariableNamesFromCF(cf, n):
    if 'Plots' in cf:
        if str(n) in cf['Plots']:
            if 'Variables' in cf['Plots'][str(n)]:
                SeriesList = eval(cf['Plots'][str(n)]['Variables'])
            else:
                msg = 'GetPlotVariableNamesFromCF: Variables key not in control file for plot '+str(n)
                logger.warning(msg)
        else:
            msg = 'GetPlotVariableNamesFromCF: '+str(n)+' key not in Plots section of control file'
            logger.warning(msg)
    else:
        msg = 'GetPlotVariableNamesFromCF: Plots key not in control file'
        logger.warning(msg)
    return SeriesList

def GetSeries(ds, label, group="root", out_type="ma"):
    """
    Purpose:
     Return the data, flag and attributes of a variable in the data structure.
     This is a rewrite of the original to handle data structures with groups.
    Usage:
    Side effects:
    Author: PRI
    Date: July 2022
    Modifications:
    """
    gvars = getattr(ds, group)["Variables"]
    gattr = getattr(ds, group)["Attributes"]
    nrecs = int(float(gattr["nc_nrecs"]))
    # check the series requested is in the data structure
    labels = sorted(list(gvars.keys()))
    if label in labels:
        data = gvars[label]["Data"].copy()
        flag = gvars[label]["Flag"].copy()
        attr = copy.deepcopy(gvars[label]["Attr"])
    else:
        # tell the user we can't find the series
        msg = " GetSeries: " + label + " not found, creating empty series ..."
        logger.error(msg)
        data = numpy.full(nrecs, c.missing_value, dtype=numpy.float64)
        flag = numpy.ones(nrecs, dtype=numpy.int32)
        attr = {"long_name": "", "units": "", "statistic_type": "average"}
    # check to see what kind of output the user wants
    if isinstance(data, numpy.ndarray) and out_type == "ma":
        # convert to a masked array
        data = numpy.ma.masked_values(data, c.missing_value)
    elif isinstance(data, numpy.ndarray) and out_type == "nan":
        # leave as ndarray, convert c.missing_value to NaN
        data = numpy.where(data == c.missing_value, numpy.nan, data)
    elif isinstance(data, numpy.ndarray) and int(float(out_type)) == c.missing_value:
        # leave as ndarray, leave c.missing_value
        pass
    elif isinstance(data, numpy.ndarray) and numpy.isfinite(float(out_type)):
        # user specified missing data code
        data = numpy.where(data == c.missing_value, float(out_type), data)
    else:
        # default is masked array
        data = numpy.ma.masked_values(data, c.missing_value)
    return data, flag, attr

def MakeEmptySeries(ds, ThisOne):
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    Series = float(c.missing_value)*numpy.ones(nRecs, dtype=numpy.float64)
    Flag = numpy.ones(nRecs, dtype=numpy.int32)
    Attr = make_attribute_dictionary()
    return Series, Flag, Attr

def GetVariable(ds, label, group="root", start=0, end=-1, mode="truncate", out_type="ma", match="exact"):
    """
    Purpose:
     Returns a data variable from the data structure as a dictionary.
     This is a rewrite of the original to handle data structures with groups.
    Usage:
     variable = pfp_utils.GetVariable(ds, label)
    Required arguments are;
      ds    - the data structure (class)
      label - label of the data variable in ds (string)
    Optional arguments are;
      start - start date or index (integer), default 0
      end   - end date or index (integer), default -1
      mode  - truncate or pad the data
      out_type - masked array or ndarray
      match    - type of datetime match options are:
                "exact" - finds the specified datetime and returns the index
                "wholehours" - finds the start of the first whole hour and end of
                               the last whole hour
                "wholedays" - finds the start of the first whole day and end of
                               the last whole day
                "wholemonths" - finds the start of the first whole month and end of
                               the last whole month
     This function returns a variable as a dictionary;
      variable["Label"] - variable label in data structure
      variable["Data"] - numpy float64 masked array containing data
      variable["Flag"] - numpy int32 array containing QC flags
      variable["Attr"] - dictionary of variable attributes
      variable["DateTime"] - datetimes of the data
    Example:
     The code snippet below will return the incoming shortwave data values
     (Fsd), the associated QC flag and the variable attributes;
      ds = pfp_io.nc_read_series("HowardSprings_2011_L3.nc")
      Fsd = pfp_utils.GetVariable(ds, "Fsd")
    Author: PRI
    """
    gvars = getattr(ds, group)["Variables"]
    gattr = getattr(ds, group)["Attributes"]
    dt = gvars["DateTime"]["Data"]
    # get the data, flag and attributes for this variable from the data structure
    data, flag, attr = GetSeries(ds, label, group=group, out_type=out_type)

    nrecs = int(float(gattr["nc_nrecs"]))
    ts = gattr["time_step"]
    if ts in ["daily", "monthly", "annual"]:
        # convert datetime to date
        dt = numpy.array([d.date() for d in dt])
        # we only handle specific cases of start and end
        if (isinstance(start, numbers.Number) and isinstance(end, numbers.Number) and
            end > start):
            # start and end are both numbers so use them as indices
            dt = dt[start:end+1]
            data = data[start:end+1]
            flag = flag[start:end+1]
        elif (isinstance(start, str) and isinstance(end, str)):
            # start and end are both strings
            start = dateutil.parser.parse(start)
            end = dateutil.parser.parse(end)
            if (end > start):
                idx = numpy.where((dt >= start.date()) & (dt <= end.date()))[0]
                dt = dt[idx]
                data = data[idx]
                flag = flag[idx]
        elif (isinstance(start, datetime.date) and isinstance(end, datetime.date) and
              end > start):
            # start and end are both dates
            idx = numpy.where((dt >= start.date()) & (dt <= end.date()))[0]
            dt = dt[idx]
            data = data[idx]
            flag = flag[idx]
        else:
            pass
    else:
        ts = int(float(ts))
        match_options = {"start": {"exact": "exact",
                                   "wholehours": "startnexthour",
                                   "wholedays": "startnextday",
                                   "wholemonths": "startnextmonth"},
                         "end": {"exact": "exact",
                                 "wholehours": "endprevioushour",
                                 "wholedays": "endpreviousday",
                                 "wholemonths": "endpreviousmonth"}}
        si = GetDateIndex(dt, start, ts=ts, default=0, match=match_options["start"][match])
        if end == -1: end = nrecs-1
        ei = GetDateIndex(dt, end, ts=ts, default=nrecs-1, match=match_options["end"][match])
        if mode == "truncate":
            # truncate to the requested start and end indices
            data = get_variable_truncate(data, nrecs, si, ei)
            flag = get_variable_truncate(flag, nrecs, si, ei)
            dt = get_variable_truncate(dt, nrecs, si, ei)
        elif mode == "mirror":
            data = get_variable_mirror(data, nrecs, si, ei)
            flag = get_variable_mirror(flag, nrecs, si, ei)
            start = dt[0] + datetime.timedelta(minutes=int(si*ts))
            end = dt[0] + datetime.timedelta(minutes=int((ei-1)*ts))
            ts_delta = datetime.timedelta(minutes=ts)
            dt = numpy.array([d for d in perdelta(start, end, ts_delta)])
        else:
            msg = "  Unsupported mode (" + str(mode) + "), must be 'truncate' or 'mirror'"
            logger.error(msg)
    # assemble the variable dictionary
    variable = {"Label": label, "Data": data, "Flag": flag, "Attr": attr,
                "DateTime": dt, "time_step": ts}
    # make sure there is a value for the long_name attribute
    if "long_name" not in variable["Attr"]:
        variable["Attr"]["long_name"] = label
    return variable

def GetUnitsFromds(ds, ThisOne):
    units = ds.root["Variables"][ThisOne]['Attr']['units']
    return units

def get_base_path():
    """
    Purpose:
     Return the base path dependng on whether we are running as a script
     or a Pyinstaller application.
    Author: https://stackoverflow.com/questions/7674790/bundling-data-files-with-pyinstaller-onefile
    """
    # check if we running as a PyInstaller application
    if getattr(sys, 'frozen', False):
        # running as a PyInstaller application
        base_path = sys._MEIPASS
    else:
        # running as a script
        base_path = os.path.abspath(".")
    return base_path

def get_cfsection(cf, label, mode='quiet'):
    '''
    Find the section in the control file that contains an entry for the series "series".
    USEAGE:  section = pfp_utils.get_cfsection(cf, label)
    INPUT:   cf      - a control file object (from ConfigObj)
             label   - the name of the series (string)
    RETURNS: section - the name of the section containing an entry for <series_name> (string)
    Note that the returned section name is an empty string if there is no entry for <series_name> in
    the control file.
    '''
    got_section = False
    sections = list(cf.keys())
    for section in ["level", "controlfile_name", "Files", "Global", "Options",
                    "Soil", "Massman", "GUI", "ustar_threshold", "Plots"]:
        if section in sections:
            sections.remove(section)
    for section in sections:
        if label in cf[section]:
            got_section = True
            return section
    if not got_section:
        msg = " get_cfsection: variable " + str(label) + " not found in control file"
        if mode != "quiet":
            logger.warning(msg)
    return None

def get_coverage_groups(ds,rad=None,met=None,flux=None,soil=None):
    level = "L1"
    if "processing_level" in ds.root["Attributes"]:
        level = str(ds.root["Attributes"]["processing_level"])
    rad = ['Fsd','Fsu','Fld','Flu','Fn']
    met = ['AH','CO2','Precip','ps','Ta','Ws','Wd']
    flux = ['Fm','ustar','Fh','Fe','Fco2']
    soil = ['Fg','Ts','Sws']
    for ThisGroup, ThisLabel in zip([rad,met,flux,soil],['radiation','meteorology','flux','soil']):
        sum_coverage = float(0); count = float(0)
        for ThisOne in ThisGroup:
            if ThisOne in list(ds.root["Variables"].keys()):
                coverage_level = strip_non_numeric(ds.root["Variables"][ThisOne]['Attr']['coverage_'+level])
                sum_coverage = sum_coverage + float(coverage_level)
                count = count + 1
        if count!=0:
            coverage_group = sum_coverage/count
        else:
            coverage_group = 0
        ds.root["Attributes"]['coverage_'+ThisLabel+'_'+level] = str('%d'%coverage_group) + "%"

def get_coverage_individual(ds):
    level = "L1"
    if "processing_level" in ds.root["Attributes"]:
        level = str(ds.root["Attributes"]["processing_level"])
    SeriesList = list(ds.root["Variables"].keys())
    for ThisOne in ["DateTime","DateTime_UTC"]:
        if ThisOne in SeriesList: SeriesList.remove(ThisOne)
    for ThisOne in SeriesList:
        num_good = len(numpy.where(abs(ds.root["Variables"][ThisOne]['Data']-float(c.missing_value))>c.eps)[0])
        coverage = 100*float(num_good)/float(ds.root["Attributes"]['nc_nrecs'])
        ds.root["Variables"][ThisOne]['Attr']['coverage_'+level] = str('%d'%coverage) + "%"

def get_datetime_from_nctime(ds):
    """
    Purpose:
     Create a series of datetime objects from the time read from a netCDF file.
    Usage:
     pfp_utils.get_datetimefromnctime(ds,time,time_units)
    Side effects:
     Creates a Python datetime series in the data structure
    Author: PRI
    Date: September 2014
    """
    time_step = ds.root["Attributes"]["time_step"]
    nc_time_data = ds.root["Variables"]["time"]["Data"]
    nc_time_units = ds.root["Variables"]["time"]["Attr"]["units"]
    # 20210912 PRI - deprecate num2pydate as part of SegFault testing
    # 20250516 PRI - revet to using cftime
    # 20250516 PRI - note that cftime.num2pydate() now returns real_datetime object
    dt = cftime.num2pydate(nc_time_data, nc_time_units)
    if time_step in ["daily", "monthly", "annual"]:
        dt = numpy.array(dt)
    else:
        time_step = int(float(time_step))
        dt = numpy.array([rounddttots(ldt, time_step) for ldt in dt])
    calendar = "gregorian"
    if "calendar" in ds.root["Variables"]["time"]["Attr"]:
        calendar = ds.root["Variables"]["time"]["Attr"]["calendar"]
    pydt = {"Label": "DateTime", "Data": dt, "Flag": numpy.zeros(len(dt)),
            "Attr": {"long_name": "Datetime in local timezone", "units": "",
                     "calendar": calendar}}
    CreateVariable(ds, pydt)
    return

def get_datetime_from_excel_date(values, xl_datemode):
    values = numpy.array(values)
    xl_date = values + 1462*int(xl_datemode)
    base_date = datetime.datetime(1899, 12, 30)
    dt = [base_date + datetime.timedelta(days=xl_date[i]) for i in range(len(values))]
    return numpy.ma.array(dt, copy=True)

def get_datetime_from_xldatetime(ds):
    ''' Creates a series of Python datetime objects from the Excel date read from the Excel file.
        Thanks to John Machin for the quick and dirty code
         see http://stackoverflow.com/questions/1108428/how-do-i-read-a-date-in-excel-format-in-python'''

    logger.info(' Getting the Python datetime series from the Excel datetime')
    xldate = ds.root["Variables"]['xlDateTime']['Data']
    nRecs = len(ds.root["Variables"]['xlDateTime']['Data'])
    datemode = int(ds.root["Attributes"]['xl_datemode'])
    ds.root["Variables"][str('DateTime')] = {}
    basedate = datetime.datetime(1899, 12, 30)
    dt = [None]*nRecs
    for i in range(nRecs):
        dt[i] = basedate + datetime.timedelta(days=xldate[i] + 1462 * datemode)
    ds.root["Variables"]['DateTime']['Data'] = numpy.array(dt)
    ds.root["Variables"]['DateTime']['Flag'] = numpy.zeros(nRecs)
    ds.root["Variables"]['DateTime']['Attr'] = {}
    ds.root["Variables"]['DateTime']['Attr']['long_name'] = 'Datetime in local timezone'
    ds.root["Variables"]['DateTime']['Attr']['units'] = 'None'
    ds.root["Variables"]['DateTime']['Attr']['calendar'] = 'gregorian'
    return

def get_datetime_from_ymdhms(ds):
    ''' Creates a series of Python datetime objects from the year, month,
    day, hour, minute and second series stored in the netCDF file.'''
    SeriesList = list(ds.root["Variables"].keys())
    if ('Year' not in SeriesList or 'Month' not in SeriesList or 'Day' not in SeriesList or
        'Hour' not in SeriesList or 'Minute' not in SeriesList or 'Second' not in SeriesList):
        logger.info(' get_datetime_from_ymdhms: unable to find all datetime fields required')
        return
    logger.info(' Getting the date and time series')
    #pdb.set_trace()
    year = ds.root["Variables"]["Year"]["Data"].astype('int')
    month = ds.root["Variables"]["Month"]["Data"].astype('int')
    day = ds.root["Variables"]["Day"]["Data"].astype('int')
    hour = ds.root["Variables"]["Hour"]["Data"].astype('int')
    minute = ds.root["Variables"]["Minute"]["Data"].astype('int')
    second = ds.root["Variables"]["Second"]["Data"].astype('int')
    dt = [datetime.datetime(yr,mn,dy,hr,mi,se) for yr,mn,dy,hr,mi,se in zip(year,month,day,hour,minute,second)]
    ds.root["Variables"]["DateTime"] = {}
    ds.root["Variables"]["DateTime"]["Data"] = numpy.array(dt)
    ds.root["Variables"]["DateTime"]["Flag"] = numpy.zeros(len(dt))
    ds.root["Variables"]["DateTime"]["Attr"] = {}
    ds.root["Variables"]["DateTime"]["Attr"]["long_name"] = "Datetime in local timezone"
    ds.root["Variables"]["DateTime"]["Attr"]["units"] = "None"
    ds.root["Variables"]['DateTime']['Attr']['calendar'] = "gregorian"
    return

def get_ddoy_from_datetime(dt):
    """ Return the decimal day of the year from a datetime."""
    ddoy = dt.timetuple().tm_yday + float(dt.hour+float(dt.minute+float(dt.second)/60)/60)/24
    return ddoy

def get_diurnalstats(dt,data,info):
    ts = info["time_step"]
    nperday = info["nperday"]
    si = 0
    while abs(dt[si].hour+float(dt[si].minute)/60-float(ts)/60)>c.eps:
        si = si + 1
    ei = len(dt)-1
    while abs(dt[ei].hour+float(dt[ei].minute)/60)>c.eps:
        ei = ei - 1
    data_wholedays = data[si:ei+1]
    ndays = len(data_wholedays)//nperday
    data_2d = numpy.ma.reshape(data_wholedays,[ndays,nperday])
    diel_stats = {}
    diel_stats["Hr"] = numpy.ma.array([i*ts/float(60) for i in range(0,nperday)], copy=True)
    diel_stats["Av"] = numpy.ma.average(data_2d,axis=0)
    diel_stats["Sd"] = numpy.ma.std(data_2d,axis=0)
    diel_stats["Mx"] = numpy.ma.max(data_2d,axis=0)
    diel_stats["Mn"] = numpy.ma.min(data_2d,axis=0)
    diel_stats["Number"] = numpy.ma.count(data_2d,axis=0)
    return diel_stats

def get_end_index(ldt, end, default=-1, mode="quiet"):
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
                    msg = "Requested end date not found"
                    logger.warning(msg)
                ei = default
        except ValueError:
            if mode == "verbose":
                msg = "Error parsing end date string"
                logger.warning(msg)
            ei = default
    elif isinstance(end, datetime.datetime):
        if end >= ldt[0] and end <= ldt[-1]:
            ei = numpy.where(ldt == end)[0][0]
        else:
            if mode == "verbose":
                msg = "Requested end date not found"
                logger.warning(msg)
            ei = default
    elif (isinstance(end, numbers.Number)):
        ei = min([int(end), len(ldt)])
    else:
        if mode == "verbose":
            msg = "Unrecognised type for end date"
            logger.warning(msg)
        ei = default
    return ei

def get_executable_suffix():
    """ Returns the executable suffix based on operating system and architecture."""
    if platform.system() in ["Windows"]:
        if platform.machine() in ["i386", "AMD64", "x86_64"]:
            executable_suffix = ".exe"
        else:
            msg = "Unrecgnised architecture for Windows"
            raise RuntimeError(msg)
    elif platform.system() in ["Darwin"]:
        if platform.machine() in ["arm64"]:
            executable_suffix = "_arm64"
        elif platform.machine() in ["x86_64"]:
            executable_suffix = "_x86_64"
        else:
            msg = "Unrecognised architecture for macOS"
            raise RuntimeError(msg)
    elif platform.system() in ["Linux"]:
        executable_suffix = ""
    else:
        msg = "Unrecognised operating system"
        raise RuntimeError(msg)
    return executable_suffix

def get_keyvaluefromcf(cf,sections,key,default=None,mode="quiet"):
    """
    Purpose:
     General return a keyword value from a control file.
    Usage:
     keyval = pfp_utils.get_keyvaluefromcf(cf,sections,key,default=default)
     where
      cf is a control file object from ConfigObj
      sections is a list of sections and nested sub-sections to search
      key is the keyword
      default is a default value
    Example:
     ncOutFileName = pfp_utils.get_keyvaluefromcf(cf,["Files","Out"],"ncFileName",default="")
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

def get_label_list_from_cf(cf):
    """
    Purpose:
     Returns a list of variable labels from a control file.
    Usage:
     label_list = pfp_utils.get_label_list_from_cf(cf)
     where cf is a control file object
           label_list is a list of variable labels referenced in the control file.
    """
    if "Variables" in cf:
        label_list = list(cf["Variables"].keys())
    elif "Drivers" in cf:
        label_list = list(cf["Drivers"].keys())
    elif "Fluxes" in cf:
        label_list = list(cf["Fluxes"].keys())
    else:
        label_list = []
        msg = "No Variables, Drivers or Fluxes section found in control file"
        logger.error(msg)
    return label_list

def get_missingingapfilledseries(ds, l4_info):
    """
    Purpose:
     Check series in data structure and print a message to the screen if missing points are found.
    Usage:
     gfalternate_checkformissing(ds,series_list=series_list)
      where ds is a data structure
            series_list is a list of series to check
    Author: PRI
    Date: March 2015
    """
    # create an empty list
    alt_list = []
    # check to see if there was any gap filling using data from alternate sources
    if "GapFillFromAlternate" in list(l4_info.keys()):
        l4a = l4_info["GapFillFromAlternate"]
        # if so, get a list of the quantities gap filled from alternate sources
        alt_list = list(set([l4a["outputs"][item]["target"] for item in list(l4a["outputs"].keys())]))
    # create an empty list
    cli_list = []
    # check to see if there was any gap filling from climatology
    if "GapFillFromClimatology" in list(l4_info.keys()):
        l4c = l4_info["GapFillFromClimatology"]
        # if so, get a list of the quantities gap filled using climatology
        cli_list = list(set([l4c["outputs"][item]["target"] for item in list(l4c["outputs"].keys())]))
    # one list to rule them, one list to bind them ...
    gf_list = list(set(alt_list + cli_list))
    # clear out if there was no gap filling
    if len(gf_list) == 0:
        return
    # loop over the series to be checked
    gap_found = False
    for series in gf_list:
        if series not in list(ds.root["Variables"].keys()): continue
        var = GetVariable(ds, series)
        idx = numpy.ma.where(numpy.ma.getmaskarray(var["Data"]) == True)[0]
        if len(idx) != 0:
            gap_found = True
            msg = " Missing points ("+str(len(idx))+") found in "+series
            logger.error(msg)
    if not gap_found:
        msg = " No missing values found in gap filled series"
        logger.info(msg)
    return

def get_number_from_heightstring(height):
    z = str(height)
    if "m" in z: z = z.replace("m","")
    try:
        z = float(z)
    except:
        z = None
    return z

def get_nctime_from_datetime(ds):
    """
    Purpose:
     Generate a time series in the supplied units from the datetime objects stored
     in the data structure ds.
     The time variable is in units of days since 1800-01-01 00:00:00.0.
    Usage:
     get_nctime_from_datetime(ds)
     where ds is a data structure (data_structure)
    Author: PRI
    Date: October 2017
    """
    # 20210913 PRI - replace netCDF4.date2num() to fix SegFaults
    #ldt = ds.root["Variables"]["DateTime"]["Data"]
    #data = netCDF4.date2num(ldt, time_units, calendar=calendar)
    nc_time_units = "days since 1800-01-01 00:00:00.0"
    epoch_start = dateutil.parser.parse(nc_time_units, fuzzy=True)
    ldt = GetVariable(ds, "DateTime")
    epoch_start_date = datetime.datetime(epoch_start.year, epoch_start.month, epoch_start.day,
                                         epoch_start.hour, epoch_start.minute, epoch_start.second)
    data = numpy.array([(t-epoch_start_date).days+(t-epoch_start_date).seconds/86400
                        for t in ldt["Data"]])
    flag = numpy.zeros(len(data))
    attr = {"calendar": "gregorian", "long_name": "time", "standard_name": "time",
            "units": nc_time_units}
    variable = {"Label": "time", "Data": data, "Flag": flag, "Attr": attr}
    CreateVariable(ds, variable)
    return

def get_nctime_from_datetime_data(dt, nc_time_units="days since 1800-01-01 00:00:00.0"):
    """
    Purpose:
     Generate a time series in the supplied units from the datetime objects stored
     in the data structure ds.
     The time variable is in units of days since 1800-01-01 00:00:00.0.
    Usage:
     get_nctime_from_datetime_data(dt)
     where dt is an array of datetimes
    Author: PRI
    Date: September 2021
    """
    epoch_start = dateutil.parser.parse(nc_time_units, fuzzy=True)
    epoch_start_date = datetime.datetime(epoch_start.year, epoch_start.month, epoch_start.day,
                                         epoch_start.hour, epoch_start.minute, epoch_start.second)
    data = [(t-epoch_start_date).days+(t-epoch_start_date).seconds/86400 for t in dt]
    return numpy.array(data)

def get_nrecs(ds):
    if 'nc_nrecs' in list(ds.root["Attributes"].keys()):
        nRecs = int(ds.root["Attributes"]['nc_nrecs'])
    elif 'NumRecs' in list(ds.root["Attributes"].keys()):
        nRecs = int(ds.root["Attributes"]['NumRecs'])
    else:
        series_list = list(ds.root["Variables"].keys())
        nRecs = len(ds.root["Variables"][series_list[0]]['Data'])
    return nRecs

def get_start_index(ldt, start, default=None, mode="quiet"):
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
                    msg = "Requested start date not found"
                    logger.warning(msg)
                si = default
        except ValueError:
            if mode == "verbose":
                msg = "Error parsing start date string"
                logger.warning(msg)
            si = default
    elif isinstance(start, datetime.datetime):
        if start >= ldt[0] and start <= ldt[-1]:
            si = numpy.where(ldt == start)[0][0]
        else:
            if mode == "verbose":
                msg = "Requested start date not found"
                logger.warning(msg)
            si = default
    elif (isinstance(start, numbers.Number)):
        si = max([0, int(start)])
    else:
        if mode == "verbose":
            msg = "Unrecognised type for start"
            logger.warning(msg)
        si = default
    return si

def get_timestep(ds):
    """
    Purpose:
     Return an array of time steps in seconds between records
    Useage:
     dt = pfp_utils.get_timestep(ds)
    Author: PRI
    Date: February 2015
    """
    # local pointer to the Python datetime series
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    # time step between records in seconds
    dt = numpy.array([(ldt[i]-ldt[i-1]).total_seconds() for i in range(1,len(ldt))])
    return dt

def get_timezone(site_name,prompt="no"):
    """ Return the time zone based on the site name."""
    time_zone = ""
    found = False
    # strip out spaces and commas from the site name
    site_name = site_name.replace(" ","").replace(",","")
    for item in list(c.tz_dict.keys()):
        if item in site_name.lower():
            time_zone = c.tz_dict[item]
            found = True
    return time_zone,found

def get_utc_offset(ldt, time_zone):
    pytz_time_zone = pytz.timezone(time_zone)
    utc_offset = pytz_time_zone.utcoffset(ldt)
    dst = pytz_time_zone.dst(ldt)
    standard_offset = utc_offset - dst
    return {"utc_offset": utc_offset, "standard_offset": standard_offset}

def get_UTCfromlocaltime(ds):
    '''
    Purpose:
     Creates a UTC datetime series in the data structure from the
     local datetime series.
    Usage:
     ldt_UTC = pfp_utils.get_UTCfromlocaltime(ds)
    Assumptions:
     No daylight savings used in the local datetime
    Author: PRI
    '''
    # check the time_zone global attribute is set, we cant continue without it
    if "time_zone" not in list(ds.root["Attributes"].keys()):
        logger.warning("get_UTCfromlocaltime: time_zone not in global attributes, checking elsewhere ...")
        if "site_name" in list(ds.root["Attributes"].keys()):
            site_name = ds.root["Attributes"]["site_name"]
        else:
            logger.warning("get_UTCfromlocaltime: site_name not in global attributes, skipping UTC calculation ...")
            return
        time_zone,found = get_timezone(site_name,prompt="no")
        if not found:
            logger.warning("get_UTCfromlocaltime: site_name not in time zone dictionary")
            return
        else:
            logger.info("get_UTCfromlocaltime: time_zone found in time zone dictionary")
            ds.root["Attributes"]["time_zone"] = time_zone
    logger.info(' Getting the UTC datetime from the local datetime')
    # get the time zone
    tz = ds.root["Attributes"]["time_zone"]
    # create a timezone object
    loc_tz = pytz.timezone(tz)
    # local pointer to the datetime series in ds
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    # localise the datetime by assigning a time zone
    ldt_loc = [loc_tz.localize(dt) for dt in ldt]
    # remove any daylight saving time
    ldt_loc_nodst = [dt+dt.dst() for dt in ldt_loc]
    # convert to UTC
    ldt_utc = [dt.astimezone(pytz.utc) for dt in ldt_loc_nodst]
    return ldt_utc

def get_variable_mirror(data, nrecs, si, ei):
    was_ma = False
    if numpy.ma.isMA(data):
        was_ma = True
        data = numpy.ma.filled(data, fill_value=c.missing_value)
    # reflect data about end boundaries if si or ei are out of bounds
    if si < 0 and ei > nrecs-1:
        # mirror at the start
        data = numpy.append(numpy.fliplr([data[1:abs(si)+1]])[0], data)
        # mirror at the end
        sim = 2*nrecs-1-ei
        eim = nrecs-1
        data = numpy.append(data, numpy.fliplr([data[sim:eim]])[0])
    elif si < 0 and ei <= nrecs-1:
        # mirror at start, truncate at end
        data = numpy.append(numpy.fliplr([data[1:abs(si)+1]])[0], data[:ei+1])
    elif si >= 0 and ei > nrecs-1:
        # truncate at start, mirror at end
        sim = 2*nrecs-1-ei
        eim = nrecs
        data = numpy.append(data[si:], numpy.fliplr([data[sim:eim]])[0])
    elif si >= 0 and ei <= nrecs-1:
        # truncate at the start and end
        data = data[si:ei+1]
    else:
        msg = 'GetSeries: unrecognised combination of si ('+str(si)+') and ei ('+str(ei)+')'
        raise ValueError(msg)
    if was_ma:
        data = numpy.ma.masked_values(data, c.missing_value)
    return data

def get_variable_truncate(data, nrecs, si, ei):
    return data[max(0, si): min(nrecs-1, ei)+1]

def get_xldatefromdatetime(ds):
    '''
    Purpose:
     Returns a list of xldatetime (floating point number represent decimal days
     since 00:00 1/1/1900) from a list of Python datetimes
    Usage:
     pfp_utils.get_xldatefromdatetime(ds)
    Assumptions:
     The Excel datetime series ("xlDateTime") exists in the data structure ds.
    Author: PRI
    '''
    # get the datemode of the original Excel spreadsheet
    if "xl_datemode" in list(ds.root["Attributes"].keys()):
        datemode = int(ds.root["Attributes"]["xl_datemode"])
    else:
        datemode = int(0)
    # get the Excel datetime attributes
    xldt_attr = {"long_name": "Date/time in Excel format", "units": "days since 1899-12-31 00:00:00"}
    # get a local pointer to the Python DateTime series in ds
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    flag = ds.root["Variables"]["DateTime"]["Flag"]
    # get a list of Excel datetimes from the Python datetime objects
    xldate = [xlrd.xldate.xldate_from_datetime_tuple((ldt[i].year,
                                                      ldt[i].month,
                                                      ldt[i].day,
                                                      ldt[i].hour,
                                                      ldt[i].minute,
                                                      ldt[i].second),
                                                      datemode) for i in range(0,len(ldt))]
    xldt_new = numpy.ma.array(xldate, dtype=numpy.float64, copy=True)
    # create the Excel datetime series
    var = {"Label": "xlDateTime", "Data": xldt_new, "Flag": flag, "Attr": xldt_attr}
    CreateVariable(ds, var)
    return

def get_yearfractionfromdatetime(dt):
    """
    Return the fraction of a year from a datetime.
    From https://stackoverflow.com/questions/6451655/python-how-to-convert-datetime-dates-to-decimal-years
    """
    def sinceEpoch(dt):
        """returns seconds since epoch"""
        return time.mktime(dt.timetuple())
    s = sinceEpoch
    year = dt.year
    startOfThisYear = datetime.datetime(year=year, month=1, day=1)
    startOfNextYear = datetime.datetime(year=year+1, month=1, day=1)
    yearElapsed = s(dt) - s(startOfThisYear)
    yearDuration = s(startOfNextYear) - s(startOfThisYear)
    fraction = yearElapsed/yearDuration
    return year + fraction

def get_ymdhmsfromdatetime(ds):
    '''
    Purpose:
     Gets the year, month, day, hour, minute and second from a list of
     Python datetimes.  The Python datetime series is read from
     the input data structure and the results are written back to the
     data structure.
    Usage:
     pfp_utils.get_ymdhmsfromdatetime(ds)
    Assumptions:
     None
    Author: PRI
    '''
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    dt = ds.root["Variables"]["DateTime"]["Data"]
    flag = numpy.zeros(nRecs,dtype=numpy.int32)
    Year = numpy.array([dt[i].year for i in range(0,nRecs)]).astype(numpy.int32)
    Month = numpy.array([dt[i].month for i in range(0,nRecs)]).astype(numpy.int32)
    Day = numpy.array([dt[i].day for i in range(0,nRecs)]).astype(numpy.int32)
    Hour = numpy.array([dt[i].hour for i in range(0,nRecs)]).astype(numpy.int32)
    Minute = numpy.array([dt[i].minute for i in range(0,nRecs)]).astype(numpy.int32)
    Second = numpy.array([dt[i].second for i in range(0,nRecs)]).astype(numpy.int32)
    Hdh = numpy.array([float(Hour[i])+float(Minute[i])/60. for i in range(0,nRecs)]).astype(numpy.float64)
    Ddd = numpy.array([(dt[i] - datetime.datetime(Year[i],1,1)).days+1+Hdh[i]/24. for i in range(0,nRecs)]).astype(numpy.float64)
    var = {"Label": "Year", "Data": Year, "Flag": flag, "Attr": {"long_name": "Year"}}
    CreateVariable(ds, var)
    var = {"Label": "Month", "Data": Month, "Flag": flag, "Attr": {"long_name": "Month"}}
    CreateVariable(ds, var)
    var = {"Label": "Day", "Data": Day, "Flag": flag, "Attr": {"long_name": "Day"}}
    CreateVariable(ds, var)
    var = {"Label": "Hour", "Data": Hour, "Flag": flag, "Attr": {"long_name": "Hour"}}
    CreateVariable(ds, var)
    var = {"Label": "Minute", "Data": Minute, "Flag": flag, "Attr": {"long_name": "Minute"}}
    CreateVariable(ds, var)
    var = {"Label": "Second", "Data": Second, "Flag": flag, "Attr": {"long_name": "Second"}}
    CreateVariable(ds, var)
    var = {"Label": "Hdh", "Data": Hdh, "Flag": flag, "Attr": {"long_name": "Decimal hour of the day"}}
    CreateVariable(ds, var)
    var = {"Label": "Ddd", "Data": Ddd, "Flag": flag, "Attr": {"long_name": "Decimal day of the year"}}
    CreateVariable(ds, var)
    return

def get_ymdhmsfromxldate(ds):
    """
        Gets year, month, day, hour, and if available seconds, from
        excel-formatted Timestamp

        Usage pfp_ts.get_ymdhmsfromxldate(ds)
        cf: control file
        ds: data structure
        """
    logger.info(' Getting date and time variables')
    # get the date mode of the original Excel datetime
    datemode = int(ds.root["Attributes"]['xl_datemode'])
    nRecs = len(ds.root["Variables"]['xlDateTime']['Data'])
    Year = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Month = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Day = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Hour = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Minute = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Second = numpy.array([c.missing_value]*nRecs,numpy.int32)
    Hdh = numpy.array([c.missing_value]*nRecs,numpy.float64)
    Ddd = numpy.array([c.missing_value]*nRecs,numpy.float64)
    flag = numpy.zeros(nRecs)
    for i in range(nRecs):
        DateTuple = xlrd.xldate_as_tuple(ds.root["Variables"]['xlDateTime']['Data'][i],datemode)
        Year[i] = int(DateTuple[0])
        Month[i] = int(DateTuple[1])
        Day[i] = int(DateTuple[2])
        Hour[i] = int(DateTuple[3])
        Minute[i] = int(DateTuple[4])
        Second[i] = int(DateTuple[5])
        Hdh[i] = float(DateTuple[3])+float(DateTuple[4])/60.
        Ddd[i] = ds.root["Variables"]['xlDateTime']['Data'][i] - xlrd.xldate.xldate_from_date_tuple((Year[i],1,1),datemode) + 1
    var = {"Label": "Year", "Data": Year, "Flag": flag, "Attr": {"long_name": "Year"}}
    CreateVariable(ds, var)
    var = {"Label": "Month", "Data": Month, "Flag": flag, "Attr": {"long_name": "Month"}}
    CreateVariable(ds, var)
    var = {"Label": "Day", "Data": Day, "Flag": flag, "Attr": {"long_name": "Day"}}
    CreateVariable(ds, var)
    var = {"Label": "Hour", "Data": Hour, "Flag": flag, "Attr": {"long_name": "Hour"}}
    CreateVariable(ds, var)
    var = {"Label": "Minute", "Data": Minute, "Flag": flag, "Attr": {"long_name": "Minute"}}
    CreateVariable(ds, var)
    var = {"Label": "Second", "Data": Second, "Flag": flag, "Attr": {"long_name": "Second"}}
    CreateVariable(ds, var)
    var = {"Label": "Hdh", "Data": Hdh, "Flag": flag, "Attr": {"long_name": "Decimal hour of the day"}}
    CreateVariable(ds, var)
    var = {"Label": "Ddd", "Data": Ddd, "Flag": flag, "Attr": {"long_name": "Decimal day of the year"}}
    CreateVariable(ds, var)
    return

def haskey(cf,ThisOne,key):
    return key in list(cf['Variables'][ThisOne].keys())

def incf(cf,ThisOne):
    return ThisOne in list(cf['Variables'].keys())

def is_number(s):
    try:
        n=str(float(s))
        if n == "nan" or n=="inf" or n=="-inf" : return False
    except ValueError:
        try:
            complex(s) # for complex
        except ValueError:
            return False
    return True

def linear_function(B,x):
    """
    Purpose:
     Linear function for use with orthogonal distance regression.
    Usage:
     linear = scipy.odr.Model(pfp_utils.linear_function)
     where B is a list of slope and offset values
           x is an array of x values
    """
    return B[0]*x + B[1]

def list_to_string(l):
    """ Convert list to comma separated string."""
    if isinstance(l, list):
        s = ",".join(l)
    else:
        s = ""
    return s

def make_attribute_dictionary(attr=None):
    """
    Purpose:
     Make an empty attribute dictionary.
    Usage:
     attr_new = pfp_utils.make_attribute_dictionary(attr_in)
     where attr_in is an existing attribute dictionary
    Author: PRI
    Date: Back in the day
    """
    attr_out = {"long_name": "", "units": "", "statistic_type": "average"}
    defaults = list(attr_out.keys())
    if attr is None:
        pass
    elif isinstance(attr, dict):
        attr_out = copy.deepcopy(attr)
        for default in defaults:
            if default not in attr_out:
                attr_out[default] = ""
    else:
        msg = "  make_attribute_dictionary: argument not a dictionary"
        logger.debug(msg)
    return attr_out

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

def MergeQCFlag(QCFlag_list):
    """ Merge a list of QC flags by taking the element-wise maximum."""
    if len(QCFlag_list)==0: return None
    if len(QCFlag_list)==1: return QCFlag_list[0]
    flag = QCFlag_list[0].copy()                            # get a copy of the first flag
    for item in QCFlag_list[1:]:                            # loop over the list of flags
        tmp_flag = item.copy()                              # get a copy of the next flag
        index = numpy.where(numpy.mod(tmp_flag,10)==0)      # find the elements with flag = 0, 10, 20 etc
        tmp_flag[index] = 0                                 # set them all to 0
        flag = numpy.maximum(flag,tmp_flag)                 # now take the maximum
    return flag

def MergeVariables(ds, out_label, in_labels):
    """
    Purpose:
     Merge the variables with labels in in_labels into a single variable with
     the label out_label.
    Usage:
    Author: PRI
    Date: October 2018
    """
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    var_in = GetVariable(ds, in_labels[0])
    var_out = CopyVariable(var_in)
    if len(in_labels) == 1:
        return var_out
    for label in in_labels[1:]:
        var_in = GetVariable(ds, label)
        if var_in["Attr"]["units"] != var_out["Attr"]["units"]:
            continue
        in_mask = numpy.ma.getmaskarray(var_in["Data"])
        out_mask = numpy.ma.getmaskarray(var_out["Data"])
        condition = (out_mask == True) & (in_mask == False)
        var_out["Data"] = numpy.ma.where(condition, var_in["Data"], var_out["Data"])
        var_out["Flag"] = numpy.ma.where(condition, var_in["Flag"], var_out["Flag"])
    append_to_attribute(var_out["Attr"], {descr_level: "merged from " + str(in_labels)})
    var_out["Label"] = out_label
    return var_out

def nxMom_nxScalar_alpha(zoL):
    nRecs = numpy.size(zoL)
    nxMom = numpy.ma.ones(nRecs) * 0.079
    nxScalar = numpy.ma.ones(nRecs) * 0.085
    alpha = numpy.ma.ones(nRecs) * 0.925
    #  get the index of stable conditions
    stable = numpy.ma.where(zoL>0)[0]
    #  now set the series to their stable values
    nxMom[stable] = 0.079 * (1 + 7.9 * zoL[stable]) ** 0.75
    nxScalar[stable] = 2.0 - 1.915 / (1 + 0.5 * zoL[stable])
    alpha[stable] = 1
    return nxMom, nxScalar, alpha

def PadVariable(var_in, start, end, out_type="ma"):
    """
    Purpose:
     Pad a variable to the specified start and end dates.
    Usage:
    Side effects:
    Author: PRI
    Date: November 2019
    """
    ts = int(var_in["time_step"])
    ts_dt = datetime.timedelta(minutes=ts)
    dt_padded = numpy.array([d for d in perdelta(start, end, ts_dt)])
    n_padded = len(dt_padded)
    if out_type == "nan":
        data_padded = numpy.full(n_padded, numpy.nan, dtype=numpy.float64)
    elif out_type == "ma":
        data_padded = numpy.ma.masked_all(n_padded, dtype=numpy.float64)
    else:
        data_padded = numpy.full(n_padded, c.missing_value, dtype=numpy.float64)
    flag_padded = numpy.full(n_padded, 1, dtype=numpy.int32)
    idxa, idxb = FindMatchingIndices(dt_padded, var_in["DateTime"])
    data_padded[idxa] = var_in["Data"]
    flag_padded[idxa] = var_in["Flag"]
    var_out = {"Label":var_in["Label"], "Attr":var_in["Attr"],
               "Data":data_padded, "Flag":flag_padded,
               "DateTime":dt_padded, "time_step":ts}
    return var_out

def parse_rangecheck_limits(s):
    """
    Purpose:
     Parse the RangeCheck limits string either read from a control file or
     from a variable attribute without resorting to Python's eval statement.
     And as a bonus, we will do some error checking ...
    Usage:
     rangecheck_limit_list = pfp_utils.parse_rangecheck_limits(s)
     where s is the input string
           rangecheck_limits_list is the returned list
    Side effects:
     Returns an empty list and logs an error message if the input string can
     not be handled.
    Author: PRI
    Date: September 2017
    """
    # initialise the returned list to an empty list
    l = []
    # check to see that a string was passed in
    if not isinstance(s, str):
        # error message and return if input was not a string
        msg = "parse_rangecheck_limits: argument must be a string"
        logger.error(msg)
        return []
    if ("[" in s) and ("]" in s) and ("*" in s):
        # old style of [value]*12
        s = s[s.index("[")+1:s.index("]")]
    elif ("[" in s) and ("]" in s) and ("*" not in s):
        # old style of [1,2,3,4,5,6,7,8,9,10,11,12]
        s = s.replace("[", "").replace("]", "")
    else:
        pass
    # split the string on commas
    l = s.split(",")
    # only acceptable lengths are 12 (1 per month) or 1
    if len(l) != 1:
        if len(l) != 12:
            msg = "parse_rangecheck_limits: number of values must be 12 or 1"
            logger.error(msg)
            return []
    return [float(e) for e in l]

def path_exists(pathname,mode="verbose"):
    if not os.path.isdir(pathname):
        if mode=="verbose":
            logger.error(' Path '+pathname+' not found')
        return False
    else:
        return True

def perdelta(start, end, delta):
    """
    Yields an iterator of datetime objects from start to end with time step delta.
    """
    curr = start
    while curr <= end:
        yield curr
        curr += delta

def polyval(p,x):
    """
    Replacement for the polyval routine in numpy.  This version doesnt check the
    input variables to make sure they are array_like.  This means that when
    masked arrays are treated correctly when they are passed to this routine.
    Parameters
    ----------
     p : a 1D array of coefficients, highest order first
     x : a 1D array of points at which to evaluate the polynomial described by
         the coefficents in p
    Example
    -------
    >>> x = numpy.array([1,2,3])
    >>> p = numpy.array([2,0])
    >>> pfp_utils.polyval(p,x)
        array([2,4,6])
    >>> y = numpy.array([1,c.missing_value,3])
    >>> y = numpy.ma.masked_where(y==c.missing_value,y)
    >>> pfp_utils.polyval(p,y)
    masked_array(data = [2 -- 6],
                 mask = [False True False],
                 fill_value = 999999)
    """
    y = 0
    for i in range(len(p)):
        y = x*y + p[i]
    return y

def rounddttots(dt,ts=30):
    """
    Purpose:
     Round the time stamp to the nearest time step.
    Usage:
    Author: PRI (probably stolen from StackOverFlow)
    Date: Back in the day
    """
    dt += datetime.timedelta(minutes=int(ts/2))
    dt -= datetime.timedelta(minutes=dt.minute % int(ts),seconds=dt.second,microseconds=dt.microsecond)
    return dt

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

def round_datetime(ds, mode="nearest_timestep"):
    """
    Purpose:
     Round the series of Python datetimes to the nearest time based on mode
    Usage:
     pfp_utils.round_datetime(ds,mode=mode)
     where;
      mode = "nearest_second" rounds to the nearesy second
      mode = "nearest_timestep" rounds to the nearest time step
    Author: PRI
    Date: February 2015
    """
    # local pointer to the datetime series
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    # check which rounding option has been chosen
    if mode.lower() == "nearest_timestep":
        # get the time step
        if "time_step" in ds.root["Attributes"]:
            ts = int(float(ds.root["Attributes"]["time_step"]))
        else:
            ts = numpy.mean(get_timestep(ds)/60)
            ts = roundtobase(ts, base=30)
            ds.root["Attributes"]["time_step"] = str(int(float(ts)))
        # round to the nearest time step
        rldt = [rounddttots(dt, ts=ts) for dt in ldt]
    elif mode.lower() == "nearest_second":
        # round to the nearest second
        rldt = [rounddttoseconds(dt) for dt in ldt]
    else:
        # unrecognised option for mode, return original datetime series
        msg = " Unrecognised mode (" + str(mode) + ")" + " ,returning original time series"
        logger.error(msg)
        rldt = ds.root["Variables"]["DateTime"]["Data"]
    # replace the original datetime series with the rounded one
    ds.root["Variables"]["DateTime"]["Data"] = numpy.array(rldt)
    return

def roundtobase(x,base=5):
    return int(base*round(float(x)/base))

def round2significant(x, d, direction='nearest'):
    """
    Round to 'd' significant digits with the option to round to
    the nearest number, round up or round down.
    """
    if numpy.ma.is_masked(x):
        y = float(0)
    elif numpy.isclose(x, 0.0):
        y = float(0)
    else:
        n = d - numpy.ceil(numpy.log10(abs(x)))
        if direction.lower() == 'up':
            y = round(numpy.ceil(x*10**n))/float(10**n)
        elif direction.lower() == 'down':
            y = round(numpy.floor(x*10**n))/float(10**n)
        else:
            y = round(x*10**n)/float(10**n)
    return y

def r(b, p, alpha):
    """
    Function to calculate the r coeficient of the Massman frequency correction.
    """
    r = ((b ** alpha) / (b ** alpha + 1)) * \
           ((b ** alpha) / (b ** alpha + p ** alpha)) * \
           (1 / (p ** alpha + 1))
    return r

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
            Series = numpy.ma.masked_where(abs(Series-float(c.missing_value)) < c.eps, Series)
    return Series, WasND

def SetUnitsInds(ds, ThisOne, units):
    ds.root["Variables"][ThisOne]['Attr']['units'] = units

def startlog(loggername,loggerfile):
    logger = logging.getLogger(loggername)
    logger.setLevel(logging.DEBUG)
    fh = logging.FileHandler(loggerfile)
    fh.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s', '%H:%M:%S')
    #formatter = logging.Formatter('%(asctime)s %(name)-8s %(levelname)-6s %(message)s', '%d-%m-%y %H:%M')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

def strip_non_numeric(s):
    """
    Strip non-numeric characters from a string.
    """
    return "".join([c for c in s if c in "-1234567890."])

def UpdateGlobalAttributes(cfg, ds, level):
    """
    Purpose:
     Update the global attributes in the data structure if any are specified in the
     control file.
    Usage:
    Author: PRI
    Date: Back in the day
    """
    ds.root["Attributes"]["processing_level"] = str(level)
    ds.root["Attributes"]["python_version"] = sys.version
    # put the control file name into the global attributes
    ds.root["Attributes"]["controlfile_name"] = cfg.filename
    if "Global" in cfg:
        for item in list(cfg["Global"].keys()):
            if item not in list(ds.root["Attributes"].keys()):
                ds.root["Attributes"][item] = cfg["Global"][item].replace("\n"," ").replace("\r","")

def update_progress(progress):
    barLength = 50 # Modify this to change the length of the progress bar
    if isinstance(progress, int):
        progress = float(progress)
    if not isinstance(progress, float):
        progress = 0
    if progress < 0:
        progress = 0
    if progress >= 1:
        progress = 1
    block = int(round(barLength*progress))
    progress = round(progress,2)
    text = "\rPercent: [{0}] {1:3d}%".format( "#"*block + "-"*(barLength-block), int(progress*100))
    sys.stdout.write(text)
    sys.stdout.flush()
    return

def mypause(interval):
    import matplotlib
    import matplotlib.pyplot as plt
    import matplotlib.backends
    backend = plt.rcParams['backend']
    if backend in matplotlib.rcsetup.interactive_bk:
        figManager = matplotlib._pylab_helpers.Gcf.get_active()
        if figManager is not None:
            canvas = figManager.canvas
            if canvas.figure.stale:
                canvas.draw()
            canvas.start_event_loop(interval)
            return

def variables_in_datastructure(ds, labels_to_check):
    """
    Check to see if the specified labels are in the data structure.
    """
    ok = True
    labels_in_ds = sorted(list(ds.root["Variables"].keys()))
    missing = []
    for label_to_check in labels_to_check:
        if label_to_check not in labels_in_ds:
            missing.append(label_to_check)
            ok = False
    return ok, missing
