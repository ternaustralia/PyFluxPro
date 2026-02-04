# standard modules
import copy
import inspect
import logging
import numbers
import os
import platform
import traceback
# 3rd party modules
from configobj import ConfigObj
#import numpy
import timezonefinder
# PFP modules
from scripts import constants as c
from scripts import pfp_func_units
from scripts import pfp_func_stats
from scripts import pfp_func_transforms
from scripts import pfp_gui
from scripts import pfp_io
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

#def CheckCFCompliance(nc_file_uri):
    #"""
    #Purpose:
     #Run the CF Conventions checker on a netCDF file.
    #Side effects:
     #Creates 3 text files in the same folder as the netCDF file
     #and with the following suffixes:
      #_cfchecker.all - contains all messages from cfchecker
      #_cfchecker.errors - contains all ERROR messages from cfchecker
      #_cfchecker.warnings - contains all WARNING messages from cfchecker
    #Author: PRI
    #Date: July 2021
    #"""
    #msg = " Checking CF compliance for " + os.path.basename(nc_file_uri)
    #logger.info(msg)
    #try:
        ## cfchecker log file for all messages
        #cf_file_uri = nc_file_uri.replace(".nc", "_cfchecker.all")
        ## cfchecker log file for error messages
        #cf_error_uri = cf_file_uri.replace("_cfchecker.all", "_cfchecker.errors")
        ## cfchecker log file for warning messages
        #cf_warning_uri = cf_file_uri.replace("_cfchecker.all", "_cfchecker.warnings")
        ## with a little work, cfchecker could be used directly in PFP
        ## path to Python running this show
        #env_bin = os.path.join(sys.exec_prefix, "bin")
        ## path to cfchecks in that Python install
        #env_cfchecks = os.path.join(env_bin, "cfchecks")
        ## command to run with path to cfchecks
        #cmd = [env_cfchecks, "-v 1.8", nc_file_uri]
        #with open(cf_file_uri, "w") as f:
            ## run cfchecks as a subprocess at this stage
            #subprocess.run(cmd, stdout=f)
        ## parse the output of cfchecker and write warnings and errors to separate files
        ## error file
        #error_file = open(cf_error_uri, "w")
        #n_errors = 0
        ## warning file
        #warning_file = open(cf_warning_uri, "w")
        #n_warnings = 0
        ## read the cfchecker log file
        #with open(cf_file_uri) as f:
            #for line in f:
                #if "CHECKING NetCDF FILE" in line:
                    ## line containing the file name
                    #error_file.write(line)
                    #warning_file.write(line)
                    #continue
                #if "Checking variable:" in line:
                    ## line containing the variable name
                    #parts = line.split(" ")
                    #variable_name = parts[2].rstrip()
                    #continue
                #if (("ERROR:" in line) and ('variable_name' in locals())):
                    ## line containing error messages
                    #line_out = " " + variable_name + " " + line
                    #error_file.write(line_out)
                    #n_errors += 1
                    #continue
                #if (("WARN:" in line) and ('variable_name' in locals())):
                    ## line containing warning messages
                    #line_out = " " + variable_name + " " + line
                    #warning_file.write(line_out)
                    #n_warnings += 1
                    #continue
        ## close the error and warning files
        #error_file.close()
        #warning_file.close()
        ## tell the user what we found
        #if n_errors > 0:
            ## number of errors found by cfchecker
            #msg = " CF checks returned " + str(n_errors) + " errors"
            #logger.error(msg)
            #msg = "  Check " + cf_error_uri + " for details"
            #logger.error(msg)
        #if n_warnings > 0:
            ## number of warnings found by cfchecker
            #msg = " CF checks returned " + str(n_warnings) + " warnings"
            #logger.warning(msg)
            #msg = "  Check " + cf_warning_uri + " for details"
            #logger.warning(msg)
        ## info message to user about errors and warnings
        #msg = " CF checks returned " + str(n_errors) + " errors and "
        #msg += str(n_warnings) + " warnings"
        #logger.info(msg)
    #except Exception:
        #msg = "Error during CF compliance check of " + os.path.split(nc_file_uri)[1]
        #logger.error(msg)
        #error_message = traceback.format_exc()
        #logger.error(error_message)
    #return

def check_executables():
    # check for the executable files required
    if platform.system() == "Windows":
        executable_extension = ".exe"
    else:
        executable_extension = ""
    executable_names = ["solo/bin/sofm", "solo/bin/solo", "solo/bin/seqsolo",
                        "mds/bin/gf_mds", "mpt/bin/ustar_mp"]
    missing_executable = False
    for executable_name in executable_names:
        executable_name = executable_name + executable_extension
        if not os.path.isfile(executable_name):
            missing_executable = True
    if missing_executable:
        msg = "One or more of the required executable files could not be found.\n"
        msg = msg + "If you are running on Windows, clone the repository again.\n"
        msg = msg + "If you are running on OSX or Linux, use the make_nix script\n"
        msg = msg + "to compile the executables."
        pfp_gui.MsgBox_Quit(msg, title="Critical")
    return

def climatology_update_controlfile(cfg):
    """
    Purpose:
     Parse the climatology control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.climatology_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: September 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the climatology control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_variables_rename(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the climatology control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def cpd_barr_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the CPD (Barr) control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.cpd_barr_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: September 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    # force the level to "cpd_barr", early versions used "cpd1"
    cfg["level"] = "cpd_barr"
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the CPD (Barr) control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_rename(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the CPD (Barr) control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def cpd_mchugh_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the CPD (McHugh) control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.cpd_mchugh_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: September 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    # force the level to "cpd_mchugh", early versions used "cpd2"
    cfg["level"] = "cpd_mchugh"
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the CPD (McHugh) control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_rename(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the CPD (McHugh) control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def cpd_mcnew_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the CPD (McNew) control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.cpd_mcnew_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: May 2021
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    # force the level to "cpd_mcnew", early versions used "cpd3"
    cfg["level"] = "cpd_mcnew"
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the CPD (McNew) control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_rename(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the CPD (McNew) control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def mpt_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the MPT control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.mpt_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: September 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # initialise the return logical
    ok = True
    # force the level to "mpt"
    cfg["level"] = "mpt"
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the MPT control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_rename(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the MPT control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def concatenate_update_controlfile(cfg):
    """
    Purpose:
     Parse the concatenate control file to update the syntax from earlier OFQC/PFP
     versions to the syntax used by this version.
    Usage:
     result = pfp_compliance.concatenate_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the concatenate control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: February 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the concatenation control file syntax"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def ParseConcatenateControlFile(cf):
    """
    Purpose:
     Make the concatenate information dictionary
    Usage:
    Side effects:
    Author: PRI
    Date: August 2019
    """
    info = {}
    info["cfg"] = copy.deepcopy(cf)
    info["NetCDFConcatenate"] = {"OK": True}
    inc = info["NetCDFConcatenate"]
    # check the control file has a Files section
    if "Files" not in cf:
        msg = " Files section missing from control file"
        logger.error(msg)
        inc["OK"] = False
        return info
    # check the [Files] section contains an [Out] section and an [In] section
    for item in ["Out", "In"]:
        if item not in cf["Files"]:
            msg = " " + item + " subsection missing from Files section"
            logger.error(msg)
            inc["OK"] = False
            return info
    # check the [In] section contains at least 1 entry
    if len(list(cf["Files"]["In"].keys())) < 1:
        msg = " No input files specified"
        logger.error(msg)
        inc["OK"] = False
        return info
    # get a list of the input file names
    inc["in_file_names"] = []
    for key in sorted(list(cf["Files"]["In"].keys())):
        file_name = cf["Files"]["In"][key]
        if os.path.isfile(file_name):
            inc["in_file_names"].append(file_name)
        else:
            msg = " File not found (" + os.path.basename(file_name) + ")"
            logger.warning(msg)
    # check to see if we have any files to concatenate
    if len(inc["in_file_names"]) == 0:
        msg = " No input files to concatenate"
        logger.error(msg)
        inc["OK"] = False
        return info
    # get the output file name
    if "ncFileName" not in cf["Files"]["Out"]:
        msg = " No ncFileName key in Out subsection of Files section"
        logger.error(msg)
        inc["OK"] = False
        return info
    inc["out_file_name"] = cf["Files"]["Out"]["ncFileName"]
    # check the output path exists, create if it doesn't
    file_path, file_name = os.path.split(inc["out_file_name"])
    if not os.path.isdir(file_path):
        os.makedirs(file_path)
    # work through the choices in the [Options] section
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "ApplyMADFilter", default = "")
    inc["ApplyMADFilter"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "ApplyFco2Storage", default = "No")
    inc["ApplyFco2Storage"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "NumberOfDimensions", default=3)
    inc["NumberOfDimensions"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "MaxGapInterpolate", default=0)
    inc["MaxGapInterpolate"] = int(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "FixTimeStepMethod", default="round")
    inc["FixTimeStepMethod"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "Truncate", default="No")
    inc["Truncate"] = str(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "TruncateThreshold", default=50)
    inc["TruncateThreshold"] = float(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "SeriesToCheck", default="all")
    inc["SeriesToCheck"] = pfp_utils.csv_string_to_list(opt)
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "SeriesToKeep", default=None)
    if opt is not None:
        inc["SeriesToKeep"] = pfp_utils.csv_string_to_list(opt)
    # now add the bits and pieces
    inc["time_coverage_start"] = []
    inc["time_coverage_end"] = []
    inc["chrono_files"] = []
    inc["labels"] = []
    inc["attributes"] = ["height", "instrument", "long_name", "standard_name",
                         "statistic_type", "units", "valid_range", "MAD filter"]
    # add key for suppressing output of intermediate variables e.g. Cpd etc
    opt = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "KeepIntermediateSeries", default="No")
    info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    return info

def ParseL1ControlFile(cf):
    """
    Purpose:
     Check the contents of the Li control file.
     If the L1 control file contents are OK, return with the required information.
     If the L1 control file contents are not OK, return with an error message.
    """
    logger.info(" Parsing the L1 control file")
    # create the settings dictionary
    l1_info = {"status": {"value": 0, "message": "OK"},
              "read_excel": {}}
    l1ire = l1_info["read_excel"]
    # copy the files section from the control file
    l1ire["Files"] = copy.deepcopy(cf["Files"])
    l1ire["Files"]["file_name"] = os.path.join(cf["Files"]["file_path"], cf["Files"]["in_filename"])
    l1ire["Files"]["in_headerrow"] = cf["Files"]["in_headerrow"]
    l1ire["Files"]["in_firstdatarow"] = cf["Files"]["in_firstdatarow"]
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="./plots/")
    plot_path = os.path.join(plot_path, "L1", "")
    if not os.path.exists(plot_path):
        os.makedirs(plot_path)
    l1ire["Files"]["plot_path"] = plot_path
    # get the global attributes
    l1ire["Global"] = copy.deepcopy(cf["Global"])
    # get the options section
    l1ire["Options"] = copy.deepcopy(cf["Options"])
    # get the variables
    l1ire["Variables"] = copy.deepcopy(cf["Variables"])
    return l1_info

def ParseL3ControlFile(cfg, ds):
    """
    Purpose:
     Parse the L3 control file and return contents in the l3_info dictionary.
    Usage:
    Side effects:
    Author: PRI
    Date: August 2019
    """
    # PRI 7/10/2021 the code to get zms will give unpredictable results if CO2
    #   profile data present
    l3_info = {"status": {"value": 0, "message": "OK", "ok": True},
               "variables": {"CO2": {}, "Fco2": {}, "Sco2": {}},
               "CombineSeries": {}}
    # copy the control file into the l3_info dictionary
    l3_info["cfg"] = copy.deepcopy(cfg)
    # add key for suppressing output of intermediate variables e.g. Cpd etc
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "KeepIntermediateSeries", default="No")
    l3_info["RemoveIntermediateSeries"] = {"KeepIntermediateSeries": opt, "not_output": []}
    # find out what label is used for CO2
    parse_l3_co2_label(l3_info)
    # get the height of the CO2 measurement
    parse_l3_co2_height(ds, l3_info)
    # get lists of variables to be merged or averaged
    parse_l3_combine(l3_info)
    return l3_info

def parse_l3_combine(info):
    """ Get a list of variables to be merged or averaged at L3. """
    cfg = info["cfg"]
    cfv = cfg["Variables"]
    labels = list(cfv.keys())
    # list of labels that are explicitly referenced in pfp_levels.l3qc()
    l3_labels = ["CO2", "Fco2", "Fg", "Fsd", "Fsu", "Fld", "Flu", "Fn",
                 "Sco2", "Sws", "Ta", "Ts", "Wd", "Ws"]
    # cs_labels is a list of all variables using MergeSeries or AverageSeries
    cs_labels = []
    # loop over L3 labels
    for label in l3_labels:
        info["CombineSeries"][label] = [l for l in labels if l.split("_")[0] == label]
        cs_labels = cs_labels + info["CombineSeries"][label]
    cs_labels = list(set(cs_labels))
    # now get a list of any other variables using MergeSeries of AverageSeries that
    # are not in cs_labels
    merge_extras = [l for l in labels if l not in cs_labels and "MergeSeries" in cfv[l]]
    average_extras = [l for l in labels if l not in cs_labels and "AverageSeries" in cfv[l]]
    info["CombineSeries"]["extras"] = merge_extras + average_extras
    return

def parse_l3_co2_label(info):
    """ Get the CO2 variable label."""
    if "CO2" in list(info["cfg"]["Variables"].keys()):
        info["variables"]["CO2"]["label"] = "CO2"
    else:
        info["variables"]["CO2"]["label"] = None
        msg = " No entry for CO2 in control file"
        logger.warning(msg)
        info["status"]["value"] = 1
        info["status"]["message"] = msg
    return

