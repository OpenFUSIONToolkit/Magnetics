# -*-Python-*-
# Created by logannc at 02 Mar 2017  23:26
"""
This script plots the time series of each channel meeting the designated regular expression criterion.

Parameters

------------

:param keys: list. Name of a fit Dataset(s) from INPUTS.

:param channel_filter: string. Only channels with names matching this regular expression are shown.

:param axes: list. Axes objects for each key's plot. If None, a new figure and subplots are made.

:param legend_maxnum: int. Maximum number of lines to include in the legend.

:param kwargs: dictionary. Key word arguments passed to the axes plot methods.

:param plot_style: string. Choose '1d', '2d' or 'view1d' for interactive 1D plots

:param exclude: bool.
    - True to plot only the included channels with good data
    - False to plot all seleted channels

"""
defaultVars(
    keys=['RAW', 'PREPARED'],
    channel_filter=root['SETTINGS']['PHYSICS'].get('channels', '.*'),
    axes=None,
    legend_maxnum=12,
    kwargs={},
    plot_style='view1d',
    exclude=True,
)

keys = [k for k in keys if k in root['INPUTS'] or k in root['OUTPUTS']['FIT']]
view_0 = None

if axes is None:
    f, axes = plt.subplots(len(keys), sharex=True, squeeze=False, figsize=(8, 4 * len(keys)))
else:
    f = np.ravel(np.atleast_1d(axes))[0].get_figure()
axes = np.ravel(np.atleast_1d(axes))

# speed up large signal plotting
plt.ioff()

for key, ax in zip(keys, axes):
    if key in root['INPUTS']:
        ds = root['INPUTS'][key]
        if key == 'PREPARED':
            d2 = root['INPUTS']['RAW']
        else:
            d2 = None
    else:
        ds = root['OUTPUTS']['FIT'][key]
        if key == 'PREPARED':
            d2 = root['OUTPUTS']['FIT']['RAW']
        else:
            d2 = None

    channels = [k for k in ds['channel'].values if re.match(channel_filter, k)]
    if exclude and 'PREPARED' in root['INPUTS']:
        for channel in list(channels):
            if channel not in root['INPUTS']['PREPARED']['channel'].values:
                channels.remove(channel)
            elif channel in root['SETTINGS']['PHYSICS']['fit_exclude']:
                channels.remove(channel)

    if plot_style == '1d':
        ptps, lines = [], []
        for c in channels:
            s = ds['signal'].sel(channel=c)
            # only plot signals with data
            s_ptp = np.ptp(np.nan_to_num(s.values))
            if s_ptp > 0:
                kwargs1 = dict(**kwargs)
                # overplot the raw data matched at t0 for a clear comparison to assess filtering
                if d2 is not None:
                    kwargs2 = dict(**kwargs)
                    kwargs2['alpha'] = kwargs.get('alpha', 1.0) * 0.5
                    s2 = 1.0 * d2['signal'].sel(channel=c, time=s['time'])
                    s2 = s2 - (s2.values[0] - s.values[0])
                    (l,) = s2.plot(ax=ax, label=c, **kwargs2)
                    kwargs1['color'] = l.get_color()
                (l,) = s.plot(ax=ax, label=c, **kwargs1)
                lines.append(l)
                ptps.append(s_ptp)
            else:
                printe("{:} has no signal".format(c))

        # limit legend
        if len(ptps):
            ptps, lines = zip(*sorted(zip(ptps, lines)))
            nleg = min(legend_maxnum, len(lines))
            for l in lines[nleg:]:
                l.set_color('grey')
                l.set_alpha(0.4)
            ax.legend(
                lines[:nleg],
                [l.get_label() for l in lines[:nleg]],
                loc=2,
                ncol=max(1, nleg // 5),
                frameon=False,
                text_same_color=True,
                hide_markers=True,
            )

    elif plot_style == '2d':
        s = ds['signal'].sel(channel=channels)
        im = s.plot(ax=ax)

    elif plot_style.lower() == 'view1d':
        ax.set_downsampling(1e99)  # View1d doesn't play well with this? Or just memory error?
        if 'signal' in ds:
            s = ds['signal'].sel(channel=channels).rename(key + ' signal')
            # hacks reducing data to stop crashing omfit
            if 'PREPARED' in root['INPUTS']:
                s = s.sel(time=root['INPUTS']['PREPARED']['time'])  # todo: generalize: what if plotting multiply OUTPUTS?
            safe = 2e3
            if len(s['time']) > safe:
                step = int(ceil(len(s['time']) / safe))
                print("WARNING: Downsampling by {:} for quick interactive plots".format(step))
                s = s.sel(time=s['time'][::step])

            # interactive view
            v = View1d(s, dim='time', axes=ax, channel=0, plot_options=kwargs)
            if view_0 is None:
                view_0 = v
            else:
                view_0.link(v)
            # overplot the raw data matched at t0 for a clear comparison to assess filtering
            if d2 is not None:
                kwargs2 = dict(**kwargs)
                kwargs2['alpha'] = kwargs.get('alpha', 1.0) * 0.5
                s2 = 1.0 * d2['signal'].sel(channel=s['channel'], time=s['time']).rename('Shifted RAW signal')
                s2 = s2 - (s2.values[:, 0] - s.values[:, 0])[:, None]
                kwargs2['color'] = ax.lines[-1].get_color()
                v2 = View1d(s2, dim='time', axes=ax, channel=0, plot_options=kwargs2)
                view_0.link(v2)

            ax.set_ylim(s.min(), s.max())
            printi('Use arrow keys to navigate plot through channels')
        if 'vacuum' in ds:
            s = ds['vacuum'].sel(channel=channels).rename(key + ' vacuum')
            v = View1d(s, dim='time', axes=ax, channel=0)
            if view_0 is None:
                view_0 = v
            else:
                view_0.link(v)

    ax.set_title(key)
    ax.set_xlim(ds['time'][0], ds['time'][-1])

plt.ion()

ax.get_figure().tight_layout()

cornernote(device=ds.attrs['device'], shot=ds.attrs['shot'], time='', text=key)
