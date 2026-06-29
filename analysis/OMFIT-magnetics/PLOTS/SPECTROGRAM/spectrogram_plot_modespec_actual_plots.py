'''
script to do the actual plotting that can be called by any script.
The purpose of this script is to keep one script that does the
plotting of the spectrogram but the possibility to plot it in several figures as needed
'''

# import OMFITlib_spectrogram_utilities as spec_utils


def plot_rms(FFT_data, ax=None, plotting_parameters=None, xlabel=None, ylabel=None, plot_cn=False):

    if ax is None:
        fig, ax = subplots(1, 1)

    t = FFT_data['time']
    n = FFT_data['n']
    rms = FFT_data['rms']
    integ = FFT_data['integ']

    print('plotting rms...')

    ns_of_n = np.size(n)
    possible_colors = cm.get_cmap('tab20', ns_of_n).colors

    if plotting_parameters is None:
        col_set = []
        for nn, pc in zip(n, possible_colors):

            if nn == 1:
                color = matplotlib.colors.to_rgba('k')
            elif nn == 2:
                color = matplotlib.colors.to_rgba('r')
            elif nn == 3:
                color = matplotlib.colors.to_rgba('g')
            elif nn == 4:
                color = matplotlib.colors.to_rgba('b')
            else:
                color = pc
            col_set.append(color)
        nrange = n

    else:

        nrange = plotting_parameters['nrange']
        col_set = plotting_parameters['ncolor']

    colors = np.zeros((len(n), 4))
    for nn, pc in zip(nrange, col_set):
        (ind,) = np.where(nn == np.array(n))

        if isinstance(pc, str):
            colors[ind] = matplotlib.colors.to_rgba(pc)
        else:
            colors[ind] = pc

    for nn, rr, color in zip(n, rms.T, colors):
        if nn in nrange:
            ax.plot(t, rr, color=color)

    if ylabel is None:
        if integ:
            ax.set_ylabel('rms B [T]')
        else:
            ax.set_ylabel('rms dB/dt [T/s]')
    else:
        ax.set_ylabel(ylabel)

    if xlabel is None:
        ax.set_xlabel('time [s]')
    else:
        ax.set_xlabel(xlabel)

    if plot_cn:
        cndev = root['SETTINGS']['EXPERIMENT']['device']
        shot = FFT_data['shot']
        if (device == 'NSTX') & (shot > 200000):
            cndev = 'NSTX-U'
        cornernote(device=cndev, shot=shot)


def plot_spectrogram(
    FFT_data,
    fig=None,
    ax=None,
    prop_to_power=True,
    plotting_parameters=None,
    lu=20,
    log_levels=False,
    min_level=0,
    max_level=1,
    xlabel='time [s]',
    ylabel='frequency [kHz]',
    plot_cn=False,
    add_cbar=True,
    device=root['SETTINGS']['EXPERIMENT']['device'],
):

    if (ax is not None) & (fig is None) & (add_cbar is True):
        printe('A figure must be specified to add the colorbar on an existing axis.')
        add_cbar = False
    if ax is None:
        fig, ax = subplots(1, 1)

    t = FFT_data['time']
    f = FFT_data['frequency']
    mode = FFT_data['mode']
    power = FFT_data['power']
    n = FFT_data['n']
    rms = FFT_data['rms']
    integ = FFT_data['integ']

    print('plotting spectrogram...')

    ns_of_n = np.size(n)
    possible_colors = cm.get_cmap('tab20', ns_of_n).colors

    if plotting_parameters is None:
        col_set = []
        for nn, pc in zip(n, possible_colors):

            if nn == 1:
                color = matplotlib.colors.to_rgba('k')
            elif nn == 2:
                color = matplotlib.colors.to_rgba('r')
            elif nn == 3:
                color = matplotlib.colors.to_rgba('g')
            elif nn == 4:
                color = matplotlib.colors.to_rgba('b')
            else:
                color = pc
            col_set.append(color)
        nrange = n

    else:

        nrange = plotting_parameters['nrange']
        col_set = plotting_parameters['ncolor']

    colors = np.zeros((len(n), 4))
    for nn, pc in zip(nrange, col_set):
        (ind,) = np.where(nn == np.array(n))

        if isinstance(pc, str):
            colors[ind] = matplotlib.colors.to_rgba(pc)
        else:
            colors[ind] = pc

    if prop_to_power:
        n = array(n)
        rms = array(rms)
        colors = array(colors)
        ind = argsort(abs(n))[::-1]
        for nn, rr, color in zip(n[ind], rms.T[ind], colors[ind]):
            ampgrid = 0.0 * power
            inds = np.where(mode == nn)
            if len(inds) > 1:
                ampgrid[inds] = power[inds]

                if log_levels:
                    levels = np.max(np.max(ampgrid)) * (logspace(min_level, max_level, lu, base=10))
                else:
                    levels = np.max(np.max(ampgrid)) * (linspace(min_level, max_level, lu))

                im = ax.contour(t, f * 1e-3, ampgrid.T, levels=levels[1:], linewidths=1.0, colors=[color])

    else:

        cmap = matplotlib.colors.ListedColormap(colors)
        levels = np.arange(min(n) - 0.5, max(n) + 1.5)
        im = ax.contourf(t, f * 1e-3, mode.T, levels=levels, cmap=cmap)

    if add_cbar:
        fig.subplots_adjust(right=0.9, wspace=0.3, left=0.1)
        axy = np.array(ax.get_position())
        cax = fig.add_axes([0.91, axy[0, 1], 0.02, axy[1, 1] - axy[0, 1]])

        cmap_cb = matplotlib.colors.ListedColormap(col_set)
        cbar = matplotlib.colorbar.ColorbarBase(cax, cmap=cmap_cb)

        den = 2 * len(nrange)
        ticks = (2 * np.array(nrange) - 1) / den
        ticks = np.linspace(0, 1, len(nrange), endpoint=False)
        den = (1 - ticks[-1]) / 2.0
        ticks += den

        cbar.set_ticks(ticks)
        cbar.set_ticklabels([str(n) for n in nrange])

        cbar.ax.set_title('n')

    if xlabel is not None:
        ax.set_xlabel(xlabel)

    if ylabel is not None:
        ax.set_ylabel(ylabel)

    if plot_cn:
        cndev = root['SETTINGS']['EXPERIMENT']['device']
        shot = FFT_data['shot']
        if (device == 'NSTX') & (shot > 200000):
            cndev = 'NSTX-U'
        cornernote(device=cndev, shot=shot)


def actual_spectrogram_plot(
    FFT_data, fig=None, prop_to_power=True, plotting_parameters=None, lu=20, log_levels=False, min_level=0, max_level=1
):

    shot = FFT_data['shot']
    if fig == None:
        fig = plt.figure()

    ax1 = fig.add_axes([0.1, 0.7, 0.8, 0.2])
    ax2 = fig.add_axes([0.1, 0.1, 0.8, 0.5], sharex=ax1)

    plot_rms(FFT_data, ax=ax1, plotting_parameters=plotting_parameters, xlabel='', ylabel=None, plot_cn=False)

    plot_spectrogram(
        FFT_data,
        fig=fig,
        ax=ax2,
        prop_to_power=prop_to_power,
        plotting_parameters=plotting_parameters,
        lu=lu,
        log_levels=log_levels,
        min_level=min_level,
        max_level=max_level,
        xlabel='time [s]',
        ylabel='frequency [kHz]',
        plot_cn=False,
        add_cbar=True,
    )

    ax1.set_title(shot, fontsize=16)
    return ax1, ax2