def parse_l3_co2_height(ds, info):
    """ Get the height of the CO2 measurement from various sources."""
    if info["variables"]["CO2"]["label"] is None:
        return
    cfg = info["cfg"]
    got_zms = False
    labels = list(ds.root["Variables"].keys())
    CO2_label = info["variables"]["CO2"]["label"]
    # try and get the height from the CO2 variable
    if CO2_label in labels:
        # get height from attributes if the CO2 variable is already in the data structure
        try:
            CO2 = pfp_utils.GetVariable(ds, CO2_label)
            zms = float(pfp_utils.strip_non_numeric(CO2["Attr"]["height"]))
            got_zms = True
        except:
            pass
    if not got_zms and "MergeSeries" in list(cfg["Variables"][CO2_label].keys()):
        # get the height from the variables listed in MergeSeries
        try:
            source = cfg["Variables"][CO2_label]["MergeSeries"]["source"]
            source = pfp_utils.convert_csv_string_to_list(source)
            for item in source:
                var = pfp_utils.GetVariable(ds, item)
                zms = float(pfp_utils.strip_non_numeric(var["Attr"]["height"]))
                got_zms = True
                break
        except:
            pass
    if not got_zms and "AverageSeries" in list(cfg["Variables"][CO2_label].keys()):
        # get the height from the variables listed in AverageSeries
        try:
            source = cfg["Variables"][CO2_label]["AverageSeries"]["source"]
            source = pfp_utils.convert_csv_string_to_list(source)
            for item in source:
                var = pfp_utils.GetVariable(ds, item)
                zms = float(pfp_utils.strip_non_numeric(var["Attr"]["height"]))
                got_zms = True
                break
        except:
            pass
    if not got_zms and "tower_height" in list(ds.root["Attributes"].keys()):
        try:
            zms = float(pfp_utils.strip_non_numeric(ds.root["Attributes"]["tower_height"]))
            got_zms = True
        except:
            pass
    if not got_zms and pfp_utils.cfkeycheck(cfg, Base="Options", ThisOne="zms"):
        try:
            zms = float(pfp_utils.strip_non_numeric(cfg["Options"]["zms"]))
            got_zms = True
        except:
            pass
    if got_zms:
        info["variables"]["CO2"]["height"] = zms
    else:
        msg = " Unable to find height for CO2 (" + CO2_label + ") measurement"
        logger.warning(msg)
        info["status"]["value"] = 1
        info["status"]["message"] = msg
    return

def parse_variable_attributes(attributes):
    """
    Purpose:
     Clean up the variable attributes.
    Usage:
    Author: PRI
    Date: September 2019
    """
    for attr in attributes:
        value = attributes[attr]
        if not isinstance(value, str):
            continue
        if attr in ["rangecheck_lower", "rangecheck_upper", "diurnalcheck_numsd"]:
            if ("[" in value) and ("]" in value) and ("*" in value):
                # old style of [value]*12
                value = value[value.index("[")+1:value.index("]")]
            elif ("[" in value) and ("]" in value) and ("*" not in value):
                # old style of [1,2,3,4,5,6,7,8,9,10,11,12]
                value = value.replace("[", "").replace("]", "")
            strip_list = [" ", '"', "'"]
        elif ("ExcludeDates" in attr or
              "ExcludeHours" in attr or
              "LowerCheck" in attr or
              "UpperCheck" in attr):
            strip_list = ["[", "]", '"', "'"]
        else:
            strip_list = ['"', "'"]
        for c in strip_list:
            if c in value:
                value = value.replace(c, "")
        attributes[attr] = value
    return attributes

def check_batch_controlfile(self):
    """
    Purpose:
     Check the L1 control file to make sure it contains all information
     needed to run L1 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: June 2020
    """
    ok = True
    return ok

def check_l1_controlfile(cfg):
    """
    Purpose:
     Check the L1 control file to make sure it contains all information
     needed to run L1 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2021
    """
    ok = True
    # compliance checks not applied for L1 nc2csv_oneflux
    if cfg["level"] in ["L1_oneflux"]:
        return ok
    # quick and dirty use of try...except in a panic ahead to 2021 workshop
    try:
        cfg_labels = sorted(list(cfg["Variables"].keys()))
        base_path = pfp_utils.get_base_path()
        std_name = os.path.join(base_path, "controlfiles", "standard", "check_l1_controlfile.txt")
        std = ConfigObj(std_name, indent_type="    ", list_values=False, write_empty_values=True)
        std_labels = sorted(list(std["Variables"].keys()))
        # initialise the messages dictionary
        messages = {"ERROR":[], "WARNING": [], "INFO": [], "DEBUG": [], "RESULT": "ignore"}
        # check the files section
        l1_check_files(cfg, std, messages)
        # check the global attributes section
        l1_check_global_attributes(cfg, std, messages)
        # check variables whose name exactly matches an entry in the settings/l1.txt control file
        done = []
        label_matches = [l for l in cfg_labels if l in std_labels]
        for cfg_label in label_matches:
            std_label = cfg_label
            # check variable 'Attr' section
            l1_check_variables_sections(cfg, std, cfg_label, std_label, messages)
            # append this variable name to the done list
            done.append(cfg_label)
        # check variables where the first characters of the name match an entry in settings/l1.txt
        cfg_labels = sorted(list(cfg["Variables"].keys()))
        for std_label in std_labels:
            lsl = len(std_label)
            label_matches = [l for l in cfg_labels if l[:min([len(l),lsl])] == std_label and l not in done]
            for cfg_label in label_matches:
                # check variable 'Attr' section
                l1_check_variables_sections(cfg, std, cfg_label, std_label, messages)
                # append this variable name to the done list
                done.append(cfg_label)
        # check for duplicate netCDF variable labels
        l1_check_nc_labels(cfg, messages)
        # check for duplicate input variable labels
        l1_check_input_labels(cfg, messages)
        # check IRGA and sonic instrument type
        l1_check_irga_sonic_type(cfg, messages)
        # display and messages
        display_messages_interactive(messages, mode="CloseOrIgnore")
        if messages["RESULT"].lower() != "ignore":
            ok = False
    except Exception:
        ok = False
        error_message = " Error checking L1 control file, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok
def check_l2_controlfile(cfg):
    """
    Purpose:
     Check the L2 control file to make sure it contains all information
     needed to run L2 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2022
    """
    # quick and dirty use of try...except in a panic ahead to 2021 workshop
    ok = True
    try:
        # initialise the messages dictionary
        messages = {"ERROR":[], "WARNING": [], "INFO": [], "DEBUG": [], "RESULT": "ignore"}
        # check the files section
        l2_check_files(cfg, messages)
        # check the options section
        l2_check_options(cfg, messages)
        # check the variables section
        #l2_check_variables_section(cfg, std, messages)
        display_messages_interactive(messages)
        if messages["RESULT"].lower() != "ignore":
            ok = False
    except Exception:
        ok = False
        error_message = " Error checking L1 control file, see below for details ... "
        logger.error(error_message)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok
def check_l2_options(cfg, ds):
    """
    Purpose:
     Check the options specified in the L2 control file are consistent
     with the contents of the L1 netCDF file.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2022
    """
    messages = {"ERROR":[], "WARNING": [], "INFO": []}
    closed_path_irgas = list(c.instruments["irgas"]["closed_path"].keys())
    open_path_irgas = list(c.instruments["irgas"]["open_path"].keys())
    irga_types = open_path_irgas + closed_path_irgas
    nc_irga_type = None
    cfg_irga_type = None
    if ("irga_type" in ds.root["Attributes"]):
        nc_irga_type = str(ds.root["Attributes"]["irga_type"])
    if ("irga_type" in cfg["Options"]):
        cfg_irga_type = str(cfg["Options"]["irga_type"])
    if ((nc_irga_type is None) and (cfg_irga_type is None)):
        # IRGA type not found in the L1 netCDF file or the control file
        msg = "IRGA type not specified in L1 netCDF file or L2 control file"
        messages["ERROR"].append(msg)
        ds.info["returncodes"]["value"] = 1
    elif ((nc_irga_type is None) and (cfg_irga_type is not None)):
        # IRGA type not found in the L1 netCDF file but found in the L2 control file
        if (cfg_irga_type not in irga_types):
            # make sure the IRGA type is in the known IRGA list
            msg = "Unknown IRGA type specified in control file (" + cfg_irga_type + ")"
            messages["ERROR"].append(msg)
            ds.info["returncodes"]["value"] = 1
        else:
            ds.root["Attributes"]["irga_type"] = cfg_irga_type
    elif ((nc_irga_type is not None) and (cfg_irga_type is None)):
        # IRGA type found in the L1 netCDF file but not found in the L2 control file
        if (nc_irga_type not in irga_types):
            # make sure the IRGA type is in the known IRGA list
            msg = "Unknown IRGA type specified in netCDF file (" + nc_irga_type + ")"
            messages["ERROR"].append(msg)
            ds.info["returncodes"]["value"] = 1
        else:
            pass
    else:
        # IRGA type found in the L1 netCDF file and the L2 control file
        if (nc_irga_type == cfg_irga_type):
            pass
        else:
            msg = "Different IRGA types in L1 netCDF ("+nc_irga_type
            msg += ") and L2 control file ("+cfg_irga_type+")"
            ds.info["returncodes"]["value"] = 1
            messages["ERROR"].append(msg)
    # check the sonic type
    sonic_types = list(c.instruments["sonics"].keys())
    nc_sonic_type = None
    cfg_sonic_type = None
    # is sonic_type in the global attributes?
    if ("sonic_type" in ds.root["Attributes"]):
        nc_sonic_type = str(ds.root["Attributes"]["sonic_type"])
    # is sonic_type in the [Options] section of the control file
    if ("sonic_type" in cfg["Options"]):
        cfg_sonic_type = str(cfg["Options"]["sonic_type"])
    if ((nc_sonic_type is None) and (cfg_sonic_type is None)):
        # sonic type not found in the L1 netCDF file or the control file
        msg = "Sonic type not specified in L1 netCDF file or L2 control file"
        messages["ERROR"].append(msg)
        ds.info["returncodes"]["value"] = 1
    elif ((nc_sonic_type is None) and (cfg_sonic_type is not None)):
        # sonic type not found in the L1 netCDF file but found in the L2 control file
        if (cfg_sonic_type not in sonic_types):
            # make sure the sonic type is in the known sonic list
            msg = "Unknown sonic type specified in control file (" + cfg_sonic_type + ")"
            messages["ERROR"].append(msg)
            ds.info["returncodes"]["value"] = 1
        else:
            ds.root["Attributes"]["sonic_type"] = cfg_sonic_type
    elif ((nc_sonic_type is not None) and (cfg_sonic_type is None)):
        # sonic type found in the L1 netCDF file but not found in the L2 control file
        if (nc_sonic_type not in sonic_types):
            # make sure the sonic type is in the known sonic list
            msg = "Unknown sonic type specified in netCDF file (" + nc_sonic_type + ")"
            messages["ERROR"].append(msg)
            ds.info["returncodes"]["value"] = 1
        else:
            pass
    else:
        # sonic type found in the L1 netCDF file and the L2 control file
        if (nc_sonic_type == cfg_sonic_type):
            pass
        else:
            msg = "Different sonic types in L1 netCDF ("+nc_sonic_type
            msg += ") and L2 control file ("+cfg_sonic_type+")"
            ds.info["returncodes"]["value"] = 1
            messages["ERROR"].append(msg)
    # check if we are running in interactive mode and display messages accordingly
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "call_mode", default="interactive")
    if opt.lower() == "interactive":
        display_messages_interactive(messages)
    else:
        display_messages_batch(messages)
    return
def check_l3_controlfile(cfg):
    """
    Purpose:
     Check the L3 control file to make sure it contains all information
     needed to run L3 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2023
    """
    ok = True
    messages = {"ERROR":[], "WARNING": [], "INFO": [], "DEBUG": [], "RESULT": "ignore"}
    check_l3_files(cfg, messages)
    check_l3_imports(cfg, messages)
    check_l3_options(cfg, messages)
    display_messages_interactive(messages)
    if messages["RESULT"].lower() != "ignore":
        ok = False
    return ok
def check_l3_files(cfg, messages):
    """ Check the Files section in the L3 control file."""
    # check the Files section exists
    if ("Files" in cfg):
        # check file_path is in the Files section
        if "file_path" in cfg["Files"]:
            file_path = cfg["Files"]["file_path"]
            # check file_path directory exists
            if os.path.isdir(file_path):
                pass
            else:
                msg = "Files: " + file_path + " is not a directory"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'file_path' not in section"
            messages["ERROR"].append(msg)
        # check plot_path is in the Files section
        if "plot_path" in cfg["Files"]:
            plot_path = cfg["Files"]["plot_path"]
            # check plot_path directory exists
            if os.path.isdir(plot_path):
                pass
            else:
                msg = "Files: " + plot_path + " doesn't exist, creating ..."
                messages["INFO"].append(msg)
                os.mkdir(plot_path)
        else:
            msg = "Files: 'plot_path' not in section"
            messages["ERROR"].append(msg)
        # check in_filename is in the Files section
        if "in_filename" in cfg["Files"]:
            file_name = cfg["Files"]["in_filename"]
            file_parts = os.path.splitext(file_name)
            # check the file type is supported
            if (file_parts[-1].lower() in  [".nc"]):
                file_uri = os.path.join(file_path, file_name)
                if os.path.isfile(file_uri):
                    pass
                else:
                    msg = "Files: " + file_name + " not found"
                    messages["ERROR"].append(msg)
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'in_filename' not in section"
            messages["ERROR"].append(msg)
        # check the output file type
        if "out_filename" in cfg["Files"]:
            file_name = cfg["Files"]["out_filename"]
            file_parts = os.path.splitext(file_name)
            if (file_parts[-1].lower() in [".nc"]):
                pass
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
    else:
        msg = "'Files' section not in control file"
        messages["ERROR"].append(msg)
    return
