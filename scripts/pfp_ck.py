# standard modules
import copy
import datetime
import logging
import os
# 3rd party
import numpy
import dateutil.parser
# pfp modules
from scripts import constants as c
from scripts import pfp_rp
from scripts import pfp_ts
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

def ApplyQCChecks(variable):
    """
    Purpose:
     Apply the QC checks specified in the control file object to a single variable
    Usage:
     pfp_ck.ApplyQCChecks(variable)
     where variable is a variable dictionary as returned by pfp_utils.GetVariable()
    Author: PRI
    Date: September 2016
    """
    # do the range check
    ApplyRangeCheckToVariable(variable)
    # do the diurnal check
    #do_diurnalcheck_variable(cf,variable)
    # do exclude dates
    #do_excludedates_variable(cf,variable)
    # do exclude hours
    #do_excludehours_variable(cf,variable)
    return

def ApplyRangeCheckToVariable(variable):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: September 2016
    """
    dt = variable["DateTime"]
    # Check to see if a lower limit has been specified
    if "rangecheck_lower" in variable["Attr"]:
        attr = variable["Attr"]["rangecheck_lower"]
        lower = numpy.array(parse_rangecheck_limit(attr))
        valid_lower = str(numpy.min(lower))
        month = numpy.array([dt[i].month for i in range(0,len(dt))])
        lower_series = lower[month-1]
        index = numpy.ma.where(variable["Data"]<lower_series)[0]
        variable["Data"][index] = numpy.ma.masked
        variable["Flag"][index] = numpy.int32(2)
        valid_range = variable["Attr"]["valid_range"]
        old_lower = valid_range.split(",")[0]
        valid_range = valid_range.replace(old_lower,valid_lower)
        variable["Attr"]["valid_range"] = valid_range
    if "rangecheck_upper" in variable["Attr"]:
        attr = variable["Attr"]["rangecheck_upper"]
        upper = numpy.array(parse_rangecheck_limit(attr))
        valid_upper = str(numpy.min(upper))
        month = numpy.array([dt[i].month for i in range(0,len(dt))])
        upper_series = upper[month-1]
        index = numpy.ma.where(variable["Data"]>upper_series)[0]
        variable["Data"][index] = numpy.ma.masked
        variable["Flag"][index] = numpy.int32(2)
        valid_range = variable["Attr"]["valid_range"]
        old_upper = valid_range.split(",")[1]
        valid_range = valid_range.replace(old_upper,valid_upper)
        variable["Attr"]["valid_range"] = valid_range
    return

def ApplyTurbulenceFilter(cf, ds, l5_info, ustar_threshold=None):
    """
    Purpose:
    Usage:
    Author:
    Date:
    """
    iris = l5_info["RemoveIntermediateSeries"]
    opt = ApplyTurbulenceFilter_checks(cf, ds)
    if not opt["OK"]:
        return
    # dictionary of utar thresold values
    if ustar_threshold == None:
        ustar_dict = pfp_rp.get_ustar_thresholds(cf, ds)
        if ds.info["returncodes"]["value"] != 0:
            return
    else:
        ustar_dict = pfp_rp.get_ustar_thresholds_annual(ldt, ustar_threshold)
    # initialise a dictionary for the indicator series
    indicators = {}
    # local point to datetime series
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    # get data for the indicator series
    ustar = pfp_utils.GetVariable(ds, "ustar")
    # get the day/night indicator
    indicators["day"] = pfp_rp.get_day_indicator(cf, ds)
    ind_day = indicators["day"]["Data"]
    # get the turbulence indicator series
    if opt["turbulence_filter"].lower() in ["ustar", "ustar (basic)"]:
        # indicators["turbulence"] = 1 ==> turbulent, indicators["turbulence"] = 0 ==> not turbulent
        indicators["turbulence"] = pfp_rp.get_turbulence_indicator_ustar_basic(ldt, ustar, ustar_dict)
        # initialise the final indicator series as the turbulence indicator
        # subsequent filters will modify the final indicator series
        indicators["final"] = copy.deepcopy(indicators["turbulence"]["basic"])
        indicators["final"]["Label"] = "indicator_turbulence_final"
    elif opt["turbulence_filter"].lower() == "ustar (evgb)":
        # ustar >= threshold during day AND ustar has been >= threshold since sunset ==> indicators["turbulence"] = 1
        # indicators["turbulence"] = 0 during night once ustar has dropped below threshold even if it
        # increases above the threshold later in the night
        indicators["turbulence"] = pfp_rp.get_turbulence_indicator_ustar_evgb(ldt, ustar, ustar_dict, ind_day)
        # initialise the final indicator series as the turbulence indicator
        # subsequent filters will modify the final indicator series
        indicators["final"] = copy.deepcopy(indicators["turbulence"]["evgb"])
        indicators["final"]["Label"] = "indicator_turbulence_final"
    elif opt["turbulence_filter"].lower() in ["ustar (fluxnet)", "ustar (fluxnet+day)"]:
        # ustar >= threshold ==> indicators["turbulence"] = 1
        # BUT ...
        # if ustar[i] < threshold and ustar[i+1] >= threshold then
        #     indicators["turbulence"][i+1] = 0
        # IE the first period with ustar above the threshold is ignored
        indicators["turbulence"] = pfp_rp.get_turbulence_indicator_ustar_fluxnet(ldt, ustar, ustar_dict)
        # initialise the final indicator series as the turbulence indicator
        # subsequent filters will modify the final indicator series
        indicators["final"] = copy.deepcopy(indicators["turbulence"]["fluxnet"])
        indicators["final"]["Label"] = "indicator_turbulence_final"
    else:
        msg = " Unrecognised turbulence filter option ("
        msg = msg + opt["turbulence_filter"] + "), no filter applied"
        logger.error(msg)
        return
    # check to see if the user wants to accept all day time observations
    # regardless of ustar value
    if opt["accept_day_times"].lower() == "yes":
        # FluxNet method applies ustar filter to day time data
        if opt["turbulence_filter"].lower() not in ["ustar (fluxnet)"]:
            # if yes, then we force the final indicator to be 1
            # when ustar is below the threshold during the day ...
            c1 = (indicators["day"]["Data"] == 1)
            # ... but only if the ustar data is not masked
            c2 = (numpy.ma.getmaskarray(ustar) == False)
            idx = numpy.where(c1 & c2)[0]
            indicators["final"]["Data"][idx] = int(1)
            indicators["final"]["Attr"].update(indicators["day"]["Attr"])
        else:
            msg = " u* filter applied to day time data (FluxNet method)"
            logger.warning(msg)
    # write the turbulence indicator to the data structure
    for item in list(indicators["turbulence"].keys()):
        pfp_utils.CreateVariable(ds, indicators["turbulence"][item])
        iris["not_output"].append(indicators["turbulence"][item]["Label"])
    # write the day, night and evening indicators to the data structure
    pfp_utils.CreateVariable(ds, indicators["day"])
    iris["not_output"].append(indicators["day"]["Label"])
    # write the final indicator to the data structure
    pfp_utils.CreateVariable(ds, indicators["final"])
    iris["not_output"].append(indicators["final"]["Label"])

    # loop over the series to be filtered
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    for label in opt["filter_list"]:
        msg = " Applying " + opt["turbulence_filter"] + " filter to " + label
        logger.info(msg)
        # get the data
        var = pfp_utils.GetVariable(ds, label)
        # continue to next series if this series has been filtered before
        if "turbulence_filter" in var["Attr"]:
            msg = " Series " + label + " has already been filtered, skipping ..."
            logger.warning(msg)
            continue
        # save the non-filtered data
        var_nofilter = copy.deepcopy(var)
        var_nofilter["Label"] = var["Label"] + "_nofilter"
        pfp_utils.CreateVariable(ds, var_nofilter)
        iris["not_output"].append(var_nofilter["Label"])
        # now apply the filter
        var_filtered = copy.deepcopy(var)
        var_filtered["Data"] = numpy.ma.masked_where(indicators["final"]["Data"] == 0,
                                                     var["Data"], copy=True)
        var_filtered["Flag"] = numpy.copy(var["Flag"])
        idx = numpy.where(indicators["final"]["Data"] == 0)[0]
        var_filtered["Flag"][idx] = numpy.int32(502)
        # update the "description" attribute
        pfp_utils.append_to_attribute(var_filtered["Attr"], {descr_level: "turbulence filter applied"})
        # and write the filtered data to the data structure
        # write the annual ustar thresholds to the variable attributes
        for year in sorted(list(ustar_dict.keys())):
            var_filtered["Attr"]["ustar_threshold_" + str(year)] = str(ustar_dict[year]["ustar_mean"])
        pfp_utils.CreateVariable(ds, var_filtered)
        # and write a copy of the filtered data to the data structure so it
        # will still exist once the gap filling has been done
        var_filtered["Label"] = str(label) + "_filtered"
        pfp_utils.CreateVariable(ds, var_filtered)
        iris["not_output"].append(var_filtered["Label"])
        nnf = numpy.ma.count(var["Data"])
        nf = numpy.ma.count(var_filtered["Data"])
        pc = int(100 * (float(nnf - nf) / float(nnf)) + 0.5)
        msg = "  " + opt["turbulence_filter"] + " filter removed " + str(pc)
        msg += "% of available data from " + label
        logger.info(msg)
    return

def ApplyTurbulenceFilter_checks(cf, ds):
    """
    Purpose:
    Usage:
    Author:
    Date:
    """
    opt = {"OK":True, "turbulence_filter":"ustar", "filter_list":["Fco2"]}
    # return if there is no Options section in control file
    if "Options" not in cf:
        msg = " ApplyTurbulenceFilter: Options section not found in control file"
        logger.warning(msg)
        opt["OK"] = False
        return opt
    # get the value of the TurbulenceFilter key in the Options section
    opt["turbulence_filter"] = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "TurbulenceFilter", default="ustar")
    # return if turbulence filter disabled
    if opt["turbulence_filter"].lower() == "none":
        logger.warning("!!!")
        msg = "!!! Turbulence filter disabled in control file at "
        msg += ds.root["Attributes"]["processing_level"]
        logger.warning(msg)
        logger.warning("!!!")
        opt["OK"] = False
        return opt
    # check to see if filter type can be handled
    if opt["turbulence_filter"].lower() not in ["ustar", "ustar (basic)", "ustar (evgb)",
                                                "ustar (fluxnet)", "ustar (fluxnet+day)"]:
        msg = " Unrecognised turbulence filter option ("
        msg = msg+opt["turbulence_filter"]+"), no filter applied"
        logger.error(msg)
        opt["OK"] = False
        return opt
    # get the list of series to be filtered
    if "FilterList" in cf["Options"]:
        filter_string = cf["Options"]["FilterList"]
        if "," in filter_string:
            opt["filter_list"] = filter_string.split(",")
        else:
            opt["filter_list"] = [filter_string]
    # check to see if the series are in the data structure
    for item in list(opt["filter_list"]):
        if item not in list(ds.root["Variables"].keys()):
            msg = " Series "+item+" given in FilterList not found in data stucture"
            logger.warning(msg)
            opt["filter_list"].remove(item)
    # return if the filter list is empty
    if len(opt["filter_list"]) == 0:
        msg = " FilterList in control file is empty, skipping turbulence filter"
        logger.warning(msg)
        opt["OK"] = False
        return opt
    # get the value of the DayNightFilter key in the Options section
    opt["daynight_filter"] = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "DayNightFilter", default="Fsd")
    # check to see if filter type can be handled
    if opt["daynight_filter"].lower() not in ["fsd", "sa", "none"]:
        msg = " Unrecognised day/night filter option ("
        msg = msg+opt["daynight_filter"]+"), no filter applied"
        logger.error(msg)
        opt["OK"] = False
        return opt
    # check to see if all day time values are to be accepted
    opt["accept_day_times"] = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "AcceptDayTimes", default="Yes")
    opt["use_evening_filter"] = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "UseEveningFilter", default="No")

    return opt

def cliptorange(data, lower, upper):
    data = rangecheckserieslower(data,lower)
    data = rangecheckseriesupper(data,upper)
    return data

def do_dependencycheck(cf, ds, section, series, code=23, mode="quiet"):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: Back in the day
    """
    if len(series)==0:
        return
    if len(section) == 0:
        section = pfp_utils.get_cfsection(cf, series, mode='quiet')
        if section == None:
            return
    if "DependencyCheck" not in list(cf[section][series].keys()):
        return
    if "source" not in cf[section][series]["DependencyCheck"]:
        msg = " DependencyCheck: keyword 'source' not found for series " + series + ", skipping ..."
        logger.error(msg)
        return
    if mode == "verbose":
        msg = " Doing DependencyCheck for " + series
        logger.info(msg)
    # get the precursor source list from the control file
    source_string = cf[section][series]["DependencyCheck"]["source"]
    if "," in source_string:
        source_list = source_string.split(",")
    else:
        source_list = [source_string]
    # get the data
    dependent = pfp_utils.GetVariable(ds, series)
    # loop over the precursor source list
    for item in source_list:
        # check the precursor is in the data structure
        if item not in list(ds.root["Variables"].keys()):
            msg = " DependencyCheck: " + series + " precursor series "
            msg += item + " not found, skipping ..."
            logger.warning(msg)
            continue
        # get the precursor data
        precursor = pfp_utils.GetVariable(ds, item)
        # mask the dependent data where the precursor flag shows data not OK
        dependent["Data"] = numpy.ma.masked_where(numpy.mod(precursor["Flag"], 10) != 0,
                                                  dependent["Data"])
        # get an index where the precursor flag shows data not OK
        idx = numpy.ma.where(numpy.mod(precursor["Flag"], 10) != 0)[0]
        # set the dependent QC flag
        dependent["Flag"][idx] = numpy.int32(code)
    # put the data back into the data structure
    dependent["Attr"]["DependencyCheck"] = ",".join(source_list)
    pfp_utils.CreateVariable(ds, dependent)
    # our work here is done
    return

