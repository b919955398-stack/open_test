from typing import Optional
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from .settling_analysis import StepAnalysisResults
from matplotlib.patches import Rectangle
import matplotlib

COLOUR_PALLET = ["red", "blue", "green", "black"]
AXIS_COLOUR = (0, 0, 0)
SECONDARY_COLOUR = (0.98, 0.98, 0.98)

SUPRESS_OSC_METRICS = False

def produce_rise_settle_plot_pqv(
        title : str,
        output_png_path : str,
        ppoc_mw_series : pd.Series,
        qpoc_mvar_series : pd.Series,
        vpoc_pu_series : pd.Series,
        p_results : StepAnalysisResults,
        q_results : StepAnalysisResults,
        v_results : StepAnalysisResults,
        subtitle : Optional[str] = None,
        skip_active_power_plot: Optional[bool] = False
        ):
    plt.clf()
    plt.close()

    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(16, 10), squeeze=False,sharex=False,)
    cm = 1 / 2.54
    fig.set_size_inches(42 * cm, 29.7 * cm)  # A4 Size Landscape.
    plt.subplots_adjust(left=0.05, right=0.975, bottom=0.05, top=0.90, wspace=0.12, hspace=0.4)
    
    fig.suptitle(title, fontsize=16)
    axes[0,0].set_title(subtitle, fontsize=10,loc='center',y=1.15)

    ax = axes[0,0]
    # ax.set_title('Active Power (MW)',loc='left',fontsize=13,pad = 10)
    if not skip_active_power_plot:
        ax.set_ylabel(ylabel='Active Power (MW)',loc='center',fontsize=10)
        ax.plot(ppoc_mw_series.index, ppoc_mw_series, color = COLOUR_PALLET[2])

    ax = axes[1,0]
    # ax.set_title('Reactive Power (MVAr)',loc='left',fontsize=13,pad = 10)
    ax.set_ylabel(ylabel='Reactive Power (MVAr)',loc='center',fontsize=10)
    ax.plot(qpoc_mvar_series.index, qpoc_mvar_series, color = COLOUR_PALLET[2])

    ax = axes[2,0]
    # ax.set_title('Voltage (PU)',loc='left',fontsize=13,pad = 10)
    ax.set_ylabel(ylabel='Voltage (PU)',loc='center',fontsize=10)
    ax.plot(vpoc_pu_series.index, vpoc_pu_series, color = COLOUR_PALLET[2])

    for i, results in enumerate([p_results, q_results, v_results]):
       

        settling_time_s = results.settling_time_results.settling_time_sec  
        settling_upper_limit = results.settling_time_results.upper_limit
        settling_lower_limit = results.settling_time_results.lower_limit
        settled_time = results.settling_time_results.settled_time

        rise_time_s = results.rise_time_results.rise_time_sec
        # rise_lower_limit = results.rise_time_results.lower_limit
        # rise_upper_limit = results.rise_time_results.upper_limit
        rise_upper_limit_time_s = results.rise_time_results.upper_limit_time_sec
        rise_lower_limit_time_s = results.rise_time_results.lower_limit_time_sec

        ax = axes[i,0]

        ax.axhline(y=settling_upper_limit,color = COLOUR_PALLET[0], linestyle='--',lw=1.0)
        ax.axhline(y=settling_lower_limit,color = COLOUR_PALLET[0], linestyle='--',lw=1.0)
        settle_time_vline = ax.axvline(x=settled_time,color = COLOUR_PALLET[0], linestyle='--',lw=1.0,label=f"SETTLE:{round(settling_time_s,2)}s")

        # ax.axhline(y=rise_upper_limit,color = COLOUR_PALLET[1], linestyle='-',lw=1.0)
        # ax.axhline(y=rise_lower_limit,color = COLOUR_PALLET[1], linestyle='-',lw=1.0)
        # ax.axvline(x=rise_upper_limit_time_s,color = COLOUR_PALLET[1], linestyle='--',lw=1.0)
        if i ==1:   
            ax.axvline(x=rise_upper_limit_time_s,color = COLOUR_PALLET[1], linestyle='--',lw=1.0)
            rise_time_vline = ax.axvline(x=rise_lower_limit_time_s,color = COLOUR_PALLET[1], linestyle='--',lw=1.0, label=f"RISE:{round(rise_time_s,2)}s")


        if not SUPRESS_OSC_METRICS:
            dummy = Rectangle((0, 0), 1, 1, fc="w", fill=False, edgecolor='none', linewidth=0,label=fr'$\zeta$={round(results.damping_ratio,2)},half-life={round(results.halving_time_sec,2)}')
            if i == 1:
                ax.legend([settle_time_vline,rise_time_vline,dummy],[f"SETTLE:{round(settling_time_s,2)}s",f"RISE:{round(rise_time_s,2)}s",fr'$\zeta$={round(results.damping_ratio,2)}, half-life={round(results.halving_time_sec,2)}s'],frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=3,prop={'size': 8})
            else:
                 ax.legend([settle_time_vline,dummy],[f"SETTLE:{round(settling_time_s,2)}s",fr'$\zeta$={round(results.damping_ratio,2)}, half-life={round(results.halving_time_sec,2)}s'],frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=2,prop={'size': 8})
        else:
            ax.legend(frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=3,prop={'size': 8})
        ax.grid(True)

    plt.savefig(output_png_path)
    plt.clf()
    plt.close()