def check_l3_imports(cfg, messages):
    """ Check the Imports section."""
    if ("Imports" in cfg):
        import_labels = list(cfg["Imports"].keys())
        for import_label in import_labels:
            if "file_name" in cfg["Imports"][import_label]:
                import_uri = cfg["Imports"][import_label]["file_name"]
                if os.path.isfile(import_uri):
                    pass
                else:
                    msg = "Imports: " + import_uri + " not found"
                    messages["ERROR"].append(msg)
            else:
                msg = "Imports: 'file_name' not found"
                messages["ERROR"].append(msg)
    return
def check_l3_options(cfg, messages):
    """
    Purpose:
     Check the options specified in the L3 control file.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2023
    """
    check_l3_options_generic(cfg, messages)
    check_l3_options_rotation(cfg, messages)
    check_l3_options_soil(cfg, messages)
    return
def check_l3_options_generic(cfg, messages):
    """ Check the generic L3 options."""
    if "zms" in cfg["Options"]:
        zms =  cfg["Options"]["zms"]
        if isinstance(float(pfp_utils.strip_non_numeric(zms)), numbers.Number):
            pass
        else:
            msg = "zms (" + zms + ") is not a number"
            messages["ERROR"].append(msg)
    if "CO2Units" in cfg["Options"]:
        co2_units = cfg["Options"]["CO2Units"]
        if co2_units not in ["umol/mol", "mg/m^3"]:
            msg = "Unrecognised CO2 units (" + co2_units + "), must be umol/mol or mg/m^3"
            messages["ERROR"].append(msg)
    if "Fco2Units" in cfg["Options"]:
        Fco2_units = cfg["Options"]["Fco2Units"]
        if Fco2_units not in ["umol/m^2/s", "mg/m^2/s"]:
            msg = "Unrecognised Fco2 units (" + Fco2_units + "), must be umol/m^2/s or mg/m^2/s"
            messages["ERROR"].append(msg)
    for item in ["2DCoordRotation", "ApplyFco2Storage", "CalculateFluxes",
                 "CorrectFgForStorage", "CorrectIndividualFg", "KeepIntermediateSeries",
                 "MassmanCorrection", ]:
        if item in cfg["Options"]:
            opt = cfg["Options"][item]
            if opt.lower() not in ["yes", "no"]:
                msg = "Unrecognised " + item + " option (" + opt + "), must be Yes or No"
                messages["ERROR"].append(msg)
    return
def check_l3_options_rotation(cfg, messages):
    """ Check the rotation option."""
    # get the CalculateFluxes setting from the [Options] section
    calculate_fluxes_option = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "CalculateFluxes",
                                                           default="Yes")
    # if we are not calculating fluxes at L3, we do not need to check the 2DCoordRotation option
    if (calculate_fluxes_option.lower() == "no"):
        return
    # get the 2DCoordRotation setting from the L3 [Options]
    rotation_option = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "2DCoordRotation",
                                                   default="Yes")
    # check to see if 2D coordinate rotation is turned on or off
    if (rotation_option.lower() == "no"):
        # error message if calculating fluxes at L3 but 2D coordinate rotation turned off
        msg = "Coordinate rotation disabled"
        messages["ERROR"].append(msg)
    else:
        # all good
        pass
    return
def check_l3_options_soil(cfg, messages):
    """ Check the entries of the Soil section."""
    if "Soil" not in list(cfg.keys()):
        msg = "No [Soil] section in control file"
        messages["WARNING"].append(msg)
        return
    # check the numbers
    for item in ["BulkDensity", "OrganicContent"]:
        if item in cfg["Soil"]:
            opt =  cfg["Soil"][item]
            if isinstance(float(pfp_utils.strip_non_numeric(opt)), numbers.Number):
                pass
            else:
                msg = item + " (" + opt + ") is not a number"
                messages["ERROR"].append(msg)
        else:
            msg = "Required entry " + item + " missing from Soil section"
            messages["ERROR"].append(msg)
    return
def check_l5_controlfile(cfg):
    """
    Purpose:
     Check the L5 control file to make sure it contains all information
     needed to run L5 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: October 2021
    """
    ok = True
    # initialise the messages dictionary
    messages = {"ERROR":[], "WARNING": [], "INFO": [], "DEBUG": [], "RESULT": "ignore"}
    # check to see if both cpd_filename and ustar_threshold section exist
    if "ustar_threshold"in cfg:
        if "cpd_filename" in cfg["Files"]:
            msg = "ustar_threshold section and Files/cpd_filename present"
            messages["ERROR"].append(msg)
    display_messages_interactive(messages)
    if len(messages["ERROR"]) > 0:
        ok = False
    return ok
def check_l6_controlfile(cfg):
    """
    Purpose:
     Check the L6 control file to make sure it contains all information
     needed to run L6 and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: July 2022
    """
    ok = True
    # initialise the messages dictionary
    messages = {"ERROR":[], "WARNING": [], "INFO": [], "DEBUG": [], "RESULT": "ignore"}
    l6_check_files(cfg, messages)
    l6_check_options(cfg, messages)
    l6_check_ecosystemrespiration(cfg, messages)
    l6_check_netecosystemexchange(cfg, messages)
    l6_check_grossprimaryproductivity(cfg, messages)
    # check if we are running in interactive mode and display messages accordingly
    opt = pfp_utils.get_keyvaluefromcf(cfg, ["Options"], "call_mode", default="interactive")
    if opt.lower() == "interactive":
        display_messages_interactive(messages)
    else:
        display_messages_batch(messages)
    if len(messages["ERROR"]) > 0:
        ok = False
    return ok
def check_windrose_controlfile(cfg):
    """
    Purpose:
     Check the windrose plotting control file to make sure it contains all
     information needed to plot the windroses and that all information is correct.
    Usage:
    Side effects:
    Author: PRI
    Date: June 2022
    """
    ok = True
    # initialise the messages dictionary
    messages = {"ERROR":[], "WARNING": [], "INFO": []}
    check_windrose_files_section(cfg, messages)
    check_windrose_options_section(cfg, messages)
    check_windrose_variables_section(cfg, messages)
    display_messages_interactive(messages)
    if len(messages["ERROR"]) > 0:
        ok = False
    return ok
def check_windrose_files_section(cfg, messages):
    """ Check the Files section in the windrose control file."""
    # check the Files section is present
    if "Files" not in cfg:
        msg = "No Files section in control file"
        messages["ERROR"].append(msg)
        return
    # check the required entries are in the Files section
    for item in ["plot_path", "file_path", "in_filename"]:
        if item not in cfg["Files"]:
            msg = item + " not in Files section"
            messages["ERROR"].append(msg)
            return
    # check the directories and the input file exist
    if not os.path.isdir(cfg["Files"]["plot_path"]):
        msg = "Directory " + cfg["Files"]["plot_path"] + " does not exist"
        messages["ERROR"].append(msg)
        return
    if not os.path.isdir(cfg["Files"]["file_path"]):
        msg = "Directory " + cfg["Files"]["file_path"] + " does not exist"
        messages["ERROR"].append(msg)
    else:
        if not os.path.isfile(os.path.join(cfg["Files"]["file_path"],
                                           cfg["Files"]["in_filename"])):
            msg = cfg["Files"]["in_filename"] + " not found in " + cfg["Files"]["file_path"]
            messages["ERRORS"].append(msg)
    return
def check_windrose_options_section(cfg, messages):
    """ Check the Options section in the windrose control file."""
    # check the Options section is present
    if "Options" not in cfg:
        msg = "No Options section in control file"
        messages["ERROR"].append(msg)
        return
    # check the required entries are in the Options section
    for item in ["number_sectors", "number_speed_bins", "speed_bin_width", "Fsd_threshold"]:
        if item not in cfg["Options"]:
            msg = item + " not in Options section"
            messages["ERROR"].append(msg)
            return
    # check the Options entries make sense
    number_sectors = int(cfg["Options"]["number_sectors"])
    if ((number_sectors < 2) or (number_sectors > 20)):
        msg = "number_sectors must between 2 and 20"
        messages["ERROR"].append(msg)
    number_speed_bins = int(cfg["Options"]["number_speed_bins"])
    if ((number_speed_bins < 2) or (number_speed_bins > 10)):
        msg = "Number of speed bins must be between 2 and 10"
        messages["ERROR"].append(msg)
    speed_bin_width = int(cfg["Options"]["speed_bin_width"])
    if ((speed_bin_width < 1) or (speed_bin_width > 5)):
        msg = "Speed bin width must be between 1 and 5 m/s"
        messages["ERROR"].append(msg)
    Fsd_threshold = int(cfg["Options"]["Fsd_threshold"])
    if ((Fsd_threshold < -10) or (Fsd_threshold > 10)):
        msg = "Fsd threshold must be between -10 and 10 W/m^2"
        messages["ERROR"].append(msg)
    return
def check_windrose_variables_section(cfg, messages):
    """ Check the Variables section of the windrose control file."""
    # check the Variables section is present
    if "Variables" not in cfg:
        msg = "No Variables section in control file"
        messages["ERROR"].append(msg)
        return
    # check the required entries are in the Variables section
    for item in ["Fsd", "Wd", "Ws"]:
        if item not in cfg["Variables"]:
            msg = item + " not in Variables section"
            messages["ERROR"].append(msg)
            return
    # check each entry in the Variables section
    for item in ["Fsd", "Wd", "Ws"]:
        if "name" not in cfg["Variables"][item]:
            msg = item + " does not have required key 'name'"
            messages["ERROR"].append(msg)
    return
def display_messages_batch(messages):
    for msg_type in list(messages.keys()):
        if (len(messages[msg_type]) == 0):
            continue
        for msg in messages[msg_type]:
            if msg_type == "ERROR":
                logger.error("!!!!!")
                logger.error(msg)
                logger.error("!!!!!")
                raise RuntimeError(msg)
            elif msg_type == "WARNING":
                logger.warning(msg)
            elif msg_type == "INFO":
                logger.info(msg)
            elif msg_type == "RESULT":
                pass
            else:
                raise RuntimeError("display_messages_batch: Unrecognised message in messages")
    return
def display_messages_interactive(messages, mode="Close"):
    # gather variable error messages into a single list
    error_messages = []
    if len(messages["ERROR"]) > 0:
        logger.error("!!!!!")
        for n, item in enumerate(messages["ERROR"]):
            logger.error(item)
            error_messages.append(item)
        logger.error("!!!!!")
    if len(messages["WARNING"]) > 0:
        for item in messages["WARNING"]:
            logger.warning(item)
    for item in messages["INFO"]:
        logger.info(item)
    # convert error list to a comma separated string
    if len(error_messages) > 0:
        msg = "The following errors were found in the control file:\n\n"
        for item in error_messages[:-1]:
            msg += item + "\n"
        msg += error_messages[-1] + "\n\n"
        msg += "Fix the errors, close this window and run again."
        # put up the message box
        if mode == "Close":
            msgbox = pfp_gui.MsgBox_Close(msg, title="Errors")
            messages["RESULT"] = msgbox.execute()
        elif mode == "CloseOrIgnore":
            msgbox = pfp_gui.MsgBox_CloseOrIgnore(msg, title="Errors")
            messages["RESULT"] = msgbox.execute()
        else:
            msg = "Unrecognised mode in display_messages_interactive()"
            logger.error(msg)
            messages["RESULT"] = "close"
    return
def l1_check_files(cfg, std, messages):
    # check the Files section exists
    if ("Files" in cfg):
        # check file_path is in the Files section
        if "file_path" in cfg["Files"]:
            file_path = cfg["Files"]["file_path"]
            # check file_path directory exists
            if os.path.isdir(file_path):
                pass
            else:
                msg = "Files: " + file_path + " is not a directory"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'file_path' not in section"
            messages["ERROR"].append(msg)
        # check in_filename is in the Files section
        if "in_filename" in cfg["Files"]:
            file_names = cfg["Files"]["in_filename"]
            file_names = file_names.split(",")
            for file_name in file_names:
                file_parts = os.path.splitext(file_name)
                # check the file type is supported
                if (file_parts[-1].lower() in  [".xls", ".xlsx", ".csv"]):
                    file_uri = os.path.join(file_path, file_name)
                    if os.path.isfile(file_uri):
                        pass
                    else:
                        msg = "Files: " + file_name + " not found"
                        messages["ERROR"].append(msg)
                else:
                    msg = "Files: " + file_name + " doesn't end with .xls, .xlsx or .csv"
                    messages["ERROR"].append(msg)
        else:
            msg = "Files: 'in_filename' not in section"
            messages["ERROR"].append(msg)
        # check in_firstdatarow is in the Files section
        if "in_firstdatarow" in cfg["Files"]:
            for item in cfg["Files"]["in_firstdatarow"].split(","):
                # check to see if in_firdtdatarow is an integer
                try:
                    i = int(item)
                except:
                    msg = "Files: 'in_firstdatarow' is not an integer"
                    messages["ERROR"].append(msg)
        # check in_headerrow is in the Files section
        if "in_headerrow" in cfg["Files"]:
            for item in cfg["Files"]["in_headerrow"].split(","):
                # check to see if in_heafderrow is an integer
                try:
                    i = int(item)
                except:
                    msg = "Files: 'in_headerrow' is not an integer"
                    messages["ERROR"].append(msg)
        # check the output file type
        if "out_filename" in cfg["Files"]:
            file_name = cfg["Files"]["out_filename"]
            file_parts = os.path.splitext(file_name)
            if (file_parts[-1].lower() in [".nc"]):
                pass
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
    else:
        msg = "'Files' section not in control file"
        messages["ERROR"].append(msg)
    return
def l1_check_global_attributes(cfg, std, messages):
    # check the 'Global' section exists
    if "Global" in cfg:
        # check the required global attributes exist
        l1_check_global_required(cfg, std, messages)
        # check the forced global attributes
        l1_check_global_forced(cfg, std, messages)
        # check the recommended global attributes
        l1_check_global_recommended(cfg, std, messages)
    return
