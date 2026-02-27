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
    logger.info(' Read input data files from:')
    if mode in ("kljun_L3", "kormei_L3"):
        ds , fpinfo = get_footprint_L3_data_in(cf, fpinfo, mode)
        logger.info('Level 3 PyFluxPro processed netcdf data file')
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
    if list_StDate == [] or list_EnDate == []:
        logger.error("No start or end date found.")
    else:
        logger.info(list_StDate)
        logger.info(list_EnDate)

    logger.info(' Preparing footprint climatology calculation ...')
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
    logger.info("output file created.")
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
        logger.info('KML file initialised. ')

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
                msg = "Calculated cumulative footprint field"
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
    logger.info(f"Climatology set to calculate {fpinfo["Climatology"]}")
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

    return ds , fpinfo


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