def do_diurnalcheck(cf, ds, section, series, code=5):
    """
    Purpose:
     Do the diurnal QC check on the series for which it has been requested.
     The diurnal QC check works as follows:
      - get the diurnal statistics (average and standard deviation) for each month
        - the diurnal statistics are calculated from the
          data at each time step through out the day
        - there are 48 (24) diurnal values each day for
          a time step of 30 (60) minutes
      - mask any points that lie outside the average +/- NumSd*standard deviation
        where NumSd is specified by the user in the control file
    Usage:
    Side effects:
    Author: PRI
    Date: Back in the day, tidied up in April 2020 during the COVID-19 lockdown
    """
    if 'DiurnalCheck' not in list(cf[section][series].keys()):
        return
    if 'numsd' not in list(cf[section][series]["DiurnalCheck"].keys()):
        return
    ts = int(float(ds.root["Attributes"]["time_step"]))
    n = int((60./ts) + 0.5)             #Number of timesteps per hour
    nInts = int((1440.0/ts)+0.5)        #Number of timesteps per day
    Av = numpy.array([c.missing_value]*nInts, dtype=numpy.float64)
    Sd = numpy.array([c.missing_value]*nInts, dtype=numpy.float64)
    NSd = numpy.array(parse_rangecheck_limit(cf[section][series]['DiurnalCheck']['numsd']))
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    month = numpy.array([d.month for d in ldt["Data"]])
    Hdh = numpy.array([(d.hour + d.minute/float(60)) for d in ldt["Data"]])
    for m in range(1, 13):
        mindex = numpy.where(month == m)[0]
        if len(mindex) != 0:
            lHdh = Hdh[mindex]
            l2ds = ds.root["Variables"][series]["Data"][mindex]
            for i in range(nInts):
                li = numpy.where((abs(lHdh-(float(i)/float(n)))<c.eps)&(l2ds!=float(c.missing_value)))
                if numpy.size(li)!=0:
                    Av[i] = numpy.mean(l2ds[li])
                    Sd[i] = numpy.std(l2ds[li])
                else:
                    Av[i] = float(c.missing_value)
                    Sd[i] = float(c.missing_value)
            Lwr = Av - NSd[m-1]*Sd
            Upr = Av + NSd[m-1]*Sd
            hindex = numpy.array(n*lHdh,int)
            index = numpy.where(((l2ds!=float(c.missing_value))&(l2ds<Lwr[hindex]))|
                                ((l2ds!=float(c.missing_value))&(l2ds>Upr[hindex])))[0] + mindex[0]
            ds.root["Variables"][series]["Data"][index] = numpy.float64(c.missing_value)
            ds.root["Variables"][series]["Flag"][index] = numpy.int32(code)
            ds.root["Variables"][series]["Attr"]["diurnalcheck_numsd"] = cf[section][series]["DiurnalCheck"]["numsd"]
    return

