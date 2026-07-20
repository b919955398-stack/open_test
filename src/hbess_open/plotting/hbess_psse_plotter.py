"""
Open Heywood BESS PSS/E plotter.

This is the supplied project plotter with its only Pallet dependency removed.

Note:
The plotter requires that there is column in the excel spec sheet named "Plotter Table" in order to populate the table. Otherwise, there will be a table with no relevant information provided


"""


from typing import Optional, Union, Dict, List, Callable
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.gridspec as gridspec
import pandas as pd
import numpy as np
from matplotlib.table import Cell, Table
import textwrap as twp
from dataclasses import dataclass
import warnings
import os
import sys
import ast
import re



class HbessPssePlotter(object):
    def __init__(
        self, 
        pre_process_fn: Optional[Callable] = None
    ):
        self.pre_process_fn = pre_process_fn
   
    def plot_from_df_and_dict(
            self,
            df: pd.DataFrame,
            scenario_dict: Optional[Dict] = None,
            png_path: Optional[Union[str, Path]] = None,
            pdf_path: Optional[Union[str, Path]] = None,
    ):
        if self.pre_process_fn is not None:
            #print(df.columns)
            df = self.pre_process_fn(df)



        plt.clf()
        plt.close()
        col_pallet = ["#ab427a",
                "#96b23d",
                "#6162b9",
                "#ce9336",
                "#bc6abc",
                "#5aa554",
                "#ba4758",
                "#46c19a",
                "#b95436",
                "#9e8f41"]
        
        #Col Pallet with less green and red 
        # col_pallet = [
        #     "#00429d",  # Deep Blue (kept, good contrast)
        #     "#ffb703",  # Bright Amber (contrast with Deep Blue)
        #     "#118ab2",  # Cyan (kept, suitable for accessibility)
        #     "#264653",  # Dark Blue-Green (kept, works well for contrast)
        #     "#6a4c93",  # Muted Purple (accessible and distinct)
        #     "#ff6700",  # Vivid Orange (replaces mustard yellow for contrast)
        #     "#2a9d8f",  # Teal (good for accessibility)
        #     "#e76f51",  # Coral Red (replaces bright yellow, less ambiguous)
        #     "#6c757d",  # Gray-Blue (kept, neutral tone)
        #     "#dda15e"   # Warm Gold (replaces yellow gold, accessible)
        # ]

        
       
        # df = df[df.index > self.remove_first_seconds]
        # df.index = df.index - self.remove_first_seconds

# -------------------------------------------------SUBPLOT CREATION ------------------------------------------------------
        fig, axes = plt.subplots(5, 3, figsize=(10, 12),squeeze = False, sharex=True)
        cm = 1 / 2.54
        fig.set_size_inches(42 * cm, 29.7 * cm)  # A4 Size Landscape.
        fig.suptitle(scenario_dict["File_Name"],fontweight = 'bold')
        fig.subplots_adjust(left=0.05, right=0.95, bottom=0.05, top=0.9, wspace=0.2, hspace=0.3)
        axes[0,0].set_title("POC",loc = 'center',fontsize=13, pad=12)
        axes[0,1].set_title("INV", loc = 'center',fontsize=13, pad=12)
        axes[1,2].set_title('MISC',loc='center',fontsize=13, pad=12)
        axes[0][2].axis('off')

