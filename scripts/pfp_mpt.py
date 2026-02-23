# standard Python modules
import datetime
import logging
import os
import subprocess
import tempfile
# 3rd party
import numpy
import pandas
# PFP modules
from scripts import pfp_io
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

def get_seasonal_results(contents):
    # get the seasonal values
    season_values = numpy.array([float(s) for s in contents[2].split()])
    season_counts = numpy.array([int(s) for s in contents[3].split()])
    return {"value": season_values, "count": season_counts}

def get_annual_results(contents):
    # get the annual values
    season_values = numpy.array([float(s) for s in contents[2].split()])
    season_counts = numpy.array([int(s) for s in contents[3].split()])
    annual_values = numpy.max(season_values)
    annual_counts = numpy.sum(season_counts)
    return {"value": annual_values, "count": annual_counts}

def get_temperature_class_results(contents):
    # get the seasonal results by temperature class
    temperature_classes = {}
    for i, n in enumerate(range(7, 14)):
        temperature_classes[i] = {}
        temperature_classes[i]["values"] = numpy.array([float(s) for s in contents[n].split()])
        temperature_classes[i]["counts"] = numpy.zeros(len(temperature_classes[i]["values"]))
    return temperature_classes

def get_bootstrap_seasonal_results(contents):
    # get the number of seasons
    season_values = numpy.array([float(s) for s in contents[2].split()])
    number_seasons = len(season_values)
    # get the individual bootstrap results
    bootstrap_seasonal_results = {}
    for i in range(number_seasons):
        bootstrap_seasonal_results[i] = {"values": [], "counts": []}
    # on Windows machines, len(contents[n]) == 1 for the first empty line after the bootstrap section
    n = 17
    while len(contents[n]) > 1:
        season_values = numpy.array([float(s) for s in contents[n][0:contents[n].index("forward")].split()])
        season_counts = numpy.array([int(s) for s in contents[n+1][0:].split()])
        for i in range(number_seasons):
            if i < len(season_values):
                bsr = bootstrap_seasonal_results[i]
                bsr["values"] = numpy.append(bsr["values"], season_values[i])
                bsr["counts"] = numpy.append(bsr["counts"], season_counts[i])
            else:
                bsr["values"] = numpy.append(bsr["values"], float(-9999))
                bsr["counts"] = numpy.append(bsr["counts"], float(-9999))
        n = n + 2
    return bootstrap_seasonal_results

def get_bootstrap_annual_results(contents):
    # get the annual bootstrap results
    bootstrap_annual_results = {"values": []}
    # on Windows machines, len(contents[n]) == 1 for the first empty line after the bootstrap section
    n = 219
    while len(contents[n]) > 1:
        bootstrap_annual_results["values"].append(float(contents[n].strip()))
        n = n + 1
    return bootstrap_annual_results

def make_data_array(cf, ds, current_year):
    ldt = pfp_utils.GetVariable(ds, "DateTime")
    nrecs = int(ds.root["Attributes"]["nc_nrecs"])
    ts = int(float(ds.root["Attributes"]["time_step"]))
    start = datetime.datetime(current_year, 1, 1, 0, 0, 0) + datetime.timedelta(minutes=ts)
    end = datetime.datetime(current_year+1, 1, 1, 0, 0, 0)
    cdt = numpy.array([dt for dt in pfp_utils.perdelta(start, end, datetime.timedelta(minutes=ts))])
    mt = numpy.ones(len(cdt))*float(-9999)
    mt_list = [cdt] + [mt for n in list(cf["Variables"].keys())]
    data = numpy.stack(mt_list, axis=-1)
    si = pfp_utils.GetDateIndex(ldt["Data"], start, default=0)
    ei = pfp_utils.GetDateIndex(ldt["Data"], end, default=nrecs)
    dt = pfp_utils.GetVariable(ds, "DateTime", start=si, end=ei)
    idx1, idx2 = pfp_utils.FindMatchingIndices(cdt, dt["Data"])
    for n, cf_label in enumerate(list(cf["Variables"].keys())):
        label = cf["Variables"][cf_label]["name"]
        var = pfp_utils.GetVariable(ds, label, start=si, end=ei)
        data[idx1,n+1] = var["Data"]
    # convert datetime to ISO dates
    data[:,0] = numpy.array([int(xdt.strftime("%Y%m%d%H%M")) for xdt in cdt])
    return data