def do_EC155check(cf, ds, code=4):
    """
    Purpose:
     Reject covariances of H2O (UxA, UyA and UzA) and CO2 (UzC, UyC and UzC)
     based on the IRGA AGC and the standard deviation or variance of H2O and
     CO2 concentration.
     QC checks on AGC and standard deviation or variance of H2O and CO2 are
     performed before this routine is called.  This routine then rejects the
     covariance values for those times when the precursors have been rejected.
     Only 1 H2O and 1 CO2 variable, either standard deviation or
     variance, are used.
     This routine is an implicit DependencyCheck.
     EC150/155 version.
    Usage:
     pfp_ch.do_li7500check(cf, ds, code=4)
     where cf is a control file
           ds is a data structure
    Side effects:
     Covariance values are masked and flags set to 4 for all time steps when
     any of the precursors have failed a previous QC check.
    Author: PRI
    Date: October 2020 (rewrite of original)
    """
    irga_type = str(ds.root["Attributes"]["irga_type"])
    msg = " Doing the IRGA (" + irga_type + ") check"
    logger.info(msg)
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    labels = list(ds.root["Variables"].keys())
    # list of variables to be modified by this QC check
    dependents = ["UzA", "UxA", "UyA", "UzC", "UxC", "UyC",
                  "AH_IRGA_Av", "AH_IRGA_Sd", "AH_IRGA_Vr",
                  "CO2_IRGA_Av", "CO2_IRGA_Sd", "CO2_IRGA_Vr",
                  "H2O_IRGA_Av", "H2O_IRGA_Sd", "H2O_IRGA_Vr"]
    # check these are in the data structure
    for label in list(dependents):
        if label not in labels:
            dependents.remove(label)
    # return if there are no dependents to check
    if len(dependents) == 0:
        msg = "  No dependent variables found, skipping IRGA check ..."
        logger.warning(msg)
        return
    # list for conditional variables
    conditionals = []
    # check if we have the IRGA diagnostic
    got_diag = False
    for diag in ["Diag_IRGA", "Diag_7500"]:
        if diag in labels:
            got_diag = True
            conditionals.append(diag)
            break
    if not got_diag:
        msg = " IRGA diagnostic (Diag_IRGA) not found in data"
        logger.warning(msg)
    # check if we have the H2O and CO2 signal strengths
    got_signal = False
    for signal in ["CO2Sig_IRGA", "H2OSig_IRGA", "Signal_Av", "Signal_H2O", "Signal_CO2"]:
        if signal in labels:
            got_signal = True
            conditionals.append(signal)
    if not got_signal:
        msg = " Signal_H2O and Signal_CO2 not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # check of H2O standard deviation or variance (only use one)
    got_H2O = False
    for h2o in ["H2O_IRGA_Sd", "AH_IRGA_Sd", "H2O_IRGA_Vr", "AH_IRGA_Vr"]:
        if h2o in labels:
            got_H2O = True
            conditionals.append(h2o)
            break
    if not got_H2O:
        msg = " H2O standard deviation or variance not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # check of CO2 standard deviation or variance (only use one)
    got_CO2 = False
    for co2 in ["CO2_IRGA_Sd", "CO2_IRGA_Vr"]:
        if co2 in labels:
            got_CO2 = True
            conditionals.append(co2)
            break
    if not got_CO2:
        msg = " CO2 standard deviation or variance not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # return if we found no conditionals
    if len(conditionals) == 0:
        msg = " No conditional variables found, skipping IRGA check ..."
        logger.warning(msg)
        return
    # create an index series, 0 ==> not OK, 1 ==> OK
    cidx = numpy.ones(nrecs, dtype=int)
    for conditional in conditionals:
        variable = pfp_utils.GetVariable(ds, conditional)
        idx = numpy.where(numpy.ma.getmaskarray(variable["Data"]) == True)[0]
        msg = "  IRGA check: " + conditional + " rejected " + str(numpy.size(idx)) + " points"
        logger.info(msg)
        cidx[idx] = int(0)
    rejected = numpy.count_nonzero(cidx == 0)
    percent = int(numpy.rint(100*rejected/nrecs))
    msg = "  IRGA check: total number of points rejected was " + str(rejected)
    msg += " (" + str(percent) + "%)"
    logger.info(msg)
    # use the conditional series to mask the dependents
    for dependent in dependents:
        variable = pfp_utils.GetVariable(ds, dependent)
        variable["Data"] = numpy.ma.masked_where(cidx == int(0), variable["Data"])
        idx = numpy.where(cidx == int(0))[0]
        variable["Flag"][idx] = int(code)
        variable["Attr"]["irga_check"] = ",".join(dependents)
        pfp_utils.CreateVariable(ds, variable)
    return

def do_EPQCFlagCheck(cf, ds, section, series, code=9):
    """
    Purpose:
     Mask data according to the value of an EddyPro QC flag.
    Usage:
    Author: PRI
    Date: August 2017
    """
    # return if "EPQCFlagCheck" not used for this variable
    if "EPQCFlagCheck" not in list(cf[section][series].keys()):
        return
    # check the "source" key exists and is a string
    if "source" not in cf[section][series]["EPQCFlagCheck"]:
        msg = "  EPQCFlagCheck: 'source' key not found for (" + series + ")"
        logger.error(msg)
        return
    if not isinstance(cf[section][series]["EPQCFlagCheck"]["source"], str):
        msg = "  EPQCFlagCheck: 'source' value must be a string (" + series + ")"
        logger.error(msg)
        return
    # comma separated string to list
    source_list = cf[section][series]["EPQCFlagCheck"]["source"].split(",")
    # check the "reject" key exists and is a string
    if "reject" not in cf[section][series]["EPQCFlagCheck"]:
        msg = "  EPQCFlagCheck: 'reject' key not found for (" + series + ")"
        logger.error(msg)
        return
    if not isinstance(cf[section][series]["EPQCFlagCheck"]["reject"], str):
        msg = "  EPQCFlagCheck: 'reject' value must be a string (" + series + ")"
        logger.error(msg)
        return
    # comma separated string to list
    reject_list = cf[section][series]["EPQCFlagCheck"]["reject"].split(",")
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    flag = numpy.zeros(nRecs, dtype=numpy.int32)
    source_list = pfp_utils.string_to_list(cf[section][series]['EPQCFlagCheck']["source"])
    reject_list = pfp_utils.string_to_list(cf[section][series]['EPQCFlagCheck']["reject"])
    variable = pfp_utils.GetVariable(ds, series)
    for source in source_list:
        epflag = pfp_utils.GetVariable(ds, source)
        for value in reject_list:
            bool_array = numpy.isclose(epflag["Data"], float(value))
            idx = numpy.where(bool_array == True)[0]
            flag[idx] = numpy.int32(1)
    idx = numpy.where(flag == 1)[0]
    variable["Data"][idx] = float(c.missing_value)
    variable["Flag"][idx] = numpy.int32(9)
    pfp_utils.CreateVariable(ds, variable)
    return

