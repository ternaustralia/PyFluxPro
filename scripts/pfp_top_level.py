# standard modules
import logging
import os
import traceback
# 3rd party modules
import netCDF4
import matplotlib
from PyQt5 import QtWidgets
# PFP modules
from scripts import pfp_batch
from scripts import pfp_clim
from scripts import pfp_compliance
from scripts import pfp_cpd_barr
from scripts import pfp_cpd_mchugh
from scripts import pfp_cpd_mcnew
from scripts import pfp_mpt
from scripts import pfp_io
from scripts import pfp_levels
from scripts import pfp_plot
from scripts import pfp_utils
from scripts import split_dialog
from scripts import pfp_footprint

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

# top level routines for the File menu
def do_file_concatenate(cfg):
    """
    Purpose:
     Top level routine for concatenating multiple, single-year files into
     a single, multiple-year file.
     NOTE: The input files must be listed in the control file in chronological
           order.
    Usage:
     pfp_top_level.do_file_concatenate()
    Side effects:
     Creates a single netCDF file containing the contents of the input files.
    Author: PRI
    Date: Back in the day
    Mods:
     June 2018: rewrite for use with new GUI.
    """
    logger.info(" Starting concatenation of netCDF files")
    try:
        info = pfp_compliance.ParseConcatenateControlFile(cfg)
        if not info["NetCDFConcatenate"]["OK"]:
            msg = " An error occurred when parsing the control file"
            logger.error(msg)
            return
        pfp_io.NetCDFConcatenate(info)
        logger.info(" Finished concatenating files")
        logger.info("")
    except Exception:
        error_message = " Error concatenating netCDF files, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2biomet(cfg, mode="standard"):
    """
    Purpose:
     Convert a PFP-style netCDF file to an EddyPro biomet CSV file.
    Usage:
    Side effects:
     Creates a CSV file in the same directory as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     March 2020: rewrite for use with new GUI
     April 2020: routine can be invoked from File/Convert menu or
                 by loading control file and using Run/Current.
                 The latter method allows the user to modify the
                 control file before running it.
    """
    logger.info(" Starting conversion to EddyPro biomet file")
    try:
        # check to see if the user chose a standard or a custom run
        if cfg is None and mode == "standard":
            # standard run so we use the control file in PyFluxPro/controlfiles/standard
            # get the base path of script or Pyinstaller application
            base_path = pfp_utils.get_base_path()
            stdname = os.path.join(base_path, "controlfiles", "standard", "nc2csv_biomet.txt")
            # check to see if the standard control file exists
            if os.path.exists(stdname):
                # standard control file exists so read it
                cfg = pfp_io.get_controlfilecontents(stdname)
                # then ask the user to choose a netCDF file
                filename = pfp_io.get_filename_dialog(file_path=".", title='Choose a netCDF file')
                # check that the netCDF file exists
                if not os.path.exists(filename):
                    # return if no file chosen
                    logger.info( " Write biomet CSV file: no input file chosen")
                    return
                # add a [Files] section to the control file ...
                if "Files" not in cfg:
                    cfg["Files"] = {}
                # ... and put the file path, input file name and output file name in [Files]
                cfg["Files"]["file_path"] = os.path.join(os.path.split(filename)[0], "")
                in_filename = os.path.split(filename)[1]
                cfg["Files"]["in_filename"] = in_filename
                cfg["Files"]["out_filename"] = in_filename.replace(".nc", "_biomet.csv")
            else:
                # issue an error mesage and return if the standard control file does not exist
                msg = " Write biomet CSV file: standard control file 'nc2csv_biomet.txt' does not exist"
                logger.error(msg)
                return
        elif cfg is not None and mode == "custom":
            # custom run so we proceed with the user's control file
            pass
        else:
            # tell the user we got the wrong input options and return
            msg = " Write biomet CSV file: wrong input options"
            logger.error(msg)
            return
        # add the [Options] section and populate it
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        # do the business
        result = pfp_io.write_csv_ep_biomet(cfg)
        # check everything went well
        if result == 1:
            # looks good
            logger.info(" Finished converting netCDF file")
            logger.info("")
        else:
            # or not
            logger.error("")
            logger.error(" An error occurred, check the log messages")
            logger.error("")
    except Exception:
        # tell the user if something goes wrong and put the exception in the log window
        error_message = " Error converting to BIOMET format, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2oneflux(cfg, mode="standard"):
    """
    Purpose:
     Convert a PFP-style netCDF file to ONEFlux CSV files, one CSV file per year.
    Usage:
    Side effects:
     Creates a CSV file in the same directory as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     March 2020: rewrite for use with new GUI
     April 2020: routine can be invoked from File/Convert menu or
                 by loading control file and using Run/Current.
                 The latter method allows the user to modify the
                 control file before running it.
    """
    logger.info(" Starting conversion to ONEFlux CSV files")
    try:
        # check to see if the user chose a standard or a custom run
        if cfg is None and mode == "standard":
            # standard run so we use the control file in PyFluxPro/controlfiles/standard
            # get the base path of script or Pyinstaller application
            base_path = pfp_utils.get_base_path()
            stdname = os.path.join(base_path, "controlfiles", "standard", "nc2csv_oneflux.txt")
            # check to see if the standard control file exists
            if os.path.exists(stdname):
                # standard control file exists so read it
                cfg = pfp_io.get_controlfilecontents(stdname)
                # then ask the user to choose a netCDF file
                filename = pfp_io.get_filename_dialog(file_path=".", title='Choose a netCDF file')
                # check that the netCDF file exists
                if not os.path.exists(filename):
                    # return if no file chosen
                    logger.info( " Write ONEFlux CSV file: no input file chosen")
                    return
                # add a [Files] section to the control file ...
                if "Files" not in cfg:
                    cfg["Files"] = {}
                # ... and put the file path, input file name and output file name in [Files]
                cfg["Files"]["file_path"] = os.path.join(os.path.split(filename)[0], "")
                in_filename = os.path.split(filename)[1]
                cfg["Files"]["in_filename"] = in_filename
                cfg["Files"]["out_filename"] = in_filename.replace(".nc", "_oneflux.csv")
            else:
                # issue an error mesage and return if the standard control file does not exist
                msg = " Write ONEFlux CSV file: standard control file 'nc2csv_oneflux.txt' does not exist"
                logger.error(msg)
                return
        elif cfg is not None and mode == "custom":
            # custom run so we proceed with the user's control file
            pass
        else:
            # tell the user we got the wrong input options and return
            msg = " Write ONEFlux CSV file: wrong input options"
            logger.error(msg)
            return
        # add the [Options] section and populate it
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        # do the business
        result = pfp_io.write_csv_oneflux(cfg)
        # check everything went well
        if result:
            # looks good
            logger.info(" Finished converting netCDF file")
            logger.info("")
        else:
            # or not
            logger.error("")
            logger.error(" An error occurred, check the log messages")
            logger.error("")
    except Exception:
        # tell the user if something goes wrong and put the exception in the log window
        error_message = " Error converting to ONEFlux format, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2reddyproc(cfg, mode="standard"):
    """
    Purpose:
     Convert a PFP-style netCDF file to an REddyProc CSV file.
    Usage:
    Side effects:
     Creates a TSV (tab separated values) file in the same directory
     as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     March 2020: rewrite for use with new GUI
     April 2020: routine can be invoked from File/Convert menu or
                 by loading control file and using Run/Current.
                 The latter method allows the user to modify the
                 control file before running it.
    """
    logger.info(" Starting output of REddyProc file")
    try:
        # check to see if the user chose a standard or a custom run
        if cfg is None and mode == "standard":
            # standard run so we use the control file in PyFluxPro/controlfiles/standard
            # get the base path of script or Pyinstaller application
            base_path = pfp_utils.get_base_path()
            stdname = os.path.join(base_path, "controlfiles", "standard", "nc2tsv_reddyproc.txt")
            # check to see if the standard control file exists
            if os.path.exists(stdname):
                # standard control file exists so read it
                cfg = pfp_io.get_controlfilecontents(stdname)
                # then ask the user to choose a netCDF file
                filename = pfp_io.get_filename_dialog(file_path=".", title='Choose a netCDF file')
                # check that the netCDF file exists
                if not os.path.exists(filename):
                    # return if no file chosen
                    logger.info( " Write REddyProc file: no input file chosen")
                    return
                # add a [Files] section to the control file ...
                if "Files" not in cfg:
                    cfg["Files"] = {}
                # ... and put the file path, input file name and output file name in [Files]
                cfg["Files"]["file_path"] = os.path.join(os.path.split(filename)[0], "")
                in_filename = os.path.split(filename)[1]
                cfg["Files"]["in_filename"] = in_filename
                cfg["Files"]["out_filename"] = in_filename.replace(".nc", "_REddyProc.tsv")
            else:
                # issue an error mesage and return if the standard control file does not exist
                msg = " Write REddyProc file: standard control file 'nc2tsv_reddyproc.txt' does not exist"
                logger.error(msg)
                return
        elif cfg is not None and mode == "custom":
            # custom run so we proceed with the user's control file
            pass
        else:
            # tell the user we got the wrong input options and return
            msg = " Write REddyProc file: wrong input options"
            logger.error(msg)
            return
        # add the [Options] section and populate it
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        # do the business
        result = pfp_io.write_tsv_reddyproc(cfg)
        # check everything went well
        if result == 1:
            # looks good
            msg = " Finished writing REddyProc file " + cfg["Files"]["out_filename"]
            logger.info(msg)
            logger.info("")
        else:
            # or not
            logger.error("")
            logger.error(" An error occurred, check the log messages")
            logger.error("")
    except Exception:
        # tell the user if something goes wrong and put the exception in the log window
        error_message = " Error writing REddyProc file, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2ecostress(cfg):
    """
    Purpose:
     Convert a PFP-style netCDF file to an ECOSTRESS CSV file.
    Usage:
    Side effects:
     Creates a CSV file in the same directory as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     September 2018: rewrite for use with new GUI
     April 2020: routine can be invoked from File/Convert menu or
                 by loading control file and using Run/Current.
                 The latter method allows the user to modify the
                 control file before running it.
    """
    logger.info(" Starting conversion to ECOSTRESS file")
    try:
        if "Options" not in cfg:
            cfg["Options"]={}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        result = pfp_io.write_csv_ecostress(cfg)
        if result == 1:
            logger.info(" Finished converting netCDF file")
            logger.info("")
        else:
            logger.error("")
            logger.error(" An error occurred, check the log messages")
            logger.error("")
    except Exception:
        error_message = " Error converting to ECOSTRESS format, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2xls():
    """
    Purpose:
     Convert a PFP-style netCDF file to an Excel workbook.
    Usage:
    Side effects:
     Creates an Excel workbook in the same directory as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     August 2018: rewrite for use with new GUI
    """
    logger.info(" Starting conversion to Excel file")
    try:
        ncfilename = pfp_io.get_filename_dialog(file_path="../Sites", title="Choose a netCDF file", ext="*.nc")
        if len(ncfilename) == 0:
            logger.info(" No file selected, cancelling ...")
            return
        logger.info(" Converting netCDF file to Excel file")
        pfp_io.nc_2xls(ncfilename, outputlist=None)
        logger.info(" Finished converting netCDF file")
        logger.info("")
    except Exception:
        msg = " Error converting to Excel file, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_convert_nc2fluxnet(cfg):
    """
    Purpose:
     Convert a PFP-style netCDF file to a FluxNet CSV file.
    Usage:
    Side effects:
     Creates a CSV file in the same directory as the netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     September 2018: rewrite for use with new GUI
     April 2020: routine can be invoked from File/Convert menu or
                 by loading control file and using Run/Current.
                 The latter method allows the user to modify the
                 control file before running it.
    """
    logger.info(" Starting output of FluxNet CSV file")
    try:
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        result = pfp_io.write_csv_fluxnet(cfg)
        if result == 1:
            logger.info(" Finished converting netCDF file")
            logger.info("")
        else:
            logger.error("")
            logger.error(" An error occurred, check the log messages")
            logger.error("")
    except Exception:
        error_message = " Error converting to ECOSTRESS format, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_file_split():
    Dialog = QtWidgets.QDialog()
    ui = split_dialog.Ui_Dialog()
    ui.setupUi(Dialog)
    ui.pushButton_InputFileName.clicked.connect(lambda:do_file_split_browse_input_filename(ui))
    ui.pushButton_OutputFileName.clicked.connect(lambda:do_file_split_browse_output_filename(ui))
    ui.pushButton_Run.clicked.connect(lambda:do_file_split_run(ui))
    ui.pushButton_Quit.clicked.connect(lambda:do_file_split_quit(ui))
    ui.info = {}
    ui.Dialog = Dialog
    Dialog.show()
    Dialog.exec_()
