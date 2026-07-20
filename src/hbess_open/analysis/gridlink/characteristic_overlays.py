import os
from typing import List, Tuple, Optional, Callable, Dict
import matplotlib.pyplot as plt
import numpy as np

def make_characteristic_overlay(
        output_path : str,
        points : List[Tuple],
        saturated_points : Optional[List[Tuple]],
        characteristic_points : List[Tuple],
        nas_characteristic_points : Optional[List[Tuple]] = [],
        title : Optional[str] = None,
        x_label : Optional[str] = None,
        y_label : Optional[str] = None,
        points_colour : Optional[str] = 'blue',
        points_label : Optional[str] = 'Unsaturated measurements',
        points_additional_args : Optional[Dict] = None,
        saturated_points_colour : Optional[str] = 'gray',
        saturated_points_label : Optional[str] = 'Saturated measurements',
        saturated_points_additional_args : Optional[Dict] = None,
        characteristic_colour : Optional[str] = 'black',
        characteristic_label : Optional[str] = "Characteristic",
        characteristic_additional_args : Optional[Dict] = None,
        nas_characteristic_colour : Optional[str] = 'black',
        nas_characteristic_label : Optional[str] = "Characteristic",
        nas_characteristic_additional_args : Optional[Dict] = None,
        show_legend : bool = True,
        show_grid : bool = True,
        plt_callback : Optional[Callable] = None,
        minimum_diq_dv_gradient_neg: Optional[float] = None,
        ):
    plt.clf()
    plt.close()
    
    if len(points) > 0:
        x_points, y_points = zip(*points)
        extra_args = {} if points_additional_args is None else points_additional_args
        plt.scatter(
                x_points, 
                y_points, 
                color=points_colour, 
                label=points_label,
                **extra_args
                )

    if saturated_points is not None and len(saturated_points) > 0:
        x_off_points, y_off_points = zip(*saturated_points)
        extra_args = {} if saturated_points_additional_args is None else saturated_points_additional_args
        plt.scatter(
            x_off_points,
            y_off_points,
            color=saturated_points_colour,
            label=saturated_points_label,
            facecolors='none',
            **extra_args,
        )

    x_char_points, y_char_points = zip(*characteristic_points)
    extra_args = {} if characteristic_additional_args is None else characteristic_additional_args
    plt.plot(
        x_char_points,
        y_char_points,
        color=characteristic_colour,
        label=characteristic_label,
        **extra_args,
    )

    if len(nas_characteristic_points) > 0:
        x_nas_char_points, y_nas_char_points = zip(*nas_characteristic_points)
        extra_nas_args = {} if nas_characteristic_additional_args is None else nas_characteristic_additional_args
        plt.plot(
            x_nas_char_points,
            y_nas_char_points,
            color=nas_characteristic_colour,
            label=nas_characteristic_label,
            **extra_nas_args,
        )

    if minimum_diq_dv_gradient_neg is not None:
        x_intercept = 0
        x = np.linspace(0,1,100)
        y = minimum_diq_dv_gradient_neg *(x-x_intercept)

        plt.plot(x,y,label='Proposed Access Standard')


        

    if x_label is not None:
        plt.xlabel(x_label)
    if y_label is not None:
        plt.ylabel(y_label)
    
    if title is not None:
        plt.title(title)

    if show_legend:
        plt.legend()

    plt.grid(show_grid)

    if plt_callback is not None:
        plt_callback(plt)

    output_dir = os.path.dirname(output_path)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    plt.savefig(output_path)

    plt.clf()
    plt.close()