def do_excludedates(cf,ds,section,series,code=6):
    """
    Purpose:
     Mask data within a date range specified for a variable in the control file.
     This is a rewrite of the previous version to make it more robust.
    Usage:
     do_excludedates(cf, ds, section, series, code=6)
     where cf is the control file
           ds is the data structure
           section is the section in the control file e.g. "Variables"
           series is the variable label in ds
           code is the QC flag code for excluded data
    Side effects:
     Changes the data for this variable in the data structure.
    Author: PRI
    Date: February 2026
    """
    if 'ExcludeDates' not in list(cf[section][series].keys()):
        return
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ldt = ds.root["Variables"]['DateTime']['Data']
    exclude_list = list(cf[section][series]['ExcludeDates'].keys())
    num_exclude = len(exclude_list)
    for i in range(num_exclude):
        exclude_dates_string = cf[section][series]['ExcludeDates'][str(i)]
        if exclude_dates_string == "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM":
            continue
        exclude_dates_list = exclude_dates_string.split(",")
        if len(exclude_dates_list) != 2:
            msg = " ExcludeDates range does not contain 2 entries"
            logger.warning(msg)
            continue
        idx = []
        try:
            for j in range(len(exclude_dates_list)):
                dt = datetime.datetime.strptime(exclude_dates_list[j].strip(),'%Y-%m-%d %H:%M')
                ix = pfp_utils.find_nearest_value(ldt, dt)
                ix = max([0, min([ix, nrecs - 1])])
                idx.append(ix)
        except ValueError:
            msg = " Unable to get ExcludeDate range from " + exclude_dates_string + ", ignoring ..."
            logger.warning(msg)
            continue
        # mask points in the date range
        if len(idx) == 2:
            idx = [min(idx), max(idx)]
            # PRI is allowed to do direct writes to the data structure
            # everyone else has to use pfp_utils.GetVariable()/pfp_utils.CreateVariable()
            ds.root["Variables"][series]['Data'][idx[0]:idx[1] + 1] = numpy.float64(c.missing_value)
            ds.root["Variables"][series]['Flag'][idx[0]:idx[1] + 1] = numpy.int32(code)
            ds.root["Variables"][series]['Attr']['ExcludeDates_'+str(i)] = cf[section][series]['ExcludeDates'][str(i)]
    return

def do_excludehours(cf,ds,section,series,code=7):
    if 'ExcludeHours' not in list(cf[section][series].keys()): return
    ldt = ds.root["Variables"]['DateTime']['Data']
    ExcludeList = list(cf[section][series]['ExcludeHours'].keys())
    NumExclude = len(ExcludeList)
    Hour = numpy.array([d.hour for d in ldt])
    Minute = numpy.array([d.minute for d in ldt])
    for i in range(NumExclude):
        exclude_hours_string = cf[section][series]['ExcludeHours'][str(i)]
        ExcludeHourList = exclude_hours_string.split(",")
        try:
            dt = datetime.datetime.strptime(ExcludeHourList[0],'%Y-%m-%d %H:%M')
            si = pfp_utils.find_nearest_value(ldt, dt)
        except ValueError:
            si = 0
        try:
            dt = datetime.datetime.strptime(ExcludeHourList[1],'%Y-%m-%d %H:%M')
            ei = pfp_utils.find_nearest_value(ldt, dt)
        except ValueError:
            ei = -1
        for j in range(2,len(ExcludeHourList)):
            ExHr = datetime.datetime.strptime(ExcludeHourList[j],'%H:%M').hour
            ExMn = datetime.datetime.strptime(ExcludeHourList[j],'%H:%M').minute
            idx = numpy.where((Hour[si:ei] == ExHr) & (Minute[si:ei] == ExMn))[0] + si
            ds.root["Variables"][series]['Data'][idx] = numpy.float64(c.missing_value)
            ds.root["Variables"][series]['Flag'][idx] = numpy.int32(code)
            ds.root["Variables"][series]['Attr']['ExcludeHours_'+str(i)] = cf[section][series]['ExcludeHours'][str(i)]

def do_IRGAcheck(cf,ds):
    """
    Purpose:
     Decide which IRGA check routine to use depending on the setting
     of the "irga_type" key in the global attributes or the [Options]
     section of the control file.  The default is Li-7500.
    Usage:
    Author: PRI
    Date: September 2015
    """
    # check to see if the user has disabled the IRGA check
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "IRGA_Check", default="Yes")
    if opt.lower() == "no":
        msg = " *** IRGA_Check disbled in control file"
        logger.warning(msg)
        return
    # get the IRGA type from the global attributes or the control file
    if "irga_type" in ds.root["Attributes"]:
        irga_type = str(ds.root["Attributes"]["irga_type"])
    else:
        irga_type = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "irga_type", default="not found")
        if irga_type == "not found":
            msg = " IRGA type not in global attributes or Options section, using Li-7500"
            logger.warning(msg)
            irga_type = "Li-7500"
    # do the IRGA checks
    if irga_type in ["Li-7500", "Li-7500A", "Li-7500RS", "Li-7500DS",
                     "Li-7200", "Li-7200RS", "Li-7200DS"]:
        ds.root["Attributes"]["irga_type"] = irga_type
        do_li7500check(cf, ds)
    elif irga_type in ["EC150", "EC155", "IRGASON"]:
        ds.root["Attributes"]["irga_type"] = irga_type
        do_EC155check(cf, ds)
    else:
        msg = " Unsupported IRGA type " + irga_type + ", contact the developer ..."
        logger.error(msg)
        return
    return