def l1_check_global_required(cfg, std, messages):
    # check the global attributes
    required = std["Global"]["Required"]
    cfg_global = sorted(list(cfg["Global"].keys()))
    # check the required global attributes are present
    for item in required:
        if item not in cfg_global:
            msg = "Global: " + item + " not in section (required)"
            messages["ERROR"].append(msg)
    # check time step is present and makes sense
    if "time_step" in cfg["Global"]:
        try:
            ts = int(cfg["Global"]["time_step"])
        except ValueError:
            msg = "Global: 'time_step' is not a number"
            messages["ERROR"].append(msg)
        if ts not in [15, 20, 30, 60]:
            msg = "Global : 'time_step' must be 15, 20, 30 or 60"
            messages["ERROR"].append(msg)
    # check latitude is present and makes sense
    if "latitude" in cfg["Global"]:
        try:
            lat = float(cfg["Global"]["latitude"])
            if lat < -90.0 or lat > 90.0:
                msg = "Global: 'latitude' must be between -90 and 90"
                messages["ERROR"].append(msg)
        except ValueError:
            msg = "Global: 'latitude' is not a number"
            messages["ERROR"].append(msg)
    # check longitude is present and makes sense
    if "longitude" in cfg["Global"]:
        try:
            lon = float(cfg["Global"]["longitude"])
            if lon < -180.0 or lat > 180.0:
                msg = "Global: 'longitude' must be between -180 and 180"
                messages["ERROR"].append(msg)
        except ValueError:
            msg = "Global: 'longitude' is not a number"
            messages["ERROR"].append(msg)
    return
def l1_check_global_forced(cfg, std, messages):
    forced = std["Global"]["Forced"]
    # force global attributes that have defined values
    for item in forced:
        cfg["Global"][item] = forced[item]
        msg = "Global: setting " + item + " to " + forced[item]
        messages["DEBUG"].append(msg)
    # and do the time zone
    lon = float(cfg["Global"]["longitude"])
    lat = float(cfg["Global"]["latitude"])
    tf = timezonefinder.TimezoneFinder()
    time_zone = tf.timezone_at(lng=lon, lat=lat)
    if "time_zone" in cfg["Global"]:
        if cfg["Global"]["time_zone"] != time_zone:
            cfg["Global"]["time_zone"] = time_zone
            msg = "Global: existing time zone replaced with " + time_zone
            messages["WARNING"].append(msg)
        else:
            pass
    else:
        cfg["Global"]["time_zone"] = time_zone
    return
def l1_check_global_recommended(cfg, std, messages):
    recommended = std["Global"]["Recommended"]
    cfg_global = sorted(list(cfg["Global"].keys()))
    # check recommended global attributes
    for item in recommended:
        if item not in cfg_global:
            msg = "Global: recommended global attribute " + item + " not found"
            messages["WARNING"].append(msg)
    return
def l1_check_variables_sections(cfg, std, cfg_label, std_label, messages):
    var_keys = list(cfg["Variables"][cfg_label].keys())
    # check we have an 'Attr' section, remove variable if absent
    if ("Attr" in var_keys):
        var_attrs = list(cfg["Variables"][cfg_label]["Attr"].keys())
        if "long_name" in var_attrs:
            pass
        else:
            msg = cfg_label + ": no long_name variable attribute"
            messages["ERROR"].append(msg)
        # check statistic_type
        if "statistic_type" in var_attrs:
            l1_check_variables_statistic_type(cfg, std, cfg_label, std_label, messages)
            # check units
            if "units" in var_attrs:
                l1_check_variables_units(cfg, std, cfg_label, std_label, messages)
                l1_make_variables_attributes_consistent(cfg, std, cfg_label, std_label, messages)
                if "standard_name" in var_attrs:
                    l1_check_variables_standard_name(cfg, std, cfg_label, std_label, messages)
                else:
                    pass
            else:
                msg = cfg_label + ": no units variable attribute"
                messages["ERROR"].append(msg)
        else:
            msg = cfg_label + ": no statistic_type variable attribute"
            messages["ERROR"].append(msg)
        # check height given for CO2 value
        if "CO2" in cfg_label:
            l1_check_variables_height(cfg, cfg_label, messages)
        else:
            pass
    else:
        msg = cfg_label + ": 'Attr' section missing"
        messages["ERROR"].append(msg)
    # check the file extension, only xls, xlsx or csv allowed
    file_parts = os.path.splitext(cfg["Files"]["in_filename"])
    if ((file_parts[-1].lower() == "xls") or
        (file_parts[-1].lower() == "xlsx")):
        if (("xl" not in var_keys) or ("Function" not in var_keys)):
            msg = cfg_label + ": 'xl' section missing"
            messages["ERROR"].append(msg)
    elif (file_parts[-1].lower() == "csv"):
        if (("csv" not in var_keys) or ("Function" not in var_keys)):
            msg = cfg_label + ": 'csv' section missing"
            messages["ERROR"].append(msg)
    else:
        pass
    # check any use of Function
    if "Function" in var_keys:
        # check 'func' key is in the 'Function' section
        if "func" in cfg["Variables"][cfg_label]["Function"]:
            # get the function name
            function_string = cfg["Variables"][cfg_label]["Function"]["func"]
            function_name = function_string.split("(")[0]
            # get a list of function names in pfp_func_units and pfp_func_stats
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
            # check the function name is implemented
            if function_name not in implemented_functions:
                msg = " Skipping " + cfg_label + " (function " + function_name
                msg += " not implemented)"
                messages["ERROR"].append(msg)
            # check the arguments are being read in
            else:
                function_args = function_string[function_string.index("(")+1:-1].split(",")
                nargs = len(function_args)
                if function_name in ["Linear"]:
                    nargs = 1
                for item in function_args[:nargs]:
                    if item not in list(cfg["Variables"].keys()):
                        msg = " Skipping " + cfg_label + " (function argument '"
                        msg += item + "' not found)"
                        messages["ERROR"].append(msg)
                    else:
                        pass
        else:
            msg = cfg_label + ": 'func' not found in 'Function' subsection"
            messages["ERROR"].append(msg)
    return
def l1_check_input_labels(cfg, messages):
    #
    file_parts = os.path.splitext(cfg["Files"]["in_filename"])
    if ("xls" in file_parts[-1].lower()):
        source = "xl"
    elif ("csv" in file_parts[-1].lower()):
        source = "csv"
    else:
        msg = "Unexpected input source (" + file_parts[-1].lower() + ")"
        raise RuntimeError(msg)
    # check each variable has the necessary subsections
    input_labels = []
    cfg_labels = list(cfg["Variables"].keys())
    for cfg_label in cfg_labels:
        if ((source not in cfg["Variables"][cfg_label]) and
            ("Function" not in cfg["Variables"][cfg_label])):
            msg = "Neither '" + source + "' nor 'Function' found in " + cfg_label
            messages["ERROR"].append(msg)
        if "Attr" not in cfg["Variables"][cfg_label]:
            msg = "'Attr' subsction not found in " + cfg_label
            messages["ERROR"].append(msg)
        if source in cfg["Variables"][cfg_label]:
            if "name" in cfg["Variables"][cfg_label][source]:
                input_labels.append(cfg["Variables"][cfg_label][source]["name"])
            else:
                msg = "'name' not found in " + cfg_label
                messages["ERROR"].append(msg)
    # check for duplicate input labels
    duplicate_labels = [l for l in set(input_labels) if input_labels.count(l) > 1]
    if len(duplicate_labels) > 0:
        for duplicate_label in duplicate_labels:
            nc_duplicate_labels = []
            nc_duplicate_sheets = []
            for cfg_label in cfg_labels:
                if source in cfg["Variables"][cfg_label]:
                    if "name" in cfg["Variables"][cfg_label][source]:
                        if cfg["Variables"][cfg_label][source]["name"] == duplicate_label:
                            nc_duplicate_labels.append(cfg_label)
                            nc_duplicate_sheets.append(cfg["Variables"][cfg_label][source]["sheet"])
            if nc_duplicate_sheets[0] == nc_duplicate_sheets[1]:
                msg = "Duplicate input label " + duplicate_label + " used for "
                msg += ",".join(nc_duplicate_labels)
                messages["WARNING"].append(msg)
    return
def l1_check_irga_sonic_type(cfg, messages):
    """
    Purpose:

    Usage:

    Author: PRI
    Date: November 2022
    """
    cfg_labels = sorted(list(cfg["Variables"].keys()))
    # IRGA signal strengths
    signal_labels = ["Signal_CO2", "Signal_H2O"]
    # PFP covariances
    h2o_covars = ["UxA", "UyA", "UzA"]
    co2_covars = ["UxC", "UyC", "UzC"]
    t_covars = ["UxT", "UyT", "UzT"]
    m_covars = ["UxUy", "UxUz", "UyUz"]
    # anything with 'IRGA' in the variable name
    irga_labels = [l for l in cfg_labels if "_IRGA" in l]
    # anything with 'SONIC' in the variable name
    sonic_labels = [l for l in cfg_labels if "_SONIC" in l]
    # fluxes from EddyPro, EasyFlux and the like
    fco2_labels = [l for l in cfg_labels if l[0:4] == "Fco2"]
    sco2_labels = [l for l in cfg_labels if l[0:4] == "Sco2"]
    fh2o_labels = [l for l in cfg_labels if l[0:4] == "Fh2o"]
    fe_labels = [l for l in cfg_labels if l[0:2] == "Fe"]
    fh_labels = [l for l in cfg_labels if l[0:2] == "Fh" and l[0:4] != "Fh2o"]
    fm_labels = [l for l in cfg_labels if l[0:2] == "Fm"]
    # lists of variables by instrument
    # fast IRGAs e.g. Li-7500RS etc used for turbulence measurements
    fast_irga_only_labels = irga_labels + signal_labels
    # slow IRGAs e.g. Li-840 used for profile measurements
    slow_irga_only_labels = sco2_labels
    # sonic anemometer only
    sonic_only_labels = sonic_labels + t_covars + m_covars + fh_labels + fm_labels
    # sonic and fast IRGA
    sonic_irga_labels = h2o_covars + co2_covars + fco2_labels + fh2o_labels + fe_labels
    # all sonic or IRGA related variables
    all_sonic_irga_labels = fast_irga_only_labels + slow_irga_only_labels + sonic_only_labels + sonic_irga_labels
    # check to see if we have any sonic and IRGA related variables
    if set(cfg_labels).isdisjoint(set(all_sonic_irga_labels)):
        # no sonic or IRGA variables in control file so skip checks
        return
    # call the check routines
    l1_check_irga_only(cfg, fast_irga_only_labels, messages)
    l1_check_irga_only(cfg, slow_irga_only_labels, messages)
    l1_check_sonic_only(cfg, sonic_only_labels, messages)
    l1_check_sonic_irga(cfg, sonic_irga_labels, messages)
    return
def l1_check_irga_only(cfg, irga_only_labels, messages):
    """ Check instrument attribute of variables that depend only on the IRGA"""
    #if len(irga_only_labels) == 0:
        #return
    open_path_irgas = list(c.instruments["irgas"]["open_path"].keys())
    closed_path_irgas = list(c.instruments["irgas"]["closed_path"].keys())
    known_irgas = open_path_irgas + closed_path_irgas
    cfg_labels = sorted(list(cfg["Variables"].keys()))
    for label in list(irga_only_labels):
        if label not in cfg_labels:
            irga_only_labels.remove(label)
    if len(irga_only_labels) == 0:
        return
    irga_check = {}
    for label in irga_only_labels:
        if "instrument" in cfg["Variables"][label]["Attr"]:
            irga_type = cfg["Variables"][label]["Attr"]["instrument"]
            if irga_type in known_irgas:
                # IRGA type is something we know
                if irga_type not in irga_check:
                    irga_check[irga_type] = []
                irga_check[irga_type].append(label)
            else:
                msg = "Unknown IRGA type (" + irga_type + ") for " + label
                messages["ERROR"].append(msg)
        else:
            msg = "'instrument' attribute missing for " + label
            messages["ERROR"].append(msg)
    irga_types = list(irga_check.keys())
    if len(irga_types) == 0:
        msg = "No known irga types found"
        messages["ERROR"].append(msg)
    elif len(irga_types) == 1:
        pass
    else:
        msg = "More than 1 IRGA type specified (" + ",".join(irga_types) + ")"
        messages["ERROR"].append(msg)
        for irga_type in irga_types:
            msg = irga_type + " is used for " + ",".join(irga_check[irga_type])
            messages["ERROR"].append(msg)
    return
def l1_check_sonic_only(cfg, sonic_only_labels, messages):
    """ Check instrument attribute of variables that depend only on the sonic."""
    #if len(sonic_only_labels) == 0:
        #return
    known_sonics = list(c.instruments["sonics"].keys())
    cfg_labels = sorted(list(cfg["Variables"].keys()))
    for label in list(sonic_only_labels):
        if label not in cfg_labels:
            sonic_only_labels.remove(label)
    if len(sonic_only_labels) == 0:
        return
    sonic_check = {}
    for label in sonic_only_labels:
        if "instrument" in cfg["Variables"][label]["Attr"]:
            sonic_type = cfg["Variables"][label]["Attr"]["instrument"]
            if sonic_type in known_sonics:
                # sonic type is something we know
                if sonic_type not in sonic_check:
                    sonic_check[sonic_type] = []
                sonic_check[sonic_type].append(label)
            else:
                msg = "Unknown sonic type (" + sonic_type + ") for " + label
                messages["ERROR"].append(msg)
        else:
            msg = "'instrument' attribute missing for " + label
            messages["ERROR"].append(msg)
    sonic_types = list(sonic_check.keys())
    if len(sonic_types) == 0:
        msg = "No known sonic types found"
        messages["ERROR"].append(msg)
    elif len(sonic_types) == 1:
        pass
    else:
        msg = "More than 1 sonic type specified (" + ",".join(sonic_types) + ")"
        messages["ERROR"].append(msg)
        for sonic_type in sonic_types:
            msg = sonic_type + " is used for " + ",".join(sonic_check[sonic_type])
            messages["ERROR"].append(msg)
    return
