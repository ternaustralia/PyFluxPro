#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 15 13:53:16 2018

@author: ian
"""
import logging
import os

import datetime as dt
from lmfit import Model
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

#------------------------------------------------------------------------------
# Init
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
class partition(object):
    """
    Class for fitting of respiration parameters and estimation of respiration
    WARNING - NO FILTERING OR DATA INTEGRITY CHECKS APPLIED HERE!!!
    To do - add separate method for integrity checks on user-supplied args

    Args:
        * dataframe (pd.dataframe): containing a minimum of temperature, solar
          radiation, VPD and CO2 flux.
    Kwargs:
        * names_dict (dict): maps the variable names used in the dataset to
          common names (keys must be 'air_temperature', 'soil_temperature',
          'insolation', 'Cflux'); if None, defaults to the internal
          specification, which works for PyFluxPro.
        * weights (str, or list of ints / floats): if str, must be either
          'air' or 'soil', which determines which temperature series is used
          for the fit; if list is supplied, it must have two numbers (ints or
          floats), which are used for the weighting in the ratio air:soil
          e.g. choice of [3, 1] would cause weighting of 3:1 in favour of air
          temperature, or e.g. [1, 3] would result in the reverse.
    """
    def __init__(self, dataframe, xl_writer, l6_info, names_dict = None):
        self.interval = int(l6_info["Global"]["time_step"])
        assert self.interval % 30 == 0
        self.convert_to_photons = l6_info["Options"]["convert_to_photons"]
        if self.convert_to_photons:
            self.noct_threshold = l6_info["Options"]["noct_threshold"] * 0.46 * 4.6
        else:
            self.noct_threshold = l6_info["Options"]["noct_threshold"]
        self._fit_daytime_rb = l6_info["Options"]["fit_daytime_rb"]
        self.l6_info = l6_info

        if not names_dict:
            self.external_names = self._define_default_external_names()
        else:
            self.external_names = names_dict
        self.internal_names = self._define_default_internal_names()

        self.df = self._make_formatted_df(dataframe)
        self.xl_writer = xl_writer
        self.results = {"E0": {}}
        self.prior_parameter_estimates()
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    # Methods
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def day_params(self, date, Eo, window_size, priors_dict):

        def model_fit(these_params):
            return model.fit(df.NEE,
                             par_series = df.PPFD, vpd_series = df.VPD,
                             t_series = df.TC, params = these_params)

        if self._fit_daytime_rb:
            rb_prior = priors_dict['rb']
        else:
            rb_prior = self.nocturnal_params(date, Eo, window_size,
                                             priors_dict)['rb']
        beta_prior = priors_dict['beta']
        df = self.get_subset(date, size = window_size, mode = 'day')
        if ((len(df) > 0) and (self.l6_info["Options"]["plot_raw_data"])):
            self.plot_LL_data(df)
        try:
            if not len(df) > 4:
                raise RuntimeError('insufficient data for fit')
            f = _NEE_model
            model = Model(f, independent_vars = ['par_series', 'vpd_series',
                                                 't_series'])
            params = model.make_params(rb = rb_prior, Eo = Eo,
                                       alpha = priors_dict['alpha'],
                                       beta = beta_prior,
                                       k = priors_dict['k'])
            rmse_list, params_list = [], []
            for this_beta in [beta_prior, beta_prior / 2, beta_prior * 2]:
                params['beta'].value = this_beta
                params['Eo'].vary = False
                params['rb'].vary = self._fit_daytime_rb
                result = model_fit(these_params = params)
                if result.params['rb'] < 0:
                    raise RuntimeError('rb parameter out of range')
                if not 0 <= result.params['k'].value <= 10:
                    params['k'].value = priors_dict['k']
                    params['k'].vary = False
                    result = model_fit(these_params = params)
                if not -0.22 <= result.params['alpha'].value <= 0:
                    params['alpha'].value = priors_dict['alpha']
                    params['alpha'].vary = False
                    result = model_fit(these_params = params)
                if not -100 <= result.params['beta'].value <= 0:
                    raise RuntimeError('beta parameter out of range')
                rmse_list.append(np.sqrt(((df.NEE - result.best_fit)**2).sum()))
                params_list.append(result.best_values)
            idx = rmse_list.index(min(rmse_list))
            priors_dict['alpha'] = result.best_values['alpha']
            return params_list[idx]
        except RuntimeError as e:
            priors_dict['alpha'] = 0
            raise RuntimeError(e)
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    """Defines the internal names used by the algorithm"""

    def _define_default_internal_names(self):

        #return {'Cflux': 'NEE',
                #'air_temperature': 'Ta',
                #'soil_temperature': 'Ts',
                #'insolation': 'PPFD',
                #'vapour_pressure_deficit': 'VPD'}
        # PRI 20220720 removed Ts
        #return {'Cflux': 'NEE',
                #'air_temperature': 'Ta',
                #'insolation': 'PPFD',
                #'vapour_pressure_deficit': 'VPD'}
        # PRI 20220720 added Sws
        return {'ecosystem_respiration': 'ER',
                'net_ecosystem_exchange': 'NEE',
                'air_temperature': 'Ta',
                'soil_temperature': 'Ts',
                'insolation': 'PPFD',
                'vapour_pressure_deficit': 'VPD',
                'soil moisture': 'Sws'}
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    """Maps the variable names in the external dataset to generic variable
       references"""

    def _define_default_external_names(self):

        #return {'Cflux': 'Fco2',
                #'air_temperature': 'Ta',
                #'soil_temperature': 'Ts',
                #'insolation': 'Fsd',
                #'vapour_pressure_deficit': 'VPD'}
        # PRI 20220720 removed Ts
        #return {'Cflux': 'Fco2',
                #'air_temperature': 'Ta',
                #'insolation': 'Fsd',
                #'vapour_pressure_deficit': 'VPD'}
        # PRI 20220720 added Sws, changed Fco2 to ER
        return {'ecosystem_respiration': 'ER',
                'net_ecosystem_exchange': 'Fco2',
                'air_temperature': 'Ta',
                'soil_temperature': 'Ts',
                'insolation': 'Fsd',
                'vapour_pressure_deficit': 'VPD',
                'soil moisture': 'Sws'}
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    #def estimate_Eo(self, window_size = 15, window_step = 5, get_stats = False):
    def estimate_Eo(self, get_stats = False):

        """Estimate the activation energy type parameter for the L&T Arrhenius
           style equation using nocturnal data"""

        Eo_list = []
        called_by = self.l6_info["Options"]["called_by"]
        output = self.l6_info["Options"]["output"]
        window_size = int(self.l6_info[called_by]["outputs"][output]["window_size_days"])
        window_step = int(self.l6_info[called_by]["outputs"][output]["step_size_days"])
        for n, date in enumerate(self.make_date_iterator(window_size, window_step)):
            self.results["E0"][n] = {"start": date, "end": date,
                                     "num": 0, "T range": -9999,
                                     "rb_av": -9999, "rb_se": -9999,
                                     "E0_av": -9999, "E0_se": -9999,
                                     "E0_av_qc": -9999, "E0_se_qc": -9999}
            df = self.get_subset(date, size = window_size, mode = 'night')
            self.results["E0"][n]["start"] = self.subset_start
            self.results["E0"][n]["end"] = self.subset_end
            if len(df) == 0:
                continue
            if self.l6_info["Options"]["plot_raw_data"]:
                self.plot_E0_data(df)
            self.results["E0"][n]["num"] = len(df)
            self.results["E0"][n]["T range"] = df.TC.max() - df.TC.min()
            if ((len(df) > 6) and (df.TC.max() - df.TC.min() >= 5)):
                f = _Lloyd_and_Taylor
                ER = df.ER.values
                TC = df.TC.values
                model = Model(f, independent_vars = ['t_series'])
                params = model.make_params(rb = 1, Eo = self.priors['Eo'])
                result = model.fit(ER, t_series=TC, params=params)
                self.results["E0"][n]["E0_av"] = result.params['Eo'].value
                self.results["E0"][n]["rb_av"] = result.params['rb'].value
                if result.success:
                    # confidence interval may fail so we wrap it in a try...except block
                    try:
                        #E0_se = (result.conf_interval()['Eo'][4][1] -
                                 #result.conf_interval()['Eo'][2][1]) / 2
                        #rb_se = (result.conf_interval()['rb'][4][1] -
                                 #result.conf_interval()['rb'][2][1]) / 2
                        #self.results["E0"][n]["E0_se"] = E0_se
                        E0_se = result.params["Eo"].stderr
                        rb_se = result.params["rb"].stderr
                        self.results["E0"][n]["rb_se"] = rb_se
                        if ((50 < result.params['Eo'].value < 400) and
                            (E0_se < result.params['Eo'].value / 2.0)):
                            self.results["E0"][n]["E0_av_qc"] = result.params['Eo'].value
                            self.results["E0"][n]["E0_se_qc"] = E0_se
                            Eo_list.append([result.params['Eo'].value, E0_se])
                    except Exception as e:
                        logger.warning("*****")
                        start = np.datetime_as_string(self.results["E0"][n]["start"], unit='D')
                        end = np.datetime_as_string(self.results["E0"][n]["end"], unit='D')
                        msg = "The period " + start + " to " + end
                        msg += " generated the following message:"
                        logger.warning(msg)
                        logger.warning(e)
                        logger.warning("*****")
                        continue
                else:
                    continue
            else:
                continue
        # check to see if the raw LL plot was produced by checking the LL_fignum attribute
        if hasattr(self, "LL_fignum"):
            # check to see if a figure with this number exists
            if plt.fignum_exists(self.LL_fignum):
                # close the plot
                plt.close(self.LL_fignum)
                # delete the attribute
                delattr(self, "LL_fignum")
        E0_results = pd.DataFrame.from_dict(self.results["E0"], orient="index")
        E0_results.to_excel(excel_writer =self.xl_writer, sheet_name = "E0 results")
        if len(Eo_list) == 0:
            msg = "***** Could not find any valid estimates of E0, exiting..."
            logger.warning(msg)
            # remove this variable from those output in L6 summary
            del self.l6_info[called_by]["outputs"][output]
            Eo = None
        else:
            msg = " Found {} valid estimates of Eo (out of {} windows)".format(str(len(Eo_list)), str(n))
            logger.info(msg)
            Eo_array = np.array(Eo_list)
            Eo = ((Eo_array[:, 0] / (Eo_array[:, 1])).sum() /
                  (1 / Eo_array[:, 1]).sum())
            if not 50 < Eo < 400:
                # E0 is outside the plausible range
                msg = "***** E0 value {} outside range (50-400)".format(str(round(Eo, 2)))
                logger.warning(msg)
                # remove this variable from those output in L6 summary
                del self.l6_info[called_by]["outputs"][output]
                Eo = None
        return Eo
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def estimate_er_time_series(self, params_df = False):

        if not isinstance(params_df, pd.core.frame.DataFrame):
            params_df = self.estimate_parameters(mode = 'night')
        resp_series = pd.Series()
        for date in params_df.index:
            params = params_df.loc[date]
            str_date = dt.datetime.strftime(date, '%Y-%m-%d')
            data = self.df.loc[str_date, 'TC']
            rs = _Lloyd_and_Taylor(t_series=data, rb=params.rb, Eo=params.Eo)
            resp_series = pd.concat([resp_series, rs])
        return resp_series
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def estimate_gpp_time_series(self, params_df = False):

        if not isinstance(params_df, pd.core.frame.DataFrame):
            params_df = self.estimate_parameters(mode = 'day')
        gpp_series = pd.Series()
        for date in params_df.index:
            params = params_df.loc[date]
            str_date = dt.datetime.strftime(date, '%Y-%m-%d')
            data = self.df.loc[str_date, ['PPFD', 'VPD']]
            gpp_series = gpp_series.append(_rectangular_hyperbola
                                           (par_series = data.PPFD,
                                            vpd_series = data.VPD,
                                            alpha = params.alpha,
                                            beta = params.beta,
                                            k = params.k))

        return gpp_series
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def estimate_nee_time_series(self, params_df = False,
                                 splice_with_obs = False):
        return (self.estimate_gpp_time_series(params_df) +
                self.estimate_er_time_series(params_df))
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def estimate_parameters(self, mode, Eo = None, window_size = 4,
                            window_step = 4):

        func = self._get_func()[mode]
        if not Eo:
            Eo = self.estimate_Eo()
        # return if E0 not found
        if Eo is None:
            return None
        result_list, date_list = [], []
        #msg = "Processing the following dates ({} mode): ".format(mode)
        msg = " Processing date ranges using {} mode: ".format(mode)
        logger.info(msg)
        for date in self.make_date_iterator(window_size, window_step):
            #msg = str(date.date())
            #logger.info(msg)
            try:
                result_list.append(func(date, Eo, window_size, self.priors))
                date_list.append(date)
            except RuntimeError as e:
                # not sure we should let exceptions pass quietly ...
                #msg = '- {}'.format(e)
                #logger.error(msg)
                continue
        # check to see if the raw LL plot was produced by checking the LL_fignum attribute
        if hasattr(self, "LL_fignum"):
            # check to see if a figure with this number exists
            if plt.fignum_exists(self.LL_fignum):
                # close the plot
                plt.close(self.LL_fignum)
                # delete the attribute
                delattr(self, "LL_fignum")
        full_date_list = np.unique(self.df.index.date)
        flag = pd.Series(0, index = date_list, name = 'Fill_flag')
        flag = flag.reindex(pd.date_range(full_date_list[0], full_date_list[-1],
                                          freq='D'))
        flag.fillna(1, inplace = True)
        out_df = pd.DataFrame(result_list, index = date_list)
        out_df = out_df.resample('D').interpolate()
        out_df = out_df.reindex(np.unique(self.df.index.date))
        out_df.bfill(inplace = True)
        out_df.ffill( inplace = True)
        return out_df.join(flag)
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def _get_func(self):

        return {'night': self.nocturnal_params, 'day': self.day_params}
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def get_subset(self, date, size, mode):
        """ Returns a subset of the dataframe using a start date and window size."""
        ref_date = date + dt.timedelta(0.5)
        date_tuple = (ref_date - dt.timedelta(size / 2.0 -
                                              self.interval / 1440.0),
                      ref_date + dt.timedelta(size / 2.0))
        if mode == "day":
            sub_labels = ["NEE", "PPFD", "VPD", "TC"]
        elif mode == "night":
            sub_labels = ["ER", "TC"]
        else:
            msg = " These are not the droids you're looking for ..."
            logger.error(msg)
            raise RuntimeError(msg)
        sub_df = self.df.loc[date_tuple[0]: date_tuple[1], sub_labels]
        self.subset_start = sub_df.index.values[0]
        self.subset_end = sub_df.index.values[-1]
        sub_df = sub_df.dropna()
        return sub_df
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def make_date_iterator(self, size, step):
        """ Returns a pandas date range with a frequency of step_size."""
        start_date = (self.df.index[0].to_pydatetime().date() +
                      dt.timedelta(size / 2))
        end_date = self.df.index[-1].to_pydatetime().date()
        return pd.date_range(start_date, end_date,
                             freq = '{}D'.format(str(step)))
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def _make_formatted_df(self, df):
        """Update this to check for soil temperature - if not there, default
           to Ta"""
        sub_df = _rename_df(df, self.external_names, self.internal_names)
        if self.convert_to_photons and "PPFD" in list(sub_df):
            sub_df['PPFD'] = sub_df['PPFD'] * 0.46 * 4.6
        called_by = self.l6_info["Options"]["called_by"]
        output = self.l6_info["Options"]["output"]
        # get a list of temperature drivers
        drivers = [d for d in self.l6_info[called_by]["outputs"][output]["drivers"]
                   if d[0:2] in ["Ta", "Ts"]]
        if len(drivers) == 1:
            s = sub_df[drivers[0]].copy()
        elif len(drivers) == 2:
            weighting = self.l6_info[called_by]["outputs"][output]["weighting"]
            s = (sub_df[drivers[0]] * weighting[0] +
                 sub_df[drivers[1]] * weighting[1]) / sum(weighting)
        else:
            msg = " More than 2 drivers specified (" + str(len(drivers)) + ")"
            logger.error(msg)
            raise RuntimeError(msg)
        s.name = "TC"
        return sub_df.join(s)
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def nocturnal_params(self, date, Eo, window_size, priors_dict):

        df = self.get_subset(date, size = window_size, mode = 'night')
        if not len(df) > 2: raise RuntimeError('insufficient data for fit')
        f = _Lloyd_and_Taylor
        model = Model(f, independent_vars=['t_series'])
        params = model.make_params(rb=priors_dict['rb'], Eo=Eo)
        params['Eo'].vary = False
        result = model.fit(df.ER, t_series=df.TC, params=params)
        if result.params['rb'].value < 0:
            raise RuntimeError('rb parameter out of range')
        return result.best_values
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def plot_er(self, date, window_size = 15, Eo = None):

        state = self._fit_daytime_rb
        df = self.get_subset(date, size = window_size, mode = 'night')
        assert len(df) > 0
        if not Eo: Eo = self.estimate_Eo()
        results = {}
        try:
            results['night'] = self.nocturnal_params(date, Eo, window_size, self.priors)['rb']
        except RuntimeError as e:
            msg = "Fit of nocturnal rb failed with the following message {}".format(e)
            logger.error(msg)
        try:
            self._fit_daytime_rb = True
            results['day'] = self.day_params(date, Eo, window_size, self.priors)['rb']
        except RuntimeError as e:
            msg = "Fit of daytime rb failed with the following message {}".format(e)
            logger.error(msg)
        self._fit_daytime_rb = state
        fig, ax = plt.subplots(1, 1, figsize = (14, 8))
        fig.patch.set_facecolor('white')
        ax.axhline(0, color = 'black')
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        ax.tick_params(axis = 'y', labelsize = 14)
        ax.tick_params(axis = 'x', labelsize = 14)
        ax.set_title(dt.datetime.strftime(date, '%Y-%m-%d'), fontsize = 18)
        ax.set_xlabel('$Temperature (degC)', fontsize = 18)
        ax.set_ylabel('$NEE (umol/m^2/s)', fontsize = 18)
        labels_dict = {'night': 'Night Eo and rb', 'day': 'Night Eo, day rb'}
        styles_dict = {'night': '--', 'day': ':'}
        ax.plot(df.TC, df.NEE, color = 'None', marker = 'o',
                mfc = 'grey', mec = 'black', ms = 8, alpha = 0.5,
                label = 'Observations')
        df['TC_alt'] = np.linspace(df.TC.min(), df.TC.max(), len(df))
        for key in results.keys():
            s = _Lloyd_and_Taylor(t_series = df.TC_alt, rb = results[key],
                                  Eo = Eo)
            ax.plot(df.TC_alt, s, color = 'black', ls = styles_dict[key],
                    label = labels_dict[key])
        ax.legend(loc = [0.05, 0.8], fontsize = 12)
        return fig
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def plot_nee(self, date, window_size = 15, Eo = None):

        state = self._fit_daytime_rb
        df = self.get_subset(date, size = window_size, mode = 'day')
        assert len(df) > 0
        if not Eo: Eo = self.estimate_Eo()
        results_dict = {}
        try:
            self._fit_daytime_rb = False
            results_dict['night'] = self.day_params(date, Eo, window_size, self.priors)
        except RuntimeError as e:
            msg ="Fit of daytime parameters and nocturnal rb failed with the following message {}".format(e)
            logger.error(msg)
        try:
            self._fit_daytime_rb = True
            results_dict['day'] = self.day_params(date, Eo, window_size, self.priors)
        except RuntimeError as e:
            msg = "Fit of daytime parameters and rb failed with the following message {}".format(e)
            logger.error(msg)
        self._fit_daytime_rb = state
        fig, ax = plt.subplots(1, 1, figsize = (14, 8))
        fig.patch.set_facecolor('white')
        ax.axhline(0, color = 'black')
        ax.set_xlim([0, df.PPFD.max() * 1.05])
        ax.spines['right'].set_visible(False)
        ax.spines['top'].set_visible(False)
        ax.tick_params(axis = 'y', labelsize = 14)
        ax.tick_params(axis = 'x', labelsize = 14)
        ax.set_title(dt.datetime.strftime(date.to_pydatetime(), '%Y-%m-%d'),
                     fontsize = 18)
        ax.set_xlabel(r'$PPFD\/(\mu mol\/photons\/m^{-2}\/s^{-1})$',
                      fontsize = 18)
        ax.set_ylabel(r'$NEE\/(\mu molC\/m^{-2}\/s^{-1})$', fontsize = 18)
        labels_dict = {'night': 'Night Eo and rb', 'day': 'Night Eo, day rb'}
        markers_dict = {'night': '+', 'day': 'x'}
        colors_dict = {'night': 'blue', 'day': 'magenta'}
        ax.plot(df.PPFD, df.NEE, color = 'None', marker = 'o',
                mfc = 'grey', mec = 'black', ms = 8, alpha = 0.5,
                label = 'Observations')
        for key in results_dict.keys():
            params = results_dict[key]
            s = _NEE_model(par_series=df.PPFD, vpd_series=df.VPD,
                           t_series=df.TC, rb = params['rb'],
                           Eo = params['Eo'], alpha = params['alpha'],
                           beta = params['beta'], k = params['k'])
            ax.plot(df.PPFD, s, color = colors_dict[key],
                    marker = markers_dict[key], label = labels_dict[key],
                    ls = 'None')
        ax.legend(loc = [0.05, 0.1], fontsize = 12)
        return fig
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def plot_E0_data(self, df):
        title = np.datetime_as_string(df.index.values[0], unit='D') + " to "
        title += np.datetime_as_string(df.index.values[-1], unit='D')
        file_name = os.path.join("plots", "estimate_e0_" + title.replace(" ", "_") + ".png")

        if hasattr(self, 'E0_fignum'):
            pass
        else:
            if len(plt.get_fignums()) == 0:
                self.E0_fignum = 1
            else:
                self.E0_fignum = plt.get_fignums()[-1] + 1

        if self.l6_info["Options"]["call_mode"] == "interactive":
            plt.ion()
        else:
            current_backend = plt.get_backend()
            plt.switch_backend("agg")
            plt.ioff()

        if plt.fignum_exists(self.E0_fignum):
            fig = plt.figure(self.E0_fignum)
            plt.clf()
            axs = fig.add_subplot(1, 1, 1)
        else:
            fig, axs = plt.subplots(num=self.E0_fignum, figsize=(8, 8))

        if "Sws" in list(self.df):
            ldf = self.df[self.df.index.isin(df.index)]
            sc = axs.scatter(df.TC.values, df.ER.values, c=ldf.Sws.values, s=10)
        else:
            sc = axs.scatter(df.TC.values, df.ER.values, s=10)
        axs.set_title(title)
        axs.set_xlabel("Temperature (degC)")
        axs.set_ylabel("ER (umol/m^2/s)")
        clb = plt.colorbar(sc)
        clb.ax.set_title("Sws")
        fig.savefig(file_name, format="png")

        if self.l6_info["Options"]["call_mode"] == "interactive":
            fig.canvas.flush_events()
        else:
            plt.close()
            plt.switch_backend(current_backend)
            plt.ion()
        return
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def plot_LL_data(self, df):
        title = np.datetime_as_string(df.index.values[0], unit='D') + " to "
        title += np.datetime_as_string(df.index.values[-1], unit='D')
        file_name = os.path.join("plots", "LL_" + title.replace(" ", "_") + ".png")

        if hasattr(self, 'LL_fignum'):
            pass
        else:
            if len(plt.get_fignums()) == 0:
                self.LL_fignum = 1
            else:
                self.LL_fignum = plt.get_fignums()[-1] + 1

        if self.l6_info["Options"]["call_mode"] == "interactive":
            plt.ion()
        else:
            current_backend = plt.get_backend()
            plt.switch_backend("agg")
            plt.ioff()

        if plt.fignum_exists(self.LL_fignum):
            fig = plt.figure(self.LL_fignum)
            plt.clf()
            axs = fig.add_subplot(1, 1, 1)
        else:
            fig, axs = plt.subplots(num=self.LL_fignum, figsize=(8, 8))

        sc = axs.scatter(df.PPFD.values, df.NEE.values, c=df.VPD.values, s=10)
        axs.set_title(title)
        axs.set_xlabel("PPFD (umol/m^2/s)")
        axs.set_ylabel("NEE (umol/m^2/s)")
        clb = plt.colorbar(sc)
        clb.ax.set_title("VPD")
        fig.savefig(file_name, format="png")

        if self.l6_info["Options"]["call_mode"] == "interactive":
            fig.canvas.flush_events()
        else:
            plt.close()
            plt.switch_backend(current_backend)
            plt.ion()

        return
    #--------------------------------------------------------------------------

    #--------------------------------------------------------------------------
    def prior_parameter_estimates(self):
        self.priors = {"rb": self.df["ER"].mean(), "Eo": 100}
        if self.l6_info["Options"]["called_by"] in ["ERUsingLasslop"]:
            self.priors["alpha"] = -0.01
            lwr = self.df.loc[self.df.PPFD > self.noct_threshold, 'NEE'].quantile(0.03)
            upr = self.df.loc[self.df.PPFD > self.noct_threshold, 'NEE'].quantile(0.97)
            self.priors["beta"] = (lwr - upr)
            self.priors["k"] = 0
        return
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def _check_weights_format(weighting):

    try:
        assert isinstance(weighting, (str, list))
    except AssertionError:
        raise TypeError('"weighting" kwarg must be either string or list')
    try:
        if isinstance(weighting, str):
            assert weighting in ['air', 'soil']
            return weighting
    except AssertionError:
        raise TypeError('if str passed for "weighting" kwarg, it must '
                           'be either "air" or "soil"')
    try:
        if isinstance(weighting, list):
            assert len(weighting) == 2
            for x in weighting:
                assert isinstance(x, (int, float))
            return weighting
    except AssertionError:
        raise TypeError('if list passed for weighting kwarg, it must '
                        'conists of only 2 elements, each of which must '
                        'be of type int or float')
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
"""Arrhenius style equation as used in Lloyd and Taylor 1994"""

def _Lloyd_and_Taylor(t_series, rb, Eo):

    return rb  * np.exp(Eo * (1 / (10 + 46.02) - 1 / (t_series + 46.02)))
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
"""Rectangular hyperbola as used in Lasslop et al 2010"""

def _rectangular_hyperbola(par_series, vpd_series, alpha, beta, k):

    beta_VPD = beta * np.exp(-k * (vpd_series - 1))
    index = vpd_series <= 1
    beta_VPD[index] = beta
    GPP = (alpha * par_series) / (1 - (par_series / 2000) +
           (alpha * par_series / beta_VPD))
    index = par_series < 5
    GPP[index] = 0
    return GPP
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
"""Complete model containing both temperature and ligh response functions"""

def _NEE_model(par_series, vpd_series, t_series, rb, Eo, alpha, beta, k):

    return (_rectangular_hyperbola(par_series, vpd_series, alpha, beta, k) +
            _Lloyd_and_Taylor(t_series, rb, Eo))
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
"""Convert external names to internal names"""

def _rename_df(df, external_names, internal_names):

    assert sorted(external_names.keys()) == sorted(internal_names.keys())
    swap_dict = {external_names[key]: internal_names[key]
                 for key in internal_names.keys()}
    for label in list(swap_dict.keys()):
        if label not in list(df):
            swap_dict.pop(label)
    sub_df = df[swap_dict.keys()].copy()
    sub_df.columns = swap_dict.values()
    return sub_df
#------------------------------------------------------------------------------