def do_file_split_browse_input_filename(ui):
    input_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...", filter="*.nc")[0]
    input_file_path = str(input_file_path)
    ui.info["input_file_path"] = input_file_path
    ui.lineEdit_InputFileName.setText(os.path.basename(input_file_path))
    ncfile = netCDF4.Dataset(input_file_path, 'r')
    gattrs = ncfile.ncattrs()
    for item in ["start_date", "start_datetime", "time_coverage_start"]:
        if item in gattrs:
            ui.label_FileStartDate_value.setText(ncfile.getncattr(item))
    for item in ["end_date", "end_datetime", "time_coverage_end"]:
        if item in gattrs:
            ui.label_FileEndDate_value.setText(ncfile.getncattr(item))
    ncfile.close()
def do_file_split_browse_output_filename(ui):
    if "input_file_path" in ui.info:
        file_path = os.path.split(ui.info["input_file_path"])[0]
    else:
        file_path = "."
    output_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                         directory=file_path, filter="*.nc")[0]
    output_file_path = str(output_file_path)
    ui.info["output_file_path"] = output_file_path
    ui.lineEdit_OutputFileName.setText(os.path.basename(output_file_path))
def do_file_split_quit(ui):
    ui.Dialog.close()
def do_file_split_run(ui):
    ui.info["startdate"] = str(ui.lineEdit_StartDate.text())
    ui.info["enddate"] = str(ui.lineEdit_EndDate.text())
    if "output_file_path" not in ui.info:
        file_path = os.path.split(ui.info["input_file_path"])[0]
        file_name = str(ui.lineEdit_OutputFileName.text())
        ui.info["output_file_path"] = os.path.join(file_path, file_name)
    try:
        pfp_io.ncsplit_run(ui)
    except Exception:
        msg = " Error splitting netCDF file, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
