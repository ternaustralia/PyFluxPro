# standard modules
import datetime
import logging
import os
import zipfile
# 3rd party modules
import matplotlib.pyplot as plt
from matplotlib.path import Path
import numpy
import pandas
# from scipy.misc.pilutil import imread
# PFP modules
import constants as c
import footprint_io
import footprint_utils
import meteorologicalfunctions as mf
import footprint_utils
import matplotlib.pyplot as plt
import numpy
import pandas
import csv
import xlrd
import datetime
import dateutil
from scipy import signal as sg
import ast
from netCDF4 import Dataset as NetCDFFile
import os
import sys
import numbers
import constants as c
# Kljun, N., Calanca, P., Rotach, M. W., and Schmid, H. P., 2015:
# A simple two-dimensional parameterisation for Flux Footprint Prediction (FFP),
# Geosci. Model Dev., 8, 3695-3713.
import footprint_FFP_climatology as calcfootNK
# The following script cacl_footprint_FKM_climatology is based on the Neftel et al. (2008) ART_footprint tool:
# https://zenodo.org/record/816236#.W2eqUXBx3VM (http://doi.org/10.5281/zenodo.816236), which
# Kormann, R. and Meixner, F.X., 2001: An analytical footprint model for non-neutral stratification.
# Boundary-Layer Meteorology 99: 207. https://doi.org/10.1023/A:1018991015119 and Neftel, A., Spirig, C.,
# Ammann, C., 2008: Application and test of a simple tool for operational footprint evaluations. Environmental
# Pollution 152, 644-652.
import footprint_FKM_climatology as calcfootKM

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

# constant for converting degrees to radiant
c_d2r = numpy.pi / 180.0
# constant to convert the footprint area from x,y in lon,lat coordinates at the tower site
onedegree = 6378100.0 * c_d2r  # distance in m for 1 deg of latitude


def footprint_main(cf, mode):
    """
    Coordinate steps in footprint process => footprint_main:
    This script reads data from a PyFluxPro .nc file and processes the data for:
    (1) Kormann&Meixner uses input (single time)        zm,z0,ustar,umean,L,sigmav,wind_dir
    (2) Kljun et al. uses input (vectors for all times) zm,z0,ustar,umean,L,sigmav,wind_dir,Habl
        so Natascha's FFP also needs the height of the boundary layer ===> currently ERAI data got Habl,
        and ACCESS got Habl00 ... Habl22
    === > input for Kormann & Meixner and Natascha Kljun's footprint climatology
    (a) PyFluxPro L3 netcdf file
        ACCESS netcdf file
        AWS text file
    (b) ERA5/ACCESS netcdf file for Habl
    === > output for the climatology
    (a) daily footprint climatology
    (b) monthly footprint climatology
    (c) annual footprint climatology
    (d) special time set in controlfile for footprint climatology
    (e) hourly timestep
    GOAL: Footprint climatology can be done on a set time in controlfile
          calculating Kljun et al., 2015 and Kormann and Meixner, 2001 footprint
    DONE: set time in controlfile, special, daily, monthly and annual, every timestep
          Kljun et al. (2015) footprint
          Kormann and Meixner (2001) footprint
          save footprint fields in netcdf file
    Still to do: calculate Habl if not exist, better is set Habl (latter is done)
    C.M.Ewenz, 10 Jun 2018
               21 Jun 2018 (corrections to monthly indexing)
               29 Jun 2018 (kml file, single time stamp)
    P.R.Isaac,    Jul 2018 (re-wrote fp_data_in to get_footprint_data_in; configuration in get_footprint_cfg; time slicing; etc)
    C.M.Ewenz, 30 Jul 2018 (cleaned up printing of info, warning and error messages - include messages in logger)
    C.M.Ewenz, 22 Jan 2019 (included "Hourly" for plotting every timestep)
    C.M.Ewenz, 08 Feb 2019 (estimate cumulative footprint field)
    C.M.EWenz, 21 Feb 2019 (calculate proportion of footprint field in area of interest)
    C.M.Ewenz, 15 Dec 2023 (total re-write of controlfile and read in structure, using fpinfo dictionary)
    """
    # footprint information dictionary => fpinfo{}
    fpinfo = {}
    logger.info(' Read input data files from ...')
    if mode in ("kljun_L3", "kormei_L3"):
        ds = get_footprint_L3_data_in(cf, fpinfo, mode)
        logger.info(' ... Level 3 PyFluxPro processed netcdf data file')
    elif mode in ("kljun_AWS", "kormei_AWS"):
        ds = get_footprint_AWS_data_in(cf, fpinfo, mode)
        logger.info(' ... AWS csv text data file')
    elif mode in ("kljun_ACCESS", "kormei_ACCESS"):
        ds = get_footprint_ACCESS_data_in(cf, fpinfo, mode)
        logger.info(' ... ACCESS netcdf data file')
    ldt = ds.series["DateTime"]["Data"]

    logger.info(' Starting footprint calculation ...')
    # Create list for start and end times for footprint calculations
    list_StDate, list_EnDate = footprint_utils.create_index_list(cf, fpinfo, ldt)

    logger.info(' Starting footprint climatology calculation ...')
    # !!! Prepare Output netcdf file !!!
    # Set initial x,y Variables for output
    xout = numpy.linspace(fpinfo["xmin"], fpinfo["xmax"], fpinfo["nx"] + 1)
    yout = numpy.linspace(fpinfo["ymin"], fpinfo["ymax"], fpinfo["nx"] + 1)
    lat0 = float(fpinfo["latitude"])
    lon0 = float(fpinfo["longitude"])
    lat = lat0 + (yout / onedegree)
    lon = lon0 + (xout / (numpy.cos(lat0 * c_d2r) * onedegree))
    lon_2d, lat_2d = numpy.meshgrid(lon, lat)
    # - Initialise output netcdf file and write x,y grid into file as xDistance and yDistance from the tower
    nc_name = fpinfo["out_filename"]  # ["file_out"]
    # print 'nc_name = ',nc_name
    nc_file = footprint_io.nc_open_write(nc_name)
    # create the x and y dimensions.
    nc_file.createDimension('longitude', len(lon))
    nc_file.createDimension('latitude', len(lat))
    # create time dimension (record, or unlimited dimension)
    nc_file.createDimension('time', None)
    # create number of footprints in climatology dimension (record, or unlimited dimension)
    nc_file.createDimension('dtime', None)
    nc_file.createDimension('num', None)
    # Define coordinate variables, which will hold the coordinate information, x and y distance from the tower location.
    X = nc_file.createVariable('longitude', "d", ('longitude',))
    Y = nc_file.createVariable('latitude', "d", ('latitude',))
    # Define time variable and number of footprints variable at each time
    tx = nc_file.createVariable('dtime', "d", ('dtime',))
    num = nc_file.createVariable('num', "d", ('num',))
    # Assign units attributes to coordinate var data, attaches text attribute to coordinate variables, containing units.
    X.units = 'degree'
    Y.units = 'degree'
    # write data to coordinate vars.
    X[:] = lon
    Y[:] = lat
    # create the sumphi variable
    phi = nc_file.createVariable('sumphi', "d", ('time', 'longitude', 'latitude'))
    # set the units attribute.
    phi.units = ' '
    # === General inputs for FFP
    zmt = fpinfo["zm_d"]
    domaint = [fpinfo["xmin"], fpinfo["xmax"], fpinfo["ymin"], fpinfo["ymax"]]
    nxt = fpinfo["nx"]
    rst = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]  # [90.] #None #[20.,40.,60.,80.]
    # if plotting to screen      is requested then iplot = 1
    # if plotting to googleEarth is requested then iplot = 2
    iplot = int(cf['General']['iplot'])
    # IF export images in kml format?
    if iplot == 2:  # write kml - format header
        if "out_filename" in cf['Files']:
            # file_out = os.path.join(cf['Files']['file_path'],cf['Files']['out_filename'])
            kmlname = cf['Files']['out_filename'].replace(".nc", ".kml")
        else:
            kmlname = fpinfo["site_name"] + ".kml"
        kml_name_path = fpinfo["plot_path"] + kmlname
        fi = open(kml_name_path, 'w')
        kml_initialise(fpinfo, fi, mode)

    if fpinfo['AreaOfInterest']:
        paoi = open(fpinfo["plot_path"] + 'aoi_result.txt', 'w')
        paoi.write("Start time, Field number, Percent of total\n")

    # After deciding which climatology is done, let's do it!
    irun = -1
    for i in range(0, len(list_StDate)):
        irun = irun + 1
        # get the start and end indices
        si = list_StDate[i]
        ei = list_EnDate[i]
        # get the series as masked arrays
        timet, _, _ = footprint_utils.GetSeriesasMA(ds, "DateTime", si=si, ei=ei)
        umeant, _, _ = footprint_utils.GetSeriesasMA(ds, "Ws", si=si, ei=ei)
        olt, _, _ = footprint_utils.GetSeriesasMA(ds, "L", si=si, ei=ei)
        sigmavt, _, _ = footprint_utils.GetSeriesasMA(ds, "VSd", si=si, ei=ei)
        ustart, _, _ = footprint_utils.GetSeriesasMA(ds, "ustar", si=si, ei=ei)
        wind_dirt, _, _ = footprint_utils.GetSeriesasMA(ds, "Wd", si=si, ei=ei)
        z0t, _, _ = footprint_utils.GetSeriesasMA(ds, "z0", si=si, ei=ei)
        ht, _, _ = footprint_utils.GetSeriesasMA(ds, "Habl", si=si, ei=ei)
        # get a composite mask over all variables
        mask_all = numpy.ma.getmaskarray(ustart)
        for item in [umeant, olt, sigmavt, wind_dirt, z0t, ht]:
            mask_item = numpy.ma.getmaskarray(item)
            mask_all = numpy.ma.mask_or(mask_all, mask_item)

        # and then apply the composite mask to all variables and remove masked elements
        timet = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, timet)))
        umeant = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, umeant)))
        olt = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, olt)))
        sigmavt = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, sigmavt)))
        ustart = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, ustart)))
        wind_dirt = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, wind_dirt)))
        z0t = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, z0t)))
        ht = list(numpy.ma.compressed(numpy.ma.masked_where(mask_all == True, ht)))

        if len(umeant) == 0:
            msg = "No footprint input data for " + str(ldt[si]) + " to " + str(ldt[ei])
            logger.warning(msg)
            num[irun] = 0
        else:
            if mode in ("kljun_L3", "kljun_AWS", "kljun_ACCESS"):
                FFP = calcfootNK.FFP_climatology(fpinfo, time=timet, zm=zmt, z0=z0t, umean=umeant, h=ht, ol=olt,
                                                 sigmav=sigmavt, ustar=ustart, \
                                                 wind_dir=wind_dirt, domain=domaint, dx=None, dy=None, nx=nxt, ny=None, \
                                                 rs=rst, rslayer=1, smooth_data=1, crop=False, pulse=None, verbosity=2)
                x = FFP['x_2d']
                y = FFP['y_2d']
                f = FFP['fclim_2d']
                num[irun] = FFP['n']
                # tx[irun] = str(ldt[ei])
                phi[irun, :, :] = f
                fmax = numpy.amax(f)
                # if fmax < 1.0: #c.small_value:
                #    continue
                # else:
                fm = f / fmax
            elif mode in ("kormei_L3", "kormei_AWS", "kormei_ACCESS"):
                FKM = calcfootKM.FKM_climatology(fpinfo, time=timet, zm=zmt, z0=z0t, umean=umeant, ol=olt,
                                                 sigmav=sigmavt, ustar=ustart, \
                                                 wind_dir=wind_dirt, domain=domaint, dx=None, dy=None, nx=nxt, ny=None, \
                                                 rs=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], rslayer=0, \
                                                 smooth_data=1, crop=False, pulse=None, verbosity=2)
                x = FKM['x_2d']
                y = FKM['y_2d']
                f = FKM['fclim_2d']
                num[irun] = FKM['n']
                # tx[irun] = str(ldt[ei])
                phi[irun, :, :] = f
                fmax = numpy.amax(f)
                # if fmax < 1.0: #c.small_value:
                #    continue
                # else:
                fm = f / fmax

                # fm=f/fmax
            else:
                msg = " Unrecognised footprint type " + str(mode)
                logger.error(msg)
                return

            if fpinfo['Cumulative']:
                # ===
                msg = "Caclulated cumulative footprint field"
                logger.info(msg)
                f_min = 0.05
                f_step = 0.05
                f = calc_cumulative(fm, f_min, f_step)
            else:
                f = fm

            if fpinfo['AreaOfInterest']:
                # ===
                msg = "Contribution from area of interest"
                logger.info(msg)
                area = PolygonContribution(cf, x, y, fm, ldt[si], ldt[ei], paoi)

        # ====================================================================================================
        # get the default plot width and height
        # clevs = [0.01,0.05,0.1,0.2,0.3,0.4,0.5,0.6,0.7,0.8,0.9,1]
        clevs = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]
        # clevs = [0.1,0.8]
        imagename = footprint_utils.get_keyvaluefromcf(cf, ["General"], 'OzFlux_area_image')
        if not num[irun] == 0:
            if iplot == 1:
                # plot on screen and in jpg
                plotphifield(x, y, ldt[si], ldt[ei], f, fpinfo["site_name"], mode, clevs, imagename,
                             fpinfo['Cumulative'])
            elif iplot == 2:
                # plot on screen, in jpg and write kml (google earth) file
                kml_write(lon, lat, ldt[si], ldt[ei], f, fpinfo["site_name"], mode, clevs, fi, fpinfo["plot_path"],
                          fpinfo['Cumulative'])
            plot_num = plt.gcf().number
            if plot_num > 20:
                plt.close("all")
        # ====================================================================================================
        # Some stats:
        #  a) Possible total number of footprints per climatology = ei - si
        tot_fp = ei - si
        #  b) Remove each time step with "no value", number of times footprint is run = len(umeant)
        tot_fp_nv = len(umeant)
        #  c) Fianl number of valid footprints, removed all time steps where conditions not valid
        tot_valid = num[irun]
        msg = 'Total = ' + str(tot_fp) + ' Used = ' + str(tot_fp_nv) + ' Valid = ' + str(tot_valid) + ' footprints!'
        logger.info(msg)

        # progress = float(i+1)/float(len(list_StDate))
        # footprint_utils.update_progress(progress)
    if iplot == 2:
        # Finish kml file and process a compressed kmz file including all images
        kml_finalise(fpinfo, fi, mode, kmlname)
    if fpinfo['AreaOfInterest']:
        paoi.close()

        # ================================================================
    msg = " Finished " + str(mode) + " footprint writing"
    logger.info(msg)
    msg = " Closing netcdf file " + str(nc_name)
    logger.info(msg)
    nc_file.close()
    # ================================================================


