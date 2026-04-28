# -*- coding: utf-8 -*-

# standard modules
import datetime
import logging
import os
import time
# 3rd party modules
#import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
#from pandas.plotting import register_matplotlib_converters
#register_matplotlib_converters()
from scipy import stats
import statsmodels.api as sm
#import statsmodels.formula.api as sm
# PFP modules
from scripts import constants as c
from scripts import pfp_io
from scripts import pfp_utils

pfp_log = os.environ["pfp_log"]
logger = logging.getLogger(pfp_log)

#------------------------------------------------------------------------------
# Return a bootstrapped sample of the passed dataframe
def bootstrap(df):
    #return df.iloc[np.random.random_integers(0, len(df)-1, len(df))]
    if len(df) <= 1:
        return df
    else:
        return df.iloc[np.random.randint(0, len(df)-1, len(df))]
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def fit(temp_df):
    """
    Purpose:
     Fits a piece-wise linear regression to the Fco2 vs ustar data for a single
     season and temperature class and returns the fit statistics and the ustar
     threshold for both the 2 parameter (b) model and the 3 parameter (a) model.
    Author: Ian McHugh
    Date: Back in the day
    Mods:
     30/3/2022 PRI - rewrote using ndarrays instead of pandas data frames
    """
    Fco2 = temp_df["Fco2"].values
    ustar = temp_df["ustar"].values
    SSE_null_b = ((Fco2 - Fco2.mean())**2).sum()
    alpha0, alpha1 = stats.linregress(ustar, Fco2)[:2]
    SSE_null_a = ((Fco2 - (ustar*alpha0 + alpha1))**2).sum()
    f_a_array=np.empty(50)
    f_b_array=np.empty(50)
    idx = np.ones(50)
    for i in range(1, 49):
        # Operational (b) model
        ustar_alt = ustar.copy()
        ustar_alt[i+1:] = ustar_alt[i]
        x = np.column_stack((idx, ustar_alt))
        reg_params = np.linalg.lstsq(x, Fco2, rcond=None)[0]
        yHat = reg_params[0] + reg_params[1]*ustar_alt
        SSE_full = ((Fco2 - yHat)**2).sum()
        f_b_array[i] = (SSE_null_b-SSE_full)/(SSE_full/(50-2))
        # Diagnostic (a) model
        ustar_alt1 = ustar.copy()
        ustar_alt1[i+1:] = ustar_alt1[i]
        ustar_alt2 = (ustar - ustar[i])*np.concatenate([np.zeros(i+1),np.ones(50-(i+1))])
        x = np.column_stack((idx, ustar_alt1, ustar_alt2))
        reg_params = np.linalg.lstsq(x, Fco2, rcond=None)[0]
        yHat = reg_params[0] + reg_params[1]*ustar_alt1 + reg_params[2]*ustar_alt2
        SSE_full = ((Fco2 - yHat)**2).sum()
        f_a_array[i] = (SSE_null_a-SSE_full)/(SSE_full/(50-2))
    f_b_array[0], f_b_array[-1] = f_b_array.min(), f_b_array.min()
    f_b_max = f_b_array.max()
    change_point_b = f_b_array.argmax()
    ustar_threshold_b = ustar[change_point_b]
    f_a_array[0], f_a_array[-1] = f_a_array.min(), f_a_array.min()
    f_a_max = f_a_array.max()
    change_point_a = f_a_array.argmax()
    ustar_threshold_a = ustar[change_point_a]
    # Get regression parameters
    # b model
    ustar_alt = ustar.copy()
    ustar_alt[change_point_b+1:] = ustar_threshold_b
    x = np.column_stack((idx, ustar_alt))
    reg_params = np.linalg.lstsq(x, Fco2, rcond=None)[0]
    b0 = reg_params[0]
    b1 = reg_params[1]
    # a model
    ustar_alt1 = ustar.copy()
    ustar_alt1[change_point_a+1:] = ustar_alt1[change_point_a]
    ustar_alt2 = (ustar - ustar[change_point_a])*np.concatenate([np.zeros(change_point_a+1),np.ones(50-(change_point_a+1))])
    X = np.column_stack((ustar_alt1, ustar_alt2))
    X = sm.add_constant(X)
    resols = sm.OLS(Fco2, X).fit()
    a0 = resols.params[0]
    a1 = resols.params[1]
    a2 = resols.params[2]
    a1p = resols.pvalues[1]
    a2p = resols.pvalues[2]
    norm_a1 = a1*(ustar_threshold_a/(a0+a1*ustar_threshold_a))
    norm_a2 = a2*(ustar_threshold_a/(a0+a1*ustar_threshold_a))
    # Return results
    return [ustar_threshold_b,f_b_max,b0,b1,change_point_b,
            ustar_threshold_a,f_a_max,a0,a1,a2,norm_a1,norm_a2,change_point_a,a1p,a2p]
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Coordinate steps in CPD process
def cpd_mchugh_main(cf):
    """
    This script fetches data from an OzFluxQC .nc file and applies change point detection
    algorithms to the nocturnal C flux data to provide a best estimate for the u*threshold,
    as well as associated uncertainties (95%CI). It stratifies the data by year, 'season'*
    and temperature class (data are also binned to reduce noise) and the analysis runs
    on each of the resulting samples. It is based on:

    Barr, A.G., Richardson, A.D., Hollinger, D.Y., Papale, D., Arain, M.A., Black, T.A.,
    Bohrer, G., Dragoni, D., Fischer, M.L., Gu, L., Law, B.E., Margolis, H.A., McCaughey, J.H.,
    Munger, J.W., Oechel, W., Schaeffer, K., 2013. Use of change-point detection for
    friction–velocity threshold evaluation in eddy-covariance studies.
    Agric. For. Meteorol. 171-172, 31–45. doi:10.1016/j.agrformet.2012.11.023

    Still to do:
        - calculation of f-statistic limits for passing QC

    * Season is just a 1000 point slice of nocturnal data - these slices also overlap by 50%.
    """

    master_df,d = CPD_run(cf)

    # Find number of years in df
    years_index = sorted(list(set(master_df.index.year)))

    # Create df to keep counts of total samples and QC passed samples
    counts_df = pd.DataFrame(index=years_index,columns = ['Total'])
    counts_df.fillna(0,inplace = True)

    msg = " Starting CPD (McHugh) analysis for " + str(years_index)
    logger.info(msg)

    # Bootstrap the data and run the CPD algorithm
    #for i in xrange(d['num_bootstraps']):
    for i in range(d['num_bootstraps']):
        # Bootstrap the data for each year
        bootstrap_flag = (False if i == 0 else True)
        if bootstrap_flag == False:
            df = master_df
            msg = " Analysing observational data for first pass"
            logger.info(msg)
            start_time = time.time()
        else:
            df = pd.concat([bootstrap(master_df.loc[str(j)]) for j in years_index])
            if i==1:
                msg = " Analysing " + str(d["num_bootstraps"]) + " bootstraps"
                logger.info(msg)
                bootstrap_time = float((time.time() - start_time) * int(d["num_bootstraps"]))/float(60)
                bootstrap_time = int(bootstrap_time + 0.5)
                msg = "  This will take about " + str(bootstrap_time)
                msg += " minutes, so be patient, get coffee & read a paper"
                logger.info(msg)

        # Create nocturnal dataframe (drop all records where any one of the variables is NaN)
        temp_df = df[['Fco2','Ta','ustar','Year']][df['Fsd'] < d['radiation_threshold']].dropna(how = 'any',axis=0)

        # Arrange data into seasons
        # try: may be insufficient data, needs to be handled; if insufficient on first pass then return empty,otherwise next pass
        # this will be a marginal case, will almost always be enough data in bootstraps if enough in obs data
        years_df, seasons_df, results_df = sort(temp_df, d['flux_period'], years_index, i)

        # Use the results df index as an iterator to run the CPD algorithm on the year/season/temperature strata
        #if i==1: logger.info(' Finding change points...')
        cols = ['bMod_threshold','bMod_f_max','b0','b1','bMod_CP',
                'aMod_threshold','aMod_f_max','a0','a1','a2','norm_a1','norm_a2','aMod_CP','a1p','a2p']
        lst = []
        for j in results_df.index:
            temp_df = seasons_df.loc[j].copy()
            lst.append(fit(temp_df))
        stats_df = pd.DataFrame(np.vstack(lst), columns = cols, index = results_df.index)
        results_df = results_df.join(stats_df)

        results_df['bMod_CP'] = results_df['bMod_CP'].astype(int)
        results_df['aMod_CP'] = results_df['aMod_CP'].astype(int)

        # QC the results
        #if i==1: logger.info(' Doing within-sample QC...')
        results_df = QC1(results_df)

        # Output results and plots (if user has set output flags in config file to true)
        if bootstrap_flag == False:
            #if 'results_output_path' in d.keys():
                #results_df.to_csv(os.path.join(d['results_output_path'],'Observational_ustar_threshold_statistics.csv'))
            #if 'plot_path' in list(d.keys()) and d["plot_tclass"]:
                #logger.info('Doing plotting for observational data')
                #d["nFig"] = 0
                #fig_nums = plt.get_fignums()
                #if len(fig_nums)>0: d["nFig"] = fig_nums[-1] + 1
                #for j in results_df.index:
                    #plot_fits(seasons_df.loc[j], results_df.loc[j], d)
            logger.info(' Outputting results for observational dataset')
            xlwriter = pd.ExcelWriter(d['file_out'])
            xlsheet = "T class"
            results_df.to_excel(xlwriter,sheet_name=xlsheet)

        # Drop the season and temperature class levels from the hierarchical index,
        # drop all cases that failed QC
        results_df = results_df.reset_index(level=['season', 'T_class'], drop = True)
        results_df = results_df[results_df['b_valid'] == True]

        # If first pass, create a df to concatenate the results for each individual run
        # Otherwise concatenate all_results_df with current results_df
        if bootstrap_flag == False:
            all_results_df = results_df
        else:
            all_results_df = pd.concat([all_results_df, results_df])

        # Iterate counters for each year for each bootstrap
        for j in years_df.index:
            counts_df.loc[j, 'Total'] = counts_df.loc[j, 'Total'] + years_df.loc[j, 'seasons'] * 4
        #if bootstrap_flag:
            #progress = float(i)/float(d['num_bootstraps']-1)
            #pfp_utils.update_progress(progress)

    logger.info(' Finished change point detection for all bootstraps')
    logger.info(' Starting QC')

    # Sort by index so all years are together
    all_results_df.sort_index(inplace = True)

    # Drop all years with no data remaining after QC, and return nothing if all years were dropped
    [counts_df.drop(i,inplace=True) for i in counts_df.index if counts_df.loc[i, 'Total'] == 0]
    if counts_df.empty:
        logger.error('Insufficient data for analysis... exiting')
        return

    # QC the combined results
    logger.info(' Doing cross-sample QC...')
    output_stats_df = QC2(all_results_df, counts_df, d['num_bootstraps'])

    # Calculate final values
    logger.info(' Calculating final results')
    output_stats_df = stats_calc(all_results_df, output_stats_df)

    # If requested by user, plot: 1) histograms of u* thresholds for each year;
    #                             2) normalised a1 and a2 values
    #if 'plot_path' in list(d.keys()):
        #logger.info(' Plotting u* histograms for all valid b model thresholds for all valid years')
        #for j in output_stats_df.index:
            #if j in all_results_df.index:
                #plot_hist(all_results_df.loc[j, 'bMod_threshold'][all_results_df.loc[j, 'b_valid'] == True],
                                   #output_stats_df.loc[j, 'ustar_mean'],
                                   #output_stats_df.loc[j, 'ustar_sig'],
                                   #output_stats_df.loc[j, 'crit_t'],
                                   #j, d)

        #[plot_hist(all_results_df.loc[j, 'bMod_threshold'][all_results_df.loc[j, 'b_valid'] == True],
                   #output_stats_df.loc[j, 'ustar_mean'],
                   #output_stats_df.loc[j, 'ustar_sig'],
                   #output_stats_df.loc[j, 'crit_t'],
                   #j, d)
         #for j in output_stats_df.index]

        #logger.info(' Plotting normalised median slope parameters for all valid a model thresholds for all valid years')
        #plot_slopes(output_stats_df[['norm_a1_median', 'norm_a2_median']], d)

    # Output final stats if requested by user
    #if 'results_output_path' in d.keys():
        #output_stats_df.to_csv(os.path.join(d['results_output_path'], 'annual_statistics.csv'))
    xlsheet = "Annual"
    output_stats_df.to_excel(xlwriter,sheet_name=xlsheet)
    xlwriter.close()
    # close any open plot windows if we are doing batch processing
    #if d["call_mode"]!="interactive": plt.close('all')

    logger.info(' CPD analysis complete!')
    # Return final results
    return output_stats_df
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Fetch the data and prepare it for analysis
def CPD_run(cf):
    # Set input file and output path and create directories for plots and results
    path_out = cf['Files']['file_path']
    file_in = os.path.join(cf['Files']['file_path'],cf['Files']['in_filename'])
    #
    if "out_filename" in cf['Files']:
        file_out = os.path.join(cf['Files']['file_path'],cf['Files']['out_filename'])
    else:
        file_name = cf['Files']['in_filename'].replace(".nc","_CPD_McHugh.xlsx")
        file_out = os.path.join(cf['Files']['file_path'], file_name)
    plot_path = pfp_utils.get_keyvaluefromcf(cf, ["Files"], "plot_path", default="plots/")
    plot_path = os.path.join(plot_path, "CPD", "")
    if not os.path.isdir(plot_path):
        os.makedirs(plot_path)
    results_path = path_out
    if not os.path.isdir(results_path): os.makedirs(results_path)
    # get a dictionary of the variable names
    var_list = list(cf["Variables"].keys())
    names = {}
    for item in var_list:
        if "name" in list(cf["Variables"][item].keys()):
            names[item] = cf["Variables"][item]["name"]
        else:
            names[item] = item
    # read the netcdf file
    ds = pfp_io.NetCDFRead(file_in)
    if ds.info["returncodes"]["value"] != 0: return
    ts = int(float(ds.root["Attributes"]["time_step"]))
    # get the datetime
    dt = ds.root["Variables"]["DateTime"]["Data"]
    # adjust the datetime so that the last time period in a year is correctly assigned.
    # e.g. last period for 2013 is 2014-01-01 00:00, here we make the year 2013
    dt = dt - datetime.timedelta(minutes=ts)
    # now get the data
    d = {}
    f = {}
    for item in list(names.keys()):
        msg = " CPD (McHugh): Using variable " + names[item] + " for " + item
        logger.info(msg)
        var = pfp_utils.GetVariable(ds, names[item])
        d[item] = np.ma.filled(var["Data"], np.nan)
        f[item] = var["Flag"]
    # set data to NaNs if target (Fco2) flag is not 0 or driver (Fsd, ustar, Ta)
    # flag does not end in 0 (i.e. allow gap filled drivers but only observed target)
    # create a conditional index, 0 will be OK, 1 will be not OK
    cidx = np.zeros(len(dt))
    # loop over items in the flag dictionary
    for item in list(f.keys()):
        # check to see if we are using the target ...
        if item == "Fco2":
            # target must have a flag == 0 i.e. an observation
            idx = np.where(f[item] != 0)[0]
            cidx[idx] = 1
        else:
            # drivers must have a flag that ends in 0 i.e. can be gap filled
            idx = np.where(np.mod(f[item], 10) != 0)[0]
            cidx[idx] = 1
    # loop over the data dictionary and set rejected data to NaN
    for item in list(d.keys()):
        d[item][cidx == 1] = np.nan
    d["Year"] = np.array([ldt.year for ldt in dt])
    df = pd.DataFrame(d, index=dt)
    # replace missing values with NaN
    df.replace(c.missing_value, np.nan)
    # Build dictionary of additional configs
    d={}
    d["radiation_threshold"] = int(cf["Options"]["Fsd_threshold"])
    d["num_bootstraps"] = int(cf["Options"]["Num_bootstraps"])
    d["flux_period"] = int(float(ds.root["Attributes"]["time_step"]))
    d["site_name"] = ds.root["Attributes"]["site_name"]
    d["call_mode"] = pfp_utils.get_keyvaluefromcf(cf, ["Options"], "call_mode",
                                                  default="interactive", mode="quiet")
    d["show_plots"] = pfp_utils.get_optionskeyaslogical(cf, "show_plots", default=True)
    d["plot_tclass"] = False
    if cf["Options"]["Plot_TClass"] == "True":
        d["plot_tclass"] = True
    if cf["Options"]["Output_plots"] == "True":
        d["plot_path"] = plot_path
    if cf["Options"]["Output_results"] == "True":
        d["results_path"] = results_path
        d["file_out"] = file_out

    return df,d
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Plot identified change points in observed (i.e. not bootstrapped) data and
# write to specified folder
#def plot_fits(temp_df,stats_df,d):

    ## Create series for use in plotting (this could be more easily called from fitting function - why are we separating these?)
    #temp_df['ustar_alt']=temp_df['ustar']
    #temp_df['ustar_alt'].iloc[int(stats_df['bMod_CP'])+1:]=stats_df['bMod_threshold']
    #temp_df['ustar_alt1']=temp_df['ustar']
    #temp_df['ustar_alt1'].iloc[stats_df['aMod_CP']+1:]=temp_df['ustar_alt1'].iloc[stats_df['aMod_CP']]
    #temp_df['ustar_alt2']=((temp_df['ustar']-stats_df['aMod_threshold'])
                           #*np.concatenate([np.zeros(stats_df['aMod_CP']+1),np.ones(50-(stats_df['aMod_CP']+1))]))
    #temp_df['yHat_a']=stats_df['a0']+stats_df['a1']*temp_df['ustar_alt1']+stats_df['a2']*temp_df['ustar_alt2'] # Calculate the estimated time series
    #temp_df['yHat_b']=stats_df['b0']+stats_df['b1']*temp_df['ustar_alt']

    ## Now plot
    #fig=plt.figure(d["nFig"],figsize=(12,8))
    #fig.patch.set_facecolor('white')
    #plt.plot(temp_df['ustar'],temp_df['Fco2'],'bo')
    #plt.plot(temp_df['ustar'],temp_df['yHat_b'],color='red')
    #plt.plot(temp_df['ustar'],temp_df['yHat_a'],color='green')
    #plt.title('Year: '+str(stats_df.name[0])+', Season: '+str(stats_df.name[1])+', T class: '+str(stats_df.name[2])+'\n',fontsize=22)
    #plt.xlabel(r'u* ($m\/s^{-1}$)',fontsize=16)
    #plt.ylabel(r'Fco2 ($\mu mol C\/m^{-2} s^{-1}$)',fontsize=16)
    #plt.axvline(x=stats_df['bMod_threshold'],color='black',linestyle='--')
    #props = dict(boxstyle='round,pad=1', facecolor='white', alpha=0.5)
    #txt='Change point detected at u*='+str(round(stats_df['bMod_threshold'],3))+' (i='+str(stats_df['bMod_CP'])+')'
    #ax=plt.gca()
    #plt.text(0.57,0.1,txt,bbox=props,fontsize=12,verticalalignment='top',transform=ax.transAxes)
    #plot_out_name='Y'+str(stats_df.name[0])+'_S'+str(stats_df.name[1])+'_Tclass'+str(stats_df.name[2])+'.jpg'
    #fig.savefig(os.path.join(d["plot_path"],plot_out_name))
    #fig.clf()