def do_li7500check(cf, ds, code=4):
    """
    Purpose:
     Reject covariances of H2O (UxA, UyA and UzA) and CO2 (UzC, UyC and UzC)
     based on the IRGA AGC and the standard deviation or variance of H2O and
     CO2 concentration.
     QC checks on AGC and standard deviation or variance of H2O and CO2 are
     performed before this routine is called.  This routine then rejects the
     covariance values for those times when the precursors have been rejected.
     Only 1 H2O and 1 CO2 variable, either standard deviation or
     variance, are used.
     This routine is an implicit DependencyCheck.
     Li-7500 version.
    Usage:
     pfp_ch.do_li7500check(cf, ds, code=4)
     where cf is a control file
           ds is a data structure
    Side effects:
     Covariance values are masked and flags set to 4 for all time steps when
     any of the precursors have failed a previous QC check.
    Author: PRI
    Date: October 2020 (rewrite of original)
    """
    irga_type = str(ds.root["Attributes"]["irga_type"])
    msg = " Doing the IRGA (" + irga_type + ") check"
    logger.info(msg)
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    labels = list(ds.root["Variables"].keys())
    # list of variables to be modified by this QC check
    dependents = ["UzA", "UxA", "UyA", "UzC", "UxC", "UyC",
                  "AH_IRGA_Av", "AH_IRGA_Sd", "AH_IRGA_Vr",
                  "CO2_IRGA_Av", "CO2_IRGA_Sd", "CO2_IRGA_Vr",
                  "H2O_IRGA_Av", "H2O_IRGA_Sd", "H2O_IRGA_Vr"]
    # check these are in the data structure
    for label in list(dependents):
        if label not in labels:
            dependents.remove(label)
    # return if there are no dependents to check
    if len(dependents) == 0:
        msg = "  No dependent variables found, skipping IRGA check ..."
        logger.info(msg)
        return
    # list for conditional variables
    conditionals = []
    # check if we have the IRGA diagnostic
    got_diag = False
    for diag in ["Diag_IRGA", "Diag_7500"]:
        if diag in labels:
            got_diag = True
            conditionals.append(diag)
            break
    if not got_diag:
        msg = " IRGA diagnostic (Diag_IRGA) not found in data"
        logger.warning(msg)
    # check if we have the H2O and CO2 signal strengths
    got_signal = False
    for signal in ["CO2Sig_IRGA", "H2OSig_IRGA",
                   "Signal_Av", "Signal_H2O", "Signal_CO2",
                   "Sig_IRGA", "Sig_IRGA_Av",
                   "AGC_7500", "AGC_IRGA"]:
        if signal in labels:
            got_signal = True
            conditionals.append(signal)
    if not got_signal:
        msg = " Signal_H2O and Signal_CO2 not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # check of H2O standard deviation or variance (only use one)
    got_H2O = False
    for h2o in ["H2O_IRGA_Sd", "AH_IRGA_Sd", "H2O_IRGA_Vr", "AH_IRGA_Vr"]:
        if h2o in labels:
            got_H2O = True
            conditionals.append(h2o)
            break
    if not got_H2O:
        msg = " H2O standard deviation or variance not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # check of CO2 standard deviation or variance (only use one)
    got_CO2 = False
    for co2 in ["CO2_IRGA_Sd", "CO2_IRGA_Vr"]:
        if co2 in labels:
            got_CO2 = True
            conditionals.append(co2)
            break
    if not got_CO2:
        msg = " CO2 standard deviation or variance not used in IRGA check (not in data structure)"
        logger.warning(msg)
    # return if we found no conditionals
    if len(conditionals) == 0:
        msg = " No conditional variables found, skipping IRGA check ..."
        logger.warning(msg)
        return
    # create an index series, 0 ==> not OK, 1 ==> OK
    cidx = numpy.ones(nrecs, dtype=int)
    for conditional in conditionals:
        variable = pfp_utils.GetVariable(ds, conditional)
        idx = numpy.where(numpy.ma.getmaskarray(variable["Data"]) == True)[0]
        msg = "  IRGA check: " + conditional + " rejected " + str(numpy.size(idx)) + " points"
        logger.info(msg)
        cidx[idx] = int(0)
    rejected = numpy.count_nonzero(cidx == 0)
    percent = int(numpy.rint(100*rejected/nrecs))
    msg = "  IRGA check: total number of points rejected was " + str(rejected)
    msg += " (" + str(percent) + "%)"
    logger.info(msg)
    # use the conditional series to mask the dependents
    for dependent in dependents:
        variable = pfp_utils.GetVariable(ds, dependent)
        variable["Data"] = numpy.ma.masked_where(cidx == int(0), variable["Data"])
        idx = numpy.where(cidx == int(0))[0]
        variable["Flag"][idx] = int(code)
        variable["Attr"]["irga_check"] = ",".join(dependents)
        pfp_utils.CreateVariable(ds, variable)
    return

def do_linear(cf,ds):
    for ThisOne in list(cf['Variables'].keys()):
        if pfp_utils.haskey(cf,ThisOne,'Linear'):
            pfp_ts.ApplyLinear(cf,ds,ThisOne)