# top level routines for the Run menu
def do_run_batch(self):
    """
    Purpose:
     Top level routine for running the batch processing.
    Usage:
     pfp_top_level.do_run_batch(cfg)
     where cfg is a batch control exist
    Side effects:
     Creates netCDF files and plots as required.
    Author: PRI
    Date: September 2020
    """
    try:
        if self.file["level"] in ["batch", "batch_levels"]:
            pfp_batch.do_levels_batch(self)
        elif self.file["level"] in ["batch_sites"]:
            pfp_batch.do_sites_batch(self)
        else:
            msg = " Unrecognised batch type: " + str(self.file["level"])
            logger.error(msg)
    except Exception:
        msg = " Error running batch processing, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    self.actionStopCurrent.disconnect()
    self.menuRun.removeAction(self.actionStopCurrent)
    self.actionRunCurrent.setDisabled(False)
    return
def do_run_l1(cfg):
    """
    Purpose:
     Top level routine for running the L1 data import.
    Usage:
     pfp_top_level.do_l1()
    Side effects:
     Creates an L1 netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L1 processing")
        # add the [Options] section and populate it
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        ds1 = pfp_levels.l1qc(cfg)
        if ds1.info["returncodes"]["value"] == 0:
            outfilename = pfp_io.get_outfilenamefromcf(cfg)
            pfp_io.NetCDFWrite(outfilename, ds1)
            logger.info("Finished L1 processing")
        else:
            msg = "An error occurred during L1 processing"
            logger.error(msg)
        logger.info("")
    except Exception:
        msg = " Error running L1, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_run_l2(cfg):
    """
    Purpose:
     Top level routine for running the L2 quality control.
    Usage:
     pfp_top_level.do_l2()
    Side effects:
     Creates an L2 netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L2 processing")
        in_filepath = pfp_io.get_infilenamefromcf(cfg)
        if not pfp_utils.file_exists(in_filepath):
            in_filename = os.path.split(in_filepath)
            logger.error("File "+in_filename[1]+" not found")
            return
        ds1 = pfp_io.NetCDFRead(in_filepath)
        if ds1.info["returncodes"]["value"] != 0:
            return
        pfp_compliance.check_l2_options(cfg, ds1)
        if ds1.info["returncodes"]["value"] != 0:
            return
        ds2 = pfp_levels.l2qc(cfg, ds1)
        if ds2.info["returncodes"]["value"] != 0:
            logger.error("An error occurred during L2 processing")
            logger.error("")
            return
        outfilename = pfp_io.get_outfilenamefromcf(cfg)
        pfp_io.NetCDFWrite(outfilename, ds2)
        logger.info("Finished L2 processing")
        if "Plots" in list(cfg.keys()):
            logger.info("Plotting L1 and L2 data")
            for nFig in cfg['Plots'].keys():
                if "(disabled)" in nFig:
                    continue
                plt_cf = cfg['Plots'][str(nFig)]
                if 'type' in plt_cf.keys():
                    if str(plt_cf['type']).lower() == 'xy':
                        pfp_plot.plotxy(cfg, nFig, plt_cf, ds1, ds2)
                    else:
                        pfp_plot.plottimeseries(cfg, nFig, ds1, ds2)
                else:
                    pfp_plot.plottimeseries(cfg, nFig, ds1, ds2)
            logger.info("Finished plotting L1 and L2 data")
    except Exception:
        msg = " Error running L2, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    logger.info("")
    return