# Plot PDF of u* values and write to specified folder
#def plot_hist(S,mu,sig,crit_t,year,d):
    #if len(S)<=1:
        #logger.info(" plot_hist: 1 or less values in S for year "+str(year)+", skipping histogram ...")
        #return
    #S=S.reset_index(drop=True)
    #x_low=S.min()-0.1*S.min()
    #x_high=S.max()+0.1*S.max()
    #x=np.linspace(x_low,x_high,100)
    #if d["show_plots"]:
        #plt.ion()
    #else:
        #plt.ioff()
    #fig=plt.figure(figsize=(12,8))
    ##fig.patch.set_facecolor('white')
    ##plt.hist(S,normed=True)
    #plt.hist(S, density=True)
    #plt.xlim(x_low,x_high)
    #plt.xlabel(r'u* ($m\/s^{-1}$)',fontsize=16)
    #if np.isfinite(mu) and np.isfinite(sig):
        #plt.plot(x,stats.norm.pdf(x,mu,sig),color='red',linewidth=2.5,label='Gaussian PDF')
        #plt.axvline(x=mu-sig*crit_t,color='black',linestyle='--')
        #plt.axvline(x=mu+sig*crit_t,color='black',linestyle='--')
        #plt.axvline(x=mu,color='black',linestyle='dotted')
    #txt='mean u*='+str(mu)
    #ax=plt.gca()
    #props = dict(boxstyle='round,pad=1', facecolor='white', alpha=0.5)
    #plt.text(0.4,0.1,txt,bbox=props,fontsize=12,verticalalignment='top',transform=ax.transAxes)
    #plt.legend(loc='upper left')
    #plt.title(str(year)+'\n')
    #plot_out_name=os.path.join(d["plot_path"],d["site_name"]+'_CPD_'+str(year)+'.png')
    #fig.savefig(plot_out_name)
    #if d["show_plots"]:
        #plt.draw()
        #pfp_utils.mypause(1)
        #plt.ioff()
    #else:
        #plt.ion()
    ##if d["call_mode"].lower()!="interactive": plt.close(fig)