def get_footprint_ACCESS_data_in(cf, fpinfo, mode):
    import footprint_utils
    # read input data and prepare for input into Kormann and Meixner, 2001 or Kljun et al., 2015
    # ---------------------- Get input / output file name ------------------------------------
    # Set input file and output path and create directories for plots and results
    # =======
    # [Files]
    # =======

    fpinfo["in_filename"] = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'])
    fpinfo["results_file"] = os.path.join(cf['Files']['plot_path'], cf['Files']['results_file'])

    # read the netcdf file
    msg = ' Reading ACCESS netCDF file ' + str(fpinfo["in_filename"])
    logger.info(msg)
    ds = footprint_io.nc_read_series(fpinfo["in_filename"])
    nrecs = int(ds.globalattributes["nc_nrecs"])

    # === Which climatology, either definded time, daily, monthly or annual
    fpinfo["Climatology"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Climatology", default="Special")

    # get the output file name from controlfile or set up automatically
    if "out_filename" in cf["Files"]:
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["out_filename"])
    else:
        climfreq = fpinfo["Climatology"]
        if climfreq == 'Annual':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_y_fp.nc"))
        elif climfreq == 'Monthly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_m_fp.nc"))
        elif climfreq == 'Daily':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_d_fp.nc"))
        elif climfreq == 'Hourly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_h_fp.nc"))
        elif climfreq == 'Single':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_si_fp.nc"))
        elif climfreq == 'Special':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_sp_fp.nc"))
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], file_out)

    # plot path
    fpinfo["plot_path"] = footprint_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    if not os.path.exists(fpinfo["plot_path"]):
        os.makedirs(fpinfo["plot_path"])

    # =========
    # [Options]
    # =========

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "footprint_size", default="1000")
    fpinfo["footprint_size"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "num_cells", default="250")
    fpinfo["num_cells"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "tower_height", default="20")
    fpinfo["tower_height"] = float(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "canopy_height", default="5")
    fpinfo["canopy_height"] = float(opt)

    fpinfo["zm"] = fpinfo["tower_height"] - fpinfo["canopy_height"]
    if ((fpinfo["zm"] < 0.0) or (fpinfo["zm"] > 1000.0)):
        msg = "zm is invalid"
        logger.error(msg)

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default="10")
    fpinfo["Fsd_threshold"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "Cumulative", default=False)
    fpinfo["Cumulative"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "AreaOfInterest", default=False)
    fpinfo["AreaOfInterest"] = int(opt)

    fpinfo["site_name"] = ds.globalattributes["site_name"]
    fpinfo["flux_period"] = int(ds.globalattributes["time_step"])

    fpinfo["zm_d"] = fpinfo["tower_height"] - (2.0 / 3.0 * fpinfo["canopy_height"])
    fpinfo["xTower"] = 0  # int(cf['Tower']['xTower'])
    fpinfo["yTower"] = 0  # int(cf['Tower']['yTower'])
    fpinfo["xmin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["xmax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["ymin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["ymax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["nx"] = int(cf["Options"]["num_cells"])

    fpinfo["call_mode"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive",
                                                             mode="quiet")
    fpinfo["show_plots"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "show_plots", default=True, mode="quiet")

    if "Latitude" in cf["Options"]:
        fpinfo["latitude"] = cf["Options"]["Latitude"]
    else:
        fpinfo["latitude"] = ds.globalattributes["latitude"]
    if "Longitude" in cf["Options"]:
        fpinfo["longitude"] = cf["Options"]["Longitude"]
    else:
        fpinfo["longitude"] = ds.globalattributes["longitude"]

    # array of 0s for QC flag
    f0 = numpy.zeros(nrecs, dtype=numpy.int32)
    # array of 1s for QC flag
    f1 = numpy.ones(nrecs, dtype=numpy.int32)

    # get the variable names
    fpinfo["Fsd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fsd"], "name", default="Fsd")
    fpinfo["Wd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Wd"], "name", default="Wd")
    fpinfo["Ws"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ws"], "name", default="Ws")
    fpinfo["Ta"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ta"], "name", default="Ta")
    fpinfo["AH"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "AH"], "name", default="AH")
    fpinfo["ps"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ps"], "name", default="ps")
    fpinfo["Fh"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fh"], "name", default="Fh")
    fpinfo["Habl"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Habl"], "name", default="Habl")

    # fpinfo["ustar"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ustar"], "name", default="ustar")
    # fpinfo["L"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "L"], "name", default="L")
    # fpinfo["z0"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "z0"], "name", default="z0")
    # fpinfo["VSd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "VSd"], "name", default="V_SONIC_Sd")

    Fsd = footprint_utils.GetVariable(ds, fpinfo["Fsd"])
    Fsd["Label"] = "Fsd"
    footprint_utils.CreateVariable(ds, Fsd)
    Ws = footprint_utils.GetVariable(ds, fpinfo["Ws"])
    Ws["Label"] = "Ws"
    footprint_utils.CreateVariable(ds, Ws)
    Wd = footprint_utils.GetVariable(ds, fpinfo["Wd"])
    Wd["Label"] = "Wd"
    footprint_utils.CreateVariable(ds, Wd)
    Ta = footprint_utils.GetVariable(ds, fpinfo["Ta"])
    Ta["Label"] = "Ta"
    footprint_utils.CreateVariable(ds, Ta)
    AH = footprint_utils.GetVariable(ds, fpinfo["AH"])
    AH["Label"] = "AH"
    footprint_utils.CreateVariable(ds, AH)
    ps = footprint_utils.GetVariable(ds, fpinfo["ps"])
    ps["Label"] = "ps"
    footprint_utils.CreateVariable(ds, ps)
    Fh = footprint_utils.GetVariable(ds, fpinfo["Fh"])
    Fh["Label"] = "Fh"
    footprint_utils.CreateVariable(ds, Fh)

    # read the ACCESS data for Habl if mode = kljun
    Habl = footprint_utils.GetVariable(ds, fpinfo["Habl"])
    Habl["Label"] = "Habl"
    footprint_utils.CreateVariable(ds, Habl)

    # cross wind standard deviation
    VSd = footprint_utils.create_empty_variable("VSd", nrecs)
    VSd["Data"] = 0.3 * Ws["Data"]
    VSd["Flag"] = numpy.where(numpy.ma.getmaskarray(VSd["Data"]) == True, f1, f0)
    VSd["Attr"]["long_name"] = "Standard deviation of cross-wind velocity component, estimated from Ws"
    VSd["Attr"]["units"] = "m/s"
    footprint_utils.CreateVariable(ds, VSd)

    # friction velocity
    ustar = footprint_utils.create_empty_variable("ustar", nrecs)
    ustar["Data"] = 0.3 * Ws["Data"]
    ustar["Flag"] = numpy.where(numpy.ma.getmaskarray(ustar["Data"]) == True, f1, f0)
    ustar["Attr"]["long_name"] = "friction velocity, estimated from Ws"
    ustar["Attr"]["units"] = "m/s"
    footprint_utils.CreateVariable(ds, ustar)

    # calculate Monin-Obukhov length
    footprint_utils.CalculateMoninObukhovLength(ds, fpinfo)
    msg = "Calculate Monin-Obukhov length"
    logger.info(msg)

    # === roughness length
    msg = "Get roughness length from "
    logger.info(msg)
    z0 = footprint_utils.create_empty_variable("z0", nrecs)
    if "roughness_length" in list(ds.globalattributes.keys()):
        roughness_length = float(ds.globalattributes["roughness_length"])
        z0["Data"] = numpy.ma.array(numpy.full(nrecs, roughness_length))
        z0["Attr"]["long_name"] = "Roughness length from global attributes"
        msg = "   ... from global attribute value"
        logger.info(msg)
    elif "roughness_length" in cf["Options"]:
        roughness_length = float(cf["Options"]["roughness_length"])
        z0["Data"] = numpy.ma.array(numpy.full(nrecs, roughness_length))
        z0["Attr"]["long_name"] = "Roughness length from footprint control file"
        msg = "   ... from footprint controlfile"
        logger.info(msg)
    else:
        zT = float(cf["Options"]["tower_height"])
        zC = float(cf["Options"]["canopy_height"])
        zm = zT - (2.0 / 3.0) * zC
        L = footprint_utils.GetVariable(ds, "L")
        ustar = footprint_utils.GetVariable(ds, "ustar")
        Ws = footprint_utils.GetVariable(ds, "Ws")
        z0["Data"] = footprint_utils.z0calc(zm, L["Data"], Ws["Data"], ustar["Data"])
        z0["Attr"]["long_name"] = "Roughness length calculated from u*, L, Ws and (z-d)"
        msg = "   ... from calculation"
        logger.info(msg)
    z0["Flag"] = numpy.where(numpy.ma.getmaskarray(z0["Data"]) == True, f1, f0)
    z0["Attr"]["units"] = "m"
    footprint_utils.CreateVariable(ds, z0)

    return ds


def get_footprint_AWS_data_in(cf, fpinfo, mode):
    import footprint_utils
    # -------------------------------------------------------------------------------------------
    # read input data and prepare for input into Kormann and Meixner, 2001 or Kljun et al., 2015
    # ---------------------- Get input / output file names --------------------------------------

    # =======
    # [Files]
    # =======

    fpinfo["in_filename"] = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'])
    fpinfo["results_file"] = os.path.join(cf['Files']['plot_path'], cf['Files']['results_file'])
    fpinfo["AWSdata"] = cf['Files']['AWSdata']
    # Create data structure
    ds = footprint_io.DataStructure()
    # read csv file AWS data
    msg = ' Reading AWS csv file ' + str(fpinfo["AWSdata"])
    logger.info(msg)
    df = pandas.read_csv(fpinfo["AWSdata"])
    # determine length of data file, number of records
    nrecs, cols = df.shape
    fpinfo["nrecs"] = nrecs
    ds.globalattributes["nc_nrecs"] = fpinfo["nrecs"]
    ds.globalattributes["time_step"] = cf["Options"]["time_step"]

    # === Which climatology, either definded time, daily, monthly or annual
    fpinfo["Climatology"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Climatology", default="Special")

    # get the output file name from controlfile or set up automatically
    if "out_filename" in cf["Files"]:
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["out_filename"])
    else:
        climfreq = fpinfo["Climatology"]
        if climfreq == 'Annual':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_y_fp.nc"))
        elif climfreq == 'Monthly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_m_fp.nc"))
        elif climfreq == 'Daily':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_d_fp.nc"))
        elif climfreq == 'Hourly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_h_fp.nc"))
        elif climfreq == 'Single':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_si_fp.nc"))
        elif climfreq == 'Special':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_sp_fp.nc"))
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], file_out)

    # plot path
    fpinfo["plot_path"] = footprint_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    if not os.path.exists(fpinfo["plot_path"]):
        os.makedirs(fpinfo["plot_path"])

    # =========
    # [Options]
    # =========

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "footprint_size", default="1000")
    fpinfo["footprint_size"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "num_cells", default="250")
    fpinfo["num_cells"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "tower_height", default="20")
    fpinfo["tower_height"] = float(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "canopy_height", default="5")
    fpinfo["canopy_height"] = float(opt)

    fpinfo["zm"] = fpinfo["tower_height"] - fpinfo["canopy_height"]
    if ((fpinfo["zm"] < 0.0) or (fpinfo["zm"] > 1000.0)):
        msg = "zm is invalid"
        logger.error(msg)

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default="10")
    fpinfo["Fsd_threshold"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "Cumulative", default=False)
    fpinfo["Cumulative"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "AreaOfInterest", default=False)
    fpinfo["AreaOfInterest"] = int(opt)

    fpinfo["site_name"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Site_name", default="test")
    fpinfo["flux_period"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "time_step", default=30)

    fpinfo["zm_d"] = fpinfo["tower_height"] - (2.0 / 3.0 * fpinfo["canopy_height"])
    fpinfo["xTower"] = 0  # int(cf['Tower']['xTower'])
    fpinfo["yTower"] = 0  # int(cf['Tower']['yTower'])
    fpinfo["xmin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["xmax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["ymin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["ymax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["nx"] = int(cf["Options"]["num_cells"])

    fpinfo["call_mode"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive",
                                                             mode="quiet")
    fpinfo["show_plots"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "show_plots", default=True, mode="quiet")

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "MOL", default="1000")
    fpinfo["MOL"] = int(opt)

    if "Latitude" in cf["Options"]:
        fpinfo["latitude"] = cf["Options"]["Latitude"]
    else:
        fpinfo["latitude"] = ds.globalattributes["latitude"]
    if "Longitude" in cf["Options"]:
        fpinfo["longitude"] = cf["Options"]["Longitude"]
    else:
        fpinfo["longitude"] = ds.globalattributes["longitude"]

    # array of 0s for QC flag
    f0 = numpy.zeros(nrecs, dtype=numpy.int32)
    # array of 1s for QC flag
    f1 = numpy.ones(nrecs, dtype=numpy.int32)

    # get the variable names
    fpinfo["Fsd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fsd"], "name", default="Fsd")
    fpinfo["Wd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Wd"], "name", default="Wd")
    fpinfo["Ws"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ws"], "name", default="Ws")
    fpinfo["Ta"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ta"], "name", default="Ta")
    fpinfo["AH"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "AH"], "name", default="AH")
    fpinfo["ps"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ps"], "name", default="ps")
    fpinfo["Fh"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fh"], "name", default="Fh")

    fpinfo["ustar"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ustar"], "name", default="ustar")
    fpinfo["L"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "L"], "name", default="L")
    fpinfo["z0"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "z0"], "name", default="z0")
    fpinfo["VSd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "VSd"], "name", default="V_SONIC_Sd")

    # Read the AWS data file
    # ======================
    df['Timestamp'] = (pandas.to_datetime(df['Year Month Day Hours Minutes in YYYY'].astype(str) + '-' +
                                          df['MM'].astype(str) + '-' +
                                          df['DD'].astype(str) + ' ' +
                                          df['HH24'].astype(str) + ':' +
                                          df['MI format in Local time'].astype(str)))

    Year = footprint_utils.create_empty_variable("Year", nrecs)
    Year["Label"] = "Year"
    Year["Data"] = df['Year Month Day Hours Minutes in YYYY'].to_numpy()
    Year["Flag"] = f0
    footprint_utils.CreateVariable(ds, Year)
    Month = footprint_utils.create_empty_variable("Month", nrecs)
    Month["Label"] = "Month"
    Month["Data"] = df['MM'].to_numpy()
    Month["Flag"] = f0
    footprint_utils.CreateVariable(ds, Month)
    Day = footprint_utils.create_empty_variable("Day", nrecs)
    Day["Label"] = "Day"
    Day["Data"] = df['DD'].to_numpy()
    Day["Flag"] = f0
    footprint_utils.CreateVariable(ds, Day)
    Hour = footprint_utils.create_empty_variable("Hour", nrecs)
    Hour["Label"] = "Hour"
    Hour["Data"] = df['HH24'].to_numpy()
    Hour["Flag"] = f0
    footprint_utils.CreateVariable(ds, Hour)
    Minute = footprint_utils.create_empty_variable("Minute", nrecs)
    Minute["Label"] = "Minute"
    Minute["Data"] = df['MI format in Local time'].to_numpy()
    Minute["Flag"] = f0
    footprint_utils.CreateVariable(ds, Minute)
    Second = footprint_utils.create_empty_variable("Second", nrecs)
    Second["Label"] = "Second"
    Second["Data"] = numpy.ma.array(numpy.full(nrecs, 0))
    Second["Flag"] = f0
    footprint_utils.CreateVariable(ds, Second)

    footprint_utils.get_datetimefromymdhms(ds)

    ldt = ds.series["DateTime"]["Data"]

    msg = " Got data from " + ldt[0].strftime("%Y-%m-%d %H:%M:%S") + " to " + ldt[-1].strftime("%Y-%m-%d %H:%M:%S")
    logger.info(msg)

    # Create the data structure ds
    df["Ws"] = df['Wind speed in m/s']
    df["Ws"] = pandas.to_numeric(df["Ws"], errors='coerce')
    Ws = footprint_utils.create_empty_variable("Ws", nrecs)
    Ws["Label"] = "Ws"
    Ws["Data"] = df["Ws"].to_numpy()
    Ws["Flag"] = f0
    Ws["Attr"] = {"long_name": " Wind speed", "units": "m/s", "standard_name": "not defined"}
    footprint_utils.CreateVariable(ds, Ws)

    df["Wd"] = df['Wind direction in degrees true']
    df["Wd"] = pandas.to_numeric(df["Wd"], errors='coerce')
    Wd = footprint_utils.create_empty_variable("Wd", nrecs)
    Wd["Label"] = "Wd"
    Wd["Data"] = df["Wd"].to_numpy()
    Wd["Flag"] = f0
    Wd["Attr"] = {"long_name": " Wind direction", "units": "degree", "standard_name": "not defined"}
    footprint_utils.CreateVariable(ds, Wd)

    # read the external file for Habl if mode = kljun
    if mode == "kljun_AWS":
        footprint_io.ImportSeries(cf, ds)
    else:  # kormei does not need Habl
        Habl = footprint_utils.create_empty_variable("Habl", nrecs)
        Habl["Label"] = "Habl"
        Habl["Data"] = numpy.ma.array(numpy.full(nrecs, 1000))
        Habl["Flag"] = f0
        Habl["Attr"] = {"long_name": " Boundary-layer height", "units": "m", "standard_name": "not defined"}
        footprint_utils.CreateVariable(ds, Habl)

    # Monin-Obukhov length
    # footprint_utils.CalculateMoninObukhovLength(ds, d)
    L = footprint_utils.create_empty_variable("L", nrecs)
    L["Label"] = "L"
    L["Data"] = numpy.ma.array(numpy.full(nrecs, fpinfo["MOL"]))
    L["Flag"] = f0
    L["Attr"] = {"long_name": " Monin-Obukhov length", "units": "m", "standard_name": "not defined"}
    footprint_utils.CreateVariable(ds, L)
    # cross wind standard deviation
    # could do better with:
    # 1) reprocess L3 and output variance of U, V and W
    # 2) estimated from standard deviation of wind direction (if available)
    # 3) estimate using MO relations (needs Habl)

    VSd = footprint_utils.create_empty_variable("VSd", nrecs)
    VSd["Data"] = 0.3 * df["Ws"].to_numpy()
    VSd["Flag"] = f0  # numpy.where(numpy.ma.getmaskarray(V_Sd["Data"])==True, f1, f0)
    VSd["Attr"]["long_name"] = "Variance of cross-wind velocity component, estimated from Ws"
    VSd["Attr"]["units"] = "(m/s)2"
    footprint_utils.CreateVariable(ds, VSd)
    # === friction velocity, use 10 % of the wind speed
    Ws = footprint_utils.GetVariable(ds, "Ws")
    ustar = footprint_utils.create_empty_variable("ustar", nrecs)
    # ustar["Data"] = numpy.ma.array(numpy.full(nrecs,float(cf["Options"]["USTAR"])))
    ustar["Data"] = 0.1 * Ws["Data"]
    ustar["Attr"]["long_name"] = "friction velocity"
    ustar["Flag"] = f0  # numpy.where(numpy.ma.getmaskarray(ustar["Data"])==True, f1, f0)
    ustar["Attr"]["units"] = "m/s"
    footprint_utils.CreateVariable(ds, ustar)
    # === roughness length
    z0 = footprint_utils.create_empty_variable("z0", nrecs)
    zT = float(cf["Options"]["tower_height"])
    zC = float(cf["Options"]["canopy_height"])
    zm = zT - (2.0 / 3.0) * zC
    L = footprint_utils.GetVariable(ds, "L")
    ustar = footprint_utils.GetVariable(ds, "ustar")
    z0["Data"] = footprint_utils.z0calc(zm, L["Data"], Ws["Data"], ustar["Data"])
    z0["Attr"]["long_name"] = "Roughness length calculated from u*, L, Ws and (z-d)"
    z0["Flag"] = numpy.where(numpy.ma.getmaskarray(z0["Data"]) == True, f1, f0)
    z0["Attr"]["units"] = "m"
    footprint_utils.CreateVariable(ds, z0)

    return ds


def get_footprint_L3_data_in(cf, fpinfo, mode):
    import footprint_utils
    # read input data and prepare for input into Kormann and Meixner, 2001 or Kljun et al., 2015
    # ---------------------- Get input / output file name ------------------------------------

    # =======
    # [Files]
    # =======

    fpinfo["in_filename"] = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'])
    fpinfo["results_file"] = os.path.join(cf['Files']['plot_path'], cf['Files']['results_file'])

    # read the netcdf file
    msg = ' Reading L3 netCDF file ' + str(fpinfo["in_filename"])
    logger.info(msg)
    ds = footprint_io.nc_read_series(fpinfo["in_filename"])
    nrecs = int(ds.globalattributes["nc_nrecs"])

    # === Which climatology, either definded time, daily, monthly or annual
    fpinfo["Climatology"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Climatology", default="Special")

    # get the output file name from controlfile or set up automatically
    if "out_filename" in cf["Files"]:
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["out_filename"])
    else:
        climfreq = fpinfo["Climatology"]
        if climfreq == 'Annual':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_y_fp.nc"))
        elif climfreq == 'Monthly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_m_fp.nc"))
        elif climfreq == 'Daily':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_d_fp.nc"))
        elif climfreq == 'Hourly':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_h_fp.nc"))
        elif climfreq == 'Single':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_si_fp.nc"))
        elif climfreq == 'Special':
            file_out = os.path.join(cf['Files']['file_path'], cf['Files']['in_filename'].replace(".nc", "_sp_fp.nc"))
        fpinfo["out_filename"] = os.path.join(cf["Files"]["file_path"], file_out)

    # plot path
    fpinfo["plot_path"] = footprint_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    if not os.path.exists(fpinfo["plot_path"]):
        os.makedirs(fpinfo["plot_path"])

    # =========
    # [Options]
    # =========

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "footprint_size", default="1000")
    fpinfo["footprint_size"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "num_cells", default="250")
    fpinfo["num_cells"] = int(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "tower_height", default="20")
    fpinfo["tower_height"] = float(opt)
    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "canopy_height", default="5")
    fpinfo["canopy_height"] = float(opt)

    fpinfo["zm"] = fpinfo["tower_height"] - fpinfo["canopy_height"]
    if ((fpinfo["zm"] < 0.0) or (fpinfo["zm"] > 1000.0)):
        msg = "zm is invalid"
        logger.error(msg)

    opt = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "Fsd_threshold", default="10")
    fpinfo["Fsd_threshold"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "Cumulative", default=False)
    fpinfo["Cumulative"] = int(opt)
    opt = footprint_utils.get_optionskeyaslogical(cf, "AreaOfInterest", default=False)
    fpinfo["AreaOfInterest"] = int(opt)

    fpinfo["site_name"] = ds.globalattributes["site_name"]
    fpinfo["flux_period"] = int(ds.globalattributes["time_step"])

    fpinfo["zm_d"] = fpinfo["tower_height"] - (2.0 / 3.0 * fpinfo["canopy_height"])
    fpinfo["xTower"] = 0  # int(cf['Tower']['xTower'])
    fpinfo["yTower"] = 0  # int(cf['Tower']['yTower'])
    fpinfo["xmin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["xmax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["ymin"] = -0.5 * fpinfo["footprint_size"]
    fpinfo["ymax"] = 0.5 * fpinfo["footprint_size"]
    fpinfo["nx"] = int(cf["Options"]["num_cells"])

    fpinfo["call_mode"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode", default="interactive",
                                                             mode="quiet")
    fpinfo["show_plots"] = footprint_utils.get_keyvaluefromcf(cf, ["Options"], "show_plots", default=True, mode="quiet")

    if "Latitude" in cf["Options"]:
        fpinfo["latitude"] = cf["Options"]["Latitude"]
    else:
        fpinfo["latitude"] = ds.globalattributes["latitude"]
    if "Longitude" in cf["Options"]:
        fpinfo["longitude"] = cf["Options"]["Longitude"]
    else:
        fpinfo["longitude"] = ds.globalattributes["longitude"]

    # array of 0s for QC flag
    f0 = numpy.zeros(nrecs, dtype=numpy.int32)
    # array of 1s for QC flag
    f1 = numpy.ones(nrecs, dtype=numpy.int32)

    # get the variable names
    fpinfo["Fsd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fsd"], "name", default="Fsd")
    fpinfo["Wd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Wd"], "name", default="Wd")
    fpinfo["Ws"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ws"], "name", default="Ws")
    fpinfo["Ta"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Ta"], "name", default="Ta")
    fpinfo["AH"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "AH"], "name", default="AH")
    fpinfo["ps"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ps"], "name", default="ps")
    fpinfo["Fh"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "Fh"], "name", default="Fh")

    fpinfo["ustar"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "ustar"], "name", default="ustar")
    fpinfo["L"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "L"], "name", default="L")
    fpinfo["z0"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "z0"], "name", default="z0")
    fpinfo["VSd"] = footprint_utils.get_keyvaluefromcf(cf, ["Variables", "VSd"], "name", default="V_SONIC_Sd")

    # Read the L3 data file
    # ======================
    Fsd = footprint_utils.GetVariable(ds, fpinfo["Fsd"])
    Fsd["Label"] = "Fsd"
    footprint_utils.CreateVariable(ds, Fsd)
    Ws = footprint_utils.GetVariable(ds, fpinfo["Ws"])
    Ws["Label"] = "Ws"
    footprint_utils.CreateVariable(ds, Ws)
    Wd = footprint_utils.GetVariable(ds, fpinfo["Wd"])
    Wd["Label"] = "Wd"
    footprint_utils.CreateVariable(ds, Wd)
    Ta = footprint_utils.GetVariable(ds, fpinfo["Ta"])
    Ta["Label"] = "Ta"
    footprint_utils.CreateVariable(ds, Ta)
    AH = footprint_utils.GetVariable(ds, fpinfo["AH"])
    AH["Label"] = "AH"
    footprint_utils.CreateVariable(ds, AH)
    ps = footprint_utils.GetVariable(ds, fpinfo["ps"])
    ps["Label"] = "ps"
    footprint_utils.CreateVariable(ds, ps)
    Fh = footprint_utils.GetVariable(ds, fpinfo["Fh"])
    Fh["Label"] = "Fh"
    footprint_utils.CreateVariable(ds, Fh)

    # read the external file for Habl if mode = kljun
    if mode == "kljun":
        footprint_io.ImportSeries(cf, ds)  # === check to see if we have Habl timeseries in imports
    else:  # kormei does not need Habl
        Habl = footprint_utils.create_empty_variable("Habl", nrecs)
        Habl["Label"] = "Habl"
        Habl["Data"] = numpy.ma.array(numpy.full(nrecs, 1000))
        Habl["Flag"] = f0
        Habl["Attr"] = {"long_name": " Boundary-layer height", "units": "m"}
        footprint_utils.CreateVariable(ds, Habl)

    # cross wind standard deviation
    VSd = footprint_utils.GetVariable(ds, fpinfo["VSd"])
    VSd["Label"] = "VSd"
    footprint_utils.CreateVariable(ds, VSd)

    # friction velocity
    ustar = footprint_utils.GetVariable(ds, fpinfo["ustar"])
    ustar["Label"] = "ustar"
    footprint_utils.CreateVariable(ds, ustar)

    msg = "Get Monin-Obukhov length from "
    logger.info(msg)
    if fpinfo["L"] in list(ds.series.keys()):
        L = footprint_utils.GetVariable(ds, fpinfo["L"])
        L["Label"] = "L"
        footprint_utils.CreateVariable(ds, L)
        msg = "   ... data structure"
        logger.info(msg)
    else:
        footprint_utils.CalculateMoninObukhovLength(ds, fpinfo)
        msg = "   ... calculation"
        logger.info(msg)

        # === roughness length
    msg = "Get roughness length from "
    logger.info(msg)
    if fpinfo["z0"] in list(ds.series.keys()):
        z0 = footprint_utils.GetVariable(ds, fpinfo["z0"])
        z0["Label"] = "z0"
        footprint_utils.CreateVariable(ds, z0)
        msg = "   ... data structure"
        logger.info(msg)
    else:
        z0 = footprint_utils.create_empty_variable("z0", nrecs)
        msg = "Create z0 variable"
        logger.info(msg)
        if "roughness_length" in list(ds.globalattributes.keys()):
            roughness_length = float(ds.globalattributes["roughness_length"])
            z0["Data"] = numpy.ma.array(numpy.full(nrecs, roughness_length))
            z0["Attr"]["long_name"] = "Roughness length from global attributes"
            msg = "   ... from global attribute value"
            logger.info(msg)
        elif "roughness_length" in cf["Options"]:
            roughness_length = float(cf["Options"]["roughness_length"])
            z0["Data"] = numpy.ma.array(numpy.full(nrecs, roughness_length))
            z0["Attr"]["long_name"] = "Roughness length from footprint control file"
            msg = "   ... from footprint controlfile"
            logger.info(msg)
        else:
            zT = float(cf["Options"]["tower_height"])
            zC = float(cf["Options"]["canopy_height"])
            zm = zT - (2.0 / 3.0) * zC
            L = footprint_utils.GetVariable(ds, "L")
            ustar = footprint_utils.GetVariable(ds, fpinfo["ustar"])
            Ws = footprint_utils.GetVariable(ds, "Ws")
            z0["Data"] = footprint_utils.z0calc(zm, L["Data"], Ws["Data"], ustar["Data"])
            z0["Attr"]["long_name"] = "Roughness length calculated from u*, L, Ws and (z-d)"
            msg = "   ... from calculation"
            logger.info(msg)
        z0["Flag"] = numpy.where(numpy.ma.getmaskarray(z0["Data"]) == True, f1, f0)
        z0["Attr"]["units"] = "m"
        footprint_utils.CreateVariable(ds, z0)

    return ds