def mpt_main(cf):
    base_file_path = cf["Files"]["file_path"]
    nc_file_name = cf["Files"]["in_filename"]
    nc_file_path = os.path.join(base_file_path, nc_file_name)
    ds = pfp_io.NetCDFRead(nc_file_path)
    if ds.info["returncodes"]["value"] != 0: return
    # get a temporary directory for the log, input and output files
    tmp_dir = tempfile.TemporaryDirectory(prefix="pfp_mpt_")
    mpt = {"paths": {"tmp_base": tmp_dir.name}}
    for item in ["input", "output", "log"]:
        path = os.path.join(tmp_dir.name, item)
        os.makedirs(path)
        mpt["paths"][item] = path
    out_file_paths = run_mpt_code(cf, ds, mpt)
    if len(out_file_paths) == 0:
        return
    ustar_results = read_mpt_output(out_file_paths)
    mpt_file_path = nc_file_path.replace(".nc", "_MPT.xlsx")
    xl_write_mpt(mpt_file_path, ustar_results)
    return

def run_mpt_code(cf, ds, mpt):
    """
    Purpose:
     Runs the MPT u* threshold detection code for each year in the data set.
    Usage:
    Side effects:
     Writes an ASCII file of results which is read by later code.
    Author: Alessio Ribeca wrote the C code
            PRI wrote this wrapper
    Date: Back in the day
    """
    # get the executable suffix
    suffix = pfp_utils.get_executable_suffix()
    # set up file paths, headers and formats etc
    out_file_paths = {}
    header = "TIMESTAMP,NEE,VPD,USTAR,TA,SW_IN,H,LE"
    # check that all variables listed in the header are defined in the control file
    labels = cf["Variables"].keys()
    for label in labels:
        if label not in header:
            msg = " MPT: variable " + label + " not defined in control file, skipping MPT ..."
            logger.error(msg)
            return out_file_paths
        else:
            msg = " MPT: Using variable " + cf["Variables"][label]["name"] + " for " + label
            logger.info(msg)
    fmt = "%12i,%f,%f,%f,%f,%f,%f,%f"

    log_file_path = os.path.join(mpt["paths"]["log"], "mpt.log")
    mptlogfile = open(log_file_path, "w")
    in_base_path = os.path.join(mpt["paths"]["input"], "")
    out_base_path = os.path.join(mpt["paths"]["output"], "")
    # get the time step
    ts = int(float(ds.root["Attributes"]["time_step"]))
    if (ts != 30) and (ts != 60):
        msg = "MPT: time step must be 30 or 60 minutes (" + str(ts) + "), skipping MPT ..."
        logger.error(msg)
        return out_file_paths
    # get the datetime
    dt = pfp_utils.GetVariable(ds, "DateTime")
    # subtract 1 time step to avoid orphan years
    cdt = dt["Data"] - datetime.timedelta(minutes=ts)
    # get a list of the years in the data set
    years = sorted(list(set([ldt.year for ldt in cdt])))
    # loop over years
    for year in years:
        msg = " MPT: processing year " + str(year)
        logger.info(msg)
        #in_name = ds.info["filepath"].replace(".nc","_"+str(year)+"_MPT.csv")
        in_full_path = os.path.join(in_base_path, "mpt_"+str(year)+".csv")
        out_full_path = in_full_path.replace("input", "output").replace(".csv", "_ut.txt")
        data = make_data_array(cf, ds, year)
        numpy.savetxt(in_full_path, data, header=header, delimiter=",", comments="", fmt=fmt)
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        ustar_mp_exe = os.path.join(base_path, "mpt", "bin", "ustar_mp"+suffix)
        if ts == 30:
            cmd = [ustar_mp_exe, "-input_path="+in_full_path, "-output_path="+out_base_path]
        elif ts == 60:
            cmd = [ustar_mp_exe, "-input_path="+in_full_path, "-output_path="+out_base_path, "-hourly"]
        subprocess.call(cmd, stdout=mptlogfile)
        if os.path.isfile(out_full_path):
            out_file_paths[year] = out_full_path
    mptlogfile.close()
    return out_file_paths