# Plot normalised slope parameters to identify outlying years and output to
# results folder - user can discard output for that year
#def plot_slopes(df,d):
    #df=df.reset_index(drop=True)
    #if d["show_plots"]:
        #plt.ion()
    #else:
        #plt.ioff()
    #fig=plt.figure(figsize=(12,8))
    ##fig.patch.set_facecolor('white')
    #plt.scatter(df['norm_a1_median'],df['norm_a2_median'],s=80,edgecolors='blue',facecolors='none')
    #plt.xlim(-4,4)
    #plt.ylim(-4,4)
    #plt.xlabel('$Median\/normalised\/ a^{1}$',fontsize=16)
    #plt.ylabel('$Median\/normalised\/ a^{2}$',fontsize=16)
    #plt.title('Normalised slope parameters \n')
    #plt.axvline(x=1,color='black',linestyle='dotted')
    #plt.axhline(y=0,color='black',linestyle='dotted')
    #plot_out_name=os.path.join(d["plot_path"],d['site_name']+"_CPD_slopes.png")
    #fig.savefig(plot_out_name)
    #if d["show_plots"]:
        #plt.draw()
        #pfp_utils.mypause(1)
        #plt.ioff()
    #else:
        #plt.ion()
    ##if d["call_mode"].lower()!="interactive": plt.close(fig)