def kml_initialise(fpinfo, fi, mode):
    #
    # !#kmlname = fpinfo["site_name"] + '_' + mode + '_fp' + '.kml'
    # !#kml_name_path = fpinfo["plot_path"] +kmlname
    # !#fi = open(kml_name_path, 'w')
    fi.write('<?xml version="1.0" encoding="UTF-8"?>\n')
    fi.write('<kml xmlns="http://www.opengis.net/kml/2.2">\n')
    fi.write("<Folder>\n")
    fi.write("  <name>" + fpinfo["site_name"] + "</name>")
    # GE zooms in to the site location
    fi.write('  <LookAt>\n')
    fi.write('    <longitude>' + str(fpinfo["longitude"]) + '</longitude>\n')
    fi.write('    <latitude>' + str(fpinfo["latitude"]) + '</latitude>\n')
    fi.write('    <altitude>' + str(fpinfo["footprint_size"]) + '</altitude>\n')
    fi.write('    <range>' + str(fpinfo["footprint_size"]) + '</range>\n')
    fi.write('    <tilt>0</tilt>\n')
    fi.write('    <heading>0</heading>\n')
    fi.write('    <altitudeMode>relativeToGround</altitudeMode>\n')
    fi.write('  </LookAt>\n')
    # Define the legend in a screen overlay
    fi.write('  <ScreenOverlay>\n')
    fi.write('    <name>Legend: Footprint</name>\n')
    fi.write('    <Icon> <href>cbar.png</href></Icon>\n')
    fi.write('    <overlayXY x="0" y="0" xunits="fraction" yunits="fraction"/>\n')
    fi.write('    <screenXY x="25" y="95" xunits="pixels" yunits="pixels"/>\n')
    fi.write('    <rotationXY x="0.5" y="0.5" xunits="fraction" yunits="fraction"/>\n')
    fi.write('    <size x="0" y="0" xunits="pixels" yunits="pixels"/>\n')
    fi.write('  </ScreenOverlay>\n')
    # Adding our own icon for the placemark
    # fi.write('  <Style id="tower">\n')
    # fi.write('    <IconStyle>\n')
    # fi.write('      <scale>1.5</scale>\n')
    # fi.write('      <Icon>\n')
    # fi.write('        <href>ec_tower.png</href>\n') # !!! this file needs to be copied into the plot directory
    # fi.write('      </Icon>\n')
    # fi.write('    </IconStyle>\n')
    # fi.write('  </Style>\n')
    # Adding a placemark for the site
    fi.write('  <Placemark>\n')
    fi.write('      <name>' + fpinfo["site_name"] + '</name>\n')
    # fi.write('      <styleUrl>#tower</styleUrl>')
    fi.write('      <Point>\n')
    fi.write(
        '          <coordinates>' + str(fpinfo["longitude"]) + ',' + str(fpinfo["latitude"]) + ',0</coordinates>\n')
    fi.write('      </Point>\n')
    fi.write('  </Placemark>\n')


