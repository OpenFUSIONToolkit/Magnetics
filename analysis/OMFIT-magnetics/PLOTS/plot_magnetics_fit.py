# -*-Python-*-
# Created by logannc at 02 Mar 2017  23:27
"""
This script plots an overview of the fit accuracy. Plots include
- The temporal evolution of the reduced chi-squared (should be ~1)
- The original signals (for context)
- The worst channel residuals (should be much smaller than the original values)

Parameters

------------

:param key: string. Name of a fit Dataset(s) from OUTPUTS.

:param legend_maxnum: int. Maximum number of lines to include in the legend.

:param kwargs: dictionary. Key word arguments passed to the axes plot methods.

"""
defaultVars(key=root['SETTINGS']['PHYSICS'].get('fit_key', ''), legend_maxnum=6, kwargs={})

ds = root['OUTPUTS']['FIT'][key]

fig, axes = plt.subplots(3, sharex=True, figsize=(8, 10))

ds['red_chi_sq'].plot(ax=axes[0])
axes[0].axhline(1, color='k', lw=0.5)
axes[0].set_ylabel(r'Reduced $\chi^2$')

res_ptp = []
for c in ds['channel'].values:
    ds['signal'].sel(channel=c).plot(ax=axes[1], label=c)
    axes[1].set_ylabel('Signal')
    ds['residual'].sel(channel=c).plot(ax=axes[2], label=c)
    res_ptp.append(np.ptp(ds['residual'].sel(channel=c).values))
    axes[2].set_ylabel('Residual')

# concentrate on the worst residuals
for ax in axes[1:]:
    rptps, indxs, lines = zip(*sorted(zip(res_ptp, list(range(len(ax.lines))), ax.lines))[::-1])
    nleg = min(legend_maxnum, len(lines))
    for l in lines[nleg:]:
        l.set_alpha(0.4)
    if ax is axes[-1]:
        lines = [ax.lines[i] for i in sorted(indxs[:nleg])]
        labels = [l.get_label() for l in lines]
        ax.legend(lines, labels, loc=2, ncol=1 + (nleg > 6), frameon=False, text_same_color=True, hide_markers=True)
    ax.set_title('')

axes[0].set_title(key)
axes[0].set_ylim(1e-2, 1e3)
axes[0].set_yscale('log')
axes[0].set_xlabel('')
axes[1].set_xlabel('')
axes[2].set_ylim(*axes[1].get_ylim())

fig.tight_layout()

cornernote(device=ds.attrs['device'], shot=ds.attrs['shot'], time='')