#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Quality control within bootstrap
def QC1(QC1_df):

    # Set significance level (these need to be moved, and a model needs to be explicitly calculated for a threshold)
    fmax_a_threshold = 6.9
    fmax_b_threshold = 6.9

    QC1_df['major_mode'] = True

    # For each year, find all cases that belong to minority mode (i.e. mode is sign of slope below change point)
    total_count = QC1_df['bMod_threshold'].groupby(level = 'year').count()
    neg_slope = QC1_df['bMod_threshold'][QC1_df['b1'] < 0].groupby(level = 'year').count()
    neg_slope = neg_slope.reindex(total_count.index)
    neg_slope = neg_slope.fillna(0)
    neg_slope = neg_slope/total_count * 100
    for i in neg_slope.index:
        sign = 1 if neg_slope.loc[i] < 50 else -1
        QC1_df.loc[i, 'major_mode'] = np.sign(np.array(QC1_df.loc[i, 'b1'])) == sign

    # Make invalid (False) all b_model cases where: 1) fit not significantly better than null model;
    #                                               2) best fit at extreme ends;
    #                                               3) case belongs to minority mode (for that year)
    QC1_df['b_valid'] = ((QC1_df['bMod_f_max'] > fmax_b_threshold)
                         & (QC1_df['bMod_CP'] > 4)
                         & (QC1_df['bMod_CP'] < 45)
                         & (QC1_df['major_mode'] == True))

    # Make invalid (False) all a_model cases where: 1) fit not significantly better than null model;
    #                                               2) slope below change point not statistically significant;
    #                                               3) slope above change point statistically significant
    QC1_df['a_valid'] = ((QC1_df['aMod_f_max'] > fmax_a_threshold)
                         & (QC1_df['a1p'] < 0.05)
                         & (QC1_df['a2p'] > 0.05))

    # Return the results df
    QC1_df = QC1_df.drop('major_mode', axis = 1)
    return QC1_df