def do_run_l3(cfg):
    """
    Purpose:
     Top level routine for running the L23 post-processing.
    Usage:
     pfp_top_level.do_l3()
    Side effects:
     Creates an L3 netCDF file.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L3 processing")
        in_filepath = pfp_io.get_infilenamefromcf(cfg)
        ds2 = pfp_io.NetCDFRead(in_filepath)
        if ds2.info["returncodes"]["value"] != 0:
            return
        cfg["Options"]["call_mode"] = "interactive"
        ds3 = pfp_levels.l3qc(cfg, ds2)
        if ds3.info["returncodes"]["value"] != 0:
            logger.error("An error occurred during L3 processing")
            logger.error("")
            return
        outfilename = pfp_io.get_outfilenamefromcf(cfg)
        pfp_io.NetCDFWrite(outfilename, ds3)
        logger.info("Finished L3 processing")
        if "Plots" in list(cfg.keys()):
            logger.info("Plotting L3 data")
            for nFig in cfg['Plots'].keys():
                if "(disabled)" in nFig:
                    continue
                plt_cf = cfg['Plots'][str(nFig)]
                if 'Type' in plt_cf.keys():
                    if str(plt_cf['Type']).lower() =='xy':
                        pfp_plot.plotxy(cfg, nFig, plt_cf, ds2, ds3)
                    else:
                        pfp_plot.plottimeseries(cfg, nFig, ds2, ds3)
                else:
                    pfp_plot.plottimeseries(cfg, nFig, ds2, ds3)
            logger.info("Finished plotting L3 data")
    except Exception:
        msg = " Error running L3, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    logger.info("")
    return
def do_run_l4(main_gui):
    """
    Purpose:
     Top level routine for running the L4 gap filling.
    Usage:
     pfp_top_level.do_run_l4()
    Side effects:
     Creates an L4 netCDF file with gap filled meteorology.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L4 processing")
        tab_index_running = main_gui.tabs.tab_index_running
        cfg = main_gui.tabs.tab_dict[tab_index_running].get_data_from_model()
        in_filepath = pfp_io.get_infilenamefromcf(cfg)
        if not pfp_utils.file_exists(in_filepath):
            in_filename = os.path.split(in_filepath)
            logger.error("File "+in_filename[1]+" not found")
            return
        ds3 = pfp_io.NetCDFRead(in_filepath)
        if ds3.info["returncodes"]["value"] != 0: return
        sitename = ds3.root["Attributes"]['site_name']
        if "Options" not in cfg:
            cfg["Options"]={}
        cfg["Options"]["call_mode"] = "interactive"
        ds4 = pfp_levels.l4qc(main_gui, cfg, ds3)
        if ds4.info["returncodes"]["value"] != 0:
            logger.info("Quitting L4: " + sitename)
        else:
            logger.info("Finished L4: " + sitename)
            outfilename = pfp_io.get_outfilenamefromcf(cfg)
            pfp_io.NetCDFWrite(outfilename, ds4)
            logger.info("Finished saving L4 gap filled data")
        logger.info("")
    except Exception:
        msg = " Error running L4, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_run_l5(main_gui):
    """
    Purpose:
     Top level routine for running the L5 gap filling.
    Usage:
     pfp_top_level.do_run_l5()
    Side effects:
     Creates an L5 netCDF file with gap filled meteorology.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L5 processing")
        tab_index_running = main_gui.tabs.tab_index_running
        cfg = main_gui.tabs.tab_dict[tab_index_running].get_data_from_model()
        in_filepath = pfp_io.get_infilenamefromcf(cfg)
        if not pfp_utils.file_exists(in_filepath):
            in_filename = os.path.split(in_filepath)
            logger.error("File "+in_filename[1]+" not found")
            return
        ds4 = pfp_io.NetCDFRead(in_filepath)
        if ds4.info["returncodes"]["value"] != 0: return
        sitename = ds4.root["Attributes"]['site_name']
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        ds5 = pfp_levels.l5qc(main_gui, cfg, ds4)
        # check to see if all went well
        if ds5.info["returncodes"]["value"] != 0:
            # tell the user something went wrong
            logger.info("Quitting L5: "+sitename)
            # delete the output file if it exists
            out_filepath = pfp_io.get_outfilenamefromcf(cfg)
            if os.path.isfile(out_filepath):
                os.remove(out_filepath)
        else:
            # tell the user we are finished
            logger.info("Finished L5: "+sitename)
            # get the output file name from the control file
            outfilename = pfp_io.get_outfilenamefromcf(cfg)
            pfp_io.NetCDFWrite(outfilename, ds5)
            logger.info("Finished saving L5 gap filled data")
        logger.info("")
    except Exception:
        msg = " Error running L5, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_run_l6(main_gui):
    """
    Purpose:
     Top level routine for running the L6 gap filling.
    Usage:
     pfp_top_level.do_run_l6()
    Side effects:
     Creates an L6 netCDF file with NEE partitioned into GPP and ER.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting L6 processing")
        tab_index_running = main_gui.tabs.tab_index_running
        cfg = main_gui.tabs.tab_dict[tab_index_running].get_data_from_model()
        in_filepath = pfp_io.get_infilenamefromcf(cfg)
        if not pfp_utils.file_exists(in_filepath):
            in_filename = os.path.split(in_filepath)
            logger.error("File "+in_filename[1]+" not found")
            return
        ds5 = pfp_io.NetCDFRead(in_filepath)
        if ds5.info["returncodes"]["value"] != 0: return
        sitename = ds5.root["Attributes"]['site_name']
        if "Options" not in cfg:
            cfg["Options"] = {}
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        ds6 = pfp_levels.l6qc(main_gui, cfg, ds5)
        if ds6.info["returncodes"]["value"] != 0:
            logger.info("Quitting L6: "+sitename)
        else:
            logger.info("Finished L6: "+sitename)
            outfilename = pfp_io.get_outfilenamefromcf(cfg)
            pfp_io.NetCDFWrite(outfilename, ds6)
            logger.info("Finished saving L6 partitioned data")
        logger.info("")
    except Exception:
        msg = " Error running L6, see below for details ..."
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
# top level routines for the Plot menu
def do_plot_fcvsustar_annual():
    """
    Purpose:
     Plot Fc versus u* for each year.
    Usage:
     pfp_top_level.do_plot_fcvsustar_annual()
    Side effects:
     Annual plots of Fc versus u* to the screen and creates .PNG
     hardcopies of the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    logger.info("Starting annual Fc versus u* plots")
    try:
        file_path = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
        if len(file_path) == 0 or not os.path.isfile(file_path):
            return
        # read the netCDF file
        ds = pfp_io.NetCDFRead(file_path)
        if ds.info["returncodes"]["value"] != 0: return
        logger.info("Plotting Fc versus u* ...")
        pfp_plot.plot_fcvsustar_annual(ds)
        logger.info(" Finished plotting Fc versus u*")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting Fc versus u*, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_fcvsustar_seasonal():
    """
    Purpose:
     Plot Fc versus u* for each season for each year.
    Usage:
     pfp_top_level.do_plot_fcvsustar_seasonal()
    Side effects:
     Seasonal plots of Fc versus u* to the screen and creates .PNG
     hardcopies of the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    logger.info("Starting seasonal Fc versus u* plots")
    try:
        file_path = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
        if len(file_path) == 0 or not os.path.isfile(file_path):
            return
        # read the netCDF file
        ds = pfp_io.NetCDFRead(file_path)
        if ds.info["returncodes"]["value"] != 0: return
        logger.info("Plotting Fc versus u* ...")
        pfp_plot.plot_fcvsustar_seasonal(ds)
        logger.info(" Finished plotting Fc versus u*")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting Fc versus u*, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_fcvsustar_monthly():
    """
    Purpose:
     Plot Fc versus u* for each month for each year.
    Usage:
     pfp_top_level.do_plot_fcvsustar_monthly()
    Side effects:
     Monthly plots of Fc versus u* to the screen and creates .PNG
     hardcopies of the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    logger.info("Starting monthly Fc versus u* plots")
    try:
        file_path = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
        if len(file_path) == 0 or not os.path.isfile(file_path):
            return
        # read the netCDF file
        ds = pfp_io.NetCDFRead(file_path)
        if ds.info["returncodes"]["value"] != 0: return
        logger.info("Plotting Fc versus u* ...")
        pfp_plot.plot_fcvsustar_monthly(ds)
        logger.info(" Finished plotting Fc versus u*")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting Fc versus u*, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_fingerprints():
    """
    Purpose:
     Plot fingerprints using the standard fingerprint control file.
    Usage:
     pfp_top_level.do_plot_fingerprints()
    Side effects:
     Plots fingerprints to the screen and creates .PNG hardcopies of
     the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    logger.info("Starting fingerprint plot")
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "fingerprint.txt")
        if os.path.exists(stdname):
            cf = pfp_io.get_controlfilecontents(stdname)
            filename = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
            if len(filename)==0:
                return
            if "Files" not in dir(cf): cf["Files"] = {}
            cf["Files"]["file_path"] = os.path.split(filename)[0]+"/"
            cf["Files"]["in_filename"] = os.path.split(filename)[1]
        else:
            cf = pfp_io.load_controlfile(path="controlfiles")
            if len(cf) == 0:
                return
        logger.info("Loaded control file ...")
        if "Options" not in cf:
            cf["Options"]={}
        cf["Options"]["call_mode"] = "interactive"
        cf["Options"]["show_plots"] = "Yes"
        logger.info("Plotting fingerprint ...")
        pfp_plot.plot_fingerprint(cf)
        logger.info(" Finished plotting fingerprint")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting fingerprints, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_quickcheck():
    """
    Purpose:
     Plot summaries of data, usually L3 and above.
    Usage:
     pfp_top_level.do_plot_quickcheck()
    Side effects:
     Plots summaries to the screen and creates .PNG hardcopies of
     the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting summary plots")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "quickcheck.txt")
        if os.path.exists(stdname):
            cf = pfp_io.get_controlfilecontents(stdname)
            filename = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
            if len(filename)==0:
                return
            if "Files" not in dir(cf): cf["Files"] = {}
            cf["Files"]["file_path"] = os.path.split(filename)[0]+"/"
            cf["Files"]["in_filename"] = os.path.split(filename)[1]
        else:
            cf = pfp_io.load_controlfile(path="controlfiles")
            if len(cf)==0:
                return
        logger.info("Loaded control file ...")
        if "Options" not in cf:
            cf["Options"]={}
        cf["Options"]["call_mode"] = "interactive"
        cf["Options"]["show_plots"] = "Yes"
        logger.info("Plotting summary plots ...")
        pfp_plot.plot_quickcheck(cf)
        logger.info(" Finished plotting summaries")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting quickcheck, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_timeseries():
    """
    Purpose:
     Plot time series of data, usually L3 and above.
    Usage:
     pfp_top_level.do_plot_timeseries()
    Side effects:
     Plots timeseries to the screen and creates .PNG hardcopies of
     the plots.
    Author: PRI
    Date: Back in the day
    Mods:
     December 2017: rewrite for use with new GUI
    """
    try:
        logger.info("Starting timeseries plot")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "fluxnet.txt")
        if os.path.exists(stdname):
            cf = pfp_io.get_controlfilecontents(stdname)
            filename = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
            if len(filename)==0:
                return
            if "Files" not in dir(cf): cf["Files"] = {}
            cf["Files"]["file_path"] = os.path.split(filename)[0]+"/"
            cf["Files"]["in_filename"] = os.path.split(filename)[1]
        else:
            cf = pfp_io.load_controlfile(path="controlfiles")
            if len(cf)==0:
                return
        logger.info("Loaded control file ...")
        if "Options" not in cf:
            cf["Options"]={}
        cf["Options"]["call_mode"] = "interactive"
        cf["Options"]["show_plots"] = "Yes"
        logger.info("Plotting time series ...")
        pfp_plot.plot_fluxnet(cf)
        logger.info(" Finished plotting time series")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting time series, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_windrose_standard():
    """
    Purpose:
     Plot windroses.
    Usage:
     pfp_top_level.do_plot_windrose()
    Side effects:
     Plots windroses to the screen and creates .PNG hardcopies of
     the plots.
    Author: PRI/CE
    Date: May 2022
    Mods:
    """
    try:
        logger.info("Starting windroses plot")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "windrose.txt")
        if os.path.exists(stdname):
            cf = pfp_io.get_controlfilecontents(stdname)
            filename = pfp_io.get_filename_dialog(file_path="../Sites",title="Choose a netCDF file")
            if len(filename) == 0:
                return
            if "Files" not in dir(cf):
                cf["Files"] = {}
            cf["Files"]["plot_path"] = "plots/"
            cf["Files"]["file_path"] = os.path.split(filename)[0]+"/"
            cf["Files"]["in_filename"] = os.path.split(filename)[1]
        else:
            cf = pfp_io.load_controlfile(path="controlfiles")
            if len(cf) == 0:
                return
        logger.info("Loaded control file ...")
        if "Options" not in cf:
            cf["Options"]={}
        cf["Options"]["call_mode"] = "interactive"
        cf["Options"]["show_plots"] = "Yes"
        logger.info("Plotting windroses ...")
        pfp_plot.plot_windrose(cf)
        logger.info(" Finished plotting windroses")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting windroses, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_windrose_custom(main_ui):
    """
    Purpose:
     Plot windroses.
    Usage:
     pfp_top_level.do_plot_windrose()
    Side effects:
     Plots windroses to the screen and creates .PNG hardcopies of
     the plots.
    Author: PRI/CE
    Date: May 2022
    Mods:
    """
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        cfg["Options"]["call_mode"] = "interactive"
        cfg["Options"]["show_plots"] = "Yes"
        logger.info("Plotting windroses ...")
        pfp_plot.plot_windrose(cfg)
        logger.info(" Finished plotting windroses")
        logger.info("")
    except Exception:
        error_message = " An error occurred while plotting windroses, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return
def do_plot_closeplots():
    """
    Close plot windows.
    """
    logger.info("Closing plot windows ...")
    matplotlib.pyplot.close("all")
    return
# top level routines for the Utilities menu
def do_utilities_climatology_custom(main_ui):
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        logger.info("Starting climatology")
        pfp_clim.climatology(cfg)
        logger.info("Finished climatology")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing climatology, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_climatology_standard(main_ui, nc_file_uri):
    try:
        logger.info("Starting climatology")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "climatology.txt")
        if not os.path.exists(stdname):
            msg = " Climatology: unable to find standard control file climatology.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_Climatology.xls")
        cfg["Files"] = {"file_path": file_path, "in_filename": in_filename,
                        "out_filename": out_filename}
        pfp_clim.climatology(cfg)
        logger.info("Finished climatology")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing climatology, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return

def do_utilities_footprint_kljun_standard(main_ui,nc_file_uri):
    """
    Purpose: To calculate the footprint of the dataset using the Kljun et al method.
    Args:
        main_ui:

    Returns:

    """
    try:
        logger.info("Starting the Kljun et al footprint calculation...")

        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "kljun_footprint.txt")
        if not os.path.exists(stdname):
            msg = " Footprint: unable to find standard control file kljun_footprint.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_kljun.nc")
        results_filename = in_filename.replace(".nc", "_kljun_results.csv")
        plot_path = file_path # probably a more sensible way to do this, its staying like this for now.
        cfg["Files"] = {"file_path": file_path,"plot_path": plot_path, "in_filename": in_filename,
                        "out_filename": out_filename,"results_file" : results_filename}
        pfp_footprint.footprint_main(cfg,"kljun_L3")
        logger.info("Finished kljun et al footprint.")
        logger.info("")

    except Exception:
        error_message = " An error occurred while doing footprint, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return

def do_utilities_footprint_kormannmeixner_standard(main_ui,nc_file_uri):
    """
    Purpose: To calculate the footprint of the dataset using the Kormann meixner method.
    Args:
        main_ui:

    Returns:

    """
    try:
        logger.info("Starting the Kormann Meixner footprint calculation...")
                # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "kormei_footprint.txt")
        if not os.path.exists(stdname):
            msg = " Footprint: unable to find standard control file kormei_footprint.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_kormei.nc")
        results_filename = in_filename.replace(".nc", "_kormei_results.csv")
        plot_path = file_path # probably a more sensible way to do this, its staying like this for now.
        cfg["Files"] = {"file_path": file_path,"plot_path": plot_path, "in_filename": in_filename,
                        "out_filename": out_filename,"results_file" : results_filename}
        pfp_footprint.footprint_main(cfg,"kormei_L3")
        logger.info("Finished Kormann Meixner footprint.")
        logger.info("")
        

    except Exception:
        error_message = " An error occurred while doing footprint, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return


def do_utilities_ustar_cpd_barr_custom(main_ui):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is a line-by-line translation of the original Barr MATLAB scripts
     into Python.
    """
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        logger.info("Starting CPD u* threshold detection (Barr)")
        pfp_cpd_barr.cpd_barr_main(cfg)
        logger.info("Finished CPD u* threshold detection (Barr)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (Barr), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_cpd_barr_standard(main_ui, nc_file_uri):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is a line-by-line translation of the original Barr MATLAB scripts
     into Python.
    """
    try:
        logger.info("Starting CPD u* threshold detection (Barr)")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "cpd_barr.txt")
        if not os.path.exists(stdname):
            msg = " CPD (Barr): unable to find standard control file cpd_barr.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_CPD_Barr.xlsx")
        cfg["Files"] = {"file_path": file_path, "in_filename": in_filename,
                        "out_filename": out_filename}
        pfp_cpd_barr.cpd_barr_main(cfg)
        logger.info("Finished CPD u* threshold detection (Barr)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (Barr), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_cpd_mchugh_custom(main_ui):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is the original implementation by Ian McHugh.
    """
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        logger.info("Starting CPD u* threshold detection (McHugh)")
        pfp_cpd_mchugh.cpd_mchugh_main(cfg)
        logger.info("Finished CPD u* threshold detection (McHugh)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (McHugh), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_cpd_mchugh_standard(main_ui, nc_file_uri):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is the original implementation by Ian McHugh.
    """
    try:
        logger.info("Starting CPD u* threshold detection (McHugh)")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "cpd_mchugh.txt")
        if not os.path.exists(stdname):
            msg = " CPD (McHugh): unable to find standard control file cpd_mchugh.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_CPD_McHugh.xlsx")
        cfg["Files"] = {"file_path": file_path, "in_filename": in_filename,
                        "out_filename": out_filename}
        pfp_cpd_mchugh.cpd_mchugh_main(cfg)
        logger.info("Finished CPD u* threshold detection (McHugh)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (McHugh), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_cpd_mcnew_custom(main_ui):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is a second implementation of Barr et al by Ian McHugh circa 2020.  It
     is ~10 times faster than the original implementation.
    """
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        logger.info("Starting CPD u* threshold detection (McNew)")
        pfp_cpd_mcnew.cpd_mcnew_main(cfg)
        logger.info("Finished CPD u* threshold detection (McNew)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (McNew), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_cpd_mcnew_standard(main_ui, nc_file_uri):
    """
    Purpose:
     Calculate the u* threshold using the Change Point Detection method described in
     Barr et al. 2013, AFM 171-172, pp31-45.
     This code is a second implementation of Barr et al by Ian McHugh circa 2020.  It
     is ~10 times faster than the original implementation.
    """
    try:
        logger.info("Starting CPD u* threshold detection (McNew)")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "cpd_mcnew.txt")
        if not os.path.exists(stdname):
            msg = " CPD (McNew): unable to find standard control file cpd_mcnew.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_CPD_McNew.xlsx")
        cfg["Files"] = {"file_path": file_path, "in_filename": in_filename,
                        "out_filename": out_filename}
        pfp_cpd_mcnew.cpd_mcnew_main(cfg)
        logger.info("Finished CPD u* threshold detection (McNew)")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing CPD u* threshold (McNew), see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_mpt_custom(main_ui):
    """
    Purpose:
     Calculate the u* threshold using the Moving Point Threshold (MPT) method.
     This code calls the original FluxNet MPT C code.  The executable for this is
     in PyFluxPro/mpt/bin.
    Side effects:
     Calls pfp_mpt.mpt_main
    """
    try:
        cfg = main_ui.tabs.tab_dict[main_ui.tabs.tab_index_running].get_data_from_model()
        logger.info("Starting u* threshold detection (MPT)")
        pfp_mpt.mpt_main(cfg)
        logger.info("Finished MPT u* threshold detection")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing MPT u* threshold, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
def do_utilities_ustar_mpt_standard(main_ui, nc_file_uri):
    """
    Purpose:
     Calculate the u* threshold using the Moving Point Threshold (MPT) method.
     This code calls the original FluxNet MPT C code.  The executable for this is
     in PyFluxPro/mpt/bin.
    Side effects:
     Calls pfp_mpt.mpt_main
    """
    try:
        logger.info("Starting u* threshold detection (MPT)")
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "mpt.txt")
        if not os.path.exists(stdname):
            msg = " MPT: unable to find standard control file cpd_mcnew.txt"
            logger.error(msg)
            return
        cfg = pfp_io.get_controlfilecontents(stdname)
        file_path = os.path.join(os.path.split(nc_file_uri)[0], "")
        in_filename = os.path.split(nc_file_uri)[1]
        out_filename = in_filename.replace(".nc", "_MPT.xlsx")
        cfg["Files"] = {"file_path": file_path, "in_filename": in_filename,
                        "out_filename": out_filename}
        pfp_mpt.mpt_main(cfg)
        logger.info("Finished MPT u* threshold detection")
        logger.info("")
    except Exception:
        error_message = " An error occurred while doing MPT u* threshold, see below for details ..."
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    main_ui.actionRunCurrent.setDisabled(False)
    return
#def do_utilities_cfcheck(nc_file_uri):
    #try:
        #logger.info("Starting CF check")
        #pfp_compliance.CheckCFCompliance(nc_file_uri)
        #logger.info("Finished CF check")
        #logger.info("")
    #except Exception:
        #error_message = " An error occurred while doing the CF check, see below for details ..."
        #logger.error(error_message)
        #error_message = traceback.format_exc()
        #logger.error(error_message)
    #return