def produce_rise_settle_recovery_plot(
        title : str,
        output_png_path : str,
        ppoc_mw_series : pd.Series,
        iq_pu_series : pd.Series,
        vpoc_pu_series: pd.Series,
        p_results : StepAnalysisResults,
        iq_results : StepAnalysisResults,
        fault_clearance_time : float,
        fault_inception_time : float,
        subtitle : Optional[str] = None,
        ):
    plt.clf()
    plt.close()
    matplotlib.use('Agg')

    # ppoc_mw_series = ppoc_mw_series[ppoc_mw_series.index <= fault_clearance_time + 2] #filters to reduce the amount of time plotted, disabled by default
    # iq_pu_series = iq_pu_series[iq_pu_series.index <= fault_clearance_time + 2]
    # vpoc_pu_series = vpoc_pu_series[vpoc_pu_series.index <= fault_clearance_time + 2]


    # Assign results variables for plotting
    iq_rise_time_s = iq_results.rise_time_results.rise_time_sec
    iq_settle_time_s = iq_results.settling_time_results.settling_time_sec
    iq_settled_time = iq_results.settling_time_results.settled_time
    iq_settling_upper_limit = iq_results.settling_time_results.upper_limit
    iq_settling_lower_limit = iq_results.settling_time_results.lower_limit   
    iq_rise_upper_limit_time_s = iq_results.rise_time_results.upper_limit_time_sec
    iq_rise_lower_limit_time_s = iq_results.rise_time_results.lower_limit_time_sec    

    p_recovery_time_sec = p_results.p_recovery_time_results.p_recovery_time_sec
    recovered_time = p_results.p_recovery_time_results.recovered_time
    p_recovery_threshold = p_results.p_recovery_time_results.p_recovery_threshold


    # Set figure properties
    fig, axes = plt.subplots(nrows=3, ncols=1, figsize=(16, 10), squeeze=False,sharex=False,)
    cm = 1 / 2.54
    fig.set_size_inches(42 * cm, 29.7 * cm)  # A4 Size Landscape.
    plt.subplots_adjust(left=0.05, right=0.975, bottom=0.05, top=0.90, wspace=0.12, hspace=0.4)
    
    # Set Titles
    fig.suptitle(title, fontsize=16)
    axes[0,0].set_title(subtitle, fontsize=10,loc='center',y=1.15)

    axes[0,0].set_ylabel(ylabel='Active Power (MW)',loc='center',fontsize=10)
    axes[0,0].plot(ppoc_mw_series.index, ppoc_mw_series, color = COLOUR_PALLET[2])

    axes[1,0].set_ylabel(ylabel='Reactive Current (pu)',loc='center',fontsize=10)
    axes[1,0].plot(iq_pu_series.index, iq_pu_series, color = COLOUR_PALLET[2])

    axes[2,0].set_ylabel(ylabel='PoC Voltage (pu)',loc='center',fontsize=10)
    axes[2,0].plot(vpoc_pu_series.index, vpoc_pu_series, color = COLOUR_PALLET[2])

    # y_min, y_max = vpoc_pu_series.min(), vpoc_pu_series.max()
    # current_ticks = axes[2,0].get_yticks()
    # new_ticks = sorted(set(current_ticks) | {y_min, y_max})  # Ensure min/max are included

    # new_ticks = np.sort(np.unique(np.append(current_ticks, [y_min, y_max])))

    # # Compute absolute differences from y_min and y_max
    # dist_to_min = np.abs(new_ticks - y_min)
    # dist_to_max = np.abs(new_ticks - y_max)

    # # Get indices of the closest ticks (excluding exact min/max)
    # closest_min_idx = np.where(new_ticks != y_min, dist_to_min, np.inf).argmin()
    # closest_max_idx = np.where(new_ticks != y_max, dist_to_max, np.inf).argmin()

    # # Mask out the closest ticks
    # mask = np.ones_like(new_ticks, dtype=bool)
    # mask[closest_min_idx] = False
    # mask[closest_max_idx] = False

    # # Apply mask and update ticks
    # filtered_ticks = new_ticks[mask]
    # axes[2,0].set_yticks(filtered_ticks)



    # Add horizontal and vertical marker lines for active power
    if p_recovery_time_sec < 9999:
            axes[0,0].axvline(x=recovered_time,color = COLOUR_PALLET[0], linestyle='--',lw=1.0)
    axes[0,0].axhline(y=p_recovery_threshold,color = COLOUR_PALLET[0], linestyle='--',lw=1.0,label=f"RECOVERY:{round(p_recovery_time_sec*1000,2)}ms")
    axes[0,0].axvline(x=fault_clearance_time,color = COLOUR_PALLET[3], linestyle='--',lw=1.0,label=f"Fault Clearance Time:{round(fault_clearance_time,2)}s")
    axes[0,0].legend(frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=3,prop={'size': 8})
    axes[0,0].grid(True)

    # Add horizontal and vertical marker lines for iq
    axes[1,0].axhline(y=iq_settling_upper_limit,color = COLOUR_PALLET[0], linestyle='--',lw=1.0)
    axes[1,0].axhline(y=iq_settling_lower_limit,color = COLOUR_PALLET[0], linestyle='--',lw=1.0)
    axes[1,0].axvline(x=iq_settled_time,color = COLOUR_PALLET[0], linestyle='--',lw=1.0,label=f"SETTLE:{round(iq_settle_time_s*1000,2)}ms")

    axes[1,0].axvline(x=iq_rise_upper_limit_time_s,color = COLOUR_PALLET[1], linestyle='--',lw=1.0)
    axes[1,0].axvline(x=iq_rise_lower_limit_time_s,color = COLOUR_PALLET[1], linestyle='--',lw=1.0, label=f"RISE:{round(iq_rise_time_s*1000,2)}ms")

    axes[1,0].legend(frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=3,prop={'size': 8})
    axes[1,0].grid(True)


    axes[2,0].axvline(x=fault_inception_time,color = COLOUR_PALLET[3], linestyle='--',lw=1.0,label=f"Fault Inception Time:{round(fault_inception_time,2)}s")
    axes[2,0].axvline(x=fault_clearance_time,color = COLOUR_PALLET[3], linestyle='--',lw=1.0,label=f"Fault Clearance Time:{round(fault_clearance_time,2)}s")
    axes[2,0].legend(frameon = False,loc = "lower left", bbox_to_anchor=(0.0, 1.0), ncol=3,prop={'size': 8})
    axes[2,0].grid(True)


    plt.savefig(output_png_path)
    plt.clf()
    plt.close()

    plt.close()


        

