# -*-Python-*-
# Created by nlogan at 24 May 2017  09:02
"""
This script plots the amplitude and phase of each mode of the chosen fit.

Parameters

------------

:param keys: list. Name of a fit Dataset(s) from OUTPUTS.

:param kwargs: dictionary. Key word arguments passed to the axes plot methods.

"""
defaultVars(
    keys=(root['SETTINGS']['PHYSICS'].get('fit_key', ''),), energy=root['SETTINGS']['PHYSICS'].get('fit_energy', 0.98), kwargs={}, axes=None
)

# some plot option defaults
lw = max(2, rcParams['lines.linewidth'])
if 'lw' in kwargs:
    kwargs['linewidth'] = kwargs.pop('lw')
kwargs.setdefault('linewidth', lw)
xkwargs = kwargs.copy()
xkwargs['linewidth'] += 1
for k in ['ls', 'linestyle', 'label', 'marker']:
    if k in xkwargs:
        xkwargs.pop(k)

if axes is None:
    fig, axes = plt.subplots(2, sharex=True)
else:
    assert shape(axes) == (2,), "Requires 2 axes"
    fig = axes[0].get_figure()

for key in keys:
    ds = root['OUTPUTS']['FIT'][key]

    # SVD of data matrix
    s = ds['signal_precon_svals']
    energy_tot = np.sum(s ** 2)
    energy_frac = np.cumsum(s ** 2, axis=s.dims.index('signal_svd_index')) / energy_tot
    energy_frac_ignored = energy_frac * 1
    energy_frac_ignored[: ds.attrs['signal_effective_rank']] = np.nan

    axes[0].plot(ds['signal_svd_index'] + 1, energy_frac, marker='o', label='All', **kwargs)
    axes[0].plot(ds['signal_svd_index'] + 1, energy_frac_ignored, marker='x', linestyle='', label='Removed', **xkwargs)
    axes[0].axhline(ds.attrs['signal_energy_limit'], color='k', linestyle='--')
    axes[0].set_xlim(xmin=0)
    axes[0].set_xlabel('Cumulative Singular Value Index')
    axes[0].set_ylabel('Energy Fraction')
    axes[0].set_title(key + ' Data Matrix Conditioning')

    # SVD of design matrix
    A = ds['basis'].values
    U_a, w_a, Vh_a = np.linalg.svd(A)
    c_a = np.abs(w_a[0] / w_a)
    c_a_ignored = c_a * 1
    c_a_ignored[c_a < ds.attrs['fit_condition']] = np.nan
    axes[1].plot(np.arange(len(c_a)) + 1, c_a, marker='o', label='All', **kwargs)
    axes[1].plot(np.arange(len(c_a)) + 1, c_a_ignored, marker='x', linestyle='', label='Removed', **xkwargs)
    axes[1].axhline(ds.attrs['fit_condition'], color='k', linestyle='--')
    axes[1].set_xlim(xmin=0)
    axes[1].set_xlabel('Singular Value Index')
    axes[1].set_ylabel('Condition Number')
    axes[1].set_title(key + ' Design Matrix Conditioning')

for ax in axes:
    ax.legend().draggable()
fig.tight_layout()
