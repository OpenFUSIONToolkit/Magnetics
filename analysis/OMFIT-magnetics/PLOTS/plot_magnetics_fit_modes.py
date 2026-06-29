# -*-Python-*-
# Created by logannc at 02 Mar 2017  23:28
"""
This script plots the amplitude and phase of each mode of the chosen fit.

Parameters

------------

:param keys: list. Name of a fit Dataset(s) from OUTPUTS.

:param legend_maxnum: int. Maximum number of lines to include in the legend.

:param kwargs: dictionary. Key word arguments passed to the axes plot methods.

"""
defaultVars(keys=(root['SETTINGS']['PHYSICS'].get('fit_key', ''),), n_filter=(), m_filter=(), legend_maxnum=12, kwargs={}, axes=None)

printi("Plotting modes")

if axes is None:
    fig, axes = plt.subplots(2, sharex=True, figsize=(8, 8))
else:
    assert shape(axes) == (2,), "Requires 2 axes"
    fig = axes[0].get_figure()

for key in keys:
    ds = root['OUTPUTS']['FIT'][key]

    max_amp = np.max([np.percentile(np.abs(ds['fit_coeffs']).sel(mode=m), 90) for m in ds['mode']])
    for i, m in enumerate(ds['mode']):
        if len(n_filter) and ds['fit_ns'].values[m] not in n_filter:
            continue
        elif len(m_filter) and ds['fit_ms'].values[m] not in m_filter:
            continue
        coeff = ds['fit_coeffs'].sel(mode=m)
        sigma = ds['fit_sigmas'].sel(mode=m)
        label = '{:}/{:}'.format(ds['fit_ms'].values[i], ds['fit_ns'].values[i])
        if len(keys) > 1:
            label = key + ' ' + label
        c, s = np.real(coeff), np.imag(coeff)
        ec, es = np.real(sigma), np.imag(sigma)
        uamp = unumpy.sqrt(unumpy.uarray(s, es) ** 2 + unumpy.uarray(c, ec) ** 2)
        uphase = unumpy.arctan2(unumpy.uarray(s, es), unumpy.uarray(c, ec)) * (180 / np.pi)
        (l,) = uband(ds['time'], uamp, label=label, ax=axes[0])
        if np.percentile(np.abs(coeff), 90) > 0.1 * max_amp:  # don't clutter phase plot with wild phases of small amplitude modes
            (l,) = uband(ds['time'], uphase, label=label, ax=axes[1], color=l.get_color())

    abs_max = [np.max(np.abs(l.get_ydata())) for l in axes[0].lines]
    for ax in axes:
        aptps, indxs, lines = zip(*sorted(zip(abs_max, list(range(len(ax.lines))), ax.lines))[::-1])
        nleg = min(legend_maxnum, len(lines))
        for l in lines[nleg:]:
            l.set_alpha(0.4)
        if ax is axes[0]:
            handles = [ax.lines[i] for i in sorted(indxs[:nleg])]
            labels = [ax.lines[i].get_label() for i in sorted(indxs[:nleg])]
            if all([lbl.startswith('0/') for lbl in labels]):
                leg_title = 'n'
                labels = [lbl.replace('0/', '') for lbl in labels]
            else:
                leg_title = 'm/n'
            if len(keys) == 1:
                title = key + ' m/n'
            else:
                title = 'Fit m/n'
            leg = ax.legend(
                handles, labels, loc=2, ncol=1 + (nleg > 5), title=leg_title, text_same_color=True, hide_markers=True, frameon=False
            )
            leg.draggable(True)
        ax.set_title('')

    axes[0].set_title(key)
    axes[0].set_ylabel('Amplitude')
    axes[0].autoscale('y')
    axes[0].set_ylim(ymin=0)
    axes[1].set_ylabel('Phase (deg)')
    axes[1].set_xlabel('Time (sec)')
    axes[1].set_ylim(-180, 180)
    axes[1].set_yticks([-180, -90, 0, 90, 180])

cornernote(device=ds.attrs['device'], shot=ds.attrs['shot'], time='', text=key, ax=axes[1])

fig.tight_layout()