#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
# Quality control across bootstraps
def QC2(df,output_df,bootstrap_n):

    # Get the median values of the normalised slope parameters for each year
    output_df['norm_a1_median']=df['norm_a1'][df['a_valid']==True].groupby(df[df['a_valid']==True].index).median()
    output_df['norm_a2_median']=df['norm_a2'][df['a_valid']==True].groupby(df[df['a_valid']==True].index).median()

    # Get the proportion of all available cases that passed QC for b model
    output_df['QCpass']=df['bMod_threshold'][df['b_valid']==True].groupby(df[df['b_valid']==True].index).count()
    output_df['QCpass_prop']=output_df['QCpass']/output_df['Total']

    # Identify years where either diagnostic or operational model did not find enough good data for robust estimate
    output_df['a_valid']=(~(np.isnan(output_df['norm_a1_median']))&(~np.isnan(output_df['norm_a2_median'])))
    #output_df['b_valid']=(output_df['QCpass']>(4*bootstrap_n))&(output_df['QCpass_prop']>0.2)
    output_df['b_valid']=(output_df['QCpass']>=bootstrap_n)&(output_df['QCpass_prop']>=0.2)
    for i in output_df.index:
        if output_df['a_valid'].loc[i]==False:
            #log.info(' Insufficient valid cases for robust diagnostic (a model) u* determination in year '+str(i))
            logger.warning(' Insufficient valid cases for '+str(i)+' (a model)')
        if output_df['b_valid'].loc[i]==False:
            #log.info(' Insufficient valid cases for robust operational (b model) u* determination in year '+str(i))
            logger.warning(' Insufficient valid cases for '+str(i)+' (b model)')

    return output_df