#------------------- ---------------------------------POC PLOTS -----------------------------------------------------------
        # [0, 0] POC active power
        scaling = [1.0,1.0]
        axes[0,0].plot(df.index, df["PPOC_REF_MW"] * scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        axes[0,0].xaxis.set_label_position('top')
        axes[0,0].plot(df.index, df["PPOC_MW"] * scaling[1], color=col_pallet[1], label='MEAS',linewidth=1.5, alpha =0.85)

        axes[0,0].set_xlabel("Active Power (MW)",loc="left")
        axes[0,0].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[0,0].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[0,0]
        ax.set_facecolor((0.98,0.98,0.98,0.8))
        # min_val = (df["PPOC_MW"] * scaling[1]).min()
        # max_val = (df["PPOC_MW"] * scaling[1]).max()

        min_val = min(
            (df["PPOC_REF_MW"] * scaling[0]).min(),
            (df["PPOC_MW"] * scaling[1]).min()
            )
        max_val = max(
            (df["PPOC_REF_MW"] * scaling[0]).max(),
            (df["PPOC_MW"] * scaling[1]).max()
            )
        ax.set_ylim(min_val-10,max_val+10)

        # [1,0] POC Reactive power
        scaling = [1.0,1.0]
        # axes[1,0].plot(df.index, df["PWRRTSPNTTOT"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        #axes[1,0].plot(df.index, df["QREF_MVAR"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        axes[1,0].xaxis.set_label_position('top')
        axes[1,0].plot(df.index, df["QPOC_REF_MVAR"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        # axes[1,0].plot(df.index, df["QLCLCMD"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        # axes[1,0].plot(df.index, df["QRMTMEAS"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        # axes[1,0].plot(df.index, df["QREFINT"]*scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        axes[1,0].plot(df.index, df["QPOC_MVAR"]*scaling[1], color=col_pallet[1], label='MEAS',linewidth=1.5, alpha =0.85)
        # axes[0,0].plot(df.index, df["PPOC_REF_MW"] * scaling[0], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        axes[1,0].set_xlabel("Reactive Power (MVAr)",loc="left")
        axes[1,0].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[1,0].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[1,0]
        ax.set_facecolor((0.98,0.98,0.98))   
        # min_val = (df["QPOC_MVAR"] * scaling[1]).min()
        # max_val = (df["QPOC_MVAR"] * scaling[1]).max()
        min_val = min(
            (df["QPOC_REF_MVAR"] * scaling[0]).min(),        
            (df["QPOC_MVAR"] * scaling[1]).min()
            )
        max_val = max(
            (df["QPOC_REF_MVAR"] * scaling[0]).max(),
            (df["QPOC_MVAR"] * scaling[1]).max()
            )
        ax.set_ylim(min_val-2,max_val+2)

        # [2,0] POC Voltage  
        axes[2,0].plot(df.index, df["V_POC_REF_PU"], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        # axes[2,0].plot(df.index, df["V_POC_REF_PU_2"], color=col_pallet[2], label='REF',linestyle="dashed",linewidth=1.5)
        # axes[2,0].plot(df.index, df["V_POC_REF_PU_3"]*1.06, color=col_pallet[3], label='REF',linestyle="dashed",linewidth=1.5)
        axes[2,0].plot(df.index, df["V_POC_PU"], color=col_pallet[1], label='MEAS',linewidth=1.5, alpha =0.85)
        axes[2,0].xaxis.set_label_position('top')
     
        axes[2,0].set_xlabel("Voltage (pu)",loc="left")
        axes[2,0].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[2,0].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[2,0]
        ax.set_facecolor((0.98,0.98,0.98))   
        min_val =min(df["V_POC_PU"].min(), df["V_POC_REF_PU"].min())
        max_val =max(df["V_POC_PU"].max(), df["V_POC_REF_PU"].max())
        ax.set_ylim(min_val-0.012,max_val+0.012)


        # [3,0] Active Current (pu) 
        axes[3,0].plot(df.index, df["POC_Id_PU_max_cont"], color=col_pallet[1], label='Id',linewidth=1.5)
        axes[3,0].xaxis.set_label_position('top')

        axes[3,0].set_xlabel("Active Current (pu)",loc="left")
        axes[3,0].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[3,0].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[3,0]
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = df["POC_Id_PU_max_cont"].min()
        max_val = df["POC_Id_PU_max_cont"].max()
        ax.set_ylim(min_val-0.1,max_val+0.1)



        # [4,0] Reactive Current (pu) 
        axes[4,0].plot(df.index, df["POC_Iq_PU_max_cont"], color=col_pallet[1], label='Iq',linewidth=1.5)
        axes[4,0].xaxis.set_label_position('top')

        axes[4,0].set_xlabel("Reactive Current (pu)",loc="left")
        axes[4,0].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[4,0].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[4,0]
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = df["POC_Iq_PU_max_cont"].min()
        max_val = df["POC_Iq_PU_max_cont"].max()
        ax.set_ylim(min_val-0.1,max_val+0.1)

#-----------------------------------------INV PLOTS----------------------------------------------------------------
        # [0,1] INV active Power 
        #scaling = [-200.0,200.0]
        scaling = [105.8,105.8]
        axes[0,1].plot(df.index, df["PREF_MW"]*scaling[0], color=col_pallet[0], label='REF INV1',linestyle="dashed",linewidth=1.5)
        axes[0,1].plot(df.index, df["PMEAS_INV_PU"]*scaling[1], color=col_pallet[2], label='MEAS INV1',linewidth=1.5, alpha =0.85)
        axes[0,1].plot(df.index, df["PMEAS_INV2_PU"]*scaling[1], color=col_pallet[3], label='MEAS INV2',linewidth=1.5, alpha =0.85)
        axes[0,1].plot(df.index, df["PMEAS_INV3_PU"]*scaling[1], color=col_pallet[4], label='MEAS INV3',linewidth=1.5, alpha =0.85)
        axes[0,1].plot(df.index, df["PMEAS_INV4_PU"]*scaling[1], color=col_pallet[5], label='MEAS INV4',linewidth=1.5, alpha =0.85)
        axes[0,1].xaxis.set_label_position('top')

        axes[0,1].set_xlabel("Active Power (MW)",loc="left")
        axes[0,1].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[0,1].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[0,1]
        ax.set_facecolor((0.98,0.98,0.98))
   
        # min_val = (df["PMEAS_INV_PU"] * scaling[1]).min()
        # max_val = (df["PMEAS_INV_PU"] * scaling[1]).max()

        min_val = min(
            (df["PREF_MW"] * scaling[0]).min(),
            (df["PMEAS_INV_PU"] * scaling[1]).min()
            )
        max_val = max(
            (df["PREF_MW"] * scaling[0]).max(),
            (df["PMEAS_INV_PU"] * scaling[1]).max()
            )
        ax.set_ylim(min_val-2,max_val+2)



        # [1,1] INV reactive Power 
        #scaling= [105.84, 103.32, 100.0, 100.0]
        scaling = [63.48,63.48,105.8]
        
        axes[1,1].plot(df.index, df["QINV_REF_MVAR"]*scaling[0], color=col_pallet[5], label='REF INV1',linestyle="dashed",linewidth=1.5)
        # axes[1,1].plot(df.index, df["QINV_OUT"]*scaling[1], color=col_pallet[0], label='REF INV1_DROOP',linestyle="dashed",linewidth=1.5)
        # axes[1,1].plot(df.index, df["QINV_OUT_2"]*scaling[1], color=col_pallet[0], label='REF INV1_DROOP_2',linestyle="dashed",linewidth=1.5)
        axes[1,1].xaxis.set_label_position('top')
        axes[1,1].plot(df.index, df["QMEAS_INV_PU"]*scaling[2], color=col_pallet[2], label='MEAS INV1',linewidth=1.5, alpha =0.85)
        axes[1,1].plot(df.index, df["QMEAS_INV2_PU"]*scaling[2], color=col_pallet[3], label='MEAS INV2',linewidth=1.5, alpha =0.85)
        axes[1,1].plot(df.index, df["QMEAS_INV3_PU"]*scaling[2], color=col_pallet[4], label='MEAS INV3',linewidth=1.5, alpha =0.85)
        axes[1,1].plot(df.index, df["QMEAS_INV4_PU"]*scaling[2], color=col_pallet[5], label='MEAS INV4',linewidth=1.5, alpha =0.85)
        axes[1,1].set_xlabel("Reactive Power (MVAr)",loc="left")
        axes[1,1].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[1,1].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[1,1]
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = min(
            (df["QINV_OUT"] * scaling[0]).min(),
            (df["QINV_OUT_2"] * scaling[0]).min(),  
            (df["QMEAS_INV3_PU"] * scaling[0]).min(),
            (df["QMEAS_INV4_PU"] * scaling[0]).min(),         
            (df["QMEAS_INV_PU"] * scaling[2]).min()
            )
        max_val = max(
            (df["QINV_OUT"] * scaling[0]).max(),
            (df["QINV_OUT_2"] * scaling[0]).max(),  
            (df["QMEAS_INV3_PU"] * scaling[0]).max(),
            (df["QMEAS_INV4_PU"] * scaling[0]).max(), 
            (df["QMEAS_INV_PU"] * scaling[2]).max()
            )
        ax.set_ylim(min_val-2,max_val+2)

        # min_val = min(
        #     (df["INV1_QMEAS_PU"] * scaling[2]).min(),
        #     (df["INV1_Q_CV_PU"] * scaling[0]).min(),
        # )
        # min_val =(df["QINV_REF_MVAR"] * scaling[2]).min()
        # max_val =(df["QINV_REF_MVAR"] * scaling[2]).max()
 
        # max_val = max((df["INV1_QMEAS_PU"] * scaling[0]).max(),(df["INV2_QMEAS_PU"] * scaling[1]).max(),(df["QREF_MVAR_INV"] * scaling[2]).min())

        # [2,1] INV voltage - V referebce is disabled due to the control mode M+5 is set to 5. It will be enabled when it's set to 1.

        # axes[2,1] .plot(df.index, df["V_INV_REF_PU"], color=col_pallet[0], label='REF',linestyle="dashed",linewidth=1.5)
        axes[2,1] .plot(df.index, df["V_HYBESS_PU"], color=col_pallet[0], label='INV1 Vrms',linewidth=1.5)
        axes[2,1] .xaxis.set_label_position('top')
        axes[2,1] .plot(df.index, df["V_HYBESS_PU"], color=col_pallet[0], label='INV1 Vrms',linewidth=1.5)
        axes[2,1] .xaxis.set_label_position('top')
       
        axes[2,1] .set_xlabel("Voltage (pu)",loc="left")
        axes[2,1] .legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[2,1] .grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[2,1] 
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = (df["V_HYBESS_PU"].min())
        max_val = (df["V_HYBESS_PU"].max())
        ax.set_ylim(min_val-0.05,max_val+0.05)



        #[3,1] Active Current (pu)
        axes[3,1].xaxis.set_label_position('top')
        # axes[3,1].plot(df.index, df["INV1_ID_COMMAND_PU"], color=col_pallet[0], label="REF INV1", linestyle = 'dashed', linewidth=1.5)
        axes[3,1].plot(df.index, df["INV1_Id_PU"], color=col_pallet[1], label='MEAS INV1',linewidth=1.5, alpha =0.85)
      
        axes[3,1].set_xlabel("Active Current (pu)",loc="left")
        axes[3,1].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 6, ncol=2)
        axes[3,1].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[3,1]
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = (df["INV1_Id_PU"].min())
        max_val = (df["INV1_Id_PU"].max())
        ax.set_ylim(min_val-0.1,max_val+0.1)

        #[4,1] Reactive Current (pu)
        axes[4,1].xaxis.set_label_position('top')
        #axes[4,1].plot(df.index, df["INV1_VUEL_PU"], color=col_pallet[0], label='REF INV1', linestyle = 'dashed', linewidth=1.5)
        axes[4,1].plot(df.index, df["INV1_Iq_PU"], color=col_pallet[1], label='MEAS INV1',linewidth=1.5, alpha =0.85)

        axes[4,1].set_xlabel("Reactive Current (pu)",loc="left")
        axes[4,1].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[4,1].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[4,1]
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = (df["INV1_Iq_PU"].min())
        max_val = (df["INV1_Iq_PU"].max())
        # min_val = df["IQ_MEAS"].min()
        # max_val = df["IQ_MEAS"].max()
        ax.set_ylim(min_val-0.1,max_val+0.1)

        #------------------------------------------------------ MISC PLOTS ---------------------------------------------------

        # [1,2] Main TX OLTC 
        if "PhaseStep" in str(png_path):
            axes[1,2].plot(df.index, df["HYBESS_V_POC_ANG"], color=col_pallet[0], label='POC',linewidth=1.5)
            axes[1,2].xaxis.set_label_position('top')
            axes[1,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
       
            axes[1,2].set_xlabel("Voltage Phase Angle POC (deg)",loc="left")
            axes[1,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
           
            ax = axes[1,2]
            ax.set_facecolor((0.98,0.98,0.98))
            min_val = df["HYBESS_V_POC_ANG"].min()
            max_val = df["HYBESS_V_POC_ANG"].max()
            ax.set_ylim(min_val-10,max_val+10)
        else:
            axes[1,2].plot(df.index, df["Main_Tx_HVMV_Ratio"], color=col_pallet[0], label='TAP NUMBER',linewidth=1.5)
            axes[1,2].xaxis.set_label_position('top')

            axes[1,2].set_xlabel("Main TX OLTC",loc="left")
            axes[1,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
            axes[1,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
            ax = axes[1,2]
            ax.set_facecolor((0.98,0.98,0.98))
            min_val = df["Main_Tx_HVMV_Ratio"].min()
            max_val = df["Main_Tx_HVMV_Ratio"].max()
            ax.set_ylim(min_val-0.1,max_val+0.1) 


        # # [2,2] FRT Flags

        axes[2,2].plot(df.index, df["HVRT_FLAG"], color=col_pallet[0], label='PPC HVRT',linewidth=1.5)
        axes[2,2].xaxis.set_label_position('top')

        axes[2,2].plot(df.index, df["LVRT_FLAG"], color=col_pallet[1], label='PPC LVRT',linewidth=1.5)
        axes[2,2].plot(df.index, df["INV_FRT"], color=col_pallet[2], label='INV FRT proxy',linewidth=1.5)        

        axes[2,2].set_xlabel("FRT Flags",loc="left")
        axes[2,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=3)
        axes[2,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        ax = axes[2,2] 
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = min(df["HVRT_FLAG"].min(),df["LVRT_FLAG"].min())
        max_val = max(df["HVRT_FLAG"].max(),df["LVRT_FLAG"].max())
        ax.set_ylim(min_val-2,max_val+2)

        #[3,2] Frequency (Hz)
        scaling = 50
        offset = 50
        axes[3,2].plot(df.index,df["POC_F_PU"]*scaling+offset, color=col_pallet[0], label='POC',linewidth=1.5)

        axes[3,2].xaxis.set_label_position('top')

        axes[3,2].set_xlabel("Frequency (Hz)",loc="left")
        axes[3,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[3,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
        freq = df["POC_F_PU"]*scaling + offset

        min_val = freq.min()
        max_val = freq.max()
        axes[3,2].set_ylim(min_val -2 , max_val +2)
        ax = axes[2,2] 
        ax.set_facecolor((0.98,0.98,0.98))


        #[4,2] RMS Current
        # axes[3,2].plot(df.index, df["Irms_HV_ pu"], color=col_pallet[0], label='POC',linewidth=1.5)
        # axes[3,2].xaxis.set_label_position('top')
        # axes[3,2].plot(df.index, df["INV1_Irms_LV_pu"], color=col_pallet[1], label='INV1 Irms pu',linewidth=1.5)
        
        # axes[3,2].set_xlabel("RMS Current (pu)",loc="left")
        # axes[3,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        # axes[3,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)

        # ax = axes[3,2] 
        # ax.set_facecolor((0.98,0.98,0.98))
        # min_val = min(df["Irms_HV_pu"].min(),df["INV1_Irms_LV_pu"].min())
        # max_val = max(df["Irms_HV_pu"].max(),df["INV1_Irms_LV_pu"].max())
        # ax.set_ylim(min_val-0.1,max_val+0.1)
        axes[4,2].plot(df.index, df["Irms_HV_pu"], color=col_pallet[0], label='POC',linewidth=1.5)
        axes[4,2].plot(df.index, df["INV1_Irms_LV_pu"], color=col_pallet[1], label='INV',linewidth=1.5)
        axes[4,2].xaxis.set_label_position('top')
    
        axes[4,2].set_xlabel("RMS Current (pu)",loc="left")
        axes[4,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
        axes[4,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
       
        ax = axes[4,2] 
        ax.set_facecolor((0.98,0.98,0.98))
        min_val = min(df["Irms_HV_pu"].min(),df["INV1_Irms_LV_pu"].min())
        max_val = max(df["Irms_HV_pu"].max(),df["INV1_Irms_LV_pu"].max())
        ax.set_ylim(min_val-0.1,max_val+0.1)



        #[4,2] Main TX HV/MV Ratio

            # axes[4,2].plot(df.index, df["Main_Tx_HVMV_Ratio"], color=col_pallet[0], label='HV/MV Ratio',linewidth=1.5)
            # axes[4,2].xaxis.set_label_position('top')
            
            # axes[4,2].set_xlabel("Main TX HV/MV Ratio",loc="left")
            # axes[4,2].legend(frameon = False, loc = 'lower right',bbox_to_anchor=(1.0,1.0),fontsize = 7, ncol=2)
            # axes[4,2].grid(True, linestyle=':', which = 'major', alpha=1,linewidth=1.2)
            # ax = axes[4,2]
            # ax.set_facecolor((0.98,0.98,0.98))
            # min_val = df["Main_Tx_HVMV_Ratio"].min()
            # max_val = df["Main_Tx_HVMV_Ratio"].max()
            # ax.set_ylim(min_val-2,max_val+2)





#----------------------------------------------- TABLE ------------------------------------------------------------
        data = []
        if "Plotter Table" in scenario_dict:
            if not pd.isna(scenario_dict["Plotter Table"]):
                try:
                    plotter_table = ast.literal_eval(scenario_dict["Plotter Table"])
                except (ValueError,SyntaxError)as e:
                    print(f"Error in literal_eval: {e}")
                    print("File Name:" ,scenario_dict["File_Name"], "Format of Plotter Table entry is incorrect")
                    plt.tight_layout()
                    plt.savefig(png_path, bbox_inches="tight")
                    plt.savefig(pdf_path, bbox_inches="tight")
                    plt.clf()
                    plt.close()
                    return
 
                if len(plotter_table) >0:
                    for item in range(len(plotter_table)):
                        try:
                            if plotter_table[item][0] == "X2R":
                                new_key = "X/R"
                                data.append({new_key: plotter_table[item][1]})
                            else:
                                data.append({plotter_table[item][0]: plotter_table[item][1]})
                        except Exception as e:
                            data.append({"Status": "Invalid entry"})
                            continue
                    if "software" in scenario_dict:
                        data.append({"Software": scenario_dict["software"]})   
                else:
                    data.append({"Status": "No data provided"})
        else:
            data.append({"Status": "Plotter Table column in Excel not provided"})

        ax = fig.add_subplot(5,3,3)
        rows = len(data)
        cols= 2

                
        for index,row in enumerate(data):
 
            ax.text(x=0, y=len(data)-index-1, s=list(row.keys())[0], va='center', ha='left', weight='bold', fontsize=8)
            ax.text(x=1.05, y=len(data)-index-1, s=list(row.values())[0], va='center', ha='left', fontsize=8)
 
        for row in range(rows):
            #row gridlines
            ax.plot(
                [0, cols + 1],
                [row -.5, row - .5],
                ls=':',
                lw='.5',
                c='grey'
            )
        #column highlight
        rect = patches.Rectangle(
            (0, -.5),  # bottom left starting position (x,y)
            1.0,  # width
            len(data),  
            ec='none',
            fc='grey',
            alpha=.2,
            zorder=-1
        )
        #header divider
        ax.plot([1, 1], [-.5, rows-0.5], lw='.5', c='black')
        ax.add_patch(rect)
        ax.axis('off')
              

        plt.tight_layout()
        plt.savefig(png_path, bbox_inches="tight")
        plt.savefig(pdf_path, bbox_inches="tight")
        plt.clf()
        plt.close()
                
