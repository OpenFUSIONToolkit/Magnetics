# -*-Python-*-
# Created by logannc at 16 Dec 2020  19:53

"""
This script plots a slice of the 2D fit in contours of the other
axis and time. This is a classic slcontour type plot when slicing at some theta.

defaultVars parameters
----------------------

:param fit_key: str. Name of the fit from OUTPUTS to plot

:param fix_coord: str. Dimension that will be "sliced" at fix_value

:param fix_value: float. Value of fix_coord held constant in the plot. Plot is a contour in the remaining spacial dimension and time.

:param ngrid: int.Size of the regular grid used in the remaining spacial coordinate.

:param trace_peak: bool. Plot markers showing the peak amplitude at each time and an upper 1D plot of the amplitude vs time.

:param ax: Axes. Plot in this axes instance.

:param plot_kwargs: dict. Key word arguments passed to xarray 2D DataArray plot method (imshow if data is evenly spaced in time)

"""

defaultVars(
    fit_key=root['SETTINGS']['PHYSICS'].get('fit_key', ''),
    fix_coord=root['SETTINGS']['PHYSICS'].get('plot_fix_coord', 'theta'),
    fix_value=root['SETTINGS']['PHYSICS'].get('plot_fix_value', 0),
    ngrid=90,
    show_abs=False,
    trace_peak=True,
    ax=None,
    plot_kwargs=dict(edgecolors='face', rasterized=True),
)

# get fit
ds = root['OUTPUTS']['FIT'][fit_key]

# set up grid for reconstructing the fit
if ds.attrs['fit_geometry'] == 'cylindrical':
    if fix_coord == 'theta':
        ygrid = np.deg2rad(fix_value)
        xgrid = linspace(0, 2 * pi, ngrid)
        xgrid = DataArray(xgrid, coords=[('phi', np.rad2deg(xgrid))])
        yplt = np.rad2deg(xgrid)
        ykey = r'\phi'
    elif fix_coord == 'phi':
        ts = hstack((ds['theta_end1'].values, ds['theta_end2'])) * (pi / 180.0)
        if all(np.abs(ts) > pi / 2):
            ygrid = linspace(pi / 2, 3 * pi / 2, ngrid)
        elif all(np.abs(ts) < pi / 2):
            ygrid = linspace(-pi / 2, pi / 2, ngrid)
        else:
            ygrid = linspace(-pi, pi, ngrid)
        ygrid = DataArray(ygrid, coords=[('theta', np.rad2deg(ygrid))])
        xgrid = np.deg2rad(fix_value)
        yplt = np.rad2deg(ygrid)
        ykey = r'\theta'
    else:
        raise OMFITexception('Fixed coordinate much be theta or phi')
elif ds.attrs['fit_geometry'] == 'vertical':
    if fix_coord == 'z':
        ygrid = fix_value
        xgrid = linspace(0, 2 * pi, ngrid)
        xgrid = DataArray(xgrid, coords=[('phi', np.rad2deg(xgrid))])
        yplt = np.rad2deg(xgrid)
        ykey = r'\phi'
    elif fix_coord == 'phi':
        zs = hstack((ds['z_end1'].values, ds['z_end2']))
        zbuffer = 0.1 * np.ptp(zs)
        zmax = ds['z_end1']
        ygrid = linspace(zs.min() - zbuffer, zs.max() + zbuffer, ngrid)
        ygrid = DataArray(ygrid, coords=[('z', ygrid)])
        xgrid = np.deg2rad(fix_value)
        yplt = ygrid
        ykey = r'z'
    else:
        raise OMFITexception('Fixed coordinate much be z or phi')


# form function from Fourier coeffs
if ds.attrs['fit_basis'].startswith('sinusoidal'):
    fit = (ds['fit_coeffs'] * exp(-1j * (ds['fit_ns'] * xgrid + ds['fit_ms'] * ygrid))).sum(dim='mode').real.T
elif ds.attrs['fit_basis'].startswith('gaussian'):
    ncycle = ds.attrs['fit_ncycle']
    mcycle = ds.attrs['fit_mcycle']
    fit = 0
    for nc in range(-ncycle, ncycle + 1):
        for mc in range(-mcycle, mcycle + 1):
            fit += (
                (
                    ds['fit_coeffs']
                    * exp(
                        -1 * ((ds['fit_ns'] - np.rad2deg(xgrid) + nc * 360) / ds.attrs['fit_neps']) ** 2
                        - 1 * ((ds['fit_ms'] - np.rad2deg(ygrid) + mc * 360) / ds.attrs['fit_meps']) ** 2
                    )
                )
                .sum(dim='mode')
                .real.T
            )
else:
    printe("These plots are not available for non-sinusoidal basis functions yet")
    OMFITx.End()
fit = fit.rename('Fit')

need_reset = False
if trace_peak:
    if ax is None:
        gs = matplotlib.gridspec.GridSpec(4, 4)
        fig = figure()
        ax = fig.use_subplot(gs[1:, :])
        axx = fig.use_subplot(gs[0, :], sharex=ax)
    else:
        fig = ax.figure
        rect = ax.get_position().bounds
        gs = matplotlib.gridspec.GridSpec(4, 4, left=rect[0], bottom=rect[1], right=rect[0] + rect[2], top=rect[1] + rect[3])
        ax.set_position(gs[1:, :].get_position(fig))  # main 2D plot
        axx = fig.use_subplot(gs[0, :], sharex=ax)
        need_reset = True  # for some reason the xarray plotting re-expands the original axes
else:
    if ax is None:
        fig, ax = subplots()
    else:
        fig = ax.figure

if show_abs:
    fit.values[fit.values > 0] = 0
    fit = abs(fit).rename('3D Magnitude (T)')

im = fit.plot(ax=ax, **plot_kwargs)
if ax.get_ylabel() == 'phi':
    ax.set_yticks([0, 90, 180, 270, 360])
    ax.set_ylabel('Toroidal Angle (deg.)')
ax.set_xlabel('Time (s)')

if trace_peak:
    amp = np.sqrt((fit * fit).mean(dim='phi')).rename('RMS')
    # amp = abs(fit).max(dim='phi').rename('Amp.')  # alternative metric
    ipeak = fit.argmax(dim='phi')
    phase = np.array([fit['phi'].isel(phi=[i]).values[0] for i in ipeak])

    # mark the location of the peaks on the 2D plot
    ax.plot(fit['time'].values, phase, marker='o', color='w', ls='', mfc='none')
    if need_reset:
        rect = ax.get_position().bounds
        gs = matplotlib.gridspec.GridSpec(4, 4, left=rect[0], bottom=rect[1], right=rect[0] + rect[2], top=rect[1] + rect[3])
        ax.set_position(gs[1:, :].get_position(fig))

    # Add a 1D plot of the amplitude vs time above the 2D plot
    amp.plot(ax=axx)
    axx.set_xlabel('')
    for tl in axx.xaxis.get_ticklabels():
        tl.set_visible(False)
    axx.yaxis.set_major_locator(plt.MaxNLocator(nbins=2))
    # dummy colorbar to align the axes widths
    cb = fig.colorbar(im, ax=axx)
    cb.set_label(fit.name)
    cb.ax.remove()

cornernote(ax=ax, root=root, shot=ds.attrs['shot'], device=ds.attrs['device'], time='')