def kml_write(lon, lat, zt1, zt2, data, station, mode, clevs, fi, plot_path, i_cum):
    plot_in = 'Footprint_' + mode + zt1.strftime("%Y%m%d%H%M") + '.png'
    plotname = plot_path + plot_in
    width = 5
    height = width * data.shape[0] / data.shape[1]
    plt.ioff()
    plt.figure(figsize=(width, height))
    cs = plt.contourf(data, clevs, cmap=plt.get_cmap('hsv'), alpha=0.5)  # for full colour images
    # cs = plt.contour(data,clevs,alpha=0.5) # for contours only
    plt.axis('off')
    plt.savefig(plotname, transparent=True)
    # plt.clf()
    fn = plt.gcf().number
    plt.close(fn)
    # draw a new figure and replot the colorbar there
    fig, ax = plt.subplots(figsize=(width, height))
    cbar = plt.colorbar(cs, ax=ax)
    # =========================================================================
    # rlevs = [1 - clev for clev in clevs if clev is not None]
    # cbar.set_ticks(rlevs)
    cbar.set_ticks(clevs)
    if i_cum:
        cbar.set_label('Cumulative footprint contribution in percent')
    else:
        cbar.set_label('Percentage of footprint contribution')
    ax.remove()
    plt.savefig(plot_path + 'cbar.png', bbox_inches='tight')  # , transparent=True)
    fn = plt.gcf().number
    plt.close(fn)
    plt.ion()
    # get the lat/lon bounds of the area
    lon1 = lon[0]
    lon2 = lon[-1]
    lat1 = lat[0]
    lat2 = lat[-1]
    # Hopefully the file was opened properly and the header written
    fi.write('<GroundOverlay>\n')
    fi.write('  <name>' + station + zt2.strftime("%Y%m%d%H%M") + '</name>\n')
    fi.write('  <bgColor>8fffffff</bgColor>\n')
    fi.write('  <Icon>\n')
    fi.write('    <href>' + plot_in + '</href>\n')
    fi.write('  </Icon>\n')
    fi.write('  <TimeSpan>\n')
    fi.write('    <begin>' + zt1.strftime("%Y-%m-%dT%H:%M") + '</begin>\n')
    fi.write('    <end>' + zt2.strftime("%Y-%m-%dT%H:%M") + '</end>\n')
    fi.write('  </TimeSpan>\n')
    fi.write('  <altitude>0.0</altitude>\n')
    fi.write('  <altitudeMode>clampToGround</altitudeMode>\n')
    fi.write('  <LatLonBox>\n')
    fi.write('    <north>' + str(lat2) + '</north>\n')
    fi.write('    <south>' + str(lat1) + '</south>\n')
    fi.write('    <east>' + str(lon2) + '</east>\n')
    fi.write('    <west>' + str(lon1) + '</west>\n')
    fi.write('    <rotation>0.0</rotation>\n')
    fi.write('  </LatLonBox>\n')
    fi.write('</GroundOverlay>\n')