def do_lowercheck(cf,ds,section,series,code=2):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: February 2017
    """
    # check to see if LowerCheck requested for this variable
    if "LowerCheck" not in cf[section][series]:
        return
    # Check to see if limits have been specified
    if len(list(cf[section][series]["LowerCheck"].keys())) == 0:
        msg = "do_lowercheck: no date ranges specified"
        logger.info(msg)
        return

    ldt = ds.root["Variables"]["DateTime"]["Data"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    var = pfp_utils.GetVariable(ds, series)

    lc_list = list(cf[section][series]["LowerCheck"].keys())
    for n,item in enumerate(lc_list):
        # this should be a list and we should probably check for compliance
        lwr_string = cf[section][series]["LowerCheck"][item]
        var["Attr"]["lowercheck_"+str(n)] = lwr_string
        lwr_list = lwr_string.split(",")
        start_date = dateutil.parser.parse(lwr_list[0])
        sl = float(lwr_list[1])
        end_date = dateutil.parser.parse(lwr_list[2])
        el = float(lwr_list[3])
        # get the start and end indices
        si = pfp_utils.GetDateIndex(ldt, start_date, ts=ts, default=0, match="exact")
        ei = pfp_utils.GetDateIndex(ldt, end_date, ts=ts, default=len(ldt)-1, match="exact")
        # get the segment of data between this start and end date
        seg_data = var["Data"][si:ei+1]
        seg_flag = var["Flag"][si:ei+1]
        x = numpy.arange(si, ei+1, 1)
        lower = numpy.interp(x, [si, ei], [sl, el])
        index = numpy.ma.where((seg_data < lower))[0]
        seg_data[index] = numpy.ma.masked
        seg_flag[index] = numpy.int32(code)
        var["Data"][si:ei+1] = seg_data
        var["Flag"][si:ei+1] = seg_flag
    # now put the data back into the data structure
    pfp_utils.CreateVariable(ds, var)
    return

def do_madfilter(cf, ds, section, label, code=24):
    """
    Purpose:
     Apply the MAD filter used in ONEFlux, see Pastorello et al 2020 and
     Papale et al 2006 for details.
    Some notes:
     Pastorello et al 2020 give the Fsd threshold for day/nught as 20 W/m^2
     but qc_auto uses 12 W/m^2.  qc_auto runs the MAD check 3 times with
     zfc values of 4.0, 5.5 and 7.0 but only the results from zfc=5.5
     are used.
    Usage:
    Side effects:
    Author: PRI
    Date: January 2024
    """
    # check that the MAD filter has been requested for this series
    if "MADCheck" not in list(cf[section][label].keys()):
        return
    # get the variable t be filtered
    if label not in list(ds.root["Variables"].keys()):
        msg = "  " + label + " not found, skipping MADCheck ..."
        logger.warning(msg)
        return
    var = pfp_utils.GetVariable(ds, label)
    # return if the MAD filter has already been applied to this variable
    if "MAD filter" in var["Attr"]:
        msg = " MAD filter already applied to " + label
        logger.warning(msg)
        return
    msg = " Applying the MAD (despike) filter to " + label
    logger.info(msg)
    # get the MAD filter options
    info = {"ApplyMADFilter": {"Options": {}, "Variables": [label], "General": {}}}
    inao = info["ApplyMADFilter"]["Options"]
    opt = pfp_utils.get_keyvaluefromcf(cf, [section, label, "MADCheck"], "Fsd_threshold", default=12)
    inao["Fsd_threshold"] = float(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, [section, label, "MADCheck"], "window_size", default=13)
    inao["window_size"] = int(float(opt))
    opt = pfp_utils.get_keyvaluefromcf(cf, [section, label, "MADCheck"], "zfc", default=5.5)
    inao["zfc"] = float(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, [section, label, "MADCheck"], "edge_threshold", default="20,80")
    if "," in opt:
        pctl1 = float(opt.split(",")[0])
        pctl2 = float(opt.split(",")[1])
        a = numpy.ma.compressed(var["Data"])
        edge_threshold = abs(numpy.percentile(a, pctl2) - numpy.percentile(a, pctl1))
    else:
        edge_threshold = float(opt)
    inao["edge_threshold"] = float(edge_threshold)
    # add general options
    inag = info["ApplyMADFilter"]["General"]
    inag["nc_nrecs"] = int(ds.root["Attributes"]["nc_nrecs"])
    inag["time_step"] = int(ds.root["Attributes"]["time_step"])
    inag["processing_level"] = str(ds.root["Attributes"]["processing_level"])
    # get the data
    Fsd = pfp_utils.GetVariable(ds, "Fsd")
    # save a copy of the unfiltered variable
    var_notMAD = pfp_utils.CopyVariable(var)
    var_notMAD["Label"] = var["Label"] + "_notMAD"
    pfp_utils.CreateVariable(ds, var_notMAD)
    # apply the first stage of the MAD filter
    result = do_madfilter_1(var, Fsd, info, code=24)
    # apply the second stage of the MAD filter
    var = do_madfilter_2(result, info, code=24)
    # get the processing level and description attribute name
    level = str(ds.root["Attributes"]["processing_level"])
    description = "description_" + level
    pfp_utils.append_to_attribute(var["Attr"],{description: "MAD filter applied"})
    mad_attr = [inao["Fsd_threshold"], inao["window_size"], inao["zfc"], inao["edge_threshold"]]
    var["Attr"]["MAD filter"] = ",".join(map(str, mad_attr))
    pfp_utils.CreateVariable(ds, var)
    return

def do_madfilter_1(var, Fsd, info, code=24):
    # get required constants
    inag = info["ApplyMADFilter"]["General"]
    nrecs = inag["nc_nrecs"]
    ts = inag["time_step"]
    nperday = int(24*60/ts)
    # get the MAD filter options
    window_size = info["ApplyMADFilter"]["Options"]["window_size"]
    Fsd_threshold = info["ApplyMADFilter"]["Options"]["Fsd_threshold"]
    zfc = info["ApplyMADFilter"]["Options"]["zfc"]
    # calculate the window size that results in the size of the last window being
    # as close as possible to the size of the other windows
    window_nrecs = window_size * nperday
    n_windows = int(nrecs/window_nrecs)
    n_windows_nrecs = window_nrecs * n_windows
    leftover_nrecs = nrecs - n_windows_nrecs
    addons = int(leftover_nrecs/n_windows)
    # new size for all windows but the last one
    window_nrecs = window_nrecs + addons
    # size of the last window
    last_window_nrecs = window_nrecs + (nrecs - n_windows * window_nrecs)
    # arrays of ones and zeros for general use and an array of MAD flags
    ones = numpy.ones(nrecs, dtype=int)
    zeros = numpy.zeros(nrecs, dtype=int)
    cidx = numpy.zeros(nrecs, dtype=int)
    midx = numpy.where(var["Flag"] != 0)[0]
    # get the day/night indicators based on the Fsd thtreshold.
    # NOTE: qc_auto uses 12 W/m^2 not 20 W/m^2 as stated in Pastorello et al 2020
    # the first and last day time records are included in the night time indicator
    # and vice versa see Papale et al 2006.
    inds = {"day": numpy.ma.where(Fsd["Data"] > Fsd_threshold, ones, zeros),
            "night": numpy.ma.where(Fsd["Data"] <= Fsd_threshold, ones, zeros)}
    inds["day_extended"] = inds["day"] + numpy.roll(inds["day"], 1) + numpy.roll(inds["day"], -1)
    inds["day_extended"] = numpy.where(inds["day_extended"] > 0, ones, zeros)
    inds["night_extended"] = inds["night"] + numpy.roll(inds["night"], 1) + numpy.roll(inds["night"], -1)
    inds["night_extended"] = numpy.where(inds["night_extended"] > 0, ones, zeros)
    # do the business
    # add a dictionary for this z value to the variable
    var[str(zfc)] = {}
    # night time data
    var[str(zfc)]["night"] = {"Data": numpy.ma.masked_where(inds["night_extended"] < 1, var["Data"]),
                              "Flag": numpy.ma.masked_where(inds["night_extended"] < 1, var["Flag"]),
                              "differences": numpy.ma.array(numpy.zeros(nrecs, dtype=float), mask=True),
                              "upr": numpy.zeros(nrecs, dtype=float), "lwr": numpy.zeros(nrecs, dtype=float)}
    # day time data
    var[str(zfc)]["day"] = {"Data": numpy.ma.masked_where(inds["day_extended"] < 1, var["Data"]),
                            "Flag": numpy.ma.masked_where(inds["day_extended"] < 1, var["Flag"]),
                            "differences": numpy.ma.array(numpy.zeros(nrecs, dtype=float), mask=True),
                            "upr": numpy.zeros(nrecs, dtype=float), "lwr": numpy.zeros(nrecs, dtype=float)}
    # combined night and day time daya after MAD filtering with this value of z
    var[str(zfc)]["Data"] = numpy.ma.array(numpy.zeros(nrecs, dtype=float), mask=True)
    var[str(zfc)]["Flag"] = numpy.ma.array(numpy.ones(nrecs, dtype=float), mask=True)
    # loop over day and night times
    for item in ["night", "day"]:
        # local pointer to the dictionary for this z value
        vzi = var[str(zfc)][item]
        # calculate the second differential of the variable
        dm1 = vzi["Data"][1:nrecs-1] - vzi["Data"][0:nrecs-2]
        dp1 = vzi["Data"][2:] - vzi["Data"][1:nrecs-1]
        vzi["differences"][1:nrecs-1] = (dm1 - dp1)
        # loop over the windows, default is 13 days
        for i in range(n_windows):
            si = i * window_nrecs
            ei = si + window_nrecs
            if i == n_windows-1:
                ei = si + last_window_nrecs
            vzi_diff2 = vzi["differences"][si:ei]
            median = numpy.ma.median(vzi_diff2)
            median_abs = numpy.ma.median(numpy.abs(vzi_diff2 - median))
            if numpy.ma.is_masked(median) or numpy.ma.is_masked(median_abs):
                continue
            upr = median + (zfc*median_abs/0.6745)
            lwr = median - (zfc*median_abs/0.6745)
            upr = max([upr, lwr])
            lwr = min([upr, lwr])
            # cidx=2 for observations that fail the MAD test
            fidx = numpy.ma.where((vzi_diff2 > upr) | (vzi_diff2 < lwr))[0]
            cidx[si:ei][fidx] = 2
            # cidx=3 for observations that pass the MAD test
            pidx = numpy.ma.where((vzi_diff2 >= lwr) & (vzi_diff2 <= upr))[0]
            cidx[si:ei][pidx] = 3
            vzi["Data"][si:ei] = numpy.ma.masked_where(((vzi_diff2 > upr) |
                                                        (vzi_diff2 < lwr)),
                                                        var["Data"][si:ei])
            vzi["upr"][si:ei] = upr
            vzi["lwr"][si:ei] = lwr
    # construct the data series for this value of zfc
    idx = numpy.where(inds["day"] == 1)[0]
    var[str(zfc)]["Data"][idx] = var[str(zfc)]["day"]["Data"][idx]
    idx = numpy.where(inds["night"] == 1)[0]
    var[str(zfc)]["Data"][idx] = var[str(zfc)]["night"]["Data"][idx]
    return {"cidx": cidx, "midx": midx, "var": var}

def do_madfilter_2(result, info, code=24):
    # second stage of spike rejection to deal with observations at the start and end of gaps
    inag = info["ApplyMADFilter"]["General"]
    nrecs = inag["nc_nrecs"]
    cidx = result["cidx"]
    midx = result["midx"]
    var = result["var"]
    edge_threshold = info["ApplyMADFilter"]["Options"]["edge_threshold"]
    # get an index of gap edges, these have a cidx value of 0
    eidx = numpy.where(cidx == 0)[0]
    # reject the end values so we can do differences
    idx = numpy.where((eidx > 0) & (eidx < nrecs-1))[0]
    eidx = eidx[idx]
    # indices of points immediately before and after the gap start and end
    emidx = eidx - 1
    epidx = eidx + 1
    # indices of differences at the start of gaps that are greater than the threshold
    mdiff = numpy.ma.abs(var["Data"][eidx] - var["Data"][emidx])
    mdiff_fidx = numpy.ma.where(mdiff > edge_threshold)[0]
    # set cidx=2 to indicate this point fails the second stage check
    cidx[eidx[mdiff_fidx]] = 2
    # indices of differences at the start of gaps that are less than the threshold
    mdiff_pidx = numpy.ma.where(numpy.ma.abs(var["Data"][eidx] - var["Data"][emidx]) <= edge_threshold)[0]
    # set cidx=3 to indicate this point passes the second stage check
    cidx[eidx[mdiff_pidx]] = 3
    # indices of differences at the end of gaps that are greater than the threshold
    pdiff_fidx = numpy.ma.where(numpy.ma.abs(var["Data"][epidx] - var["Data"][eidx]) > edge_threshold)[0]
    # set cidx=2 to indicate this point fails the second stage check
    cidx[eidx[pdiff_fidx]] = 2
    # indices of differences at the end of gaps that are greater than the threshold
    pdiff_pidx = numpy.ma.where(numpy.ma.abs(var["Data"][epidx] - var["Data"][eidx]) <= edge_threshold)[0]
    # set cidx=3 to indicate this point passes the second stage check
    cidx[eidx[pdiff_pidx]] = 3
    # mask data points where cidx!=3, these observations have failed the first or second
    # stage spike check
    var["Data"] = numpy.ma.masked_where(cidx != 3, var["Data"])
    # and set the QC flag for these points
    mad_flags = numpy.full(nrecs, int(code), dtype=int)
    flag = numpy.where(cidx != 3, mad_flags, var["Flag"])
    flag[midx] = var["Flag"][midx]
    var["Flag"] = flag
    # save the conditional index
    var["cidx"] = cidx
    nfail = len(flag[flag==24])
    pfail = int(100*nfail/nrecs+0.5)
    msg = "  MAD filter removed " + str(nfail) + " points (" + str(pfail) + "%) from " + var["Label"]
    if pfail < 10:
        logger.info(msg)
    else:
        logger.warning(msg)
    return var

def do_qcchecks(cf,ds,mode="verbose"):
    if "processing_level" in ds.root["Attributes"]:
        level = str(ds.root["Attributes"]["processing_level"])
        if mode!="quiet": logger.info(" Doing the QC checks at level "+str(level))
    else:
        if mode!="quiet": logger.info(" Doing the QC checks")
    # get the series list from the control file
    series_list = []
    for item in ["Variables","Drivers","Fluxes"]:
        if item in cf:
            section = item
            series_list = list(cf[item].keys())
    if len(series_list)==0:
        msg = " do_qcchecks: Variables, Drivers or Fluxes section not found in control file, skipping QC checks ..."
        logger.warning(msg)
        return
    # loop over the series specified in the control file
    # first time for general QC checks
    for series in series_list:
        # check the series is in the data structure
        if series not in list(ds.root["Variables"].keys()):
            if mode!="quiet":
                msg = " QC checks: series "+series+" not found in data structure, skipping ..."
                logger.warning(msg)
            continue
        # if so, do the QC checks
        do_qcchecks_oneseries(cf,ds,section,series)
    # loop over the series in the control file
    # second time for dependencies
    for series in series_list:
        # check the series is in the data structure
        if series not in list(ds.root["Variables"].keys()):
            if mode!="quiet":
                msg = " Dependencies: series "+series+" not found in data structure, skipping ..."
                logger.warning(msg)
            continue
        # if so, do dependency check
        do_dependencycheck(cf,ds,section,series,code=23,mode="quiet")

def do_qcchecks_oneseries(cf, ds, section, series):
    if len(section) == 0:
        section = pfp_utils.get_cfsection(cf, series, mode='quiet')
        if section == None:
            return
    # do the range check
    do_rangecheck(cf, ds, section, series, code=2)
    # do the lower range check
    do_lowercheck(cf, ds, section, series, code=2)
    # do the upper range check
    do_uppercheck(cf, ds, section, series, code=2)
    # do the diurnal check
    do_diurnalcheck(cf, ds, section, series, code=5)
    # do the EP QC flag check
    do_EPQCFlagCheck(cf, ds, section, series, code=9)
    # do exclude dates
    do_excludedates(cf, ds, section, series, code=6)
    # do exclude hours
    do_excludehours(cf, ds, section, series, code=7)
    # do the MAD check
    do_madfilter(cf, ds, section, series, code=24)

def do_rangecheck(cf, ds, section, series, code=2):
    """
    Purpose:
     Applies a range check to data series listed in the control file.  Data values that
     are less than the lower limit or greater than the upper limit are replaced with
     c.missing_value and the corresponding QC flag element is set to 2.
    Usage:
    Author: PRI
    Date: Back in the day
    """
    # check that RangeCheck has been requested for this series
    if 'RangeCheck' not in list(cf[section][series].keys()):
        return
    # check that the upper and lower limits have been given
    if ("lower" not in list(cf[section][series]["RangeCheck"].keys()) or
        "upper" not in list(cf[section][series]["RangeCheck"].keys())):
        msg = "RangeCheck: key not found in control file for "+series+", skipping ..."
        logger.warning(msg)
        return
    # get the month from the datetime series
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    month = numpy.array([d.month for d in ldt["Data"]])
    # get the upper and lower limits
    upper = cf[section][series]['RangeCheck']['upper']
    upr = numpy.array(parse_rangecheck_limit(upper))
    if len(upr) != 12:
        msg = " Need 12 'upper' values, got "+str(len(upr))+" for "+series
        logger.error(msg)
        return
    valid_upper = numpy.max(upr)
    upr = upr[month - 1]
    lower = cf[section][series]['RangeCheck']['lower']
    lwr = numpy.array(parse_rangecheck_limit(lower))
    if len(lwr) != 12:
        msg = " Need 12 'lower' values, got "+str(len(lwr))+" for "+series
        logger.error(msg)
        return
    valid_lower = numpy.min(lwr)
    lwr = lwr[month - 1]
    # get the data, flag and attributes
    var = pfp_utils.GetVariable(ds, series)
    # convert the data from a masked array to an ndarray so the range check works
    var["Data"] = numpy.ma.filled(var["Data"], fill_value=c.missing_value)
    # get the indices of elements outside this range
    idx = numpy.where((var["Data"] < lwr)|(var["Data"] > upr))[0]
    # set elements outside range to missing and set the QC flag
    var["Data"][idx] = numpy.float64(c.missing_value)
    var["Flag"][idx] = numpy.int32(code)
    # update the variable attributes
    var["Attr"]["rangecheck_lower"] = cf[section][series]["RangeCheck"]["lower"]
    var["Attr"]["rangecheck_upper"] = cf[section][series]["RangeCheck"]["upper"]
    var["Attr"]["valid_range"] = str(valid_lower) + "," + str(valid_upper)
    # and now put the data back into the data structure
    pfp_utils.CreateVariable(ds, var)
    # now we can return
    return

def do_SONICcheck(cf, ds, code=3):
    """
    Purpose:
     Does an implicit dependency check using the sonic diagnostic.
    Usage:
    Side effects:
    Assumptions:
    History:
     Started life in OzFluxQC as do_CSATcheck()
    Author: PRI
    Date: Back in the day
    """
    # check to see if the user has disabled the IRGA check
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "SONIC_Check", default="Yes")
    if opt.lower() == "no":
        msg = " *** SONIC_Check disbled in control file"
        logger.warning(msg)
        return
    msg = " Doing the SONIC check"
    logger.info(msg)
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    labels = list(ds.root["Variables"].keys())
    # list of variables to be modified by this QC check
    dependents = ["UxA", "UxC", "UxT", "UxUy", "UxUz",
                  "Ux_SONIC_Av", "Ux_SONIC_Sd", "Ux_SONIC_Vr",
                  "UyA", "UyC", "UyT", "UyUz",
                  "Uy_SONIC_Av", "Uy_SONIC_Sd", "Uy_SONIC_Vr",
                  "UzA", "UzC", "UzT",
                  "Uz_SONIC_Av", "Uz_SONIC_Sd", "Uz_SONIC_Vr",
                  "Tv_SONIC_Av", "Tv_SONIC_Sd", "Tv_SONIC_Vr",
                  "U_SONIC_Av", "U_SONIC_Sd", "U_SONIC_Vr",
                  "V_SONIC_Av", "V_SONIC_Sd", "V_SONIC_Vr",
                  "W_SONIC_Av", "W_SONIC_Sd", "W_SONIC_Vr"]
    # check these are in the data structure
    for label in list(dependents):
        if label not in labels:
            dependents.remove(label)
    # return if there are no dependents to check
    if len(dependents) == 0:
        msg = "  No dependent variables found, skipping SONIC check ..."
        logger.info(msg)
        return
    # list for conditional variables
    conditionals = []
    # check if we have the SONIC diagnostic
    got_diag = False
    for diag in ["Diag_SONIC", "Diag_CSAT"]:
        if diag in labels:
            got_diag = True
            conditionals.append(diag)
            break
    if not got_diag:
        msg = " Sonic diagnostic (Diag_SONIC) not found in data"
        logger.warning(msg)
    # check if we have Uz standard deviation or vaiance (only use one)
    got_uz = False
    for uz in ["Uz_SONIC_Sd", "W_SONIC_Sd", "Uz_SONIC_Vr", "W_SONIC_Vr"]:
        if uz in labels:
            got_uz = True
            conditionals.append(uz)
            break
    if not got_uz:
        msg = " Neither Uz or W standard deviation or variance used in SONIC check (not in data structure)"
        logger.warning(msg)
    # check if we have Tv standard deviation or variance (only use one)
    got_tv = False
    for tv in ["Tv_SONIC_Sd", "Tv_SONIC_Vr"]:
        if tv in labels:
            got_tv = True
            conditionals.append(tv)
            break
    if not got_tv:
        msg = " Tv standard deviation or variance not used in SONIC check (not in data structure)"
        logger.warning(msg)
    # return if we found no conditionals
    if len(conditionals) == 0:
        msg = " No conditional variables found, skipping SONIC check ..."
        logger.warning(msg)
        return
    # create an index series, 0 ==> not OK, 1 ==> OK
    cidx = numpy.ones(nrecs, dtype=int)
    for conditional in conditionals:
        variable = pfp_utils.GetVariable(ds, conditional)
        idx = numpy.where(numpy.ma.getmaskarray(variable["Data"]) == True)[0]
        msg = "  SONIC check: " + conditional + " rejected " + str(numpy.size(idx)) + " points"
        logger.info(msg)
        cidx[idx] = int(0)
    rejected = numpy.count_nonzero(cidx == 0)
    percent = int(numpy.rint(100*rejected/nrecs))
    msg = "  SONIC check: total number of points rejected was " + str(rejected)
    msg += " (" + str(percent) + "%)"
    logger.info(msg)
    # use the conditional series to mask the dependents
    for dependent in dependents:
        variable = pfp_utils.GetVariable(ds, dependent)
        variable["Data"] = numpy.ma.masked_where(cidx == int(0), variable["Data"])
        idx = numpy.where(cidx == int(0))[0]
        variable["Flag"][idx] = int(code)
        variable["Attr"]["sonic_check"] = ",".join(dependents)
        pfp_utils.CreateVariable(ds, variable)
    return

def do_uppercheck(cf,ds,section,series,code=2):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: February 2017
    """
    # check to see if UpperCheck requested for this variable
    if "UpperCheck" not in cf[section][series]:
        return
    # Check to see if limits have been specified
    if len(list(cf[section][series]["UpperCheck"].keys())) == 0:
        msg = "do_uppercheck: no date ranges specified"
        logger.info(msg)
        return

    ldt = ds.root["Variables"]["DateTime"]["Data"]
    ts = int(float(ds.root["Attributes"]["time_step"]))
    var = pfp_utils.GetVariable(ds, series)

    uc_list = list(cf[section][series]["UpperCheck"].keys())
    for n,item in enumerate(uc_list):
        # this should be a list and we should probably check for compliance
        upr_string = cf[section][series]["UpperCheck"][item]
        var["Attr"]["uppercheck_"+str(n)] = str(upr_string)
        upr_list = upr_string.split(",")
        start_date = dateutil.parser.parse(upr_list[0])
        su = float(upr_list[1])
        end_date = dateutil.parser.parse(upr_list[2])
        eu = float(upr_list[3])
        # get the start and end indices
        si = pfp_utils.GetDateIndex(ldt, start_date, ts=ts, default=0, match="exact")
        ei = pfp_utils.GetDateIndex(ldt, end_date, ts=ts, default=len(ldt)-1, match="exact")
        seg_data = var["Data"][si:ei+1]
        seg_flag = var["Flag"][si:ei+1]
        x = numpy.arange(si, ei+1, 1)
        upper = numpy.interp(x, [si, ei], [su, eu])
        index = numpy.ma.where((seg_data > upper))[0]
        seg_data[index] = numpy.ma.masked
        seg_flag[index] = numpy.int32(code)
        var["Data"][si:ei+1] = seg_data
        var["Flag"][si:ei+1] = seg_flag
    # now put the data back into the data structure
    pfp_utils.CreateVariable(ds, var)
    return

