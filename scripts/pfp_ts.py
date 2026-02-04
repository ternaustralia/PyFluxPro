# standard
import copy
import datetime
import inspect
import logging
import os
# 3d party
import numpy
from matplotlib.dates import date2num
from scipy import interpolate
# PFP
from scripts import constants as c
from scripts import meteorologicalfunctions as pfp_mf
from scripts import pfp_func_units
from scripts import pfp_func_stats
from scripts import pfp_func_transforms
from scripts import pfp_io
from scripts import pfp_utils
from scripts import pysolar

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

def ApplyLinear(cf,ds,ThisOne):
    """
        Applies a linear correction to variable passed from pfp_ls. Time period
        to apply the correction, slope and offset are specified in the control
        file.

        Usage pfp_ts.ApplyLinear(cf,ds,x)
        cf: control file
        ds: data structure
        x: input/output variable in ds.  Example: 'Cc_7500_Av'
        """
    if ThisOne not in list(ds.root["Variables"].keys()): return
    if pfp_utils.incf(cf,ThisOne) and pfp_utils.haskey(cf,ThisOne,'Linear'):
        msg = " Applying linear correction to " + ThisOne
        logger.info(msg)
        data = numpy.ma.masked_where(ds.root["Variables"][ThisOne]['Data']==float(c.missing_value),ds.root["Variables"][ThisOne]['Data'])
        flag = ds.root["Variables"][ThisOne]['Flag'].copy()
        ldt = ds.root["Variables"]['DateTime']['Data']
        LinearList = list(cf['Variables'][ThisOne]['Linear'].keys())
        for i in range(len(LinearList)):
            linear_dates_string = cf['Variables'][ThisOne]['Linear'][str(i)]
            linear_dates_list = linear_dates_string.split(",")
            try:
                dt = datetime.datetime.strptime(linear_dates_list[0],'%Y-%m-%d %H:%M')
                si = pfp_utils.find_nearest_value(ldt, dt)
            except ValueError:
                si = 0
            try:
                dt = datetime.datetime.strptime(linear_dates_list[1],'%Y-%m-%d %H:%M')
                ei = pfp_utils.find_nearest_value(ldt, dt)
            except ValueError:
                ei = -1
            Slope = float(linear_dates_list[2])
            Offset = float(linear_dates_list[3])
            data[si:ei] = Slope * data[si:ei] + Offset
            index = numpy.where(flag[si:ei]==0)[0]
            flag[si:ei][index] = numpy.int32(10)
            ds.root["Variables"][ThisOne]['Data'] = numpy.ma.filled(data,float(c.missing_value)).astype(numpy.float64)
            ds.root["Variables"][ThisOne]['Flag'] = flag

def ApplyWdOffset(cf, ds, label):
    """
    Purpose:
     Apply an offset correction for a specified date range to a wind direction variable.
    Usage:
     pfp_ts.ApplyWdOffset(cf, da, label)
    """
    labels = list(ds.root["Variables"].keys())
    if label not in labels:
        return
    if pfp_utils.incf(cf, label) and pfp_utils.haskey(cf, label, "Wd offset"):
        msg = "  Applying offset to " + label
        logger.info(msg)
        data = numpy.ma.masked_where(ds.root["Variables"][label]["Data"]==float(c.missing_value), ds.root["Variables"][label]['Data'])
        flag = ds.root["Variables"][label]["Flag"].copy()
        ldt = ds.root["Variables"]["DateTime"]["Data"]

        date_ranges = list(cf["Variables"][label]["Wd offset"].keys())
        for i in range(len(date_ranges)):
            dates_string = cf["Variables"][label]["Wd offset"][str(i)]
            dates_list = dates_string.split(",")
            try:
                dt = datetime.datetime.strptime(dates_list[0], "%Y-%m-%d %H:%M")
                si = pfp_utils.find_nearest_value(ldt, dt)
            except ValueError:
                si = 0
            try:
                dt = datetime.datetime.strptime(dates_list[1], "%Y-%m-%d %H:%M")
                ei = pfp_utils.find_nearest_value(ldt, dt)
            except ValueError:
                ei = -1
            offset = float(dates_list[2])

            data[si:ei] = numpy.ma.mod(data[si:ei] + offset, float(360))
            index = numpy.where(flag[si:ei] == 0)[0]
            flag[si:ei][index] = numpy.int32(10)
            ds.root["Variables"][label]["Data"] = numpy.ma.filled(data, float(c.missing_value)).astype(numpy.float64)
            ds.root["Variables"][label]["Flag"] = flag
    return

def AverageSeriesByElements(cf, ds, Av_out):
    """
        Calculates the average of multiple time series.  Multiple time series
        are entered and a single time series representing the average at each
        observational period is returned.

        Usage pfp_ts.AverageSeriesByElements(cf,ds,Av_out)
        cf: control file object (must contain an entry for Av_out)
        ds: data structure
        Av_out: output variable to ds.  Example: 'Fg'
        Series_in: input variable series in ds.  Example: ['Fg_8cma','Fg_8cmb']
        """
    # sanity checks
    if Av_out not in list(cf['Variables'].keys()):
        return
    if Av_out in ds.info["averageserieslist"]:
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    ones = numpy.ones(nrecs)
    zeros = numpy.zeros(nrecs)
    # get the name of the description variable attribute
    processing_level = ds.root["Attributes"]["processing_level"]
    descr_level = "description_" + processing_level
    # get the list of series to average
    srclist = pfp_utils.GetAverageSeriesKeys(cf, Av_out)
    logger.info(" Averaging " + str(srclist) + "==>" + Av_out)
    # check to see if they are in the data structure
    labels = ds.root["Variables"].keys()
    for label in list(srclist):
        if label not in labels:
            msg = " Variable " + label + " not found in data structure, skipping ..."
            logger.warning(msg)
            srclist.remove(label)
    nSeries = len(srclist)
    if nSeries == 0:
        logger.error("  AverageSeriesByElements: no input series specified for " + str(Av_out))
        return
    avg = pfp_utils.GetVariable(ds, srclist[0])
    labels_averaged = srclist[0]
    if len(srclist) > 1:
        for ThisOne in srclist[1:]:
            labels_averaged = labels_averaged + ", " + ThisOne
            var = pfp_utils.GetVariable(ds, ThisOne)
            avg["Data"] = numpy.ma.vstack((avg["Data"], var["Data"]))
        avg["Data"] = numpy.ma.average(avg["Data"], axis=0)
        avg["Flag"] = numpy.where(numpy.ma.getmaskarray(avg["Data"]) == True, ones, zeros)
    ds.info["averageserieslist"].append(Av_out)
    # update the attributes
    tmp = "Element-wise average of series " + labels_averaged
    pfp_utils.append_to_attribute(avg["Attr"], {descr_level: tmp})
    avg["Label"] = Av_out
    pfp_utils.CreateVariable(ds, avg)

def CalculateAvailableEnergy(ds, Fa_out="Fa", Fn_in="Fn", Fg_in="Fg"):
    """
        Calculate the average energy as Fn - G.

        Usage pfp_ts.CalculateAvailableEnergy(ds, Fa_out='Fa', Fn_in='Fn', Fg_in='Fg')
        ds: data structure
        Fa_out: output available energy variable to ds.  Example: 'Fa'
        Fn_in: input net radiation in ds.  Example: 'Fn'
        Fg_in: input ground heat flux in ds.  Example: 'Fg'
        """
    msg = " Calculating available energy from Fn and Fg"
    logger.info(msg)
    # make an empty Fa variable
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    Fa = pfp_utils.CreateEmptyVariable(Fa_out, nrecs)
    if Fn_in not in list(ds.root["Variables"].keys()):
        msg = " Series " + Fn_in + " not found in data file"
        logger.warning(msg)
    elif Fg_in not in list(ds.root["Variables"].keys()):
        msg = " Series " + Fg_in + " not found in data file"
        logger.warning(msg)
    else:
        processing_level = ds.root["Attributes"]["processing_level"]
        descr_level = "description_" + processing_level
        ones = numpy.ones(nrecs, dtype=numpy.int32)
        zeros = numpy.zeros(nrecs, dtype=numpy.int32)
        Fn = pfp_utils.GetVariable(ds, Fn_in)
        Fg = pfp_utils.GetVariable(ds, Fg_in)
        Fa["Data"] = Fn["Data"] - Fg["Data"]
        mask = numpy.ma.getmaskarray(Fa["Data"])
        Fa["Flag"] = numpy.where(mask == True, ones, zeros)
        Fa["Attr"] = {"long_name": "Available energy",
                       descr_level: "Calculated from " + Fn_in + ", " + Fg_in,
                      "units": "W/m^2", "statistic_type": "average"}
        if (("instrument" in Fn["Attr"]) and ("instrument" in Fg["Attr"])):
            Fa["Attr"]["instrument"] = Fn["Attr"]["instrument"] + ", " + Fg["Attr"]["instrument"]
    pfp_utils.CreateVariable(ds, Fa)
    return

def CalculateET(ds, info):
    """
    Purpose:
     Calculate ET from Fe
    Usage:
     pfp_ts.CalculateET(ds)
      where ds is a data structure
    Side effects:
     Series to hold the ET data are created in ds.
    Author: PRI
    Date: June 2015
    """
    msg = " Calculating ET from Fe"
    logger.info(msg)
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    labels = list(ds.root["Variables"].keys())
    if "EvapoTranspiration" not in list(info.keys()):
        replace = False
        info["EvapoTranspiration"] = {}
        dsv = ds.root["Variables"]
        labels = list(dsv.keys())
        fe_labels = [l for l in labels if l[0:2] == "Fe"]
        for fe_label in fe_labels:
            if "standard_name" in dsv[fe_label]["Attr"]:
                if dsv[fe_label]["Attr"]["standard_name"] == "surface_upward_latent_heat_flux":
                    et_label = fe_label.replace("Fe", "ET")
                    info["EvapoTranspiration"][et_label] = {"Fe": fe_label}
    else:
        replace = True
    iET = info["EvapoTranspiration"]
    # loop over the latent heat fluxes
    et_labels = list(iET.keys())
    for et_label in et_labels:
        # get the latent heat flux
        fe_label = iET[et_label]["Fe"]
        Fe = pfp_utils.GetVariable(ds, fe_label)
        if "standard_name" in Fe["Attr"]:
            if Fe["Attr"]["standard_name"] == "surface_upward_latent_heat_flux":
                if ((et_label in labels) and not replace):
                    msg = "  ET variable " + et_label + " already exists, not replacing ..."
                    logger.warning(msg)
                else:
                    ET = pfp_utils.CreateEmptyVariable(et_label, nrecs)
                    ET["Data"] = Fe["Data"]/c.Lv
                    ET["Flag"] = Fe["Flag"]
                    ET["Attr"]["long_name"] = "Evapo-transpiration"
                    ET["Attr"]["standard_name"] = "water_evapotranspiration_flux"
                    ET["Attr"]["units"] = "kg/m^2/s"
                    pfp_utils.CreateVariable(ds, ET)
            else:
                continue
        else:
            continue
    return

def CalculateFluxes(cf, ds):
    """
        Calculate the fluxes from the rotated covariances.

        Usage pfp_ts.CalculateFluxes(ds)
        ds: data structure

        Pre-requisite: CoordRotation2D

        Accepts meteorological constants or variables
        """
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs, dtype=numpy.int32)
    ones = numpy.ones(nRecs, dtype=numpy.int32)
    rhom = pfp_utils.GetVariable(ds, "rhom")
    RhoCp = pfp_utils.GetVariable(ds, "RhoCp")
    Lv = pfp_utils.GetVariable(ds, "Lv")

    logger.info(" Calculating fluxes from covariances")
    if "wT" in list(ds.root["Variables"].keys()):
        ok_units = ["m.degC/s", "degC.m/s"]
        wT = pfp_utils.GetVariable(ds, "wT")
        if wT["Attr"]["units"] in ok_units:
            Fhv = RhoCp["Data"]*wT["Data"]
            attr = {"long_name": "Virtual heat flux", "units": "W/m^2",
                    descr_level: "Rotated to natural wind coordinates",
                    "statistic_type": "average"}
            for item in ["instrument", "height"]:
                if item in wT["Attr"]:
                    attr[item] = wT["Attr"][item]
            flag = numpy.where(numpy.ma.getmaskarray(Fhv) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, {"Label": "Fhv", "Data": Fhv, "Flag": flag, "Attr": attr})
        else:
            logger.error(" CalculateFluxes: Incorrect units for wT, Fhv not calculated")
    else:
        logger.error("  CalculateFluxes: wT not found, Fhv not calculated")
    if "wA" in list(ds.root["Variables"].keys()):
        wA = pfp_utils.GetVariable(ds, "wA")
        if wA["Attr"]["units"] == "g/m^2/s":
            Fe = Lv["Data"]*wA["Data"]/float(1000)
            attr = {"long_name": "Latent heat flux", "units": "W/m^2",
                    "standard_name": "surface_upward_latent_heat_flux",
                    descr_level: "Rotated to natural wind coordinates",
                    "statistic_type": "average"}
            for item in ["instrument", "height"]:
                if item in wA["Attr"]:
                    attr[item] = wA["Attr"][item]
            flag = numpy.where(numpy.ma.getmaskarray(Fe) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, {"Label": "Fe", "Data": Fe, "Flag": flag, "Attr": attr})
        else:
            logger.error(" CalculateFluxes: Incorrect units for wA, Fe not calculated")
    else:
        logger.error("  CalculateFluxes: wA not found, Fe not calculated")
    if "wC" in list(ds.root["Variables"].keys()):
        wC = pfp_utils.GetVariable(ds, "wC")
        if wC["Attr"]["units"] == "mg/m^2/s":
            Fco2 = wC["Data"]
            attr = {"long_name": "CO2 flux", "units": "mg/m^2/s",
                    descr_level: "Rotated to natural wind coordinates",
                    "statistic_type": "average"}
            for item in ["instrument", "height"]:
                if item in wC["Attr"]:
                    attr[item] = wC["Attr"][item]
            flag = numpy.where(numpy.ma.getmaskarray(Fco2) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, {"Label": "Fco2", "Data": Fco2, "Flag": flag, "Attr": attr})
        else:
            logger.error(" CalculateFluxes: Incorrect units for wC, Fco2 not calculated")
    else:
        logger.error("  CalculateFluxes: wC not found, Fco2 not calculated")
    if "uw" in list(ds.root["Variables"].keys()):
        if "vw" in list(ds.root["Variables"].keys()):
            uw = pfp_utils.GetVariable(ds, "uw")
            vw = pfp_utils.GetVariable(ds, "vw")
            vs = uw["Data"]*uw["Data"] + vw["Data"]*vw["Data"]
            Fm = rhom["Data"]*numpy.ma.sqrt(vs)
            us = numpy.ma.sqrt(numpy.ma.sqrt(vs))
            attr = {"long_name": "Momentum flux", "units": "kg/m/s^2",
                    "standard_name": "magnitude_of_surface_downward_stress",
                    descr_level: "Rotated to natural wind coordinates",
                    "statistic_type": "average"}
            for item in ["instrument", "height"]:
                if item in uw["Attr"]:
                    attr[item] = uw["Attr"][item]
            flag = numpy.where(numpy.ma.getmaskarray(Fm) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, {"Label": "Fm", "Data": Fm, "Flag": flag, "Attr": attr})
            pfp_utils.CreateVariable(ds, {"Label": "Fm_PFP", "Data": Fm, "Flag": flag, "Attr": attr})
            attr = {"long_name": "Friction velocity", "units": "m/s",
                    descr_level: "Rotated to natural wind coordinates",
                    "statistic_type": "average"}
            for item in ["instrument", "height"]:
                if item in uw["Attr"]:
                    attr[item] = uw["Attr"][item]
            flag = numpy.where(numpy.ma.getmaskarray(us) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, {"Label": "ustar", "Data": us, "Flag": flag, "Attr": attr})
            pfp_utils.CreateVariable(ds, {"Label": "ustar_PFP", "Data": us, "Flag": flag, "Attr": attr})
        else:
            logger.error("  CalculateFluxes: vw not found, Fm and ustar not calculated")
    else:
        logger.error("  CalculateFluxes: uw not found, Fm and ustar not calculated")

def CalculateHumidities(ds):
    """
    Purpose:
     Calculate any missing humidities from whatever is available.
     If absolute humidity (AH) is available then;
      - calculate specific humidity (SH) if it is not present
      - calculate relative humidity (RH) if it is not present
     If specific humidity (SH) is available then;
      - calculate absolute humidity (AH) if it is not present
      - calculate relative humidity (RH) if it is not present
     If reative humidity (RH) is available then;
      - calculate specific humidity (SH) if it is not present
      - calculate relative humidity (RH) if it is not present
    Usage:
     pfp_ts.CalculateHumidities(ds)
    Date:
     March 2015
    Author: PRI
    """
    if "AH" not in list(ds.root["Variables"].keys()):
        if "SH" in list(ds.root["Variables"].keys()):
            msg = " Calculating absolute humidity from specific humidity"
            logger.info(msg)
            AbsoluteHumidityFromSpecificHumidity(ds)   # calculate AH from SH
        elif "RH" in list(ds.root["Variables"].keys()):
            msg = " Calculating absolute humidity from relative humidity"
            logger.info(msg)
            AbsoluteHumidityFromRelativeHumidity(ds)   # calculate AH from RH
    if "SH" not in list(ds.root["Variables"].keys()):
        if "AH" in list(ds.root["Variables"].keys()):
            msg = " Calculating specific humidity from absolute humidity"
            logger.info(msg)
            SpecificHumidityFromAbsoluteHumidity(ds)
        elif "RH" in list(ds.root["Variables"].keys()):
            msg = " Calculating specific humidity from relative humidity"
            logger.info(msg)
            SpecificHumidityFromRelativeHumidity(ds)
    if "RH" not in list(ds.root["Variables"].keys()):
        if "AH" in list(ds.root["Variables"].keys()):
            msg = " Calculating relative humidity from absolute humidity"
            logger.info(msg)
            RelativeHumidityFromAbsoluteHumidity(ds)
        elif "SH" in list(ds.root["Variables"].keys()):
            msg = " Calculating relative humidity from specific humidity"
            logger.info(msg)
            RelativeHumidityFromSpecificHumidity(ds)
    return

def CalculateHumiditiesAfterGapFill(ds, info):
    """
    Purpose:
     Check to see which humidity quantities (AH, RH or SH) have been gap filled
     and, if necessary, calculate the other humidity quantities from the gap
     filled one.
    Usage:
     pfp_ts.CalculateHumiditiesAfterGapFill(ds, info)
     where ds is a data structure
    Author: PRI
    Date: April 2015
    """
    # create an empty list
    alt_list = []
    # check to see if there was any gap filling using data from alternate sources
    if "GapFillFromAlternate" in list(info.keys()):
        ia = info["GapFillFromAlternate"]
        # if so, get a list of the quantities gap filled from alternate sources
        alt_list = list(set([ia["outputs"][item]["target"] for item in list(ia["outputs"].keys())]))
    # create an empty list
    cli_list = []
    # check to see if there was any gap filling from climatology
    if "GapFillFromClimatology" in list(info.keys()):
        ic = info["GapFillFromClimatology"]
        # if so, get a list of the quantities gap filled using climatology
        cli_list = list(set([ic["outputs"][item]["target"] for item in list(ic["outputs"].keys())]))
    # one list to rule them, one list to bind them ...
    gf_list = list(set(alt_list+cli_list))
    # clear out if there was no gap filling
    if len(gf_list)==0: return
    # check to see if absolute humidity (AH) was gap filled ...
    if "AH" in gf_list:
        if "SH" not in gf_list: SpecificHumidityFromAbsoluteHumidity(ds)
        if "RH" not in gf_list: RelativeHumidityFromAbsoluteHumidity(ds)
    # ... or was relative humidity (RH) gap filled ...
    elif "RH" in gf_list:
        if "AH" not in gf_list: AbsoluteHumidityFromRelativeHumidity(ds)
        if "SH" not in gf_list: SpecificHumidityFromRelativeHumidity(ds)
    # ... or was specific humidity (SH) gap filled ...
    elif "SH" in gf_list:
        if "AH" not in gf_list: AbsoluteHumidityFromSpecificHumidity(ds)
        if "RH" not in gf_list: RelativeHumidityFromSpecificHumidity(ds)
    else:
        msg = "No humidities were gap filled!"
        logger.warning(msg)

