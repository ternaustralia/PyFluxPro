# standard modules
from collections import OrderedDict
import copy
import inspect
import logging
import os
import traceback
# 3rd party modules
from configobj import ConfigObj
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.widgets import Button,  SpanSelector
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import numpy
from PyQt5 import QtCore, QtGui, QtWidgets
# PFP modules
from scripts import pfp_ck
from scripts import pfp_func_units
from scripts import pfp_func_stats
from scripts import pfp_func_transforms
from scripts import pfp_gfALT
from scripts import pfp_gfSOLO
from scripts import pfp_io
from scripts import pfp_plot
from scripts import pfp_ts
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

class myMessageBox(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(myMessageBox, self).__init__(parent)
        if title == "Critical":
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.Ok)
        self.exec_()

class MsgBox_Close(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(MsgBox_Close, self).__init__(parent)
        if title in ["Critical", "Error"]:
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.No)
        self.button(QtWidgets.QMessageBox.No).setText("Close")
    def execute(self):
        self.setModal(False)
        self.show()
        self.exec_()
        return "close"

class MsgBox_CloseOrIgnore(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(MsgBox_CloseOrIgnore, self).__init__(parent)
        if title == "Critical":
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.Yes |
                                QtWidgets.QMessageBox.No)
        self.button(QtWidgets.QMessageBox.Yes).setText("Ignore")
        self.button(QtWidgets.QMessageBox.No).setText("Close")
    def execute(self):
        self.setModal(False)
        self.show()
        self.exec_()
        if self.clickedButton() is self.button(QtWidgets.QMessageBox.Yes):
            return "ignore"
        else:
            return "close"

class MsgBox_Continue(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(MsgBox_Continue, self).__init__(parent)
        if title in ["Critical", "Error"]:
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.Yes)
        self.button(QtWidgets.QMessageBox.Yes).setText("Continue")
        self.setModal(False)
        self.show()
        self.exec_()

class MsgBox_ContinueOrQuit(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(MsgBox_ContinueOrQuit, self).__init__(parent)
        if title == "Critical":
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.Yes |
                                QtWidgets.QMessageBox.No)
        self.button(QtWidgets.QMessageBox.Yes).setText("Continue")
        self.button(QtWidgets.QMessageBox.No).setText("Quit")
        self.setModal(False)
        self.show()
        self.exec_()

class MsgBox_Quit(QtWidgets.QMessageBox):
    def __init__(self, msg, title="Information", parent=None):
        super(MsgBox_Quit, self).__init__(parent)
        if title in ["Critical", "Error"]:
            self.setIcon(QtWidgets.QMessageBox.Critical)
        elif title == "Warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        else:
            self.setIcon(QtWidgets.QMessageBox.Information)
        self.setText(msg)
        self.setWindowTitle(title)
        self.setStandardButtons(QtWidgets.QMessageBox.No)
        self.button(QtWidgets.QMessageBox.No).setText("Quit")
        self.setModal(False)
        self.show()
        self.exec_()

class myTreeView(QtWidgets.QTreeView):
    """
    Purpose:
     Subclass of QTreeView with the dragEnterEvent() and dropEvent() methods overloaded
     to constrain drag and drop moves within the control file. The following drag
     and drop rules are implemented:
     1) items can only be dropped within the section from which they originate.
     2) items can't be dropped on top of other items.
    Usage:
     view = myTreeView()
    Author: PRI
    Date: August 2020
    """
    def __init__(self):
        QtWidgets.QTreeView.__init__(self)
        # disable multiple selections
        self.setSelectionMode(self.SingleSelection)
        # enable selction of single cells
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        # enable drag and drop as internal move only
        self.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        # enable drag and drop
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        # rows have alternating colours and headers
        self.setAlternatingRowColors(True)
        self.setHeaderHidden(False)
        # create info dictionary
        self.info = {"one_line_sections": ["Files", "Global", "Options", "Soil", "Massman",
                                           "ustar_threshold", "concatenate", "In"]}

    def dragEnterEvent(self, event):
        """
        Purpose:
         Re-implement the standard dragEnterEvent to get the behaviour we want.
        Usage:
        Author: PRI
        Date: August 2020
        """
        # wrap in a try ... except to trap unforseen events (quick but dirty)
        try:
            self.setDropIndicatorShown(True)
            # index of selected item
            idxs = self.selectedIndexes()[0]
            # only enable event if user has clicked in first column
            if idxs.column() == 0:
                # save some stuff needed for the drop event
                self.info["source_index"] = idxs
                self.info["source_item"] = idxs.model().itemFromIndex(idxs)
                self.info["source_parent"] = self.info["source_item"].parent()
                source_parent = self.info["source_parent"]
                self.info["source_key"] = QtGui.QStandardItem(source_parent.child(idxs.row(),0).text())
                # second column only available if section in "one_line_sections"
                if self.info["source_parent"].text() in self.info["one_line_sections"]:
                    self.info["source_value"] = QtGui.QStandardItem(source_parent.child(idxs.row(),1).text())
                else:
                    self.info["source_value"] = QtGui.QStandardItem("")
                # accept this event
                event.accept()
            else:
                # ignore everything else
                event.ignore()
        except:
            event.ignore()

    def dropEvent(self, event):
        """
        Purpose:
         Re-implement the standard dropEvent to get the behaviour we want.
        Usage:
        Author: PRI
        Date: August 2020
        """
        # wrap in a try ... except to trap unforseen events (dirty coding)
        try:
            # index of the item under the drop
            idxd = self.indexAt(event.pos())
            # save so useful stuff
            self.info["destination_index"] = idxd
            self.info["destination_item"] = idxd.model().itemFromIndex(idxd)
            self.info["destination_parent"] = self.info["destination_item"].parent()
            destination_parent_text = self.info["destination_parent"].text()
            source_parent_text = self.info["source_parent"].text()
            # only allow drag and drop within the same section
            if (destination_parent_text == source_parent_text):
                # don't allow drop on another item
                if (self.dropIndicatorPosition() != QtWidgets.QAbstractItemView.OnItem):
                    # use special drop event code for one line sections
                    if self.info["source_parent"].text() in self.info["one_line_sections"]:
                        idxs = self.info["source_index"]
                        key = self.info["source_key"]
                        value = self.info["source_value"]
                        self.info["source_parent"].removeRow(idxs.row())
                        self.info["source_parent"].insertRow(idxd.row(), [key, value])
                        event.accept()
                    else:
                        # use standard drop event code for everything else
                        QtWidgets.QTreeView.dropEvent(self, event)
                else:
                    # ignore everything else
                    event.ignore()
            else:
                event.ignore()
        except:
            event.ignore()
        # refresh the GUI
        self.model().layoutChanged.emit()

class myTxtBox(QtWidgets.QInputDialog):
    def __init__(self, title="", prompt="", parent=None):
        super(myTxtBox, self).__init__(parent)
        self.getText(None, title, prompt, QtWidgets.QLineEdit.Normal,"")