def kml_finalise(fpinfo, fi, mode, kmlname):
    # write the footer of the kml file and close the file
    fi.write("</Folder>\n")
    fi.write('</kml>\n')
    fi.close()
    # copy tower icon into the plot path directory to be added to the kmz file
    # create a kmz file out of the kml file
    cwd = os.getcwd()
    os.chdir(fpinfo["plot_path"])
    kmzname = kmlname.replace(".kml", ".kmz")
    msg = " Creating KMZ file " + kmzname
    logger.info(msg)
    plotlist = [p for p in os.listdir('.') if p.endswith(".png")]
    compression = zipfile.ZIP_DEFLATED
    zf = zipfile.ZipFile(kmzname, mode='w')
    zf.write(kmlname, compress_type=compression)
    os.remove(kmlname)
    for f in plotlist:
        zf.write(f, compress_type=compression)
        os.remove(f)
    zf.close()
    os.chdir(cwd)


def plotphifield(x, y, zt1, zt2, data, station, mode, clevs, imagename, i_cum):
    # plot footprint in 2-dim field; use x,y - coordinates
    text = 'Footprint ' + station + ' ' + zt1.strftime("%Y%m%d%H%M") + '  to  ' + zt2.strftime("%Y%m%d%H%M")
    plotname = 'plots/Footprint_' + mode + zt1.strftime("%Y%m%d%H%M") + '.jpg'
    x_ll = x[0, 0]  # xllcorner #-250
    x_ur = x[-1, -1]  # xurcorner # 250
    y_ll = y[0, 0]  # yllcorner #-250
    y_ur = y[-1, -1]  # yurcorner # 250
    # create figure and axes instances
    plt.ion()
    fig = plt.figure(figsize=(10, 10))
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.8])
    cs = plt.contourf(x, y, data, clevs, cmap=plt.get_cmap('hsv'))
    cbar = plt.colorbar(cs, location='right', pad=0.04, fraction=0.046)
    if i_cum:
        cbar.set_label('Cumulative footprint contribution in percent')
    else:
        cbar.set_label('Percentage of footprint contribution')
    # contour levels
    plt.title(text)
    plt.xlabel('x [m]')
    plt.ylabel('y [m]')
    if imagename != None:
        # img = imread(imagename)
        img = plt.imread(imagename)
        plt.imshow(img, zorder=0, extent=[x_ll, x_ur, y_ll, y_ur])
    plt.savefig(plotname)
    plt.draw()
    plt.pause(1e-9)
    plt.ioff()