#------------------------------------------------------------------------------



#------------------------------------------------------------------------------
def sort(df, flux_period, years_index, i):

    # Set the bin size on the basis of the flux measurement frequency
    if flux_period == 30:
        bin_size = 1000
    else:
        bin_size = 600

    # Create a df containing count stats for the variables for all available years
    years_df = pd.DataFrame(index=years_index)
    years_df['Fco2_count'] = df['Fco2'].groupby([lambda x: x.year]).count()
    years_df['seasons'] = [years_df.loc[j, 'Fco2_count']/(bin_size//2)-1 for j in years_df.index]
    years_df['seasons'].fillna(0, inplace=True)
    years_df['seasons'] = np.where(years_df['seasons'] < 0, 0, years_df['seasons'])
    # 2026-04-24 PRI replace NaN with 0 so that astype(int) will work in pamdas 3+.
    years_df.fillna(0, inplace=True)
    years_df['seasons'] = years_df['seasons'].astype(int)
    if np.all(years_df['seasons'] <= 0):
        logger.error('No years with sufficient data for evaluation, exiting...')
        return
    elif np.any(years_df['seasons'] <= 0):
        exclude_years_list = years_df[years_df['seasons'] <= 0].index.tolist()
        exclude_years_str= ','.join(map(str, exclude_years_list))
        #log.info(' Insufficient data for evaluation in the following years: ' + exclude_years_str + ' (excluded from analysis)')
        if i==1:
            logger.warning(' '+exclude_years_str + ' excluded from analysis (insufficient data)')
        years_df = years_df[years_df['seasons'] > 0]

    # Extract overlapping series, sort by temperature and concatenate
    lst = []
    for year in years_df.index:
        #for season in xrange(years_df.loc[year, 'seasons']):
        for season in range(int(years_df.loc[year, 'seasons'])):
            start_ind = season * (bin_size // 2)
            end_ind = season * (bin_size // 2) + bin_size
            # ugly hack to avoid FutureWarning from pandas V0.16.2 and older
            try:
                #lst.append(df.ix[str(year)].iloc[start_ind:end_ind].sort_values(by='Ta',axis = 0))
                lst.append(df.loc[str(year)].iloc[start_ind:end_ind].sort_values(by='Ta',axis = 0))
            except AttributeError:
                #lst.append(df.ix[str(year)].iloc[start_ind:end_ind].sort('Ta', axis = 0))
                lst.append(df.loc[str(year)].iloc[start_ind:end_ind].sort('Ta', axis = 0))
    seasons_df = pd.concat([frame for frame in lst])

    # Make a hierarchical index for year, season, temperature class, bin for the seasons dataframe
    years_index=np.concatenate([np.int32(np.ones(years_df.loc[year, 'seasons'] * bin_size) * year)
                                for year in years_df.index])

    #seasons_index=np.concatenate([np.concatenate([np.int32(np.ones(bin_size)*(season+1))
                                                  #for season in xrange(years_df.loc[year, 'seasons'])])
                                                  #for year in years_df.index])
    seasons_index=np.concatenate([np.concatenate([np.int32(np.ones(bin_size)*(season+1))
                                                  for season in range(int(years_df.loc[year, 'seasons']))])
                                                  for year in years_df.index])

    #Tclass_index=np.tile(np.concatenate([np.int32(np.ones(bin_size/4)*(i+1)) for i in xrange(4)]),
                         #len(seasons_index)/bin_size)
    Tclass_index=np.tile(np.concatenate([np.int32(np.ones(bin_size//4)*(i+1)) for i in range(4)]),
                         len(seasons_index)//bin_size)

    bin_index=np.tile(np.int32(np.arange(bin_size//4)/(bin_size//200)),len(seasons_df)//(bin_size//4))

    # Zip together hierarchical index and add to df
    arrays = [years_index, seasons_index, Tclass_index]
    tuples = list(zip(*arrays))
    hierarchical_index = pd.MultiIndex.from_tuples(tuples, names = ['year','season','T_class'])
    seasons_df.index = hierarchical_index

    # Set up the results df
    results_df = pd.DataFrame({'T_avg':seasons_df['Ta'].groupby(level = ['year','season','T_class']).mean(),
                               'Year':seasons_df['Year'].groupby(level = ['year','season','T_class']).mean()})

    # Sort the seasons by ustar, then bin average and drop the bin level from the index
    # ugly hack to avoid FutureWarning from pandas V0.16.2 and older
    try:
        seasons_df = pd.concat([seasons_df.loc[i[0]].loc[i[1]].loc[i[2]].sort_values(by='ustar', axis=0) for i in results_df.index])
    except AttributeError:
        seasons_df = pd.concat([seasons_df.loc[i[0]].loc[i[1]].loc[i[2]].sort('ustar', axis=0) for i in results_df.index])
    seasons_df.index = hierarchical_index
    seasons_df = seasons_df.set_index(bin_index, append = True)
    seasons_df.index.names = ['year','season','T_class','bin']
    seasons_df = seasons_df.groupby(level=['year','season','T_class','bin']).mean()
    seasons_df = seasons_df.reset_index(level = ['bin'], drop = True)
    seasons_df = seasons_df[['ustar','Fco2']]

    return years_df, seasons_df, results_df
#------------------------------------------------------------------------------

#------------------------------------------------------------------------------
def stats_calc(df,stats_df):

    # Add statistics vars to output df
    stats_df['ustar_mean'] = np.nan
    stats_df['ustar_sig'] = np.nan
    stats_df['ustar_n'] = np.nan
    stats_df['crit_t'] = np.nan
    stats_df['95%CI_lower'] = np.nan
    stats_df['95%CI_upper'] = np.nan
    stats_df['skew'] = np.nan
    stats_df['kurt'] = np.nan

    # Drop data that failed b model, then drop b model boolean variable
    df=df[df['b_valid']==True]
    df=df.drop('b_valid',axis=1)

    # Calculate stats
    for i in stats_df.index:
        if stats_df.loc[i, 'b_valid']:
            if isinstance(df.loc[i, 'bMod_threshold'],pd.Series):
                temp = stats.describe(df.loc[i, 'bMod_threshold'])
                stats_df.loc[i, 'ustar_mean'] = temp[2]
                stats_df.loc[i, 'ustar_sig'] = np.sqrt(temp[3])
                stats_df.loc[i, 'crit_t'] = stats.t.ppf(1 - 0.025, temp[0])
                stats_df.loc[i, '95%CI_lower'] = (stats_df.loc[i, 'ustar_mean'] -
                                                  stats_df.loc[i, 'ustar_sig'] *
                                                  stats_df.loc[i, 'crit_t'])
                stats_df.loc[i, '95%CI_upper'] = (stats_df.loc[i, 'ustar_mean'] +
                                                  stats_df.loc[i, 'ustar_sig'] *
                                                  stats_df.loc[i, 'crit_t'])
                stats_df.loc[i, 'skew'] = temp[4]
                stats_df.loc[i, 'kurt'] = temp[5]
            else:
                stats_df.loc[i, 'ustar_mean'] = df.loc[i, 'bMod_threshold']

    return stats_df
#------------------------------------------------------------------------------