def do_wd_offset(cf, ds):
    labels = list(cf["Variables"].keys())
    for label in labels:
        if pfp_utils.haskey(cf, label, "Wd offset"):
            pfp_ts.ApplyWdOffset(cf, ds, label)

def parse_rangecheck_limit(s):
    """
    Purpose:
     Parse the RangeCheck upper or lower value string.
     Valid string formats are;
      '100'
      '[100]*12'
      '[1,2,3,4,5,6,7,8,9,10,11,12]'
      '1,2,3,4,5,6,7,8,9,10,11,12'
    Author: PRI
    Date: August 2018
    """
    val_list = []
    try:
        val_list = [float(s)]*12
    except ValueError:
        if ("[" in s) and ("]" in s) and ("*" in s):
            val = s[s.index("[")+1:s.index("]")]
            val_list = [float(val)]*12
        elif ("[" in s) and ("]" in s) and ("," in s) and ("*" not in s):
            s = s.replace("[","").replace("]","")
            val_list = [float(n) for n in s.split(",")]
        elif ("[" not in s) and ("]" not in s) and ("," in s) and ("*" not in s):
            val_list = [float(n) for n in s.split(",")]
        else:
            msg = " Unrecognised format for RangeCheck limit ("+s+")"
            logger.error(msg)
    return val_list