class file_explore(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(file_explore, self).__init__()
        self.ds = main_gui.ds
        self.tabs = main_gui.tabs
        self.figure_number = 0
        self.view = QtWidgets.QTreeView()
        self.model = QtGui.QStandardItemModel()
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        self.view.setAlternatingRowColors(True)
        self.view.setHeaderHidden(False)
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.view.setModel(self.model)
        self.get_model_from_data()
        self.view.setColumnWidth(0, 200)
        # expand the "Variables" section
        for row in range(self.model.rowCount()):
            section = self.model.item(row)
            if section.text() not in ["Global attributes", "Group attributes"]:
                idx = self.model.index(row, 0)
                self.view.expand(idx)

    def add_global(self):
        """ Add a new entry to the [Global] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the new children
        child0 = QtGui.QStandardItem("New item")
        child1 = QtGui.QStandardItem("")
        selected_item.appendRow([child0, child1])
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_global_above(self):
        """ Add a new variable above the selected variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()

        ## construct the new variable dictionary
        #new_var = {"xl":{"sheet":"", "name":""},
                   #"Attr":{"height": "", "instrument": "", "long_name": "",
                           #"statistic_type": "average", "standard_name": "",
                           #"units": ""}}
        #subsection = QtGui.QStandardItem("New variable")
        #self.add_subsubsection(subsection, new_var)

        # get the new children
        child0 = QtGui.QStandardItem("New item")
        child1 = QtGui.QStandardItem("")
        parent.insertRow(idx.row(), [child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def context_menu(self, position):
        self.context_menu = QtWidgets.QMenu()
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        # get the indices of selected items
        idx = self.view.selectedIndexes()
        if len(idx) == 1 and idx[0].data() == "Global attributes":
            # context menu to add global attribute
            self.context_menu.actionAddGlobal = QtWidgets.QAction(self)
            self.context_menu.actionAddGlobal.setText("Add attribute")
            self.context_menu.addAction(self.context_menu.actionAddGlobal)
            self.context_menu.actionAddGlobal.triggered.connect(self.add_global)
        elif len(idx) == 1 and idx[0].parent().data() == "Global attributes":
            selected_text = idx[0].data()
            # context menu to add global attribute above selected item
            self.context_menu.actionAddGlobalAbove = QtWidgets.QAction(self)
            self.context_menu.actionAddGlobalAbove.setText("Add attribute")
            self.context_menu.addAction(self.context_menu.actionAddGlobalAbove)
            self.context_menu.actionAddGlobalAbove.triggered.connect(self.add_global_above)
            if selected_text not in ["canopy_height", "featureType", "fluxnet_id",
                                     "irga_type", "license_name",
                                     "latitude", "longitude",
                                     "processing_level",
                                     "site_name", "sonic_type",
                                     "time_step", "time_zone",
                                     "time_coverage_end", "time_coverage_start"]:
                self.context_menu.actionRemoveGlobal = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGlobal.setText("Remove attribute")
                self.context_menu.addAction(self.context_menu.actionRemoveGlobal)
                self.context_menu.actionRemoveGlobal.triggered.connect(self.remove_item)
        else:
            # get the group labels of selected items
            groups = list(set([i.parent().data() for i in idx]))
            # dictionary to hold the labels of selected variables for each group
            selections = {}
            # add the selected variable labels to the right group in selections
            for i in idx:
                # get the group label of this selected item
                group = i.parent().data()
                # skip anything selected in 'Global attributes'
                if (group in ["Global attributes"]):
                    continue
                # add the group to selections if not there
                if group not in selections:
                    selections[group] = []
                # append the label of the selected variable to the group
                selections[i.parent().data()].append(i.data())
            # rename the 'Variables' group to 'root'
            for key in list(selections.keys()):
                if key is None or key == "Variables":
                    selections["root"] = selections.pop(key)
                    break
            # return if selections is empty (no variables selected)
            if len(list(selections.keys())) == 0:
                return
            # plot time series, separate axes or grouped
            menuPlotTimeSeries = QtWidgets.QMenu(self)
            menuPlotTimeSeries.setTitle("Plot time series")
            actionPlotTimeSeriesSeparate = QtWidgets.QAction(self)
            actionPlotTimeSeriesSeparate.setText("Separate")
            actionPlotTimeSeriesSeparate.triggered.connect(lambda: self.plot_timeseries(selections))
            actionPlotTimeSeriesGrouped = QtWidgets.QAction(self)
            actionPlotTimeSeriesGrouped.setText("Grouped")
            actionPlotTimeSeriesGrouped.triggered.connect(lambda: self.plot_timeseries_grouped(selections))
            menuPlotTimeSeries.addAction(actionPlotTimeSeriesSeparate)
            menuPlotTimeSeries.addAction(actionPlotTimeSeriesGrouped)
            self.context_menu.addMenu(menuPlotTimeSeries)
            # plot time series of percentiles
            self.context_menu.actionPlotPercentiles = QtWidgets.QAction(self)
            self.context_menu.actionPlotPercentiles.setText("Plot percentiles")
            self.context_menu.addAction(self.context_menu.actionPlotPercentiles)
            self.context_menu.actionPlotPercentiles.triggered.connect(lambda: self.plot_percentiles(selections))
            # plot fingerprints
            # check the time steps for all groups containing selected variables
            groups = list(selections.keys())
            groups = ["root" if i == "Global attributes" else i for i in groups]
            time_steps = []
            for group in groups:
                time_steps.append(str(getattr(self.ds, group)["Attributes"]["time_step"]))
            # all time steps for selected variables must be 30 or 60 to plot fingerprints
            if all([True if ts in ["30", "60"] else False for ts in time_steps]):
                self.context_menu.actionPlotFingerprints = QtWidgets.QAction(self)
                self.context_menu.actionPlotFingerprints.setText("Plot fingerprints")
                self.context_menu.addAction(self.context_menu.actionPlotFingerprints)
                self.context_menu.actionPlotFingerprints.triggered.connect(lambda: self.plot_fingerprints(selections))

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def get_data_from_model(self):
        """ Iterate over the model and get the data.  Allows editing of attributes."""
        model = self.model
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            if key1 in ["Global attributes"]:
                # global attributes
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    self.ds.root["Attributes"][key2] = val2
            elif key1 in ["Variables"]:
                for j in range(section.rowCount()):
                    variable_section = section.child(j)
                    label = variable_section.text()
                    for k in range(variable_section.rowCount()):
                        key2 = str(variable_section.child(k, 0).text())
                        val2 = str(variable_section.child(k, 1).text())
                        self.ds.root["Variables"][label]["Attr"][key2] = val2
            else:
                # this is a netCDF file with groups
                group_attributes = {}
                variables = {}
                for j in range(section.rowCount()):
                    if section.child(j).text() in ["Group attributes"]:
                        for k in range(section.child(j).rowCount()):
                            key = str(section.child(j).child(k, 0).text())
                            value = str(section.child(j).child(k, 1).text())
                            group_attributes[key] = value
                    else:
                        label = section.child(j).text()
                        group = getattr(self.ds, key1)
                        variables[label] = {"Data": group["Variables"][label]["Data"],
                                            "Flag": group["Variables"][label]["Flag"],
                                            "Attr": group["Variables"][label]["Attr"]}
                        for k in range(section.child(j).rowCount()):
                            key = str(section.child(j).child(k, 0).text())
                            value = str(section.child(j).child(k, 1).text())
                            variables[label]["Attr"][key] = value
                # create the group as an attribute in the data structure
                setattr(self.ds, key1, {"Attributes": group_attributes,
                                        "Variables": variables})
                #msg = " Unrecognised object (" + key1 + ") in netCDF file"
                #msg += ", skipping ..."
                #logger.warning(msg)
        return self.ds

    def get_model_from_data(self):
        self.model.setHorizontalHeaderLabels(["Variable", "long_name"])
        self.model.itemChanged.connect(self.handleItemChanged)
        gattrs = sorted(list(self.ds.root["Attributes"].keys()))
        long_name = QtGui.QStandardItem("")
        section = QtGui.QStandardItem("Global attributes")
        section.setEditable(False)
        for gattr in gattrs:
            value = str(self.ds.root["Attributes"][gattr])
            child0 = QtGui.QStandardItem(gattr)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            section.appendRow([child0, child1])
        self.model.appendRow([section, long_name])
        groups = list(vars(self.ds).keys())
        if "info" in groups:
            groups.remove("info")
        for group in groups:
            gvars = getattr(self.ds, group)["Variables"]
            if group == "root":
                group_section = QtGui.QStandardItem("Variables")
            else:
                group_section = QtGui.QStandardItem(group)
                attr_section = QtGui.QStandardItem("Group attributes")
                gattrs = getattr(self.ds, group)["Attributes"]
                for gattr in gattrs:
                    value = str(gattrs[gattr])
                    child0 = QtGui.QStandardItem(gattr)
                    child1 = QtGui.QStandardItem(value)
                    attr_section.appendRow([child0, child1])
                group_section.appendRow([attr_section, QtGui.QStandardItem("")])
            group_section.setEditable(False)
            labels = sorted(list(gvars.keys()))
            if len(labels) == 0:
                continue
            for label in labels:
                var = pfp_utils.GetVariable(self.ds, label, group=group)
                long_name = QtGui.QStandardItem(var["Attr"]["long_name"])
                variable_section = QtGui.QStandardItem(label)
                # some variable names are not editable
                if label in ["DateTime", "time"]:
                    variable_section.setEditable(False)
                for attr in var["Attr"]:
                    value = str(var["Attr"][attr])
                    child0 = QtGui.QStandardItem(attr)
                    child1 = QtGui.QStandardItem(value)
                    variable_section.appendRow([child0, child1])
                group_section.appendRow([variable_section, long_name])
            self.model.appendRow([group_section, QtGui.QStandardItem("")])
        return

    def handleItemChanged(self, item):
        """
        Purpose:
         Handler for when view items are edited.
         Supported editing functions are:
          Rename a variable
          Rename a global or a variable attribute
          Change the value of a global or variable attribute
        """
        # get a list of variables in the data structure
        labels = list(self.ds.root["Variables"].keys())
        # check to see if the selected text before the change was a variable name
        if hasattr(self, "double_click_selected_text"):
            if self.double_click_selected_text in labels:
                # if it was, rename the variable in the data structure
                idx = self.view.selectedIndexes()
                new_label = idx[0].data()
                old_label = self.double_click_selected_text
                self.ds.root["Variables"][new_label] = self.ds.root["Variables"].pop(old_label)
            else:
                # renaming attributes or changing their value is handled when the data is
                # read back from the model by self.get_data_from_model()
                pass
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        return

    def plot_histograms(self, labels):
        """ Wrapper for plot histograms function."""
        # remove anything that is not the label of a variable in self.ds
        for label in list(labels):
            if label not in list(self.ds.root["Variables"].keys()):
                labels.remove(label)
        # check to make sure there is something left to plot
        if len(labels) == 0:
            msg = " No variables to plot"
            logger.warning(msg)
            return
        # go ahead and plot
        pfp_plot.plot_explore_histograms(self.ds, labels)
        # increment the figure number
        self.figure_number += 1
        return

    def plot_fingerprints(self, selections):
        """ Wrapper for plot fingerprints function."""
        # remove anything that is not the label of a variable in self.ds
        groups = sorted(list(selections.keys()))
        for group in groups:
            gvars = getattr(self.ds, group)
            labels = sorted(selections[group])
            for label in labels:
                if label not in list(gvars["Variables"].keys()):
                    selections[group].remove(label)
            # check to make sure there is something left to plot
            if len(selections[group]) == 0:
                msg = " No variables in group " + group + " to plot"
                logger.warning(msg)
                selections.pop(group)
        if len(selections.keys()) == 0:
            msg = " Nothing to plot"
            logger.warning(msg)
            return
        # go ahead and plot
        try:
            pfp_plot.plot_explore_fingerprints(self.ds, selections)
            # increment the figure number
            self.figure_number += 1
        except Exception:
            error_message = " An error occurred while plotting fingerprints, see below for details ..."
            logger.error(error_message)
            error_message = traceback.format_exc()
            logger.error(error_message)
        return

    def plot_percentiles(self, selections):
        """ Wrapper for plot percentiles function."""
        # remove anything that is not the label of a variable in self.ds
        groups = sorted(list(selections.keys()))
        for group in groups:
            gvars = getattr(self.ds, group)
            labels = sorted(selections[group])
            for label in labels:
                if label not in list(gvars["Variables"].keys()):
                    selections[group].remove(label)
            # check to make sure there is something left to plot
            if len(selections[group]) == 0:
                msg = " No variables in group " + group + " to plot"
                logger.warning(msg)
                selections.pop(group)
        if len(selections.keys()) == 0:
            msg = " Nothing to plot"
            logger.warning(msg)
            return
        # go ahead and plot
        try:
            pfp_plot.plot_explore_percentiles(self.ds, selections)
            # increment the figure number
            self.figure_number += 1
        except Exception:
            error_message = " An error occurred while plotting percentile time series, see below for details ..."
            logger.error(error_message)
            error_message = traceback.format_exc()
            logger.error(error_message)
        return

    def plot_timeseries(self, selections):
        """ Wrapper for plot time series function."""
        # remove anything that is not the label of a variable in self.ds
        groups = sorted(list(selections.keys()))
        for group in groups:
            gvars = getattr(self.ds, group)
            labels = sorted(selections[group])
            for label in labels:
                if label not in list(gvars["Variables"].keys()):
                    selections[group].remove(label)
            # check to make sure there is something left to plot
            if len(selections[group]) == 0:
                msg = " No variables in group " + group + " to plot"
                logger.warning(msg)
                selections.pop(group)
        if len(selections.keys()) == 0:
            msg = " Nothing to plot"
            logger.warning(msg)
            return
        # go ahead and plot
        try:
            pfp_plot.plot_explore_timeseries(self.ds, selections)
            # increment the figure number
            self.figure_number += 1
        except Exception:
            error_message = " An error occurred while plotting time series, see below for details ..."
            logger.error(error_message)
            error_message = traceback.format_exc()
            logger.error(error_message)
        return

    def plot_timeseries_grouped(self, selections):
        """ Wrapper for plot time series function."""
        # remove anything that is not the label of a variable in self.ds
        groups = sorted(list(selections.keys()))
        for group in groups:
            gvars = getattr(self.ds, group)
            labels = sorted(selections[group])
            for label in labels:
                if label not in list(gvars["Variables"].keys()):
                    selections[group].remove(label)
            # check to make sure there is something left to plot
            if len(selections[group]) == 0:
                msg = " No variables in group " + group + " to plot"
                logger.warning(msg)
                selections.pop(group)
        if len(selections.keys()) == 0:
            msg = " Nothing to plot"
            logger.warning(msg)
            return
        # go ahead and plot
        try:
            pfp_plot.plot_explore_timeseries_grouped(self.ds, selections)
            # increment the figure number
            self.figure_number += 1
        except Exception:
            error_message = " An error occurred while plotting time series, see below for details ..."
            logger.error(error_message)
            error_message = traceback.format_exc()
            logger.error(error_message)
        return

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")
        return

class pick_exclude_date_range(QtWidgets.QDialog):
    def __init__(self, var, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"QC Tool")
        self.setMinimumSize(1000, 700)

        # Data setup
        self.var = copy.deepcopy(var)
        self.deletion_log = []
        self.shift_is_held = False
        self.first_idx = None

        # Create Matplotlib Figure and Canvas
        self.fig = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.fig)
        self.ax = self.fig.add_subplot(111)

        # Initial Plot
        self.line, = self.ax.plot(self.var["DateTime"], self.var["Data"], '-r', alpha=0.3)
        self.pts = self.ax.scatter(self.var["DateTime"], self.var["Data"], picker=True,
                                   pickradius=1, s=20, color='blue')
        self.ax.set_xlim(left=self.var["DateTime"][0], right=self.var["DateTime"][-1])
        # Layout UI
        layout = QtWidgets.QVBoxLayout()
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        self.save_btn = QtWidgets.QPushButton("Save & Update Control File")
        self.save_btn.clicked.connect(self.accept) # 'accept' closes dialog and returns 1
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        layout.addLayout(btn_layout)
        self.setLayout(layout)

        # Add the SpanSelector
            # direction='horizontal' tracks the x-axis (time)
        # interactive=True allows you to resize the selection before finishing
        self.span = SpanSelector(self.ax, self.on_span_select, 'horizontal',
                                 useblit=True, props=dict(alpha=0.3, facecolor='orange'),
                                 interactive=False, button=1)
        # Start with it disabled so it doesn't interfere with normal clicks
        self.span.set_active(False)

        # Connect Matplotlib Events
        self.canvas.mpl_connect('key_press_event', self.on_key_press)
        self.canvas.mpl_connect('key_release_event', self.on_key_release)
        self.canvas.mpl_connect('pick_event', self.on_pick)

        # Force focus to catch key events
        self.canvas.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.canvas.setFocus()

        # use tight layout
        self.fig.tight_layout()

    def on_key_press(self, event):
        if event.key == 'shift':
            self.shift_is_held = True
            self.span.set_active(True)

    def on_key_release(self, event):
        if event.key == 'shift':
            self.shift_is_held = False
            self.span.set_active(False)
            self.first_idx = None

    def on_pick(self, event):
        # Ignore if zooming/panning
        #if self.toolbar.mode != "":
            #return

        current_idx = event.ind[0]
        if self.shift_is_held:
            if self.first_idx is None:
                self.first_idx = current_idx
                self.ann_start = self.ax.annotate('Start', (self.var["DateTime"][current_idx],
                                           self.var["Data"][current_idx]), color='green')
                self.canvas.draw()
            else:
                start, end = sorted([self.first_idx, current_idx])
                self.deletion_log.append((self.var["DateTime"][start], self.var["DateTime"][end]))
                self.var["Data"][start:end+1] = numpy.nan
                self.first_idx = None
                self.ann_start.remove()
                self.update_plot()
        else:
            ts = self.var["DateTime"][current_idx]
            self.deletion_log.append((ts, ts))
            self.var["Data"][current_idx] = numpy.nan
            self.update_plot()

    def on_span_select(self, xmin, xmax):
        """Called when the mouse button is released after dragging"""
        # Matplotlib provides xmin/xmax as floats. Convert them to datetime objects.
        dt_min = mdates.num2date(xmin).replace(tzinfo=None)
        dt_max = mdates.num2date(xmax).replace(tzinfo=None)
        # Find the indices in the time array that fall within this range
        mask = (self.var["DateTime"] >= dt_min) & (self.var["DateTime"] <= dt_max)
        indices = numpy.where(mask)[0]

        if len(indices) > 0:
            # Log the range based on actual data limits within the selection
            start_time = self.var["DateTime"][indices[0]]
            end_time = self.var["DateTime"][indices[-1]]
            self.deletion_log.append((start_time, end_time))

            # Apply the deletion
            self.var["Data"][mask] = numpy.nan
            self.update_plot()
            #print(f"Excluded range: {start_time} to {end_time}")

    def update_plot(self):
        #self.ax.texts = []
        self.pts.set_offsets(numpy.c_[self.var["DateTime"], self.var["Data"]])
        self.line.set_ydata(self.var["Data"])
        self.canvas.draw()

class edit_cfg_batch(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_batch, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.main_gui = main_gui
        self.tabs = main_gui.tabs
        self.implemented_levels = ["L1", "L2", "L3",
                                   "nc2csv_oneflux",
                                   "concatenate", "climatology",
                                   "cpd_barr", "cpd_mchugh", "cpd_mcnew", "mpt",
                                   "L4", "L5", "L6"]
        self.edit_batch_gui()

    def add_control_file(self):
        """ Add an entry for a new input file."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        dict_to_add = {str(subsection.rowCount()): "Right click to browse"}
        # add the subsubsection
        self.add_subsection(subsection, dict_to_add)

    def add_control_file_above(self):
        """ Add a new control file above the selected entry."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        new_file_number = min([0, int(float(selected_item.text()))-1])
        # get the parent of the selected item
        parent = selected_item.parent()
        # insert the new file entry
        new_file_entry = [QtGui.QStandardItem(str(new_file_number)),
                          QtGui.QStandardItem("Right click to browse")]
        parent.insertRow(idx.row(), new_file_entry)
        # renumber the section
        self.renumber_subsection_keys(parent)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        return

    def add_level(self):
        """ Add a level to be processed."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        s = self.context_menu.sender().text()
        level = s.rsplit(" ", 1)[-1]
        dict_to_add = {level: {"0": "Right click to browse"}}
        # add the subsubsection
        self.add_subsubsection(selected_item, dict_to_add)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def add_subsubsection(self, subsection, dict_to_add):
        """ Add a subsubsection to the model."""
        for key in dict_to_add:
            subsubsection = QtGui.QStandardItem(key)
            subsubsection.setEditable(False)
            self.add_subsection(subsubsection, dict_to_add[key])
            subsection.appendRow(subsubsection)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path)[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_path = QtCore.QDir.toNativeSeparators(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_path)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        add_separator = False
        if level == 0:
            existing_entries = self.get_existing_entries()
            # sections with only 1 level
            if selected_text == "Options":
                pass
            elif selected_text == "Levels":
                for level in self.implemented_levels:
                    if level not in existing_entries:
                        level_text = "Add " + level
                        self.context_menu.actionAddLevel = QtWidgets.QAction(self)
                        self.context_menu.actionAddLevel.setText(level_text)
                        self.context_menu.addAction(self.context_menu.actionAddLevel)
                        self.context_menu.actionAddLevel.triggered.connect(self.add_level)
                        add_separator = True
        elif level == 1:
            parent = selected_item.parent()
            if str(parent.text()) == "Levels":
                if selected_text in self.implemented_levels:
                    self.context_menu.actionAddControlFile = QtWidgets.QAction(self)
                    self.context_menu.actionAddControlFile.setText("Add control file")
                    self.context_menu.addAction(self.context_menu.actionAddControlFile)
                    self.context_menu.actionAddControlFile.triggered.connect(self.add_control_file)
                    add_separator = True
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                self.context_menu.actionRemoveLevel = QtWidgets.QAction(self)
                self.context_menu.actionRemoveLevel.setText("Remove level")
                self.context_menu.addAction(self.context_menu.actionRemoveLevel)
                self.context_menu.actionRemoveLevel.triggered.connect(self.remove_item)
        elif level == 2:
            parent = selected_item.parent()
            section = selected_item.parent().parent()
            if (str(section.text()) == "Levels"):
                if (selected_item.column() == 0):
                    self.context_menu.actionAddControlFileAbove = QtWidgets.QAction(self)
                    self.context_menu.actionAddControlFileAbove.setText("Add control file")
                    self.context_menu.addAction(self.context_menu.actionAddControlFileAbove)
                    self.context_menu.actionAddControlFileAbove.triggered.connect(self.add_control_file_above)
                    self.context_menu.addSeparator()
                    self.context_menu.actionRemoveInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveInputFile.setText("Remove file")
                    self.context_menu.addAction(self.context_menu.actionRemoveInputFile)
                    self.context_menu.actionRemoveInputFile.triggered.connect(self.remove_cfg_file)
                elif (selected_item.column() == 1):
                    # edit the selected control file
                    if os.path.isfile(selected_item.text()):
                        self.context_menu.actionEditInputFile = QtWidgets.QAction(self)
                        self.context_menu.actionEditInputFile.setText("Edit")
                        self.context_menu.addAction(self.context_menu.actionEditInputFile)
                        arg = lambda: self.main_gui.file_open(file_uri=selected_item.text())
                        self.context_menu.actionEditInputFile.triggered.connect(arg)
                    # browse for a control file
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
        elif level == 3:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_batch_gui(self):
        """ Edit batch control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "batch"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Levels"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_keyval_by_val_name(self, section, val):
        """ Get the value from a section based on the value name."""
        found = False
        key_child = ""
        val_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 1).text()) == str(val):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        level = 0
        idx = self.view.selectedIndexes()[0]
        while idx.parent().isValid():
            idx = idx.parent()
            level += 1
        return level

    def get_model_from_data(self):
        """ Build model from the control file."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be some way to do this recursively
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(val))
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Levels"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    for val in self.cfg[key1][key2]:
                        value = self.cfg[key1][key2][val]
                        child0 = QtGui.QStandardItem(val)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(str(value))
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Levels"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_cfg_file(self):
        """ Remove a control file from the level section."""
        # remove the item
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def renumber_subsection_keys(self, subsection):
        """ Renumber the subsection keys when an item is removed."""
        for i in range(subsection.rowCount()):
            child = subsection.child(i)
            child.setText(str(i))
        return

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_batch_sites(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_batch_sites, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.main_gui = main_gui
        self.tabs = main_gui.tabs
        self.implemented_levels = ["L1", "L2", "L3",
                                   "nc2csv_oneflux",
                                   "concatenate", "climatology",
                                   "cpd_barr", "cpd_mchugh", "cpd_mcnew", "mpt",
                                   "L4", "L5", "L6"]
        self.edit_batch_gui()

    def add_control_file(self):
        """ Add an entry for a new input file."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        dict_to_add = {str(subsection.rowCount()): "Right click to browse"}
        # add the subsubsection
        self.add_subsection(subsection, dict_to_add)

    def add_control_file_above(self):
        """ Add a new control file above the selected entry."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        new_file_number = min([0, int(float(selected_item.text()))-1])
        # get the parent of the selected item
        parent = selected_item.parent()
        # insert the new file entry
        new_file_entry = [QtGui.QStandardItem(str(new_file_number)),
                          QtGui.QStandardItem("Right click to browse")]
        parent.insertRow(idx.row(), new_file_entry)
        # renumber the section
        self.renumber_subsection_keys(parent)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        return

    def add_site(self):
        """ Add a site to be processed."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        dict_to_add = {"<site_name>": {"0": "Right click to browse"}}
        # add the subsubsection
        self.add_subsubsection(selected_item, dict_to_add)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_site_above(self):
        """ Add a new site above the selected entry."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # insert the new site entry
        new_site_entry = QtGui.QStandardItem("<site_name>")
        new_site_entry.appendRow([QtGui.QStandardItem("0"),
                                 QtGui.QStandardItem("Right click to browse")])
        parent.insertRow(idx.row(), new_site_entry)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        return

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def add_subsubsection(self, subsection, dict_to_add):
        """ Add a subsubsection to the model."""
        for key in dict_to_add:
            subsubsection = QtGui.QStandardItem(key)
            #subsubsection.setEditable(False)
            self.add_subsection(subsubsection, dict_to_add[key])
            subsection.appendRow(subsubsection)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path)[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_path = QtCore.QDir.toNativeSeparators(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_path)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            #existing_entries = self.get_existing_entries()
            # sections with only 1 level
            if selected_text == "Options":
                pass
            elif selected_text == "Sites":
                site_text = "Add site"
                self.context_menu.actionAddSite = QtWidgets.QAction(self)
                self.context_menu.actionAddSite.setText(site_text)
                self.context_menu.addAction(self.context_menu.actionAddSite)
                self.context_menu.actionAddSite.triggered.connect(self.add_site)
        elif level == 1:
            parent = selected_item.parent()
            if str(parent.text()) == "Sites":
                self.context_menu.actionAddControlFile = QtWidgets.QAction(self)
                self.context_menu.actionAddControlFile.setText("Add control file")
                self.context_menu.addAction(self.context_menu.actionAddControlFile)
                self.context_menu.actionAddControlFile.triggered.connect(self.add_control_file)
                self.context_menu.actionAddSiteAbove = QtWidgets.QAction(self)
                self.context_menu.actionAddSiteAbove.setText("Add site")
                self.context_menu.addAction(self.context_menu.actionAddSiteAbove)
                self.context_menu.actionAddSiteAbove.triggered.connect(self.add_site_above)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveSite = QtWidgets.QAction(self)
                self.context_menu.actionRemoveSite.setText("Remove site")
                self.context_menu.addAction(self.context_menu.actionRemoveSite)
                self.context_menu.actionRemoveSite.triggered.connect(self.remove_item)
        elif level == 2:
            parent = selected_item.parent()
            section = selected_item.parent().parent()
            if (str(section.text()) == "Sites"):
                if (selected_item.column() == 0):
                    self.context_menu.actionAddControlFileAbove = QtWidgets.QAction(self)
                    self.context_menu.actionAddControlFileAbove.setText("Add control file")
                    self.context_menu.addAction(self.context_menu.actionAddControlFileAbove)
                    self.context_menu.actionAddControlFileAbove.triggered.connect(self.add_control_file_above)
                    self.context_menu.addSeparator()
                    self.context_menu.actionRemoveInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveInputFile.setText("Remove file")
                    self.context_menu.addAction(self.context_menu.actionRemoveInputFile)
                    self.context_menu.actionRemoveInputFile.triggered.connect(self.remove_cfg_file)
                elif (selected_item.column() == 1):
                    # edit the selected control file
                    if os.path.isfile(selected_item.text()):
                        self.context_menu.actionEditInputFile = QtWidgets.QAction(self)
                        self.context_menu.actionEditInputFile.setText("Edit")
                        self.context_menu.addAction(self.context_menu.actionEditInputFile)
                        arg = lambda: self.main_gui.file_open(file_uri=selected_item.text())
                        self.context_menu.actionEditInputFile.triggered.connect(arg)
                    # browse for a control file
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
        elif level == 3:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_batch_gui(self):
        """ Edit batch control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "batch_sites"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Sites"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_keyval_by_val_name(self, section, val):
        """ Get the value from a section based on the value name."""
        found = False
        key_child = ""
        val_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 1).text()) == str(val):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        level = 0
        idx = self.view.selectedIndexes()[0]
        while idx.parent().isValid():
            idx = idx.parent()
            level += 1
        return level

    def get_model_from_data(self):
        """ Build model from the control file."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be some way to do this recursively
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(val))
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Sites"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    for val in self.cfg[key1][key2]:
                        value = self.cfg[key1][key2][val]
                        child0 = QtGui.QStandardItem(val)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(str(value))
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Levels"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_cfg_file(self):
        """ Remove a control file from the level section."""
        # remove the item
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def renumber_subsection_keys(self, subsection):
        """ Renumber the subsection keys when an item is removed."""
        for i in range(subsection.rowCount()):
            child = subsection.child(i)
            child.setText(str(i))
        return

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L1(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L1, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        # disable editing of essential entries in Files
        self.files_essential = ["file_path", "in_filename", "in_firstdatarow",
                                "in_headerrow", "out_filename"]
        self.edit_L1_gui()

    def add_attribute(self):
        """ Add a variable attribute to a variable in the [Variables] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the new children
        child0 = QtGui.QStandardItem("New attribute")
        child1 = QtGui.QStandardItem("")
        # add them to the parent
        selected_item.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_csv_section(self):
        """ Add a csv section to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        dict_to_add = {"csv":{"name": ""}}
        # add the subsubsection
        self.add_subsubsection(selected_item, dict_to_add)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_csv_variable(self):
        """ Add a new CSV variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        new_var = {"csv":{"name":""},
                   "Attr":{"height": "", "instrument": "", "long_name": "",
                           "statistic_type": "average", "standard_name": "",
                           "units": ""}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_csv_variable_above(self):
        """ Add a new CSV variable above the selected variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # construct the new variable dictionary
        new_var = {"csv":{"name":""},
                   "Attr":{"height": "", "instrument": "", "long_name": "",
                           "statistic_type": "average", "standard_name": "",
                           "units": ""}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.insertRow(idx.row(), subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_function(self):
        """ Add a function to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        dict_to_add = {"Function":{"func": "Right click to browse"}}
        # add the subsubsection
        self.add_subsubsection(selected_item, dict_to_add)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_function_entry(self, source):
        """ Add the selected function to the variables [Function] subsection."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get a list of function names in the source file
        implemented_functions_name = [name for name,data in inspect.getmembers(source, inspect.isfunction)]
        # get the arguments for the functions in the source file
        implemented_functions_data = [data for name,data in inspect.getmembers(source, inspect.isfunction)]
        # get the context menu entry that has been selected
        sender = str(self.context_menu.sender().text())
        sender = sender.replace(" ", "_")
        # get the arguments for the selected function
        args = inspect.getfullargspec(implemented_functions_data[implemented_functions_name.index(sender)])
        # construct the function string
        function_string = sender+"("
        for item in args[0][2:]:
            function_string = function_string + str(item) + ","
        function_string = function_string[:-1] + ")"
        # get the selected item from the index
        item = idx.model().itemFromIndex(idx)
        # change the text of the selected item
        item.setText(function_string)

    def add_global(self):
        """ Add a new entry to the [Global] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the new children
        child0 = QtGui.QStandardItem("New item")
        child1 = QtGui.QStandardItem("")
        selected_item.appendRow([child0, child1])
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_linear(self):
        """ Add a linear correction to a variable."""
        new_qc = {"Linear": {"0": "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_linearrange(self):
        """ Add another date range to the Linear QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_plot_path(self):
        """ Add plot_path to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("plot_path")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_wdoffset(self):
        """ Add an offset to a wind direction variable."""
        new_qc = {"Wd offset": {"0": "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 0.0"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_wdoffsetrange(self):
        """ Add another date range to the wind direction offset correction."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 0.0")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_qc_check(self, selected_item, new_qc):
        for key1 in new_qc:
            parent = QtGui.QStandardItem(key1)
            parent.setEditable(False)
            for key in new_qc[key1]:
                val = str(new_qc[key1][key])
                child0 = QtGui.QStandardItem(key)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent.appendRow([child0, child1])
            selected_item.appendRow(parent)
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def add_subsubsection(self, subsection, dict_to_add):
        """ Add a subsubsection to the model."""
        for key in dict_to_add:
            subsubsection = QtGui.QStandardItem(key)
            self.add_subsection(subsubsection, dict_to_add[key])
            subsection.appendRow(subsubsection)

    def add_xl_variable(self):
        """ Add a new variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        new_var = {"xl":{"sheet":"", "name":""},
                   "Attr":{"height": "", "instrument": "", "long_name": "",
                           "statistic_type": "average", "standard_name": "",
                           "units": ""}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_xl_variable_above(self):
        """ Add a new variable above the selected variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # construct the new variable dictionary
        new_var = {"xl":{"sheet":"", "name":""},
                   "Attr":{"height": "", "instrument": "", "long_name": "",
                           "statistic_type": "average", "standard_name": "",
                           "units": ""}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.insertRow(idx.row(), subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_xl_section(self):
        """ Add an xl section to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        dict_to_add = {"xl":{"sheet": "", "name": ""}}
        # add the subsubsection
        self.add_subsubsection(selected_item, dict_to_add)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...", file_path)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)
            self.update_tab_text()

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        filter_text = "All (*.csv *.xls *.xlsx);;CSV (*.csv);;Excel (*.xls *.xlsx)"
        new_file_path = QtWidgets.QFileDialog.getOpenFileNames(caption="Choose an input file ...",
                                                               directory=file_path,
                                                               filter=filter_text)[0]
        # update the model
        if len(new_file_path) > 0:
            if self.browse_input_file_check_entry(new_file_path):
                new_file_names = []
                for item in new_file_path:
                    new_file_names.append(os.path.split(item)[1])
                s = ",".join(new_file_names)
                parent.child(selected_item.row(), 1).setText(s)
                self.update_header_rows(new_file_names)
                self.update_tab_text()
        return

    def browse_input_file_check_entry(self, new_file_path):
        """
         Check the files selected by the user.  The rukes are:
          1) if the file name ends in .xls or .xlsx then;
             i) only 1 file can be selected
          2) if the file name ends in .csv then;
             i) no more than to 2 files can be selected
             ii) if 2 files are selected they must be full_output
                and biomet
          3) file extensions .xls, .xlsx and .csv can't be mixed
        """
        ok = True
        # check file extensions
        new_file_extensions = []
        new_file_names = []
        for item in new_file_path:
            _, file_extension = os.path.splitext(item)
            new_file_extensions.append(file_extension)
            file_name = os.path.basename(item)
            new_file_names.append(file_name)
        new_file_extension = list(set(new_file_extensions))
        if len(new_file_extension) == 1:
            # check Excel and CSV rules
            if new_file_extension[0].lower() in [".xls", ".xlsx"]:
                if len(new_file_path) == 1:
                    ok = True
                else:
                    msg = " Only 1 Excel workbook can be opened"
                    logger.error(msg)
                    ok = False
            elif new_file_extension[0].lower() in [".csv"]:
                if len(new_file_path) == 1:
                    ok = True
                elif len(new_file_path) == 2:
                    s = ",".join(new_file_names)
                    if "biomet" in s and "full_output" in s:
                        ok = True
                    else:
                        msg = " When opening 2 CSV files, they must be 'biomet' and 'full_output' files"
                        logger.error(msg)
                        ok = False
                else:
                    msg = " No more than 2 CSV files can be opened"
                    logger.error(msg)
                    ok = False
            else:
                msg = " Unrecognised file type (must be .xls, .xlsx or .csv)"
                logger.error(msg)
                ok = False
        else:
            msg = " All input files must be of the same type (same file extension)"
            logger.error(msg)
            ok = False
        return ok

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            self.update_tab_text()

    def edit_L1_gui(self):
        """ Edit L1 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = self.cfg["level"]
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Global", "Output", "General", "Options", "Soil", "Massman"]:
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        for l in range(subsubsection.rowCount()):
                            key4 = str(subsubsection.child(l, 0).text())
                            val4 = str(subsubsection.child(l, 1).text())
                            cfg[key1][key2][key3][key4] = val4
        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item in the model."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            idx = indexes[0]
            while idx.parent().isValid():
                idx = idx.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be some way to do this recursively
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Files", "Global"]:
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    value = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    if key2 in self.files_essential:
                        child0.setEditable(False)
                    child1 = QtGui.QStandardItem(value)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    parent2 = QtGui.QStandardItem(key2)
                    for key3 in sorted(list(self.cfg[key1][key2])):
                        parent3 = QtGui.QStandardItem(key3)
                        parent3.setEditable(False)
                        for key4 in sorted(list(self.cfg[key1][key2][key3])):
                            value = self.cfg[key1][key2][key3][key4]
                            child0 = QtGui.QStandardItem(key4)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(value)
                            parent3.appendRow([child0, child1])
                        parent2.appendRow(parent3)
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Global", "Variables", "Attr", "Plots"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def browse_plot_path(self):
        """ Browse for the plot path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def context_menu(self, position):
        """ Right click context menu."""
        # are we reading an Excel or CSV file?
        basename = self.cfg["Files"]["in_filename"]
        src = "xl"
        if ".csv" in basename.lower():
            src = "csv"
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        add_separator = False
        if level == 0:
            if selected_text == "Files":
                existing_entries = self.get_existing_entries()
                if "file_path" not in existing_entries:
                    self.context_menu.actionAddfile_path = QtWidgets.QAction(self)
                    self.context_menu.actionAddfile_path.setText("Add file_path")
                    self.context_menu.addAction(self.context_menu.actionAddfile_path)
                    self.context_menu.actionAddfile_path.triggered.connect(self.add_file_path)
                if "in_filename" not in existing_entries:
                    self.context_menu.actionAddin_filename = QtWidgets.QAction(self)
                    self.context_menu.actionAddin_filename.setText("Add in_filename")
                    self.context_menu.addAction(self.context_menu.actionAddin_filename)
                    self.context_menu.actionAddin_filename.triggered.connect(self.add_in_filename)
                if "out_filename" not in existing_entries:
                    self.context_menu.actionAddout_filename = QtWidgets.QAction(self)
                    self.context_menu.actionAddout_filename.setText("Add out_filename")
                    self.context_menu.addAction(self.context_menu.actionAddout_filename)
                    self.context_menu.actionAddout_filename.triggered.connect(self.add_out_filename)
                if "plot_path" not in existing_entries:
                    self.context_menu.actionAddplot_path = QtWidgets.QAction(self)
                    self.context_menu.actionAddplot_path.setText("Add plot_path")
                    self.context_menu.addAction(self.context_menu.actionAddplot_path)
                    self.context_menu.actionAddplot_path.triggered.connect(self.add_plot_path)
            elif selected_text == "Global":
                self.context_menu.actionAddGlobal = QtWidgets.QAction(self)
                self.context_menu.actionAddGlobal.setText("Add attribute")
                self.context_menu.addAction(self.context_menu.actionAddGlobal)
                self.context_menu.actionAddGlobal.triggered.connect(self.add_global)
            elif selected_text == "Variables":
                if src == "xl":
                    self.context_menu.actionAddxlVariable = QtWidgets.QAction(self)
                    self.context_menu.actionAddxlVariable.setText("Add xl variable")
                    self.context_menu.addAction(self.context_menu.actionAddxlVariable)
                    self.context_menu.actionAddxlVariable.triggered.connect(self.add_xl_variable)
                elif src == "csv":
                    self.context_menu.actionAddCSVVariable = QtWidgets.QAction(self)
                    self.context_menu.actionAddCSVVariable.setText("Add csv variable")
                    self.context_menu.addAction(self.context_menu.actionAddCSVVariable)
                    self.context_menu.actionAddCSVVariable.triggered.connect(self.add_csv_variable)
        elif level == 1:
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                # check to see if we have the selected subsection
                if key == "file_path":
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key == "in_filename":
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key == "out_filename":
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
                elif key == "plot_path":
                    self.context_menu.actionBrowsePlotPath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowsePlotPath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowsePlotPath)
                    self.context_menu.actionBrowsePlotPath.triggered.connect(self.browse_plot_path)
                else:
                    pass
            if ((str(parent.text()) == "Files") and (selected_item.column() == 0) and
                (selected_item.text() not in self.files_essential)):
                self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveItem)
                self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Global":
                exclude = ["latitude", "longitude", "site_name", "time_step", "time_zone",
                           "Conventions", "data_link", "featureType", "license_name", "license",
                           "publisher_name", "ozflux_link"]
                if selected_item.text() not in exclude:
                    self.context_menu.actionRemoveGlobal = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveGlobal.setText("Remove attribute")
                    self.context_menu.addAction(self.context_menu.actionRemoveGlobal)
                    self.context_menu.actionRemoveGlobal.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Variables":
                existing_entries = self.get_existing_entries()
                if "xl" not in existing_entries and "csv" not in existing_entries:
                    if src == "xl":
                        self.context_menu.actionAddxlSection = QtWidgets.QAction(self)
                        self.context_menu.actionAddxlSection.setText("Add xl section")
                        self.context_menu.addAction(self.context_menu.actionAddxlSection)
                        self.context_menu.actionAddxlSection.triggered.connect(self.add_xl_section)
                    elif src == "csv":
                        self.context_menu.actionAddCSVSection = QtWidgets.QAction(self)
                        self.context_menu.actionAddCSVSection.setText("Add csv section")
                        self.context_menu.addAction(self.context_menu.actionAddCSVSection)
                        self.context_menu.actionAddCSVSection.triggered.connect(self.add_csv_section)
                    add_separator = True
                if "Function" not in existing_entries:
                    self.context_menu.actionAddFunction = QtWidgets.QAction(self)
                    self.context_menu.actionAddFunction.setText("Add Function")
                    self.context_menu.addAction(self.context_menu.actionAddFunction)
                    self.context_menu.actionAddFunction.triggered.connect(self.add_function)
                    add_separator = True
                if "Linear" not in existing_entries:
                    self.context_menu.actionAddLinear = QtWidgets.QAction(self)
                    self.context_menu.actionAddLinear.setText("Add Linear")
                    self.context_menu.addAction(self.context_menu.actionAddLinear)
                    self.context_menu.actionAddLinear.triggered.connect(self.add_linear)
                # 'Wd offset' option only for wind direction variables
                if (("Wd offset" not in existing_entries) and (selected_text[0:2] == "Wd")):
                    self.context_menu.actionAddWdOffset = QtWidgets.QAction(self)
                    self.context_menu.actionAddWdOffset.setText("Add Wd offset")
                    self.context_menu.addAction(self.context_menu.actionAddWdOffset)
                    self.context_menu.actionAddWdOffset.triggered.connect(self.add_wdoffset)
                if add_separator:
                    self.context_menu.addSeparator()
                if src == "xl":
                    self.context_menu.actionAddxlVariableAbove = QtWidgets.QAction(self)
                    self.context_menu.actionAddxlVariableAbove.setText("New xl variable")
                    self.context_menu.addAction(self.context_menu.actionAddxlVariableAbove)
                    self.context_menu.actionAddxlVariableAbove.triggered.connect(self.add_xl_variable_above)
                elif src == "csv":
                    self.context_menu.actionAddCSVVariableAbove = QtWidgets.QAction(self)
                    self.context_menu.actionAddCSVVariableAbove.setText("New csv variable")
                    self.context_menu.addAction(self.context_menu.actionAddCSVVariableAbove)
                    self.context_menu.actionAddCSVVariableAbove.triggered.connect(self.add_csv_variable_above)
                self.context_menu.actionRemoveVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveVariable)
                self.context_menu.actionRemoveVariable.triggered.connect(self.remove_item)
        elif level == 2:
            section_text = str(idx.parent().parent().data())
            if section_text == "Variables":
                if str(idx.data()) == "Attr":
                    self.context_menu.actionAddAttribute = QtWidgets.QAction(self)
                    self.context_menu.actionAddAttribute.setText("Add attribute")
                    self.context_menu.addAction(self.context_menu.actionAddAttribute)
                    self.context_menu.actionAddAttribute.triggered.connect(self.add_attribute)
                elif str(idx.data()) in ["Function", "Linear", "Wd offset", "xl", "csv"]:
                    self.context_menu.actionRemoveSubSubSection = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveSubSubSection.setText("Remove item")
                    self.context_menu.addAction(self.context_menu.actionRemoveSubSubSection)
                    self.context_menu.actionRemoveSubSubSection.triggered.connect(self.remove_item)
                    if str(idx.data()) in ["Linear"]:
                        self.context_menu.actionAddLinearRange = QtWidgets.QAction(self)
                        self.context_menu.actionAddLinearRange.setText("Add date range")
                        self.context_menu.addAction(self.context_menu.actionAddLinearRange)
                        self.context_menu.actionAddLinearRange.triggered.connect(self.add_linearrange)
                        add_separator = True
                    if str(idx.data()) in ["Wd offset"]:
                        self.context_menu.actionAddWdOffsetRange = QtWidgets.QAction(self)
                        self.context_menu.actionAddWdOffsetRange.setText("Add date range")
                        self.context_menu.addAction(self.context_menu.actionAddWdOffsetRange)
                        self.context_menu.actionAddWdOffsetRange.triggered.connect(self.add_wdoffsetrange)
                        add_separator = True
        elif level == 3:
            if ((str(idx.parent().data()) == "Attr") and (selected_item.column() == 0) and
                (selected_item.text() not in ["long_name", "statistic_type", "units"])):
                self.context_menu.actionRemoveAttribute = QtWidgets.QAction(self)
                self.context_menu.actionRemoveAttribute.setText("Remove attribute")
                self.context_menu.addAction(self.context_menu.actionRemoveAttribute)
                self.context_menu.actionRemoveAttribute.triggered.connect(self.remove_item)
            elif (str(idx.parent().data()) == "Function" and (selected_item.column() == 1)):
                # do the units conversion functions
                implemented_func_units = [name for name,data in inspect.getmembers(pfp_func_units, inspect.isfunction)]
                menuUnits = QtWidgets.QMenu(self)
                menuUnits.setTitle("Units")
                actionAddUnitsFunction = {}
                for item in implemented_func_units:
                    actionAddUnitsFunction[item] = QtWidgets.QAction(self)
                    actionAddUnitsFunction[item].setText(str(item.replace("_", " ")))
                    actionAddUnitsFunction[item].triggered.connect(lambda: self.add_function_entry(pfp_func_units))
                    menuUnits.addAction(actionAddUnitsFunction[item])
                # now do the statistics conversion functions
                implemented_func_stats = [name for name,data in inspect.getmembers(pfp_func_stats, inspect.isfunction)]
                menuStats = QtWidgets.QMenu(self)
                menuStats.setTitle("Statistics")
                actionAddStatsFunction = {}
                for item in implemented_func_stats:
                    actionAddStatsFunction[item] = QtWidgets.QAction(self)
                    actionAddStatsFunction[item].setText(str(item.replace("_", " ")))
                    actionAddStatsFunction[item].triggered.connect(lambda: self.add_function_entry(pfp_func_stats))
                    menuStats.addAction(actionAddStatsFunction[item])
                # do the units conversion functions
                implemented_func_transforms = [name for name,data in inspect.getmembers(pfp_func_transforms, inspect.isfunction)]
                menuTransforms = QtWidgets.QMenu(self)
                menuTransforms.setTitle("Transforms")
                actionAddTransformsFunction = {}
                for item in implemented_func_transforms:
                    actionAddTransformsFunction[item] = QtWidgets.QAction(self)
                    actionAddTransformsFunction[item].setText(str(item.replace("_", " ")))
                    actionAddTransformsFunction[item].triggered.connect(lambda: self.add_function_entry(pfp_func_transforms))
                    menuTransforms.addAction(actionAddTransformsFunction[item])
                self.context_menu.addMenu(menuUnits)
                self.context_menu.addMenu(menuStats)
                self.context_menu.addMenu(menuTransforms)
            elif (str(idx.parent().data()) in ["Linear", "Wd offset"] and str(idx.data()) != "0"):
                self.context_menu.actionRemoveExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveExcludeDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveExcludeDateRange)
                self.context_menu.actionRemoveExcludeDateRange.triggered.connect(self.remove_daterange)

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def remove_daterange(self):
        """ Remove a date range from the ustar_threshold section."""
        # remove the date range
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_header_rows(self, new_file_names):
        """
         Check to see if we are reading a full_output and a biomet CSV file
         and update the in_firstdatarow and in_headerrow entries accordingly.
        """
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the row number of in_firstdatarow and in_headerrow in parent
        _, _, _, ifdr = self.get_keyval_by_key_name(parent, "in_firstdatarow")
        _, _, _, ihr = self.get_keyval_by_key_name(parent, "in_headerrow")
        got_ep_output = False
        in_firstdatarow = []
        in_headerrow = []
        for new_file_name in new_file_names:
            if "biomet" in new_file_name:
                got_ep_output = True
                in_firstdatarow.append("3")
                in_headerrow.append("1")
            elif "full_output" in new_file_name:
                got_ep_output = True
                in_firstdatarow.append("4")
                in_headerrow.append("2")
            elif "fluxnet" in new_file_name:
                got_ep_output = True
                in_firstdatarow.append("2")
                in_headerrow.append("1")
            else:
                pass
        if got_ep_output:
            parent.child(ifdr, 1).setText(",".join(in_firstdatarow))
            parent.child(ihr, 1).setText(",".join(in_headerrow))
        return

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L2(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L2, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.main_gui = main_gui
        self.tabs = main_gui.tabs
        self.edit_L2_gui()

    def add_dependencycheck(self):
        """ Add a dependency check to a variable."""
        new_qc = {"DependencyCheck":{"source":""}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_diurnalcheck(self):
        """ Add a diurnal check to a variable."""
        new_qc = {"DiurnalCheck":{"numsd":"5"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludedates(self):
        """ Add an exclude dates check to a variable."""
        new_qc = {"ExcludeDates":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludedaterange(self):
        """ Add another date range to the ExcludeDates QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_excludehours(self):
        """ Add an exclude hours check to a variable."""
        new_qc = {"ExcludeHours":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM,HH:MM,HH:MM, ..."}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludehourrange(self):
        """ Add an exclude hours check to a variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM,HH:MM,HH:MM, ...")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_file_path(self):
        """ Add file_path to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("file_path")
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_in_filename(self):
        """ Add in_filename to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("in_filename")
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_irga_check(self):
        """ Add IRGA check to Options section."""
        new_options = {"IRGA_Check": "Yes"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_irga_type(self):
        """ Add irga_type to Options section."""
        new_options = {"irga_type": "Li-7500RS"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_linear(self):
        """ Add a linear correction to a variable."""
        new_qc = {"Linear": {"0": "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_linearrange(self):
        """ Add another date range to the Linear QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_lowercheck(self):
        """ Add a lower range check to a variable."""
        new_qc = {"LowerCheck":{"0":"YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_lowercheckrange(self):
        """ Add another date range to the LowerCheck QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_madcheck(self):
        """ Add the MAD check to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        if selected_item.text().split("_")[0] == "Fco2":
            edge_threshold = 6
        elif selected_item.text().split("_")[0] in ["Fe", "Fh"]:
            edge_threshold = 100
        else:
            edge_threshold = "20,80"
        new_qc = {"MADCheck":{"Fsd_threshold": 12, "edge_threshold": edge_threshold,
                              "window_size": 13, "zfc": 5.5,}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_options_section(self):
        """ Add an Options section."""
        self.sections["Options"] = QtGui.QStandardItem("Options")
        new_options = {"irga_type": "Li-7500RS", "sonic_type": "CSAT3B",
                       "SONIC_Check": "Yes", "IRGA_Check": "Yes"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.model.insertRow(self.section_headings.index("Variables"), self.sections["Options"])
        self.update_tab_text()

    def add_out_filename(self):
        """ Add out_filename to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("out_filename")
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_plot_path(self):
        """ Add plot_path to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("plot_path")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_qc_check(self, selected_item, new_qc):
        for key1 in new_qc:
            parent = QtGui.QStandardItem(key1)
            parent.setEditable(False)
            for key in new_qc[key1]:
                val = str(new_qc[key1][key])
                child0 = QtGui.QStandardItem(key)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent.appendRow([child0, child1])
            selected_item.appendRow(parent)
        self.update_tab_text()

    def add_rangecheck(self):
        """ Add a range check to a variable."""
        new_qc = {"RangeCheck":{"lower":0, "upper": 1}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_scatterplot(self):
        """ Add a new scatter plot to the 'Plots' section."""
        new_plot = {"type":"xy", "xseries":"", "yseries":""}
        parent = QtGui.QStandardItem("New scatter plot")
        for key in new_plot:
            val = new_plot[key]
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(str(val))
            parent.appendRow([child0, child1])
        self.sections["Plots"].appendRow(parent)
        self.update_tab_text()

    def add_sonic_check(self):
        """ Add sonic check to Options section."""
        new_options = {"SONIC_Check": "Yes"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_sonic_type(self):
        """ Add sonic_type to Options section."""
        new_options = {"sonic_type": "CSAT3B"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def add_subsubsection(self, subsection, dict_to_add):
        """ Add a subsubsection to the model."""
        for key in dict_to_add:
            subsubsection = QtGui.QStandardItem(key)
            self.add_subsection(subsubsection, dict_to_add[key])
            subsection.appendRow(subsubsection)

    def add_timeseries(self):
        """ Add a new time series to the 'Plots' section."""
        new_plot = {"variables":""}
        parent = QtGui.QStandardItem("New time series")
        for key in new_plot:
            value = new_plot[key]
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(str(value))
            parent.appendRow([child0, child1])
        self.sections["Plots"].appendRow(parent)
        self.update_tab_text()

    def add_uppercheck(self):
        """ Add a upper range check to a variable."""
        new_qc = {"UpperCheck":{"0":"YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_uppercheckrange(self):
        """ Add another date range to the UpperCheck QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        new_var_qc = {"RangeCheck":{"lower":0, "upper": 1}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var_qc)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_variable_above(self):
        """ Add a new variable above the selected variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # construct the new variable dictionary
        new_var = {"RangeCheck":{"lower":0, "upper": 1}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.insertRow(idx.row(), subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_winddirectioncorrection(self):
        """ Add the wind direction correction check to a variable."""
        new_qc = {"CorrectWindDirection":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <correction>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_winddirectioncorrectionrange(self):
        """ Add another date range to the wind direction correction."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <correction>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_plot_path(self):
        """ Browse for the plot path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            add_separator = False
            selected_text = str(idx.data())
            self.section_headings = []
            root = self.model.invisibleRootItem()
            for i in range(root.rowCount()):
                self.section_headings.append(str(root.child(i).text()))
            if "Options" not in self.section_headings and selected_text == "Files":
                self.context_menu.actionAddOptionsSection = QtWidgets.QAction(self)
                self.context_menu.actionAddOptionsSection.setText("Add Options section")
                self.context_menu.addAction(self.context_menu.actionAddOptionsSection)
                self.context_menu.actionAddOptionsSection.triggered.connect(self.add_options_section)
                add_separator = True
            if selected_text == "Files":
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                existing_entries = self.get_existing_entries()
                if "file_path" not in existing_entries:
                    self.context_menu.actionAddfile_path = QtWidgets.QAction(self)
                    self.context_menu.actionAddfile_path.setText("Add file_path")
                    self.context_menu.addAction(self.context_menu.actionAddfile_path)
                    self.context_menu.actionAddfile_path.triggered.connect(self.add_file_path)
                if "in_filename" not in existing_entries:
                    self.context_menu.actionAddin_filename = QtWidgets.QAction(self)
                    self.context_menu.actionAddin_filename.setText("Add in_filename")
                    self.context_menu.addAction(self.context_menu.actionAddin_filename)
                    self.context_menu.actionAddin_filename.triggered.connect(self.add_in_filename)
                if "out_filename" not in existing_entries:
                    self.context_menu.actionAddout_filename = QtWidgets.QAction(self)
                    self.context_menu.actionAddout_filename.setText("Add out_filename")
                    self.context_menu.addAction(self.context_menu.actionAddout_filename)
                    self.context_menu.actionAddout_filename.triggered.connect(self.add_out_filename)
                if "plot_path" not in existing_entries:
                    self.context_menu.actionAddplot_path = QtWidgets.QAction(self)
                    self.context_menu.actionAddplot_path.setText("Add plot_path")
                    self.context_menu.addAction(self.context_menu.actionAddplot_path)
                    self.context_menu.actionAddplot_path.triggered.connect(self.add_plot_path)
            elif selected_text == "Options":
                existing_entries = self.get_existing_entries()
                if "irga_type" not in existing_entries:
                    self.context_menu.actionirgatype = QtWidgets.QAction(self)
                    self.context_menu.actionirgatype.setText("irga_type")
                    self.context_menu.addAction(self.context_menu.actionirgatype)
                    self.context_menu.actionirgatype.triggered.connect(self.add_irga_type)
                    add_separator = True
                if "sonic_type" not in existing_entries:
                    self.context_menu.actionsonictype = QtWidgets.QAction(self)
                    self.context_menu.actionsonictype.setText("sonic_type")
                    self.context_menu.addAction(self.context_menu.actionsonictype)
                    self.context_menu.actionsonictype.triggered.connect(self.add_sonic_type)
                    add_separator = True
                if "SONIC_Check" not in existing_entries:
                    self.context_menu.actionSonicCheck = QtWidgets.QAction(self)
                    self.context_menu.actionSonicCheck.setText("SONIC_Check")
                    self.context_menu.addAction(self.context_menu.actionSonicCheck)
                    self.context_menu.actionSonicCheck.triggered.connect(self.add_sonic_check)
                    add_separator = True
                if "IRGA_Check" not in existing_entries:
                    self.context_menu.actionIRGACheck = QtWidgets.QAction(self)
                    self.context_menu.actionIRGACheck.setText("IRGA_Check")
                    self.context_menu.addAction(self.context_menu.actionIRGACheck)
                    self.context_menu.actionIRGACheck.triggered.connect(self.add_irga_check)
                    add_separator = True
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                self.context_menu.actionRemoveOptionsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOptionsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveOptionsSection)
                self.context_menu.actionRemoveOptionsSection.triggered.connect(self.remove_section)
            elif selected_text == "Variables":
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_variable)
            elif selected_text == "Plots":
                self.context_menu.actionAddTimeSeries = QtWidgets.QAction(self)
                self.context_menu.actionAddTimeSeries.setText("Add time series")
                self.context_menu.addAction(self.context_menu.actionAddTimeSeries)
                self.context_menu.actionAddTimeSeries.triggered.connect(self.add_timeseries)
                self.context_menu.actionAddScatterPlot = QtWidgets.QAction(self)
                self.context_menu.actionAddScatterPlot.setText("Add scatter plot")
                self.context_menu.addAction(self.context_menu.actionAddScatterPlot)
                self.context_menu.actionAddScatterPlot.triggered.connect(self.add_scatterplot)
        elif level == 1:
            selected_item = idx.model().itemFromIndex(idx)
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                # check to see if we have the selected subsection
                if key == "file_path":
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key == "in_filename":
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                    self.context_menu.actionOpenInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionOpenInputFile.setText("Open...")
                    self.context_menu.addAction(self.context_menu.actionOpenInputFile)
                    self.context_menu.actionOpenInputFile.triggered.connect(self.open_netcdf_file)
                elif key == "out_filename":
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
                    self.context_menu.actionOpenOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionOpenOutputFile.setText("Open...")
                    self.context_menu.addAction(self.context_menu.actionOpenOutputFile)
                    self.context_menu.actionOpenOutputFile.triggered.connect(self.open_netcdf_file)
                elif key == "plot_path":
                    self.context_menu.actionBrowsePlotPath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowsePlotPath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowsePlotPath)
                    self.context_menu.actionBrowsePlotPath.triggered.connect(self.browse_plot_path)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key == "irga_type":
                    existing_entry = str(parent.child(selected_item.row(),1).text())
                    if existing_entry != "Li-7500":
                        self.context_menu.actionSetIRGATypeLi7500 = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeLi7500.setText("Li-7500")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeLi7500)
                        self.context_menu.actionSetIRGATypeLi7500.triggered.connect(self.set_irga_li7500)
                    if existing_entry != "Li-7500A":
                        self.context_menu.actionSetIRGATypeLi7500A = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeLi7500A.setText("Li-7500A")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeLi7500A)
                        self.context_menu.actionSetIRGATypeLi7500A.triggered.connect(self.set_irga_li7500a)
                    if existing_entry != "Li-7500RS":
                        self.context_menu.actionSetIRGATypeLi7500RS = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeLi7500RS.setText("Li-7500RS")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeLi7500RS)
                        self.context_menu.actionSetIRGATypeLi7500RS.triggered.connect(self.set_irga_li7500rs)
                    if existing_entry != "Li-7200":
                        self.context_menu.actionSetIRGATypeLi7200 = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeLi7200.setText("Li-7200")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeLi7200)
                        self.context_menu.actionSetIRGATypeLi7200.triggered.connect(self.set_irga_li7200)
                    if existing_entry != "Li-7200RS":
                        self.context_menu.actionSetIRGATypeLi7200RS = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeLi7200RS.setText("Li-7200RS")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeLi7200RS)
                        self.context_menu.actionSetIRGATypeLi7200RS.triggered.connect(self.set_irga_li7200RS)
                    if existing_entry != "EC150":
                        self.context_menu.actionSetIRGATypeEC150 = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeEC150.setText("EC150")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeEC150)
                        self.context_menu.actionSetIRGATypeEC150.triggered.connect(self.set_irga_ec150)
                    if existing_entry != "EC155":
                        self.context_menu.actionSetIRGATypeEC155 = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeEC155.setText("EC155")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeEC155)
                        self.context_menu.actionSetIRGATypeEC155.triggered.connect(self.set_irga_ec155)
                    if existing_entry != "IRGASON":
                        self.context_menu.actionSetIRGATypeIRGASON = QtWidgets.QAction(self)
                        self.context_menu.actionSetIRGATypeIRGASON.setText("IRGASON")
                        self.context_menu.addAction(self.context_menu.actionSetIRGATypeIRGASON)
                        self.context_menu.actionSetIRGATypeIRGASON.triggered.connect(self.set_irga_irgason)
                elif key == "sonic_type":
                    existing_entry = str(parent.child(selected_item.row(),1).text())
                    if existing_entry != "CSAT3":
                        self.context_menu.actionSetSonicTypeCSAT3 = QtWidgets.QAction(self)
                        self.context_menu.actionSetSonicTypeCSAT3.setText("CSAT3")
                        self.context_menu.addAction(self.context_menu.actionSetSonicTypeCSAT3)
                        self.context_menu.actionSetSonicTypeCSAT3.triggered.connect(self.set_sonic_csat3)
                    if existing_entry != "CSAT3A":
                        self.context_menu.actionSetSonicTypeCSAT3A = QtWidgets.QAction(self)
                        self.context_menu.actionSetSonicTypeCSAT3A.setText("CSAT3A")
                        self.context_menu.addAction(self.context_menu.actionSetSonicTypeCSAT3A)
                        self.context_menu.actionSetSonicTypeCSAT3A.triggered.connect(self.set_sonic_csat3a)
                    if existing_entry != "CSAT3B":
                        self.context_menu.actionSetSonicTypeCSAT3B = QtWidgets.QAction(self)
                        self.context_menu.actionSetSonicTypeCSAT3B.setText("CSAT3B")
                        self.context_menu.addAction(self.context_menu.actionSetSonicTypeCSAT3B)
                        self.context_menu.actionSetSonicTypeCSAT3B.triggered.connect(self.set_sonic_csat3b)
                elif key in ["SONIC_Check", "IRGA_Check"]:
                    existing_entry = str(parent.child(selected_item.row(),1).text())
                    if existing_entry != "Yes":
                        self.context_menu.actionSetCheckYes = QtWidgets.QAction(self)
                        self.context_menu.actionSetCheckYes.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionSetCheckYes)
                        self.context_menu.actionSetCheckYes.triggered.connect(self.set_check_yes)
                    if existing_entry != "No":
                        self.context_menu.actionSetCheckNo = QtWidgets.QAction(self)
                        self.context_menu.actionSetCheckNo.setText("No")
                        self.context_menu.addAction(self.context_menu.actionSetCheckNo)
                        self.context_menu.actionSetCheckNo.triggered.connect(self.set_check_no)
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                if selected_item.text() in ["irga_type", "sonic_type", "SONIC_Check", "IRGA_Check"]:
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Variables":
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                # only put a QC check in the context menu if it is not already present
                if "RangeCheck" not in existing_entries:
                    self.context_menu.actionAddRangeCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddRangeCheck.setText("Add RangeCheck")
                    self.context_menu.addAction(self.context_menu.actionAddRangeCheck)
                    self.context_menu.actionAddRangeCheck.triggered.connect(self.add_rangecheck)
                if "DependencyCheck" not in existing_entries:
                    self.context_menu.actionAddDependencyCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDependencyCheck.setText("Add DependencyCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDependencyCheck)
                    self.context_menu.actionAddDependencyCheck.triggered.connect(self.add_dependencycheck)
                if "DiurnalCheck" not in existing_entries:
                    self.context_menu.actionAddDiurnalCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDiurnalCheck.setText("Add DiurnalCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDiurnalCheck)
                    self.context_menu.actionAddDiurnalCheck.triggered.connect(self.add_diurnalcheck)
                if "ExcludeDates" not in existing_entries:
                    self.context_menu.actionAddExcludeDates = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeDates.setText("Add ExcludeDates")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeDates)
                    self.context_menu.actionAddExcludeDates.triggered.connect(self.add_excludedates)
                if "ExcludeHours" not in existing_entries:
                    self.context_menu.actionAddExcludeHours = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeHours.setText("Add ExcludeHours")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeHours)
                    self.context_menu.actionAddExcludeHours.triggered.connect(self.add_excludehours)
                if "LowerCheck" not in existing_entries:
                    self.context_menu.actionAddLowerCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddLowerCheck.setText("Add LowerCheck")
                    self.context_menu.addAction(self.context_menu.actionAddLowerCheck)
                    self.context_menu.actionAddLowerCheck.triggered.connect(self.add_lowercheck)
                if "MADCheck" not in existing_entries:
                    self.context_menu.actionAddMADCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddMADCheck.setText("Add MADCheck")
                    self.context_menu.addAction(self.context_menu.actionAddMADCheck)
                    self.context_menu.actionAddMADCheck.triggered.connect(self.add_madcheck)
                if "UpperCheck" not in existing_entries:
                    self.context_menu.actionAddUpperCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddUpperCheck.setText("Add UpperCheck")
                    self.context_menu.addAction(self.context_menu.actionAddUpperCheck)
                    self.context_menu.actionAddUpperCheck.triggered.connect(self.add_uppercheck)
                if "CorrectWindDirection" not in existing_entries:
                    self.context_menu.actionAddWindDirectionCorrection = QtWidgets.QAction(self)
                    self.context_menu.actionAddWindDirectionCorrection.setText("Add CorrectWindDirection")
                    self.context_menu.addAction(self.context_menu.actionAddWindDirectionCorrection)
                    self.context_menu.actionAddWindDirectionCorrection.triggered.connect(self.add_winddirectioncorrection)
                if "Linear" not in existing_entries:
                    self.context_menu.actionAddLinear = QtWidgets.QAction(self)
                    self.context_menu.actionAddLinear.setText("Add Linear")
                    self.context_menu.addAction(self.context_menu.actionAddLinear)
                    self.context_menu.actionAddLinear.triggered.connect(self.add_linear)
                self.context_menu.addSeparator()
                self.context_menu.actionAddVariableAbove = QtWidgets.QAction(self)
                self.context_menu.actionAddVariableAbove.setText("New variable")
                self.context_menu.addAction(self.context_menu.actionAddVariableAbove)
                self.context_menu.actionAddVariableAbove.triggered.connect(self.add_variable_above)
                self.context_menu.actionRemoveVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveVariable)
                self.context_menu.actionRemoveVariable.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Plots":
                self.context_menu.actionDisablePlot = QtWidgets.QAction(self)
                self.context_menu.actionDisablePlot.setText("Disable plot")
                self.context_menu.addAction(self.context_menu.actionDisablePlot)
                self.context_menu.actionDisablePlot.triggered.connect(self.disable_plot)
                self.context_menu.actionEnablePlot = QtWidgets.QAction(self)
                self.context_menu.actionEnablePlot.setText("Enable plot")
                self.context_menu.addAction(self.context_menu.actionEnablePlot)
                self.context_menu.actionEnablePlot.triggered.connect(self.enable_plot)
                self.context_menu.actionRemovePlot = QtWidgets.QAction(self)
                self.context_menu.actionRemovePlot.setText("Remove plot")
                self.context_menu.addAction(self.context_menu.actionRemovePlot)
                self.context_menu.actionRemovePlot.triggered.connect(self.remove_item)
        elif level == 2:
            add_separator = False
            if str(idx.data()) in ["ExcludeDates"]:
                self.context_menu.actionPickDateRange = QtWidgets.QAction(self)
                self.context_menu.actionPickDateRange.setText("Pick date range")
                self.context_menu.addAction(self.context_menu.actionPickDateRange)
                self.context_menu.actionPickDateRange.triggered.connect(self.pick_excludedaterange)
                self.context_menu.actionAddExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeDateRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeDateRange)
                self.context_menu.actionAddExcludeDateRange.triggered.connect(self.add_excludedaterange)
                add_separator = True
            if str(idx.data()) in ["ExcludeHours"]:
                self.context_menu.actionAddExcludeHourRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeHourRange.setText("Add hour range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeHourRange)
                self.context_menu.actionAddExcludeHourRange.triggered.connect(self.add_excludehourrange)
                add_separator = True
            if str(idx.data()) in ["LowerCheck"]:
                self.context_menu.actionAddLowerCheckRange = QtWidgets.QAction(self)
                self.context_menu.actionAddLowerCheckRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddLowerCheckRange)
                self.context_menu.actionAddLowerCheckRange.triggered.connect(self.add_lowercheckrange)
                add_separator = True
            if str(idx.data()) in ["UpperCheck"]:
                self.context_menu.actionAddUpperCheckRange = QtWidgets.QAction(self)
                self.context_menu.actionAddUpperCheckRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddUpperCheckRange)
                self.context_menu.actionAddUpperCheckRange.triggered.connect(self.add_uppercheckrange)
                add_separator = True
            if str(idx.data()) in ["CorrectWindDirection"]:
                self.context_menu.actionAddWindDirectionCorrectionRange = QtWidgets.QAction(self)
                self.context_menu.actionAddWindDirectionCorrectionRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddWindDirectionCorrectionRange)
                self.context_menu.actionAddWindDirectionCorrectionRange.triggered.connect(self.add_winddirectioncorrectionrange)
                add_separator = True
            if str(idx.data()) in ["Linear"]:
                self.context_menu.actionAddLinearRange = QtWidgets.QAction(self)
                self.context_menu.actionAddLinearRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddLinearRange)
                self.context_menu.actionAddLinearRange.triggered.connect(self.add_linearrange)
                add_separator = True
            if add_separator:
                self.context_menu.addSeparator()
                add_separator = False
            if str(idx.data()) in ["RangeCheck", "DependencyCheck", "DiurnalCheck", "ExcludeDates",
                                   "ExcludeHours", "LowerCheck", "MADCheck", "UpperCheck"]:
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
        elif level == 3:
            if (str(idx.parent().data()) in ["ExcludeDates", "ExcludeHours", "LowerCheck",
                                             "UpperCheck", "Linear"] and
                str(idx.data()) != "0"):
                self.context_menu.actionRemoveExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveExcludeDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveExcludeDateRange)
                self.context_menu.actionRemoveExcludeDateRange.triggered.connect(self.remove_daterange)

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def disable_plot(self):
        """ Disable a plot by adding '[disabled]' to the title."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        if "(disabled)" not in selected_text:
            selected_text = "(disabled)" + selected_text
        selected_item.setText(selected_text)
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_L2_gui(self):
        """ Edit L2 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def enable_plot(self):
        """ Enable a plot by removing '[disabled]' from the title."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        if "(disabled)" in selected_text:
            selected_text = selected_text.replace("(disabled)", "")
        selected_item.setText(selected_text)
        return

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "L2"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Plots"]:
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
            elif key1 in ["Variables"]:
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        for l in range(subsubsection.rowCount()):
                            key4 = str(subsubsection.child(l, 0).text())
                            val4 = str(subsubsection.child(l, 1).text())
                            cfg[key1][key2][key3][key4] = val4
        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item in the model."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            idx = indexes[0]
            while idx.parent().isValid():
                idx = idx.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be some way to do this recursively
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    value = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(value)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif  key1 in ["Plots"]:
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    for key3 in self.cfg[key1][key2]:
                        value = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(value)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 3 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    parent2 = QtGui.QStandardItem(key2)
                    for key3 in sorted(list(self.cfg[key1][key2].keys())):
                        parent3 = QtGui.QStandardItem(key3)
                        parent3.setEditable(False)
                        for key4 in sorted(list(self.cfg[key1][key2][key3].keys())):
                            value = self.cfg[key1][key2][key3][key4]
                            child0 = QtGui.QStandardItem(key4)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(value)
                            parent3.appendRow([child0, child1])
                        parent2.appendRow(parent3)
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Global", "Variables", "Attr", "Plots"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        # update the control file contents
        self.cfg = self.get_data_from_model()

    def open_netcdf_file(self):
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        if len(selected_item.text()) == 0:
            return
        file_path = self.cfg["Files"]["file_path"]
        file_name = selected_item.text()
        file_uri = os.path.join(file_path, file_name)
        if not os.path.isfile(file_uri):
            return
        self.main_gui.file_open(file_uri=file_uri)
        return

    def pick_excludedaterange(self):
        self.cfg = self.get_data_from_model()
        nc_uri = os.path.join(self.cfg["Files"]["file_path"], self.cfg["Files"]["in_filename"])
        logger.info(" calling NetCDFRead from edit_cfg_L2")
        self.ds = pfp_io.NetCDFRead(nc_uri)
        # get the selected variable
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        label =  parent.text()
        pfp_ck.do_qcchecks_oneseries(self.cfg, self.ds, "Variables", label)
        self.var = pfp_utils.GetVariable(self.ds, label)
        self.qc_dialog =  pick_exclude_date_range(self.var, parent=self)
        if self.qc_dialog.exec_():
            #print(self.qc_dialog.deletion_log)
            delete_points = self.qc_dialog.deletion_log
            idx = self.view.selectedIndexes()[0]
            selected_item = idx.model().itemFromIndex(idx)
            for i in range(len(delete_points)):
                start = delete_points[i][0].strftime("%Y-%m-%d %H:%M")
                end = delete_points[i][1].strftime("%Y-%m-%d %H:%M")
                rowCount = selected_item.rowCount()
                child = selected_item.child(rowCount-1, 1)
                if child.text() == "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM":
                    child.setText(start+","+end)
                else:
                    child0 = QtGui.QStandardItem(str(rowCount))
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(start+","+end)
                    selected_item.appendRow([child0, child1])
            self.update_tab_text()
        else:
            #print("QC cancelled by user")
            pass
        return

    def remove_daterange(self):
        """ Remove a date range from the ustar_threshold section."""
        # remove the date range
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def remove_section(self):
        """ Remove a section from the view."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the root
        root = self.model.invisibleRootItem()
        # remove the row
        root.removeRow(selected_item.row())
        self.update_tab_text()

    def set_check_no(self):
        """ Set the Sonic check to No."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("No")

    def set_check_yes(self):
        """ Set the Sonic check to Yes."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Yes")

    def set_irga_ec150(self):
        """ Set the IRGA type to EC150."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("EC150")

    def set_irga_ec155(self):
        """ Set the IRGA type to EC155."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("EC155")

    def set_irga_irgason(self):
        """ Set the IRGA type to IRGASON."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("IRGASON")

    def set_irga_li7500(self):
        """ Set the IRGA type to Li-7500."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Li-7500")

    def set_irga_li7500a(self):
        """ Set the IRGA type to Li-7500A (pre and post V6.5)."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Li-7500A")

    def set_irga_li7500rs(self):
        """ Set the IRGA type to Li-7500RS."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Li-7500RS")

    def set_irga_li7200(self):
        """ Set the IRGA type to Li-7200."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Li-7200")

    def set_irga_li7200RS(self):
        """ Set the IRGA type to Li-7200RS."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("Li-7200RS")

    def set_sonic_csat3(self):
        """ Set the sonic type to CSAT3."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("CSAT3")

    def set_sonic_csat3a(self):
        """ Set the sonic type to CSAT3A."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("CSAT3A")

    def set_sonic_csat3b(self):
        """ Set the sonic type to CSAT3B."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("CSAT3B")

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L3(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L3, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.load_netcdf_async()
        self.main_gui = main_gui
        self.tabs = main_gui.tabs
        self.edit_L3_gui()

    def add_2dcoordrotation(self):
        """ Add 2DCoordRotation to the [Options] section."""
        child0 = QtGui.QStandardItem("2DCoordRotation")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_applyfco2storage_to_options(self):
        """ Add storage term to Fco2 to the [Options] section."""
        child0 = QtGui.QStandardItem("ApplyFco2Storage")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_applyfco2storage_to_variable(self):
        """ Add apply Fco2 storage instruction to a variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        parent = QtGui.QStandardItem("ApplyFco2Storage")
        child0 = QtGui.QStandardItem("source")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("")
        parent.appendRow([child0, child1])
        selected_item.appendRow(parent)
        self.update_tab_text()

    def add_averageseries(self):
        """ Add an average series instruction to a variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        parent = QtGui.QStandardItem("AverageSeries")
        child0 = QtGui.QStandardItem("source")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("")
        parent.appendRow([child0, child1])
        selected_item.appendRow(parent)
        self.update_tab_text()

    def add_correctindividualfg(self):
        """ Add correct individual Fg to the [Options] section."""
        child0 = QtGui.QStandardItem("CorrectIndividualFg")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("No")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_correctfgforstorage(self):
        """ Add correct Fg for storage to the [Options] section."""
        child0 = QtGui.QStandardItem("CorrectFgForStorage")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_co2units_to_options(self):
        """ Add CO2 units to the [Options] section."""
        child0 = QtGui.QStandardItem("CO2Units")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("umol/mol")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_dependencycheck(self):
        """ Add a dependency check to a variable."""
        new_qc = {"DependencyCheck":{"source":""}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_diurnalcheck(self):
        """ Add a diurnal check to a variable."""
        new_qc = {"DiurnalCheck":{"numsd":"5"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludedates(self):
        """ Add an exclude dates check to a variable."""
        new_qc = {"ExcludeDates":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludedaterange(self):
        """ Add another date range to the ExcludeDates QC check."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_excludehours(self):
        """ Add an exclude hours check to a variable."""
        new_qc = {"ExcludeHours":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM,HH:MM,HH:MM, ..."}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_excludehourrange(self):
        """ Add an exclude hours check to a variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM,HH:MM,HH:MM, ...")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_fco2units_to_options(self):
        """ Add Fco2 units to the [Options] section."""
        child0 = QtGui.QStandardItem("Fco2Units")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("umol/m^2/s")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_fileentry(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        # get the sender
        s = self.context_menu.sender().text()
        file_entry = s.rsplit(" ", 1)[-1]
        dict_to_add = {file_entry: "Right click to browse"}
        # add the subsection
        self.add_subsection(section, dict_to_add)
        # update the tab text
        self.update_tab_text()

    def add_file_path(self):
        """ Add file_path to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("file_path")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_imports_section(self):
        """ Add an Imports section."""
        self.sections["Imports"] = QtGui.QStandardItem("Imports")
        self.add_imports_variable()
        self.model.insertRow(self.section_headings.index("Files")+1, self.sections["Imports"])
        self.update_tab_text()

    def add_imports_variable(self):
        """ Add a variable to the Imports section."""
        new_import = {"file_name": "Right click to browse", "var_name": "<variable_name>"}
        new_variable = QtGui.QStandardItem("New variable")
        for key in new_import:
            val = new_import[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            new_variable.appendRow([child0, child1])
        self.sections["Imports"].appendRow(new_variable)
        self.update_tab_text()

    def add_in_filename(self):
        """ Add in_filename to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("in_filename")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_keepintermediateseries(self):
        """ Add KeepIntermediateSeries to the [Options] section."""
        child0 = QtGui.QStandardItem("KeepIntermediateSeries")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("No")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_madcheck(self):
        """ Add the MAD check to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        if selected_item.text().split("_")[0] == "Fco2":
            edge_threshold = 6
        elif selected_item.text().split("_")[0] in ["Fe", "Fh"]:
            edge_threshold = 100
        else:
            edge_threshold = "20,80"
        new_qc = {"MADCheck":{"Fsd_threshold": 12, "edge_threshold": edge_threshold,
                              "window_size": 13, "zfc": 5.5,}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_massmancorrection(self):
        """ Add Massman correction to the [Options] section."""
        child0 = QtGui.QStandardItem("MassmanCorrection")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_linear(self):
        """ Add a linear correction to a variable."""
        new_qc = {"Linear": {"0": "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_linearrange(self):
        """ Add another date range to the Linear QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, 1.0, 0.0")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_lowercheck(self):
        """ Add a lower range check to a variable."""
        new_qc = {"LowerCheck":{"0":"YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_lowercheckrange(self):
        """ Add another date range to the LowerCheck QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_massman_section(self):
        """ Add a Massman section."""
        self.sections["Massman"] = QtGui.QStandardItem("Massman")
        new_massman = {"zmd": "<height_above_displacement_plane>",
                       "z0": "<roughness_length>",
                       "north_separation": "<north_separation>",
                       "east_separation": "<east_separation>"}
        for key in new_massman:
            value = new_massman[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Massman"].appendRow([child0, child1])
        self.model.insertRow(self.section_headings.index("Variables"), self.sections["Massman"])
        self.update_tab_text()

    def add_mergeseries(self):
        """ Add a merge series instruction to a variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        parent = QtGui.QStandardItem("MergeSeries")
        child0 = QtGui.QStandardItem("source")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("")
        parent.appendRow([child0, child1])
        selected_item.appendRow(parent)
        self.update_tab_text()

    def add_out_filename(self):
        """ Add out_filename to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("out_filename")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_plot_path(self):
        """ Add plot_path to the 'Files' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        child0 = QtGui.QStandardItem("plot_path")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Right click to browse")
        parent.appendRow([child0, child1])
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_qc_check(self, selected_item, new_qc):
        """ Add a QC check to a variable."""
        for key1 in new_qc:
            parent = QtGui.QStandardItem(key1)
            for key in new_qc[key1]:
                val = str(new_qc[key1][key])
                child0 = QtGui.QStandardItem(key)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent.appendRow([child0, child1])
            selected_item.appendRow(parent)
        self.update_tab_text()

    def add_rangecheck(self):
        """ Add a range check to a variable."""
        new_qc = {"RangeCheck":{"lower":0, "upper": 1}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_scatterplot(self):
        """ Add a new scatter plot to the 'Plots' section."""
        new_plot = {"Type":"xy","Title":"", "XSeries":"[]", "YSeries":"[]"}
        parent = QtGui.QStandardItem("New scatter plot")
        for key in new_plot:
            val = new_plot[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(str(val))
            parent.appendRow([child0, child1])
        self.sections["Plots"].appendRow(parent)
        self.update_tab_text()

    def add_soil_section(self):
        """ Add a Soil section."""
        self.sections["Soil"] = QtGui.QStandardItem("Soil")
        new_soil = {"FgDepth": "<depth_of_heat_flux_plate>",
                    "BulkDensity": "<soil_bulk_density>",
                    "OrganicContent": "<soil_organic_content>",
                    "SwsDefault": "<default_soil_moisture>",
                    "SwsSeries": "Sws"}
        for key in new_soil:
            value = new_soil[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Soil"].appendRow([child0, child1])
        self.model.insertRow(self.section_headings.index("Variables"), self.sections["Soil"])
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def add_subsubsection(self, subsection, dict_to_add):
        """ Add a subsubsection to the model."""
        for key in dict_to_add:
            subsubsection = QtGui.QStandardItem(key)
            self.add_subsection(subsubsection, dict_to_add[key])
            subsection.appendRow(subsubsection)

    def add_timeseries(self):
        """ Add a new time series to the 'Plots' section."""
        new_plot = {"variables":""}
        parent = QtGui.QStandardItem("New time series")
        for key in new_plot:
            val = new_plot[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(str(val))
            parent.appendRow([child0, child1])
        self.sections["Plots"].appendRow(parent)
        self.update_tab_text()

    def add_uppercheck(self):
        """ Add a upper range check to a variable."""
        new_qc = {"UpperCheck":{"0":"YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_uppercheckrange(self):
        """ Add another date range to the UpperCheck QC check."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,<start_value>,YYYY-mm-dd HH:MM,<end_value>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_calculatefluxes(self):
        """ Add CalculateFluxes to the [Options] section."""
        child0 = QtGui.QStandardItem("CalculateFluxes")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_usefhvforfh(self):
        """ Add UseFhvforFh to the Options section."""
        child0 = QtGui.QStandardItem("UseFhvforFh")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("Yes")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def add_variable(self):
        new_var_qc = {"RangeCheck":{"lower":0, "upper": 1}}
        parent2 = QtGui.QStandardItem("New variable")
        for key3 in new_var_qc:
            parent3 = QtGui.QStandardItem(key3)
            for key in new_var_qc[key3]:
                val = new_var_qc[key3][key]
                child0 = QtGui.QStandardItem(key)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(str(val))
                parent3.appendRow([child0, child1])
            parent2.appendRow(parent3)
        self.sections["Variables"].appendRow(parent2)
        self.update_tab_text()

    def add_variable_above(self):
        """ Add a new variable above the selected variable."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # construct the new variable dictionary
        new_var = {"RangeCheck":{"lower":0, "upper": 1}}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsubsection(subsection, new_var)
        parent.insertRow(idx.row(), subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_winddirectioncorrection(self):
        """ Add the wind direction correction check to a variable."""
        new_qc = {"CorrectWindDirection":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <correction>"}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_winddirectioncorrectionrange(self):
        """ Add another date range to the wind direction correction."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <correction>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_zms(self):
        """ Add zms to the [Options] section."""
        child0 = QtGui.QStandardItem("zms")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("")
        self.sections["Options"].appendRow([child0, child1])
        self.update_tab_text()

    def browse_alternate_file(self):
        """ Browse for the alternate data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "*.nc"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path, "")
        # dialog for open file
        new_file = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an alternate data file ...",
                                                     directory=file_path, filter=file_filter)[0]
        # quit if cancel button pressed
        if len(str(new_file)) > 0:
            # update the model
            parent.child(selected_item.row(), 1).setText(new_file)

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def change_selected_text(self, new_text):
        """ Change the selected text."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_item.setText(new_text)

    def context_menu(self, position):
        """ Right click context menu."""
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        add_separator = False
        if level == 0:
            # sections with only 1 level
            # get a list of the section headings at the root level
            self.section_headings = []
            root = self.model.invisibleRootItem()
            for i in range(root.rowCount()):
                self.section_headings.append(str(root.child(i).text()))
            if selected_text == "Files":
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                for item in ["plot_path", "file_path", "in_filename", "out_filename"]:
                    if item not in existing_entries:
                        self.context_menu.actionAddFileEntry = QtWidgets.QAction(self)
                        self.context_menu.actionAddFileEntry.setText("Add " + item)
                        self.context_menu.addAction(self.context_menu.actionAddFileEntry)
                        self.context_menu.actionAddFileEntry.triggered.connect(self.add_fileentry)
                        add_separator = True
                if "Imports" not in self.section_headings:
                    self.context_menu.actionAddImportsSection = QtWidgets.QAction(self)
                    self.context_menu.actionAddImportsSection.setText("Add Imports section")
                    self.context_menu.addAction(self.context_menu.actionAddImportsSection)
                    self.context_menu.actionAddImportsSection.triggered.connect(self.add_imports_section)
                    add_separator = True
                if "Massman" not in self.section_headings:
                    self.context_menu.actionAddMassmanSection = QtWidgets.QAction(self)
                    self.context_menu.actionAddMassmanSection.setText("Add Massman section")
                    self.context_menu.addAction(self.context_menu.actionAddMassmanSection)
                    self.context_menu.actionAddMassmanSection.triggered.connect(self.add_massman_section)
                    add_separator = True
                if "Soil" not in self.section_headings:
                    self.context_menu.actionAddSoilSection = QtWidgets.QAction(self)
                    self.context_menu.actionAddSoilSection.setText("Add Soil section")
                    self.context_menu.addAction(self.context_menu.actionAddSoilSection)
                    self.context_menu.actionAddSoilSection.triggered.connect(self.add_soil_section)
                    add_separator = True
            elif selected_text == "Imports":
                self.context_menu.actionAddImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddImportsVariable)
                self.context_menu.actionAddImportsVariable.triggered.connect(self.add_imports_variable)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsSection)
                self.context_menu.actionRemoveImportsSection.triggered.connect(self.remove_section)
            elif selected_text == "Options":
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                if "2DCoordRotation" not in existing_entries:
                    self.context_menu.actionAdd2DCoordRotation = QtWidgets.QAction(self)
                    self.context_menu.actionAdd2DCoordRotation.setText("2DCoordRotation")
                    self.context_menu.addAction(self.context_menu.actionAdd2DCoordRotation)
                    self.context_menu.actionAdd2DCoordRotation.triggered.connect(self.add_2dcoordrotation)
                if "ApplyFco2Storage" not in existing_entries:
                    self.context_menu.actionAddApplyFco2Storage = QtWidgets.QAction(self)
                    self.context_menu.actionAddApplyFco2Storage.setText("ApplyFco2Storage")
                    self.context_menu.addAction(self.context_menu.actionAddApplyFco2Storage)
                    self.context_menu.actionAddApplyFco2Storage.triggered.connect(self.add_applyfco2storage_to_options)
                if "CalculateFluxes" not in existing_entries:
                    self.context_menu.actionAddCalculateFluxes = QtWidgets.QAction(self)
                    self.context_menu.actionAddCalculateFluxes.setText("CalculateFluxes")
                    self.context_menu.addAction(self.context_menu.actionAddCalculateFluxes)
                    self.context_menu.actionAddCalculateFluxes.triggered.connect(self.add_calculatefluxes)
                if "CO2Units" not in existing_entries:
                    self.context_menu.actionAddCO2Units = QtWidgets.QAction(self)
                    self.context_menu.actionAddCO2Units.setText("CO2Units")
                    self.context_menu.addAction(self.context_menu.actionAddCO2Units)
                    self.context_menu.actionAddCO2Units.triggered.connect(self.add_co2units_to_options)
                if "CorrectIndividualFg" not in existing_entries:
                    self.context_menu.actionAddCorrectIndividualFg = QtWidgets.QAction(self)
                    self.context_menu.actionAddCorrectIndividualFg.setText("CorrectIndividualFg")
                    self.context_menu.addAction(self.context_menu.actionAddCorrectIndividualFg)
                    self.context_menu.actionAddCorrectIndividualFg.triggered.connect(self.add_correctindividualfg)
                if "CorrectFgForStorage" not in existing_entries:
                    self.context_menu.actionAddCorrectFgForStorage = QtWidgets.QAction(self)
                    self.context_menu.actionAddCorrectFgForStorage.setText("CorrectFgForStorage")
                    self.context_menu.addAction(self.context_menu.actionAddCorrectFgForStorage)
                    self.context_menu.actionAddCorrectFgForStorage.triggered.connect(self.add_correctfgforstorage)
                if "Fco2Units" not in existing_entries:
                    self.context_menu.actionAddFco2Units = QtWidgets.QAction(self)
                    self.context_menu.actionAddFco2Units.setText("Fco2Units")
                    self.context_menu.addAction(self.context_menu.actionAddFco2Units)
                    self.context_menu.actionAddFco2Units.triggered.connect(self.add_fco2units_to_options)
                if "KeepIntermediateSeries" not in existing_entries:
                    self.context_menu.actionAddKeepIntermediateSeries = QtWidgets.QAction(self)
                    self.context_menu.actionAddKeepIntermediateSeries.setText("KeepIntermediateSeries")
                    self.context_menu.addAction(self.context_menu.actionAddKeepIntermediateSeries)
                    self.context_menu.actionAddKeepIntermediateSeries.triggered.connect(self.add_keepintermediateseries)
                if "MassmanCorrection" not in existing_entries:
                    self.context_menu.actionAddMassmanCorrection = QtWidgets.QAction(self)
                    self.context_menu.actionAddMassmanCorrection.setText("MassmanCorrection")
                    self.context_menu.addAction(self.context_menu.actionAddMassmanCorrection)
                    self.context_menu.actionAddMassmanCorrection.triggered.connect(self.add_massmancorrection)
                if "UseFhvforFh" not in existing_entries:
                    self.context_menu.actionAddUseFhvforFh = QtWidgets.QAction(self)
                    self.context_menu.actionAddUseFhvforFh.setText("UseFhvforFh")
                    self.context_menu.addAction(self.context_menu.actionAddUseFhvforFh)
                    self.context_menu.actionAddUseFhvforFh.triggered.connect(self.add_usefhvforfh)
                if "zms" not in existing_entries:
                    self.context_menu.actionAddzms = QtWidgets.QAction(self)
                    self.context_menu.actionAddzms.setText("Add zms")
                    self.context_menu.addAction(self.context_menu.actionAddzms)
                    self.context_menu.actionAddzms.triggered.connect(self.add_zms)
            elif selected_text in ["Massman", "Soil"]:
                self.context_menu.actionRemoveSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveSection)
                self.context_menu.actionRemoveSection.triggered.connect(self.remove_section)
            elif selected_text == "Variables":
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_variable)
            elif selected_text == "Plots":
                self.context_menu.actionAddTimeSeries = QtWidgets.QAction(self)
                self.context_menu.actionAddTimeSeries.setText("Add time series")
                self.context_menu.addAction(self.context_menu.actionAddTimeSeries)
                self.context_menu.actionAddTimeSeries.triggered.connect(self.add_timeseries)
                self.context_menu.actionAddScatterPlot = QtWidgets.QAction(self)
                self.context_menu.actionAddScatterPlot.setText("Add scatter plot")
                self.context_menu.addAction(self.context_menu.actionAddScatterPlot)
                self.context_menu.actionAddScatterPlot.triggered.connect(self.add_scatterplot)
        elif level == 1:
            # sections with 2 levels
            # get the selected item
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                # check to see if we have the selected subsection
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key == "in_filename":
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                    self.context_menu.actionOpenInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionOpenInputFile.setText("Open...")
                    self.context_menu.addAction(self.context_menu.actionOpenInputFile)
                    self.context_menu.actionOpenInputFile.triggered.connect(self.open_netcdf_file)
                elif key == "out_filename":
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
                    self.context_menu.actionOpenOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionOpenOutputFile.setText("Open...")
                    self.context_menu.addAction(self.context_menu.actionOpenOutputFile)
                    self.context_menu.actionOpenOutputFile.triggered.connect(self.open_netcdf_file)
                else:
                    pass
            elif (str(parent.text()) == "Files") and (selected_item.column() == 0):
                key = str(parent.child(selected_item.row(),0).text())
                if key not in ["file_path", "plot_path", "in_filename", "out_filename"]:
                    self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveItem.setText("Remove item")
                    self.context_menu.addAction(self.context_menu.actionRemoveItem)
                    self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
                else:
                    pass
            elif (str(parent.text()) == "Imports"):
                self.context_menu.actionRemoveImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsVariable)
                self.context_menu.actionRemoveImportsVariable.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Options":
                key = str(parent.child(selected_item.row(),0).text())
                if (selected_item.column() == 0):
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                elif (selected_item.column() == 1) and (key in ["2DCoordRotation", "ApplyFco2Storage",
                                                                "CalculateFluxes", "CorrectIndividualFg",
                                                                "CorrectFgForStorage", "KeepIntermediateSeries",
                                                                "MassmanCorrection", "UseFhvforFh"]):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key in ["CO2Units"]):
                    if selected_text != "umol/mol":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("umol/mol")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("umol/mol"))
                    if selected_text != "mg/m^3":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("mg/m^3")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("mg/m^3"))
                elif (selected_item.column() == 1) and (key in ["Fco2Units"]):
                    if selected_text != "umol/m^2/s":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("umol/m^2/s")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("umol/m^2/s"))
                    if selected_text != "mg/m^2/s":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("mg/m^2/s")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("mg/m^2/s"))
            elif str(parent.text()) == "Variables":
                selected_text = str(idx.data())
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                # only put a QC check in the context menu if it is not already present
                if "RangeCheck" not in existing_entries:
                    self.context_menu.actionAddRangeCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddRangeCheck.setText("Add RangeCheck")
                    self.context_menu.addAction(self.context_menu.actionAddRangeCheck)
                    self.context_menu.actionAddRangeCheck.triggered.connect(self.add_rangecheck)
                if "DependencyCheck" not in existing_entries:
                    self.context_menu.actionAddDependencyCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDependencyCheck.setText("Add DependencyCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDependencyCheck)
                    self.context_menu.actionAddDependencyCheck.triggered.connect(self.add_dependencycheck)
                if "DiurnalCheck" not in existing_entries:
                    self.context_menu.actionAddDiurnalCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDiurnalCheck.setText("Add DiurnalCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDiurnalCheck)
                    self.context_menu.actionAddDiurnalCheck.triggered.connect(self.add_diurnalcheck)
                if "MADCheck" not in existing_entries:
                    self.context_menu.actionAddMADCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddMADCheck.setText("Add MADCheck")
                    self.context_menu.addAction(self.context_menu.actionAddMADCheck)
                    self.context_menu.actionAddMADCheck.triggered.connect(self.add_madcheck)
                if "ExcludeDates" not in existing_entries:
                    self.context_menu.actionAddExcludeDates = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeDates.setText("Add ExcludeDates")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeDates)
                    self.context_menu.actionAddExcludeDates.triggered.connect(self.add_excludedates)
                if "ExcludeHours" not in existing_entries:
                    self.context_menu.actionAddExcludeHours = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeHours.setText("Add ExcludeHours")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeHours)
                    self.context_menu.actionAddExcludeHours.triggered.connect(self.add_excludehours)
                if "LowerCheck" not in existing_entries:
                    self.context_menu.actionAddLowerCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddLowerCheck.setText("Add LowerCheck")
                    self.context_menu.addAction(self.context_menu.actionAddLowerCheck)
                    self.context_menu.actionAddLowerCheck.triggered.connect(self.add_lowercheck)
                if "UpperCheck" not in existing_entries:
                    self.context_menu.actionAddUpperCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddUpperCheck.setText("Add UpperCheck")
                    self.context_menu.addAction(self.context_menu.actionAddUpperCheck)
                    self.context_menu.actionAddUpperCheck.triggered.connect(self.add_uppercheck)
                if "CorrectWindDirection" not in existing_entries:
                    self.context_menu.actionAddWindDirectionCorrection = QtWidgets.QAction(self)
                    self.context_menu.actionAddWindDirectionCorrection.setText("Add CorrectWindDirection")
                    self.context_menu.addAction(self.context_menu.actionAddWindDirectionCorrection)
                    self.context_menu.actionAddWindDirectionCorrection.triggered.connect(self.add_winddirectioncorrection)
                if "Linear" not in existing_entries:
                    self.context_menu.actionAddLinear = QtWidgets.QAction(self)
                    self.context_menu.actionAddLinear.setText("Add Linear")
                    self.context_menu.addAction(self.context_menu.actionAddLinear)
                    self.context_menu.actionAddLinear.triggered.connect(self.add_linear)
                if "ApplyFco2Storage" not in existing_entries and selected_text[0:4] == "Fco2":
                    if selected_text not in ["Fco2_storage", "Fco2_profile", "Fco2_single"]:
                        self.context_menu.addSeparator()
                        self.context_menu.actionAddApplyFco2Storage = QtWidgets.QAction(self)
                        self.context_menu.actionAddApplyFco2Storage.setText("Add ApplyFco2Storage")
                        self.context_menu.addAction(self.context_menu.actionAddApplyFco2Storage)
                        self.context_menu.actionAddApplyFco2Storage.triggered.connect(self.add_applyfco2storage_to_variable)
                self.context_menu.addSeparator()
                if "MergeSeries" not in existing_entries:
                    self.context_menu.actionAddMergeSeries = QtWidgets.QAction(self)
                    self.context_menu.actionAddMergeSeries.setText("Add MergeSeries")
                    self.context_menu.addAction(self.context_menu.actionAddMergeSeries)
                    self.context_menu.actionAddMergeSeries.triggered.connect(self.add_mergeseries)
                if "AverageSeries" not in existing_entries:
                    self.context_menu.actionAddAverageSeries = QtWidgets.QAction(self)
                    self.context_menu.actionAddAverageSeries.setText("Add AverageSeries")
                    self.context_menu.addAction(self.context_menu.actionAddAverageSeries)
                    self.context_menu.actionAddAverageSeries.triggered.connect(self.add_averageseries)
                self.context_menu.addSeparator()
                self.context_menu.actionAddVariableAbove = QtWidgets.QAction(self)
                self.context_menu.actionAddVariableAbove.setText("New variable")
                self.context_menu.addAction(self.context_menu.actionAddVariableAbove)
                self.context_menu.actionAddVariableAbove.triggered.connect(self.add_variable_above)
                self.context_menu.actionRemoveVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveVariable)
                self.context_menu.actionRemoveVariable.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Plots":
                self.context_menu.actionDisablePlot = QtWidgets.QAction(self)
                self.context_menu.actionDisablePlot.setText("Disable plot")
                self.context_menu.addAction(self.context_menu.actionDisablePlot)
                self.context_menu.actionDisablePlot.triggered.connect(self.disable_plot)
                self.context_menu.actionEnablePlot = QtWidgets.QAction(self)
                self.context_menu.actionEnablePlot.setText("Enable plot")
                self.context_menu.addAction(self.context_menu.actionEnablePlot)
                self.context_menu.actionEnablePlot.triggered.connect(self.enable_plot)
                self.context_menu.actionRemovePlot = QtWidgets.QAction(self)
                self.context_menu.actionRemovePlot.setText("Remove plot")
                self.context_menu.addAction(self.context_menu.actionRemovePlot)
                self.context_menu.actionRemovePlot.triggered.connect(self.remove_item)
        elif level == 2:
            add_separator = False
            # we are in a subsection
            selected_item = idx.model().itemFromIndex(idx)
            # get the subsection
            subsection = selected_item.parent()
            # get the section
            section = subsection.parent()
            # check to see what the user whats us to do based on what was selected when the right click happened
            if str(idx.data()) in ["ExcludeDates"]:
                # we are adding a date range to an ExcludeDates QC check
                self.context_menu.actionPickDateRange = QtWidgets.QAction(self)
                self.context_menu.actionPickDateRange.setText("Pick date range")
                self.context_menu.addAction(self.context_menu.actionPickDateRange)
                self.context_menu.actionPickDateRange.triggered.connect(self.pick_excludedaterange)
                self.context_menu.actionAddExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeDateRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeDateRange)
                self.context_menu.actionAddExcludeDateRange.triggered.connect(self.add_excludedaterange)
                add_separator = True
            if str(idx.data()) in ["ExcludeHours"]:
                self.context_menu.actionAddExcludeHourRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeHourRange.setText("Add hour range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeHourRange)
                self.context_menu.actionAddExcludeHourRange.triggered.connect(self.add_excludehourrange)
                add_separator = True
            if str(idx.data()) in ["LowerCheck"]:
                self.context_menu.actionAddLowerCheckRange = QtWidgets.QAction(self)
                self.context_menu.actionAddLowerCheckRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddLowerCheckRange)
                self.context_menu.actionAddLowerCheckRange.triggered.connect(self.add_lowercheckrange)
                add_separator = True
            if str(idx.data()) in ["UpperCheck"]:
                self.context_menu.actionAddUpperCheckRange = QtWidgets.QAction(self)
                self.context_menu.actionAddUpperCheckRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddUpperCheckRange)
                self.context_menu.actionAddUpperCheckRange.triggered.connect(self.add_uppercheckrange)
                add_separator = True
            if str(idx.data()) in ["CorrectWindDirection"]:
                self.context_menu.actionAddWindDirectionCorrectionRange = QtWidgets.QAction(self)
                self.context_menu.actionAddWindDirectionCorrectionRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddWindDirectionCorrectionRange)
                self.context_menu.actionAddWindDirectionCorrectionRange.triggered.connect(self.add_winddirectioncorrectionrange)
                add_separator = True
            if str(idx.data()) in ["Linear"]:
                self.context_menu.actionAddLinearRange = QtWidgets.QAction(self)
                self.context_menu.actionAddLinearRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddLinearRange)
                self.context_menu.actionAddLinearRange.triggered.connect(self.add_linearrange)
                add_separator = True
            if (str(section.text()) == "Imports") and (selected_item.column() == 1):
                # we are browsing for a file name in an Imports section
                key = str(subsection.child(selected_item.row(),0).text())
                if key in ["file_name"]:
                    self.context_menu.actionBrowseAlternateFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseAlternateFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseAlternateFile)
                    self.context_menu.actionBrowseAlternateFile.triggered.connect(self.browse_alternate_file)
                    add_separator = True
            if add_separator:
                self.context_menu.addSeparator()
                add_separator = False
            if str(idx.data()) in ["RangeCheck", "DependencyCheck", "DiurnalCheck", "ExcludeDates",
                                   "MADCheck", "LowerCheck", "UpperCheck"]:
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
            if (str(idx.data()) in ["AverageSeries", "ApplyFco2Storage", "MergeSeries"]):
                self.context_menu.actionRemoveMergeSeriesItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveMergeSeriesItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveMergeSeriesItem)
                self.context_menu.actionRemoveMergeSeriesItem.triggered.connect(self.remove_item)
        elif level == 3:
            if (str(idx.parent().data()) in ["ExcludeDates", "ExcludeHours", "LowerCheck",
                                             "UpperCheck", "Linear"] and
                str(idx.data()) != "0"):
                self.context_menu.actionRemoveExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveExcludeDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveExcludeDateRange)
                self.context_menu.actionRemoveExcludeDateRange.triggered.connect(self.remove_daterange)
            if (str(idx.parent().data()) in ["AverageSeries", "MergeSeries"] and
                str(idx.data()) != "source"):
                self.context_menu.actionRemoveMergeSeriesItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveMergeSeriesItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveMergeSeriesItem)
                self.context_menu.actionRemoveMergeSeriesItem.triggered.connect(self.remove_item)

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_L3_gui(self):
        """ Edit L3 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        # create a new control file object
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        # set the control file level
        cfg["level"] = "L3"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Global", "Options", "Soil", "Massman"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Plots", "Imports"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
            elif key1 in ["Variables"]:
                # sections with 3 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        for l in range(subsubsection.rowCount()):
                            key4 = str(subsubsection.child(l, 0).text())
                            val4 = str(subsubsection.child(l, 1).text())
                            cfg[key1][key2][key3][key4] = val4
        return cfg

    def enable_plot(self):
        """ Enable a plot by removing '[disabled]' from the title."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        if "(disabled)" in selected_text:
            selected_text = selected_text.replace("(disabled)", "")
        selected_item.setText(selected_text)
        return

    def disable_plot(self):
        """ Disable a plot by adding '[disabled]' to the title."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        if "(disabled)" not in selected_text:
            selected_text = "(disabled)" + selected_text
        selected_item.setText(selected_text)
        return

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item in the model."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            idx = indexes[0]
            while idx.parent().isValid():
                idx = idx.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be some way to do this recursively
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Files", "Global", "Output", "Options", "Soil", "Massman"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    value = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(value)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Plots", "Imports"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    for key3 in self.cfg[key1][key2]:
                        value = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(value)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 3 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    parent2 = QtGui.QStandardItem(key2)
                    for key3 in sorted(list(self.cfg[key1][key2].keys())):
                        if key3 in ["RangeCheck", "DependencyCheck", "DiurnalCheck", "ExcludeDates",
                                    "LowerCheck", "UpperCheck", "MADCheck",
                                    "ApplyFco2Storage", "MergeSeries", "AverageSeries"]:
                            parent3 = QtGui.QStandardItem(key3)
                            parent3.setEditable(False)
                            for key4 in sorted(list(self.cfg[key1][key2][key3].keys())):
                                value = self.cfg[key1][key2][key3][key4]
                                child0 = QtGui.QStandardItem(key4)
                                child0.setEditable(False)
                                child1 = QtGui.QStandardItem(value)
                                parent3.appendRow([child0, child1])
                            parent2.appendRow(parent3)
                    if parent2.hasChildren():
                        self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Soil", "Massman", "Variables", "Plots"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def load_netcdf_async(self):
        # Create a thread and a worker
        self.thread = QtCore.QThread()
        self.worker = NetCDFReadWorker(self.cfg)
        # Move worker to the new thread
        self.worker.moveToThread(self.thread)
        # Connect signals and slots
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_load_success)
        self.worker.finished.connect(self.thread.quit) # Stop thread when done
        self.worker.error.connect(self.on_load_error)
        # Clean up memory when finished
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        # Start the thread
        self.thread.start()

    def on_load_success(self, ds):
        logger.info("  Successfully loaded data structure from netCDF")
        self.ds = ds

    def on_load_error(self, message):
        logger.error("  Failed to load data structure from netCDF {message}")

    def open_netcdf_file(self):
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        if len(selected_item.text()) == 0:
            return
        file_path = self.cfg["Files"]["file_path"]
        file_name = selected_item.text()
        file_uri = os.path.join(file_path, file_name)
        if not os.path.isfile(file_uri):
            return
        self.main_gui.file_open(file_uri=file_uri)
        return

    def pick_excludedaterange(self):
        """
        Function to display variable as a time series in a separate window and
        allow the user to select individual points or ranges of points
        to be removed by the ExcludeDates QC function.  Selected points or
        ranges are written back to the control file.
        """
        self.cfg = self.get_data_from_model()
        # get the selected variable
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        label =  parent.text()
        pfp_ts.CombineSeries(self.cfg, self.ds, label)
        pfp_ck.do_qcchecks_oneseries(self.cfg, self.ds, "Variables", label)
        self.var = pfp_utils.GetVariable(self.ds, label)
        self.qc_dialog =  pick_exclude_date_range(self.var, parent=self)
        if self.qc_dialog.exec_():
            #print(self.qc_dialog.deletion_log)
            delete_points = self.qc_dialog.deletion_log
            idx = self.view.selectedIndexes()[0]
            selected_item = idx.model().itemFromIndex(idx)
            for i in range(len(delete_points)):
                start = delete_points[i][0].strftime("%Y-%m-%d %H:%M")
                end = delete_points[i][1].strftime("%Y-%m-%d %H:%M")
                rowCount = selected_item.rowCount()
                child = selected_item.child(rowCount-1, 1)
                if child.text() == "YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM":
                    child.setText(start+","+end)
                else:
                    child0 = QtGui.QStandardItem(str(rowCount))
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(start+","+end)
                    selected_item.appendRow([child0, child1])
            self.update_tab_text()
        else:
            #print("QC cancelled by user")
            pass
        return

    def remove_daterange(self):
        """ Remove a date range from the ustar_threshold section."""
        # remove the date range
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def remove_section(self):
        """ Remove a section from the view."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the root
        root = self.model.invisibleRootItem()
        # remove the row
        root.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_climatology(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_climatology, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_climatology_gui()

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"name": "", "format": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                else:
                    pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_climatology_gui(self):
        """ Edit a climatology control file GUI."""
        # get a QTreeView
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "climatology"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name, leave editing enabled
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_concatenate(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_concatenate, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_concatenate_gui()

    def edit_concatenate_gui(self):
        """ Edit a concatenate control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in sorted(list(self.cfg[key1].keys())):
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(val))
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Files"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    if key2 in ["Out", "In"]:
                        parent2 = QtGui.QStandardItem(key2)
                        parent2.setEditable(False)
                        for val in self.cfg[key1][key2]:
                            value = self.cfg[key1][key2][val]
                            child0 = QtGui.QStandardItem(val)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(str(value))
                            parent2.appendRow([child0, child1])
                        self.sections[key1].appendRow(parent2)
                    else:
                        val = self.cfg[key1][key2]
                        child0 = QtGui.QStandardItem(key2)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(str(val))
                        self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "concatenate"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Files"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    if key2 in ["plot_path"]:
                        cfg[key1][key2] = section.child(j,1).text()
                    else:
                        cfg[key1][key2] = {}
                        for k in range(subsection.rowCount()):
                            key3 = str(subsection.child(k, 0).text())
                            val3 = str(subsection.child(k, 1).text())
                            cfg[key1][key2][key3] = val3
        return cfg

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def change_selected_text(self, new_text):
        """ Change the selected text."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_item.setText(new_text)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            # sections with only 1 level
            if selected_text == "Options":
                existing_entries = self.get_existing_entries()
                if "ApplyFco2Storage" not in existing_entries:
                    self.context_menu.actionAddApplyFco2Storage = QtWidgets.QAction(self)
                    self.context_menu.actionAddApplyFco2Storage.setText("ApplyFco2Storage")
                    self.context_menu.addAction(self.context_menu.actionAddApplyFco2Storage)
                    self.context_menu.actionAddApplyFco2Storage.triggered.connect(self.add_applyfco2storage)
                if "NumberOfDimensions" not in existing_entries:
                    self.context_menu.actionAddNumberOfDimensions = QtWidgets.QAction(self)
                    self.context_menu.actionAddNumberOfDimensions.setText("NumberOfDimensions")
                    self.context_menu.addAction(self.context_menu.actionAddNumberOfDimensions)
                    self.context_menu.actionAddNumberOfDimensions.triggered.connect(self.add_numberofdimensions)
                if "MaxGapInterpolate" not in existing_entries:
                    self.context_menu.actionAddMaxGapInterpolate = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxGapInterpolate.setText("MaxGapInterpolate")
                    self.context_menu.addAction(self.context_menu.actionAddMaxGapInterpolate)
                    self.context_menu.actionAddMaxGapInterpolate.triggered.connect(self.add_maxgapinterpolate)
                if "FixTimeStepMethod" not in existing_entries:
                    self.context_menu.actionAddFixTimeStepMethod = QtWidgets.QAction(self)
                    self.context_menu.actionAddFixTimeStepMethod.setText("FixTimeStepMethod")
                    self.context_menu.addAction(self.context_menu.actionAddFixTimeStepMethod)
                    self.context_menu.actionAddFixTimeStepMethod.triggered.connect(self.add_fixtimestepmethod)
                if "Truncate" not in existing_entries:
                    self.context_menu.actionAddTruncate = QtWidgets.QAction(self)
                    self.context_menu.actionAddTruncate.setText("Truncate")
                    self.context_menu.addAction(self.context_menu.actionAddTruncate)
                    self.context_menu.actionAddTruncate.triggered.connect(self.add_truncate)
                if "TruncateThreshold" not in existing_entries:
                    self.context_menu.actionAddTruncateThreshold = QtWidgets.QAction(self)
                    self.context_menu.actionAddTruncateThreshold.setText("TruncateThreshold")
                    self.context_menu.addAction(self.context_menu.actionAddTruncateThreshold)
                    self.context_menu.actionAddTruncateThreshold.triggered.connect(self.add_truncatethreshold)
                if "SeriesToCheck" not in existing_entries:
                    self.context_menu.actionAddSeriesToCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddSeriesToCheck.setText("SeriesToCheck")
                    self.context_menu.addAction(self.context_menu.actionAddSeriesToCheck)
                    self.context_menu.actionAddSeriesToCheck.triggered.connect(self.add_seriestocheck)
                if "SeriesToKeep" not in existing_entries:
                    self.context_menu.actionAddSeriesToKeep = QtWidgets.QAction(self)
                    self.context_menu.actionAddSeriesToKeep.setText("SeriesToKeep")
                    self.context_menu.addAction(self.context_menu.actionAddSeriesToKeep)
                    self.context_menu.actionAddSeriesToKeep.triggered.connect(self.add_seriestokeep)
                if "DoFingerprints" not in existing_entries:
                    self.context_menu.actionAddDoFingerprints = QtWidgets.QAction(self)
                    self.context_menu.actionAddDoFingerprints.setText("DoFingerprints")
                    self.context_menu.addAction(self.context_menu.actionAddDoFingerprints)
                    self.context_menu.actionAddDoFingerprints.triggered.connect(self.add_dofingerprints)
        elif level == 1:
            parent = selected_item.parent()
            key = str(parent.child(selected_item.row(),0).text())
            if (str(parent.text()) == "Options"):
                if (selected_item.column() == 0):
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                elif (selected_item.column() == 1) and (key in ["ApplyFco2Storage",
                                                                "DoFingerprints",
                                                                "Truncate"]):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("No"))
            elif str(parent.text()) == "Files":
                if ((selected_item.column() == 0) and (selected_text == "In")):
                    self.context_menu.actionAddInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionAddInputFile.setText("Add input file")
                    self.context_menu.addAction(self.context_menu.actionAddInputFile)
                    self.context_menu.actionAddInputFile.triggered.connect(self.add_inputfile)
                elif ((selected_item.column() == 1) and (key == "plot_path")):
                    self.context_menu.actionBrowsePlotPath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowsePlotPath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowsePlotPath)
                    self.context_menu.actionBrowsePlotPath.triggered.connect(self.browse_plot_path)
        elif level == 2:
            parent = selected_item.parent()
            section = selected_item.parent().parent()
            if ((str(section.text()) == "Files") and (str(parent.text()) == "In")):
                if (selected_item.column() == 0):
                    self.context_menu.actionAddInputFileAbove = QtWidgets.QAction(self)
                    self.context_menu.actionAddInputFileAbove.setText("Add file")
                    self.context_menu.addAction(self.context_menu.actionAddInputFileAbove)
                    self.context_menu.actionAddInputFileAbove.triggered.connect(self.add_input_file_above)
                    self.context_menu.actionRemoveInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveInputFile.setText("Remove file")
                    self.context_menu.addAction(self.context_menu.actionRemoveInputFile)
                    self.context_menu.actionRemoveInputFile.triggered.connect(self.remove_input_file)
                elif (selected_item.column() == 1):
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
            elif ((str(section.text()) == "Files") and (str(parent.text()) == "Out")):
                if str(parent.child(selected_item.row(), 0).text()) == "ncFileName":
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
        elif level == 3:
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def get_section(self, section_name):
        """ Gets a section from a model by matching the section name."""
        model = self.tree.model()
        for i in range(model.rowCount()):
            section = model.item(i)
            if str(section.text()) == str(section_name):
                break
        return section, i

    def get_subsection(self, section, idx):
        """ Gets a subsection from a model by matching the subsection name."""
        for i in range(section.rowCount()):
            # get the child subsection
            subsection = section.child(i)
            # check to see if we have the selected subsection
            if str(subsection.text()) == str(idx.data()):
                break
        return subsection, i

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_keyval_by_val_name(self, section, val):
        """ Get the value from a section based on the value name."""
        found = False
        key_child = ""
        val_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 1).text()) == str(val):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        level = 0
        idx = self.view.selectedIndexes()[0]
        while idx.parent().isValid():
            idx = idx.parent()
            level += 1
        return level

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

    def add_applyfco2storage(self):
        """ Add the ApplyFco2Storage option to the context menu."""
        dict_to_add = {"ApplyFco2Storage": "Yes"}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_dofingerprints(self):
        """ Add the DoFingerprints option to the context menu."""
        # add the option to the [Options] section
        dict_to_add = {"DoFingerprints": "No"}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_inputfile(self):
        """ Add an entry for a new input file."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        dict_to_add = {str(subsection.rowCount()): "Right click to browse"}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_input_file_above(self):
        """ Add an input file above the selected entry and renumber the section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        new_file_number = min([0, int(float(selected_item.text()))-1])
        # get the parent of the selected item
        parent = selected_item.parent()
        # insert the new file entry
        new_file_entry = [QtGui.QStandardItem(str(new_file_number)),
                          QtGui.QStandardItem("Right click to browse")]
        parent.insertRow(idx.row(), new_file_entry)
        # renumber the section
        self.renumber_subsection_keys(parent)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()
        return

    def add_numberofdimensions(self):
        """ Add the NumberOfDimensions option to the context menu."""
        dict_to_add = {"NumberOfDimensions": "3"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_maxgapinterpolate(self):
        """ Add the MaxGapInterpolate option to the context menu."""
        # add the option to the [Options] section
        dict_to_add = {"MaxGapInterpolate": "3"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_fixtimestepmethod(self):
        """ Add the FixTimeStepMethod option to the context menu."""
        # add the option to the [Options] section
        dict_to_add = {"FixTimeStepMethod": "round"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_subsection(self, dict_to_add):
        """ Add a subsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])
        self.update_tab_text()

    def add_seriestocheck(self):
        """ Add the SeriesToCheck option to the context menu."""
        # add the option to the [Options] section
        series = "all"
        dict_to_add = {"SeriesToCheck": series}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_seriestokeep(self):
        """ Add the SeriesToKeep option to the context menu."""
        # add the option to the [Options] section
        series = "AH,CO2,Fa,Fco2,Fe,Fg,Fh,Fld,Flu,Fm,Fn,Fsd,Fsu,H2O,Precip,RH,SH,Sws,Ta,Ts,VP,Wd,Ws,ps,ustar"
        dict_to_add = {"SeriesToKeep": series}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_truncate(self):
        """ Add the Truncate option to the context menu."""
        # add the option to the [Options] section
        dict_to_add = {"Truncate": "Yes"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)
        # automatically add the threshold and series to check
        self.add_truncatethreshold()
        self.add_seriestocheck()

    def add_truncatethreshold(self):
        """ Add the TruncateThreshold option to the context menu."""
        # add the option to the [Options] section
        dict_to_add = {"TruncateThreshold": "50"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_path = QtCore.QDir.toNativeSeparators(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_path)

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_path = QtCore.QDir.toNativeSeparators(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_path)

    def browse_plot_path(self):
        """ Browse for the plot path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder ...",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def remove_option(self):
        """ Remove an option."""
        # loop over selected items in the tree
        for idx in self.tree.selectedIndexes():
            # get the "Options" section
            section, i = self.get_section("Options")
            # loop over all children in the "Options" section
            subsection, i = self.get_subsection(section, idx)
            # remove the option
            section.removeRow(i)
            self.update_tab_text()

    def remove_input_file(self):
        """ Remove an input file."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
            self.renumber_subsection_keys(parent)
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def renumber_subsection_keys(self, subsection):
        """ Renumber the subsection keys when an item is removed."""
        for i in range(subsection.rowCount()):
            child = subsection.child(i)
            child.setText(str(i))
        return

class edit_cfg_cpd_barr(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_cpd_barr, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_cpd_barr_gui()

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"name": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            # populate the output file name with a default based on the input file name
            for n in range(parent.rowCount()):
                if parent.child(n, 0).text() == "out_filename":
                    xls_filename = new_file_parts[1].replace(".nc", "_CPD_Barr.xlsx")
                    parent.child(n, 1).setText(xls_filename)
        return

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.xlsx")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["Options"]:
                pass
            else:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_output_file)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_cpd_barr_gui(self):
        """ Edit a CPD (Barr) control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "cpd_barr"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Options", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_cpd_mchugh(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_cpd_mchugh, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_cpd_mchugh_gui()

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"name": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            # populate the output file name with a default based on the input file name
            for n in range(parent.rowCount()):
                if parent.child(n, 0).text() == "out_filename":
                    xls_filename = new_file_parts[1].replace(".nc", "_CPD_McHugh.xlsx")
                    parent.child(n, 1).setText(xls_filename)
        return

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.xls")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["Options"]:
                pass
            else:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_output_file)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_cpd_mchugh_gui(self):
        """ Edit a CPD (McHugh) control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "cpd_mchugh"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Options", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_cpd_mcnew(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_cpd_mcnew, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_cpd_mcnew_gui()

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"name": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            # populate the output file name with a default based on the input file name
            for n in range(parent.rowCount()):
                if parent.child(n, 0).text() == "out_filename":
                    xls_filename = new_file_parts[1].replace(".nc", "_CPD_McNew.xlsx")
                    parent.child(n, 1).setText(xls_filename)
        return

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.xlsx")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["Options"]:
                pass
            else:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_output_file)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_cpd_mcnew_gui(self):
        """ Edit a CPD (McNew) control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "cpd_mcnew"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Options", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_mpt(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_mpt, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_mpt_gui()

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"name": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            # populate the output file name with a default based on the input file name
            for n in range(parent.rowCount()):
                if parent.child(n, 0).text() == "out_filename":
                    xls_filename = new_file_parts[1].replace(".nc", "_MPT.xlsx")
                    parent.child(n, 1).setText(xls_filename)
        return

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.xls")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["Options"]:
                pass
            else:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_output_file)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_mpt_gui(self):
        """ Edit an MPT control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "mpt"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Options", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L4(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L4, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_l4_gui()

    def add_alternate(self):
        """ Add GapFillFromAlternate to a variable."""
        dict_to_add = {"GapFillFromAlternate":{"<var_alt>": {"source": "<alt>"}}}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsubsection(dict_to_add)

    def add_alternate_fit(self):
        """ Add fit to alternate variable."""
        dict_to_add = {"fit":"ols"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_alternate_lag(self):
        """ Add lag to alternate variable."""
        dict_to_add = {"lag":"yes"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_climatology(self):
        """ Add GapFillFromClimatology to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.data()) + "_cli"
        dict_to_add = {"GapFillFromClimatology": {var_name: {"method":"interpolated daily"}}}
        # add the subsubsection (GapFillFromClimatology)
        self.add_subsubsubsection(dict_to_add)

    def add_dependencycheck(self):
        """ Add a dependency check to a variable."""
        dict_to_add = {"DependencyCheck":{"source":""}}
        # add the subsubsection (DependencyCheck)
        self.add_subsubsection(dict_to_add)

    def add_diurnalcheck(self):
        """ Add a diurnal check to a variable."""
        dict_to_add = {"DiurnalCheck":{"numsd":"5"}}
        # add the subsubsection (DiurnalCheck)
        self.add_subsubsection(dict_to_add)

    def add_excludedates(self):
        """ Add an exclude dates check to a variable."""
        dict_to_add = {"ExcludeDates":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM"}}
        # add the subsubsection (ExcludeDates)
        self.add_subsubsection(dict_to_add)

    def add_excludedaterange(self):
        """ Add another date range to the ExcludeDates QC check."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_fileentry(self):
        """ Add a new entry to the [Files] section."""
        sender = str(self.context_menu.sender().text())
        item =  sender.split(" ")[1]
        dict_to_add = {item: "Right click to browse"}
        # add the subsection
        editable = True
        if item in ["access", "aws", "climatology", "era5"]:
            editable = False
        self.add_subsection(dict_to_add, editable=editable)

    def add_gui_section(self):
        """ Add a GUI section."""
        self.sections["GUI"] = QtGui.QStandardItem("GUI")
        self.sections["GUI"].setEditable(False)
        gui_section = {"GapFillFromAlternate": {"period_option": "days",
                                               "start_date": "", "end_date": "",
                                               "number_days": "90", "number_months": "3",
                                               "auto_complete": "yes", "min_percent": "30",
                                               "overwrite": "no", "show_plots": "no",
                                               "show_all": "no"}}
        for key1 in sorted(list(gui_section.keys())):
            gui_method = QtGui.QStandardItem(key1)
            gui_method.setEditable(False)
            for key2 in sorted(list(gui_section[key1].keys())):
                val = gui_section[key1][key2]
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                gui_method.appendRow([child0, child1])
            self.sections["GUI"].appendRow(gui_method)
        idx = self.section_headings.index("Drivers")
        self.model.insertRow(idx, self.sections["GUI"])
        self.section_headings.insert(idx, "GUI")
        self.update_tab_text()

    def add_imports_section(self):
        """ Add an Imports section."""
        self.sections["Imports"] = QtGui.QStandardItem("Imports")
        self.add_imports_variable()
        idx = self.section_headings.index("Files")+1
        self.model.insertRow(idx, self.sections["Imports"])
        self.section_headings.insert(idx, "Imports")
        self.update_tab_text()

    def add_imports_variable(self):
        """ Add a variable to the Imports section."""
        new_import = {"file_name": "Right click to browse", "var_name": "<variable_name>"}
        new_variable = QtGui.QStandardItem("New variable")
        for key in new_import:
            val = new_import[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            new_variable.appendRow([child0, child1])
        self.sections["Imports"].appendRow(new_variable)
        self.update_tab_text()

    def add_interpolatetype(self):
        """ Add InterpolateType to the [Options] section."""
        dict_to_add = {"InterpolateType": "Akima"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_keepintermediateseries(self):
        """ Add KeepIntermediateSeries to the [Options] section."""
        dict_to_add = {"KeepIntermediateSeries": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_maxgapinterpolate(self):
        """ Add MaxGapInterpolate to the [Options] section."""
        dict_to_add = {"MaxGapInterpolate": "3"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_MDS(self):
        """ Add GapFillUsingMDS to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.data()) + "_MDS"
        dict_to_add = {"GapFillUsingMDS":{var_name: {"drivers": "['Fsd','Ta','VPD']",
                                                     "tolerances":"[(20, 50), 2.5, 0.5]"}}}
        # add the subsubsection (GapFillUsingMDS)
        self.add_subsubsubsection(dict_to_add)

    def add_more_alternate(self):
        """ Add another alternate source to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.parent().data()) + "_<alt>"
        dict_to_add = {var_name: {"source": "<alt>"}}
        # add the subsubsection (RangeCheck)
        self.add_subsubsection(dict_to_add, editable=True)

    def add_new_variable(self):
        """ Add a new variable."""
        gfALT = {"<var>_<alt>": {"source": "<alt>"}}
        gfCLIM = {"<var>_cli": {"method": "interpolated daily"}}
        gfMS = {"source": "<var>,<var>_<alt>,<var>_cli"}
        d2a = {"New variable": {"GapFillFromAlternate": gfALT,
                                "GapFillFromClimatology": gfCLIM,
                                "MergeSeries": gfMS}}
        self.add_variable(d2a)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_rangecheck(self):
        """ Add a range check to a variable."""
        dict_to_add = {"RangeCheck":{"lower":0, "upper": 1}}
        # add the subsubsection (RangeCheck)
        self.add_subsubsection(dict_to_add)

    def add_subsection(self, dict_to_add, editable=False):
        """ Add a subsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            if not editable:
                child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])
        self.update_tab_text()

    def add_subsubsection(self, dict_to_add, editable=False):
        """ Add a subsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key1 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key1)
            if not editable:
                subsubsection.setEditable(False)
            for key2 in dict_to_add[key1]:
                val = str(dict_to_add[key1][key2])
                child0 = QtGui.QStandardItem(key2)
                if not editable:
                    child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                subsubsection.appendRow([child0, child1])
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_subsubsubsection(self, dict_to_add):
        """ Add a subsubsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key3 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key3)
            subsubsection.setEditable(False)
            for key4 in dict_to_add[key3]:
                subsubsubsection = QtGui.QStandardItem(key4)
                subsubsubsection.setEditable(False)
                for val in dict_to_add[key3][key4]:
                    value = dict_to_add[key3][key4][val]
                    child0 = QtGui.QStandardItem(val)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(value))
                    subsubsubsection.appendRow([child0, child1])
                subsubsection.appendRow(subsubsubsection)
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_truncate(self):
        """ Add Truncate to the [Options] section."""
        dict_to_add = {"Truncate": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_variable(self, d2a):
        """ Add a variable."""
        for key2 in d2a:
            parent2 = QtGui.QStandardItem(key2)
            # key3 is the gap filling method
            for key3 in d2a[key2]:
                parent3 = QtGui.QStandardItem(key3)
                parent3.setEditable(False)
                if key3 in ["GapFillFromAlternate", "GapFillFromClimatology"]:
                    # key4 is the gap fill variable name
                    for key4 in d2a[key2][key3]:
                        parent4 = QtGui.QStandardItem(key4)
                        # key5 is the source of the alternate data
                        for key5 in d2a[key2][key3][key4]:
                            val = d2a[key2][key3][key4][key5]
                            child0 = QtGui.QStandardItem(key5)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(val)
                            parent4.appendRow([child0, child1])
                        parent3.appendRow(parent4)
                elif key3 in ["MergeSeries", "RangeCheck", "ExcludeDates"]:
                    for key4 in d2a[key2][key3]:
                        val = d2a[key2][key3][key4]
                        child0 = QtGui.QStandardItem(key4)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent3.appendRow([child0, child1])
                parent2.appendRow(parent3)
            self.sections["Drivers"].appendRow(parent2)

    #def add_variable_above(self):
        #""" Add a new variable above the selected variable."""
        ## get the index of the selected item
        #idx = self.view.selectedIndexes()[0]
        ## get the selected item from the index
        #selected_item = idx.model().itemFromIndex(idx)
        ## get the parent of the selected item
        #parent = selected_item.parent()
        ## construct the new variable dictionary
        #new_var = {"RangeCheck":{"lower":0, "upper": 1}}
        #subsection = QtGui.QStandardItem("New variable")
        #self.add_subsubsection(subsection, new_var)
        #parent.insertRow(idx.row(), subsection)
        ## add an asterisk to the tab text to indicate the tab contents have changed
        #self.update_tab_text()

    def browse_alternate_file(self):
        """ Browse for the alternate data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "*.nc"
        if str(parent.child(selected_item.row(), 0).text()) in ["climatology"]:
            file_filter = "*.xls"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path, "")
        # dialog for open file
        new_file = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an alternate data file ...",
                                                     directory=file_path, filter=file_filter)[0]
        # quit if cancel button pressed
        if len(str(new_file)) > 0:
            # update the model
            new_file = QtCore.QDir.toNativeSeparators(str(new_file))
            parent.child(selected_item.row(), 1).setText(new_file)

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                         file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_imports_file(self):
        """ Browse for the imports file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "*.nc"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path,"")
        # dialog for open file
        new_file = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an Imports file ...",
                                                     directory=file_path, filter=file_filter)[0]
        # update the model
        if len(str(new_file)) > 0:
            new_file = QtCore.QDir.toNativeSeparators(str(new_file))
            parent.child(selected_item.row(), 1).setText(new_file)

    def browse_input_file(self, type_filter):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                          directory=file_path, filter=type_filter)[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                          directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def change_selected_text(self, new_text):
        """ Change the selected text."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_item.setText(new_text)

    def context_menu(self, position):
        """ Right click context menu."""
        self.view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectItems)
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        add_separator = False
        # get a list of the section headings at the root level
        self.section_headings = []
        root = self.model.invisibleRootItem()
        for i in range(root.rowCount()):
            self.section_headings.append(str(root.child(i).text()))
        if level == 0:
            if "Imports" not in self.section_headings and selected_text == "Files":
                self.context_menu.actionAddImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsSection.setText("Add Imports section")
                self.context_menu.addAction(self.context_menu.actionAddImportsSection)
                self.context_menu.actionAddImportsSection.triggered.connect(self.add_imports_section)
                add_separator = True
            if "GUI" not in self.section_headings and selected_text == "Files":
                self.context_menu.actionAddGUISection = QtWidgets.QAction(self)
                self.context_menu.actionAddGUISection.setText("Add GUI section")
                self.context_menu.addAction(self.context_menu.actionAddGUISection)
                self.context_menu.actionAddGUISection.triggered.connect(self.add_gui_section)
                add_separator = True
            # sections with only 1 level
            if selected_text == "Files":
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                for item in ["plot_path", "file_path", "in_filename", "out_filename",
                             "aws", "access", "era5", "climatology", "other"]:
                    if item not in existing_entries:
                        self.context_menu.actionAddFileEntry = QtWidgets.QAction(self)
                        self.context_menu.actionAddFileEntry.setText("Add " + item)
                        self.context_menu.addAction(self.context_menu.actionAddFileEntry)
                        #self.context_menu.actionAddFileEntry.triggered.connect(lambda:self.add_fileentry(item))
                        self.context_menu.actionAddFileEntry.triggered.connect(self.add_fileentry)
                        add_separator = True
            elif selected_text == "Imports":
                self.context_menu.actionAddImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddImportsVariable)
                self.context_menu.actionAddImportsVariable.triggered.connect(self.add_imports_variable)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsSection)
                self.context_menu.actionRemoveImportsSection.triggered.connect(self.remove_section)
            elif selected_text == "Options":
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                # only put an option in the context menu if it is not already present
                if "InterpolateType" not in existing_entries:
                    self.context_menu.actionAddInterpolateType = QtWidgets.QAction(self)
                    self.context_menu.actionAddInterpolateType.setText("InterpolateType")
                    self.context_menu.addAction(self.context_menu.actionAddInterpolateType)
                    self.context_menu.actionAddInterpolateType.triggered.connect(self.add_interpolatetype)
                if "KeepIntermediateSeries" not in existing_entries:
                    self.context_menu.actionKeepIntermediateSeries = QtWidgets.QAction(self)
                    self.context_menu.actionKeepIntermediateSeries.setText("KeepIntermediateSeries")
                    self.context_menu.addAction(self.context_menu.actionKeepIntermediateSeries)
                    self.context_menu.actionKeepIntermediateSeries.triggered.connect(self.add_keepintermediateseries)
                if "MaxGapInterpolate" not in existing_entries:
                    self.context_menu.actionAddMaxGapInterpolate = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxGapInterpolate.setText("MaxGapInterpolate")
                    self.context_menu.addAction(self.context_menu.actionAddMaxGapInterpolate)
                    self.context_menu.actionAddMaxGapInterpolate.triggered.connect(self.add_maxgapinterpolate)
                if "Truncate" not in existing_entries:
                    self.context_menu.actionAddTruncate = QtWidgets.QAction(self)
                    self.context_menu.actionAddTruncate.setText("Truncate")
                    self.context_menu.addAction(self.context_menu.actionAddTruncate)
                    self.context_menu.actionAddTruncate.triggered.connect(self.add_truncate)
            elif selected_text == "GUI":
                self.context_menu.actionRemoveGUISection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGUISection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveGUISection)
                self.context_menu.actionRemoveGUISection.triggered.connect(self.remove_section)
            elif selected_text in ["Drivers"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
        elif level == 1:
            # sections with 2 levels
            # get the selected item
            selected_item = idx.model().itemFromIndex(idx)
            # get the selected item text
            selected_text = str(idx.data())
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    arg = lambda: self.browse_input_file(type_filter="*.nc")
                    self.context_menu.actionBrowseInputFile.triggered.connect(arg)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
                else:
                    self.context_menu.actionBrowseAlternateFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseAlternateFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseAlternateFile)
                    self.context_menu.actionBrowseAlternateFile.triggered.connect(self.browse_alternate_file)
            elif (str(parent.text()) == "Files") and (selected_item.column() == 0):
                key = str(parent.child(selected_item.row(),0).text())
                if key not in ["file_path", "plot_path", "in_filename", "out_filename"]:
                    self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveItem.setText("Remove item")
                    self.context_menu.addAction(self.context_menu.actionRemoveItem)
                    self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
                else:
                    pass
            elif (str(parent.text()) == "Imports"):
                self.context_menu.actionRemoveImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsVariable)
                self.context_menu.actionRemoveImportsVariable.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "Options"):
                key = str(parent.child(selected_item.row(),0).text())
                if (selected_item.column() == 0):
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                elif (selected_item.column() == 1) and (key == "InterpolateType"):
                    if selected_text != "linear":
                        self.context_menu.actionChangeInterpolateType = QtWidgets.QAction(self)
                        self.context_menu.actionChangeInterpolateType.setText("linear")
                        self.context_menu.addAction(self.context_menu.actionChangeInterpolateType)
                        self.context_menu.actionChangeInterpolateType.triggered.connect(lambda:self.change_selected_text("linear"))
                    if selected_text != "Akima":
                        self.context_menu.actionChangeInterpolateType = QtWidgets.QAction(self)
                        self.context_menu.actionChangeInterpolateType.setText("Akima")
                        self.context_menu.addAction(self.context_menu.actionChangeInterpolateType)
                        self.context_menu.actionChangeInterpolateType.triggered.connect(lambda:self.change_selected_text("Akima"))
                elif (selected_item.column() == 1) and (key in ["KeepIntermediateSeries"]):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeKeepIntermediateSeries = QtWidgets.QAction(self)
                        self.context_menu.actionChangeKeepIntermediateSeries.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeKeepIntermediateSeries)
                        self.context_menu.actionChangeKeepIntermediateSeries.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeKeepIntermediateSeries = QtWidgets.QAction(self)
                        self.context_menu.actionChangeKeepIntermediateSeries.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeKeepIntermediateSeries)
                        self.context_menu.actionChangeKeepIntermediateSeries.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key in ["Truncate"]):
                    if selected_text != "First missing":
                        self.context_menu.actionChangeTruncate0 = QtWidgets.QAction(self)
                        self.context_menu.actionChangeTruncate0.setText("First missing")
                        self.context_menu.addAction(self.context_menu.actionChangeTruncate0)
                        self.context_menu.actionChangeTruncate0.triggered.connect(lambda:self.change_selected_text("First missing"))
                    if selected_text != "To imports":
                        if "Imports" in self.section_headings:
                            self.context_menu.actionChangeTruncate1 = QtWidgets.QAction(self)
                            self.context_menu.actionChangeTruncate1.setText("To imports")
                            self.context_menu.addAction(self.context_menu.actionChangeTruncate1)
                            self.context_menu.actionChangeTruncate1.triggered.connect(lambda:self.change_selected_text("To imports"))
                    if selected_text != "No":
                        self.context_menu.actionChangeTruncate2 = QtWidgets.QAction(self)
                        self.context_menu.actionChangeTruncate2.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeTruncate2)
                        self.context_menu.actionChangeTruncate2.triggered.connect(lambda:self.change_selected_text("No"))
            elif (str(parent.text()) in ["Drivers"]):
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                # only put a QC check in the context menu if it is not already present
                if "GapFillFromAlternate" not in existing_entries:
                    self.context_menu.actionAddAlternate = QtWidgets.QAction(self)
                    self.context_menu.actionAddAlternate.setText("Add Alternate")
                    self.context_menu.addAction(self.context_menu.actionAddAlternate)
                    self.context_menu.actionAddAlternate.triggered.connect(self.add_alternate)
                    add_separator = True
                if "GapFillUsingMDS" not in existing_entries:
                    self.context_menu.actionAddMDS = QtWidgets.QAction(self)
                    self.context_menu.actionAddMDS.setText("Add MDS")
                    self.context_menu.addAction(self.context_menu.actionAddMDS)
                    self.context_menu.actionAddMDS.triggered.connect(self.add_MDS)
                    add_separator = True
                if "GapFillFromClimatology" not in existing_entries:
                    self.context_menu.actionAddClimatology = QtWidgets.QAction(self)
                    self.context_menu.actionAddClimatology.setText("Add Climatology")
                    self.context_menu.addAction(self.context_menu.actionAddClimatology)
                    self.context_menu.actionAddClimatology.triggered.connect(self.add_climatology)
                    add_separator = True
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                if "RangeCheck" not in existing_entries:
                    self.context_menu.actionAddRangeCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddRangeCheck.setText("Add RangeCheck")
                    self.context_menu.addAction(self.context_menu.actionAddRangeCheck)
                    self.context_menu.actionAddRangeCheck.triggered.connect(self.add_rangecheck)
                    add_separator = True
                if "DependencyCheck" not in existing_entries:
                    self.context_menu.actionAddDependencyCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDependencyCheck.setText("Add DependencyCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDependencyCheck)
                    self.context_menu.actionAddDependencyCheck.triggered.connect(self.add_dependencycheck)
                    add_separator = True
                if "DiurnalCheck" not in existing_entries:
                    self.context_menu.actionAddDiurnalCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDiurnalCheck.setText("Add DiurnalCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDiurnalCheck)
                    self.context_menu.actionAddDiurnalCheck.triggered.connect(self.add_diurnalcheck)
                    add_separator = True
                if "ExcludeDates" not in existing_entries:
                    self.context_menu.actionAddExcludeDates = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeDates.setText("Add ExcludeDates")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeDates)
                    self.context_menu.actionAddExcludeDates.triggered.connect(self.add_excludedates)
                    add_separator = True
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                #self.context_menu.actionAddVariableAbove = QtWidgets.QAction(self)
                #self.context_menu.actionAddVariableAbove.setText("New variable")
                #self.context_menu.addAction(self.context_menu.actionAddVariableAbove)
                #self.context_menu.actionAddVariableAbove.triggered.connect(self.add_variable_above)
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "Imports"):
                self.context_menu.actionRemoveImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsVariable)
                self.context_menu.actionRemoveImportsVariable.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            parent = selected_item.parent()
            grand_parent = selected_item.parent().parent()
            subsubsection_name = str(idx.data())
            if subsubsection_name in ["RangeCheck", "DependencyCheck", "DiurnalCheck"]:
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
            elif subsubsection_name in ["ExcludeDates"]:
                self.context_menu.actionAddExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeDateRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeDateRange)
                self.context_menu.actionAddExcludeDateRange.triggered.connect(self.add_excludedaterange)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
            elif subsubsection_name in ["GapFillFromAlternate", "GapFillUsingMDS", "GapFillFromClimatology"]:
                if subsubsection_name == "GapFillFromAlternate":
                    self.context_menu.actionAddMoreAlternate = QtWidgets.QAction(self)
                    self.context_menu.actionAddMoreAlternate.setText("Add Alternate")
                    self.context_menu.addAction(self.context_menu.actionAddMoreAlternate)
                    self.context_menu.actionAddMoreAlternate.triggered.connect(self.add_more_alternate)
                self.context_menu.actionRemoveGFMethod = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGFMethod.setText("Remove method")
                self.context_menu.addAction(self.context_menu.actionRemoveGFMethod)
                self.context_menu.actionRemoveGFMethod.triggered.connect(self.remove_item)
            if str(grand_parent.text() == "Imports"):
                key = str(parent.child(selected_item.row(),0).text())
                if (key == "file_name") and (selected_item.column() == 1):
                    self.context_menu.actionBrowseImportsFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseImportsFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseImportsFile)
                    self.context_menu.actionBrowseImportsFile.triggered.connect(self.browse_imports_file)
        elif level == 3:
            # sections with 4 levels
            # get the parent text
            parent_text = str(idx.parent().data())
            if parent_text == "ExcludeDates":
                self.context_menu.actionRemoveExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveExcludeDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveExcludeDateRange)
                self.context_menu.actionRemoveExcludeDateRange.triggered.connect(self.remove_daterange)
            elif parent_text == "GapFillFromAlternate":
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                if "fit" not in existing_entries:
                    self.context_menu.actionAddAltFit = QtWidgets.QAction(self)
                    self.context_menu.actionAddAltFit.setText("Add fit")
                    self.context_menu.addAction(self.context_menu.actionAddAltFit)
                    self.context_menu.actionAddAltFit.triggered.connect(self.add_alternate_fit)
                    add_separator = True
                if "lag" not in existing_entries:
                    self.context_menu.actionAddAltLag = QtWidgets.QAction(self)
                    self.context_menu.actionAddAltLag.setText("Add lag")
                    self.context_menu.addAction(self.context_menu.actionAddAltLag)
                    self.context_menu.actionAddAltLag.triggered.connect(self.add_alternate_lag)
                    add_separator = True
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                self.context_menu.actionRemoveGFMethodVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGFMethodVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveGFMethodVariable)
                self.context_menu.actionRemoveGFMethodVariable.triggered.connect(self.remove_item)
        elif level == 4:
            selected_item = idx.model().itemFromIndex(idx)
            selected_text = str(idx.data())
            parent = idx.parent()
            key = parent.child(selected_item.row(), 0)
            key_text = str(key.data())
            if selected_text in ["fit", "lag"]:
                self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveItem)
                self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
            elif key_text == "fit":
                if selected_text != "ols":
                    self.context_menu.actionOLS = QtWidgets.QAction(self)
                    self.context_menu.actionOLS.setText("OLS")
                    self.context_menu.addAction(self.context_menu.actionOLS)
                    self.context_menu.actionOLS.triggered.connect(lambda:self.change_selected_text("ols"))
                if selected_text != "ols_thru0":
                    self.context_menu.actionOLSThroughOrigin = QtWidgets.QAction(self)
                    self.context_menu.actionOLSThroughOrigin.setText("OLS through origin")
                    self.context_menu.addAction(self.context_menu.actionOLSThroughOrigin)
                    self.context_menu.actionOLSThroughOrigin.triggered.connect(lambda:self.change_selected_text("ols_thru0"))
                if selected_text != "replace":
                    self.context_menu.actionReplace = QtWidgets.QAction(self)
                    self.context_menu.actionReplace.setText("replace")
                    self.context_menu.addAction(self.context_menu.actionReplace)
                    self.context_menu.actionReplace.triggered.connect(lambda:self.change_selected_text("replace"))
                if selected_text != "mrev":
                    self.context_menu.actionMREV = QtWidgets.QAction(self)
                    self.context_menu.actionMREV.setText("mrev")
                    self.context_menu.addAction(self.context_menu.actionMREV)
                    self.context_menu.actionMREV.triggered.connect(lambda:self.change_selected_text("mrev"))
                if selected_text != "rma":
                    self.context_menu.actionRMA = QtWidgets.QAction(self)
                    self.context_menu.actionRMA.setText("rma")
                    self.context_menu.addAction(self.context_menu.actionRMA)
                    self.context_menu.actionRMA.triggered.connect(lambda:self.change_selected_text("rma"))
                if selected_text != "odr":
                    self.context_menu.actionODR = QtWidgets.QAction(self)
                    self.context_menu.actionODR.setText("odr")
                    self.context_menu.addAction(self.context_menu.actionODR)
                    self.context_menu.actionODR.triggered.connect(lambda:self.change_selected_text("odr"))
            elif key_text == "lag":
                if selected_text != "yes":
                    self.context_menu.actionYes = QtWidgets.QAction(self)
                    self.context_menu.actionYes.setText("Yes")
                    self.context_menu.addAction(self.context_menu.actionYes)
                    self.context_menu.actionYes.triggered.connect(lambda:self.change_selected_text("yes"))
                if selected_text != "no":
                    self.context_menu.actionNo = QtWidgets.QAction(self)
                    self.context_menu.actionNo.setText("No")
                    self.context_menu.addAction(self.context_menu.actionNo)
                    self.context_menu.actionNo.triggered.connect(lambda:self.change_selected_text("no"))

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_l4_gui(self):
        """ Edit an L4 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "L4"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Global", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["GUI", "Imports"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
            elif key1 in []:
                # sections with 3 levels
                pass
            elif key1 in ["Drivers"]:
                # sections with 4 levels
                for j in range(section.rowCount()):
                    # subsections are variables
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        # subsubsections are GapFillFromAlternate, GapFillFromClimatology and MergeSeries
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        if key3 in ["GapFillFromAlternate", "GapFillFromClimatology", "GapFillUsingMDS"]:
                            for l in range(subsubsection.rowCount()):
                                subsubsubsection = subsubsection.child(l)
                                key4 = str(subsubsubsection.text())
                                cfg[key1][key2][key3][key4] = {}
                                for m in range(subsubsubsection.rowCount()):
                                    key5 = str(subsubsubsection.child(m, 0).text())
                                    val5 = str(subsubsubsection.child(m, 1).text())
                                    cfg[key1][key2][key3][key4][key5] = val5
                        elif key3 in ["MergeSeries", "RangeCheck", "DiurnalCheck", "DependencyCheck", "ExcludeDates"]:
                            for l in range(subsubsection.rowCount()):
                                key4 = str(subsubsection.child(l, 0).text())
                                val4 = str(subsubsection.child(l, 1).text())
                                cfg[key1][key2][key3][key4] = val4

        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_keyval_by_val_name(self, section, val):
        """ Get the value from a section based on the value name."""
        found = False
        key_child = ""
        val_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 1).text()) == str(val):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        level = 0
        idx = self.view.selectedIndexes()[0]
        while idx.parent().isValid():
            idx = idx.parent()
            level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Files", "Global", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["GUI", "Imports"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the gap filling method
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    # key3 is the gap filling method options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Drivers"]:
                # sections with 4 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the gap filling method
                    for key3 in self.cfg[key1][key2]:
                        parent3 = QtGui.QStandardItem(key3)
                        parent3.setEditable(False)
                        if key3 in ["GapFillFromAlternate", "GapFillFromClimatology"]:
                            # key4 is the alternate variable name
                            for key4 in self.cfg[key1][key2][key3]:
                                parent4 = QtGui.QStandardItem(key4)
                                # key5 is the source of the alternate data
                                for key5 in self.cfg[key1][key2][key3][key4]:
                                    val = self.cfg[key1][key2][key3][key4][key5]
                                    child0 = QtGui.QStandardItem(key5)
                                    child0.setEditable(False)
                                    child1 = QtGui.QStandardItem(val)
                                    parent4.appendRow([child0, child1])
                                parent3.appendRow(parent4)
                        elif key3 in ["MergeSeries", "RangeCheck", "ExcludeDates"]:
                            for key4 in self.cfg[key1][key2][key3]:
                                val = self.cfg[key1][key2][key3][key4]
                                child0 = QtGui.QStandardItem(key4)
                                child0.setEditable(False)
                                child1 = QtGui.QStandardItem(val)
                                parent3.appendRow([child0, child1])
                        parent2.appendRow(parent3)
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def get_subsection_from_index(self, section, idx):
        """ Gets a subsection from a model by matching the subsection name."""
        for i in range(section.rowCount()):
            # get the child subsection
            subsection = section.child(i)
            # check to see if we have the selected subsection
            if str(subsection.text()) == str(idx.data()):
                break
        return subsection, i

    def get_subsection_from_text(self, section, text):
        """ Gets a subsection from a model by matching the subsection name"""
        for i in range(section.rowCount()):
            subsection = section.child(i)
            if str(subsection.text()) == text:
                break
        return subsection, i

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Drivers"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_daterange(self):
        """ Remove a date range from the ustar_threshold section."""
        # remove the date range
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def remove_section(self):
        """ Remove a section from the view."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        # get the root
        root = self.model.invisibleRootItem()
        # remove the row
        root.removeRow(selected_item.row())
        self.section_headings.remove(selected_text)
        # if we are removing the Imports section, we may have to update the
        # Options/Truncate entry
        if selected_text == "Imports":
            # get the top level parent
            parent = self.model.invisibleRootItem()
            # loop over the sections in the top level parent
            for i in range(parent.rowCount()):
                item = parent.child(i)
                # and find the Options section
                if item.text() == "Options":
                    # then loop over the entries in the Options section
                    for j in range(item.rowCount()):
                        # and find the Truncate entry
                        if item.child(j, 0).text() == "Truncate":
                            # and if this is set to 'To Imports'
                            if item.child(j, 1).text() == "To imports":
                                # set it to 'No'
                                item.child(j, 1).setText("No")
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L5(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L5, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_l5_gui()

    def add_acceptdaytimes(self):
        """ Add AcceptDayTimes to the [Options] section."""
        dict_to_add = {"AcceptDayTimes": "Yes"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_daynightfilter(self):
        """ Add DayNightFilter to the [Options] section."""
        dict_to_add = {"DayNightFilter": "Fsd"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_dependencycheck(self):
        """ Add a dependency check to a variable."""
        dict_to_add = {"DependencyCheck":{"source":""}}
        # add the subsubsection (DependencyCheck)
        self.add_subsubsection(dict_to_add)

    def add_diurnalcheck(self):
        """ Add a diurnal check to a variable."""
        dict_to_add = {"DiurnalCheck":{"numsd":"5"}}
        # add the subsubsection (DiurnalCheck)
        self.add_subsubsection(dict_to_add)

    def add_eveningfilterlength(self):
        """ Add EveningFilterLength to the [Options] section."""
        dict_to_add = {"EveningFilterLength": "0"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_excludedaterange(self):
        """ Add another date range to the ExcludeDates QC check."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_excludedates(self):
        """ Add an exclude dates check to a variable."""
        dict_to_add = {"ExcludeDates":{"0":"YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM"}}
        # add the subsubsection (ExcludeDates)
        self.add_subsubsection(dict_to_add)

    def add_fileentry(self, item):
        """ Add a new entry to the [Files] section."""
        dict_to_add = {item: "Right click to browse"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_filterlist(self):
        """ Add FilterList to the [Options] section."""
        dict_to_add = {"FilterList": "Fco2"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_fsdthreshold(self):
        """ Add Fsd_threshold to the [Options] section."""
        dict_to_add = {"Fsd_threshold": "10"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_gui_section(self):
        """ Add a GUI section."""
        self.sections["GUI"] = QtGui.QStandardItem("GUI")
        self.sections["GUI"].setEditable(False)
        gui_section = {"GapFillUsingSOLO": {"nodes": "auto", "training": "500", "nda_factor": "5",
                                            "learning_rate": "0.001", "iterations": "500",
                                            "period_option": "days",
                                            "start_date": "", "end_date": "",
                                            "number_days": "60", "number_months": "2",
                                            "auto_complete": "yes", "min_percent": "25",
                                            "overwrite": "no", "show_plots": "no",
                                            "show_all": "no"}}
        for key1 in sorted(list(gui_section.keys())):
            gui_method = QtGui.QStandardItem(key1)
            gui_method.setEditable(False)
            for key2 in sorted(list(gui_section[key1].keys())):
                val = gui_section[key1][key2]
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                gui_method.appendRow([child0, child1])
            self.sections["GUI"].appendRow(gui_method)
        self.model.insertRow(self.section_headings.index("Fluxes"), self.sections["GUI"])
        self.update_tab_text()

    def add_imports_section(self):
        """ Add an Imports section."""
        self.sections["Imports"] = QtGui.QStandardItem("Imports")
        self.add_imports_variable()
        idx = self.section_headings.index("Files")+1
        self.model.insertRow(idx, self.sections["Imports"])
        self.section_headings.insert(idx, "Imports")
        self.update_tab_text()

    def add_imports_variable(self):
        """ Add a variable to the Imports section."""
        new_import = {"file_name": "Right click to browse", "var_name": "<variable_name>"}
        new_variable = QtGui.QStandardItem("New variable")
        for key in new_import:
            val = new_import[key]
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            new_variable.appendRow([child0, child1])
        self.sections["Imports"].appendRow(new_variable)
        self.update_tab_text()

    def add_interpolatetype(self):
        """ Add InterpolateType to the [Options] section."""
        dict_to_add = {"InterpolateType": "Akima"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_keepintermediateseries(self):
        """ Add KeepIntermediateSeries to the [Options] section."""
        dict_to_add = {"KeepIntermediateSeries": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_madcheck(self):
        """ Add the MAD check to a variable."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        if selected_item.text().split("_")[0] == "Fco2":
            edge_threshold = 6
        elif selected_item.text().split("_")[0] in ["Fe", "Fh"]:
            edge_threshold = 100
        else:
            edge_threshold = "20,80"
        new_qc = {"MADCheck":{"Fsd_threshold": 12, "edge_threshold": edge_threshold,
                              "window_size": 13, "zfc": 5.5,}}
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        self.add_qc_check(selected_item, new_qc)
        self.update_tab_text()

    def add_mask_long_gaps(self):
        """ Add the mask long gaps option."""
        dict_to_add = {"mask long gaps": "Yes"}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_maxgapinterpolate(self):
        """ Add MaxGapInterpolate to the [Options] section."""
        dict_to_add = {"MaxGapInterpolate": "3"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_maxshortgapdays(self):
        """ Add MaxShortGapDays to the [Options] section."""
        dict_to_add = {"MaxShortGapDays": "30"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_MDS(self):
        """ Add GapFillUsingMDS to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.data()) + "_MDS"
        dict_to_add = {"GapFillUsingMDS":{var_name: {"drivers": "Fsd,Ta,VPD",
                                                     "tolerances":"(20, 50),2.5,0.5"}}}
        # add the subsubsection (GapFillUsingMDS)
        self.add_subsubsubsection(dict_to_add)
        # update the Merge section
        selected_item =idx.model().itemFromIndex(idx)
        for i in range(selected_item.rowCount()):
            if str(selected_item.child(i, 0).text()) == "MergeSeries":
                sources = str(selected_item.child(i).child(0, 1).text())
                sources = sources + "," + var_name
                selected_item.child(i).child(0,1).setText(sources)

    def add_mds_target(self):
        """ Add MDS target to a variable."""
        dict_to_add = {"target":""}
        # add the subsubsection
        self.add_subsection(dict_to_add)

    def add_new_variable(self):
        """ Add a new variable."""
        gfSOLO = {"<var>_SOLO": {"drivers": ""}}
        gfLONG = {"<var>_LONG": {"drivers": ""}}
        gfMDS = {"<var>_MDS": {"drivers": "Fsd,Ta,VPD", "tolerances": "(20,50),2.5,0.5"}}
        gfMS = {"source": "<var>,<var>_MDS,<var>_SOLO,<var>_LONG"}
        var_dict = OrderedDict()
        var_dict["GapFillUsingMDS"] = gfMDS
        var_dict["GapFillUsingSOLO"] = gfSOLO
        var_dict["GapFillLongSOLO"] = gfLONG
        var_dict["MergeSeries"] = gfMS
        d2a = {"New variable": var_dict}
        self.add_variable(d2a)
        # update the tab text with an asterix if required
        self.update_tab_text()

    def add_qc_check(self, selected_item, new_qc):
        for key1 in new_qc:
            parent = QtGui.QStandardItem(key1)
            parent.setEditable(False)
            for key in new_qc[key1]:
                val = str(new_qc[key1][key])
                child0 = QtGui.QStandardItem(key)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent.appendRow([child0, child1])
            selected_item.appendRow(parent)
        self.update_tab_text()

    def add_rangecheck(self):
        """ Add a range check to a variable."""
        dict_to_add = {"RangeCheck":{"lower":0, "upper": 1}}
        # add the subsubsection (RangeCheck)
        self.add_subsubsection(dict_to_add)

    def add_sathreshold(self):
        """ Add sa_threshold to the [Options] section."""
        dict_to_add = {"sa_threshold": "-5"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_solo(self):
        """ Add GapFillUsingSOLO to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.data()) + "_SOLO"
        dict_to_add = {"GapFillUsingSOLO":{var_name: {"drivers": "Fn,Fg,SH,VPD,Ta,Ts"}}}
        # add the subsubsection (GapFillUsingSOLO)
        self.add_subsubsubsection(dict_to_add)
        # update the Merge section
        selected_item =idx.model().itemFromIndex(idx)
        for i in range(selected_item.rowCount()):
            if str(selected_item.child(i, 0).text()) == "MergeSeries":
                sources = str(selected_item.child(i).child(0, 1).text())
                sources = sources + "," + var_name
                selected_item.child(i).child(0,1).setText(sources)

    def add_solo_long(self):
        """ Add GapFillLongSOLO to a variable."""
        idx = self.view.selectedIndexes()[0]
        var_name = str(idx.data()) + "_LONG"
        dict_to_add = {"GapFillLongSOLO":{var_name: {"drivers": "Fn,Fg,SH,VPD,Ta,Ts,EVI"}}}
        # add the subsubsection (GapFillUsingSOLO)
        self.add_subsubsubsection(dict_to_add)
        # update the Merge section
        selected_item =idx.model().itemFromIndex(idx)
        for i in range(selected_item.rowCount()):
            if str(selected_item.child(i, 0).text()) == "MergeSeries":
                sources = str(selected_item.child(i).child(0, 1).text())
                sources = sources + "," + var_name
                selected_item.child(i).child(0,1).setText(sources)

    def add_solo_settings(self):
        """ Add solo_settings to a variable."""
        dict_to_add = {"solo_settings":"5,500,5,0.001,500"}
        # add the subsubsection (GapFillFromAlternate)
        self.add_subsection(dict_to_add)

    def add_subsection(self, dict_to_add):
        """ Add a subsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])
        self.update_tab_text()

    def add_subsubsection(self, dict_to_add):
        """ Add a subsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key1 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key1)
            subsubsection.setEditable(False)
            for key2 in dict_to_add[key1]:
                val = str(dict_to_add[key1][key2])
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                subsubsection.appendRow([child0, child1])
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_subsubsubsection(self, dict_to_add):
        """ Add a subsubsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key3 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key3)
            subsubsection.setEditable(False)
            for key4 in dict_to_add[key3]:
                subsubsubsection = QtGui.QStandardItem(key4)
                subsubsubsection.setEditable(False)
                for val in dict_to_add[key3][key4]:
                    value = dict_to_add[key3][key4][val]
                    child0 = QtGui.QStandardItem(val)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(value))
                    subsubsubsection.appendRow([child0, child1])
                subsubsection.appendRow(subsubsubsection)
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_summary_plot(self):
        """ Add a summary plot to the summary plots section."""
        new_plot = {"variables":""}
        parent = QtGui.QStandardItem("New summary plot")
        parent.setEditable(False)
        for key in new_plot:
            val = new_plot[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(str(val))
            parent.appendRow([child0, child1])
        self.sections["SummaryPlots"].appendRow(parent)
        self.update_tab_text()

    def add_summary_plots_section(self):
        """ Add a summary plots section."""
        dict_to_add = {"SOLO": {"Variables": "ustar_SOLO,Fh_SOLO,Fe_SOLO,Fc_SOLO"}}
        self.sections["SummaryPlots"] = QtGui.QStandardItem("SummaryPlots")
        self.sections["SummaryPlots"].setEditable(False)
        for key2 in dict_to_add:
            subsection = QtGui.QStandardItem(key2)
            subsection.setEditable(False)
            for key3 in dict_to_add[key2]:
                child0 = QtGui.QStandardItem(key3)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(dict_to_add[key2][key3])
                subsection.appendRow([child0, child1])
            self.sections["SummaryPlots"].appendRow(subsection)
        self.model.appendRow(self.sections["SummaryPlots"])
        self.update_tab_text()

    def add_truncate(self):
        """ Add Truncate to the [Options] section."""
        dict_to_add = {"Truncate": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_turbulencefilter(self):
        """ Add TurbulenceFilter to the [Options] section."""
        dict_to_add = {"TurbulenceFilter": "ustar"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_usefsdsynthreshold(self):
        """ Add UseFsdsyn_threshold to the [Options] section."""
        dict_to_add = {"UseFsdsyn_threshold": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_useeveningfilter(self):
        """ Add UseEveningFilter to the [Options] section."""
        dict_to_add = {"UseEveningFilter": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_ustar_threshold_section(self):
        """ Add a ustar threshold section."""
        self.sections["ustar_threshold"] = QtGui.QStandardItem("ustar_threshold")
        self.sections["ustar_threshold"].setEditable(False)
        child0 = QtGui.QStandardItem("0")
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <ustar_threshold>")
        self.sections["ustar_threshold"].appendRow([child0, child1])
        idx = self.section_headings.index("Fluxes")
        self.model.insertRow(idx, self.sections["ustar_threshold"])
        self.section_headings.insert(idx, "ustar_threshold")
        self.update_tab_text()

    def add_ustar_threshold_daterange(self):
        """ Add a year to the [ustar_threshold] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the children
        child0 = QtGui.QStandardItem(str(selected_item.rowCount()))
        child0.setEditable(False)
        child1 = QtGui.QStandardItem("YYYY-mm-dd HH:MM,YYYY-mm-dd HH:MM, <ustar_threshold>")
        # add them
        selected_item.appendRow([child0, child1])
        self.update_tab_text()

    def add_variable(self, d2a):
        """ Add a variable."""
        for key2 in d2a:
            parent2 = QtGui.QStandardItem(key2)
            # key3 is the gap filling method
            for key3 in d2a[key2]:
                parent3 = QtGui.QStandardItem(key3)
                parent3.setEditable(False)
                if key3 in ["GapFillUsingMDS", "GapFillUsingSOLO", "GapFillLongSOLO"]:
                    # key4 is the gap fill variable name
                    for key4 in d2a[key2][key3]:
                        parent4 = QtGui.QStandardItem(key4)
                        # key5 is the source of the alternate data
                        for key5 in d2a[key2][key3][key4]:
                            val = d2a[key2][key3][key4][key5]
                            child0 = QtGui.QStandardItem(key5)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(val)
                            parent4.appendRow([child0, child1])
                        parent3.appendRow(parent4)
                elif key3 in ["MergeSeries", "RangeCheck", "ExcludeDates"]:
                    for key4 in d2a[key2][key3]:
                        val = d2a[key2][key3][key4]
                        child0 = QtGui.QStandardItem(key4)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent3.appendRow([child0, child1])
                parent2.appendRow(parent3)
            self.sections["Fluxes"].appendRow(parent2)

    def browse_cpd_file(self):
        """ Browse for the CPD results file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "Excel (*.xls *.xlsx)"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path,"")
        # dialog for open file
        file_path = os.path.join(file_path, "")
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose a CPD results file ...",
                                                          directory=file_path, filter=file_filter)[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_path = QtCore.QDir.toNativeSeparators(str(new_file_path))
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_imports_file(self):
        """ Browse for the imports file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "*.nc"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path,"")
        # dialog for open file
        new_file = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an Imports file ...",
                                                     directory=file_path, filter=file_filter)[0]
        # update the model
        if len(str(new_file)) > 0:
            new_file = QtCore.QDir.toNativeSeparators(str(new_file))
            parent.child(selected_item.row(), 1).setText(new_file)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def change_selected_text(self, new_text):
        """ Change the selected text."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_item.setText(new_text)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        add_separator = False
        # get a list of the section headings at the root level
        self.section_headings = []
        root = self.model.invisibleRootItem()
        for i in range(root.rowCount()):
            self.section_headings.append(str(root.child(i).text()))
        if level == 0:
            # sections with only 1 level
            if selected_text == "Files":
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                for item in ["plot_path", "file_path", "in_filename", "out_filename", "cpd_filename"]:
                    if item not in existing_entries:
                        self.context_menu.actionAddFileEntry = QtWidgets.QAction(self)
                        self.context_menu.actionAddFileEntry.setText("Add " + item)
                        self.context_menu.addAction(self.context_menu.actionAddFileEntry)
                        self.context_menu.actionAddFileEntry.triggered.connect(lambda:self.add_fileentry(item))
                        add_separator = True
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                if "ustar_threshold" not in self.section_headings:
                    self.context_menu.actionAddUstarThreshold = QtWidgets.QAction(self)
                    self.context_menu.actionAddUstarThreshold.setText("Add u* threshold section")
                    self.context_menu.addAction(self.context_menu.actionAddUstarThreshold)
                    self.context_menu.actionAddUstarThreshold.triggered.connect(self.add_ustar_threshold_section)
                    add_separator = True
                if "GUI" not in self.section_headings:
                    self.context_menu.actionAddGUISection = QtWidgets.QAction(self)
                    self.context_menu.actionAddGUISection.setText("Add GUI section")
                    self.context_menu.addAction(self.context_menu.actionAddGUISection)
                    self.context_menu.actionAddGUISection.triggered.connect(self.add_gui_section)
                    add_separator = True
                if "Imports" not in self.section_headings:
                    self.context_menu.actionAddImports = QtWidgets.QAction(self)
                    self.context_menu.actionAddImports.setText("Add Imports section")
                    self.context_menu.addAction(self.context_menu.actionAddImports)
                    self.context_menu.actionAddImports.triggered.connect(self.add_imports_section)
                    add_separator = True
            elif selected_text in ["Imports"]:
                self.context_menu.actionAddImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddImportsVariable)
                self.context_menu.actionAddImportsVariable.triggered.connect(self.add_imports_variable)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsSection)
                self.context_menu.actionRemoveImportsSection.triggered.connect(self.remove_section)
            elif selected_text == "Options":
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                # only put an option in the context menu if it is not already present
                if "MaxGapInterpolate" not in existing_entries:
                    self.context_menu.actionAddMaxGapInterpolate = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxGapInterpolate.setText("MaxGapInterpolate")
                    self.context_menu.addAction(self.context_menu.actionAddMaxGapInterpolate)
                    self.context_menu.actionAddMaxGapInterpolate.triggered.connect(self.add_maxgapinterpolate)
                if "MaxShortGapDays" not in existing_entries:
                    self.context_menu.actionAddMaxShortGapDays = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxShortGapDays.setText("MaxShortGapDays")
                    self.context_menu.addAction(self.context_menu.actionAddMaxShortGapDays)
                    self.context_menu.actionAddMaxShortGapDays.triggered.connect(self.add_maxshortgapdays)
                if "FilterList" not in existing_entries:
                    self.context_menu.actionAddFilterList = QtWidgets.QAction(self)
                    self.context_menu.actionAddFilterList.setText("FilterList")
                    self.context_menu.addAction(self.context_menu.actionAddFilterList)
                    self.context_menu.actionAddFilterList.triggered.connect(self.add_filterlist)
                if "TurbulenceFilter" not in existing_entries:
                    self.context_menu.actionAddTurbulenceFilter = QtWidgets.QAction(self)
                    self.context_menu.actionAddTurbulenceFilter.setText("TurbulenceFilter")
                    self.context_menu.addAction(self.context_menu.actionAddTurbulenceFilter)
                    self.context_menu.actionAddTurbulenceFilter.triggered.connect(self.add_turbulencefilter)
                if "DayNightFilter" not in existing_entries:
                    self.context_menu.actionAddDayNightFilter = QtWidgets.QAction(self)
                    self.context_menu.actionAddDayNightFilter.setText("DayNightFilter")
                    self.context_menu.addAction(self.context_menu.actionAddDayNightFilter)
                    self.context_menu.actionAddDayNightFilter.triggered.connect(self.add_daynightfilter)
                if "AcceptDayTimes" not in existing_entries:
                    self.context_menu.actionAddAcceptDayTimes = QtWidgets.QAction(self)
                    self.context_menu.actionAddAcceptDayTimes.setText("AcceptDayTimes")
                    self.context_menu.addAction(self.context_menu.actionAddAcceptDayTimes)
                    self.context_menu.actionAddAcceptDayTimes.triggered.connect(self.add_acceptdaytimes)
                if "Fsd_threshold" not in existing_entries:
                    self.context_menu.actionAddFsd_threshold = QtWidgets.QAction(self)
                    self.context_menu.actionAddFsd_threshold.setText("Fsd_threshold")
                    self.context_menu.addAction(self.context_menu.actionAddFsd_threshold)
                    self.context_menu.actionAddFsd_threshold.triggered.connect(self.add_fsdthreshold)
                if "Truncate" not in existing_entries:
                    self.context_menu.actionAddTruncate = QtWidgets.QAction(self)
                    self.context_menu.actionAddTruncate.setText("Truncate")
                    self.context_menu.addAction(self.context_menu.actionAddTruncate)
                    self.context_menu.actionAddTruncate.triggered.connect(self.add_truncate)
                if "KeepIntermediateSeries" not in existing_entries:
                    self.context_menu.actionAddKeepIntermediateSeries = QtWidgets.QAction(self)
                    self.context_menu.actionAddKeepIntermediateSeries.setText("KeepIntermediateSeries")
                    self.context_menu.addAction(self.context_menu.actionAddKeepIntermediateSeries)
                    self.context_menu.actionAddKeepIntermediateSeries.triggered.connect(self.add_keepintermediateseries)
            elif selected_text == "GUI":
                self.context_menu.actionRemoveGUISection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGUISection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveGUISection)
                self.context_menu.actionRemoveGUISection.triggered.connect(self.remove_section)
            elif selected_text in ["Fluxes"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["ustar_threshold"]:
                self.context_menu.actionAddUstarThreshold = QtWidgets.QAction(self)
                self.context_menu.actionAddUstarThreshold.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddUstarThreshold)
                self.context_menu.actionAddUstarThreshold.triggered.connect(self.add_ustar_threshold_daterange)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveUstarThreshold = QtWidgets.QAction(self)
                self.context_menu.actionRemoveUstarThreshold.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveUstarThreshold)
                self.context_menu.actionRemoveUstarThreshold.triggered.connect(self.remove_section)
            elif selected_text in ["Imports"]:
                self.context_menu.actionAddImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddImportsVariable)
                self.context_menu.actionAddImportsVariable.triggered.connect(self.add_imports_variable)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsSection)
                self.context_menu.actionRemoveImportsSection.triggered.connect(self.remove_section)
            elif selected_text in ["SummaryPlots"]:
                self.context_menu.actionAddSummaryPlot = QtWidgets.QAction(self)
                self.context_menu.actionAddSummaryPlot.setText("Add summary plot")
                self.context_menu.addAction(self.context_menu.actionAddSummaryPlot)
                self.context_menu.actionAddSummaryPlot.triggered.connect(self.add_summary_plot)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveSummaryPlotSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveSummaryPlotSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveSummaryPlotSection)
                self.context_menu.actionRemoveSummaryPlotSection.triggered.connect(self.remove_section)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
                elif key in ["cpd_filename"]:
                    self.context_menu.actionBrowseCPDFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseCPDFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseCPDFile)
                    self.context_menu.actionBrowseCPDFile.triggered.connect(self.browse_cpd_file)
                else:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
            elif (str(parent.text()) == "Files") and (selected_item.column() == 0):
                key = str(parent.child(selected_item.row(),0).text())
                if key not in ["file_path", "plot_path", "in_filename", "out_filename"]:
                    self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveItem.setText("Remove item")
                    self.context_menu.addAction(self.context_menu.actionRemoveItem)
                    self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
                else:
                    pass
            elif (str(parent.text()) == "Imports"):
                self.context_menu.actionRemoveImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsVariable)
                self.context_menu.actionRemoveImportsVariable.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "Options"):
                key = str(parent.child(selected_item.row(),0).text())
                if (selected_item.column() == 0):
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                elif (selected_item.column() == 1) and (key == "AcceptDayTimes"):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeAcceptDayTimes = QtWidgets.QAction(self)
                        self.context_menu.actionChangeAcceptDayTimes.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeAcceptDayTimes)
                        self.context_menu.actionChangeAcceptDayTimes.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeAcceptDayTimes = QtWidgets.QAction(self)
                        self.context_menu.actionChangeAcceptDayTimes.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeAcceptDayTimes)
                        self.context_menu.actionChangeAcceptDayTimes.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key == "InterpolateType"):
                    if selected_text != "linear":
                        self.context_menu.actionChangeInterpolateType = QtWidgets.QAction(self)
                        self.context_menu.actionChangeInterpolateType.setText("linear")
                        self.context_menu.addAction(self.context_menu.actionChangeInterpolateType)
                        self.context_menu.actionChangeInterpolateType.triggered.connect(lambda:self.change_selected_text("linear"))
                    if selected_text != "Akima":
                        self.context_menu.actionChangeInterpolateType = QtWidgets.QAction(self)
                        self.context_menu.actionChangeInterpolateType.setText("Akima")
                        self.context_menu.addAction(self.context_menu.actionChangeInterpolateType)
                        self.context_menu.actionChangeInterpolateType.triggered.connect(lambda:self.change_selected_text("Akima"))
                elif (selected_item.column() == 1) and (key == "KeepIntermediateSeries"):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeKeepIntermediateSeries = QtWidgets.QAction(self)
                        self.context_menu.actionChangeKeepIntermediateSeries.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeKeepIntermediateSeries)
                        self.context_menu.actionChangeKeepIntermediateSeries.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeKeepIntermediateSeries = QtWidgets.QAction(self)
                        self.context_menu.actionChangeKeepIntermediateSeries.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeKeepIntermediateSeries)
                        self.context_menu.actionChangeKeepIntermediateSeries.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key in ["Truncate"]):
                    if selected_text != "To imports":
                        if "Imports" in self.section_headings:
                            self.context_menu.actionChangeTruncate1 = QtWidgets.QAction(self)
                            self.context_menu.actionChangeTruncate1.setText("To imports")
                            self.context_menu.addAction(self.context_menu.actionChangeTruncate1)
                            self.context_menu.actionChangeTruncate1.triggered.connect(lambda:self.change_selected_text("To imports"))
                    if selected_text != "No":
                        self.context_menu.actionChangeTruncate2 = QtWidgets.QAction(self)
                        self.context_menu.actionChangeTruncate2.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeTruncate2)
                        self.context_menu.actionChangeTruncate2.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key == "TurbulenceFilter"):
                    existing_entry = str(parent.child(selected_item.row(),1).text())
                    for item in ["ustar (basic)", "ustar (EvGB)", "ustar (FluxNet)",
                                 "ustar (FluxNet+day)", "none"]:
                        if existing_entry != item:
                            self.context_menu.SetUstarFilter = QtWidgets.QAction(self)
                            self.context_menu.SetUstarFilter.setText(item)
                            self.context_menu.addAction(self.context_menu.SetUstarFilter)
                            self.context_menu.SetUstarFilter.triggered.connect(lambda: self.set_ustar_filter(item))
            elif (str(parent.text()) in ["Fluxes"]):
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                # only put a QC check in the context menu if it is not already present
                if "GapFillUsingSOLO" not in existing_entries:
                    self.context_menu.actionAddSOLO = QtWidgets.QAction(self)
                    self.context_menu.actionAddSOLO.setText("Add SOLO")
                    self.context_menu.addAction(self.context_menu.actionAddSOLO)
                    self.context_menu.actionAddSOLO.triggered.connect(self.add_solo)
                    add_separator = True
                if "GapFillLongSOLO" not in existing_entries:
                    self.context_menu.actionAddLongSOLO = QtWidgets.QAction(self)
                    self.context_menu.actionAddLongSOLO.setText("Add SOLO (long gaps)")
                    self.context_menu.addAction(self.context_menu.actionAddLongSOLO)
                    self.context_menu.actionAddLongSOLO.triggered.connect(self.add_solo_long)
                    add_separator = True
                if "GapFillUsingMDS" not in existing_entries:
                    self.context_menu.actionAddMDS = QtWidgets.QAction(self)
                    self.context_menu.actionAddMDS.setText("Add MDS")
                    self.context_menu.addAction(self.context_menu.actionAddMDS)
                    self.context_menu.actionAddMDS.triggered.connect(self.add_MDS)
                    add_separator = True
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                if "RangeCheck" not in existing_entries:
                    self.context_menu.actionAddRangeCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddRangeCheck.setText("Add RangeCheck")
                    self.context_menu.addAction(self.context_menu.actionAddRangeCheck)
                    self.context_menu.actionAddRangeCheck.triggered.connect(self.add_rangecheck)
                    add_separator = True
                if "DependencyCheck" not in existing_entries:
                    self.context_menu.actionAddDependencyCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDependencyCheck.setText("Add DependencyCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDependencyCheck)
                    self.context_menu.actionAddDependencyCheck.triggered.connect(self.add_dependencycheck)
                    add_separator = True
                if "DiurnalCheck" not in existing_entries:
                    self.context_menu.actionAddDiurnalCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddDiurnalCheck.setText("Add DiurnalCheck")
                    self.context_menu.addAction(self.context_menu.actionAddDiurnalCheck)
                    self.context_menu.actionAddDiurnalCheck.triggered.connect(self.add_diurnalcheck)
                    add_separator = True
                if "ExcludeDates" not in existing_entries:
                    self.context_menu.actionAddExcludeDates = QtWidgets.QAction(self)
                    self.context_menu.actionAddExcludeDates.setText("Add ExcludeDates")
                    self.context_menu.addAction(self.context_menu.actionAddExcludeDates)
                    self.context_menu.actionAddExcludeDates.triggered.connect(self.add_excludedates)
                    add_separator = True
                if "MADCheck" not in existing_entries:
                    self.context_menu.actionAddMADCheck = QtWidgets.QAction(self)
                    self.context_menu.actionAddMADCheck.setText("Add MADCheck")
                    self.context_menu.addAction(self.context_menu.actionAddMADCheck)
                    self.context_menu.actionAddMADCheck.triggered.connect(self.add_madcheck)
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "ustar_threshold"):
                self.context_menu.actionRemoveDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveDateRange)
                self.context_menu.actionRemoveDateRange.triggered.connect(self.remove_daterange)
            elif (str(parent.text()) == "Imports"):
                self.context_menu.actionRemoveImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsVariable)
                self.context_menu.actionRemoveImportsVariable.triggered.connect(self.remove_item)
            elif str(parent.text()) == "SummaryPlots":
                self.context_menu.actionRemoveSummaryPlot = QtWidgets.QAction(self)
                self.context_menu.actionRemoveSummaryPlot.setText("Remove summary plot")
                self.context_menu.addAction(self.context_menu.actionRemoveSummaryPlot)
                self.context_menu.actionRemoveSummaryPlot.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            parent = selected_item.parent()
            grand_parent = selected_item.parent().parent()
            subsubsection_name = str(idx.data())
            if subsubsection_name in ["RangeCheck", "DependencyCheck", "DiurnalCheck", "MADCheck"]:
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
            elif subsubsection_name in ["ExcludeDates"]:
                self.context_menu.actionAddExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionAddExcludeDateRange.setText("Add date range")
                self.context_menu.addAction(self.context_menu.actionAddExcludeDateRange)
                self.context_menu.actionAddExcludeDateRange.triggered.connect(self.add_excludedaterange)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveQCCheck = QtWidgets.QAction(self)
                self.context_menu.actionRemoveQCCheck.setText("Remove QC check")
                self.context_menu.addAction(self.context_menu.actionRemoveQCCheck)
                self.context_menu.actionRemoveQCCheck.triggered.connect(self.remove_item)
            elif subsubsection_name in ["GapFillUsingSOLO", "GapFillLongSOLO", "GapFillUsingMDS", "GapFillFromClimatology"]:
                self.context_menu.actionRemoveGFMethod = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGFMethod.setText("Remove method")
                self.context_menu.addAction(self.context_menu.actionRemoveGFMethod)
                self.context_menu.actionRemoveGFMethod.triggered.connect(self.remove_GFMethod)
            if str(grand_parent.text() == "Imports"):
                key = str(parent.child(selected_item.row(),0).text())
                if (key == "file_name") and (selected_item.column() == 1):
                    self.context_menu.actionBrowseImportsFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseImportsFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseImportsFile)
                    self.context_menu.actionBrowseImportsFile.triggered.connect(self.browse_imports_file)
        elif level == 3:
            # sections with 4 levels
            # get the parent text
            parent_text = str(idx.parent().data())
            if parent_text == "ExcludeDates":
                self.context_menu.actionRemoveExcludeDateRange = QtWidgets.QAction(self)
                self.context_menu.actionRemoveExcludeDateRange.setText("Remove date range")
                self.context_menu.addAction(self.context_menu.actionRemoveExcludeDateRange)
                self.context_menu.actionRemoveExcludeDateRange.triggered.connect(self.remove_daterange)
            elif parent_text == "GapFillUsingSOLO":
                # get a list of existing entries
                existing_entries = self.get_existing_entries()
                if "solo_settings" not in existing_entries:
                    self.context_menu.actionAddSOLOSettings = QtWidgets.QAction(self)
                    self.context_menu.actionAddSOLOSettings.setText("Add SOLO settings")
                    self.context_menu.addAction(self.context_menu.actionAddSOLOSettings)
                    self.context_menu.actionAddSOLOSettings.triggered.connect(self.add_solo_settings)
                    add_separator = True
                if "mask long gaps" not in existing_entries:
                    self.context_menu.actionAddMaskLongGaps = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaskLongGaps.setText("Add mask long gaps")
                    self.context_menu.addAction(self.context_menu.actionAddMaskLongGaps)
                    self.context_menu.actionAddMaskLongGaps.triggered.connect(self.add_mask_long_gaps)
                if add_separator:
                    add_separator = False
                    self.context_menu.addSeparator()
                self.context_menu.actionRemoveGFMethodVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGFMethodVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveGFMethodVariable)
                self.context_menu.actionRemoveGFMethodVariable.triggered.connect(self.remove_item)
            elif parent_text == "GapFillUsingMDS":
                existing_entries = self.get_existing_entries()
                if "target" not in existing_entries:
                    self.context_menu.actionAddMDStarget = QtWidgets.QAction(self)
                    self.context_menu.actionAddMDStarget.setText("Add target")
                    self.context_menu.addAction(self.context_menu.actionAddMDStarget)
                    self.context_menu.actionAddMDStarget.triggered.connect(self.add_mds_target)
                if "mask long gaps" not in existing_entries:
                    self.context_menu.actionAddMaskLongGaps = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaskLongGaps.setText("Add mask long gaps")
                    self.context_menu.addAction(self.context_menu.actionAddMaskLongGaps)
                    self.context_menu.actionAddMaskLongGaps.triggered.connect(self.add_mask_long_gaps)
        elif level == 4:
            selected_text = str(idx.data())
            parent = selected_item.parent()
            key = str(parent.child(selected_item.row(),0).text())
            if (selected_item.column() == 0) and selected_text in ["solo_settings", "mask long gaps"]:
                self.context_menu.actionRemoveSOLOSettings = QtWidgets.QAction(self)
                self.context_menu.actionRemoveSOLOSettings.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveSOLOSettings)
                self.context_menu.actionRemoveSOLOSettings.triggered.connect(self.remove_item)
            if (selected_item.column() == 1) and (key == "mask long gaps"):
                if selected_text != "Yes":
                    self.context_menu.actionChangeMaskLongGaps = QtWidgets.QAction(self)
                    self.context_menu.actionChangeMaskLongGaps.setText("Yes")
                    self.context_menu.addAction(self.context_menu.actionChangeMaskLongGaps)
                    self.context_menu.actionChangeMaskLongGaps.triggered.connect(lambda:self.change_selected_text("Yes"))
                if selected_text != "No":
                    self.context_menu.actionChangeMaskLongGaps = QtWidgets.QAction(self)
                    self.context_menu.actionChangeMaskLongGaps.setText("No")
                    self.context_menu.addAction(self.context_menu.actionChangeMaskLongGaps)
                    self.context_menu.actionChangeMaskLongGaps.triggered.connect(lambda:self.change_selected_text("No"))
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_l5_gui(self):
        """ Edit an L5 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "L5"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Global", "Output", "Options", "ustar_threshold"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Imports", "GUI"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
            elif key1 in []:
                # sections with 3 levels
                pass
            elif key1 in ["Fluxes", "Variables"]:
                # sections with 4 levels
                for j in range(section.rowCount()):
                    # subsections are variables
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        # subsubsections are GapFillUsingSOLO, GapFillUsingMDS and MergeSeries
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        if key3 in ["GapFillUsingSOLO", "GapFillLongSOLO", "GapFillUsingMDS"]:
                            for l in range(subsubsection.rowCount()):
                                subsubsubsection = subsubsection.child(l)
                                key4 = str(subsubsubsection.text())
                                cfg[key1][key2][key3][key4] = {}
                                for m in range(subsubsubsection.rowCount()):
                                    key5 = str(subsubsubsection.child(m, 0).text())
                                    val5 = str(subsubsubsection.child(m, 1).text())
                                    cfg[key1][key2][key3][key4][key5] = val5
                        elif key3 in ["MergeSeries", "RangeCheck", "DiurnalCheck",
                                      "DependencyCheck", "ExcludeDates", "MADCheck"]:
                            for l in range(subsubsection.rowCount()):
                                key4 = str(subsubsection.child(l, 0).text())
                                val4 = str(subsubsection.child(l, 1).text())
                                cfg[key1][key2][key3][key4] = val4

        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if key1 in ["Files", "Global", "Options", "ustar_threshold"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif  key1 in ["Imports", "GUI"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Fluxes", "Variables"]:
                # sections with 4 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the gap filling method
                    for key3 in self.cfg[key1][key2]:
                        parent3 = QtGui.QStandardItem(key3)
                        parent3.setEditable(False)
                        if key3 in ["GapFillUsingSOLO", "GapFillLongSOLO", "GapFillUsingMDS"]:
                            # key4 is the gap fill variable name
                            for key4 in self.cfg[key1][key2][key3]:
                                parent4 = QtGui.QStandardItem(key4)
                                # key5 is the source of the alternate data
                                for key5 in self.cfg[key1][key2][key3][key4]:
                                    val = self.cfg[key1][key2][key3][key4][key5]
                                    child0 = QtGui.QStandardItem(key5)
                                    child0.setEditable(False)
                                    child1 = QtGui.QStandardItem(val)
                                    parent4.appendRow([child0, child1])
                                parent3.appendRow(parent4)
                        elif key3 in ["MergeSeries", "RangeCheck", "ExcludeDates",
                                      "DiurnalCheck", "DependencyCheck", "MADCheck"]:
                            for key4 in self.cfg[key1][key2][key3]:
                                val = self.cfg[key1][key2][key3][key4]
                                child0 = QtGui.QStandardItem(key4)
                                child0.setEditable(False)
                                child1 = QtGui.QStandardItem(val)
                                parent3.appendRow([child0, child1])
                        parent2.appendRow(parent3)
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
        return

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Fluxes"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_daterange(self):
        """ Remove a date range from the ustar_threshold section."""
        # remove the date range
        self.remove_item()
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # item from index
        selected_item = idx.model().itemFromIndex(idx)
        # parent of selected item
        parent = selected_item.parent()
        # renumber the subsections
        for i in range(parent.rowCount()):
            parent.child(i, 0).setText(str(i))

    def remove_GFMethod(self):
        """ Remove a gap filling method from a variable."""
        # get the currently selected item
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent
        parent = selected_item.parent()
        # get the variable name
        var_name = str(selected_item.child(0).text())
        # find the MergeSeries entry
        for i in range(parent.rowCount()):
            if str(parent.child(i, 0).text()) == "MergeSeries":
                # get the "Sources" value
                sources = str(parent.child(i).child(0, 1).text())
                # remove the variable name from the Sources value
                if var_name in sources:
                    sources = sources.replace(var_name, "")
                    # remove double commas
                    sources = sources.replace(",,",",")
                    # remove leading or trailing commas
                    if sources[0] == ",":
                        sources = sources[1:]
                    if sources[-1] == ",":
                        sources = sources[:-1]
                    # update the MergeSeries Sources value
                    parent.child(i).child(0, 1).setText(sources)
        self.remove_item()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        # update the tab text
        self.update_tab_text()

    def remove_section(self):
        """ Remove a section from the view."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # remove the entry from the section_headings list
        self.section_headings.remove(selected_item.text())
        # get the root
        root = self.model.invisibleRootItem()
        # remove the row
        root.removeRow(selected_item.row())
        # update the tab text
        self.update_tab_text()

    def set_none(self):
        """ Set the turbulence filter to none."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText("none")

    def set_ustar_filter(self, item):
        """ Set the turbulence filter type."""
        sender = str(self.context_menu.sender().text())
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        parent = selected_item.parent()
        parent.child(selected_item.row(), 1).setText(sender)

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_L6(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_L6, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_l6_gui()

    def add_fileentry(self, item):
        """ Add a new entry to the [Files] section."""
        dict_to_add = {item: "Right click to browse"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_global_attribute(self):
        """ Add a new global attribute to the [Global] section."""
        dict_to_add = {"New attribute":""}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_gui_section(self):
        """ Add a GUI section."""
        self.sections["GUI"] = QtGui.QStandardItem("GUI")
        self.sections["GUI"].setEditable(False)
        gui_section = {"ERUsingSOLO": {"nodes": "1", "training": "500", "nda_factor": "5",
                                       "learning_rate": "0.001", "iterations": "500",
                                       "period_option": "manual",
                                       "start_date": "", "end_date": "",
                                       "number_days": "90", "number_months": "3",
                                       "auto_complete": "yes", "min_percent": "5",
                                       "overwrite": "no", "show_plots": "no",
                                       "show_all": "no"}}
        for key1 in sorted(list(gui_section.keys())):
            gui_method = QtGui.QStandardItem(key1)
            gui_method.setEditable(False)
            for key2 in sorted(list(gui_section[key1].keys())):
                val = gui_section[key1][key2]
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                gui_method.appendRow([child0, child1])
            self.sections["GUI"].appendRow(gui_method)
        self.model.insertRow(self.section_headings.index("EcosystemRespiration"), self.sections["GUI"])
        self.update_tab_text()

    def add_imports_section(self):
        """ Add an Imports section."""
        self.sections["Imports"] = QtGui.QStandardItem("Imports")
        self.add_imports_variable()
        self.model.insertRow(self.section_headings.index("Files")+1, self.sections["Imports"])
        self.update_tab_text()

    def add_imports_variable(self):
        """ Add a variable to the Imports section."""
        new_import = {"file_name": "Right click to browse", "var_name": "<variable_name>"}
        new_variable = QtGui.QStandardItem("New variable")
        for key in new_import:
            val = new_import[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            new_variable.appendRow([child0, child1])
        self.sections["Imports"].appendRow(new_variable)
        self.update_tab_text()

    def add_maxgapinterpolate(self):
        """ Add MaxGapInterpolate to the [Options] section."""
        dict_to_add = {"MaxGapInterpolate":"3"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_maxgapdays(self):
        """ Add MaxGapDays to the [Options] section."""
        dict_to_add = {"MaxGapDays": "180"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_minpercentday(self):
        """ Add MinPercentDay to the [Options] section."""
        dict_to_add = {"MinPercentDay": "10"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def add_er_variable(self, method):
        """ Add a variable to the EcosystemRespiration section."""
        if method == "SOLO":
            solo_options = {"drivers": "Ta,Ts,Sws",
                            "target": "ER"}
            er_to_add = {"ER_SOLO": {"ERUsingSOLO": {"ER_SOLO_all": solo_options},
                                     "MergeSeries": {"source": "ER,ER_SOLO_all"}}}
            nee_to_add = {"NEE_SOLO": {"Fco2": "Fco2", "ER": "ER_SOLO"}}
            gpp_to_add = {"GPP_SOLO": {"NEE": "NEE_SOLO", "ER": "ER_SOLO"}}
        elif method == "LT":
            lt_options = {"drivers": "Ta",
                          "target": "ER",
                          "minimum_temperature_spread": 5,
                          "step_size_days": 5,
                          "window_size_days": 15,
                          "minimum_percent_annual": 5,
                          "minimum_percent_noct_window": 5,
                          "output_plots": False}
            er_to_add = {"ER_LT": {"ERUsingLloydTaylor": {"ER_LT_all": lt_options},
                                     "MergeSeries": {"source": "ER,ER_LT_all"}}}
            nee_to_add = {"NEE_LT": {"Fco2": "Fco2", "ER": "ER_LT"}}
            gpp_to_add = {"GPP_LT": {"NEE": "NEE_LT", "ER": "ER_LT"}}
        elif method == "LL":
            ll_options = {"drivers": "Fsd,VPD,Ta",
                          "target": "ER",
                          "step_size_days": 5,
                          "window_size_days": 15,
                          "output_plots": False}
            er_to_add = {"ER_LL": {"ERUsingLasslop": {"ER_LL_all": ll_options},
                                     "MergeSeries": {"source": "ER,ER_LL_all"}}}
            nee_to_add = {"NEE_LL": {"Fco2": "Fco2", "ER": "ER_LL"}}
            gpp_to_add = {"GPP_LL": {"NEE": "NEE_LL", "ER": "ER_LL"}}
        else:
            return
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        for key2 in er_to_add:
            parent2 = QtGui.QStandardItem(key2)
            parent2.setEditable(False)
            for key3 in er_to_add[key2]:
                parent3 = QtGui.QStandardItem(key3)
                parent3.setEditable(False)
                if key3 in ["ERUsingSOLO", "ERUsingLloydTaylor", "ERUsingLasslop"]:
                    for key4 in er_to_add[key2][key3]:
                        parent4 = QtGui.QStandardItem(key4)
                        parent4.setEditable(False)
                        for key5 in er_to_add[key2][key3][key4]:
                            val = er_to_add[key2][key3][key4][key5]
                            child0 = QtGui.QStandardItem(key5)
                            child0.setEditable(False)
                            child1 = QtGui.QStandardItem(str(val))
                            parent4.appendRow([child0, child1])
                        parent3.appendRow(parent4)
                elif key3 in ["MergeSeries"]:
                    for key4 in er_to_add[key2][key3]:
                        val = er_to_add[key2][key3][key4]
                        child0 = QtGui.QStandardItem(key4)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent3.appendRow([child0, child1])
                parent2.appendRow(parent3)
            section.appendRow(parent2)
        # update the NetEcosystemExchange section
        # iterate over sections to find the NetEcosystemExchange section
        for i in range(self.model.rowCount()):
            section = self.model.item(i)
            if section.text() == "NetEcosystemExchange":
                break
        # add the NEE variable
        for key2 in nee_to_add:
            parent2 = QtGui.QStandardItem(key2)
            parent2.setEditable(False)
            for key3 in nee_to_add[key2]:
                val = nee_to_add[key2][key3]
                child0 = QtGui.QStandardItem(key3)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent2.appendRow([child0, child1])
            section.appendRow(parent2)
        # update the GrossPrimaryProduction section
        # iterate over sections to find the GrossPrimaryProduction section
        for i in range(self.model.rowCount()):
            section = self.model.item(i)
            if section.text() == "GrossPrimaryProductivity":
                break
        # add the GPP variable
        for key2 in gpp_to_add:
            parent2 = QtGui.QStandardItem(key2)
            parent2.setEditable(False)
            for key3 in gpp_to_add[key2]:
                val = gpp_to_add[key2][key3]
                child0 = QtGui.QStandardItem(key3)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent2.appendRow([child0, child1])
            section.appendRow(parent2)
        self.update_tab_text()

    def add_et_variable(self):
        """ Add a variable to the ET section"""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        var_to_add = {"New variable": {"Fe": ""}}
        for key1 in var_to_add:
            parent = QtGui.QStandardItem(key1)
            #parent.setEditable(False)
            for key2 in var_to_add[key1]:
                val = var_to_add[key1][key2]
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                parent.appendRow([child0, child1])
            section.appendRow(parent)
        self.update_tab_text()

    def add_options_section(self):
        """ Add an Options section."""
        self.sections["Options"] = QtGui.QStandardItem("Options")
        new_options = {"Fsd_threshold": "10", "PlotRawData": "No",
                       "MaxGapInterpolate": "3", "MaxGapDays": "180",
                       "MinPercentDay": "10", "Truncate": "No"}
        for key in new_options:
            value = new_options[key]
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(value)
            self.sections["Options"].appendRow([child0, child1])
        self.model.insertRow(self.section_headings.index("EcosystemRespiration"),
                             self.sections["Options"])
        self.update_tab_text()

    def add_subsection(self, dict_to_add):
        """ Add a subsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child0.setEditable(False)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])
        self.update_tab_text()

    def add_subsubsection(self, dict_to_add):
        """ Add a subsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key1 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key1)
            subsubsection.setEditable(False)
            for key2 in dict_to_add[key1]:
                val = str(dict_to_add[key1][key2])
                child0 = QtGui.QStandardItem(key2)
                child0.setEditable(False)
                child1 = QtGui.QStandardItem(val)
                subsubsection.appendRow([child0, child1])
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_subsubsubsection(self, dict_to_add):
        """ Add a subsubsubsection to the model."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        subsection = idx.model().itemFromIndex(idx)
        for key3 in dict_to_add:
            subsubsection = QtGui.QStandardItem(key3)
            subsubsection.setEditable(False)
            for key4 in dict_to_add[key3]:
                subsubsubsection = QtGui.QStandardItem(key4)
                subsubsubsection.setEditable(False)
                for val in dict_to_add[key3][key4]:
                    value = dict_to_add[key3][key4][val]
                    child0 = QtGui.QStandardItem(val)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(str(value))
                    subsubsubsection.appendRow([child0, child1])
                subsubsection.appendRow(subsubsubsection)
            subsection.appendRow(subsubsection)
        self.update_tab_text()

    def add_truncate(self):
        """ Add Truncate to the [Options] section."""
        dict_to_add = {"Truncate": "No"}
        # add the subsection
        self.add_subsection(dict_to_add)

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_imports_file(self):
        """ Browse for the imports file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # set the file filter
        file_filter = "*.nc"
        # get the file path from the selected item
        file_path = os.path.split(str(idx.data()))[0]
        file_path = os.path.join(file_path,"")
        # dialog for open file
        new_file = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an Imports file ...",
                                                     directory=file_path, filter=file_filter)[0]
        # update the model
        if len(str(new_file)) > 0:
            new_file = QtCore.QDir.toNativeSeparators(str(new_file))
            parent.child(selected_item.row(), 1).setText(new_file)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def change_selected_text(self, new_text):
        """ Change the selected text."""
        idx = self.view.selectedIndexes()[0]
        selected_item = idx.model().itemFromIndex(idx)
        selected_item.setText(new_text)

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        add_separator = False
        # get a list of the section headings at the root level
        self.section_headings = []
        root = self.model.invisibleRootItem()
        for i in range(root.rowCount()):
            self.section_headings.append(str(root.child(i).text()))
        if level == 0:
            add_separator = False
            selected_text = str(idx.data())
            if selected_text == "Files":
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                for item in ["plot_path", "file_path", "in_filename", "out_filename"]:
                    if item not in existing_entries:
                        self.context_menu.actionAddFileEntry = QtWidgets.QAction(self)
                        self.context_menu.actionAddFileEntry.setText("Add " + item)
                        self.context_menu.addAction(self.context_menu.actionAddFileEntry)
                        self.context_menu.actionAddFileEntry.triggered.connect(lambda:self.add_fileentry(item))
                        add_separator = True
                if add_separator:
                    self.context_menu.addSeparator()
                    add_separator = False
                if "GUI" not in self.section_headings:
                    self.context_menu.actionAddGUISection = QtWidgets.QAction(self)
                    self.context_menu.actionAddGUISection.setText("Add GUI section")
                    self.context_menu.addAction(self.context_menu.actionAddGUISection)
                    self.context_menu.actionAddGUISection.triggered.connect(self.add_gui_section)
                    add_separator = True
                if "Imports" not in self.section_headings:
                    self.context_menu.actionAddImportsSection = QtWidgets.QAction(self)
                    self.context_menu.actionAddImportsSection.setText("Add Imports section")
                    self.context_menu.addAction(self.context_menu.actionAddImportsSection)
                    self.context_menu.actionAddImportsSection.triggered.connect(self.add_imports_section)
                    add_separator = True
                if "Options" not in self.section_headings:
                    self.context_menu.actionAddOptionsSection = QtWidgets.QAction(self)
                    self.context_menu.actionAddOptionsSection.setText("Add Options section")
                    self.context_menu.addAction(self.context_menu.actionAddOptionsSection)
                    self.context_menu.actionAddOptionsSection.triggered.connect(self.add_options_section)
                    add_separator = True
            elif selected_text == "Imports":
                self.context_menu.actionAddImportsVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddImportsVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddImportsVariable)
                self.context_menu.actionAddImportsVariable.triggered.connect(self.add_imports_variable)
                self.context_menu.addSeparator()
                self.context_menu.actionRemoveImportsSection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveImportsSection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveImportsSection)
                self.context_menu.actionRemoveImportsSection.triggered.connect(self.remove_section)
            elif selected_text == "Options":
                # get a list of existing entries in this section
                existing_entries = self.get_existing_entries()
                # only put a QC check in the context menu if it is not already present
                if "MaxGapInterpolate" not in existing_entries:
                    self.context_menu.actionAddMaxGapInterpolate = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxGapInterpolate.setText("MaxGapInterpolate")
                    self.context_menu.addAction(self.context_menu.actionAddMaxGapInterpolate)
                    self.context_menu.actionAddMaxGapInterpolate.triggered.connect(self.add_maxgapinterpolate)
                if "MaxGapDays" not in existing_entries:
                    self.context_menu.actionAddMaxGapDays = QtWidgets.QAction(self)
                    self.context_menu.actionAddMaxGapDays.setText("MaxGapDays")
                    self.context_menu.addAction(self.context_menu.actionAddMaxGapDays)
                    self.context_menu.actionAddMaxGapDays.triggered.connect(self.add_maxgapdays)
                if "MinPercentDay" not in existing_entries:
                    self.context_menu.actionAddMinPercentDay = QtWidgets.QAction(self)
                    self.context_menu.actionAddMinPercentDay.setText("MinPercentDay")
                    self.context_menu.addAction(self.context_menu.actionAddMinPercentDay)
                    self.context_menu.actionAddMinPercentDay.triggered.connect(self.add_minpercentday)
                if "Truncate" not in existing_entries and "Imports" in self.section_headings:
                    self.context_menu.actionAddTruncate = QtWidgets.QAction(self)
                    self.context_menu.actionAddTruncate.setText("Truncate")
                    self.context_menu.addAction(self.context_menu.actionAddTruncate)
                    self.context_menu.actionAddTruncate.triggered.connect(self.add_truncate)
            elif selected_text == "GUI":
                self.context_menu.actionRemoveGUISection = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGUISection.setText("Remove section")
                self.context_menu.addAction(self.context_menu.actionRemoveGUISection)
                self.context_menu.actionRemoveGUISection.triggered.connect(self.remove_section)
            elif selected_text == "Global":
                self.context_menu.actionAddGlobalAttribute = QtWidgets.QAction(self)
                self.context_menu.actionAddGlobalAttribute.setText("Add global attribute")
                self.context_menu.addAction(self.context_menu.actionAddGlobalAttribute)
                self.context_menu.actionAddGlobalAttribute.triggered.connect(self.add_global_attribute)
            elif selected_text in ["EcosystemRespiration"]:
                existing_entries = self.get_existing_entries2()
                if "ERUsingSOLO" not in existing_entries:
                    self.context_menu.actionAddSOLOVariable = QtWidgets.QAction(self)
                    self.context_menu.actionAddSOLOVariable.setText("Add SOLO variable")
                    self.context_menu.addAction(self.context_menu.actionAddSOLOVariable)
                    self.context_menu.actionAddSOLOVariable.triggered.connect(lambda: self.add_er_variable("SOLO"))
                if "ERUsingLloydTaylor" not in existing_entries:
                    self.context_menu.actionAddLTVariable = QtWidgets.QAction(self)
                    self.context_menu.actionAddLTVariable.setText("Add Lloyd-Taylor variable")
                    self.context_menu.addAction(self.context_menu.actionAddLTVariable)
                    self.context_menu.actionAddLTVariable.triggered.connect(lambda: self.add_er_variable("LT"))
                if "ERUsingLasslop" not in existing_entries:
                    self.context_menu.actionAddLLVariable = QtWidgets.QAction(self)
                    self.context_menu.actionAddLLVariable.setText("Add Lasslop variable")
                    self.context_menu.addAction(self.context_menu.actionAddLLVariable)
                    self.context_menu.actionAddLLVariable.triggered.connect(lambda: self.add_er_variable("LL"))
            elif selected_text in ["EvapoTranspiration"]:
                existing_entries = self.get_existing_entries()
                self.context_menu.actionAddETVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddETVariable.setText("Add ET variable")
                self.context_menu.addAction(self.context_menu.actionAddETVariable)
                self.context_menu.actionAddETVariable.triggered.connect(lambda: self.add_et_variable())
            elif selected_text in ["NetEcosystemExchange"]:
                pass
            elif selected_text in ["GrossPrimaryProductivity"]:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
            elif (str(parent.text()) == "Global") and (selected_item.column() == 0):
                self.context_menu.actionRemoveGlobalAttribute = QtWidgets.QAction(self)
                self.context_menu.actionRemoveGlobalAttribute.setText("Remove attribute")
                self.context_menu.addAction(self.context_menu.actionRemoveGlobalAttribute)
                self.context_menu.actionRemoveGlobalAttribute.triggered.connect(self.remove_item)
            elif str(parent.text()) == "Options":
                key = str(parent.child(selected_item.row(),0).text())
                if (selected_item.column() == 0):
                    self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                    self.context_menu.actionRemoveOption.setText("Remove option")
                    self.context_menu.addAction(self.context_menu.actionRemoveOption)
                    self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                elif (selected_item.column() == 1) and (key in ["PlotRawData"]):
                    if selected_text != "Yes":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("Yes")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("Yes"))
                    if selected_text != "No":
                        self.context_menu.actionChangeOption = QtWidgets.QAction(self)
                        self.context_menu.actionChangeOption.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeOption)
                        self.context_menu.actionChangeOption.triggered.connect(lambda:self.change_selected_text("No"))
                elif (selected_item.column() == 1) and (key in ["Truncate"]):
                    if selected_text != "To imports":
                        if "Imports" in self.section_headings:
                            self.context_menu.actionChangeTruncate1 = QtWidgets.QAction(self)
                            self.context_menu.actionChangeTruncate1.setText("To imports")
                            self.context_menu.addAction(self.context_menu.actionChangeTruncate1)
                            self.context_menu.actionChangeTruncate1.triggered.connect(lambda:self.change_selected_text("To imports"))
                    if selected_text != "No":
                        self.context_menu.actionChangeTruncate2 = QtWidgets.QAction(self)
                        self.context_menu.actionChangeTruncate2.setText("No")
                        self.context_menu.addAction(self.context_menu.actionChangeTruncate2)
                        self.context_menu.actionChangeTruncate2.triggered.connect(lambda:self.change_selected_text("No"))
            elif (str(parent.text()) == "EcosystemRespiration") and (selected_item.column() == 0):
                self.context_menu.actionRemoveERVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveERVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveERVariable)
                self.context_menu.actionRemoveERVariable.triggered.connect(self.remove_er_variable)
            elif ((str(parent.text()) == "EvapoTranspiration") and (selected_item.column() == 0) and
                  (selected_text != "ET")):
                self.context_menu.actionRemoveETVariable = QtWidgets.QAction(self)
                self.context_menu.actionRemoveETVariable.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveETVariable)
                self.context_menu.actionRemoveETVariable.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            parent = selected_item.parent()
            grand_parent = selected_item.parent().parent()
            if str(grand_parent.text() == "Imports"):
                key = str(parent.child(selected_item.row(),0).text())
                if (key == "file_name") and (selected_item.column() == 1):
                    self.context_menu.actionBrowseImportsFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseImportsFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseImportsFile)
                    self.context_menu.actionBrowseImportsFile.triggered.connect(self.browse_imports_file)

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_l6_gui(self):
        """ Edit an L6 control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "L6"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Global", "Output", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["NetEcosystemExchange", "GrossPrimaryProductivity",
                          "EvapoTranspiration", "Imports", "GUI"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3
            elif key1 in ["EcosystemRespiration"]:
                # sections with 4 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        subsubsection = subsection.child(k)
                        key3 = str(subsubsection.text())
                        cfg[key1][key2][key3] = {}
                        if key3 in ["ERUsingSOLO", "ERUsingFFNET", "ERUsingLloydTaylor", "ERUsingLasslop"]:
                            for l in range(subsubsection.rowCount()):
                                subsubsubsection = subsubsection.child(l)
                                key4 = str(subsubsubsection.text())
                                cfg[key1][key2][key3][key4] = {}
                                for m in range(subsubsubsection.rowCount()):
                                    key5 = str(subsubsubsection.child(m, 0).text())
                                    val5 = str(subsubsubsection.child(m, 1).text())
                                    cfg[key1][key2][key3][key4][key5] = val5
                        elif key3 in ["MergeSeries"]:
                            for l in range(subsubsection.rowCount()):
                                key4 = str(subsubsection.child(l, 0).text())
                                val4 = str(subsubsection.child(l, 1).text())
                                cfg[key1][key2][key3][key4] = val4

        return cfg

    def get_existing_entries(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing QC checks
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                existing_entries.append(str(selected_item.child(i, 0).text()))
        return existing_entries

    def get_existing_entries2(self):
        """ Get a list of existing entries in the current section."""
        # index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from its index
        selected_item = idx.model().itemFromIndex(idx)
        # build a list of existing entries
        existing_entries = []
        if selected_item.hasChildren():
            for i in range(selected_item.rowCount()):
                if selected_item.child(i).hasChildren():
                    for j in range(selected_item.child(i).rowCount()):
                        if selected_item.child(i).child(j).text() not in ["MergeSeries"]:
                            existing_entries.append(str(selected_item.child(i).child(j).text()))
        return existing_entries

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Global", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["NetEcosystemExchange", "GrossPrimaryProductivity",
                          "EvapoTranspiration", "Imports", "GUI"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])
            elif key1 in ["EcosystemRespiration"]:
                # sections with 4 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    parent2.setEditable(False)
                    for key3 in self.cfg[key1][key2]:
                        parent3 = QtGui.QStandardItem(key3)
                        parent3.setEditable(False)
                        if key3 in ["ERUsingSOLO", "ERUsingLloydTaylor", "ERUsingLasslop"]:
                            for key4 in self.cfg[key1][key2][key3]:
                                parent4 = QtGui.QStandardItem(key4)
                                parent4.setEditable(False)
                                for key5 in self.cfg[key1][key2][key3][key4]:
                                    val = self.cfg[key1][key2][key3][key4][key5]
                                    child0 = QtGui.QStandardItem(key5)
                                    child0.setEditable(False)
                                    child1 = QtGui.QStandardItem(val)
                                    parent4.appendRow([child0, child1])
                                parent3.appendRow(parent4)
                        elif key3 in ["MergeSeries"]:
                            for key4 in self.cfg[key1][key2][key3]:
                                val = self.cfg[key1][key2][key3][key4]
                                child0 = QtGui.QStandardItem(key4)
                                child0.setEditable(False)
                                child1 = QtGui.QStandardItem(val)
                                parent3.appendRow([child0, child1])
                        parent2.appendRow(parent3)
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Options", "Drivers"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_er_variable(self):
        """ Remove a variable from the EcosystemRespiration section."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        selected_text = selected_item.text()
        # get the parent of the selected item
        parent = selected_item.parent()
        # don't allow the last ER variable to be deleted
        if parent.rowCount() == 1:
            return
        # remove the row in the EcosystemRespiration section
        parent.removeRow(selected_item.row())
        # get the NetEcosystemExchange section
        for i in range(self.model.rowCount()):
            section = self.model.item(i)
            if section.text() == "NetEcosystemExchange":
                break
        done_it = False
        for i in range(section.rowCount()):
            for j in range(section.child(i).rowCount()):
                if section.child(i).child(j, 1).text() == selected_text:
                    section.removeRow(i)
                    done_it = True
                    break
            if done_it:
                break
        # get the GrossPrimaryProductivity section
        for i in range(self.model.rowCount()):
            section = self.model.item(i)
            if section.text() == "GrossPrimaryProductivity":
                break
        done_it = False
        for i in range(section.rowCount()):
            for j in range(section.child(i).rowCount()):
                if section.child(i).child(j, 1).text() == selected_text:
                    section.removeRow(i)
                    done_it = True
                    break
            if done_it:
                break
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def remove_section(self):
        """ Remove a section from the view."""
        # loop over selected items in the tree
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the root
        root = self.model.invisibleRootItem()
        # remove the row
        root.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_nc2csv_biomet(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_nc2csv_biomet, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_nc2csv_biomet_gui()

    def edit_nc2csv_biomet_gui(self):
        """ Edit an nc2csv_biomet control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "nc2csv_biomet"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"in_name": "", "out_units": "", "out_format": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.csv")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_nc2csv_ecostress(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_nc2csv_ecostress, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_nc2csv_ecostress_gui()

    def edit_nc2csv_ecostress_gui(self):
        """ Edit an nc2csv_ecostress control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "General"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "nc2csv_ecostress"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "General"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["General"]:
                self.context_menu.actionAddItem = QtWidgets.QAction(self)
                self.context_menu.actionAddItem.setText("Add item")
                self.context_menu.addAction(self.context_menu.actionAddItem)
                self.context_menu.actionAddItem.triggered.connect(self.add_general_item)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "General") and (selected_item.column() == 0):
                self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveItem)
                self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"in_name": "", "out_units": "", "out_format": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.csv")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_nc2csv_fluxnet(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_nc2csv_fluxnet, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_nc2csv_fluxnet_gui()

    def edit_nc2csv_fluxnet_gui(self):
        """ Edit an nc2csv_fluxnet control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "General"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "nc2csv_fluxnet"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "General"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
            elif selected_text in ["General"]:
                self.context_menu.actionAddItem = QtWidgets.QAction(self)
                self.context_menu.actionAddItem.setText("Add item")
                self.context_menu.addAction(self.context_menu.actionAddItem)
                self.context_menu.actionAddItem.triggered.connect(self.add_general_item)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
            elif (str(parent.text()) == "General") and (selected_item.column() == 0):
                self.context_menu.actionRemoveItem = QtWidgets.QAction(self)
                self.context_menu.actionRemoveItem.setText("Remove item")
                self.context_menu.addAction(self.context_menu.actionRemoveItem)
                self.context_menu.actionRemoveItem.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"in_name": "", "out_units": "", "out_format": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.csv")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_nc2csv_oneflux(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_nc2csv_oneflux, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_nc2csv_oneflux_gui()

    def edit_nc2csv_oneflux_gui(self):
        """ Edit an nc2csv_oneflux control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "nc2csv_oneflux"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"format": "", "name": "", "units": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_nc2csv_reddyproc(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_nc2csv_reddyproc, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_nc2csv_reddyproc_gui()

    def edit_nc2csv_reddyproc_gui(self):
        """ Edit an nc2csv_reddyproc control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "nc2csv_reddyproc"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        # initialise logical for inserting a separator
        if level == 0:
            if selected_text in ["Variables"]:
                self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                self.context_menu.actionAddVariable.setText("Add variable")
                self.context_menu.addAction(self.context_menu.actionAddVariable)
                self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                elif key in ["out_filename"]:
                    self.context_menu.actionBrowseOutputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseOutputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseOutputFile)
                    self.context_menu.actionBrowseOutputFile.triggered.connect(self.browse_output_file)
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                self.context_menu.actionRemoveOption.setText("Remove variable")
                self.context_menu.addAction(self.context_menu.actionRemoveOption)
                self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
        elif level == 2:
            # sections with 3 levels
            pass

        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))

    def add_general_item(self):
        """ Add a new entry to the [Files] section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        section = idx.model().itemFromIndex(idx)
        dict_to_add = {"New item":""}
        # add the subsection
        self.add_subsection(section, dict_to_add)

    def add_new_variable(self):
        """ Add a new variable to the 'Variables' section."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        parent = idx.model().itemFromIndex(idx)
        dict_to_add = {"in_name": "", "out_units": "", "out_format": ""}
        subsection = QtGui.QStandardItem("New variable")
        self.add_subsection(subsection, dict_to_add)
        parent.appendRow(subsection)
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def add_subsection(self, section, dict_to_add):
        """ Add a subsection to the model."""
        for key in dict_to_add:
            val = str(dict_to_add[key])
            child0 = QtGui.QStandardItem(key)
            child1 = QtGui.QStandardItem(val)
            section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def browse_output_file(self):
        """ Browse for the output data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the top level and sub sections
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              directory=file_path, filter="*.csv")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    def remove_item(self):
        """ Remove an item from the view."""
        # loop over selected items in the tree
        for idx in self.view.selectedIndexes():
            # get the selected item from the index
            selected_item = idx.model().itemFromIndex(idx)
            # get the parent of the selected item
            parent = selected_item.parent()
            # remove the row
            parent.removeRow(selected_item.row())
        self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class edit_cfg_windrose(QtWidgets.QWidget):
    def __init__(self, main_gui):
        super(edit_cfg_windrose, self).__init__()
        self.cfg = copy.deepcopy(main_gui.file)
        self.tabs = main_gui.tabs
        self.edit_windrose_gui()

    #def add_new_variable(self):
        #""" Add a new variable to the 'Variables' section."""
        ## get the index of the selected item
        #idx = self.view.selectedIndexes()[0]
        ## get the selected item from the index
        #parent = idx.model().itemFromIndex(idx)
        #dict_to_add = {"name": ""}
        #subsection = QtGui.QStandardItem("New variable")
        #self.add_subsection(subsection, dict_to_add)
        #parent.appendRow(subsection)
        ## add an asterisk to the tab text to indicate the tab contents have changed
        #self.update_tab_text()

    #def add_subsection(self, section, dict_to_add):
        #""" Add a subsection to the model."""
        #for key in dict_to_add:
            #val = str(dict_to_add[key])
            #child0 = QtGui.QStandardItem(key)
            #child0.setEditable(False)
            #child1 = QtGui.QStandardItem(val)
            #section.appendRow([child0, child1])

    def browse_file_path(self):
        """ Browse for the data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the selected entry text
        file_path = str(idx.data())
        # dialog for new directory
        new_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Choose a folder",
                                                             file_path, QtWidgets.QFileDialog.ShowDirsOnly)
        # quit if cancel button pressed
        if len(str(new_dir)) > 0:
            # make sure the string ends with a path delimiter
            tmp_dir = QtCore.QDir.toNativeSeparators(str(new_dir))
            new_dir = os.path.join(tmp_dir, "")
            # update the model
            parent.child(selected_item.row(), 1).setText(new_dir)

    def browse_input_file(self):
        """ Browse for the input data file path."""
        # get the index of the selected item
        idx = self.view.selectedIndexes()[0]
        # get the selected item from the index
        selected_item = idx.model().itemFromIndex(idx)
        # get the parent of the selected item
        parent = selected_item.parent()
        # get the file_path so it can be used as a default directory
        key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        # dialog for open file
        new_file_path = QtWidgets.QFileDialog.getOpenFileName(caption="Choose an input file ...",
                                                              directory=file_path, filter="*.nc")[0]
        # update the model
        if len(str(new_file_path)) > 0:
            new_file_parts = os.path.split(str(new_file_path))
            parent.child(selected_item.row(), 1).setText(new_file_parts[1])
            ## populate the output file name with a default based on the input file name
            #for n in range(parent.rowCount()):
                #if parent.child(n, 0).text() == "out_filename":
                    #xls_filename = new_file_parts[1].replace(".nc", "_CPD_Barr.xls")
                    #parent.child(n, 1).setText(xls_filename)
        return

    #def browse_output_file(self):
        #""" Browse for the output data file path."""
        ## get the index of the selected item
        #idx = self.view.selectedIndexes()[0]
        ## get the selected item from the index
        #selected_item = idx.model().itemFromIndex(idx)
        ## get the parent of the selected item
        #parent = selected_item.parent()
        ## get the top level and sub sections
        ## get the file_path so it can be used as a default directory
        #key, file_path, found, j = self.get_keyval_by_key_name(parent, "file_path")
        ## dialog for open file
        #new_file_path = QtWidgets.QFileDialog.getSaveFileName(caption="Choose an output file ...",
                                                              #directory=file_path, filter="*.xls")[0]
        ## update the model
        #if len(str(new_file_path)) > 0:
            #new_file_parts = os.path.split(str(new_file_path))
            #parent.child(selected_item.row(), 1).setText(new_file_parts[1])

    def context_menu(self, position):
        """ Right click context menu."""
        # get a menu
        self.context_menu = QtWidgets.QMenu()
        # get the index of the selected item
        if len(self.view.selectedIndexes()) == 0:
            # trap right click when nothing is selected
            return
        idx = self.view.selectedIndexes()[0]
        # get the selected item text
        selected_text = str(idx.data())
        # get the selected item
        selected_item = idx.model().itemFromIndex(idx)
        # get the level of the selected item
        level = self.get_level_selected_item()
        if level == 0:
            if selected_text in ["Variables"]:
                #self.context_menu.actionAddVariable = QtWidgets.QAction(self)
                #self.context_menu.actionAddVariable.setText("Add variable")
                #self.context_menu.addAction(self.context_menu.actionAddVariable)
                #self.context_menu.actionAddVariable.triggered.connect(self.add_new_variable)
                pass
            elif selected_text in ["Options"]:
                pass
            else:
                pass
        elif level == 1:
            # sections with 2 levels
            # get the parent of the selected item
            parent = selected_item.parent()
            if (str(parent.text()) == "Files") and (selected_item.column() == 1):
                key = str(parent.child(selected_item.row(),0).text())
                if key in ["file_path", "plot_path"]:
                    self.context_menu.actionBrowseFilePath = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseFilePath.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseFilePath)
                    self.context_menu.actionBrowseFilePath.triggered.connect(self.browse_file_path)
                elif key in ["in_filename"]:
                    self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    self.context_menu.actionBrowseInputFile.setText("Browse...")
                    self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_input_file)
                #elif key in ["out_filename"]:
                    #self.context_menu.actionBrowseInputFile = QtWidgets.QAction(self)
                    #self.context_menu.actionBrowseInputFile.setText("Browse...")
                    #self.context_menu.addAction(self.context_menu.actionBrowseInputFile)
                    #self.context_menu.actionBrowseInputFile.triggered.connect(self.browse_output_file)
                else:
                    pass
            elif (str(parent.text()) == "Options") and (selected_item.column() == 0):
                pass
            elif (str(parent.text()) == "Variables") and (selected_item.column() == 0):
                #self.context_menu.actionRemoveOption = QtWidgets.QAction(self)
                #self.context_menu.actionRemoveOption.setText("Remove variable")
                #self.context_menu.addAction(self.context_menu.actionRemoveOption)
                #self.context_menu.actionRemoveOption.triggered.connect(self.remove_item)
                pass
            else:
                pass
        else:
            pass
        self.context_menu.exec_(self.view.viewport().mapToGlobal(position))
        return

    def double_click(self):
        """ Save the selected text on double click events."""
        idx = self.view.selectedIndexes()
        self.double_click_selected_text = idx[0].data()
        return

    def edit_windrose_gui(self):
        """ Edit a windrose control file GUI."""
        # get a QTreeView and a standard model
        self.view = myTreeView()
        # get a QStandardItemModel
        self.model = QtGui.QStandardItemModel()
        # add the model to the view
        self.view.setModel(self.model)
        # set the context menu policy
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        # connect the context menu requested signal to appropriate slot
        self.view.customContextMenuRequested.connect(self.context_menu)
        self.view.doubleClicked.connect(self.double_click)
        # do the QTreeView layout
        vbox = QtWidgets.QVBoxLayout()
        vbox.addWidget(self.view)
        self.setLayout(vbox)
        self.setGeometry(300, 300, 600, 400)
        # build the model
        self.get_model_from_data()
        # set the default width for the first column
        self.view.setColumnWidth(0, 200)
        # expand the top level of the sections
        for row in range(self.model.rowCount()):
            idx = self.model.index(row, 0)
            self.view.expand(idx)

    def get_data_from_model(self):
        """ Iterate over the model and get the data."""
        cfg = ConfigObj(indent_type="    ", list_values=False)
        cfg.filename = self.cfg.filename
        cfg["level"] = "windrose"
        model = self.model
        # there must be a way to do this recursively
        for i in range(model.rowCount()):
            section = model.item(i)
            key1 = str(section.text())
            cfg[key1] = {}
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                for j in range(section.rowCount()):
                    key2 = str(section.child(j, 0).text())
                    val2 = str(section.child(j, 1).text())
                    cfg[key1][key2] = val2
            elif key1 in ["Variables"]:
                # sections with 2 levels
                for j in range(section.rowCount()):
                    subsection = section.child(j)
                    key2 = str(subsection.text())
                    cfg[key1][key2] = {}
                    for k in range(subsection.rowCount()):
                        key3 = str(subsection.child(k, 0).text())
                        val3 = str(subsection.child(k, 1).text())
                        cfg[key1][key2][key3] = val3

        return cfg

    def get_keyval_by_key_name(self, section, key):
        """ Get the value from a section based on the key name."""
        found = False
        val_child = ""
        key_child = ""
        for i in range(section.rowCount()):
            if str(section.child(i, 0).text()) == str(key):
                found = True
                key_child = str(section.child(i, 0).text())
                val_child = str(section.child(i, 1).text())
                break
        return key_child, val_child, found, i

    def get_level_selected_item(self):
        """ Get the level of the selected item."""
        indexes = self.view.selectedIndexes()
        level = -1
        if len(indexes) > 0:
            level = 0
            index = indexes[0]
            while index.parent().isValid():
                index = index.parent()
                level += 1
        return level

    def get_model_from_data(self):
        """ Build the data model."""
        self.model.setHorizontalHeaderLabels(['Parameter', 'Value'])
        self.model.itemChanged.connect(self.handleItemChanged)
        # there must be someway outa here, said the Joker to the Thief ...
        self.sections = {}
        for key1 in self.cfg:
            if not self.cfg[key1]:
                continue
            if key1 in ["Files", "Options"]:
                # sections with only 1 level
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                for key2 in self.cfg[key1]:
                    val = self.cfg[key1][key2]
                    child0 = QtGui.QStandardItem(key2)
                    child0.setEditable(False)
                    child1 = QtGui.QStandardItem(val)
                    self.sections[key1].appendRow([child0, child1])
                self.model.appendRow(self.sections[key1])
            elif key1 in ["Variables"]:
                # sections with 2 levels
                self.sections[key1] = QtGui.QStandardItem(key1)
                self.sections[key1].setEditable(False)
                # key2 is the variable name
                for key2 in self.cfg[key1]:
                    parent2 = QtGui.QStandardItem(key2)
                    # key3 is the variable options
                    for key3 in self.cfg[key1][key2]:
                        val = self.cfg[key1][key2][key3]
                        child0 = QtGui.QStandardItem(key3)
                        child0.setEditable(False)
                        child1 = QtGui.QStandardItem(val)
                        parent2.appendRow([child0, child1])
                    self.sections[key1].appendRow(parent2)
                self.model.appendRow(self.sections[key1])

    def get_sibling_names(self):
        idx = self.view.selectedIndexes()[0]
        parent = idx.parent().model().itemFromIndex(idx.parent())
        sibling_names = []
        if parent.hasChildren():
            for i in range(parent.rowCount()):
                sibling_names.append(str(parent.child(i, 0).text()))
        return sibling_names

    def handleItemChanged(self, item):
        """ Handler for when view items are edited."""
        # here we trap attempts by the user to add duplicate entries
        # index of selected item
        idx = self.view.selectedIndexes()[0]
        # selected item from index
        selected_item = idx.model().itemFromIndex(idx)
        # text of selected item, this will be the name of the item the user
        # is trying to add
        selected_text = selected_item.text()
        # parent of the item the user is trying to add
        parent = selected_item.parent()
        # user has done something silly
        if not hasattr(parent, "text"):
            return
        # check parent text to see if this item needs to be checked for duplicates
        if parent.text() in ["Files", "Options", "Variables"]:
            # get the names of the new item's siblings
            sibling_names = self.get_sibling_names()
            # if the user is trying to use the same name as an existing entry there
            # will be entries with this name in the siblings name list
            if len(list(set(sibling_names))) != len(sibling_names):
                # duplicate entries found
                msg = "'" + selected_text + "' already exists in " + parent.text() + " section"
                # put up a message box to tell the user
                MsgBox_Continue(msg)
                # change the item name back to the original
                selected_item.setText(self.double_click_selected_text)
                return
        # update the control file contents
        self.cfg = self.get_data_from_model()
        # add an asterisk to the tab text to indicate the tab contents have changed
        self.update_tab_text()

    #def remove_item(self):
        #""" Remove an item from the view."""
        ## loop over selected items in the tree
        #for idx in self.view.selectedIndexes():
            ## get the selected item from the index
            #selected_item = idx.model().itemFromIndex(idx)
            ## get the parent of the selected item
            #parent = selected_item.parent()
            ## remove the row
            #parent.removeRow(selected_item.row())
        #self.update_tab_text()

    def update_tab_text(self):
        """ Add an asterisk to the tab title text to indicate tab contents have changed."""
        # add an asterisk to the tab text to indicate the tab contents have changed
        tab_text = str(self.tabs.tabText(self.tabs.tab_index_current))
        if "*" not in tab_text:
            self.tabs.setTabText(self.tabs.tab_index_current, tab_text+"*")

class NetCDFReadWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)
    error = QtCore.pyqtSignal(str)
    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.nc_uri = os.path.join(self.cfg["Files"]["file_path"],
                                   self.cfg["Files"]["in_filename"])

    def run(self):
        try:
            # Open the netCDF file
            #dataset = nc.Dataset(self.file_path, 'r')
            self.ds = pfp_io.NetCDFRead(self.nc_uri)
            # Signal that we are done and pass the dataset object
            self.finished.emit(self.ds)
        except Exception as e:
            self.error.emit(str(e))

class pfp_l4_ui(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(pfp_l4_ui, self).__init__(parent)
        self.resize(400, 236)
        self.setWindowTitle("Gap fill (alternate)")
        self.RunButton = QtWidgets.QPushButton(self)
        self.RunButton.setGeometry(QtCore.QRect(20, 200, 93, 27))
        self.RunButton.setText("Run")
        self.DoneButton = QtWidgets.QPushButton(self)
        self.DoneButton.setGeometry(QtCore.QRect(150, 200, 93, 27))
        self.DoneButton.setText("Done")
        self.QuitButton = QtWidgets.QPushButton(self)
        self.QuitButton.setGeometry(QtCore.QRect(270, 200, 93, 27))
        self.QuitButton.setText("Quit")
        self.checkBox_ShowPlots = QtWidgets.QCheckBox(self)
        self.checkBox_ShowPlots.setGeometry(QtCore.QRect(20, 170, 94, 22))
        self.checkBox_ShowPlots.setText("Show plots")
        self.checkBox_ShowPlots.setChecked(True)
        self.checkBox_PlotAll = QtWidgets.QCheckBox(self)
        self.checkBox_PlotAll.setGeometry(QtCore.QRect(150, 170, 94, 22))
        self.checkBox_PlotAll.setText("Plot all")
        self.checkBox_Overwrite = QtWidgets.QCheckBox(self)
        self.checkBox_Overwrite.setGeometry(QtCore.QRect(270, 170, 94, 22))
        self.checkBox_Overwrite.setText("Overwrite")

        self.radioButton_NumberMonths = QtWidgets.QRadioButton(self)
        self.radioButton_NumberMonths.setGeometry(QtCore.QRect(20, 140, 110, 22))
        self.radioButton_NumberMonths.setText("Months")
        self.radioButton_NumberMonths.setChecked(True)
        self.radioButton_NumberDays = QtWidgets.QRadioButton(self)
        self.radioButton_NumberDays.setGeometry(QtCore.QRect(130, 140, 110, 22))
        self.radioButton_NumberDays.setText("Days")
        self.radioButton_Manual = QtWidgets.QRadioButton(self)
        self.radioButton_Manual.setGeometry(QtCore.QRect(20, 110, 110, 25))
        self.radioButton_Manual.setText("Manual")
        self.radioButtons = QtWidgets.QButtonGroup(self)
        self.radioButtons.addButton(self.radioButton_NumberMonths)
        self.radioButtons.addButton(self.radioButton_NumberDays)
        self.radioButtons.addButton(self.radioButton_Manual)

        self.lineEdit_NumberMonths = QtWidgets.QLineEdit(self)
        self.lineEdit_NumberMonths.setGeometry(QtCore.QRect(90, 140, 30, 25))
        self.lineEdit_NumberMonths.setText("3")
        self.lineEdit_NumberDays = QtWidgets.QLineEdit(self)
        self.lineEdit_NumberDays.setGeometry(QtCore.QRect(220, 140, 30, 25))
        self.lineEdit_NumberDays.setText("90")
        self.checkBox_AutoComplete = QtWidgets.QCheckBox(self)
        self.checkBox_AutoComplete.setGeometry(QtCore.QRect(270, 140, 120, 25))
        self.checkBox_AutoComplete.setChecked(True)
        self.checkBox_AutoComplete.setText("Auto complete")
        self.lineEdit_MinPercent = QtWidgets.QLineEdit(self)
        self.lineEdit_MinPercent.setGeometry(QtCore.QRect(220, 110, 30, 25))
        self.lineEdit_MinPercent.setText("50")
        self.label_MinPercent = QtWidgets.QLabel(self)
        self.label_MinPercent.setGeometry(QtCore.QRect(140, 110, 80, 25))
        self.label_MinPercent.setText("Min pts (%)")
        self.lineEdit_EndDate = QtWidgets.QLineEdit(self)
        self.lineEdit_EndDate.setGeometry(QtCore.QRect(220, 77, 161, 25))
        self.label_EndDate = QtWidgets.QLabel(self)
        self.label_EndDate.setGeometry(QtCore.QRect(30, 80, 171, 20))
        self.label_EndDate.setText("End date (YYYY-MM-DD)")
        self.lineEdit_StartDate = QtWidgets.QLineEdit(self)
        self.lineEdit_StartDate.setGeometry(QtCore.QRect(220, 47, 161, 25))
        self.label_StartDate = QtWidgets.QLabel(self)
        self.label_StartDate.setGeometry(QtCore.QRect(30, 47, 171, 20))
        self.label_StartDate.setText("Start date (YYYY-MM-DD)")
        self.label_DataStartDate = QtWidgets.QLabel(self)
        self.label_DataStartDate.setGeometry(QtCore.QRect(48, 6, 111, 17))
        self.label_DataEndDate = QtWidgets.QLabel(self)
        self.label_DataEndDate.setGeometry(QtCore.QRect(244, 6, 101, 17))
        self.label_DataStartDate_value = QtWidgets.QLabel(self)
        self.label_DataStartDate_value.setGeometry(QtCore.QRect(33, 26, 151, 20))
        self.label_DataEndDate_value = QtWidgets.QLabel(self)
        self.label_DataEndDate_value.setGeometry(QtCore.QRect(220, 26, 141, 17))
        self.label_DataStartDate.setText("Data start date")
        self.label_DataEndDate.setText("Data end date")
        self.label_DataStartDate_value.setText("YYYY-MM-DD HH:mm")
        self.label_DataEndDate_value.setText("YYYY-MM-DD HH:mm")
        # connect signals to slots
        self.RunButton.clicked.connect(lambda:pfp_gfALT.gfalternate_run_interactive(self))
        self.DoneButton.clicked.connect(lambda:pfp_gfALT.gfalternate_done(self))
        self.QuitButton.clicked.connect(lambda:pfp_gfALT.gfalternate_quit(self))

class solo_gui(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(solo_gui, self).__init__(parent)
        self.resize(400, 265)
        # component sizes and positions
        row_height = 25
        label_width = 145
        label_height = 20
        lineedit_long_width = 160
        lineedit_short_width = 30
        lineedit_height = 20
        radiobutton_width = 110
        radiobutton_height = 20
        checkbox_width = 95
        checkbox_height = 20
        button_width = 90
        button_height = 25
        # first row; Date start and end headings
        row1_y = 5
        self.label_DataStartDate = QtWidgets.QLabel(self)
        self.label_DataStartDate.setGeometry(QtCore.QRect(48, row1_y, label_width, label_height))
        self.label_DataEndDate = QtWidgets.QLabel(self)
        self.label_DataEndDate.setGeometry(QtCore.QRect(244, row1_y, label_width, label_height))
        # second row; Date start and end values
        row2_y = row1_y + row_height
        self.label_DataStartDate_value = QtWidgets.QLabel(self)
        self.label_DataStartDate_value.setGeometry(QtCore.QRect(33, row2_y, label_width, label_height))
        self.label_DataEndDate_value = QtWidgets.QLabel(self)
        self.label_DataEndDate_value.setGeometry(QtCore.QRect(220, row2_y, label_width, label_height))
        self.label_DataStartDate.setText("Data start date")
        self.label_DataEndDate.setText("Data end date")
        self.label_DataStartDate_value.setText("YYYY-MM-DD HH:mm")
        self.label_DataEndDate_value.setText("YYYY-MM-DD HH:mm")
        # third row; Nodes etc
        row3_y = row2_y + row_height
        self.label_Nodes = QtWidgets.QLabel(self)
        self.label_Nodes.setGeometry(QtCore.QRect(20, row3_y, 60, label_height))
        self.label_Nodes.setText("Nodes")
        self.lineEdit_Nodes = QtWidgets.QLineEdit(self)
        self.lineEdit_Nodes.setGeometry(QtCore.QRect(80, row3_y, 50, lineedit_height))
        self.lineEdit_Nodes.setText("10")
        self.label_Training = QtWidgets.QLabel(self)
        self.label_Training.setGeometry(QtCore.QRect(150, row3_y, 50, label_height))
        self.label_Training.setText("Training")
        self.lineEdit_Training = QtWidgets.QLineEdit(self)
        self.lineEdit_Training.setGeometry(QtCore.QRect(210, row3_y, 50, lineedit_height))
        self.lineEdit_Training.setText("500")
        self.label_NdaFactor = QtWidgets.QLabel(self)
        self.label_NdaFactor.setGeometry(QtCore.QRect(270, row3_y, 70, label_height))
        self.label_NdaFactor.setText("Nda factor")
        self.lineEdit_NdaFactor = QtWidgets.QLineEdit(self)
        self.lineEdit_NdaFactor.setGeometry(QtCore.QRect(340, row3_y, 50, lineedit_height))
        self.lineEdit_NdaFactor.setText("5")
        # fourth row; Learning, Iterations
        row4_y = row3_y + row_height
        self.label_Learning = QtWidgets.QLabel(self)
        self.label_Learning.setGeometry(QtCore.QRect(140, row4_y, 60, label_height))
        self.label_Learning.setText("Learning")
        self.lineEdit_Learning = QtWidgets.QLineEdit(self)
        self.lineEdit_Learning.setGeometry(QtCore.QRect(210, row4_y, 50, lineedit_height))
        self.lineEdit_Learning.setText("0.001")
        self.label_Iterations = QtWidgets.QLabel(self)
        self.label_Iterations.setGeometry(QtCore.QRect(270, row4_y, 70, label_height))
        self.label_Iterations.setText("Iterations")
        self.lineEdit_Iterations = QtWidgets.QLineEdit(self)
        self.lineEdit_Iterations.setGeometry(QtCore.QRect(340, row4_y, 50, lineedit_height))
        self.lineEdit_Iterations.setText("500")
        # fifth row; start date line edit box
        row5_y = row4_y + row_height
        self.label_StartDate = QtWidgets.QLabel(self)
        self.label_StartDate.setGeometry(QtCore.QRect(30, row5_y, lineedit_long_width, lineedit_height))
        self.label_StartDate.setText("Start date (YYYY-MM-DD)")
        self.lineEdit_StartDate = QtWidgets.QLineEdit(self)
        self.lineEdit_StartDate.setGeometry(QtCore.QRect(220, row5_y, lineedit_long_width, lineedit_height))
        # sixth row; end date line edit box
        row6_y = row5_y + row_height
        self.label_EndDate = QtWidgets.QLabel(self)
        self.label_EndDate.setGeometry(QtCore.QRect(30, row6_y, lineedit_long_width, lineedit_height))
        self.label_EndDate.setText("End date (YYYY-MM-DD)")
        self.lineEdit_EndDate = QtWidgets.QLineEdit(self)
        self.lineEdit_EndDate.setGeometry(QtCore.QRect(220, row6_y, lineedit_long_width, lineedit_height))
        # seventh row
        row7_y = row6_y + row_height
        self.radioButton_Manual = QtWidgets.QRadioButton(self)
        self.radioButton_Manual.setGeometry(QtCore.QRect(20, row7_y, radiobutton_width, radiobutton_height))
        self.radioButton_Manual.setText("Manual")
        self.lineEdit_MinPercent = QtWidgets.QLineEdit(self)
        self.lineEdit_MinPercent.setGeometry(QtCore.QRect(220, row7_y, 30, lineedit_height))
        self.lineEdit_MinPercent.setText("25")
        self.label_MinPercent = QtWidgets.QLabel(self)
        self.label_MinPercent.setGeometry(QtCore.QRect(140, row7_y, 80, label_height))
        self.label_MinPercent.setText("Min pts (%)")
        # eighth row; Months, Days, Auto-complete
        row8_y = row7_y + row_height
        self.radioButton_NumberMonths = QtWidgets.QRadioButton(self)
        self.radioButton_NumberMonths.setGeometry(QtCore.QRect(20, row8_y, radiobutton_width, radiobutton_height))
        self.radioButton_NumberMonths.setText("Months")
        self.lineEdit_NumberMonths = QtWidgets.QLineEdit(self)
        self.lineEdit_NumberMonths.setGeometry(QtCore.QRect(90, row8_y, lineedit_short_width, lineedit_height))
        self.radioButton_NumberDays = QtWidgets.QRadioButton(self)
        self.radioButton_NumberDays.setGeometry(QtCore.QRect(150, row8_y, radiobutton_width, radiobutton_height))
        self.radioButton_NumberDays.setText("Days")
        self.lineEdit_NumberDays = QtWidgets.QLineEdit(self)
        self.lineEdit_NumberDays.setGeometry(QtCore.QRect(220, row8_y, lineedit_short_width, lineedit_height))
        self.lineEdit_NumberDays.setText("60")
        self.checkBox_AutoComplete = QtWidgets.QCheckBox(self)
        self.checkBox_AutoComplete.setGeometry(QtCore.QRect(270, row8_y, radiobutton_width+10, radiobutton_height))
        self.checkBox_AutoComplete.setText("Auto complete")
        # define the radio button group
        self.radioButtons = QtWidgets.QButtonGroup(self)
        self.radioButtons.addButton(self.radioButton_NumberMonths)
        self.radioButtons.addButton(self.radioButton_NumberDays)
        self.radioButtons.addButton(self.radioButton_Manual)
        # ninth row; Show plots, Plot all and Overwrite checkboxes
        row9_y = row8_y + row_height
        self.checkBox_ShowPlots = QtWidgets.QCheckBox(self)
        self.checkBox_ShowPlots.setGeometry(QtCore.QRect(20, row9_y, checkbox_width, checkbox_height))
        self.checkBox_ShowPlots.setText("Show plots")
        self.checkBox_ShowPlots.setChecked(True)
        self.checkBox_PlotAll = QtWidgets.QCheckBox(self)
        self.checkBox_PlotAll.setGeometry(QtCore.QRect(150, row9_y, checkbox_width, checkbox_height))
        self.checkBox_PlotAll.setText("Plot all")
        self.checkBox_Overwrite = QtWidgets.QCheckBox(self)
        self.checkBox_Overwrite.setGeometry(QtCore.QRect(270, row9_y, checkbox_width, checkbox_height))
        self.checkBox_Overwrite.setText("Overwrite")
        # tenth (bottom) row; Run, Done and Quit buttons
        row10_y = row9_y + row_height
        self.RunButton = QtWidgets.QPushButton(self)
        self.RunButton.setGeometry(QtCore.QRect(20, row10_y, button_width, button_height))
        self.RunButton.setText("Run")
        self.DoneButton = QtWidgets.QPushButton(self)
        self.DoneButton.setGeometry(QtCore.QRect(150, row10_y, button_width, button_height))
        self.DoneButton.setText("Done")
        self.QuitButton = QtWidgets.QPushButton(self)
        self.QuitButton.setGeometry(QtCore.QRect(270, row10_y, button_width, button_height))
        self.QuitButton.setText("Quit")
        # connect the "Run", "Done" and "Quit" buttons to their slots
        self.RunButton.clicked.connect(self.call_gui_run)
        self.DoneButton.clicked.connect(self.call_gui_done)
        self.QuitButton.clicked.connect(self.call_gui_quit)

    def call_gui_run(self):
        try:
            pfp_gfSOLO.gfSOLO_run_interactive(self)
        except Exception:
            msg = "Error occurred during SOLO processing "
            logger.error(msg)
            error_message = traceback.format_exc()
            logger.error(error_message)
            pfp_gfSOLO.gfSOLO_quit(self)

    def call_gui_quit(self):
        pfp_gfSOLO.gfSOLO_quit(self)

    def call_gui_done(self):
        pfp_gfSOLO.gfSOLO_done(self)