def calc_cumulative(f, f_min, f_step):
    # ------------------------------------------------------------------------------------
    # calculate the cumulative footprint values by correlating the percentage of max field
    # to the contribution of the area between two isolines to the total
    # cmewenz - Feb 2019
    fcum05 = numpy.ma.masked_where(f <= f_min, f)
    fcum05 = numpy.ma.filled(fcum05, float(0))
    fcum = numpy.sum(fcum05)
    num = int(round((1.0 - (f_min)) / f_step))
    ser1 = numpy.linspace(1.0 - f_step, f_min, num)
    ser2 = numpy.linspace(1.0, f_min + f_step, num)
    ser3 = 0.5 * (ser1 + ser2)
    cclevs = []
    stest = 0.0
    fmax = numpy.amax(f)
    for i in range(0, len(ser1)):
        test = numpy.ma.masked_where((f <= ser1[i]) | (f > ser2[i]), f)
        if test.count() > 0:
            test = numpy.sum(test) / fcum
        else:
            test = 0.0
        stest = stest + test
        cclevs.append(stest)
    # estimating polygon to match the correlation between cumulative and percent from max
    fcum_eq = numpy.polyfit(ser3, cclevs, 3)
    # print fcum_eq
    fcum = fcum_eq[0] * f * f * f + fcum_eq[1] * f * f + fcum_eq[2] * f + fcum_eq[3]
    f = fcum

    return f


def PolygonContribution(cf, x, y, fm, start, finish, paoi):
    # =======================================================================================================
    # Create a field which defines in what area of interest each grid point is located in
    # a maximum of 10 AoIs can be defined, must be rectangles but do not need to line up
    # with the grid, so can be to an angle of the x,y grid
    # ID = number for field identification
    # area = rectangle specification; x1_coord y1_coord x2_coord y2_coord x3_coord y3_coord x4_coord y4_coord
    # cmewenz 22/02/2019
    # =======================================================================================================
    ix, iy = numpy.shape(fm)
    x, y = x.flatten(), y.flatten()
    points = numpy.vstack((x, y)).T
    sum_fm = fm.sum()
    for ID in list(cf["AOI"].keys()):
        area = footprint_utils.get_keyvaluefromcf(cf, ["AOI", ID], "area", default="")
        area = [float(i) for i in area]
        vertices = numpy.reshape(area, (-1, 2))
        polygon = Path(vertices)
        # Find if grid point is inside a polygon using matplotlib
        # (https://stackoverflow.com/questions/21339448/how-to-get-list-of-points-inside-a-polygon-in-python)
        grid = polygon.contains_points(points)
        mask = grid.reshape(ix, iy)
        # mask fm to only contain the area of interest data
        fm_masked = numpy.ma.compressed(numpy.ma.masked_where(mask == False, fm))
        # sum the area
        sum_fm_masked = fm_masked.sum()
        # write to file
        paoi.write("%s, %s, % 8.2f\n" % (start.strftime("%Y%m%d %H%M"), ID, 100.0 * (sum_fm_masked / sum_fm)))
    return


import logging

logger = logging.getLogger("footprint_log")