def rangecheckserieslower(data,lower):
    if lower is None:
        logger.info(' rangecheckserieslower: no lower bound set')
        return data
    if numpy.ma.isMA(data):
        data = numpy.ma.masked_where(data<lower,data)
    else:
        index = numpy.where((abs(data-numpy.float64(c.missing_value))>c.eps)&(data<lower))[0]
        data[index] = numpy.float64(c.missing_value)
    return data

def rangecheckseriesupper(data,upper):
    if upper is None:
        logger.info(' rangecheckserieslower: no upper bound set')
        return data
    if numpy.ma.isMA(data):
        data = numpy.ma.masked_where(data>upper,data)
    else:
        index = numpy.where((abs(data-numpy.float64(c.missing_value))>c.eps)&(data>upper))[0]
        data[index] = numpy.float64(c.missing_value)
    return data

def UpdateVariableAttributes_QC(cf, variable):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI
    Date: November 2016
    """
    label = variable["Label"]
    section = pfp_utils.get_cfsection(cf, label, mode='quiet')
    if section == None:
        return
    if "RangeCheck" not in cf[section][label]:
        return
    if "lower" in cf[section][label]["RangeCheck"]:
        variable["Attr"]["rangecheck_lower"] = cf[section][label]["RangeCheck"]["lower"]
    if "upper" in cf[section][label]["RangeCheck"]:
        variable["Attr"]["rangecheck_upper"] = cf[section][label]["RangeCheck"]["upper"]
    return
