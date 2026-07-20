from typing import List
import matplotlib.pyplot as plt
import pandas as pd
from typing import Optional
import numpy as np

def produce_disturbance_tracking_plot_pqv(
        output_png_path : str,
        title : str,
        results_df : pd.DataFrame,
        perr_mw_signals : List[pd.Series],
        qerr_mvar_signals : List[pd.Series],
        verr_adj_pu_signals : List[pd.Series],
        skip_active_power_plot: Optional[bool] = None,
        P_base: Optional[float] = None,
        Active_power_filter_threshold: Optional[float]=None

        ):
    plt.clf()
    plt.close()
    
    fig, ax = plt.subplots(nrows=2, ncols=3, figsize=(16, 9), sharex=True, gridspec_kw={'height_ratios':[4,1]})
    plt.subplots_adjust(left=0.05, right=0.975, bottom=0.1, top=0.90, wspace=0.18, hspace=0.15)

    #plt.title("TODO: ADD V RISE TIME AND FIX VERR CALC",loc='center')
    # ax.rcParams['axes.grid'] = True
    ax[0,0].grid(True)
    ax[0,1].grid(True)
    ax[0,2].grid(True)

    for signal in perr_mw_signals:
        if skip_active_power_plot is not None:
            if not skip_active_power_plot:
                ax[0,0].plot(signal.index, signal)
        else:
            ax[0,0].plot(signal.index, signal)

    for signal in qerr_mvar_signals:
        ax[0,1].plot(signal.index, signal)
    for signal in verr_adj_pu_signals:
        ax[0,2].plot(signal.index, signal)

    if P_base is not None: #This should be the active power rating of the plant
        results_df_pmw_copy = results_df.copy()
        if Active_power_filter_threshold is not None:
            results_df_pmw_copy = results_df_pmw_copy[np.abs(results_df_pmw_copy["Change in Ppoc (MW)"]) >= Active_power_filter_threshold* P_base]  #filtering the cases where the active powre change is less than specified threshold
        else:
            #assume a 10% threshold 
            results_df_pmw_copy = results_df_pmw_copy[np.abs(results_df_pmw_copy["Change in Ppoc (MW)"]) >= 0.1* P_base]
    else:
        results_df_pmw_copy = results_df.copy() 

    ax[1,0].boxplot(results_df_pmw_copy["Ppoc Settling Time (sec)"],vert=False,widths=0.6)
    if results_df_pmw_copy.empty:
        ax[1,0].text(0.5, 0.5, "Not applicable", ha='center', va='center', transform=ax[1,0].transAxes)

    ax[0,0].set_title("Active Power",pad=10)
    ax[0,0].set_ylabel("Ppoc (MW)")
    ax[1,0].set_xlabel("Time since disturbance (s)")
    ax[1,0].set_yticks(ticks=[1],labels=["Settle \nTime (s)"])
    ax[1,0].set_title("Active Power",pad=10)

    ax[1,1].boxplot([results_df["Qpoc Settling Time (sec)"],results_df["Qpoc Rise Time (sec)"]],vert=False,widths=0.6)
    ax[0,1].set_title("Reactive Power",pad=10)
    ax[0,1].set_ylabel("Qpoc (MVAr)")
    ax[1,1].set_xlabel("Time since disturbance (s)")
    ax[1,1].set_yticks(ticks=[1,2],labels=["Settle \nTime (s)","Rise \nTime (s)"])
    ax[1,1].set_title("Reactive Power",pad=10)

    ax[1,2].boxplot(results_df["Vpoc Settling TIme (sec)"],vert=False,widths=0.6)
    ax[0,2].set_title("Connection Point Voltage",pad=10)
    ax[0,2].set_ylabel("Vpoc (pu)")
    ax[1,2].set_xlabel("Time since disturbance (s)")
    ax[1,2].set_yticks(ticks=[1],labels=["Settle \nTime (s)"])
    ax[1,2].set_title("Connection Point Voltage",pad=10)

    plt.savefig(output_png_path)
    plt.clf()
    plt.close()
    