def read_mpt_output(out_file_paths):
    ustar_results = {"Annual":{}, "Years":{}}
    ury = ustar_results["Years"]
    year_list = sorted(out_file_paths.keys())
    for year in year_list:
        ury[year] = {}
        out_file_path = out_file_paths[year]
        with open(out_file_path) as mpt_file:
            contents = [l.rstrip('\n') for l in mpt_file.readlines()]
        # check the first line to make sure it is what we expect
        if not "ustar threshold by season" in contents[0] or not "bootstrapping" in contents[15]:
            msg = "MPT: unexpected contents in MPT output file"
            logger.error(msg)
            return ustar_results
        ury[year]["seasonal"] = get_seasonal_results(contents)
        ury[year]["annual"] = get_annual_results(contents)
        ury[year]["temperature_classes"] = get_temperature_class_results(contents)
        ury[year]["bootstraps_seasonal"] = get_bootstrap_seasonal_results(contents)
        ury[year]["bootstraps_annual"] = get_bootstrap_annual_results(contents)
    return ustar_results

def xl_write_mpt(mpt_full_path, ustar_results):
    """
    Purpose:
    Usage:
    Side effects:
    Author: PRI
    Date: November 2019
    Mods:
     September 2021 - rewritten to use pandas
    """
    annual = {}
    years = sorted(list(ustar_results["Years"].keys()))
    for year in years:
        season_list = sorted(list(ustar_results["Years"][year]["bootstraps_seasonal"].keys()))
        values = ustar_results["Years"][year]["bootstraps_seasonal"][0]["values"]
        season_list.remove(0)
        for s in season_list:
            values = numpy.concatenate((values, ustar_results["Years"][year]["bootstraps_seasonal"][s]["values"]))
        values = numpy.ma.masked_values(values, -9999)
        ustar_results["Years"][year]["annual"]["stdev"] = numpy.ma.std(values)
        annual[year] = {"ustar_mean": ustar_results["Years"][year]["annual"]["value"],
                        "ustar_sig": ustar_results["Years"][year]["annual"]["stdev"]}
    xlwriter = pandas.ExcelWriter(mpt_full_path)
    df_annual = pandas.DataFrame.from_dict(annual, orient='index')
    df_annual.index.names = ["Year"]
    df_annual.to_excel(excel_writer= xlwriter, sheet_name='Annual')
    by_years = {}
    for year in years:
        by_years["Seasonal"] = {"Values": ustar_results["Years"][year]["seasonal"]["value"],
                                "Counts": ustar_results["Years"][year]["seasonal"]["count"]}
        by_years["Temperature classes"] = {}
        temperature_classes = sorted(list(ustar_results["Years"][year]["temperature_classes"].keys()))
        for t in temperature_classes:
            d = {}
            for i in range(len(ustar_results["Years"][year]["temperature_classes"][t]["values"])):
                d[i] = ustar_results["Years"][year]["temperature_classes"][t]["values"][i]
            by_years["Temperature classes"][t] = d
        d = {}
        for i in range(len(ustar_results["Years"][year]["bootstraps_seasonal"])):
            d[str(i)+" Values"] = ustar_results["Years"][year]["bootstraps_seasonal"][i]["values"]
            d[str(i)+" Counts"] = ustar_results["Years"][year]["bootstraps_seasonal"][i]["counts"]
        by_years["Bootstraps_seasonal"] = d
        d = {}
        for i in range(len(ustar_results["Years"][year]["bootstraps_annual"])):
            d["Values"] = ustar_results["Years"][year]["bootstraps_annual"]["values"]
        by_years["Bootstraps_annual"] = d
        df_bootstraps = pandas.DataFrame.from_dict(by_years["Bootstraps_annual"])
        df_bootstraps.index.names = ["Bootstraps annual"]
        df_bootstraps.to_excel(xlwriter, sheet_name=str(year), startrow=0, startcol=0)
        df_seasonal = pandas.DataFrame.from_dict(by_years["Seasonal"])
        df_seasonal.index.names = ["Seasonal"]
        df_seasonal.to_excel(xlwriter, sheet_name=str(year), startrow=0, startcol=3)
        df_temperature = pandas.DataFrame.from_dict(by_years["Temperature classes"], orient='index')
        df_temperature.index.names = ["Temperature classes"]
        df_temperature.to_excel(xlwriter, sheet_name=str(year), startrow=10, startcol=3)
        df_bootstraps = pandas.DataFrame.from_dict(by_years["Bootstraps_seasonal"])
        df_bootstraps.index.names = ["Bootstraps seasonal"]
        df_bootstraps.to_excel(xlwriter, sheet_name=str(year), startrow=20, startcol=3)
    xlwriter.close()
    return