def AbsoluteHumidityFromRelativeHumidity(ds):
    """ Calculate absolute humidity from relative humidity. """
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "RH"])
    if not ok:
        msg = ",".join(missing) + " missing, AH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating absolute humidity from relative humidity')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    RH = pfp_utils.GetVariable(ds, "RH")
    AH_new = pfp_utils.CreateEmptyVariable("AH", nrecs)
    AH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], RH["Flag"]])
    AH_new["Data"] = pfp_mf.absolutehumidityfromrelativehumidity(Ta["Data"], RH["Data"])
    if "AH" in list(ds.root["Variables"].keys()):
        AH = pfp_utils.GetVariable(ds, "AH")
        index = numpy.where(numpy.ma.getmaskarray(AH["Data"]) == True)[0]
        AH["Data"][index] = AH_new["Data"][index]
        AH["Flag"][index] = AH_new["Flag"][index]
        pfp_utils.append_to_attribute(AH["Attr"], {descr_level: "merged with AH calculated from RH"})
        pfp_utils.CreateVariable(ds, AH)
    else:
        AH_new["Attr"] = {"long_name": "Absolute humidity", "units": "g/m^3",
                          "statistic_type": "average",
                          "standard_name": "mass_concentration_of_water_vapor_in_air",
                          descr_level: "Absoulte humidity calculated from Ta and RH"}
        pfp_utils.CreateVariable(ds, AH_new)
    return

def AbsoluteHumidityFromSpecificHumidity(ds):
    """ Calculate absolute humidity from specific humidity. """
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "ps", "SH"])
    if not ok:
        msg = ",".join(missing) + " missing, AH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(" Calculating absolute humidity from specific humidity")
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    ps = pfp_utils.GetVariable(ds, "ps")
    SH = pfp_utils.GetVariable(ds, "SH")
    AH_new = pfp_utils.CreateEmptyVariable("AH", nrecs)
    AH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], ps["Flag"], SH["Flag"]])
    RH = pfp_mf.relativehumidityfromspecifichumidity(SH["Data"], Ta["Data"], ps["Data"])
    AH_new["Data"] = pfp_mf.absolutehumidityfromrelativehumidity(Ta["Data"], RH)
    if "AH" in list(ds.root["Variables"].keys()):
        AH = pfp_utils.GetVariable(ds, "AH")
        index = numpy.where(numpy.ma.getmaskarray(AH["Data"]) == True)[0]
        AH["Data"][index] = AH_new["Data"][index]
        AH["Flag"][index] = AH_new["Flag"][index]
        pfp_utils.append_to_attribute(AH["Attr"], {descr_level: "merged with AH calculated from SH"})
        pfp_utils.CreateVariable(ds, AH)
    else:
        AH_new["Attr"] = {"long_name": "Absolute humidity", "units": "g/m^3",
                          "statistic_type": "average",
                          "standard_name": "mass_concentration_of_water_vapor_in_air",
                          descr_level: "Absoulte humidity calculated from Ta, ps and SH"}
        pfp_utils.CreateVariable(ds, AH_new)
    return

def RelativeHumidityFromDewpoint(ds):
    """ Calculate relative humidity from dewpoint. """
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating relative humidity from dewpoint')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    Td = pfp_utils.GetVariable(ds, "Td")
    RH_new = pfp_utils.CreateEmptyVariable("RH", nrecs)
    RH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], Td["Flag"]])
    # relative humidity in units of percent
    RH_new["Data"] = pfp_mf.relativehumidityfromdewpoint(Td["Data"], Ta["Data"])
    if "RH" in list(ds.root["Variables"].keys()):
        RH = pfp_utils.GetVariable(ds, "RH")
        index = numpy.where(numpy.ma.getmaskarray(RH["Data"]) == True)[0]
        RH["Data"][index] = RH_new["Data"][index]
        RH["Flag"][index] = RH_new["Flag"][index]
        pfp_utils.append_to_attribute(RH["Attr"], {descr_level: "merged with RH calculated from AH"})
        pfp_utils.CreateVariable(ds, RH)
    else:
        RH_new["Attr"] = {"long_name": "Relative humidity", "units": "percent",
                          "statistic_type": "average",
                          "standard_name": "relative_humidity",
                          descr_level: "Relative humidity calculated from AH and Ta"}
        pfp_utils.CreateVariable(ds, RH_new)
    return

def RelativeHumidityFromSpecificHumidity(ds):
    """ Calculate relative humidity from specific humidity. """
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "ps", "SH"])
    if not ok:
        msg = ",".join(missing) + " missing, RH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating relative humidity from specific humidity')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    ps = pfp_utils.GetVariable(ds, "ps")
    SH = pfp_utils.GetVariable(ds, "SH")
    RH_new = pfp_utils.CreateEmptyVariable("RH", nrecs)
    RH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], ps["Flag"], SH["Flag"]])
    RH_new["Data"] = pfp_mf.relativehumidityfromspecifichumidity(SH["Data"], Ta["Data"], ps["Data"])
    if "RH" in list(ds.root["Variables"].keys()):
        RH = pfp_utils.GetVariable(ds, "RH")
        index = numpy.where(numpy.ma.getmaskarray(RH["Data"]) == True)[0]
        RH["Data"][index] = RH_new["Data"][index]
        RH["Flag"][index] = RH_new["Flag"][index]
        pfp_utils.append_to_attribute(RH["Attr"], {descr_level: "merged with RH calculated from SH"})
        pfp_utils.CreateVariable(ds, RH)
    else:
        RH_new["Attr"] = {"long_name": "Relative humidity", "units": "percent",
                          "standard_name": "relative_humidity", "statistic_type": "average",
                          descr_level: "Relative humidity calculated from SH, Ta and ps"}
        pfp_utils.CreateVariable(ds, RH_new)
    return

def RelativeHumidityFromAbsoluteHumidity(ds):
    """ Calculate relative humidity from absolute humidity. """
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "AH"])
    if not ok:
        msg = ",".join(missing) + " missing, RH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating relative humidity from absolute humidity')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    AH = pfp_utils.GetVariable(ds, "AH")
    RH_new = pfp_utils.CreateEmptyVariable("RH", nrecs)
    RH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], AH["Flag"]])
    # relative humidity in units of percent
    RH_new["Data"] = pfp_mf.relativehumidityfromabsolutehumidity(AH["Data"], Ta["Data"])
    if "RH" in list(ds.root["Variables"].keys()):
        RH = pfp_utils.GetVariable(ds, "RH")
        index = numpy.where(numpy.ma.getmaskarray(RH["Data"]) == True)[0]
        RH["Data"][index] = RH_new["Data"][index]
        RH["Flag"][index] = RH_new["Flag"][index]
        pfp_utils.append_to_attribute(RH["Attr"], {descr_level: "merged with RH calculated from AH"})
        pfp_utils.CreateVariable(ds, RH)
    else:
        RH_new["Attr"] = {"long_name": "Relative humidity", "units": "percent",
                          "statistic_type": "average",
                          "standard_name": "relative_humidity",
                          descr_level: "Relative humidity calculated from AH and Ta"}
        pfp_utils.CreateVariable(ds, RH_new)
    return

def smooth(x,window_len=11,window='hanning'):
    """
    Purpose:
        Smooth the data using a window with requested size.
        This method is based on the convolution of a scaled window with the signal.
        The signal is prepared by introducing reflected copies of the signal
        (with the window size) in both ends so that transient parts are minimized
        in the begining and end part of the output signal.
    Input:
        x: the input signal
        window_len: the dimension of the smoothing window; should be an odd integer
        window: the type of window from 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'
            flat window will produce a moving average smoothing.
    Output:
        the smoothed signal
    Example:
        t=linspace(-2,2,0.1)
        x=sin(t)+randn(len(t))*0.1
        y=smooth(x)
    See also:
        numpy.hanning, numpy.hamming, numpy.bartlett, numpy.blackman, numpy.convolve
        scipy.signal.lfilter
    TODO: the window parameter could be the window itself if an array instead of a string
    Note:
        1) length(output) != length(input), to correct this: return y[(window_len/2-1):-(window_len/2)] instead of just y.
        2) odd values for window_len return output with different length from input
    Source:
        Lifted from scipy Cookbook (http://wiki.scipy.org/Cookbook/SignalSmooth)
    """
    if x.ndim != 1:
        raise ValueError("smooth only accepts 1 dimension arrays.")
    if x.size < window_len:
        raise ValueError("Input vector needs to be bigger than window size.")
    if window_len<3:
        return x
    if not window in ['flat', 'hanning', 'hamming', 'bartlett', 'blackman']:
        raise ValueError("Window is on of 'flat', 'hanning', 'hamming', 'bartlett', 'blackman'")
    s=numpy.r_[x[window_len-1:0:-1],x,x[-1:-window_len:-1]]
    if window == 'flat': #moving average
        w=numpy.ones(window_len,'d')
    else:
        w=eval('numpy.'+window+'(window_len)')
    y=numpy.convolve(w/w.sum(),s,mode='valid')
#    return y
    return y[(window_len//2-1):-(window_len//2)]

def SpecificHumidityFromAbsoluteHumidity(ds):
    """ Calculate specific humidity from absolute humidity. """
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "ps", "AH"])
    if not ok:
        msg = ",".join(missing) + " missing, SH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating specific humidity from absolute humidity')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds,"Ta")
    ps = pfp_utils.GetVariable(ds,"ps")
    AH = pfp_utils.GetVariable(ds,"AH")
    SH_new = pfp_utils.CreateEmptyVariable("SH", nrecs)
    SH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], ps["Flag"], AH["Flag"]])
    RH = pfp_mf.relativehumidityfromabsolutehumidity(AH["Data"], Ta["Data"])
    SH_new["Data"] = pfp_mf.specifichumidityfromRH(RH, Ta["Data"], ps["Data"])
    if "SH" in list(ds.root["Variables"].keys()):
        SH = pfp_utils.GetVariable(ds, "SH")
        index = numpy.where(numpy.ma.getmaskarray(SH["Data"]) == True)[0]
        SH["Data"][index] = SH_new["Data"][index]
        SH["Flag"][index] = SH_new["Flag"][index]
        pfp_utils.append_to_attribute(SH["Attr"], {descr_level: "merged with SH calculated from AH"})
        pfp_utils.CreateVariable(ds, SH)
    else:
        SH_new["Attr"] = {"long_name": "Specific humidity", "units": "kg/kg",
                          "standard_name": "specific_humidity",
                          "statistic_type": "average",
                          descr_level: "Specific humidity calculated from AH, Ta and ps"}
        pfp_utils.CreateVariable(ds, SH_new)
    return

def SpecificHumidityFromRelativeHumidity(ds):
    """ Calculate specific humidity from relative humidity."""
    ok, missing = pfp_utils.variables_in_datastructure(ds, ["Ta", "ps", "RH"])
    if not ok:
        msg = ",".join(missing) + " missing, SH not calculated"
        logger.warning(msg)
        return
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    logger.info(' Calculating specific humidity from relative humidity')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Ta = pfp_utils.GetVariable(ds, "Ta")
    ps = pfp_utils.GetVariable(ds, "ps")
    RH = pfp_utils.GetVariable(ds, "RH")
    SH_new = pfp_utils.CreateEmptyVariable("SH", nrecs)
    SH_new["Flag"] = pfp_utils.MergeQCFlag([Ta["Flag"], ps["Flag"], RH["Flag"]])
    SH_new["Data"] = pfp_mf.specifichumidityfromRH(RH["Data"], Ta["Data"], ps["Data"])
    if "SH" in list(ds.root["Variables"].keys()):
        SH = pfp_utils.GetVariable(ds, "SH")
        index = numpy.where(numpy.ma.getmaskarray(SH["Data"]) == True)[0]
        SH["Data"][index] = SH_new["Data"][index]
        SH["Flag"][index] = SH_new["Flag"][index]
        pfp_utils.append_to_attribute(SH["Attr"], {descr_level: "merged with SH calculated from RH"})
        pfp_utils.CreateVariable(ds, SH)
    else:
        SH_new["Attr"] = {"long_name": "Specific humidity", "units": "kg/kg",
                          "standard_name": "specific_humidity",
                          "statistic_type": "average",
                          descr_level: "Specific humidity calculated from AH, Ta and ps"}
        pfp_utils.CreateVariable(ds, SH_new)
    return