def l1_check_sonic_irga(cfg, sonic_irga_labels, messages):
    """
    Purpose:
     Check the 'instrument' attribute of all variables associated with the sonic
     and the fast IRGA and make sure only one sonic type and one IRGA type are
     specified from the lists of known sonics and IRGAs.
    Usage:
     l1_check_sonic_irga(cfg, sonic_irga_labels, messages)
     where cfg is a control file
           sonic_irga_labels is a list of variables measured using the sonic
                             and the fast IRGA
           messages is a dictionary for error, warning and info messages
    Author: PRI
    Date: November 2022
    """
    #if len(sonic_irga_labels) == 0:
        #return
    open_path_irgas = list(c.instruments["irgas"]["open_path"].keys())
    closed_path_irgas = list(c.instruments["irgas"]["closed_path"].keys())
    known_irgas = open_path_irgas + closed_path_irgas
    known_sonics = list(c.instruments["sonics"].keys())
    cfg_labels = sorted(list(cfg["Variables"].keys()))
    for sonic_irga_label in list(sonic_irga_labels):
        if sonic_irga_label not in cfg_labels:
            sonic_irga_labels.remove(sonic_irga_label)
    if len(sonic_irga_labels) == 0:
        return
    sonic_check = {}
    irga_check = {}
    for sonic_irga_label in sonic_irga_labels:
        if "instrument" in cfg["Variables"][sonic_irga_label]["Attr"]:
            instrument_type = cfg["Variables"][sonic_irga_label]["Attr"]["instrument"]
            if "," in instrument_type:
                # instrument is a string with comma separated values
                itl = [l.strip() for l in instrument_type.split(",")]
                if len(itl) == 2:
                    for item in itl:
                        if ((item not in known_sonics) and (item not in known_irgas)):
                            msg = "Unrecognised instrument (" + item + ") for " + sonic_irga_label
                            messages["ERROR"].append(msg)
                            continue
                        if item in known_sonics:
                            if item not in sonic_check:
                                sonic_check[item] = []
                            sonic_check[item].append(sonic_irga_label)
                        if item in known_irgas:
                            if item not in irga_check:
                                irga_check[item] = []
                            irga_check[item].append(sonic_irga_label)
                else:
                    msg = "'instrument' attribute must have 2 entries separated by a comma, got "
                    msg += instrument_type + " for " + sonic_irga_label
                    messages["ERROR"].append(msg)
            elif ((instrument_type.strip() in known_sonics) and
                  (instrument_type.strip() in known_irgas)):
                if instrument_type.strip() not in sonic_check:
                    sonic_check[instrument_type.strip()] = []
                sonic_check[instrument_type.strip()].append(sonic_irga_label)
                if instrument_type.strip() not in irga_check:
                    irga_check[instrument_type.strip()] = []
                irga_check[instrument_type.strip()].append(sonic_irga_label)
            else:
                # instrument attribute is something we can't handle
                msg = "'instrument' attribute must have 2 entries separated by a comma, got "
                msg += instrument_type + " for " + sonic_irga_label
                messages["ERROR"].append(msg)
        else:
            msg = "'instrument' attribute missing for " + sonic_irga_label
            messages["ERROR"].append(msg)
    sonic_types = list(sonic_check.keys())
    if len(sonic_types) == 0:
        msg = "No known sonic types found"
        messages["ERROR"].append(msg)
    elif len(sonic_types) == 1:
        cfg["Global"]["sonic_type"] = str(sonic_types[0])
        msg = " Sonic type set to " + cfg["Global"]["sonic_type"]
        logger.info(msg)
    else:
        msg = "More than 1 sonic type specified (" + ",".join(sonic_types) + ")"
        messages["ERROR"].append(msg)
        for sonic_type in sonic_types:
            msg = sonic_type + " is used for " + ",".join(sonic_check[sonic_type])
            messages["ERROR"].append(msg)
    irga_types = list(irga_check.keys())
    if len(irga_types) == 0:
        msg = "No known IRGA types found"
        messages["ERROR"].append(msg)
    elif len(irga_types) == 1:
        cfg["Global"]["irga_type"] = str(irga_types[0])
        msg = " IRGA type set to " + cfg["Global"]["irga_type"]
        logger.info(msg)
    else:
        msg = "More than 1 IRGA type specified (" + ",".join(irga_types) + ")"
        messages["ERROR"].append(msg)
        for irga_type in irga_types:
            msg = irga_type + " is used for " + ",".join(irga_check[irga_type])
            messages["ERROR"].append(msg)
    return
def l1_check_nc_labels(cfg, messages):
    nc_labels = list(cfg["Variables"].keys())
    duplicate_labels = [l for l in set(nc_labels) if nc_labels.count(l) > 1]
    if len(duplicate_labels) == 0:
        return
    for duplicate_label in duplicate_labels:
        msg = "Duplicate netCDF label " + duplicate_label + " found "
        msg += str(duplicate_labels.count(duplicate_label)) + " times"
        messages["ERROR"].append(msg)
    return
def l1_check_variables_height(cfg, cfg_label, messages):
    cfg_attr = cfg["Variables"][cfg_label]["Attr"]
    if "height" in cfg_attr:
        height = pfp_utils.strip_non_numeric(cfg_attr["height"])
        if pfp_utils.is_number(height):
            pass
        else:
            msg = cfg_label + ": 'height' attribute not a number"
            messages["ERROR"].append(msg)
    else:
        msg = cfg_label + ": no 'height' attribute found"
        messages["ERROR"].append(msg)
    return
def l1_check_variables_statistic_type(cfg, std, cfg_label, std_label, messages):
    cfg_attr = cfg["Variables"][cfg_label]["Attr"]
    std_var = std["Variables"][std_label]
    statistic_types = sorted(list(std_var.keys()))
    cfg_stat_type = cfg_attr["statistic_type"]
    if cfg_stat_type not in statistic_types:
        msg = cfg_label + ": unrecognised statistic_type (" + cfg_stat_type + ")"
        messages["ERROR"].append(msg)
    return
def l1_check_variables_units(cfg, std, cfg_label, std_label, messages):
    cfg_attr = cfg["Variables"][cfg_label]["Attr"]
    cfg_stat_type = cfg_attr["statistic_type"]
    if cfg_stat_type in std["Variables"][std_label]:
        std_stat_type = std["Variables"][std_label][cfg_stat_type]
        std_units = sorted(list(std_stat_type.keys()))
        cfg_units = cfg_attr["units"]
        if cfg_units not in std_units:
            msg = cfg_label + ": unrecognised units (" + cfg_units + ")"
            messages["ERROR"].append(msg)
    return
def l1_check_variables_standard_name(cfg, std, cfg_label, std_label, messages):
    cfg_attr = cfg["Variables"][cfg_label]["Attr"]
    cfg_units = cfg_attr["units"]
    cfg_stat_type = cfg_attr["statistic_type"]
    if cfg_stat_type in std["Variables"][std_label]:
        std_stat_type = std["Variables"][std_label][cfg_stat_type]
        if cfg_units in std_stat_type:
            if (("standard_name" in cfg_attr) and
                ("standard_name" not in std_stat_type[cfg_units])):
                msg = cfg_label + ": standard_name not allowed, removing..."
                messages["WARNING"].append(msg)
                cfg["Variables"][cfg_label]["Attr"].pop("standard_name")
            else:
                pass
        else:
            msg = cfg_label + ": unrecognised units (" + cfg_units + ")"
            if msg not in messages["ERROR"]:
                messages["ERROR"].append(msg)
    return
def l1_make_variables_attributes_consistent(cfg, std, cfg_label, std_label, messages):
    cfg_attr = cfg["Variables"][cfg_label]["Attr"]
    cfg_units = cfg_attr["units"]
    cfg_stat_type = cfg_attr["statistic_type"]
    if cfg_stat_type in std["Variables"][std_label]:
        std_stat_type = std["Variables"][std_label][cfg_stat_type]
        if cfg_units in std_stat_type:
            for item in std_stat_type[cfg_units]:
                if (item not in cfg_attr):
                    # attribute not found so add it
                    msg = cfg_label + ": attribute (" + item + ") not found, adding..."
                    messages["WARNING"].append(msg)
                    cfg_attr[item] = std_stat_type[cfg_units][item]
                elif (cfg_attr[item] != std_stat_type[cfg_units][item]):
                    # cfg attribute not the same as the std attribute, replace it
                    msg = cfg_label + ": invalid " + item + " (" + cfg_attr[item] + ")"
                    msg += ", replacing..."
                    messages["WARNING"].append(msg)
                    cfg_attr[item] = std_stat_type[cfg_units][item]
                else:
                    pass
        else:
            msg = cfg_label + ": unrecognised units (" + cfg_units + ")"
            if msg not in messages["ERROR"]:
                messages["ERROR"].append(msg)
    return