def FKM_climatology(fpinfo, time=None, zm=None, z0=None, umean=None, ol=None, sigmav=None, ustar=None,
                    wind_dir=None, domain=None, dx=None, dy=None, nx=None, ny=None,
                    rs=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8], rslayer=0,
                    smooth_data=1, crop=False, pulse=None, verbosity=2):
    """
    Derive a flux footprint estimate based on the paper from Kormann and Meixner (2001). The equations solved
    follow the work from Neftel et al. (2008) and the ART footprint tool. Currently no sections are
    defined to estimate the proportion of footprint source from this defined areas as in Neftel et al. (2008).
    See Kormann, R. and Meixner, F.X., 2001: An analytical footprint model for non-neutral stratification.
    Boundary-Layer Meteorology 99: 207. https://doi.org/10.1023/A:1018991015119 and
    Neftel, A., Spirig, C., Ammann, C., 2008: Application and test of a simple tool for operational footprint
    evaluations. Environmental Pollution 152, 644-652. for details.
    The layout of this python script follows the footprint climatology layout by Kljun et al., 2015.
    contact: cacilia.ewenz@internode.on.net

    This function calculates footprints within a fixed physical domain for a series of
    time steps, rotates footprints into the corresponding wind direction and aggregates
    all footprints to a footprint climatology. The percentage of source area is
    calculated for the footprint climatology.


    FKM Input
        All vectors need to be of equal length (one value for each time step)
        zm       = Measurement height above displacement height (i.e. z-d) [m]
                   usually a scalar, but can also be a vector
        z0       = Roughness length [m]
                   usually a scalar, but can also be a vector
        umean    = Vector of mean wind speed at zm [ms-1] - enter [None] if not known
                   Either z0 or umean is required. If both are given,
                   z0 is selected to calculate the footprint
        ol       = Vector of Obukhov length [m]
        sigmav   = Vector of standard deviation of lateral velocity fluctuations [ms-1]
                   if not available it is calculated as 0.5*Ws (wind speed)
        ustar    = Vector of friction velocity [ms-1]
        wind_dir = Vector of wind direction in degrees (of 360) for rotation of the footprint

        Optional input:
        domain       = Domain size as an array of [xmin xmax ymin ymax] [m].
                       Footprint will be calculated for a measurement at [0 0 zm] m
                       Default is smallest area including the r% footprint or [-1000 1000 -1000 1000]m,
                       whichever smallest (80% footprint if r not given).
        dx, dy       = Cell size of domain [m]
                       Small dx, dy results in higher spatial resolution and higher computing time
                       Default is dx = dy = 2 m. If only dx is given, dx=dy.
        nx, ny       = Two integer scalars defining the number of grid elements in x and y
                       Large nx/ny result in higher spatial resolution and higher computing time
                       Default is nx = ny = 1000. If only nx is given, nx=ny.
                       If both dx/dy and nx/ny are given, dx/dy is given priority if the domain is also specified.
        pulse        = Display progress of footprint calculations every pulse-the footprint (e.g., "100")
        verbosity    = Level of verbosity at run time: 0 = completely silent, 1 = notify only of fatal errors,
                       2 = all notifications
    FKM output
        FKM      = Structure array with footprint climatology data for measurement at [0 0 zm] m
        x_2d     = x-grid of 2-dimensional footprint [m]
        y_2d     = y-grid of 2-dimensional footprint [m]
        fclim_2d = Normalised footprint function values of footprint climatology [m-2]
        n        = Number of footprints calculated and included in footprint climatology
        flag_err = 0 if no error, 1 in case of error, 2 if not all contour plots (rs%) within specified domain

    Footprint calculation following the Kormann-Meixner Approach
    1st Version by Marx Stampfli, stampfli mathematics, Bern, Switzerland
    Revision December 2006, C. Spirig and A. Neftel, Agroscope, Zurich, Switzerland
                ported into python CM Ewenz, Adelaide Nov 2015 to May 2016
    Array of lower and upper ranges for following parameters
                 (empty,Xcoord,Ycoord,U_star,     LM,Std_v,Wdir,   zm,U_meas,empty)
    lrange = Array(0,    -5000, -5000,  0.01,-999999,    0,   0,    0,     0,    0)
    urange = Array(0,     5000,  5000,     5, 999999,   20, 360, 1000,    30,    0)

    Created: May 2018 Cacilia Ewenz
    version: 0.1
    last change: 08/06/2018 Cacilia Ewenz
    Copyright (C) 2018, Cacilia Ewenz
    """


    c_d2r = c.Pi / 180.0

    # =============
    result = {}
    # ================================================================================
    # initialise counter for exception messages
    counter = [None] * 22  # There are 21/20 different exceptions raised in kormei/kljun
    msgstring = [None] * 22
    # Input check
    flag_err = 0

    # Check existence of required input pars
    if None in [zm, ol, sigmav, ustar] or (z0 is None and umean is None):
        raise_fkm_exception(1, verbosity, counter, msgstring)

    # Convert all input items to lists
    if not isinstance(zm, list): zm = [zm]
    if not isinstance(ol, list): ol = [ol]
    if not isinstance(sigmav, list): sigmav = [sigmav]
    if not isinstance(ustar, list): ustar = [ustar]
    if not isinstance(wind_dir, list): wind_dir = [wind_dir]
    if not isinstance(z0, list): z0 = [z0]
    if not isinstance(umean, list): umean = [umean]

    # Check that all lists have same length, if not raise an error and exit
    ts_len = len(ustar)
    # print " zm = ",len(zm),len(ol),len(z0)

    if any(len(lst) != ts_len for lst in [sigmav, wind_dir, ol]):
        # at least one list has a different length, exit with error message
        raise_fkm_exception(11, verbosity, counter, msgstring)

    # Special treatment for zm, which is allowed to have length 1 for any
    # length >= 1 of all other parameters
    if all(val is None for val in zm): raise_fkm_exception(12, verbosity, counter, msgstring)
    if len(zm) == 1:
        # raise_fkm_exception(17, verbosity, counter, msgstring)
        zm = [zm[0] for i in range(ts_len)]

    # Rename lists as now the function expects time series of inputs
    times, ustars, sigmavs, ols, wind_dirs, zms, z0s, umeans = \
        time, ustar, sigmav, ol, wind_dir, zm, z0, umean

    # ===========================================================================
    # Define computational domain
    # Check passed values and make some smart assumptions
    if isinstance(dx, numbers.Number) and dy is None: dy = dx
    if isinstance(dy, numbers.Number) and dx is None: dx = dy
    if not all(isinstance(item, numbers.Number) for item in [dx, dy]): dx = dy = None
    if isinstance(nx, int) and ny is None: ny = nx
    if isinstance(ny, int) and nx is None: nx = ny
    if not all(isinstance(item, int) for item in [nx, ny]): nx = ny = None
    if not isinstance(domain, list) or len(domain) != 4: domain = None

    if all(item is None for item in [dx, nx, domain]):
        # If nothing is passed, default domain is a square of 2 Km size centered
        # at the tower with pixel size of 2 meters (hence a 1000x1000 grid)
        domain = [-1000., 1000., -1000., 1000.]
        dx = dy = 2.
        nx = ny = 1000
    elif domain is not None:
        # If domain is passed, it takes the precendence over anything else
        if dx is not None:
            # If dx/dy is passed, takes precendence over nx/ny
            nx = int((domain[1] - domain[0]) / dx)
            ny = int((domain[3] - domain[2]) / dy)
        else:
            # If dx/dy is not passed, use nx/ny (set to 1000 if not passed)
            if nx is None: nx = ny = 1000
            # If dx/dy is not passed, use nx/ny
            dx = (domain[1] - domain[0]) / float(nx)
            dy = (domain[3] - domain[2]) / float(ny)
    elif dx is not None and nx is not None:
        # If domain is not passed but dx/dy and nx/ny are, define domain
        domain = [-nx * dx / 2, nx * dx / 2, -ny * dy / 2, ny * dy / 2]
    elif dx is not None:
        # If domain is not passed but dx/dy is, define domain and nx/ny
        domain = [-1000, 1000, -1000, 1000]
        nx = int((domain[1] - domain[0]) / dx)
        ny = int((domain[3] - domain[2]) / dy)
    elif nx is not None:
        # If domain and dx/dy are not passed but nx/ny is, define domain and dx/dy
        domain = [-1000, 1000, -1000, 1000]
        dx = (domain[1] - domain[0]) / float(nx)
        dy = (domain[3] - domain[2]) / float(nx)

    # Put domain into more convenient vars
    xmin, xmax, ymin, ymax = domain
    # print " domain = ",xmin,xmax,ymin,ymax

    # Define pulse if not passed
    if pulse == None:
        if ts_len <= 20:
            pulse = 1
        else:
            pulse = int(ts_len / 20)

    # ===========================================================================
    # Define physical domain in cartesian and polar coordinates
    # Cartesian coordinates
    x = numpy.linspace(xmin, xmax, nx + 1)
    y = numpy.linspace(ymin, ymax, ny + 1)
    x_2d, y_2d = numpy.meshgrid(x, y)

    # initialize raster for footprint climatology
    fclim_2d = numpy.zeros(x_2d.shape)
    # ===========================================================================
    # Loop on time series

    # Initialize logic array valids to those 'timestamps' for which all inputs are
    # at least present (but not necessarily physically plausible)
    valids = [True if not any([val is None for val in vals]) else False \
              for vals in zip(ustars, sigmavs, ols, wind_dirs, zms)]

    for ix, (time, ustar, sigmav, ol, wind_dir, zm, z0, umean) \
            in enumerate(zip(times, ustars, sigmavs, ols, wind_dirs, zms, z0s, umeans)):

        # Counter
        if verbosity > 1 and ix % pulse == 0:
            progress = float(ix + 1) / float(ts_len)
            footprint_utils.update_progress(progress)
            # msg = "Calculating footprint ", ix+1, " of ", str(ts_len)
            # logger.info(msg)

        valids[ix] = check_fkm_inputs(ustar, sigmav, ol, wind_dir, zm, z0, umean, rslayer, verbosity, counter,
                                      msgstring)
        # If inputs are not valid, skip current footprint
        # if not valids[ix]:
        #     raise_fkm_exception(16, verbosity, counter, msgstring)
        # else:
        if valids[ix]:
            # --- calculate Korman-Meixner footprint
            # phi, u, m, n
            zmol = zm / ol
            # print zm, ol, zmol
            if ol > 0.0:
                phi = 1.0 + 5.0 * zmol
                u = (ustar / c.k) * (numpy.log(zm / z0) + 5.0 * zmol)
                m = (1.0 + 5.0 * (zmol)) / (numpy.log(zm / z0) + 5.0 * zmol)
                n = 1.0 / (1.0 + 5.0 * zmol)
                # print("pix=", ix, n, zmol)
            elif ol == 0.0:
                phi = 1.0
                u = ustar / c.k * (numpy.log(zm / z0))
                m = ustar / c.k / u
                n = 1.0
                # print("zix=", ix, n, zmol)
            else:
                zeta = (1.0 - 16.0 * zmol) ** 0.25
                psi = -2.0 * numpy.log(0.5 * (1.0 + zeta)) - numpy.log(0.5 * (1.0 + zeta * zeta)) + 2.0 * numpy.arctan(
                    zeta) - 0.5 * c.Pi
                phi = 1.0 / (zeta ** 2)
                u = ustar / c.k * (numpy.log(zm / z0) + psi)
                m = ustar / c.k / zeta / u
                n = (1.0 - 24.0 * zmol) / (1.0 - 16.0 * zmol)
                # print("nix=", ix, n, zmol)
            # r, mu
            r = 2 + m - n

            mu = (1 + m) / (2 + m - n)

            # U=Umaj, Kmaj, xi
            Umaj = u / (zm ** m)
            Kmaj = c.k * ustar * zm / phi / zm ** n
            # Kmaj corresponds to kappa in KM 2001
            xi = Umaj * (zm ** r) / (r * r * Kmaj)
            # xPhiMax is the (x-)position of the maximum of phi
            xPhiMax = r * xi / (2 * r + 1)

            if mu == 0.0:
                GammaProxmu = 0.0
            else:
                GammaProxmu = (1.0 / mu) + 0.1002588 * numpy.exp(mu) - 0.493536 + 0.3066 * mu - 0.09 * (mu ** 2)

            if 1 / r == 0.0:
                GammaProx1r = 0.0
            else:
                GammaProx1r = r + 0.1002588 * numpy.exp(1 / r) - 0.493536 + 0.3066 * (1 / r) - 0.09 * ((1 / r) ** 2)

            # Kormann-Meixner parameters A-E
            A = 1 + mu
            B = Umaj * (zm ** r) / r / r / Kmaj
            C = (B ** mu) / GammaProxmu
            D = sigmav * GammaProx1r / GammaProxmu / ((r * r * Kmaj / Umaj) ** (m / r)) / Umaj
            E = (r - m) / r
            #
            # Ellipse parameter for KorMei output
            #
            lev = 0.01
            # lev = 0.2
            phimax = KorMeix0(xPhiMax, 0, 0, A, B, C, D, E)
            KM_p01a = EllipseZero(False, lev, xPhiMax, phimax, A, B, C, D,
                                  E)  # x value closest to sensor where phi(x,0)=0.01
            KM_p01b = EllipseZero(True, lev, xPhiMax, phimax, A, B, C, D,
                                  E)  # x value far away from sensor where phi(x,0)=0.01
            x0 = (KM_p01b - KM_p01a) / 2  # center of ellipse
            KM_p01c = EllipseMax(x0, lev, xPhiMax, phimax, A, B, C, D, E, mu, xi)  # half width of ellipse
            #
            # Result: f_2d = normalised f_2d field over the x and y gridcells
            #
            f_2d = numpy.zeros(x_2d.shape)
            # Wind direction and mathematical definitions of angles
            theta = numpy.fmod(450.0 - wind_dir, 360.0) * c_d2r
            x_ = x_2d * numpy.cos(theta) + y_2d * numpy.sin(theta)
            y_ = -x_2d * numpy.sin(theta) + y_2d * numpy.cos(theta)
            # mask negative x values
            f_2d = numpy.ma.masked_where(x_ <= 0.0, f_2d)
            x_ma = numpy.ma.masked_where(x_ <= 0.0, x_)

            # This is the original version from the ART-footprint model of Neftel et al., 2008
            # --------------------------------------------------------------------------------
            # sigma = D * x**E
            # CWIF = C * numpy.exp(-B / x) * x**(-A)

            sigma = D * x_ma ** E
            F = C * numpy.exp(-B / x_ma) * x_ma ** (-A)
            Dy = 1 / numpy.sqrt(2 * c.Pi) / sigma * numpy.exp(-y_ ** 2 / 2 / sigma ** 2)

            # print("KM: ",Umaj,Kmaj,m,n,A,B,C,D,E,sigma,F,Dy)

            Phimaj = Dy * F
            KorMeix = Phimaj
            f_2d = KorMeix

            f_2d = numpy.ma.filled(f_2d, float(0))
            # ====================================
            # Add to footprint climatology raster
            # print "max of f_2d=",np.max(f_2d)
            fclim_2d = fclim_2d + f_2d;
            # ===================================
            result[time] = {'ustar': ustar, 'Vsd': sigmav, 'L': ol, 'Wd': wind_dir, 'Ws': umean, \
                            'z0': z0, 'A': A, 'B': B, 'C': C, 'D': D, 'E': E, \
                            'KM_p01a': KM_p01a, 'KM_p01b': KM_p01b, 'KM_p01c': KM_p01c}

    if fpinfo["Climatology"] == 'Special':
        results_file = fpinfo["results_file"]
        # AWSdata = cf['Files']['AWSdata']
        df = pandas.DataFrame(result)
        msg = "Write Kormann and Meixner parameter into csv file"
        logger.info(msg)
        # out = fpinfo["out_filename"].replace(".nc",".csv")
        df.transpose(copy=False).to_csv(results_file)
    # ========================================================
    # Continue if at least one valid footprint was calculated
    n = sum(valids)
    vs = None
    clevs = None
    if n == 0:
        logger.warning("No footprint calculated")
        flag_err = 1
    else:
        # ===========================================================================
        # Normalize and smooth footprint climatology
        fclim_2d = fclim_2d / n;

        # logger.info("Number of valid footprints = "+str(n))

        if smooth_data is not None:
            skernel = numpy.matrix('0.05 0.1 0.05; 0.1 0.4 0.1; 0.05 0.1 0.05')
            fclim_2d = sg.convolve2d(fclim_2d, skernel, mode='same');
            fclim_2d = sg.convolve2d(fclim_2d, skernel, mode='same');

    # Finally print the stats for exception messages, fatal exceptions already resulted in aborting program
    raise_fkm_exception(0, verbosity, counter, msgstring)

    return {'x_2d': x_2d, 'y_2d': y_2d, 'fclim_2d': fclim_2d, 'n': n, 'flag_err': flag_err}