def CalculateMeteorologicalVariables(ds, info, Ta_name='Ta', Tv_name='Tv_SONIC_Av',
                                     ps_name='ps', SH_name="SH",AH_name='AH', RH_name='RH'):
    """
    Purpose:
     Add time series of meteorological variables based on fundamental
     relationships (Stull 1988)
    Usage:
     pfp_ts.CalculateMeteorologicalVariables(ds,Ta_name,Tv_name,ps_name,SH_name,AH_name,RH_name)
     where
        ds: data structure
        Ta_name: data series name for air temperature
        Tv_name: data series name for sonic virtual air temperature
        ps_name: data series name for pressure
        AH_name: data series name for absolute humidity
        SH_name : data series name for specific humidity
        RH_name: data series for relative humidity
    Side effects:
     The following variables are added:
        rhom: density of moist air, pfp_mf.densitymoistair(Ta,ps,AH)
        Lv: latent heat of vapourisation, pfp_mf.Lv(Ta)
        SH: specific humidity, pfp_mf.specifichumidity(mr)
            where mr (mixing ratio) = pfp_mf.mixingratio(ps,vp)
        Cpm: specific heat of moist air, pfp_mf.specificheatmoistair(SH)
        VPD: vapour pressure deficit, VPD = VPsat(Ta) - VP
    Author: PRI
    Date: Back in the day
    Modifications:
     June 2022 - rewrote to use pfp_utils.GetVariable() and pfp_utils.CreateVariable()
    """
    msg = " Calculating meteorological variables"
    logger.info(msg)
    iris = info["RemoveIntermediateSeries"]
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    ones = numpy.ones(nrecs, dtype=numpy.int32)
    labels_to_check = [Ta_name, ps_name, AH_name, SH_name]
    ok, missing = pfp_utils.variables_in_datastructure(ds, labels_to_check)
    if not ok:
        msg = ",".join(missing) + " missing, meteorological variables not calculated"
        logger.warning(msg)
        return
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    # get the required data series
    Ta = pfp_utils.GetVariable(ds, Ta_name)
    # deal with possible aliases for the sonic temperature for the time being
    if Tv_name not in list(ds.root["Variables"].keys()):
        # use Tv_CSAT if it is in the data structure, otherwise use Ta
        if "Tv_CSAT_Av" in list(ds.root["Variables"].keys()):
            Tv_name = "Tv_CSAT_Av"
        elif "Tv_CSAT" in list(ds.root["Variables"].keys()):
            Tv_name = "Tv_CSAT"
        else:
            Tv_name = Ta_name
    Tv = pfp_utils.GetVariable(ds, Tv_name)
    ps = pfp_utils.GetVariable(ds, ps_name)
    AH = pfp_utils.GetVariable(ds, AH_name)
    SH = pfp_utils.GetVariable(ds, SH_name)
    # do the calculations
    # vapour pressure from absolute humidity and temperature
    VP = pfp_utils.CreateEmptyVariable("VP", nrecs)
    VP["Data"] = pfp_mf.vapourpressure(AH["Data"], Ta["Data"])
    VP["Attr"] = {"long_name": "Vapour pressure", "units": "kPa",
                  "standard_name": "water_vapor_partial_pressure_in_air",
                  descr_level: "Vapour pressure calculated from AH, Ta and ps",
                  "statistic_type": "average"}
    VP["Flag"] = numpy.where(numpy.ma.getmaskarray(VP["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, VP)
    # saturation vapour pressure
    VPsat = pfp_utils.CreateEmptyVariable("VPsat", nrecs)
    VPsat["Data"] = pfp_mf.VPsat(Ta["Data"])
    VPsat["Attr"] = {"long_name": "Saturation vapour pressure", "units": "kPa",
                     "statistic_type": "average"}
    VPsat["Flag"] = numpy.where(numpy.ma.getmaskarray(VPsat["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, VPsat)
    iris["not_output"].append("VPsat")
    # partial density of dry air
    rhod = pfp_utils.CreateEmptyVariable("rhod", nrecs)
    rhod["Data"] = pfp_mf.densitydryair(Ta["Data"], ps["Data"], VP["Data"])
    rhod["Attr"] = {"long_name": "Density of dry air", "units": "kg/m^3",
                    "statistic_type": "average"}
    rhod["Flag"] = numpy.where(numpy.ma.getmaskarray(rhod["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, rhod)
    iris["not_output"].append("rhod")
    # density of moist air
    rhom = pfp_utils.CreateEmptyVariable("rhom", nrecs)
    rhom["Data"] = pfp_mf.densitymoistair(Ta["Data"], ps["Data"], VP["Data"])
    rhom["Attr"] = {"long_name": "Density of moist air", "units": "kg/m^3",
                    "standard_name": "air_density", "statistic_type": "average"}
    rhom["Flag"] = numpy.where(numpy.ma.getmaskarray(rhom["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, rhom)
    iris["not_output"].append("rhom")
    # partial density of water vapour
    rhow = pfp_utils.CreateEmptyVariable("rhow", nrecs)
    rhow["Data"] = pfp_mf.densitywatervapour(Ta["Data"], VP["Data"])
    rhow["Attr"] = {"long_name": "Partial density of water vapour", "units": "kg/m^3",
                    "statistic_type": "average"}
    rhow["Flag"] = numpy.where(numpy.ma.getmaskarray(rhow["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, rhow)
    iris["not_output"].append("rhow")
    # latent heat of vapourisation
    Lv = pfp_utils.CreateEmptyVariable("Lv", nrecs)
    Lv["Data"] = pfp_mf.Lv(Ta["Data"])
    Lv["Attr"] = {"long_name": "Latent heat of vapourisation", "units": "J/kg",
                  "statistic_type": "average"}
    Lv["Flag"] = numpy.where(numpy.ma.getmaskarray(Lv["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, Lv)
    iris["not_output"].append("Lv")
    # saturation mixing ratio
    mrsat = pfp_mf.mixingratio(ps["Data"], VPsat["Data"])
    # saturation specific humidity from saturation mixing ratio
    SHsat = pfp_mf.specifichumidity(mrsat)
    # specific heat capacity of dry air
    Cpd = pfp_utils.CreateEmptyVariable("Cpd", nrecs)
    Cpd["Data"] = pfp_mf.specificheatcapacitydryair(Tv["Data"])
    Cpd["Attr"] = {"long_name": "Specific heat capacity of dry air", "units": "J/kg/K",
                   "statistic_type": "average"}
    Cpd["Flag"] = numpy.where(numpy.ma.getmaskarray(Cpd["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, Cpd)
    iris["not_output"].append("Cpd")
    # specific heat capacity of water vapour
    Cpw = pfp_utils.CreateEmptyVariable("Cpw", nrecs)
    Cpw["Data"] = pfp_mf.specificheatcapacitywatervapour(Ta["Data"], AH["Data"])
    Cpw["Attr"] = {"long_name": "Specific heat capacity of water vapour", "units": "J/kg/K",
                   "statistic_type": "average"}
    Cpw["Flag"] = numpy.where(numpy.ma.getmaskarray(Cpw["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, Cpw)
    iris["not_output"].append("Cpw")
    # product of air density and specific heat capacity
    RhoCp = pfp_utils.CreateEmptyVariable("RhoCp", nrecs)
    RhoCp["Data"] = pfp_mf.densitytimesspecificheat(rhow["Data"], Cpw["Data"],
                                                    rhod["Data"], Cpd["Data"])
    RhoCp["Attr"] = {"long_name": "Product of air density and specific heat capacity",
                     "units": "J/m^3/K", "statistic_type": "average"}
    RhoCp["Flag"] = numpy.where(numpy.ma.getmaskarray(RhoCp["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, RhoCp)
    iris["not_output"].append("RhoCp")
    # specific heat of moist air
    Cpm = pfp_utils.CreateEmptyVariable("Cpm", nrecs)
    Cpm["Data"] = pfp_mf.specificheatmoistair(SH["Data"])
    Cpm["Attr"] = {"long_name": "Specific heat capacity of moist air", "units": "J/kg/K",
                   "statistic_type": "average"}
    Cpm["Flag"] = numpy.where(numpy.ma.getmaskarray(Cpm["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, Cpm)
    iris["not_output"].append("Cpm")
    # vapour pressure deficit
    VPD = pfp_utils.CreateEmptyVariable("VPD", nrecs)
    VPD["Data"] = VPsat["Data"] - VP["Data"]
    VPD["Attr"] = {"long_name": "Vapour pressure deficit", "units": "kPa",
                   "standard_name": "water_vapor_saturation_deficit_in_air",
                   descr_level: "Vapour pressure deficit calculated from AH, Ta and ps",
                   "statistic_type": "average"}
    VPD["Flag"] = numpy.where(numpy.ma.getmaskarray(VPD["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, VPD)
    # specific humidity deficit
    SHD = pfp_utils.CreateEmptyVariable("SHD", nrecs)
    SHD["Data"] = SHsat - SH["Data"]
    SHD["Attr"] = {"long_name": "Specific humidity deficit", "units": "kg/kg",
                   descr_level: "Specific humidity deficit calculated from SH, Ta and ps",
                   "statistic_type": "average"}
    SHD["Flag"] = numpy.where(numpy.ma.getmaskarray(SHD["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, SHD)
    # H2O concentration
    H2O = pfp_utils.CreateEmptyVariable("H2O", nrecs)
    H2O["Data"] = pfp_mf.h2o_mmolpmolfromgpm3(AH["Data"], Ta["Data"], ps["Data"])
    H2O["Attr"] = {"long_name": "H2O concentration", "units": "mmol/mol",
                   "standard_name": "mole_fraction_of_water_vapor_in_air",
                   descr_level: "Water vapour mixing ratio calculated from AH, Ta and ps",
                   "statistic_type": "average"}
    H2O["Flag"] = numpy.where(numpy.ma.getmaskarray(H2O["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, H2O)
    return

def CalculateMoninObukhovLength(ds):
    """
    Purpose:
     Calculate the Monin Obukhov length.
    Usage:
     pfp_ts.CalculateMoninObukhovLength(ds)
     where ds is a data structure
    Side effects:
     Creates a new series in the data structure containing the Monin-Obukhov length.
    Author: PRI
    Date: April 2018
    """
    logger.info(' Calculating Monin-Obukhov length')
    # create a variable dictionary for L
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    L = pfp_utils.CreateEmptyVariable("L", nrecs, datetime=ldt["Data"])
    # create QC flags
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    ones = numpy.ones(nrecs, dtype=numpy.int32)
    # get the required meteorological variables
    Ta = pfp_utils.GetVariable(ds, "Ta")
    ps = pfp_utils.GetVariable(ds, "ps")
    vp = pfp_utils.GetVariable(ds, "VP")
    # get the required fluxes
    ustar = pfp_utils.GetVariable(ds, "ustar")
    Fh = pfp_utils.GetVariable(ds, "Fh")
    # calculate the density of dry air
    rho_dry = pfp_mf.densitydryair(Ta["Data"], ps["Data"], vp["Data"])
    # calculate virtual potential temperature
    Tp = pfp_mf.theta(Ta["Data"], ps["Data"])
    mr = pfp_mf.mixingratio(ps["Data"], vp["Data"])
    Tvp = pfp_mf.virtualtheta(Tp, mr)
    L["Data"] = -Tvp*rho_dry*c.Cp*(ustar["Data"]**3)/(c.g*c.k*Fh["Data"])
    # get the QC flag
    L["Flag"] = numpy.where(numpy.ma.getmaskarray(L["Data"]) == True, ones, zeros)
    # update the variable attributes
    L["Attr"]["units"] = "m"
    L["Attr"]["long_name"] = "Monin-Obukhov length"
    # put the Monin-Obukhov variable in the data structure
    pfp_utils.CreateVariable(ds, L)
    return

def CalculateNetRadiation(cf,ds,Fn_out='Fn_4cmpt',Fsd_in='Fsd',Fsu_in='Fsu',Fld_in='Fld',Flu_in='Flu'):
    """
    Purpose:
     Calculate the net radiation from the 4 components of the surface
     radiation budget.
    Usage:
     pfp_ts.CalculateNetRadiation(cf,ds,Fn_out,Fsd_in,Fsu_in,Fld_in,Flu_in)
        cf: control file
        ds: data structure
        Fn_out: output net radiation variable to ds.  Example: 'Fn_KZ'
        Fsd_in: input downwelling solar radiation in ds.  Example: 'Fsd'
        Fsu_in: input upwelling solar radiation in ds.  Example: 'Fsu'
        Fld_in: input downwelling longwave radiation in ds.  Example: 'Fld'
        Flu_in: input upwelling longwave radiation in ds.  Example: 'Flu'
    Side effects:
     Creates a new series in the data structure containing the net radiation.
    Author: PRI
    Date: Sometime early on
    """
    logger.info(' Calculating net radiation from 4 components')
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nrecs,dtype=numpy.int32)
    ones = numpy.ones(nrecs,dtype=numpy.int32)
    Fn_calc = pfp_utils.CreateEmptyVariable(Fn_out, nrecs)
    if ((Fsd_in in list(ds.root["Variables"].keys())) and
        (Fsu_in in list(ds.root["Variables"].keys())) and
        (Fld_in in list(ds.root["Variables"].keys())) and
        (Flu_in in list(ds.root["Variables"].keys()))):
        Fsd = pfp_utils.GetVariable(ds, Fsd_in)
        Fsu = pfp_utils.GetVariable(ds, Fsu_in)
        Fld = pfp_utils.GetVariable(ds, Fld_in)
        Flu = pfp_utils.GetVariable(ds, Flu_in)
        Fn_calc["Data"] = (Fsd["Data"] - Fsu["Data"]) + (Fld["Data"] - Flu["Data"])
        if Fn_out not in list(ds.root["Variables"].keys()):
            descr = "Calculated net radiation using "+Fsd_in+','+Fsu_in+','+Fld_in+','+Flu_in
            Fn_calc["Attr"] = {"long_name": "Net radiation", "statistic_type": "average",
                               descr_level: descr,
                               "standard_name": "surface_net_downward_radiative_flux",
                               "units": "W/m^2"}
            Fn_calc["Flag"] = numpy.where(numpy.ma.getmaskarray(Fn_calc["Data"]) == True, ones, zeros)
            pfp_utils.CreateVariable(ds, Fn_calc)
        else:
            Fn_exist = pfp_utils.GetVariable(ds, Fn_out)
            idx = numpy.where((numpy.ma.getmaskarray(Fn_exist["Data"]) == True)&
                              (numpy.ma.getmaskarray(Fn_calc["Data"]) == False))[0]
            if len(idx) != 0:
                Fn_exist["Data"][idx] = Fn_calc["Data"][idx]
                Fn_exist["Flag"][idx] = numpy.int32(20)
            pfp_utils.CreateVariable(ds, Fn_exist)
    else:
        missing_items = []
        for item in [Fsd_in, Fsu_in, Fld_in, Flu_in]:
            if item not in list(ds.root["Variables"].keys()):
                missing_items.append(item)
        msg = "  " + ",".join(missing_items) + " not found, "+Fn_out+" set to missing"
        logger.warning(msg)
        attr = {"long_name": "Calculated net radiation (one or more components missing)",
                "standard_name": "surface_net_downward_radiative_flux", "units": "W/m^2",
                "statistic_type": "average"}
        Fn = pfp_utils.CreateEmptyVariable(Fn_out, nrecs, attr=attr)
        pfp_utils.CreateVariable(ds, Fn)
    return

def CheckCovarianceUnits(ds):
    """
    Purpose:
    Usage:
    Author: PRI
    Date: September 2015
    """
    logger.info(' Checking covariance units')
    co2_list = ["UxC", "UyC", "UzC"]
    h2o_list = ["UxA", "UyA", "UzA", "UxH", "UyH", "UzH"]
    for item in co2_list:
        if item not in list(ds.root["Variables"].keys()): continue
        var = pfp_utils.GetVariable(ds, item)
        if "umol" in var["Attr"]["units"]:
            Ta = pfp_utils.GetVariable(ds, "Ta")
            ps = pfp_utils.GetVariable(ds, "ps")
            var["Data"] = pfp_mf.co2_mgCO2pm3fromppm(var["Data"], Ta["Data"], ps["Data"])
            var["Attr"]["units"] = "mg/m^2/s"
            pfp_utils.CreateVariable(ds, var)
    for item in h2o_list:
        if item not in list(ds.root["Variables"].keys()): continue
        var = pfp_utils.GetVariable(ds, item)
        if "mmol" in var["Attr"]["units"]:
            Ta = pfp_utils.GetVariable(ds, "Ta")
            ps = pfp_utils.GetVariable(ds, "ps")
            var["Data"] = pfp_mf.h2o_gpm3frommmolpmol(var["Data"], Ta["Data"], ps["Data"])
            var["Attr"]["units"] = "g/m^2/s"
            if "H" in item: item = item.replace("H","A")
            pfp_utils.CreateVariable(ds, var)
    return

def CombineSeries(cf, ds, labels, convert_units=False, save_originals=False, mode="quiet"):
    """
    Purpose:
     Combine two variables by merging or element-wise averaging.
     This is a wrapper that decides whether to merge or average 2 variables
     based on the key specified in the control file.
    Usage:
     pfp_ts.CombineSeries(cf, ds, label, convert_units=False, save_originals=False)
     where cf is a cotrol file
           ds is a data structure
           label is the label of the output (merged or averaged) variable
           convert_units=True if you want to check all variables have the same units
                              before merging or averaging
           save_originals=True if you want to save the orginal series if the output
                               label is the same as an input variable
    Side effects:
    Author: PRI
    Date: October 2019
    """
    # check to see if labels argument is a string (single variable label)
    if isinstance(labels, str):
        # if so, make it a list
        labels = [labels]
    # loop over the variables to be checked
    for label in labels:
        if (label not in cf["Variables"]):
            if mode != "quiet":
                msg = " CombineSeries: Variable " + label + " not found in control file"
                msg += ", skipping ..."
                logger.warning(msg)
            return
        if "MergeSeries" in cf["Variables"][label]:
            MergeSeries(cf, ds, label, convert_units=convert_units, save_originals=save_originals)
        elif "AverageSeries" in cf["Variables"][label]:
            AverageSeriesByElements(cf, ds, label)
        else:
            if mode != "quiet":
                msg = " CombineSeries: Neither MergeSeries nor AverageSeries "
                msg += " option given for variable " + label
                msg += ", skipping ..."
                logger.warning(msg)
            pass
    return

def CoordRotation2D(cf, ds, info):
    """
        2D coordinate rotation to force v = w = 0.  Based on Lee et al, Chapter
        3 of Handbook of Micrometeorology.  This routine does not do the third
        rotation to force v'w' = 0.

        Usage pfp_ts.CoordRotation2D(ds)
        ds: data structure
        """
    msg = " Applying 2D coordinate rotation (components and covariances)"
    logger.info(msg)
    iris = info["RemoveIntermediateSeries"]
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs,dtype=numpy.int32)
    ones = numpy.ones(nRecs,dtype=numpy.int32)
    # check to see if the wind velocity component variances are in the data structure
    labels_to_check = ["Uy_SONIC_Vr", "Ux_SONIC_Vr", "Uz_SONIC_Vr"]
    ok, missing = pfp_utils.variables_in_datastructure(ds, labels_to_check)
    if not ok:
        # if not, check to see if we have the wind velocity standard deviations
        labels_to_check = ["Uy_SONIC_Sd", "Ux_SONIC_Sd", "Uz_SONIC_Sd"]
        ok, missing = pfp_utils.variables_in_datastructure(ds, labels_to_check)
        if not ok:
            # quit if we have neither variances nor standard deviations
            msg = ",".join(missing) + " missing, 2D coordinate rotation not done"
            logger.error(msg)
            info["status"]["ok"] = False
            info["status"]["message"] = msg
            return
        else:
            # calculate the variances from the standard deviations
            msg = "  Calculating wind velocity component variances from standard deviations"
            logger.info(msg)
            for sd_label in labels_to_check:
                vr_label = sd_label.replace("_Sd", "_Vr")
                pfp_func_stats.Variance_from_standard_deviation(ds, vr_label, sd_label)
    # now check to see if we have everything else we need
    labels_to_check = ["Ux_SONIC_Av", "Uy_SONIC_Av", "Uz_SONIC_Av",
                       "Ux_SONIC_Vr", "Uy_SONIC_Vr", "Uz_SONIC_Vr",
                       "UxUz", "UyUz", "UxUy",
                       "UzC", "UzA", "UzT",
                       "UxC", "UyC", "UxA", "UyA", "UxT", "UyT"]
    ok, missing = pfp_utils.variables_in_datastructure(ds, labels_to_check)
    if not ok:
        # quit if any of the equired variables are not present
        msg = ",".join(missing) + " missing, 2D coordinate rotation not done"
        logger.error(msg)
        info["status"]["ok"] = False
        info["status"]["message"] = msg
        return
    # get the raw wind velocity components
    Ux = pfp_utils.GetVariable(ds, "Ux_SONIC_Av") # longitudinal component in CSAT coordinate system
    Uy = pfp_utils.GetVariable(ds, "Uy_SONIC_Av") # lateral component in CSAT coordinate system
    Uz = pfp_utils.GetVariable(ds, "Uz_SONIC_Av") # vertical component in CSAT coordinate system
    # get the raw covariances
    UxUz = pfp_utils.GetVariable(ds, "UxUz")      # covariance(Ux,Uz)
    UyUz = pfp_utils.GetVariable(ds, "UyUz")      # covariance(Uy,Uz)
    UxUy = pfp_utils.GetVariable(ds, "UxUy")      # covariance(Ux,Uy)
    UyUy = pfp_utils.GetVariable(ds, "Uy_SONIC_Vr")# variance(Uy)
    UxUx = pfp_utils.GetVariable(ds, "Ux_SONIC_Vr")# variance(Ux)
    UzUz = pfp_utils.GetVariable(ds, "Uz_SONIC_Vr")# variance(Uz)
    UzC = pfp_utils.GetVariable(ds, "UzC")        # covariance(Uz,C)
    UzA = pfp_utils.GetVariable(ds, "UzA")        # covariance(Uz,A)
    UzT = pfp_utils.GetVariable(ds, "UzT")        # covariance(Uz,T)
    UxC = pfp_utils.GetVariable(ds, "UxC")        # covariance(Ux,C)
    UyC = pfp_utils.GetVariable(ds, "UyC")        # covariance(Uy,C)
    UxA = pfp_utils.GetVariable(ds, "UxA")        # covariance(Ux,A)
    UyA = pfp_utils.GetVariable(ds, "UyA")        # covariance(Ux,A)
    UxT = pfp_utils.GetVariable(ds, "UxT")        # covariance(Ux,T)
    UyT = pfp_utils.GetVariable(ds, "UyT")        # covariance(Uy,T)
    # apply 2D coordinate rotation unless otherwise specified in control file
    rotate = True
    if ("Options" in cf) and ("2DCoordRotation" in list(cf["Options"].keys())):
        if not cf["Options"].as_bool("2DCoordRotation"):
            rotate = False
    if rotate:
        # get the 2D and 3D wind speeds
        ws2d = numpy.ma.sqrt(Ux["Data"]**2 + Uy["Data"]**2)
        ws3d = numpy.ma.sqrt(Ux["Data"]**2 + Uy["Data"]**2 + Uz["Data"]**2)
        # get the sine and cosine of the angles through which to rotate
        #  - first we rotate about the Uz axis by eta to get v = 0
        #  - then we rotate about the v axis by theta to get w = 0
        ce = Ux["Data"]/ws2d          # cos(eta)
        se = Uy["Data"]/ws2d          # sin(eta)
        ct = ws2d/ws3d                # cos(theta)
        st = Uz["Data"]/ws3d          # sin(theta)
        # get the rotation angles
        theta = numpy.rad2deg(numpy.arctan2(st, ct))
        eta = numpy.rad2deg(numpy.arctan2(se, ce))
        # do the wind velocity components first
        u = Ux["Data"]*ct*ce + Uy["Data"]*ct*se + Uz["Data"]*st   # longitudinal component in natural wind coordinates
        v = Uy["Data"]*ce - Ux["Data"]*se                         # lateral component in natural wind coordinates
        w = Uz["Data"]*ct - Ux["Data"]*st*ce - Uy["Data"]*st*se   # vertical component in natural wind coordinates
        # do the variances
        uu = UxUx["Data"]*ct**2*ce**2 + UyUy["Data"]*ct**2*se**2 + UzUz["Data"]*st**2 + \
            2*UxUy["Data"]*ct**2*ce*se + 2*UxUz["Data"]*ct*st*ce + 2*UyUz["Data"]*ct*st*se
        vv = UyUy["Data"]*ce**2 + UxUx["Data"]*se**2 - 2*UxUy["Data"]*ce*se
        ww = UzUz["Data"]*ct**2 + UxUx["Data"]*st**2*ce**2 + UyUy["Data"]*st**2*se**2 - \
            2*UxUz["Data"]*ct*st*ce - 2*UyUz["Data"]*ct*st*se + 2*UxUy["Data"]*st**2*ce*se
        # now do the scalar covariances
        wT = UzT["Data"]*ct - UxT["Data"]*st*ce - UyT["Data"]*st*se       # covariance(w,T) in natural wind coordinate system
        wA = UzA["Data"]*ct - UxA["Data"]*st*ce - UyA["Data"]*st*se       # covariance(w,A) in natural wind coordinate system
        wC = UzC["Data"]*ct - UxC["Data"]*st*ce - UyC["Data"]*st*se       # covariance(w,C) in natural wind coordinate system
        # now do the momentum covariances
        # full equations, Wesely PhD thesis via James Cleverly and EddyPro
        # covariance(w,x) in natural wind coordinate system
        uw = UxUz["Data"]*ce*(ct*ct-st*st) - 2*UxUy["Data"]*ct*st*ce*se + \
            UyUz["Data"]*se*(ct*ct-st*st) - UxUx["Data"]*ct*st*ce*ce - \
            UyUy["Data"]*ct*st*se*se + UzUz["Data"]*ct*st
        # covariance(x,y) in natural wind coordinate system
        uv = UxUy["Data"]*ct*(ce*ce-se*se) + UyUz["Data"]*st*ce - \
            UxUz["Data"]*st*se - UxUx["Data"]*ct*ce*se + UyUy["Data"]*ct*ce*se
        # covariance(w,y) in natural wind coordinate system
        vw = UyUz["Data"]*ct*ce - UxUz["Data"]*ct*se - UxUy["Data"]*st*(ce*ce-se*se) + \
             UxUx["Data"]*st*ce*se - UyUy["Data"]*st*ce*se
    else:
        msg = " 2D coordinate rotation disabled, using unrotated components and covariances"
        logger.warning(msg)
        # dummy series for rotation angles
        theta = numpy.zeros(nRecs)
        eta = numpy.zeros(nRecs)
        # unrotated wind components
        u = Ux["Data"]           # unrotated x xomponent
        v = Uy["Data"]           # unrotated y xomponent
        w = Uz["Data"]           # unrotated z xomponent
        # unrotated covariances
        wT = UzT["Data"]       # unrotated  wT covariance
        wA = UzA["Data"]       # unrotated  wA covariance
        wC = UzC["Data"]       # unrotated  wC covariance
        uw = UxUz["Data"]      # unrotated  uw covariance
        vw = UyUz["Data"]      # unrotated  vw covariance
        uv = UxUy["Data"]      # unrotated  uv covariance
        # unrotated variances
        uu = UxUx["Data"]      # unrotated  u variance
        vv = UyUy["Data"]      # unrotated  v variance
        ww = UzUz["Data"]      # unrotated  w variance
    # store the rotated quantities in the data structure
    attr = {"long_name": "Horizontal rotation angle", "units": "degrees",
            "height": Uz["Attr"]["height"], "statistic_type": "average"}
    flag = numpy.where(numpy.ma.getmaskarray(eta) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "eta", "Data": eta, "Flag": flag, "Attr": attr})
    iris["not_output"].append("eta")

    attr = {"long_name": "Vertical rotation angle", "units": "degrees",
            "height": Uz["Attr"]["height"], "statistic_type": "average"}
    flag = numpy.where(numpy.ma.getmaskarray(theta) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "theta", "Data": theta, "Flag": flag, "Attr": attr})
    iris["not_output"].append("theta")

    attr = copy.deepcopy(Ux["Attr"])
    attr["long_name"] = "Longitudinal component of wind-speed in natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(u) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "U_SONIC_Av", "Data": u, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(Uy["Attr"])
    attr["long_name"] = "Lateral component of wind-speed in natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(v) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "V_SONIC_Av", "Data": v, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(Uz["Attr"])
    attr["long_name"] = "Vertical component of wind-speed in natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(w) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "W_SONIC_Av", "Data": w, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UzT["Attr"])
    attr["long_name"] = "Kinematic heat flux, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(wT) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "wT", "Data": wT, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UzA["Attr"])
    attr["long_name"] = "Kinematic vapour flux, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(wA) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "wA", "Data": wA, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UzC["Attr"])
    attr["long_name"] = "Kinematic CO2 flux, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(wC) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "wC", "Data": wC, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UxUz["Attr"])
    attr["long_name"] = "Momentum flux X component, corrected to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(uw) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "uw", "Data": uw, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UxUy["Attr"])
    attr["long_name"] = "Horizontal streamwise-crosswind covariance, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(uv) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "uv", "Data": uv, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UyUz["Attr"])
    attr["long_name"] = "Momentum flux Y component, corrected to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(vw) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "vw", "Data": vw, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UxUx["Attr"])
    attr["long_name"] = "Variance of streamwise windspeed, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(uu) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "U_SONIC_Vr", "Data": uu, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UxUx["Attr"])
    attr["long_name"] = "Standard deviation of streamwise windspeed, rotated to natural wind coordinates"
    attr["units"] = "m/s"
    data = numpy.ma.sqrt(uu)
    flag = numpy.where(numpy.ma.getmaskarray(uu) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "U_SONIC_Sd", "Data": data, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UyUy["Attr"])
    attr["long_name"] = "Variance of cross-stream windspeed, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(vv) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "V_SONIC_Vr", "Data": vv, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UyUy["Attr"])
    attr["long_name"] = "Standard deviation of cross-stream windspeed, rotated to natural wind coordinates"
    attr["units"] = "m/s"
    data = numpy.ma.sqrt(vv)
    flag = numpy.where(numpy.ma.getmaskarray(vv) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "V_SONIC_Sd", "Data": data, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UzUz["Attr"])
    attr["long_name"] = "Variance of vertical windspeed, rotated to natural wind coordinates"
    flag = numpy.where(numpy.ma.getmaskarray(ww) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "W_SONIC_Vr", "Data": ww, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(UzUz["Attr"])
    attr["long_name"] = "Standard deviation of vertical windspeed, rotated to natural wind coordinates"
    attr["units"] = "m/s"
    data = numpy.ma.sqrt(ww)
    flag = numpy.where(numpy.ma.getmaskarray(ww) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "W_SONIC_Sd", "Data": data, "Flag": flag, "Attr": attr})

    if pfp_utils.get_optionskeyaslogical(cf, "RelaxRotation"):
        RotatedSeriesList = ['wT', 'wA', 'wC', 'uw', 'vw']
        NonRotatedSeriesList = ['UzT', 'UzA', 'UzC', 'UxUz', 'UyUz']
        for ThisOne, ThatOne in zip(RotatedSeriesList, NonRotatedSeriesList):
            ReplaceWhereMissing(ds.root["Variables"][ThisOne], ds.root["Variables"][ThisOne], ds.root["Variables"][ThatOne], FlagValue=21)

def CalculateComponentsFromWsWd(ds):
    """
    Purpose:
     Calculate U (positive east) and V (positive north) from wind speed and direction and
     put the components into the data structure.
    Usage:
     pfp_ts.CalculateComponentsFromWsWd(ds)
    Author: PRI/WW/MK/EvG
    Date: July 2016
    """
    Wd = pfp_utils.GetVariable(ds, "Wd")
    Ws = pfp_utils.GetVariable(ds, "Ws")
    u, v = pfp_utils.convert_WSWDtoUV(Ws, Wd)
    pfp_utils.CreateVariable(ds, u)
    pfp_utils.CreateVariable(ds, v)

def CalculateSco2ONEFlux(ds, CO2_in="CO2", Sco2_out="Sco2_oneflux"):
    """
    Purpose:
     Calculate the CO2 flux storage term from a single point measurement of CO2.
     This routine uses the method coded in ONEFlux/oneflux_steps/qc_auto.  This
     uses a factor of 0.024 to approximate the correction from umol/mol to
     umol/m^3.  The factor of 0.024 is approximately correct for a pressure of
     101 kPa and a temperature of 22 degC.
    Usage:
    Side effects:
    Author: PRI
    Date: January 2024
    """
    msg = " Calculating Sco2 (single point, ONEFlux method)"
    logger.info(msg)
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ts = int(ds.root["Attributes"]["time_step"])
    ones = numpy.ones(nrecs, dtype=int)
    zeros = numpy.zeros(nrecs, dtype=int)
    CO2 = pfp_utils.GetVariable(ds, CO2_in)
    if CO2["Attr"]["units"] != "umol/mol":
        msg = "  CO2 units must be umol/mol (" + CO2["Attr"]["units"] + "), Sco2 not calculated"
        logger.error(msg)
        return
    attr = {"height": pfp_utils.strip_non_numeric(str(CO2["Attr"]["height"])),
            "instrument": CO2["Attr"]["instrument"],
            "long_name": "Storage term of CO2 flux using ONEFlux method",
            "statistic_type": "average",
            "units": "umol/m^2/s"}
    Sco2 = pfp_utils.CreateEmptyVariable(Sco2_out, nrecs, attr=attr)
    Sco2["Data"][1:nrecs] = ((CO2["Data"][1:nrecs] - CO2["Data"][0:nrecs-1])/(ts*60)*
                             (float(Sco2["Attr"]["height"])/0.024))
    Sco2["Flag"] = numpy.where(numpy.ma.getmaskarray(Sco2["Data"]), ones, zeros)
    pfp_utils.CreateVariable(ds, Sco2)
    return

def CalculateSco2SinglePoint(ds, Sco2_out="Sco2_single"):
    """
    Calculate CO2 flux storage term in the air column beneath the CO2 instrument.  This
    routine assumes the air column between the sensor and the surface is well mixed.

    Usage pfp_ts.CalculateSco2SinglePoint(ds, Sco2_out='Sco2_single')
    ds: data structure
    Sco2_out: label of the single point storage term
    """
    labels = list(ds.root["Variables"].keys())
    if Sco2_out not in labels:
        # sanity checks
        for label in ["CO2", "Ta", "ps"]:
            if label not in labels:
                msg = " " + label + " not in data structure, Sco2 not calculated"
                logger.warning(msg)
                return
        if "height" in ds.root["Variables"]["CO2"]["Attr"]:
            height = pfp_utils.strip_non_numeric(str(ds.root["Variables"]["CO2"]["Attr"]["height"]))
            height = float(height)
        else:
            msg = " 'height' attribute missing from CO2 variable, Sco2 not calculated"
            logger.warning(msg)
            return
        # seems safe to proceed
        msg = " Calculating Sco2 (single height)"
        logger.info(msg)
        nRecs = int(ds.root["Attributes"]["nc_nrecs"])
        zeros = numpy.zeros(nRecs, dtype=numpy.int32)
        ones = numpy.ones(nRecs, dtype=numpy.int32)
        ts = int(float(ds.root["Attributes"]["time_step"]))
        level = str(ds.root["Attributes"]["processing_level"])
        descr_level = "description_" + level
        # create an empty output variable
        ldt = pfp_utils.GetVariable(ds, "DateTime")
        Sco2_single = pfp_utils.CreateEmptyVariable(Sco2_out, nRecs, datetime=ldt["Data"])
        # get the input data
        CO2 = pfp_utils.GetVariable(ds, "CO2")
        Ta = pfp_utils.GetVariable(ds, "Ta")
        ps = pfp_utils.GetVariable(ds, "ps")
        # check the CO2 concentration units
        # if the units are mg/m^3, convert CO2 concentration to umol/mol before taking the difference
        pfp_utils.convert_units_func(ds, CO2, "umol/mol")
        # calculate the change in CO2 concentration between time steps
        # CO2 concentration assumed to be in umol/mol
        dc = numpy.ma.ediff1d(CO2["Data"], to_begin=0)
        # convert the CO2 concentration difference from umol/mol to umol/m^3
        dc = pfp_mf.co2_umolpm3fromppm(dc, Ta["Data"], ps["Data"])
        # calculate the time step in seconds
        epoch = datetime.datetime(1970, 1, 1, 0, 0, 0)
        seconds = numpy.array([(dt-epoch).total_seconds() for dt in ldt["Data"]])
        dt = numpy.ediff1d(seconds, to_begin=float(ts)*60)
        # calculate the CO2 flux based on storage below the measurement height
        Sco2_single["Data"] = height*dc/dt
        # do the attributes
        Sco2_single["Attr"] = {}
        for attr in ["instrument", "height"]:
            if attr in CO2["Attr"]:
                Sco2_single["Attr"][attr] = CO2["Attr"][attr]
        Sco2_single["Attr"]["height"] = height
        Sco2_single["Attr"]["units"] = "umol/m^2/s"
        Sco2_single["Attr"]["standard_name"] = "surface_upward_mole_flux_of_carbon_dioxide"
        Sco2_single["Attr"]["long_name"] = "Storage term of CO2 flux"
        Sco2_single["Attr"]["statistic_type"] = "average"
        tmp = "Sco2 calcuated using single point CO2 measurement"
        Sco2_single["Attr"][descr_level] = tmp
        # put the storage flux in the data structure
        mask = numpy.ma.getmaskarray(Sco2_single["Data"])
        Sco2_single["Flag"] = numpy.where(mask == True, ones, zeros)
        pfp_utils.CreateVariable(ds, Sco2_single)
    else:
        msg = "  " + Sco2_out + " found in data structure, not calculated"
        logger.info(msg)
    return

def CorrectFco2ForStorage(cf, ds, Fco2_out="Fco2", Fco2_in="Fco2"):
    """
    Correct CO2 flux for storage in the air column beneath the CO2 instrument.

    Usage pfp_ts.CorrectFco2ForStorage(cf, ds, Fco2_out, Fco2_in)
    cf: control file object
    ds: data structure
    Fco2_out: series label of the corrected CO2 flux
    Fco2_in: series label of the input CO2 flux
    Sco2: series label of the CO2 flux storage term

    """
    descr_level = "description_" + str(ds.root["Attributes"]["processing_level"])
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs,dtype=numpy.int32)
    ones = numpy.ones(nRecs,dtype=numpy.int32)
    # check to see if applying the Fc storage term has been requested for any
    # individual variables
    apply_storage = {}
    for label in list(cf["Variables"].keys()):
        if "ApplyFco2Storage" in cf["Variables"][label]:
            source = str(cf["Variables"][label]["ApplyFco2Storage"]["source"])
            apply_storage[label] = source
    # if no individual series have been specified, do the default
    if len(list(apply_storage.keys())) == 0:
        # check to see if correction for storage has been requested in [Options]
        if not pfp_utils.get_optionskeyaslogical(cf, "ApplyFco2Storage"):
            return
        # check to see if we have the required data series
        if Fco2_in not in list(ds.root["Variables"].keys()):
            msg = Fco2_in + " not found in data, skipping Fco2 storage correction ..."
            logger.warning(msg)
            return
        # check to see if we have an Fco2_profile series
        if "Sco2" in list(ds.root["Variables"].keys()):
            msg = " Using Sco2 for the storage term"
            logger.info(msg)
            Sco2_in = "Sco2"
        elif "Sco2_storage" in list(ds.root["Variables"].keys()):
            msg = " Using Sco2_storage for the storage term"
            logger.info(msg)
            Sco2_in = "Sco2_storage"
        elif "Sco2_profile" in list(ds.root["Variables"].keys()):
            msg = " Using Sco2_profile for the storage term"
            logger.info(msg)
            Sco2_in = "Sco2_profile"
        elif "Sco2_single" in list(ds.root["Variables"].keys()):
            msg = " Using Sco2_single for the storage term"
            logger.info(msg)
            Sco2_in = "Sco2_single"
        else:
            msg = " Storage term (Sco2, Sco2_storage, Sco2_profile or Sco2_single) not found"
            logger.warning(msg)
            return
        # apply the storage term
        msg = " ***!!! Applying CO2 storage term using " + Sco2_in +" !!!***"
        logger.info(msg)
        Fco2_uncorrected = pfp_utils.GetVariable(ds, Fco2_in)
        Sco2 = pfp_utils.GetVariable(ds, Sco2_in)
        if Fco2_uncorrected["Attr"]["units"] != Sco2["Attr"]["units"]:
            msg = "CorrectFco2ForStorage: units of Fco2 do not match those of storage term"
            msg += ", storage not applied"
            logger.error(msg)
            return
        # get a copy of the uncorrected data
        Fco2_corrected = copy.deepcopy(Fco2_uncorrected)
        # add the storage term
        Fco2_corrected["Data"] = Fco2_uncorrected["Data"] + Sco2["Data"]
        # if requested, replace missing storage corrected with uncorrected data
        if pfp_utils.get_optionskeyaslogical(cf, "RelaxFco2Storage"):
            # if so, replace missing corrected Fco2 with uncorrected Fco2
            mask = numpy.ma.getmaskarray(Fco2_uncorrected["Data"])
            idx = numpy.where(mask == True)[0]
            Fco2_corrected["Data"][idx] = Fco2_uncorrected["Data"][idx]
            msg = " Replaced corrected Fco2 with " + str(len(idx)) + " uncorrected values"
            logger.info(msg)
        # write the uncorrected CO2 flux to the data structure
        Fco2_uncorrected["Label"] = "Fco2_uncorrected"
        tmp = Fco2_uncorrected["Label"] + ", not corrected for storage"
        pfp_utils.append_to_attribute(Fco2_uncorrected["Attr"], {descr_level: tmp})
        pfp_utils.CreateVariable(ds, Fco2_uncorrected)
        # write the corrected CO2 flux to the data structure
        Fco2_corrected["Label"] = "Fco2"
        tmp = "corrected for storage using supplied storage term"
        pfp_utils.append_to_attribute(Fco2_corrected["Attr"], {descr_level: tmp})
        mask = numpy.ma.getmaskarray(Fco2_corrected["Data"])
        flag = numpy.where(mask == True, ones, zeros)
        Fco2_corrected["Flag"] = flag
        pfp_utils.CreateVariable(ds, Fco2_corrected)
    else:
        # loop over the series for which apply Fco2 storage was requested
        for label in list(apply_storage.keys()):
            # check to make sure the requested series is in the data structure
            if label not in list(ds.root["Variables"].keys()):
                # skip if it isn't
                msg = " Requested series " + label + " not found in data structure"
                logger.error(msg)
                continue
            # get the storage flux label
            source = apply_storage[label]
            if source not in list(ds.root["Variables"].keys()):
                msg = " Requested series " + source + " not found in data structure"
                logger.error(msg)
                continue
            # get the data
            Fco2_uncorrected = pfp_utils.GetVariable(ds, label)
            Sco2 = pfp_utils.GetVariable(ds, source)
            # check the units
            if Fco2_uncorrected["Attr"]["units"] != Sco2["Attr"]["units"]:
                msg = " Units for " + label + " and " + source + " don't match"
                logger.error(msg)
                return
            msg = " *** Applying storage term " + source + " to " + label + " ***"
            logger.info(msg)
            # Make a copy of the uncorrected Fco2
            Fco2_corrected = copy.deepcopy(Fco2_uncorrected)
            # update the label, the long name and write the uncorrected data to the data structure
            Fco2_uncorrected["Label"] = Fco2_uncorrected["Label"] + "_uncorrected"
            Fco2_uncorrected["Attr"][descr_level] = Fco2_uncorrected["Attr"]["long_name"]
            Fco2_uncorrected["Attr"][descr_level] += ", not corrected for storage"
            pfp_utils.CreateVariable(ds, Fco2_uncorrected)
            # correct Fco2 by adding the storage
            Fco2_corrected["Data"] = Fco2_uncorrected["Data"] + Sco2["Data"]
            # if requested, replace missing storage corrected with uncorrected data
            if pfp_utils.get_optionskeyaslogical(cf, "RelaxFco2Storage"):
                # if so, replace missing corrected Fco2 with uncorrected Fco2
                mask = numpy.ma.getmaskarray(Fco2_corrected["Data"])
                idx = numpy.where(mask == True)[0]
                Fco2_corrected["Data"][idx] = Fco2_uncorrected["Data"][idx]
                msg = " Replaced corrected Fco2 with " + str(len(idx)) + " uncorrected values"
                logger.info(msg)
            # write the uncorrected CO2 flux to the data structure
            Fco2_uncorrected["Attr"][descr_level] = Fco2_uncorrected["Attr"]["long_name"]
            Fco2_uncorrected["Attr"][descr_level] += ", not corrected for storage"
            pfp_utils.CreateVariable(ds, Fco2_uncorrected)
            # write the corrected CO2 flux to the data structure
            Fco2_corrected["Attr"][descr_level] = Fco2_corrected["Attr"]["long_name"]
            Fco2_corrected["Attr"][descr_level] += ", corrected for storage using supplied storage term"
            Fco2_corrected["Label"] = "Fco2"
            mask = numpy.ma.getmaskarray(Fco2_corrected["Data"])
            flag = numpy.where(mask == True, ones, zeros)
            Fco2_corrected["Flag"] = flag
            pfp_utils.CreateVariable(ds, Fco2_corrected)
    return

def CorrectIndividualFgForStorage(cf,ds):
    if pfp_utils.cfkeycheck(cf,Base='FunctionArgs',ThisOne='CFgArgs'):
        List = list(cf['FunctionArgs']['CFgArgs'].keys())
        for i in range(len(List)):
            CFgArgs = pfp_utils.string_to_list(cf['FunctionArgs']['CFgArgs'][str(i)])
            CorrectFgForStorage(cf,ds,Fg_out=CFgArgs[0],Fg_in=CFgArgs[1],Ts_in=CFgArgs[2],Sws_in=CFgArgs[3])
        return

def CorrectFgForStorage(cf, ds, info, Fg_out='Fg', Fg_in='Fg', Ts_in='Ts', Sws_in="Sws"):
    """
        Correct ground heat flux for storage in the layer above the heat flux plate

        Usage pfp_ts.CorrectFgForStorage(cf,ds,Fg_out,Fg_in,Ts_in,Sws_in)
        ds: data structure
        Fg_out: output soil heat flux variable to ds.  Example: 'Fg'
        Fg_in: input soil heat flux in ds.  Example: 'Fg_Av'
        Ts_in: input soil temperature in ds.  Example: 'Ts'

        Parameters loaded from control file:
            FgDepth: Depth of soil heat flux plates, m
            BulkDensity: soil bulk density, kg/m3
            OrganicContent: soil organic content, fraction
            SwsDefault: default value of soil moisture content used when no sensors present
        Mods:
         Rewritten in mid-2025
          - get Fg depth from variable attribute
          - assume soil moisture variable is Sws
          - get default soil moisture as average of good Sws data
        """
    iris = info["RemoveIntermediateSeries"]
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nrecs, dtype=numpy.int32)
    ones = numpy.ones(nrecs,dtype=numpy.int32)
    # check to see if the user wants to skip the correction
    if not pfp_utils.get_optionskeyaslogical(cf, "CorrectFgForStorage", default=True):
        logger.info(' CorrectFgForStorage: storage correction disabled in control file')
        return
    # check to see if we have the uncorrected Fg, the soil temperature Ts and moisture Sws
    if Fg_in not in list(ds.root["Variables"].keys()):
        logger.warning(' CorrectFgForStorage: '+Fg_in+' not found in data structure, Fg not corrected')
        return
    if Ts_in not in list(ds.root["Variables"].keys()):
        logger.warning(' CorrectFgForStorage: '+Ts_in+' not found in data structure, Fg not corrected')
        return
    if Sws_in not in list(ds.root["Variables"].keys()):
        logger.warning(' CorrectFgForStorage: '+Sws_in+' not found in data structure, Fg not corrected')
        return
    # get the data
    Fg = pfp_utils.GetVariable(ds, Fg_in)
    Ts = pfp_utils.GetVariable(ds, Ts_in)
    Sws = pfp_utils.GetVariable(ds, Sws_in)
    # sanity check for all missing data
    for item in [Fg, Ts, Sws]:
        if item["Data"].mask.all():
            msg = " CorrectFgForStorage: all " + item["Label"]
            msg += " data is missing, skipping correction..."
            logger.warning(msg)
            return
    sws_default = min(1.0, max(0.0, numpy.ma.mean(Sws["Data"])))
    # get the soil properties needed to calculate soil specific heat capacity
    if "height" in Fg["Attr"]:
        d = float(pfp_utils.strip_non_numeric(Fg["Attr"]["height"]))
    elif "FgDepth" in cf["Soil"]:
        d = max(0.0,min(0.5,float(cf['Soil']['FgDepth'])))
    else:
        msg = "  CorrectFgForStorage: depthg of Fg not found, Fg not corrected"
        logger.warning(msg)
        return
    logger.info(' Correcting soil heat flux for storage')
    bd = max(100.0,min(2500.0,float(cf['Soil']['BulkDensity'])))
    oc = max(0.0,min(1.0,float(cf['Soil']['OrganicContent'])))
    mc = 1.0 - oc
    # mask is True if Fg or Ts are masked
    m1 = numpy.ma.getmaskarray(Fg["Data"])
    m2 = numpy.ma.getmaskarray(Ts["Data"])
    mask = numpy.ma.mask_or(m1, m2, copy=True, shrink=False)
    # index of records where soil moisture is missing but Fg and Ts are not
    iom = numpy.ma.where((numpy.ma.getmaskarray(Sws["Data"])==True) & (mask==False))[0]
    # tell the user we are using the default soil moisture value
    if len(iom) != 0:
        msg = "  CorrectFgForStorage: default soil moisture used for "
        msg += str(len(iom)) + " values"
        logger.info(msg)
        Sws["Data"][iom] = sws_default
    # create the output variable
    Fg_corr = pfp_utils.CreateEmptyVariable(Fg_out, nrecs)
    # get the soil temperature difference from time step to time step
    dTs = pfp_utils.CreateEmptyVariable("dTs", nrecs)
    dTs["Data"] = numpy.ma.zeros(nrecs)
    dTs["Data"][1:] = numpy.ma.diff(Ts["Data"])
    # set the temporal difference in Ts for the first value of the series to missing value ...
    dTs[0] = numpy.ma.masked
    # write the temperature difference into the data structure so we can use its flag later
    dTs["Flag"] = numpy.zeros(nrecs, dtype=numpy.int32)
    index = numpy.where(numpy.ma.getmaskarray(dTs["Data"]) == True)[0]
    dTs["Flag"][index] = numpy.int32(1)
    dTs["Attr"] = {"long_name": "Change in soil temperature", "units": "degC",
                   "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, dTs)
    iris["not_output"].append("dTs")
    # get the time difference
    dt = numpy.ma.zeros(nrecs)
    dt[1:] = numpy.diff(date2num(ds.root["Variables"]["DateTime"]["Data"]))*float(86400)
    dt[0] = dt[1]
    # calculate the specific heat capacity of the soil
    Cs = pfp_utils.CreateEmptyVariable("Cs", nrecs)
    Cs["Data"] = mc*bd*c.Cd + oc*bd*c.Co + Sws["Data"]*c.rho_water*c.Cw
    # calculate the soil heat storage
    S = pfp_utils.CreateEmptyVariable("S", nrecs)
    S["Data"] = Cs["Data"]*(dTs["Data"]/dt)*numpy.abs(d)
    # apply the storage term
    Fg_corr["Data"] = Fg["Data"] + S["Data"]
    # put the corrected soil heat flux into the data structure
    Fg_corr["Attr"] = {"long_name": "Ground heat flux",
                       descr_level: "Ground heat flux corrected for storage",
                       "units": "W/m^2", "statistic_type": "average",
                       "standard_name": "downward_heat_flux_at_ground_level_in_soil"}
    Fg_corr["Flag"] = numpy.where(numpy.ma.getmaskarray(Fg_corr["Data"]) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, Fg_corr)
    # save the input (uncorrected) soil heat flux series, this will be used if the correction is relaxed
    Fg["Attr"] = {"long_name": "Ground heat flux",
                  descr_level: "Ground heat flux uncorrected for storage",
                  "units": "W/m^2", "statistic_type": "average",
                  "standard_name": "downward_heat_flux_at_ground_level_in_soil"}
    Fg["Label"] = "Fg_Av"
    pfp_utils.CreateVariable(ds, Fg)
    # put the storage term in the data structure
    S["Flag"] = numpy.where(numpy.ma.getmaskarray(S["Data"]) == True, ones, zeros)
    S["Attr"] = {"long_name": "Ground heat flux storage", "units": "W/m^2",
                 "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, S)
    iris["not_output"].append("S")
    # put the soil specific heat capacity into the data structure
    Cs["Flag"] = numpy.where(numpy.ma.getmaskarray(Cs["Data"]) == True, ones, zeros)
    Cs["Attr"] = {"long_name": "Soil specific heat capacity", "units": "J/m^3/K",
                  "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, Cs)
    iris["not_output"].append("Cs")
    if pfp_utils.get_optionskeyaslogical(cf, "RelaxFgStorage"):
        ReplaceWhereMissing(ds.root["Variables"]["Fg"], ds.root["Variables"]["Fg"], ds.root["Variables"]["Fg_Av"], FlagValue=20)
    return

def CorrectWindDirection(cf, ds, Wd_in):
    """
        Correct wind direction for mis-aligned sensor direction.

        Usage pfp_ts.CorrectWindDirection(cf, ds, Wd_in)
        cf: control file
        ds: data structure
        Wd_in: input/output wind direction variable in ds.  Example: 'Wd_CSAT'
        """
    msg = " Correcting wind direction (" + str(Wd_in) + ")"
    logger.info(msg)
    Wd = pfp_utils.GetVariable(ds, Wd_in)
    ldt = ds.root["Variables"]["DateTime"]["Data"]
    KeyList = list(cf["Variables"][Wd_in]["CorrectWindDirection"].keys())
    for i in range(len(KeyList)):
        correct_wd_string = cf["Variables"][Wd_in]["CorrectWindDirection"][str(i)]
        correct_wd_list = correct_wd_string.split(",")
        for i, item in enumerate(correct_wd_list):
            correct_wd_list[i] = correct_wd_list[i].strip()
        si = pfp_utils.get_start_index(ldt, correct_wd_list[0], mode="quiet")
        if si is None:
            msg = " CorrectWindDirection: start date (" + correct_wd_list[0]
            msg += ") not found, no correction applied"
            logger.warning(msg)
            return
        ei = pfp_utils.get_end_index(ldt, correct_wd_list[1], mode="quiet")
        if ei == -1:
            msg = " CorrectWindDirection: end date (" + correct_wd_list[1]
            msg += ") not found, using last date in data"
            logger.warning(msg)
            ei = len(ldt) - 1
        try:
            Correction = float(correct_wd_list[2])
        except:
            msg = " CorrectWindDirection: bad value (" + str(correct_wd_list[2])
            msg += ") for correction, not applied"
            logger.warning(msg)
            return
        Wd["Data"][si:ei] = Wd["Data"][si:ei] + Correction
    Wd["Data"] = numpy.mod(Wd["Data"], float(360))
    pfp_utils.CreateVariable(ds, Wd)
    return

def do_attributes(cf,ds):
    """
        Import attriubes in L1 control file to netCDF dataset.  Included
        global and variable attributes.  Also attach flag definitions to global
        meta-data for reference.

        Usage pfp_ts.do_attributes(cf,ds)
        cf: control file
        ds: data structure
        """
    logger.info(' Getting the attributes given in control file')
    if 'Global' in list(cf.keys()):
        for gattr in list(cf['Global'].keys()):
            ds.root["Attributes"][gattr] = cf['Global'][gattr]
        ds.root["Attributes"]['Flag00'] = 'Good data'
        ds.root["Attributes"]['Flag10'] = 'Corrections: Apply Linear'
        ds.root["Attributes"]['Flag20'] = 'GapFilling: Driver gap filled using ACCESS'
        ds.root["Attributes"]['Flag30'] = 'GapFilling: Flux gap filled by ANN (SOLO)'
        ds.root["Attributes"]['Flag40'] = 'GapFilling: Gap filled by climatology'
        ds.root["Attributes"]['Flag50'] = 'GapFilling: Gap filled by interpolation'
        ds.root["Attributes"]['Flag60'] = 'GapFilling: Flux gap filled using ratios'
        ds.root["Attributes"]['Flag01'] = 'QA/QC: Missing value in L1 dataset'
        ds.root["Attributes"]['Flag02'] = 'QA/QC: L2 Range Check'
        ds.root["Attributes"]['Flag03'] = 'QA/QC: CSAT Diagnostic'
        ds.root["Attributes"]['Flag04'] = 'QA/QC: LI7500 Diagnostic'
        ds.root["Attributes"]['Flag05'] = 'QA/QC: L2 Diurnal SD Check'
        ds.root["Attributes"]['Flag06'] = 'QA/QC: Excluded Dates'
        ds.root["Attributes"]['Flag07'] = 'QA/QC: Excluded Hours'
        ds.root["Attributes"]['Flag08'] = 'QA/QC: Missing value found with QC flag = 0'
        ds.root["Attributes"]['Flag11'] = 'Corrections/Combinations: Coordinate Rotation (Ux, Uy, Uz, UxT, UyT, UzT, UxA, UyA, UzA, UxC, UyC, UzC, UxUz, UxUx, UxUy, UyUz, UxUy, UyUy)'
        ds.root["Attributes"]['Flag12'] = 'Corrections/Combinations: Massman Frequency Attenuation Correction (Coord Rotation, Tv_CSAT, AH_HMP, ps)'
        ds.root["Attributes"]['Flag13'] = 'Corrections/Combinations: Virtual to Actual Fh (Coord Rotation, Massman, Ta_HMP)'
        ds.root["Attributes"]['Flag14'] = 'Corrections/Combinations: WPL correction for flux effects on density measurements (Coord Rotation, Massman, Fhv to Fh, CO2_IRGA_Av)'
        ds.root["Attributes"]['Flag15'] = 'Corrections/Combinations: Ta from Tv'
        ds.root["Attributes"]['Flag16'] = 'Corrections/Combinations: L3 Range Check'
        ds.root["Attributes"]['Flag17'] = 'Corrections/Combinations: L3 Diurnal SD Check'
        ds.root["Attributes"]['Flag18'] = 'Corrections/Combinations: u* filter'
        ds.root["Attributes"]['Flag19'] = 'Corrections/Combinations: Gap coordination'
        ds.root["Attributes"]['Flag21'] = 'GapFilling: Used non-rotated covariance'
        ds.root["Attributes"]['Flag31'] = 'GapFilling: Flux gap not filled by ANN'
        ds.root["Attributes"]['Flag38'] = 'GapFilling: L4 Range Check'
        ds.root["Attributes"]['Flag39'] = 'GapFilling: L4 Diurnal SD Check'
        # the following flags are used by James Cleverly's version but not
        # by the standard OzFlux version.
        #ds.root["Attributes"]['Flag51'] = 'albedo: bad Fsd < threshold (290 W/m^2 default) only if bad time flag (31) not set'
        #ds.root["Attributes"]['Flag52'] = 'albedo: bad time flag (not midday 10.00 to 14.00)'
        #ds.root["Attributes"]['Flag61'] = 'Penman-Monteith: bad rst (rst < 0) only if bad Uavg (35), bad Fe (33) and bad Fsd (34) flags not set'
        #ds.root["Attributes"]['Flag62'] = 'Penman-Monteith: bad Fe < threshold (0 W/m^2 default) only if bad Fsd (34) flag not set'
        #ds.root["Attributes"]['Flag63'] = 'Penman-Monteith: bad Fsd < threshold (10 W/m^2 default)'
        #ds.root["Attributes"]['Flag64'] = 'Penman-Monteith: Uavg == 0 (undefined aerodynamic resistance under calm conditions) only if bad Fe (33) and bad Fsd (34) flags not set'
        #ds.root["Attributes"]['Flag70'] = 'Partitioning Night: Re computed from exponential temperature response curves'
        #ds.root["Attributes"]['Flag80'] = 'Partitioning Day: GPP/Re computed from light-response curves, GPP = Re - Fc'
        #ds.root["Attributes"]['Flag81'] = 'Partitioning Day: GPP night mask'
        #ds.root["Attributes"]['Flag82'] = 'Partitioning Day: Fco2 > Re, GPP = 0, Re = Fco2'
    for ThisOne in list(ds.root["Variables"].keys()):
        if ThisOne in cf['Variables']:
            if 'Attr' in list(cf['Variables'][ThisOne].keys()):
                ds.root["Variables"][ThisOne]['Attr'] = {}
                for attr in list(cf['Variables'][ThisOne]['Attr'].keys()):
                    ds.root["Variables"][ThisOne]['Attr'][attr] = cf['Variables'][ThisOne]['Attr'][attr]
                if "missing_value" not in list(ds.root["Variables"][ThisOne]['Attr'].keys()):
                    ds.root["Variables"][ThisOne]['Attr']["missing_value"] = numpy.int32(c.missing_value)

def DoFunctions(ds, info):
    """
    Purpose:
     Evaluate functions used in the L1 control file.
    Usage:
    Author: PRI
    Date: September 2015
    """
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    implemented_func_units = [name for name,data in
                              inspect.getmembers(pfp_func_units,
                                                 inspect.isfunction)]
    implemented_func_stats = [name for name,data in
                              inspect.getmembers(pfp_func_stats,
                                                 inspect.isfunction)]
    implemented_func_transforms = [name for name,data in
                                   inspect.getmembers(pfp_func_transforms,
                                                      inspect.isfunction)]
    implemented_functions = (implemented_func_units +
                             implemented_func_stats +
                             implemented_func_transforms)
    functions = {}
    units_vars = []
    stats_vars = []
    transforms_vars = []
    for label in list(info["Variables"].keys()):
        # datetime functions handled elsewhere for now
        if label == "DateTime":
            continue
        if "Function" not in list(info["Variables"][label].keys()):
            continue
        if "func" not in list(info["Variables"][label]["Function"].keys()):
            msg = " 'func' keyword not found in [Functions] for " + label
            logger.error(msg)
            continue
        function_string = info["Variables"][label]["Function"]["func"]
        function_string = function_string.replace('"', '')
        function_name = function_string.split("(")[0]
        function_args = function_string.split("(")[1].replace(")", "").replace(" ", "").split(",")
        if function_name not in implemented_functions:
            msg = " Requested function " + function_name + " not imlemented, skipping ..."
            logger.error(msg)
            continue
        if function_name in implemented_func_units:
            functions[label] = {"type": "units", "name": function_name, "arguments": function_args}
            units_vars.append(label)
        elif function_name in implemented_func_stats:
            functions[label] = {"type": "stats", "name": function_name, "arguments": function_args}
            stats_vars.append(label)
        elif function_name in implemented_func_transforms:
            functions[label] = {"type": "transforms", "name": function_name, "arguments": function_args}
            transforms_vars.append(label)
    series_list = list(ds.root["Variables"].keys())
    for label in units_vars:
        if label not in series_list:
            var = pfp_utils.CreateEmptyVariable(label, nrecs, attr=info["Variables"][label]["Attr"])
            pfp_utils.CreateVariable(ds, var)
        old_units = ds.root["Variables"][label]["Attr"]["units"]
        result = getattr(pfp_func_units, functions[label]["name"])(ds, label, *functions[label]["arguments"])
        new_units = ds.root["Variables"][label]["Attr"]["units"]
        if result:
            if new_units != old_units:
                msg = " Units for " + label + " converted from " + old_units + " to " + new_units
                logger.info(msg)
            else:
                msg = " " + label + " calculated from " + ','.join(functions[label]["arguments"])
                logger.info(msg)
    for label in stats_vars:
        if label not in series_list:
            var = pfp_utils.CreateEmptyVariable(label, nrecs, attr=info["Variables"][label]["Attr"])
            pfp_utils.CreateVariable(ds, var)
        result = getattr(pfp_func_stats, functions[label]["name"])(ds, label, *functions[label]["arguments"])
        if result:
            msg = " Completed function for " + label
            logger.info(msg)
    for label in transforms_vars:
        if label not in series_list:
            var = pfp_utils.CreateEmptyVariable(label, nrecs, attr=info["Variables"][label]["Attr"])
            pfp_utils.CreateVariable(ds, var)
        result = getattr(pfp_func_transforms, functions[label]["name"])(ds, label, *functions[label]["arguments"])
        if result:
            msg = " Completed function for " + label
            logger.info(msg)
    return

def CalculateStandardDeviations(ds):
    """
    Purpose:
     Calculate standard deviations from variances and vice versa.
    Usage:
     pfp_ts.CalculateStandardDeviations(ds)
     where ds is a data structure
    Author: PRI
    Date: Back in the day
    """
    logger.info(" Getting variances from standard deviations & vice versa")
    # !!! this section deals with messy legacy variable names !!!
    # initialise lists of variables that have been done
    sd_done = []
    vr_done = []
    # get a dictionary of variances and the stanard deviations we want from them
    d = {"AH_IRGA_Vr": {"sd_label": "AH_IRGA_Sd",
                        "long_name": "Absolute humidity",
                        "statistic_type": "standard_deviation",
                        "units": "g/m^3"},
         "H2O_IRGA_Vr": {"sd_label": "H2O_IRGA_Sd",
                         "long_name": "H2O concentration",
                         "statistic_type": "standard_deviation",
                         "units": "mmol/m^3"},
         "CO2_IRGA_Vr": {"sd_label": "CO2_IRGA_Sd",
                         "long_name": "CO2 concentration",
                         "statistic_type": "standard_deviation",
                         "units": "mg/m^3"},
         "Ux_SONIC_Vr": {"sd_label": "Ux_SONIC_Sd",
                         "long_name": "Longitudinal wind velocity component, sonic coordinates",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"},
         "Uy_SONIC_Vr": {"sd_label": "Uy_SONIC_Sd",
                         "long_name": "Lateral wind velocity component, sonic coordinates",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"},
         "Uz_SONIC_Vr": {"sd_label": "Uz_SONIC_Sd",
                         "long_name": "Vertical wind velocity component, sonic coordinates",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"},
         "Tv_SONIC_Vr": {"sd_label": "Tv_SONIC_Sd",
                         "long_name": "Virtual temperature",
                         "statistic_type": "standard_deviation",
                         "units": "degC"},
         "U_SONIC_Vr": {"sd_label": "U_SONIC_Sd",
                         "long_name": "Along wind velocity component",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"},
         "V_SONIC_Vr": {"sd_label": "V_SONIC_Sd",
                         "long_name": "Across wind velocity component",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"},
         "W_SONIC_Vr": {"sd_label": "W_SONIC_Sd",
                         "long_name": "Vertical wind velocity component",
                         "statistic_type": "standard_deviation",
                         "units": "m/s"}}
    # get a list of variables in the data structure
    labels = list(ds.root["Variables"].keys())
    # loop over the variances and create the standard deviations
    for vr_label in list(d.keys()):
        if vr_label in labels and d[vr_label]["sd_label"] not in labels:
            vr = pfp_utils.GetVariable(ds, vr_label)
            sd = copy.deepcopy(vr)
            sd["Label"] = d[vr_label]["sd_label"]
            sd["Data"] = numpy.ma.sqrt(vr["Data"])
            sd["Attr"]["long_name"] = d[vr_label]["long_name"]
            sd["Attr"]["statistic_type"] = d[vr_label]["statistic_type"]
            sd["Attr"]["units"] = d[vr_label]["units"]
            pfp_utils.CreateVariable(ds, sd)
            sd_done.append(sd["Label"])
    # now do the same with the standard deviations
    d = {"AH_IRGA_Sd": {"vr_label": "AH_IRGA_Vr",
                        "long_name": "Absolute humidity",
                        "statistic_type": "variance",
                        "units": "g^2/m^6"},
         "H2O_IRGA_Sd": {"vr_label": "H2O_IRGA_Vr",
                         "long_name": "H2O concentration",
                         "statistic_type": "variance",
                         "units": "mmol^2/m^6"},
         "CO2_IRGA_Sd": {"vr_label": "CO2_IRGA_Vr",
                         "long_name": "CO2 concentration",
                         "statistic_type": "variance",
                         "units": "mg^2/m^6"},
         "Ux_SONIC_Sd": {"vr_label": "Ux_SONIC_Vr",
                         "long_name": "Longitudinal wind velocity component, sonic coordinates",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"},
         "Uy_SONIC_Sd": {"vr_label": "Uy_SONIC_Vr",
                         "long_name": "Lateral wind velocity component, sonic coordinates",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"},
         "Uz_SONIC_Sd": {"vr_label": "Uz_SONIC_Vr",
                         "long_name": "Vertical wind velocity component, sonic coordinates",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"},
         "Tv_SONIC_Sd": {"vr_label": "Tv_SONIC_Vr",
                         "long_name": "Virtual temperature",
                         "statistic_type": "variance",
                         "units": "degC^2"},
         "U_SONIC_Sd": {"vr_label": "U_SONIC_Vr",
                         "long_name": "Along wind velocity component",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"},
         "V_SONIC_Sd": {"vr_label": "V_SONIC_Vr",
                         "long_name": "Across wind velocity component",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"},
         "W_SONIC_Sd": {"vr_label": "W_SONIC_Vr",
                         "long_name": "Vertical wind velocity component",
                         "statistic_type": "variance",
                         "units": "m^2/s^2"}}
    labels = list(ds.root["Variables"].keys())
    # loop over the standard deviations and create the variances
    for sd_label in list(d.keys()):
        if sd_label in labels and d[sd_label]["vr_label"] not in labels and sd_label not in sd_done:
            sd = pfp_utils.GetVariable(ds, sd_label)
            vr = copy.deepcopy(sd)
            vr["Label"] = d[sd_label]["vr_label"]
            vr["Data"] = sd["Data"]*sd["Data"]
            vr["Attr"]["long_name"] = d[sd_label]["long_name"]
            vr["Attr"]["statistic_type"] = d[sd_label]["statistic_type"]
            vr["Attr"]["units"] = d[sd_label]["units"]
            pfp_utils.CreateVariable(ds, vr)
            vr_done.append(vr["Label"])
    return

def Fco2_WPL(cf, ds, CO2_in="CO2", Fco2_in="Fco2"):
    """
        Apply Webb, Pearman and Leuning correction to carbon flux.  This
        correction is necessary to account for flux effects on density
        measurements.  Original formulation: Campbell Scientific

        Usage pfp_ts.Fc_WPL(cf, ds)
        cf: control file
        ds: data structure

        Used for fluxes that are raw or rotated.

        Pre-requisite: CalculateFluxes, CalculateFluxes_Unrotated or CalculateFluxesRM
        Pre-requisite: FhvtoFh
        Pre-requisite: Fe_WPL

        Accepts meteorological constants or variables
        """
    ds.info["returncodes"]["message"] = ""
    ds.info["returncodes"]["value"] = 0
    # get the IRGA type
    irga_type = str(ds.root["Attributes"]["irga_type"])
    # define the known IRGAs, this should be an external settings option
    closed_path_irgas = list(c.instruments["irgas"]["closed_path"].keys())
    open_path_irgas = list(c.instruments["irgas"]["open_path"].keys())
    # WPL correction only applied to open-path IRGAs
    if (irga_type in closed_path_irgas):
        msg = " WPL (Fco2): closed-path IRGA type (" + irga_type + "), WPL not applied"
        logger.info(msg)
        return
    elif (irga_type in open_path_irgas):
        pass
    else:
        msg = " WPL (Fco2): unrecognised IRGA type (" + irga_type + "), WPL not applied"
        logger.error(msg)
        ds.info["returncodes"]["value"] = 1
        ds.info["returncodes"]["message"] = msg
        return
    msg = " Applying WPL correction to Fco2 (IRGA type is " + irga_type + ")"
    logger.info(msg)
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Fco2 = pfp_utils.GetVariable(ds, Fco2_in)
    Fh = pfp_utils.GetVariable(ds, "Fh")
    Fe = pfp_utils.GetVariable(ds, "Fe")
    Ta = pfp_utils.GetVariable(ds, "Ta")
    Ta["Data"] = Ta["Data"] + c.C2K
    AH = pfp_utils.GetVariable(ds, "AH")
    AH["Data"] = AH["Data"] * c.g2kg
    rhod = pfp_utils.GetVariable(ds, "rhod")
    RhoCp = pfp_utils.GetVariable(ds, "RhoCp")
    Lv = pfp_utils.GetVariable(ds, "Lv")
    CO2 = pfp_utils.GetVariable(ds, CO2_in)
    CO2 = pfp_utils.convert_units_func(ds, CO2, "mg/m^3")
    sigma = AH["Data"] / rhod["Data"]
    co2_wpl_Fe = (c.mu/(1+c.mu*sigma))*(CO2["Data"]/rhod["Data"])*(Fe["Data"]/Lv["Data"])
    co2_wpl_Fh = (CO2["Data"]/Ta["Data"])*(Fh["Data"]/RhoCp["Data"])
    Fco2_wpl_data = Fco2["Data"] + co2_wpl_Fe + co2_wpl_Fh
    Fco2_wpl_flag = numpy.zeros(len(Fco2_wpl_data))
    index = numpy.where(numpy.ma.getmaskarray(Fco2_wpl_data) == True)[0]
    Fco2_wpl_flag[index] = numpy.int32(14)
    attr = {"long_name": "CO2 flux", "units": "mg/m^2/s", "statistic_type": "average"}
    pfp_utils.append_to_attribute(attr, {descr_level: "WPL corrected"})
    for item in ["instrument", "height"]:
        if item in Fco2["Attr"]:
            attr[item] = Fco2["Attr"][item]
    variable = {"Label": "Fco2", "Data": Fco2_wpl_data, "Flag": Fco2_wpl_flag, "Attr": attr}
    pfp_utils.CreateVariable(ds, variable)
    variable = {"Label": "Fco2_PFP", "Data": Fco2_wpl_data, "Flag": Fco2_wpl_flag, "Attr": attr}
    pfp_utils.CreateVariable(ds, variable)
    return

def Fe_WPL(cf, ds):
    """
        Apply Webb, Pearman and Leuning correction to vapour flux.  This
        correction is necessary to account for flux effects on density
        measurements.  Original formulation: Campbell Scientific

        Usage pfp_ts.Fe_WPL(cf, ds)
        cf: control file
        ds: data structure

        Used for fluxes that are raw or rotated.

        Pre-requisite: CalculateFluxes, CalculateFluxes_Unrotated or CalculateFluxesRM
        Pre-requisite: FhvtoFh

        Accepts meteorological constants or variables
        """
    ds.info["returncodes"]["message"] = ""
    ds.info["returncodes"]["value"] = 0
    # get the IRGA type
    irga_type = str(ds.root["Attributes"]["irga_type"])
    # define the known IRGAs, this should be an external settings option
    closed_path_irgas = list(c.instruments["irgas"]["closed_path"].keys())
    open_path_irgas = list(c.instruments["irgas"]["open_path"].keys())
    if (irga_type in closed_path_irgas):
        msg = " WPL (Fe): closed-path IRGA type (" + irga_type + "), WPL not applied"
        logger.info(msg)
        return
    elif (irga_type in open_path_irgas):
        pass
    else:
        msg = " WPL (Fe): unrecognised IRGA type (" + irga_type + "), WPL not applied"
        logger.error(msg)
        ds.info["returncodes"]["value"] = 1
        ds.info["returncodes"]["message"] = msg
        return
    msg = " Applying WPL correction to Fe (IRGA type is " + irga_type + ")"
    logger.info(msg)
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    Fe = pfp_utils.GetVariable(ds, "Fe")
    Fh = pfp_utils.GetVariable(ds, "Fh")
    Ta = pfp_utils.GetVariable(ds, "Ta")
    Ta["Data"] = Ta["Data"] + c.C2K
    AH = pfp_utils.GetVariable(ds, "AH")
    rhod = pfp_utils.GetVariable(ds, "rhod")
    RhoCp = pfp_utils.GetVariable(ds, "RhoCp")
    Lv = pfp_utils.GetVariable(ds, "Lv")
    AH["Data"] = AH["Data"]*c.g2kg
    sigma = AH["Data"]/rhod["Data"]
    h2o_wpl_Fe = c.mu*sigma*Fe["Data"]
    h2o_wpl_Fh = (1+c.mu*sigma)*AH["Data"]*Lv["Data"]*(Fh["Data"]/RhoCp["Data"])/Ta["Data"]
    Fe_wpl_data = Fe["Data"] + h2o_wpl_Fe + h2o_wpl_Fh
    Fe_wpl_flag = numpy.zeros(len(Fe_wpl_data))
    idx = numpy.where(numpy.ma.getmaskarray(Fe_wpl_data) == True)[0]
    Fe_wpl_flag[idx] = numpy.int32(14)
    attr = {"long_name": "Latent heat flux", "units": "W/m^2",
            "standard_name": "surface_upward_latent_heat_flux",
            "statistic_type": "average"}
    pfp_utils.append_to_attribute(attr, {descr_level: "WPL corrected"})
    for item in ["instrument", "height"]:
        if item in Fe["Attr"]:
            attr[item] = Fe["Attr"][item]
    variable = {"Label": "Fe", "Data": Fe_wpl_data, "Flag": Fe_wpl_flag, "Attr": attr}
    pfp_utils.CreateVariable(ds, variable)
    variable = {"Label": "Fe_PFP", "Data": Fe_wpl_data, "Flag": Fe_wpl_flag, "Attr": attr}
    pfp_utils.CreateVariable(ds, variable)
    return

def FhvtoFh(cf, ds, Tv_in = "Tv_SONIC_Av"):
    '''
    Convert the virtual heat flux to the sensible heat flux.
    USEAGE:
     pfp_ts.FhvtoFh(cf, ds)
    INPUT:
     All inputs are read from the data structure.
    OUTPUT:
     All outputs are written to the data structure.
    '''
    logger.info(" Converting virtual Fhv to Fh")
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs,dtype=numpy.int32)
    ones = numpy.ones(nRecs,dtype=numpy.int32)
    # get the input series
    Fhv = pfp_utils.GetVariable(ds, "Fhv")              # get the virtual heat flux
    Tv = pfp_utils.GetVariable(ds, Tv_in)               # get the virtual temperature, C
    Tv["Data"] = Tv["Data"] + c.C2K                     # convert from C to K
    wA = pfp_utils.GetVariable(ds, "wA")                # get the wA covariance, g/m^2/s
    wA["Data"] = wA["Data"] * c.g2kg                    # convert from g/m^2/s to kg/m2/s
    SH = pfp_utils.GetVariable(ds, "SH")                # get the specific humidity, kg/kg
    wT = pfp_utils.GetVariable(ds, "wT")                # get the wT covariance, m.K/s
    # get the utility series
    RhoCp = pfp_utils.GetVariable(ds, "RhoCp")          # get rho*Cp
    rhom = pfp_utils.GetVariable(ds, "rhom")            # get the moist air density, kg/m3
    # define local constants
    alpha = 0.51
    # do the conversion
    t1 = RhoCp["Data"]*alpha*Tv["Data"]*wA["Data"]/rhom["Data"]
    t2 = RhoCp["Data"]*alpha*SH["Data"]*wT["Data"]
    Fh = Fhv["Data"] - t1 - t2
    # put the calculated sensible heat flux into the data structure
    attr = {"long_name": "Sensible heat flux", "units": "W/m^2",
            "standard_name": "surface_upward_sensible_heat_flux",
            "statistic_type": "average"}
    for item in ["instrument", "height"]:
        if item in wT["Attr"]:
            attr[item] = wT["Attr"][item]
    flag = numpy.where(numpy.ma.getmaskarray(Fh) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": "Fh", "Data": Fh, "Flag": flag, "Attr": attr})
    pfp_utils.CreateVariable(ds, {"Label": "Fh_PFP", "Data": Fh, "Flag": flag, "Attr": attr})
    if pfp_utils.get_optionskeyaslogical(cf, "UseFhvforFh"):
        nok_before = (ds.root["Variables"]["Fh"]["Data"] != c.missing_value).sum()
        ReplaceWhereMissing(ds.root["Variables"]['Fh'], ds.root["Variables"]['Fh'], ds.root["Variables"]['Fhv'], FlagValue=20)
        nok_after = (ds.root["Variables"]["Fh"]["Data"] != c.missing_value).sum()
        percent_replaced = numpy.rint(100 * (nok_after - nok_before) / nRecs)
        msg = "  " + str(percent_replaced) + "% of Fh values replaced with Fhv"
        if percent_replaced < 10:
            logger.info(msg)
        else:
            logger.warning(msg)
    return

def get_averages(Data):
    """
        Get daily averages on days when no 30-min observations are missing.
        Days with missing observations return a value of c.missing_value
        Values returned are sample size (Num) and average (Av)

        Usage pfp_ts.get_averages(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(abs(Data-float(c.missing_value))>c.eps)
    Num = numpy.size(li)
    if Num == 0:
        Av = c.missing_value
    elif Num == 48:
        Av = numpy.ma.mean(Data[li])
    else:
        x = 0
        index = numpy.ma.where(Data.mask == True)[0]
        if len(index) == 1:
            x = 1
        elif len(index) > 1:
            for i in range(len(Data)):
                if Data.mask[i] == True:
                    x = x + 1

        if x == 0:
            Av = numpy.ma.mean(Data[li])
        else:
            Av = c.missing_value
    return Num, Av

def get_laggedcorrelation(x_in,y_in,maxlags):
    """
    Calculate the lagged cross-correlation between 2 1D arrays.
    Taken from the matplotlib.pyplot.xcorr source code.
    PRI added handling of masked arrays.
    """
    lags = numpy.arange(-maxlags,maxlags+1)
    mask = numpy.ma.mask_or(x_in.mask,y_in.mask,copy=True,shrink=False)
    x = numpy.ma.array(x_in, mask=mask, copy=True)
    y = numpy.ma.array(y_in, mask=mask, copy=True)
    x = numpy.ma.compressed(x)
    y = numpy.ma.compressed(y)
    corr = numpy.correlate(x, y, mode=2)
    corr/= numpy.sqrt(numpy.dot(x,x) * numpy.dot(y,y))
    if maxlags is None: maxlags = len(x) - 1
    if maxlags >= len(x) or maxlags < 1:
        raise ValueError('pfp_ts.get_laggedcorrelation: maxlags must be None or strictly positive < %d'%len(x))
    corr = corr[len(x)-1-maxlags:len(x)+maxlags]
    return lags,corr

def get_minmax(Data):
    """
        Get daily minima and maxima on days when no 30-min observations are missing.
        Days with missing observations return a value of c.missing_value
        Values returned are sample size (Num), minimum (Min) and maximum (Max)

        Usage pfp_ts.get_minmax(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(abs(Data-float(c.missing_value))>c.eps)
    Num = numpy.size(li)
    if Num == 0:
        Min = c.missing_value
        Max = c.missing_value
    elif Num == 48:
        Min = numpy.ma.min(Data[li])
        Max = numpy.ma.max(Data[li])
    else:
        x = 0
        index = numpy.ma.where(Data.mask == True)[0]
        if len(index) == 1:
            x = 1
        elif len(index) > 1:
            for i in range(len(Data)):
                if Data.mask[i] == True:
                    x = x + 1

        if x == 0:
            Min = numpy.ma.min(Data[li])
            Max = numpy.ma.max(Data[li])
        else:
            Min = c.missing_value
            Max = c.missing_value
    return Num, Min, Max

def get_nightsums(Data):
    """
        Get nightly sums and averages on nights when no 30-min observations are missing.
        Nights with missing observations return a value of c.missing_value
        Values returned are sample size (Num), sums (Sum) and average (Av)

        Usage pfp_ts.get_nightsums(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(Data.mask == False)[0]
    Num = numpy.size(li)
    if Num == 0:
        Sum = c.missing_value
        Av = c.missing_value
    else:
        x = 0
        for i in range(len(Data)):
            if Data.mask[i] == True:
                x = x + 1

        if x == 0:
            Sum = numpy.ma.sum(Data[li])
            Av = numpy.ma.mean(Data[li])
        else:
            Sum = c.missing_value
            Av = c.missing_value

    return Num, Sum, Av

def get_soilaverages(Data):
    """
        Get daily averages of soil water content on days when 15 or fewer 30-min observations are missing.
        Days with 16 or more missing observations return a value of c.missing_value
        Values returned are sample size (Num) and average (Av)

        Usage pfp_ts.get_soilaverages(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(abs(Data-float(c.missing_value))>c.eps)
    Num = numpy.size(li)
    if Num > 33:
        Av = numpy.ma.mean(Data[li])
    else:
        Av = c.missing_value
    return Num, Av

def get_subsums(Data):
    """
        Get separate daily sums of positive and negative fluxes when no 30-min observations are missing.
        Days with missing observations return a value of c.missing_value
        Values returned are positive and negative sample sizes (PosNum and NegNum) and sums (SumPos and SumNeg)

        Usage pfp_ts.get_subsums(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(abs(Data-float(c.missing_value))>c.eps)
    Num = numpy.size(li)
    if Num == 48:
        pi = numpy.ma.where(Data[li]>0)
        ni = numpy.ma.where(Data[li]<0)
        PosNum = numpy.size(pi)
        NegNum = numpy.size(ni)
        if PosNum > 0:
            SumPos = numpy.ma.sum(Data[pi])
        else:
            SumPos = 0
        if NegNum > 0:
            SumNeg = numpy.ma.sum(Data[ni])
        else:
            SumNeg = 0
    else:
        pi = numpy.ma.where(Data[li]>0)
        ni = numpy.ma.where(Data[li]<0)
        PosNum = numpy.size(pi)
        NegNum = numpy.size(ni)
        SumPos = c.missing_value
        SumNeg = c.missing_value
    return PosNum, NegNum, SumPos, SumNeg

def get_sums(Data):
    """
        Get daily sums when no 30-min observations are missing.
        Days with missing observations return a value of c.missing_value
        Values returned are sample size (Num) and sum (Sum)

        Usage pfp_ts.get_sums(Data)
        Data: 1-day dataset
        """
    li = numpy.ma.where(abs(Data-float(c.missing_value))>c.eps)
    Num = numpy.size(li)
    if Num == 0:
        Sum = c.missing_value
    elif Num == 48:
        Sum = numpy.ma.sum(Data[li])
    else:
        x = 0
        index = numpy.ma.where(Data.mask == True)[0]
        if len(index) == 1:
            x = 1
        elif len(index) > 1:
            for i in range(len(Data)):
                if Data.mask[i] == True:
                    x = x + 1

        if x == 0:
            Sum = numpy.ma.sum(Data[li])
        else:
            Sum = c.missing_value
    return Num, Sum

def get_qcflag(ds):
    """
        Set up flags during ingest of L1 data.
        Identifies missing observations as c.missing_value and sets flag value 1

        Usage pfp_ts.get_qcflag(ds)
        ds: data structure
        """
    logger.info(' Setting up the QC flags')
    nRecs = len(ds.root["Variables"]['xlDateTime']['Data'])
    for ThisOne in list(ds.root["Variables"].keys()):
        ds.root["Variables"][ThisOne]['Flag'] = numpy.zeros(nRecs,dtype=numpy.int32)
        index = numpy.where(ds.root["Variables"][ThisOne]['Data']==c.missing_value)[0]
        ds.root["Variables"][ThisOne]['Flag'][index] = numpy.int32(1)

def get_synthetic_fsd(ds):
    """
    Purpose:
     Calculates a time series of synthetic downwelling shortwave radiation.  The
     solar altitude is also output.
    Useage:
     pfp_ts.get_synthetic_fsd(ds)
    Author: PRI
    Date: Sometime in 2014
    """
    logger.info(' Calculating synthetic Fsd')
    nrecs = int(float(ds.root["Attributes"]["nc_nrecs"]))
    Fsd_syn = pfp_utils.CreateEmptyVariable("Fsd_syn", nrecs)
    solar_altitude = pfp_utils.CreateEmptyVariable("solar_altitude", nrecs)
    # get the latitude and longitude
    lat = float(ds.root["Attributes"]["latitude"])
    lon = float(ds.root["Attributes"]["longitude"])
    # get the UTC time from the local time
    ldt_UTC = pfp_utils.get_UTCfromlocaltime(ds)
    # get the solar altitude
    solar_altitude["Data"] = [pysolar.GetAltitude(lat, lon, dt) for dt in ldt_UTC]
    # get the synthetic downwelling shortwave radiation
    Fsd_syn["Data"] = [pysolar.GetRadiationDirect(dt, alt)
                       for dt, alt in
                       zip(ldt_UTC, solar_altitude["Data"])]
    Fsd_syn["Data"] = numpy.ma.array(Fsd_syn["Data"], copy=True)
    # get the QC flag
    Fsd_syn["Flag"] = numpy.zeros(nrecs, dtype=numpy.int32)
    # add the synthetic downwelling shortwave radiation to the data structure
    Fsd_syn["Attr"] = {"long_name": "Synthetic downwelling shortwave radiation",
                       "units": "W/m^2",
                       "standard_name": "surface_downwelling_shortwave_flux_in_air",
                       "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, Fsd_syn)
    ds.info["intermediate"].append("Fsd_syn")
    # add the solar altitude to the data structure
    solar_altitude["Attr"] = {"long_name": "Solar altitude",
                              "units": "degrees", "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, solar_altitude)
    ds.info["intermediate"].append("solar_altitude")

def InvertSign(ds,ThisOne):
    logger.info(' Inverting sign of '+ThisOne)
    index = numpy.where(abs(ds.root["Variables"][ThisOne]['Data']-float(c.missing_value))>c.eps)[0]
    ds.root["Variables"][ThisOne]['Data'][index] = float(-1)*ds.root["Variables"][ThisOne]['Data'][index]

def InterpolateDataStructure(ds_old, labels=None, new_time_step=30, interpolation="Akima",
                             sums="skip", mode="verbose"):
    """
    Purpose:
     Interpolate a data structure on to a new time step.
    Usage:
    Side effects:
     Returns a data structure with data interpolated onto a new time step.
    Author: PRI
    Date: April 2021
    """
    # coerce the new and old time steps to integers
    new_time_step = int(float(new_time_step))
    old_time_step = int(float(ds_old.root["Attributes"]["time_step"]))
    # sanity checks
    if ((new_time_step == old_time_step) and (mode != "quiet")):
        msg = " New time step equal to old time step, no interpolation needed ..."
        logger.info(msg)
        ds_new = copy.deepcopy(ds_old)
        return ds_new
    if ((interpolation not in ["linear", "Akima"]) and (mode != "quiet")):
        msg = " Unrecognised interpolation type (" + str(interpolation) +"), no interpolation done ..."
        logger.error(msg)
        ds_new = copy.deepcopy(ds_old)
        return ds_new
    if ((sums not in ["skip", "interpolate"]) and (mode != "quiet")):
        msg = " Unrecognised sums option (" + str(sums) +"), no interpolation done ..."
        logger.error(msg)
        ds_new = copy.deepcopy(ds_old)
        return ds_new
    # create a new data structure
    ds_new = pfp_io.DataStructure()
    # copy the global attributes
    ds_new.root["Attributes"] = copy.deepcopy(ds_old.root["Attributes"])
    # update the time step global attribute
    ds_new.root["Attributes"]["time_step"] = new_time_step
    # generate a datetime variable at the new time step
    dt_old = pfp_utils.GetVariable(ds_old, "DateTime")
    start_date = dt_old["Data"][0]
    end_date = dt_old["Data"][-1]
    delta = datetime.timedelta(minutes=new_time_step)
    dt_tmp = numpy.array([dt for dt in pfp_utils.perdelta(start_date, end_date, delta)])
    nrecs = len(dt_tmp)
    # and update the nc_nrecs global attribute
    ds_new.root["Attributes"]["nc_nrecs"] = nrecs
    dt_new = {"Label": "DateTime", "Data": dt_tmp,
              "Flag": numpy.zeros(nrecs),
              "Attr": dt_old["Attr"]}
    pfp_utils.CreateVariable(ds_new, dt_new)
    # check the labels to be interpolated
    if labels is None:
        # generate list of labels from data structure
        labels = [l for l in list(ds_old.root["Variables"].keys()) if "DateTime" not in l]
    else:
        for label in list(labels):
            if label not in list(ds_old.root["Variables"].keys()):
                labels.remove(label)
        if ((len(labels) == 0) and (mode != "quiet")):
            msg = " Requested variables not found in data structure, skipping interpolation ..."
            logger.error(msg)
            return ds_new
    # get the indices of matching times
    iA, iB = pfp_utils.FindMatchingIndices(dt_old["Data"], dt_new["Data"])
    # copy the old data onto the new time step
    for label in labels:
        # create an empty variable with the new time step
        var_new = pfp_utils.CreateEmptyVariable(label, nrecs)
        # get the old variable at the old time step
        var_old = pfp_utils.GetVariable(ds_old, label)
        # copy data at the old time step to the new time step
        var_new["Data"][iB] = var_old["Data"][iA]
        var_new["Flag"][iB] = var_old["Flag"][iA]
        # copy the variable attributes
        var_new["Attr"] = copy.deepcopy(var_old["Attr"])
        # create the new variable
        pfp_utils.CreateVariable(ds_new, var_new)
    # and then interpolate
    InterpolateOverMissing(ds_new, labels, max_length_hours=3, int_type=interpolation, sums=sums)
    return ds_new

def InterpolateOverMissing(ds, labels, max_length_hours=0, int_type="linear", sums="skip"):
    """
    Purpose:
     Interpolate over periods of missing data.  Uses linear interpolation.
    Usage:
     pfp_ts.InterpolateOverMissing(ds, labels, max_length_hours=0, int_type="linear", sums="skip")
     where ds is the data structure
           label is a series label or a list of labels
           max_length_hours is the maximum gap length (hours) to be filled by interpolation
           int_type is the interpolation type ("linear" or "Akima")
           sums is how to treat variables with a statistic_type of "sum" ("skip" or "interpolate")
    Side effects:
     Fills gaps.
    Author: PRI
    Date: September 2014
    """
    # check to see if we need to do anything
    if max_length_hours == 0:
        msg = " Interpolation disabled (max_length_hours set to 0)"
        logger.info(msg)
        return
    if isinstance(labels, str):
        labels = [labels]
    elif isinstance(labels, list):
        pass
    else:
        msg = " Input label " + labels + " must be a string or a list"
        logger.error(msg)
        return
    ts = int(float(ds.root["Attributes"]["time_step"]))
    max_length_points = int((max_length_hours * float(60)/float(ts)) + 0.5)
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    for label in labels:
        # check that series is in the data structure
        if label not in list(ds.root["Variables"].keys()):
            msg = " Variable " + label + " not found in data structure"
            logger.error(msg)
            continue
        # get the data
        var = pfp_utils.GetVariable(ds, label)
        # check statistic type and options for sums
        if var["Attr"]["statistic_type"] in ["sum", "total"]:
            if sums == "interpolate":
                # set the sum flag and the first data point
                is_sum = True
                first_data_point = var["Data"][0]
                # convert sum or total to accumulated quantity
                var["Data"] = numpy.ma.cumsum(var["Data"])
                # update the statistic_type variable attribute
                var["Attr"]["statistic_type"] = "accumulated"
                # force the interpolaton type to linear
                interpolation = "linear"
            else:
                msg = label + " not interpolated (statistic type="
                msg += var["Attr"]["statistic_type"] + ", sums=" + sums + ")"
                logger.warning(msg)
                continue
        else:
            is_sum = False
            interpolation = int_type

        # convert the Python datetime to a number
        DateNum = date2num(ds.root["Variables"]["DateTime"]["Data"])
        # index of good values
        mask = numpy.ma.getmaskarray(var["Data"])
        iog = numpy.where(mask == False)[0]
        # index of missing values
        iom = numpy.where(mask == True)[0]
        # return if there is not enough data to use
        if len(iog) < 2:
            msg = " Less than 2 good points available for interpolation " + str(label)
            logger.info(msg)
            continue
        # remove masked data and convert to ndarray
        data = numpy.ma.compressed(var["Data"][iog])
        # copy the original flag
        flag_int = numpy.copy(var["Flag"])
        # do the interpolation
        if interpolation == "linear":
            # linear interpolation function
            int_fn = interpolate.interp1d(DateNum[iog], data, bounds_error=False)
            # interpolate over the whole time series
            data_int = int_fn(DateNum).astype(numpy.float64)
        elif interpolation == "Akima":
            int_fn = interpolate.Akima1DInterpolator(DateNum[iog], data)
            data_int = int_fn(DateNum).astype(numpy.float64)
        else:
            msg = " Unrecognised interpolator option (" + int_type + "), skipping ..."
            logger.error(msg)
            continue
        # trap non-finite values from the Akima 1D interpolator
        idx = numpy.where(numpy.isfinite(data_int) != True)[0]
        data_int = numpy.ma.masked_where(numpy.isfinite(data_int) != True, data_int)
        # set the flag of interpolated points to 50
        flag_int[iom] = numpy.int32(50)
        # and to 51 where the interpolation did not provide a value
        flag_int[idx] = numpy.int32(51)

        # convert from accumulated back to instantaneous
        if is_sum:
            data_int = numpy.ma.ediff1d(data_int, to_begin=first_data_point)
            var["Attr"]["statistic_type"] = "sum"

        # now replace data in contiguous blocks of length > min with missing data
        # first, a conditional index, 0 where data is good, 1 where it is missing
        cond_ind = numpy.zeros(nRecs, dtype=numpy.int32)
        cond_ind[iom] = 1
        cond_bool = (cond_ind == 1)
        # start and stop indices of contiguous blocks
        mask_int = numpy.ma.getmaskarray(data_int)
        for start, stop in pfp_utils.contiguous_regions(cond_bool):
            # code to handle minimum segment length goes here
            duration = stop - start
            if duration > max_length_points:
                mask_int[start:stop] = True
                flag_int[start:stop] = var["Flag"][start:stop]
        data_int = numpy.ma.masked_where(mask_int == True, data_int)
        # put data_int back into the data structure
        var["Data"] = data_int
        var["Flag"] = flag_int
        pfp_utils.CreateVariable(ds, var)
    return

def MassmanStandard(cf, ds, Ta_in='Ta', AH_in='AH', ps_in='ps', u_in="U_SONIC_Av",
                    ustar_in='ustar', ustar_out='ustar', L_in='L', L_out ='L',
                    uw_out='uw', vw_out='vw', wT_out='wT', wA_out='wA', wC_out='wC'):
    """
       Massman corrections.
       The steps involved are as follows:
        1) calculate ustar and L using rotated but otherwise uncorrected covariances
       """
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "MassmanCorrection", default="Yes")
    if (opt.lower() != "yes"):
        msg = " Massman frequency correction disabled in control file, skipping correction ..."
        logger.warning(msg)
        return
    if "Massman" not in cf:
        msg = " Massman section not in control file, skipping frequency correction ..."
        logger.warning(msg)
        return
    logger.info(" Correcting for flux loss from spectral attenuation")
    descr_level = str(ds.root["Attributes"]["processing_level"])
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    zeros = numpy.zeros(nRecs, dtype=numpy.int32)
    ones = numpy.ones(nRecs, dtype=numpy.int32)
    zmd = float(cf["Massman"]["zmd"])             # z-d for site
    if ("angle" in cf["Massman"] and
        "CSATarm" in cf["Massman"] and
        "IRGAarm" in cf["Massman"]):
        # this is the original definition of lateral and longitudinal separation
        # as coded by James
        angle = float(cf["Massman"]["angle"])         # CSAT3-IRGA separation angle
        CSATarm = float(cf["Massman"]["CSATarm"])     # CSAT3 mounting distance
        IRGAarm = float(cf["Massman"]["IRGAarm"])     # IRGA mounting distance
        lLat = numpy.ma.sin(numpy.deg2rad(angle)) * IRGAarm
        lLong = CSATarm - (numpy.ma.cos(numpy.deg2rad(angle)) * IRGAarm)
    elif ("north_separation" in cf["Massman"] and
          "east_separation" in cf["Massman"]):
        # the following is the definition of lateral and longitudinal separation
        # used in EddyPro, it is not equivalent to the one used above
        nsep = float(cf["Massman"]["north_separation"])
        esep = float(cf["Massman"]["east_separation"])
        lLat = numpy.sqrt(nsep*nsep + esep*esep)
        lLong = float(0)
    else:
        msg = " Required separation information not found in Massman section of control file"
        logger.error(msg)
        return
    # *** Massman_1stpass starts here ***
    #  The code for the first and second passes is very similar.  It would be useful to make them the
    #  same and put into a loop to reduce the number of lines in this function.
    # calculate ustar and Monin-Obukhov length from rotated but otherwise uncorrected covariances
    # get some instrument specific constants
    sonic_type = str(ds.root["Attributes"]["sonic_type"])
    irga_type = str(ds.root["Attributes"]["irga_type"])
    lwVert = c.instruments["sonics"][sonic_type]["lwVert"]
    lwHor = c.instruments["sonics"][sonic_type]["lwHor"]
    lTv = c.instruments["sonics"][sonic_type]["lTv"]
    for path_type in list(c.instruments["irgas"].keys()):
        if irga_type in list(c.instruments["irgas"][path_type].keys()):
            break
    dIRGA = c.instruments["irgas"][path_type][irga_type]["dIRGA"]
    lIRGA = c.instruments["irgas"][path_type][irga_type]["lIRGA"]
    Ta = pfp_utils.GetVariable(ds, Ta_in)
    AH = pfp_utils.GetVariable(ds, AH_in)
    ps = pfp_utils.GetVariable(ds, ps_in)
    u = pfp_utils.GetVariable(ds, u_in)
    uw = pfp_utils.GetVariable(ds, "uw")
    vw = pfp_utils.GetVariable(ds, "vw")
    wT = pfp_utils.GetVariable(ds, "wT")
    wC = pfp_utils.GetVariable(ds, "wC")
    wA = pfp_utils.GetVariable(ds, "wA")
    if ustar_in not in list(ds.root["Variables"].keys()):
        ustarm = pfp_utils.CreateEmptyVariable(ustar_in, nRecs)
        ustarm["Data"] = numpy.ma.sqrt(numpy.ma.sqrt(uw["Data"] ** 2 + vw["Data"] ** 2))
    else:
        ustarm = pfp_utils.GetVariable(ds, ustar_in)
    if L_in not in list(ds.root["Variables"].keys()):
        Lm = pfp_utils.CreateEmptyVariable(L_in, nRecs)
        Lm["Data"] = pfp_mf.molen(Ta["Data"], AH["Data"], ps["Data"], ustarm["Data"], wT["Data"],
                                  fluxtype="kinematic")
    else:
        Lm = pfp_utils.GetVariable(ds, L_in)
    # now calculate z on L
    zoLm = zmd / Lm["Data"]
    # start calculating the correction coefficients for approximate corrections
    #  create nxMom, nxScalar and alpha series with their unstable values by default
    nxMom, nxScalar, alpha = pfp_utils.nxMom_nxScalar_alpha(zoLm)
    # now calculate the fxMom and fxScalar coefficients
    fxMom = nxMom * u["Data"] / zmd
    fxScalar = nxScalar * u["Data"] / zmd
    # compute spectral filters
    tau_sonic_law_4scalar = lwVert / (8.4 * u["Data"])
    tau_sonic_laT_4scalar = lTv / (4.0 * u["Data"])
    tau_irga_la = (lIRGA / (4.0 * u["Data"]))
    tau_irga_va = (0.2+0.4*dIRGA/lIRGA)*(lIRGA/u["Data"])
    tau_irga_bw = 0.016
    tau_irga_lat = (lLat / (1.1 * u["Data"]))
    tau_irga_lon = (lLong / (1.05 * u["Data"]))

    tao_eMom = numpy.ma.sqrt(((lwVert / (5.7 * u["Data"])) ** 2) +
                             ((lwHor / (2.8 * u["Data"])) ** 2))
    tao_ewT = numpy.ma.sqrt((tau_sonic_law_4scalar ** 2) + (tau_sonic_laT_4scalar ** 2))

    tao_ewIRGA = numpy.ma.sqrt((tau_sonic_law_4scalar ** 2) +
                               (tau_irga_la ** 2) +
                               (tau_irga_va ** 2) +
                               (tau_irga_bw ** 2) +
                               (tau_irga_lat ** 2) +
                               (tau_irga_lon ** 2))

    tao_b = c.Tb / 2.8
    # calculate coefficients
    bMom = pfp_utils.bp(fxMom, tao_b)
    bScalar = pfp_utils.bp(fxScalar, tao_b)
    pMom = pfp_utils.bp(fxMom, tao_eMom)
    pwT = pfp_utils.bp(fxScalar, tao_ewT)
    # calculate corrections for momentum and scalars
    rMom = pfp_utils.r(bMom, pMom, alpha)
    rwT = pfp_utils.r(bScalar, pwT, alpha)
    # determine approximately-true Massman fluxes
    uwm = uw["Data"] / rMom
    vwm = vw["Data"] / rMom
    wTm = wT["Data"] / rwT
    # *** Massman_1stpass ends here ***
    # *** Massman_2ndpass starts here ***
    # we have calculated the first pass corrected momentum and temperature covariances, now we use
    # these to calculate the final corrections
    #  first, get the 2nd pass corrected friction velocity and Monin-Obukhov length
    ustarm["Data"] = numpy.ma.sqrt(numpy.ma.sqrt(uwm ** 2 + vwm ** 2))
    Lm["Data"] = pfp_mf.molen(Ta["Data"], AH["Data"], ps["Data"], ustarm["Data"], wTm,
                              fluxtype='kinematic')
    zoLm = zmd / Lm["Data"]
    nxMom, nxScalar, alpha = pfp_utils.nxMom_nxScalar_alpha(zoLm)
    fxMom = nxMom * (u["Data"] / zmd)
    fxScalar = nxScalar * (u["Data"] / zmd)
    # calculate coefficients
    bMom = pfp_utils.bp(fxMom, tao_b)
    bScalar = pfp_utils.bp(fxScalar, tao_b)
    pMom = pfp_utils.bp(fxMom, tao_eMom)
    pwT = pfp_utils.bp(fxScalar, tao_ewT)
    pwIRGA = pfp_utils.bp(fxScalar, tao_ewIRGA)
    # calculate corrections for momentum and scalars
    rMom = pfp_utils.r(bMom, pMom, alpha)
    rwT = pfp_utils.r(bScalar, pwT, alpha)
    rwIRGA = pfp_utils.r(bScalar, pwIRGA, alpha)
    # determine true fluxes
    uwM = uw["Data"] / rMom
    vwM = vw["Data"] / rMom
    wTM = wT["Data"] / rwT
    wCM = wC["Data"] / rwIRGA
    wAM = wA["Data"] / rwIRGA
    ustarM = numpy.ma.sqrt(numpy.ma.sqrt(uwM ** 2 + vwM ** 2))
    LM = pfp_mf.molen(Ta["Data"], AH["Data"], ps["Data"], ustarM, wTM, fluxtype="kinematic")
    # write the 2nd pass Massman corrected covariances to the data structure
    attr = {"long_name": "Friction velocity", "units": "m/s", "statistic_type": "average"}
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(ustarM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": ustar_out, "Data": ustarM, "Flag": flag, "Attr": attr})

    attr = {"long_name": "Monin-Obukhov length", descr_level: "Massman frequency correction",
            "units": "m", "statistic_type": "average"}
    flag = numpy.where(numpy.ma.getmaskarray(LM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": L_out, "Data": LM, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(uw["Attr"])
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(uwM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": uw_out, "Data": uwM, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(vw["Attr"])
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(vwM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": vw_out, "Data": vwM, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(wT["Attr"])
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(wTM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": wT_out, "Data": wTM, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(wA["Attr"])
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(wAM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": wA_out, "Data": wAM, "Flag": flag, "Attr": attr})

    attr = copy.deepcopy(wC["Attr"])
    pfp_utils.append_to_attribute(attr, {descr_level: "Massman frequency correction"})
    flag = numpy.where(numpy.ma.getmaskarray(wCM) == True, ones, zeros)
    pfp_utils.CreateVariable(ds, {"Label": wC_out, "Data": wCM, "Flag": flag, "Attr": attr})
    # *** Massman_2ndpass ends here ***
    return

def MergeSeriesUsingDict(ds, info, merge_order="standard"):
    """ Merge series as defined in the merge dictionary."""
    # create decsription level attribute string
    descr_level = "description_" + ds.root["Attributes"]["processing_level"]
    merge = info["MergeSeries"]
    if merge_order not in merge:
        msg = "MergeSeriesUsingDict: merge order " + merge_order + " not found"
        logger.warning(msg)
        return
    # loop over the entries in merge
    for target in list(merge[merge_order].keys()):
        srclist = merge[merge_order][target]["source"]
        logger.info(" Merging "+str(srclist)+"==>"+target)
        if srclist[0] not in list(ds.root["Variables"].keys()):
            logger.error("  MergeSeries: primary input series "+srclist[0]+" not found")
            continue
        data = ds.root["Variables"][srclist[0]]["Data"].copy()
        flag1 = ds.root["Variables"][srclist[0]]["Flag"].copy()
        flag2 = ds.root["Variables"][srclist[0]]["Flag"].copy()
        attr = ds.root["Variables"][srclist[0]]["Attr"].copy()
        SeriesNameString = srclist[0]
        tmplist = list(srclist)
        tmplist.remove(tmplist[0])
        s2add = ""
        for label in tmplist:
            if label in list(ds.root["Variables"].keys()):
                SeriesNameString = SeriesNameString+", "+label
                # find the elements with flag = 0, 10, 20 etc
                index = numpy.where(numpy.mod(flag1, 10) == 0)[0]
                # set them all to 0
                flag2[index] = 0
                # index of flag values other than 0,10,20,30 ...
                index = numpy.where(flag2 != 0)[0]
                # replace bad primary with good secondary
                data[index] = ds.root["Variables"][label]["Data"][index].copy()
                flag1[index] = ds.root["Variables"][label]["Flag"][index].copy()
                s2add = pfp_utils.append_string(s2add, ds.root["Variables"][label]["Attr"][descr_level], caps=False)
            else:
                logger.error(" MergeSeries: secondary input series "+label+" not found")
        s2add = "gap filled using " + s2add
        pfp_utils.append_to_attribute(attr, {descr_level: s2add})
        var = {"Label": target, "Data": data, "Flag": flag1, "Attr": attr}
        pfp_utils.CreateVariable(ds, var)
    return

def MergeHumidities(cf, ds, convert_units=False):
    if "AH" not in cf["Variables"] and "RH" not in cf["Variables"] and "SH" not in cf["Variables"]:
        msg = " MergeHumidities: No humidities found in control file, returning ..."
        logger.warning(msg)
        return
    if "AH" in cf["Variables"]:
        if "MergeSeries" in cf["Variables"]["AH"]:
            MergeSeries(cf, ds, "AH", convert_units=convert_units)
            pfp_utils.CheckUnits(ds, "AH", "g/m^3", convert_units=True)
        elif "AverageSeries" in cf["Variables"]["AH"]:
            AverageSeriesByElements(cf, ds, "AH")
            pfp_utils.CheckUnits(ds, "AH", "g/m^3", convert_units=True)
    if "RH" in cf["Variables"]:
        if "MergeSeries" in cf["Variables"]["RH"]:
            MergeSeries(cf, ds, "RH", convert_units=convert_units)
            pfp_utils.CheckUnits(ds, "RH", "percent", convert_units=True)
        elif "AverageSeries" in cf["Variables"]["RH"]:
            AverageSeriesByElements(cf, ds, "RH")
            pfp_utils.CheckUnits(ds, "RH", "percent", convert_units=True)
    if "SH" in cf["Variables"]:
        if "MergeSeries" in cf["Variables"]["SH"]:
            MergeSeries(cf, ds, "SH", convert_units=convert_units)
            pfp_utils.CheckUnits(ds, "SH", "kg/kg", convert_units=True)
        elif "AverageSeries" in cf["Variables"]["SH"]:
            AverageSeriesByElements(cf, ds, "SH")
            pfp_utils.CheckUnits(ds, "SH", "kg/kg", convert_units=True)
    return

def MergeSeries(cf, ds, series, convert_units=False, save_originals=False):
    """
    Purpose:
     Merge two series of data to produce one series containing the best data from both.
     If the QC flag for Primary is in okflags, the value from Primary is placed in destination.
     If the QC flag for Primary is not in okflags but the QC flag for Secondary is, the value
     from Secondary is placed in Destination.
    Usage:
     pfp_ts.MergeSeries(cf,ds,series,okflags=okflags.convert_units=False,save_originals=False)
         where ds is the data structure containing all series
               series (str) is the label of the destination series
               okflags (list) is a list of QC flag values for which the data is considered acceptable
               convert_units (boolean) if True, we will attempt to match units if they are not the same
               save_originals (boolean) it True, original series will be saved before merge
    Author: PRI
    Date: Back in the day
    History:
     16/7/2017 - made okflags optional, implemented save_originals
     30/10/2018 - rewrote to use pfp_utils.GetVariable()
     12/06/2025 - replace okflags with mod(flag, 10)==0 to handle import flags (e.g 300, 400 etc)
    """
    # check to see if the series is specified in the control file
    section = pfp_utils.get_cfsection(cf, series)
    if section == None:
        return
    # check to see if the entry for series in the control file has the MergeSeries key
    if 'MergeSeries' not in list(cf[section][series].keys()):
        return
    # check to see if the series has already been merged
    if series in ds.info["mergeserieslist"]:
        return
    # get the name of the description variable attribute
    processing_level = ds.root["Attributes"]["processing_level"]
    descr_level = "description_" + processing_level
    # now get the source list and the standard name
    srclist = pfp_utils.GetMergeSeriesKeys(cf,series,section=section)
    nSeries = len(srclist)
    if nSeries==0:
        logger.warning(' MergeSeries: no input series specified for '+str(series))
        return
    if nSeries == 1:
        msg = ' Merging ' + str(srclist) + '==>' + series
        logger.info(msg)
        primary_series = srclist[0]
        if primary_series not in list(ds.root["Variables"].keys()):
            msg = "  MergeSeries: primary input series " + primary_series
            msg = msg + " not found for " + str(series)
            logger.warning(msg)
            return
        primary = pfp_utils.GetVariable(ds, primary_series)
        if (primary_series == series) and save_originals:
            tmp = pfp_utils.CopyVariable(primary)
            tmp["Label"] = tmp["Label"] + "_b4merge"
            pfp_utils.CreateVariable(ds, tmp)
        SeriesNameString = primary_series
    else:
        msg = " Merging " + str(srclist) + "==>" + series
        logger.info(msg)
        if srclist[0] not in list(ds.root["Variables"].keys()):
            msg = "  MergeSeries: primary input series " + srclist[0] + " not found for " + str(series)
            logger.warning(msg)
            return
        primary_series = srclist[0]
        if primary_series not in list(ds.root["Variables"].keys()):
            msg = "  MergeSeries: primary input series " + primary_series
            msg = msg + " not found for " + str(series)
            logger.warning(msg)
            return
        primary = pfp_utils.GetVariable(ds, primary_series)
        if (primary_series == series) and save_originals:
            tmp = pfp_utils.CopyVariable(primary)
            tmp["Label"] = tmp["Label"] + "_b4merge"
            pfp_utils.CreateVariable(ds, tmp)
        SeriesNameString = primary_series
        srclist.remove(primary_series)
        for secondary_series in srclist:
            if secondary_series in list(ds.root["Variables"].keys()):
                secondary = pfp_utils.GetVariable(ds, secondary_series)
                if (secondary_series == series) and save_originals:
                    tmp = pfp_utils.CopyVariable(secondary)
                    tmp["Label"] = tmp["Label"] + "_b4merge"
                    pfp_utils.CreateVariable(ds, tmp)
                if secondary["Attr"]["units"] != primary["Attr"]["units"]:
                    msg = " " + secondary_series + " units don't match " + primary_series + " units"
                    logger.warning(msg)
                    if convert_units:
                        msg = " " + secondary_series + " units converted from "
                        msg = msg + secondary["Attr"]["units"] + " to " + primary["Attr"]["units"]
                        logger.info(msg)
                        secondary = pfp_utils.convert_units_func(ds, secondary, primary["Attr"]["units"])
                    else:
                        msg = " MergeSeries: " + secondary_series + " ignored"
                        logger.error(msg)
                        continue
                # update the secondary series name string, written to variable attributes
                SeriesNameString = SeriesNameString + ", " + secondary_series
                # pointers to the primary and secondary QC flags
                pflag = primary["Flag"]
                sflag = secondary["Flag"]
                # index of elements where primary is bad and secondary is good
                index = numpy.where((numpy.mod(pflag, 10) != 0) &
                                    (numpy.mod(sflag, 10) == 0))[0]
                # replace bad primary with good secondary
                primary["Data"][index] = secondary["Data"][index]
                primary["Flag"][index] = secondary["Flag"][index]
            else:
                msg = "  MergeSeries: secondary input series " + secondary_series + " not found"
                logger.warning(msg)
    ds.info["mergeserieslist"].append(series)
    primary["Label"] = series
    pfp_utils.append_to_attribute(primary["Attr"], {descr_level: "merged from " + SeriesNameString})
    pfp_utils.CreateVariable(ds, primary)
    return

def ReplaceRotatedCovariance(cf,ds,rot_cov_label,non_cov_label):
    logger.info(' Replacing missing '+rot_cov_label+' when '+non_cov_label+' is good')
    cr = pfp_utils.GetVariable(ds, rot_cov_label)
    cn = pfp_utils.GetVariable(ds, non_cov_label)
    index = numpy.where((numpy.ma.getmaskarray(cr["Data"]) == True)&
                        (numpy.ma.getmaskarray(cn["Data"]) == False))[0]
    if len(index)!=0:
        ds.root["Variables"][rot_cov_label]["Data"][index] = cn["Data"][index]
        ds.root["Variables"][rot_cov_label]["Flag"][index] = numpy.int32(20)
    return

def RemoveIntermediateSeries(ds, info):
    """
    Purpose:
     Remove the alternate, solo, mds, climatology and composite variables
     from the L4 or L5 data structures.
    Usage:
    Side effects:
    Author: PRI
    Date: November 2018
    """
    iris = info["RemoveIntermediateSeries"]
    if iris["KeepIntermediateSeries"] == "Yes":
        return
    if "not_output" in iris:
        if len(iris["not_output"]) > 0:
            msg = " Removing intermediate series from data structure"
            logger.info(msg)
            for label in iris["not_output"]:
                if label in list(ds.root["Variables"].keys()):
                    del ds.root["Variables"][label]
            iris["not_output"] = []
    return

def ReplaceWhereMissing(Destination,Primary,Secondary,FlagOffset=None,FlagValue=None):
    p_data = Primary['Data'].copy()
    p_flag = Primary['Flag'].copy()
    s_data = Secondary['Data'].copy()
    s_flag = Secondary['Flag'].copy()
    if numpy.size(p_data)>numpy.size(s_data):
        p_data = p_data[0:numpy.size(s_data)]
    if numpy.size(s_data)>numpy.size(p_data):
        s_data = s_data[0:numpy.size(p_data)]
    index = numpy.where((abs(p_data-float(c.missing_value))<c.eps)&
                        (abs(s_data-float(c.missing_value))>c.eps))[0]
    p_data[index] = s_data[index]
    if FlagValue is None and FlagOffset is not None:
        p_flag[index] = s_flag[index] + numpy.int32(FlagOffset)
    elif FlagValue is not None and FlagOffset is None:
        p_flag[index] = numpy.int32(FlagValue)
    else:
        p_flag[index] = s_flag[index]
    Destination['Data'] = Primary['Data'].copy()
    Destination['Flag'] = Primary['Flag'].copy()
    Destination['Data'][0:len(p_data)] = p_data
    Destination['Flag'][0:len(p_flag)] = p_flag
    Destination['Attr']['long_name'] = 'Merged from original and alternate'
    Destination['Attr']['units'] = Primary['Attr']['units']

def ReplaceWhenDiffExceedsRange(DateTime,Destination,Primary,Secondary,RList):
    # get the primary data series
    p_data = numpy.ma.array(Primary['Data'], copy=True)
    p_flag = Primary['Flag'].copy()
    # get the secondary data series
    s_data = numpy.ma.array(Secondary['Data'], copy=True)
    # truncate the longest series if the sizes do not match
    if numpy.size(p_data)!=numpy.size(s_data):
        logger.warning(' ReplaceWhenDiffExceedsRange: Series lengths differ, longest will be truncated')
        if numpy.size(p_data)>numpy.size(s_data):
            p_data = p_data[0:numpy.size(s_data)]
        if numpy.size(s_data)>numpy.size(p_data):
            s_data = s_data[0:numpy.size(p_data)]
    # get the difference between the two data series
    d_data = p_data-s_data
    # normalise the difference if requested
    if RList[3]=='s':
        d_data = (p_data-s_data)/s_data
    elif RList[3]=='p':
        d_data = (p_data-s_data)/p_data
    #si = pfp_utils.GetDateIndex(DateTime,RList[0],0)
    #ei = pfp_utils.GetDateIndex(DateTime,RList[1],0)
    Range = RList[2]
    Upper = float(Range[0])
    Lower = float(Range[1])
    index = numpy.ma.where((abs(d_data)<Lower)|(abs(d_data)>Upper))
    p_data[index] = s_data[index]
    p_flag[index] = 35
    Destination['Data'] = numpy.ma.filled(p_data,float(c.missing_value))
    Destination['Flag'] = p_flag.copy()
    Destination['Attr']['long_name'] = 'Replaced original with alternate when difference exceeded threshold'
    Destination['Attr']['units'] = Primary['Attr']['units']

def savitzky_golay(y, window_size, order, deriv=0):
    ''' Apply Savitsky-Golay low-pass filter to data.'''
    try:
        window_size = numpy.abs(int(window_size))
        order = numpy.abs(int(order))
    except ValueError:
        raise ValueError("window_size and order have to be of type int")
    if window_size % 2 != 1 or window_size < 1:
        raise TypeError("window_size size must be a positive odd number")
    if window_size < order + 2:
        raise TypeError("window_size is too small for the polynomials order")
    order_range = list(range(order+1))
    half_window = (window_size -1) // 2
    # precompute coefficients
    b = numpy.mat([[k**i for i in order_range] for k in range(-half_window, half_window+1)])
    m = numpy.linalg.pinv(b).A[deriv]
    # pad the signal at the extremes with
    # values taken from the signal itself
    firstvals = y[0] - numpy.abs( y[1:half_window+1][::-1] - y[0] )
    lastvals = y[-1] + numpy.abs(y[-half_window-1:-1][::-1] - y[-1])
    y = numpy.concatenate((firstvals, y, lastvals))
    return numpy.convolve( m, y, mode='valid')

def Square(Series):
    tmp = numpy.array([c.missing_value]*numpy.size(Series),Series.dtype)
    index = numpy.where(Series!=float(c.missing_value))[0]
    tmp[index] = Series[index] ** 2
    return tmp

def SquareRoot(Series):
    tmp = numpy.array([c.missing_value]*numpy.size(Series),Series.dtype)
    index = numpy.where(Series!=float(c.missing_value))[0]
    tmp[index] = Series[index] ** .5
    return tmp

def TaFromTv(cf, ds, Ta_out="Ta_SONIC_Av", Tv_in="Tv_SONIC_Av", AH_in="AH",
             RH_in="RH", SH_in="SH", ps_in="ps"):
    # Calculate the air temperature from the virtual temperature, the
    # absolute humidity and the pressure.
    # NOTE: the virtual temperature is used in place of the air temperature
    #       to calculate the vapour pressure from the absolute humidity, the
    #       approximation involved here is of the order of 1%.
    labels = list(ds.root["Variables"].keys())
    if Ta_out in labels:
        msg = " TaFromTv: Ta_SONIC_Av already in data structure"
        logger.warning(msg)
        return
    logger.info(" Calculating Ta from Tv")
    nRecs = int(ds.root["Attributes"]["nc_nrecs"])
    ones = numpy.ones(nRecs)
    zeros = numpy.zeros(nRecs)
    SH = pfp_utils.CreateEmptyVariable("SH", nRecs)
    Ta = pfp_utils.CreateEmptyVariable(Ta_out, nRecs)
    # check to see if we have enough data to proceed
    # deal with possible aliases for the sonic temperature
    if Tv_in not in labels:
        msg = " TaFromTv: sonic virtual temperature not found in data structure"
        logger.error(msg)
        return
    if ((AH_in not in labels) and (RH_in not in labels) and (SH_in not in labels)):
        labstr = str(AH_in) + "," + str(RH_in) + "," + str(SH_in)
        msg = " TaFromTv: no humidity data (" + labstr + ") found in data structure"
        logger.error(msg)
        return
    if ps_in not in labels:
        msg = " TaFromTv: pressure (" + str(ps_in) + ") not found in data structure"
        logger.error(msg)
        return
    # we seem to have enough to continue
    descr_level = "description_" + str(ds.root["Attributes"]["processing_level"])
    Tv = pfp_utils.GetVariable(ds, Tv_in)
    ps = pfp_utils.GetVariable(ds, ps_in)
    if SH_in in list(ds.root["Variables"].keys()):
        SH = pfp_utils.GetVariable(ds, SH_in)
    elif AH_in in list(ds.root["Variables"].keys()):
        AH = pfp_utils.GetVariable(ds, AH_in)
        vp = pfp_mf.vapourpressure(AH["Data"], Tv["Data"])
        mr = pfp_mf.mixingratio(ps["Data"], vp)
        SH["Data"] = pfp_mf.specifichumidity(mr)
    elif RH_in in list(ds.root["Variables"].keys()):
        RH = pfp_utils.GetVariable(ds, RH_in)
        SH["Data"] = pfp_mf.specifichumidityfromRH(RH["Data"], Tv["Data"], ps["Data"])
    else:
        msg = " TaFromTv: no humidities found"
        logger.warning(msg)
    Ta["Data"] = pfp_mf.tafromtv(Tv["Data"], SH["Data"])
    Ta["Flag"] = numpy.where(numpy.ma.getmaskarray(Ta["Data"]) == True, ones, zeros)
    Ta["Attr"] = {"long_name": "Air temperature",
                  descr_level: "Ta calculated from Tv using " + Tv_in, "units": "degC",
                  "standard_name": "air_temperature", "statistic_type": "average"}
    pfp_utils.CreateVariable(ds, Ta)
    return