def l1_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L1 control file to update the syntax from earlier OFQC/PFP versions
     to the syntax used by this version.
    Usage:
     result = pfp_compliance.l1_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L1 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: February 2020
    """
    # initialise the return logical
    ok = True
    # update control file not applied for L1 nc2csv_oneflux
    if cfg["level"] in ["L1_oneflux"]:
        return ok
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard",
                               "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # check to see if we can load the check_l1_controlfiles.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        chkname = os.path.join(base_path, "controlfiles", "standard",
                               "check_l1_controlfile.txt")
        chk = pfp_io.get_controlfilecontents(chkname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + chkname
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L1 control file syntax"
    # clean up the options section
    cfg = update_cfg_options(cfg, std, call_mode=call_mode)
    cfg = update_cfg_global_attributes(cfg, std)
    cfg = update_cfg_variables_deprecated(cfg, std)
    cfg = update_cfg_variables_rename(cfg, std)
    cfg = l1_update_cfg_variables_attributes(cfg, std, chk)
    cfg = l1_update_cfg_variables_function(cfg, std)
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def update_cfg_global_attributes(cfg, std):
    """
    Purpose:
     Update the global attributes according to the rules in the standard control file.
    Usage:
    Author: PRI
    Date: May 2020
          June 2021 rewrite for DSA compliance, phase 1
    """
    stdga = std["Global_attributes"]
    # check for the essential global attributes
    essentials = pfp_utils.string_to_list(stdga["essentials"]["global"])
    for gattr in essentials:
        if gattr not in cfg["Global"]:
            cfg["Global"][gattr] = ""
    # remove deprecated global attributes
    deprecated = pfp_utils.string_to_list(stdga["deprecated"]["global"])
    for gattr in deprecated:
        if gattr in cfg["Global"]:
            cfg["Global"].pop(gattr)
    # rename global attributes
    rename_exact = list(stdga["rename_exact"].keys())
    for old_name in rename_exact:
        if old_name in cfg["Global"]:
            new_name = stdga["rename_exact"][old_name]
            cfg["Global"][new_name] = cfg["Global"].pop(old_name)
    # add or change global attributes as required
    force = list(stdga["force"].keys())
    for item in force:
        cfg["Global"][item] = stdga["force"][item]
    return cfg

def update_cfg_syntax(cfg, std):
    """
    Purpose:
     Update an L1 control file from the old-style (pre PFP V1.0) syntax to the
     new-style syntax (post PFP V1.0).
    Usage:
    Side effects:
     Returns a modified control file object.
    Author: PRI
    Date: 9th May 2020, the day after my 64th birthday!
    """
    strip_list = ['"', "'", "[", "]"]
    for key1 in cfg:
        if key1 in ["level", "GUI"]:
            continue
        elif key1 in ["Files", "Global", "Soil", "Massman", "ustar_threshold"]:
            for key2 in cfg[key1]:
                cfg2 = cfg[key1][key2]
                cfg2 = parse_cfg_values(key2, cfg2, strip_list)
                cfg[key1][key2] = cfg2
        elif key1 in ["Options"]:
            if cfg["level"] in list(std["Options"].keys()):
                options = str(std["Options"][cfg["level"]])
                options = pfp_utils.string_to_list(options.replace("\n", ""))
                for key2 in cfg[key1]:
                    if key2 in options:
                        cfg2 = cfg[key1][key2]
                        cfg2 = parse_cfg_values(key2, cfg2, strip_list)
                        cfg[key1][key2] = cfg2
                    else:
                        del cfg[key1][key2]
            else:
                msg = " No entry for level " + cfg["level"] + " in std control file"
                logger.warning(msg)
        elif key1 in ["Imports"]:
            for key2 in cfg[key1]:
                for key3 in cfg[key1][key2]:
                    cfg3 = cfg[key1][key2][key3]
                    cfg3 = parse_cfg_values(key3, cfg3, strip_list)
                    cfg[key1][key2][key3] = cfg3
        elif key1 in ["Variables", "Drivers", "Fluxes"]:
            for key2 in cfg[key1]:
                for key3 in cfg[key1][key2]:
                    cfg3 = cfg[key1][key2][key3]
                    if key3 in ["xl", "csv", "Attr"]:
                        # L1 control file
                        for key4 in cfg3:
                            # for keywords to lower case
                            if key4.lower() != key4:
                                cfg3[key4.lower()] = cfg3.pop(key4)
                            cfg[key1][key2][key3][key4.lower()] = parse_cfg_variables_value(key3, cfg3[key4.lower()])
                    if key3 in ["RangeCheck", "DependencyCheck", "DiurnalCheck", "ExcludeDates",
                                "CorrectWindDirection", "ApplyFco2Storage",
                                "MergeSeries", "AverageSeries",
                                "LowerCheck", "UpperCheck"]:
                        # L2, L3, L4 and L5 control files
                        for key4 in cfg3:
                            # force keywords to lower case
                            cfg3.rename(key4, key4.lower())
                            cfg4 = cfg3[key4.lower()]
                            cfg4 = parse_cfg_variables_value(key3, cfg4)
                            cfg[key1][key2][key3][key4.lower()] = cfg4
                    if key3 in ["ExcludeHours"]:
                        # L2, L3, L4 and L5 control files
                        for key4 in cfg3:
                            # force keywords to lower case
                            cfg3.rename(key4, key4.lower())
                            cfg4 = cfg3[key4.lower()]
                            cfg4 = parse_cfg_variables_value(key3, cfg4)
                            cfg[key1][key2][key3][key4.lower()] = cfg4
                    if key3 in ["GapFillFromAlternate", "GapFillFromClimatology",
                                "GapFillUsingMDS"]:
                        # L4 control file
                        for key4 in cfg3:
                            cfg4 = cfg3[key4]
                            for key5 in cfg4:
                                cfg4.rename(key5, key5.lower())
                                cfg5 = cfg4[key5.lower()]
                                cfg5 = parse_cfg_values(key5, cfg5, strip_list)
                                cfg[key1][key2][key3][key4][key5.lower()] = cfg5
                    if key3 in ["GapFillUsingSOLO", "GapFillLongSOLO", "GapFillUsingMDS",
                                "GapFillFromClimatology"]:
                        # L5 control file
                        for key4 in cfg3:
                            cfg4 = cfg[key1][key2][key3][key4]
                            for key5 in cfg4:
                                cfg4.rename(key5, key5.lower())
                                cfg5 = cfg4[key5.lower()]
                                cfg5 = parse_cfg_values(key5, cfg5, strip_list)
                                cfg[key1][key2][key3][key4][key5.lower()] = cfg5
                    if cfg["level"] in ["climatology", "cpd_barr", "cpd_mchugh"]:
                        # climatology, CPD (Barr), CPD (McHugh) control file
                        cfg[key1][key2][key3] = parse_cfg_values(key3, cfg3, strip_list)
        elif key1 in ["Plots"]:
            for key2 in cfg[key1]:
                title = parse_cfg_plots_title(cfg, key1, key2)
                cfg[key1].rename(key2, title)
                cfg2 = cfg[key1][title]
                for key3 in cfg2:
                    # force keywords to lower case
                    cfg2.rename(key3, key3.lower())
                    cfg3 = cfg2[key3.lower()]
                    cfg3 = parse_cfg_plots_value(key3, cfg3)
                    cfg[key1][title][key3.lower()] = cfg3
        else:
            del cfg[key1]
    return cfg

def l1_update_cfg_variables_attributes(cfg, std, chk):
    """
    Purpose:
     Update the variable attributes.
    Usage:
    Comments: There must be a better way to do this that avoids the double
              "for" loop.
    Author: PRI
    Date: May 2020
    """
    # list of essential variable attributes
    vattrs_essential = pfp_utils.string_to_list(std["Variables"]["essential"]["attributes"])
    stdvd = std["Variables"]["deprecated"]
    attributes_deprecated = pfp_utils.string_to_list(stdvd["attributes"])
    units_deprecated = pfp_utils.string_to_list(stdvd["units"])
    height_deprecated = pfp_utils.string_to_list(stdvd["height"])
    miscellaneous_deprecated = pfp_utils.string_to_list(stdvd["miscellaneous"])
    standard_name_deprecated = pfp_utils.string_to_list(stdvd["standard_name"])
    # list of standard attribute values
    cfg_labels = list(cfg["Variables"].keys())
    # add any essential variable attributes that are missing, deprecate those no longer used
    for label in cfg_labels:
        cfg_vattrs = list(cfg["Variables"][label]["Attr"].keys())
        for vattr in vattrs_essential:
            if vattr not in cfg_vattrs:
                cfg["Variables"][label]["Attr"][vattr] = label
        cfg_vattrs = list(cfg["Variables"][label]["Attr"].keys())
        for vattr in attributes_deprecated:
            if vattr in cfg_vattrs:
                del cfg["Variables"][label]["Attr"][vattr]
        cfg_vattrs = list(cfg["Variables"][label]["Attr"].keys())
        for vattr in cfg_vattrs:
            value = cfg["Variables"][label]["Attr"][vattr]
            if vattr == "units":
                if ((value in units_deprecated) or (len(str(value)) == 0)):
                    cfg["Variables"][label]["Attr"].pop(vattr)
            elif vattr == "height":
                if ((value in height_deprecated) or (len(str(value)) == 0)):
                    cfg["Variables"][label]["Attr"].pop(vattr)
            elif vattr == "standard_name":
                if ((value in standard_name_deprecated) or (len(str(value)) == 0)):
                    cfg["Variables"][label]["Attr"].pop(vattr)
            elif len(str(value)) == 0:
                cfg["Variables"][label]["Attr"].pop(vattr)
            else:
                if ((value in miscellaneous_deprecated) or (len(str(value)) == 0)):
                    cfg["Variables"][label]["Attr"].pop(vattr)
        cfg_vattrs = list(cfg["Variables"][label]["Attr"].keys())
        if "statistic_type" not in cfg_vattrs:
            if label[-3:] == "_Sd":
                cfg["Variables"][label]["Attr"]["statistic_type"] = "standard_deviation"
            elif label[-3:] == "_Vr":
                cfg["Variables"][label]["Attr"]["statistic_type"] = "variance"
            elif "Precip" in label:
                if cfg["Variables"][label]["Attr"]["units"] in ["mm"]:
                    cfg["Variables"][label]["Attr"]["statistic_type"] = "sum"
            else:
                cfg["Variables"][label]["Attr"]["statistic_type"] = "average"
        else:
            if cfg["Variables"][label]["Attr"]["statistic_type"] == "standard deviation":
                cfg["Variables"][label]["Attr"]["statistic_type"] = "standard_deviation"
    # coerce units into a standard form
    old_units = list(std["Variables"]["units_map"].keys())
    new_units = [std["Variables"]["units_map"][o] for o in old_units]
    ok_units = list(set(old_units + new_units))
    cfg_labels = list(cfg["Variables"].keys())
    for cfg_label in cfg_labels:
        if "units" not in cfg["Variables"][cfg_label]["Attr"]:
            continue
        cfg_units = cfg["Variables"][cfg_label]["Attr"]["units"]
        if cfg_units not in ok_units:
            msg = " Unrecognised units " + cfg_units + " for variable " + cfg_label
            logger.warning(msg)
            continue
        if cfg_units in old_units:
            # another horrible shim ...
            if cfg_units == "frac" and "Sws" in cfg_label:
                cfg["Variables"][cfg_label]["Attr"]["units"] = "m^3/m^3"
            elif cfg_units == "frac" and "RH" in cfg_label:
                cfg["Variables"][cfg_label]["Attr"]["units"] = "fraction"
            else:
                cfg["Variables"][cfg_label]["Attr"]["units"] = std["Variables"]["units_map"][cfg_units]
    # force some variable attributes to particular values
    cfg_labels = list(cfg["Variables"].keys())
    cfg_done = []
    chk_labels = list(chk["Variables"].keys())
    # exact matches first
    exact_matches = [l for l in cfg_labels if l in chk_labels]
    for cfg_label in exact_matches:
        l1_update_cfg_coerce_variable_attributes(cfg, chk, cfg_label, cfg_label)
        cfg_done.append(cfg_label)
    # then partial matches
    for chk_label in chk_labels:
        # partial matches with exact matches excluded
        lsl = len(chk_label)
        partial_matches = [l for l in cfg_labels
                           if l[:min([len(l),lsl])] == chk_label and
                           l not in exact_matches]
        for cfg_label in partial_matches:
            l1_update_cfg_coerce_variable_attributes(cfg, chk, cfg_label, chk_label)
            cfg_done.append(cfg_label)
    return cfg
def l1_update_cfg_coerce_variable_attributes(cfg, chk, cfg_label, chk_label):
    """
    Purpose:
     Coerce the variable attributes in the control file to the values
     in the standard file.
    Author: PRI
    Date: October 2021
    """
    # pointer to attributes in user control file
    cfg_attrs = cfg["Variables"][cfg_label]["Attr"]
    if "units" not in cfg_attrs:
        msg = cfg_label + " has no 'units' attribute"
        logger.warning(msg)
        return
    cfg_units = cfg_attrs["units"]
    # get the statistic type
    statistic_type = cfg_attrs["statistic_type"]
    if statistic_type not in chk["Variables"][chk_label]:
        msg = cfg_label + " unrecognised statistic_type (" + statistic_type + ")"
        logger.warning(msg)
        return
    # get a list of units for this variable and statistic type
    chk_units = list(chk["Variables"][chk_label][statistic_type].keys())
    # check variable units are in this list
    if cfg_units not in chk_units:
        msg = cfg_label + " has unrecognised units (" + cfg_units + ")"
        logger.warning(msg)
        return
    # get the attributes for this variable
    chk_attrs = chk["Variables"][chk_label][statistic_type][cfg_units]
    for chk_attr in chk_attrs:
        cfg_attrs[chk_attr] = chk_attrs[chk_attr]
    cfg["Variables"][cfg_label]["Attr"] = cfg_attrs
    return
def l1_update_cfg_variables_function(cfg, std):
    """
    Purpose:
     Updatte function names.
    Usage:
    Author: PRI
    Date: November 2021
    """
    old_function_names = list(std["Functions"].keys())
    cfg_labels = list(cfg["Variables"].keys())
    for cfg_label in cfg_labels:
        if "Function" in cfg["Variables"][cfg_label]:
            old_function = cfg["Variables"][cfg_label]["Function"]["func"]
            old_function_name = old_function.split("(")[0]
            if old_function_name in old_function_names:
                new_function_name = std["Functions"][old_function_name]
                new_function = old_function.replace(old_function_name, new_function_name)
                cfg["Variables"][cfg_label]["Function"]["func"] = new_function
    return cfg
def update_cfg_variables_deprecated(cfg, std):
    """
    Purpose:
     Remove deprecated variables from L1 control file.
    Usage:
    Author: PRI
    Date: May 2020
    """
    stdvd = std["Variables"]["deprecated"]
    deprecated = pfp_utils.string_to_list(stdvd["variables"])
    for item in ["Variables", "Drivers", "Fluxes"]:
        if item in cfg:
            labels = sorted(list(cfg[item].keys()))
            section_name = item
    for label in deprecated:
        if label in labels:
            cfg[section_name].pop(label)
    return cfg

def l2_check_files(cfg, messages):
    # check the Files section exists
    if ("Files" in cfg):
        # check file_path is in the Files section
        if "file_path" in cfg["Files"]:
            file_path = cfg["Files"]["file_path"]
            # check file_path directory exists
            if os.path.isdir(file_path):
                pass
            else:
                msg = "Files: " + file_path + " is not a directory"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'file_path' not in section"
            messages["ERROR"].append(msg)
        # check plot_path is in the Files section
        if "plot_path" in cfg["Files"]:
            plot_path = cfg["Files"]["plot_path"]
            # check plot_path directory exists
            if os.path.isdir(plot_path):
                pass
            else:
                msg = "Files: " + plot_path + " doesn't exist, creating ..."
                messages["INFO"].append(msg)
                os.mkdir(plot_path)
        else:
            msg = "Files: 'plot_path' not in section"
            messages["ERROR"].append(msg)
        # check in_filename is in the Files section
        if "in_filename" in cfg["Files"]:
            file_name = cfg["Files"]["in_filename"]
            file_parts = os.path.splitext(file_name)
            # check the file type is supported
            if (file_parts[-1].lower() in  [".nc"]):
                file_uri = os.path.join(file_path, file_name)
                if os.path.isfile(file_uri):
                    pass
                else:
                    msg = "Files: " + file_name + " not found"
                    messages["ERROR"].append(msg)
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'in_filename' not in section"
            messages["ERROR"].append(msg)
        # check the output file type
        if "out_filename" in cfg["Files"]:
            file_name = cfg["Files"]["out_filename"]
            file_parts = os.path.splitext(file_name)
            if (file_parts[-1].lower() in [".nc"]):
                pass
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
    else:
        msg = "'Files' section not in control file"
        messages["ERROR"].append(msg)
    return
def l2_check_options(cfg, messages):
    """ Check the Options section in the L2 control file."""
    if "Options" in cfg:
        pass
    else:
        msg = "No Options section in control file, using defaults for all options"
        messages["WARNING"].append(msg)
    return
def l2_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L2 control file to update the syntax from earlier OFQC/PFP versions
     to the syntax used by this version.
    Usage:
     result = pfp_compliance.l2_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L2 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: February 2020
    """
    # copy the control file
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L2 control file syntax"
    # clean up the Options section
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L2 control file Options section"
    # clean up the variable names
    try:
        cfg = update_cfg_variables_deprecated(cfg, std)
        cfg = update_cfg_variables_rename(cfg, std)
        cfg = update_cfg_variable_attributes(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L2 control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def update_cfg_variable_attributes(cfg, std):
    """
    Purpose:
     Update the variable attributes according to the rules in the standard control file.
      - rename variables in DependencyCheck
    Usage:
    Author: PRI
    Date: May 2020
    """
    # rename exact variable name matches
    renames_exact = list(std["Variables"]["rename_exact"].keys())
    # rename pattern matches
    renames_pattern = list(std["Variables"]["rename_pattern"].keys())
    # find out the section name
    for item in ["Variables", "Drivers", "Fluxes"]:
        if item in cfg:
            section_name = item
    # loop over variables in the control file
    labels_cfg = list(cfg[section_name].keys())
    for label_cfg in labels_cfg:
        for qc in ["DependencyCheck", "MergeSeries", "AverageSeries"]:
            if qc in cfg[section_name][label_cfg]:
                source = cfg[section_name][label_cfg][qc]["source"]
                vs = pfp_utils.string_to_list(source)
                vs = [std["Variables"]["rename_exact"][v] if v in renames_exact else v for v in vs]
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    vs = [v.replace(v.split("_")[0], srp)
                          if (v.split("_")[0] == rp)
                          else v for v in vs]
                cfg[section_name][label_cfg][qc]["source"] = ",".join(vs)
            else:
                continue

        for gfm in ["GapFillFromAlternate", "GapFillFromClimatology"]:
            if gfm in cfg[section_name][label_cfg]:
                gfvs = list(cfg[section_name][label_cfg][gfm].keys())
                for gfv in gfvs:
                    if gfv in renames_exact:
                        new_name = std["Variables"]["rename_exact"][gfv]
                        cfg[section_name][label_cfg][gfm].rename(gfv, new_name)
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    # loop over the variables in the control file
                    for gfv in gfvs:
                        if (gfv.split("_")[0] == rp):
                            new_name = gfv.replace(gfv.split("_")[0], srp)
                            cfg[section_name][label_cfg][gfm].rename(gfv, new_name)
            else:
                continue

        for gfm in ["GapFillUsingSOLO", "GapFillLongSOLO", "GapFillUsingMDS"]:
            if gfm in cfg[section_name][label_cfg]:
                # loop over the variables for this gap filling method and rename if necessary
                gfvs = list(cfg[section_name][label_cfg][gfm].keys())
                for gfv in gfvs:
                    if gfv in renames_exact:
                        new_name = std["Variables"]["rename_exact"][gfv]
                        cfg[section_name][label_cfg][gfm].rename(gfv, new_name)

                # now loop over the drivers and rename if necessary
                gfvs = list(cfg[section_name][label_cfg][gfm].keys())
                for gfv in gfvs:
                    drivers = cfg[section_name][label_cfg][gfm][gfv]["drivers"]
                    drivers = pfp_utils.string_to_list(drivers)
                    for re in renames_exact:
                        if re in drivers:
                            idx = drivers.index(re)
                            drivers[idx] = std["Variables"]["rename_exact"][re]
                    drivers = pfp_utils.list_to_string(drivers)
                    cfg[section_name][label_cfg][gfm][gfv]["drivers"] = drivers

                # rename if first characters of variable name match pattern
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    # loop over the variables in the control file
                    gfvs = list(cfg[section_name][label_cfg][gfm].keys())
                    for gfv in gfvs:
                        if (gfv.split("_")[0] == rp):
                            new_name = gfv.replace(gfv.split("_")[0], srp)
                            cfg[section_name][label_cfg][gfm].rename(gfv, new_name)
                # loop over the drivers
                gfvs = list(cfg[section_name][label_cfg][gfm].keys())
                for gfv in gfvs:
                    drivers = cfg[section_name][label_cfg][gfm][gfv]["drivers"]
                    drivers = pfp_utils.string_to_list(drivers)
                    for rp in renames_pattern:
                        srp = std["Variables"]["rename_pattern"][rp]
                        for driver in list(drivers):
                            if (driver.split("_")[0] == rp):
                                new_name = driver.replace(driver.split("_")[0], srp)
                                idx = drivers.index(driver)
                                drivers[idx] = new_name
                    drivers = pfp_utils.list_to_string(drivers)
                    cfg[section_name][label_cfg][gfm][gfv]["drivers"] = drivers
            else:
                continue
    return cfg

def update_cfg_variables_rename(cfg, std):
    """
    Purpose:
     Update the variable names according to the rules in the standard control file.
    Usage:
    Author: PRI
    Date: May 2020
    """
    # dictionary of renamed variables
    renamed = {}
    # rename exact variable name matches
    renames_exact = list(std["Variables"]["rename_exact"].keys())
    # find out the section name
    for item in ["Variables", "Drivers", "Fluxes"]:
        if item in cfg:
            section_name = item
    # loop over the variables in the Variables section of the control file
    for label_cfg in list(cfg[section_name].keys()):
        # check and if required, rename the "name" key value
        if "name" in list(cfg[section_name][label_cfg].keys()):
            name = cfg[section_name][label_cfg]["name"]
            if name in renames_exact:
                new_name = std["rename_exact"][name]
                cfg[section_name][label_cfg]["name"] = new_name
        # check and if required, rename the variable itself
        if label_cfg in renames_exact:
            new_name = std["Variables"]["rename_exact"][label_cfg]
            renamed[label_cfg] = new_name
            cfg[section_name].rename(label_cfg, new_name)
    # rename pattern matches
    renames_pattern = list(std["Variables"]["rename_pattern"].keys())
    for rp in renames_pattern:
        srp = std["Variables"]["rename_pattern"][rp]
        # loop over the variables in the control file
        for label_cfg in list(cfg[section_name].keys()):
            # check and if required, rename the "name" key value
            if "name" in list(cfg[section_name][label_cfg].keys()):
                name = cfg[section_name][label_cfg]["name"]
                if (name.split("_")[0] == rp):
                    new_name = name.replace(name.split("_")[0], srp)
                    cfg[section_name][label_cfg]["name"] = new_name
            # check and if required, rename the variable itself
            if (label_cfg.split("_")[0] == rp):
                new_name = label_cfg.replace(label_cfg.split("_")[0], srp)
                renamed[label_cfg] = new_name
                cfg["Variables"].rename(label_cfg, new_name)
    # do any functions
    for label_cfg in list(cfg[section_name].keys()):
        if "Function" in cfg[section_name][label_cfg]:
            func_str = cfg[section_name][label_cfg]["Function"]["func"]
            for old_label in list(renamed.keys()):
                if old_label in func_str:
                    func_str = func_str.replace(old_label, renamed[old_label])
                    cfg[section_name][label_cfg]["Function"]["func"] = func_str
    # loop over the variables in the Plots section of the control file
    if "Plots" in list(cfg.keys()):
        plots = list(cfg["Plots"])
        for plot in plots:
            if "variables" in cfg["Plots"][plot]:
                cp = cfg["Plots"][plot]["variables"]
                vs = pfp_utils.string_to_list(cp)
                vs = [std["Variables"]["rename_exact"][v] if v in renames_exact else v for v in vs]
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    vs = [v.replace(v.split("_")[0], srp)
                          if (v.split("_")[0] == rp)
                          else v for v in vs]
                cfg["Plots"][plot]["variables"] = ",".join(vs)
            elif "type" in cfg["Plots"][plot]:
                if cfg["Plots"][plot]["type"] == "xy":
                    for axis in ["xseries", "yseries"]:
                        cp = cfg["Plots"][plot][axis]
                        vs = pfp_utils.string_to_list(cp)
                        vs = [std["Variables"]["rename_exact"][v] if v in renames_exact else v for v in vs]
                        for rp in renames_pattern:
                            srp = std["Variables"]["rename_pattern"][rp]
                            vs = [v.replace(v.split("_")[0], srp)
                                  if (v.split("_")[0] == rp)
                                  else v for v in vs]
                        cfg["Plots"][plot][axis] = ",".join(vs)
    return cfg

def l3_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L3 control file to update the syntax from earlier OFQC/PFP versions
     to the syntax used by this version.
    Usage:
     result = pfp_compliance.update_l3_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L3 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: February 2020
    """
    # get a copy of the original control file object
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L3 control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_deprecated(cfg, std)
        cfg = update_cfg_variables_rename(cfg, std)
        cfg = update_cfg_variable_attributes(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L3 control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def update_cfg_options(cfg, std, call_mode="interactive"):
    """
    Purpose:
     Update an L3 control file Options section.
    Usage:
    Side effects:
     Returns a modified control file object.
    Author: PRI
    Date: May 2020
    """
    # make sure there is an Options section
    if "Options" not in cfg:
        cfg["Options"] = {}
    # add the call mode and show plots options
    cfg["Options"]["call_mode"] = call_mode
    cfg["Options"]["show_plots"] = "Yes"
    if call_mode == "batch":
        cfg["Options"]["show_plots"] = "No"
    # move items from the General section (if it exists) to the Options section.
    if "General" in cfg:
        for item in cfg["General"]:
            cfg["Options"][item] = cfg["General"][item]
        del cfg["General"]
    # update the units in the Options section
    if cfg["level"] == "L1":
        pass
    elif cfg["level"] == "L2":
        if "irga_type" in cfg["Options"]:
            irga_type = cfg["Options"]["irga_type"]
            if irga_type in ["Li-7500A (<V6.5)", "Li-7500A (>=V6.5)"]:
                cfg["Options"]["irga_type"] = "Li-7500A"
    elif cfg["level"] == "L3":
        for item in list(cfg["Options"].keys()):
            if item in ["ApplyFcStorage", "FcUnits", "ReplaceFcStorage", "DisableFcWPL"]:
                cfg["Options"].rename(item, item.replace("Fc", "Fco2"))
            if item in ["CcUnits"]:
                cfg["Options"].rename(item, item.replace("Cc", "CO2"))
        if "UseL2Fluxes" in list(cfg["Options"].keys()):
            opt = cfg["Options"]["UseL2Fluxes"]
            if opt.lower() == "no":
                calculate_fluxes = "Yes"
            else:
                calculate_fluxes = "No"
            cfg["Options"].pop("UseL2Fluxes")
            cfg["Options"]["CalculateFluxes"] = calculate_fluxes
        # remove deprecated L3 options
        for item in ["DisableFco2WPL", "DisableFcWPL", "DisableFeWPL",
                     "DisableWPL", "ApplyWPL"]:
            if item in cfg["Options"]:
                cfg["Options"].pop(item)
        old_units = list(std["Variables"]["units_map"].keys())
        for item in list(cfg["Options"].keys()):
            if cfg["Options"][item] in old_units:
                cfg["Options"][item] = std["Variables"]["units_map"][cfg["Options"][item]]
    elif cfg["level"] == "L5":
        # rename exact variable name matches
        renames_exact = list(std["Variables"]["rename_exact"].keys())
        # rename pattern matches
        renames_pattern = list(std["Variables"]["rename_pattern"].keys())
        # loop over entries in the Options section, exact match
        options = cfg["Options"]
        for option in options:
            opt = cfg["Options"][option]
            if opt in renames_exact:
                cfg["Options"][option] = std["Variables"]["rename_exact"][opt]
        # loop over entries in the Options section, pattern match
        options = cfg["Options"]
        for rp in renames_pattern:
            llen = len(rp)
            srp = std["Variables"]["rename_pattern"][rp]
            klen = len(srp)
            for option in options:
                opt = str(cfg["Options"][option])
                if ((opt[:llen] == rp) and
                    (opt[:klen] != srp)):
                    new_opt = opt.replace(opt[:llen], srp)
                    cfg["Options"][option] = new_opt
    return cfg

def l4_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L4 control file to make sure the syntax is correct and that the
     control file contains all of the information needed.
    Usage:
     result = pfp_compliance.l4_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L4 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: June 2020
    """
    # get a copy of the original control file object
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L4 control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_deprecated(cfg, std)
        cfg = update_cfg_variables_rename(cfg, std)
        cfg = update_cfg_variable_attributes(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L4 control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def l5_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L5 control file to make sure the syntax is correct and that the
     control file contains all of the information needed.
    Usage:
     result = pfp_compliance.l5_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L5 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: June 2020
    """
    # get a copy of the original control file object
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    try:
        cfg = update_cfg_syntax(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L5 control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = update_cfg_variables_deprecated(cfg, std)
        cfg = update_cfg_variables_rename(cfg, std)
        cfg = update_cfg_variable_attributes(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L5 control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok

def l6_update_controlfile(cfg, call_mode="interactive"):
    """
    Purpose:
     Parse the L6 control file to make sure the syntax is correct and that the
     control file contains all of the information needed.
    Usage:
     result = pfp_compliance.l6_update_controlfile(cfg)
     where cfg is a ConfigObj object
           result is True if the L6 control file was updated successfully
                     False if it couldn't be updated
    Side effects:
    Author: PRI
    Date: June 2020
    """
    # get a copy of the original control file object
    cfg_original = copy.deepcopy(cfg)
    # check to see if we can load the update_control_files.txt standard control file
    try:
        # get the base path of script or Pyinstaller application
        base_path = pfp_utils.get_base_path()
        stdname = os.path.join(base_path, "controlfiles", "standard", "update_control_files.txt")
        std = pfp_io.get_controlfilecontents(stdname, mode="quiet")
    except Exception:
        ok = False
        msg = " Unable to load standard control file " + stdname
    # initialise the return logical
    ok = True
    # check to see if we have an old style L6 control file
    if "ER" in list(cfg.keys()) or "NEE" in list(cfg.keys()) or "GPP" in list(cfg.keys()):
        ok = False
        msg = "This is an old version of the L6 control file.\n"
        msg = msg + "Close the L6 control file and create a new one from\n"
        msg = msg + "the template in PyFluxPro/controlfiles/template/L6."
        pfp_gui.MsgBox_Quit(msg, title="Critical")
        return ok
    try:
        cfg = l6_update_cfg_sections(cfg)
        cfg = l6_update_cfg_syntax(cfg)
    except Exception:
        ok = False
        msg = " An error occurred while updating the L6 control file syntax"
    # clean up the variable names
    try:
        cfg = update_cfg_options(cfg, std, call_mode=call_mode)
        cfg = l6_update_cfg_variable_names(cfg, std)
        cfg = l6_update_cfg_variable_attributes(cfg, std)
    except Exception:
        ok = False
        msg = " An error occurred updating the L6 control file contents"
    if ok:
        # check to see if the control file object has been changed
        if cfg != cfg_original:
            # and save it if it has changed
            file_name = os.path.basename(cfg.filename)
            logger.info(" Updated and saved control file " + file_name)
            cfg.write()
    else:
        logger.error(msg)
        error_message = traceback.format_exc()
        logger.error(error_message)
    return ok
def l6_check_files(cfg, messages):
    # check the Files section exists
    if ("Files" in cfg):
        # check file_path is in the Files section
        if "file_path" in cfg["Files"]:
            file_path = cfg["Files"]["file_path"]
            # check file_path directory exists
            if os.path.isdir(file_path):
                pass
            else:
                msg = "Files: " + file_path + " is not a directory"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'file_path' not in section"
            messages["ERROR"].append(msg)
        # check in_filename is in the Files section
        if "in_filename" in cfg["Files"]:
            file_name = cfg["Files"]["in_filename"]
            file_parts = os.path.splitext(file_name)
            # check the file type is supported
            if (file_parts[-1].lower() in [".nc"]):
                file_uri = os.path.join(file_path, file_name)
                if os.path.isfile(file_uri):
                    pass
                else:
                    msg = "Files: " + file_name + " not found"
                    messages["ERROR"].append(msg)
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'in_filename' not in section"
            messages["ERROR"].append(msg)
        # check the output file type
        if "out_filename" in cfg["Files"]:
            file_name = cfg["Files"]["out_filename"]
            file_parts = os.path.splitext(file_name)
            if (file_parts[-1].lower() in [".nc"]):
                pass
            else:
                msg = "Files: " + file_name + " doesn't end with .nc"
                messages["ERROR"].append(msg)
        else:
            msg = "Files: 'out_filename' not in section"
            messages["ERROR"].append(msg)
        # check file_path is in the Files section
        if "plot_path" in cfg["Files"]:
            plot_path = cfg["Files"]["plot_path"]
            # check file_path directory exists
            if os.path.isdir(plot_path):
                pass
            else:
                msg = "Files: " + plot_path + " doesn't exist, creating ..."
                messages["INFO"].append(msg)
                os.mkdir(plot_path)
        else:
            msg = "Files: 'plot_path' not in section"
            messages["ERROR"].append(msg)
    else:
        msg = "'Files' section not in control file"
        messages["ERROR"].append(msg)
    return
def l6_check_ecosystemrespiration(cfg, messages):
    return
def l6_check_grossprimaryproductivity(cfg, messages):
    return
def l6_check_netecosystemexchange(cfg, messages):
    return
def l6_check_options(cfg, messages):
    if ("Options" in cfg):
        if "Fsd_threshold" in cfg["Options"]:
            opt = pfp_utils.strip_non_numeric(str(cfg["Options"]["Fsd_threshold"]))
            if pfp_utils.is_number(opt):
                pass
            else:
                msg = "Options: 'Fsd_threshold' is not a number"
                messages["ERROR"].append(msg)
        if "PlotRawData" in cfg["Options"]:
            opt = cfg["Options"]["PlotRawData"]
            if isinstance(opt, str):
                if opt.lower() in ["yes", "no"]:
                    pass
                else:
                    msg = "Options: 'PlotRawData' must be 'Yes' or 'No'"
                    messages["ERROR"].append(msg)
            else:
                msg = "Options: 'PlotRawData' must be 'Yes' or 'No'"
                messages["ERROR"].append(msg)
    else:
        # 'Options' section is optional
        pass
    return
def l6_update_cfg_sections(cfg):
    """
    Purpose:
     Add the EvapoTranspiration section to the L6 control file
     if it is not present.
    Usage:
    Side effects:
     Adds the EvapoTranspiration section to an L6 control file.
    Author: PRI
    Date: November 2023
    """
    if "EvapoTranspiration" not in cfg:
        cfg["EvapoTranspiration"] = {"ET": {"Fe": "Fe"}}
    return cfg
def l6_update_cfg_syntax(cfg):
    """
    Purpose:
     Update an L6 control file from the old-style (pre PFP V1.0) syntax to the
     new-style syntax (post PFP V1.0).
    Usage:
    Side effects:
     Returns a modified control file object.
    Author: PRI
    Date: June 2020
    """
    strip_list = ['"', "'", "[", "]"]
    for key1 in cfg:
        if key1 in ["level"]:
            cfg[key1] = parse_cfg_values(key1, cfg[key1], strip_list)
        elif key1 in ["Files", "Global"]:
            for key2 in cfg[key1]:
                cfg2 = cfg[key1][key2]
                cfg2 = parse_cfg_values(key2, cfg2, strip_list)
                cfg[key1][key2] = cfg2
        elif key1 in ["Imports", "Options"]:
            # no options section in L6 control file yet
            pass
        elif key1 in ["EcosystemRespiration"]:
            for key2 in cfg[key1]:
                cfg2 = cfg[key1][key2]
                for key3 in cfg2:
                    cfg3 = cfg[key1][key2][key3]
                    if key3 in ["ERUsingSOLO", "ERUsingLloydTaylor", "ERUsingLasslop"]:
                        for key4 in cfg3:
                            cfg4 = cfg[key1][key2][key3][key4]
                            for key5 in cfg4:
                                cfg4.rename(key5, key5.lower())
                                cfg5 = cfg4[key5.lower()]
                                cfg5 = parse_cfg_values(key5, cfg5, strip_list)
                                cfg[key1][key2][key3][key4][key5.lower()] = cfg5
                    elif key3 in ["MergeSeries"]:
                        # strip out unwanted characters
                        for key4 in cfg[key1][key2][key3]:
                            # force lower case
                            cfg3.rename(key4, key4.lower())
                            cfg4 = cfg3[key4.lower()]
                            cfg4 = parse_cfg_variables_value(key3, cfg4)
                            cfg[key1][key2][key3][key4.lower()] = cfg4
        elif key1 in ["NetEcosystemExchange", "GrossPrimaryProductivity",
                      "EvapoTranspiration"]:
            for key2 in cfg[key1]:
                for key3 in cfg[key1][key2]:
                    cfg3 = cfg[key1][key2][key3]
                    cfg3 = parse_cfg_values(key3, cfg3, strip_list)
                    cfg[key1][key2][key3] = cfg3
        elif key1 in ["GUI"]:
            continue
        else:
            del cfg[key1]
    return cfg

def l6_update_cfg_variable_attributes(cfg, std):
    """
    Purpose:
     Update the variable attributes according to the rules in the standard control file.
      - rename variables in DependencyCheck
    Usage:
    Author: PRI
    Date: June 2020
    """
    # exact and pattern rename lists
    renames_exact = list(std["Variables"]["rename_exact"].keys())
    renames_pattern = list(std["Variables"]["rename_pattern"].keys())
    # loop over the variables in the EcosystemRespiration section of the control file
    for method in ["EcosystemRespiration"]:
        labels_cfg = list(cfg[method].keys())
        for label_cfg in labels_cfg:
            for qc in ["MergeSeries", "AverageSeries"]:
                if qc in cfg[method][label_cfg]:
                    source = cfg[method][label_cfg][qc]["source"]
                    vs = pfp_utils.string_to_list(source)
                    vs = [std["Variables"]["rename_exact"][v] if v in renames_exact else v for v in vs]
                    for rp in renames_pattern:
                        srp = std["Variables"]["rename_pattern"][rp]
                        vs = [v.replace(v.split("_")[0], srp)
                              if (v.split("_")[0] == rp)
                              else v for v in vs]
                    cfg[method][label_cfg][qc]["source"] = ",".join(vs)
                else:
                    continue
            for gfm in ["ERUsingSOLO", "ERUsingLloydTaylor", "ERUsingLasslop"]:
                if gfm in cfg[method][label_cfg]:
                    # loop over the variables for this gap filling method and rename if necessary
                    gfvs = list(cfg[method][label_cfg][gfm].keys())
                    for gfv in gfvs:
                        if gfv in renames_exact:
                            new_name = std["Variables"]["rename_exact"][gfv]
                            cfg[method][label_cfg][gfm].rename(gfv, new_name)

                    # now loop over the drivers and rename if necessary
                    gfvs = list(cfg[method][label_cfg][gfm].keys())
                    for gfv in gfvs:
                        item = cfg[method][label_cfg][gfm][gfv]["drivers"]
                        drivers = pfp_utils.string_to_list(item)
                        for driver in list(drivers):
                            for re in renames_exact:
                                if driver == re:
                                    new_name = std["Variables"]["rename_exact"][re]
                                    drivers[drivers.index(driver)] = new_name
                        cfg[method][label_cfg][gfm][gfv]["drivers"] = ",".join(drivers)

                    # rename if first characters of variable name match pattern
                    for rp in renames_pattern:
                        srp = std["Variables"]["rename_pattern"][rp]
                        # loop over the variables in the control file
                        gfvs = list(cfg[method][label_cfg][gfm].keys())
                        for gfv in gfvs:
                            if (gfv.split("_")[0] == rp):
                                new_name = gfv.replace(gfv.split("_")[0], srp)
                                cfg[method][label_cfg][gfm].rename(gfv, new_name)

                    # loop over the drivers
                    gfvs = list(cfg[method][label_cfg][gfm].keys())
                    for gfv in gfvs:
                        item = cfg[method][label_cfg][gfm][gfv]["drivers"]
                        drivers = pfp_utils.string_to_list(item)
                        for driver in list(drivers):
                            for rp in renames_pattern:
                                srp = std["Variables"]["rename_pattern"][rp]
                                if (driver.split("_")[0] == rp):
                                    new_name = opt.replace(driver.split("_")[0], srp)
                                    drivers[drivers.index(driver)] = new_name
                        cfg[method][label_cfg][gfm][gfv]["drivers"] = ",".join(drivers)


    # loop over the variables in the NEE and GPP sections
    for method in ["NetEcosystemExchange", "GrossPrimaryProductivity"]:
        labels_cfg = list(cfg[method].keys())
        for label_cfg in labels_cfg:
            # first loop is over the keys
            variables = list(cfg[method][label_cfg].keys())
            for var in variables:
                opt = cfg[method][label_cfg][var]
                # exact matches
                if var in renames_exact:
                    new_name = std["Variables"]["rename_exact"][var]
                    cfg[method][label_cfg].rename(var, new_name)
                # pattern matches
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    if (var.split("_")[0] == rp):
                        new_name = var.replace(var.split("_")[0], srp)
                        cfg[method][label_cfg].rename(var, new_name)
            # second loop is over the values in case any of the keys were renamed
            variables = list(cfg[method][label_cfg].keys())
            for var in variables:
                opt = cfg[method][label_cfg][var]
                # exact matches
                if opt in renames_exact:
                    new_name = std["Variables"]["rename_exact"][opt]
                    cfg[method][label_cfg][var] = new_name
                # pattern matches
                for rp in renames_pattern:
                    srp = std["Variables"]["rename_pattern"][rp]
                    if (opt.split("_")[0] == rp):
                        new_name = opt.replace(opt.split("_")[0], srp)
                        cfg[method][label_cfg][var] = new_name
    return cfg

def l6_update_cfg_variable_names(cfg, std):
    """
    Purpose:
     Update the variable names according to the rules in the standard control file.
    Usage:
    Author: PRI
    Date: June 2020
    """
    # exact and pattern rename lists
    renames_exact = list(std["Variables"]["rename_exact"].keys())
    renames_pattern = list(std["Variables"]["rename_pattern"].keys())
    # loop over the variables in the EcosystemRespiration, NetEcosystemExchange and
    # GrossPrimaryProductivity section of the control file
    for method in ["EcosystemRespiration", "NetEcosystemExchange", "GrossPrimaryProductivity"]:
        # rename exact matches
        for label_cfg in list(cfg[method].keys()):
            if label_cfg in renames_exact:
                new_name = std["Variables"]["rename_exact"][label_cfg]
                cfg[method].rename(label_cfg, new_name)
        # rename pattern matches
        for rp in renames_pattern:
            srp = std["Variables"]["rename_pattern"][rp]
            # loop over the variables in the control file
            for label_cfg in list(cfg[method].keys()):
                if (label_cfg.split("_")[0] == rp):
                    new_name = label_cfg.replace(label_cfg.split("_")[0], srp)
                    cfg[method].rename(label_cfg, new_name)
    return cfg

def parse_cfg_plots_title(cfg, key1, key2):
    """ Parse the [Plots] section for a title."""
    title = key2
    for item in list(cfg[key1][key2].keys()):
        if item.lower() == "title":
            title = cfg[key1][key2][item]
            del cfg[key1][key2][item]
            break
    strip_list = ['"', "'"]
    for c in strip_list:
        if c in title:
            title = title.replace(c, "")
    return title

def parse_cfg_plots_value(k, v):
    """ Parse the [Plots] section keys to remove unnecessary characters."""
    if k.lower() in ["variables", "type", "xseries", "yseries"]:
        if ("[" in v) and ("]" in v):
            v = v.replace("[", "").replace("]", "")
    strip_list = [" ", '"', "'"]
    for c in strip_list:
        if c in v:
            v = v.replace(c, "")
    return v

def parse_cfg_values(k, v, strip_list):
    """ Parse key values to remove unnecessary characters."""
    # strip unwanted characters
    for c in strip_list:
        if c in v:
            v = v.replace(c, "")
    if k in ["file_path", "plot_path"] and "browse" not in v:
        if os.path.join(str(v), "") != v:
            v = os.path.join(str(v), "")
    return v

def parse_cfg_variables_excludehours(k, v):
    """ Parse value from ExcludeHours to remove unwanted characters"""
    v = v.replace("[", "").replace("]", "")
    if k in ["ExcludeHours"]:
        strip_list = ["'", '"']
    # strip unwanted characters
    for c in strip_list:
        if c in v:
            v = v.replace(c, "")
    return v

def parse_cfg_variables_value(k, v):
    """ Parse value from control file to remove unnecessary characters."""
    if pfp_utils.is_number(v):
        pass
    elif ("[" in v) and ("]" in v) and ("*" in v):
        # old style of [value]*12
        v = v[v.index("[")+1:v.index("]")]
    elif ("[" in v) and ("]" in v) and ("*" not in v):
        # old style of [1,2,3,4,5,6,7,8,9,10,11,12]
        v = v.replace("[", "").replace("]", "")
    else:
        pass
    # remove white space and quotes
    if k in ["ExcludeDates", "ExcludeHours", "CorrectWindDirection", "LowerCheck", "UpperCheck"]:
        # don't remove white space between date and time
        strip_list = ['"', "'"]
    elif k in ["Attr"]:
        # don't remove white space from variable attributes
        strip_list = ['"', "'"]
    else:
        strip_list = [" ", '"', "'"]
    # strip unwanted characters
    for c in strip_list:
        if c in v:
            v = v.replace(c, "")
    return v