# ===============================================================================
def KorMeix0(x, y, alpha, A, B, C, D, E):
    import numpy
    import constants as c

    x_ = x * numpy.cos(alpha) + y * numpy.sin(alpha)
    y_ = -x * numpy.sin(alpha) + y * numpy.cos(alpha)

    if x_ <= 0:
        KorMeix = 0
    else:
        sigma = D * x_ ** E
        F = C * numpy.exp(-B / x_) * x_ ** (-A)
        Dy = 1 / numpy.sqrt(2 * c.Pi) / sigma * numpy.exp(-y_ ** 2 / 2 / sigma ** 2)
        Phimaj = Dy * F
        KorMeix = Phimaj
    return KorMeix


def EllipseZero(flag, level, xPhiMax, phimax, A, B, C, D, E):
    """
    Delivers x value of phi where phi(x,0)=level, flag=true for x>xPhimax, flag=false for x<xPhimax
    Starting point for determining the x values: either at xPhiMax/3 or xPhiMax*3
    """
    import numpy
    import constants as c
    if flag:
        x0 = xPhiMax * 3
    else:
        x0 = xPhiMax / 3

    p = level * phimax

    for i in [1, 2, 3, 4, 5]:
        Fm = C * numpy.exp(-B / x0) * x0 ** (-A) - numpy.sqrt(2 * c.Pi) * p * (D * x0 ** E)
        dFm = (C * numpy.exp(-B / x0) * x0 ** (-A)) / x0 ** 2 * -(A * x0 - B) - p * numpy.sqrt(2 * c.Pi) * (
                    D * x0 ** E) * E / x0
        x0 = x0 - Fm / dFm

    EllipseZero = x0
    return EllipseZero


def EllipseMax(x0, level, xPhiMax, phimax, A, B, C, D, E, mu, xi):
    """
    delivers y for which phi(xcenter,y)=level, i.e. "width of ellipse"
    ellipse parameter d: short axes of ellipse
    """
    import numpy
    import constants as c
    p = level * phimax
    y = D * x0 ** E * numpy.sqrt(2) * numpy.sqrt(
        numpy.log(C * numpy.exp(-B / x0) / numpy.sqrt(2 * c.Pi) / x0 ** (A + E) / D / p))
    Gm = (1 - y ** 2 / D ** 2 / x0 ** (2 * E)) * E / x0 - xi / x0 ** 2 + (1 + mu) / x0
    dGm = 2 * (y ** 2 * E ** 2) / D ** 2 / x0 ** (2 * E + 2) - (
                1 - y ** 2 / D ** 2 / x0 ** (2 * E)) * E / x0 ** 2 + 2 * xi / x0 ** 3 + (1 + mu) / x0 ** 2

    for i in [1, 2, 3, 4, 5]:
        x0 = x0 - Gm / dGm

    ye = D * x0 ** E * numpy.sqrt(2) * numpy.sqrt(
        numpy.log(C * numpy.exp(-B / x0) / numpy.sqrt(2 * c.Pi) / x0 ** (A + E) / D / (level * phimax)))
    EllipseMax = ye

    return EllipseMax


# ===============================================================================
def check_fkm_inputs(ustar, sigmav, ol, wind_dir, zm, z0, umean, rslayer, verbosity, counter, msgstring):
    # Check passed values for physical plausibility and consistency
    if zm <= 0.:
        raise_fkm_exception(2, verbosity, counter, msgstring)
        return False
    if z0 <= 0.:
        raise_fkm_exception(3, verbosity, counter, msgstring)
        return False
    if float(zm) / ol < -3:
        raise_fkm_exception(7, verbosity, counter, msgstring)
        return False
    if float(zm) / ol > 3:
        raise_fkm_exception(7, verbosity, counter, msgstring)
        return False
    if sigmav <= 0:
        raise_fkm_exception(8, verbosity, counter, msgstring)
        return False
    if ustar <= 0.1:
        raise_fkm_exception(9, verbosity, counter, msgstring)
        return False
    if umean <= 0.0:
        raise_fkm_exception(21, verbosity, counter, msgstring)
        return False
    if wind_dir > 360:
        raise_fkm_exception(10, verbosity, counter, msgstring)
        return False
    if wind_dir < 0:
        raise_fkm_exception(10, verbosity, counter, msgstring)
        return False
    return True


# ===============================================================================
exTypes = {'message': 'Message',
           'alert': 'Alert',
           'error': 'Error',
           'fatal': 'Fatal error'}

exceptions = [
    {'code': 1,
     'type': exTypes['fatal'],
     'msg': 'At least one required parameter is missing. Please enter all '
            'required inputs. Check documentation for details.'},
    {'code': 2,
     'type': exTypes['error'],
     'msg': 'zm (measurement height) must be larger than zero.'},
    {'code': 3,
     'type': exTypes['error'],
     'msg': 'z0 (roughness length) must be larger than zero.'},
    {'code': 4,
     'type': exTypes['error'],
     'msg': 'h (ABL height) must be larger than 10 m.'},
    {'code': 5,
     'type': exTypes['error'],
     'msg': 'zm (measurement height) must be smaller than h (PBL height).'},
    {'code': 6,
     'type': exTypes['alert'],
     'msg': 'zm (measurement height) should be above roughness sub-layer (12.5*z0).'},
    {'code': 7,
     'type': exTypes['error'],
     'msg': 'zm/ol (measurement height to Obukhov length ratio) must be equal or larger than -15.5.'},
    {'code': 8,
     'type': exTypes['error'],
     'msg': 'sigmav (standard deviation of crosswind) must be larger than zero.'},
    {'code': 9,
     'type': exTypes['error'],
     'msg': 'ustar (friction velocity) must be >=0.1.'},
    {'code': 10,
     'type': exTypes['error'],
     'msg': 'wind_dir (wind direction) must be >=0 and <=360.'},
    {'code': 11,
     'type': exTypes['fatal'],
     'msg': 'Passed data arrays (ustar, zm, h, ol) don\'t all have the same length.'},
    {'code': 12,
     'type': exTypes['fatal'],
     'msg': 'No valid zm (measurement height above displacement height) passed.'},
    {'code': 13,
     'type': exTypes['alert'],
     'msg': 'Using z0, ignoring umean if passed.'},
    {'code': 14,
     'type': exTypes['alert'],
     'msg': 'No valid z0 passed, using umean.'},
    {'code': 15,
     'type': exTypes['fatal'],
     'msg': 'No valid z0 or umean array passed.'},
    {'code': 16,
     'type': exTypes['error'],
     'msg': 'At least one required input is invalid. Skipping current footprint.'},
    {'code': 17,
     'type': exTypes['alert'],
     'msg': 'Only one value of zm passed. Using it for all footprints.'},
    {'code': 18,
     'type': exTypes['fatal'],
     'msg': 'if provided, rs must be in the form of a number or a list of numbers.'},
    {'code': 19,
     'type': exTypes['alert'],
     'msg': 'rs value(s) larger than 90% were found and eliminated.'},
    {'code': 20,
     'type': exTypes['error'],
     'msg': 'zm (measurement height) must be above roughness sub-layer (12.5*z0).'},
    {'code': 21,
     'type': exTypes['error'],
     'msg': 'umean (mean wind speed) must be >=0.0.'},
]


def raise_fkm_exception(code, verbosity, counter, msgstring):
    '''Raise exception or prints message according to specified code'''

    icode = int(code)
    if icode > 0:
        if counter[icode] == None:
            counter[icode] = 1
        else:
            counter[icode] = counter[icode] + 1
        ex = [it for it in exceptions if it['code'] == code][0]
        msgstring[icode] = ex['type'] + '(' + str(ex['code']).zfill(4) + '):\n ' + ex['msg']
        # if verbosity > 0: print('')
        if ex['type'] == exTypes['fatal']:
            if verbosity > 0:
                msgstring[icode] = msgstring[icode] + '\n FKM_fixed_domain execution aborted.'
            else:
                msgstring[icode] = ''
            raise Exception(msgstring[icode])
        elif ex['type'] == exTypes['alert']:
            msgstring[icode] = msgstring[icode]  # + '\n Execution continues.'
            if verbosity > 1:
                pass
        elif ex['type'] == exTypes['error']:
            msgstring[icode] = msgstring[icode]  # + '\n Execution continues.'
            if verbosity > 1:
                pass
        else:
            if verbosity > 1:
                pass
    elif icode == 0:
        for iicode in range(1, len(counter)):
            # printout the final stats for exception messages
            if not counter[iicode] == None:
                # print message as logger info
                logger.warning(str(counter[iicode]) + ' times ' + msgstring[iicode])

# ================================================================

