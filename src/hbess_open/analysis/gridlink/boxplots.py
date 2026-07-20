import matplotlib.pyplot as plt


def make_boxplot(
        groupby_str_for_plot_title: str,
        figure_title: str,
        output_png_path: str,
        data: list[list],
        xtick_labels: list,
        ylabel_title: str
    ):
        if groupby_str_for_plot_title is not None:
            title_suffix = f" ({groupby_str_for_plot_title})"
        else:
            title_suffix = ""

        fig, ax = plt.subplots(nrows=1, ncols=1, figsize=(6, 5), sharex=False)
        plt.subplots_adjust(left=0.25, right=0.90, bottom=0.1, top=0.90, wspace=0.18, hspace=0.28)
        
        plt.title(figure_title+title_suffix,loc='center',pad=10)
        ax.grid(True)

        # ax[0].set_title("Iq Sequence Contributions"+title_suffix,pad=10)
        ax.boxplot(data,vert=True,widths=0.4)
        ax.set_xticklabels([f"{xtick_labels[i]}\n(n={len(data[i])})" for i in range(0,len(xtick_labels))])
        ax.set_ylabel(ylabel_title, size=20, labelpad=10)

        plt.savefig(output_png_path)
        plt.clf()