# -*-Python-*-
# Created by logannc at 01 Mar 2017  15:57
"""
This script performs a least squares fit of the chosen basis functions to the prepared data.

It first performs and SVD on the sensor-by-time data matrix, and removes all singular values
below the first N required to meet the cumulative energy threshold.

Parameters

------------

:param key: string. Name of the fit. The Dataset result will be stored under this name in the OUTPUTS tree.

:param channel_filter: list of regex strings. Regular expressions that must be matched to include channel in fit.

:param fit_exclude: list of regex strings. Regular expressions that exclude channels from the fit when matched.

:param ns: list. Toroidal mode numbers included in the fit basis.

:param ms: list. Poloidal mode numbers included in the fit basis.

:param omega_hz: float or string. If float, translates time to space using omega_hz*t. If string, translates
  time to space using the phase of the previous fit of the corresponding name. Either way, coefficients
  are fit once for A(x,y) instead of independently for A(x,y,t).

:param fit_basis: str. Type of basis function used in design matrix. Currently supports,
  - 'sinusoidal-point' fits A exp(i m theta + i n phi) evaluated at sensors centers
  - 'sinusoidal-integral' fits A exp(i m theta + i n phi) integrated over the sensor (theta, phi) area

:param fit_geometry: str. Choose coordinate mapping for the basis functions in the design matrix
  - 'cylindrical' uses (phi, theta) where theta is the angle at the nominal major radius
  - 'vertical' uses (phi, z)
  - 'spherical' uses (phi, alpha) where alpha is the angle at R=0

:param fit_cond: float. Condition number threshold of the basis matrix inversion in the least-squares fit. Note, this is
  1/rcond where rcond is an optional key word argument of the numpy.linalg.lstsq function. It should be above 1.

:param fit_lsv: bool. Fit the spatial structure of each of the left singular vectors (LSVs) of the channel-by-time data
  matrix and then propagate them in time using the right singular vectors (RSVs). This may save time, as it requires
  only a few spatial fits instead of an independent spacial fit at every time point (the default).

:param verbose: bool. Print status updates to console

"""
defaultVars(
    fit_key=root['SETTINGS']['PHYSICS'].get('fit_key', 'fit_0'),
    channel_filter=root['SETTINGS']['PHYSICS'].get('channels', '.*'),
    fit_exclude=root['SETTINGS']['PHYSICS'].get('fit_exclude', ()),
    ns=root['SETTINGS']['PHYSICS'].get('fit_ns', [1]),
    ms=root['SETTINGS']['PHYSICS'].get('fit_ms', [0]),
    ncenters=root['SETTINGS']['PHYSICS'].get('fit_ncenters', 6),
    mcenters=root['SETTINGS']['PHYSICS'].get('fit_mcenters', 1),
    nepsilon=root['SETTINGS']['PHYSICS'].get('fit_neps', 60),
    mepsilon=root['SETTINGS']['PHYSICS'].get('fit_meps', np.inf),
    omega_hz=root['SETTINGS']['PHYSICS'].get('fit_omega_hz', None),
    fit_basis=root['SETTINGS']['PHYSICS'].get('fit_basis', 'sinusoidal-integral'),
    fit_geometry=root['SETTINGS']['PHYSICS'].get('fit_geometry', 'cylindrical'),
    fit_cond=root['SETTINGS']['PHYSICS'].get('fit_cond', 1e3),
    fit_lsv=root['SETTINGS']['PHYSICS'].get('fit_lsv', False),
    verbose=True,
)

import scipy.special as special


def printiv(s):
    if verbose:
        printi(s)


def printv(s):
    if verbose:
        print(s)


printiv("Fitting the prepared data")

# pick which sensors to use
channels = []
fit_exclude = atleast_1d(fit_exclude)
for chan in root['INPUTS']['PREPARED']['channel'].values:
    if np.any([re.match(key, chan) for key in atleast_1d(channel_filter)]):
        if not np.any([re.match(key, chan) for key in atleast_1d(fit_exclude)]):
            if not all(isnan(root['INPUTS']['PREPARED']['signal'].sel(channel=chan).values)):
                channels.append(chan)
ds = root['INPUTS']['PREPARED'].sel(channel=channels).copy()

# basic variables
time = ds['time'].values
helicity = root['INPUTS']['PLASMA_PARAMS'].attrs['helicity']
synchronous = omega_hz is not None and omega_hz != ''
if fit_geometry == 'cylindrical':
    xkey = 'phi'
    ykey = 'theta'
elif fit_geometry == 'vertical':
    xkey = 'phi'
    ykey = 'z'
elif fit_geometry == 'spherical':
    xkey = 'phi'
    ykey = 'alpha'
x1 = ds[xkey + '_end1'].values
x2 = ds[xkey + '_end2'].values
y1 = ds[ykey + '_end1'].values
y2 = ds[ykey + '_end2'].values
sigma = ds['signal_sigma'].values
if synchronous:
    if isinstance(omega_hz, str):
        # get the synchronous phase from another fit's biggest mode (presumably a rotated, single-n coil)
        fc = root['OUTPUTS'][omega_hz]['fit_coeffs']
        fcmean = np.abs(fc).mean(dim='time')
        m = np.argmax(np.abs(fc).mean(dim='time').values)
        ref_phase = np.angle(fc.isel(mode=m).sel(time=time), deg=True)
    else:
        # this should work for a constant or a time series
        ref_phase = scipy.integrate.cumtrapz(omega_hz * np.ones_like(time), x=time, initial=0) * 360
    x1 = np.ravel(x1[:, None] - ref_phase)
    x2 = np.ravel(x2[:, None] - ref_phase)
    y1 = np.tile(y1, time.shape[0])
    y2 = np.tile(y2, time.shape[0])
    sigma = np.tile(sigma, time.shape[0])

# check if they are all differences
if any([ds['pair'] == 'None']):
    dp = None
else:
    # values of the pairs in the same order as the actual channels
    ps = [p for p in ds['pair'].values if p in ds['channel'].values]
    bad = [p for p in ds['pair'].values if p not in ds['channel'].values]
    dp = root['INPUTS']['RAW'].sel(channel=ds['pair'])
    if dp is not None:
        px1 = dp[xkey + '_end1'].values
        px2 = dp[xkey + '_end2'].values
        py1 = dp[ykey + '_end1'].values
        py2 = dp[ykey + '_end2'].values
        psigma = dp['signal_sigma'].values
        # hack for old shots where the paired signals are not available
        if all(isnan(sig) for sig in psigma):
            psigma = sigma * 1.0
        # hack for fake MPIF* sensors for HFS vertical arrays
        psigma[psigma != psigma] = np.nanmean(psigma)
        if synchronous:
            px1 = np.ravel(px1[:, None] - ref_phase)
            px2 = np.ravel(px2[:, None] - ref_phase)
            py1 = np.tile(py1, time.shape[0])
            py2 = np.tile(py2, time.shape[0])
            psigma = np.tile(psigma, time.shape[0])


# defaults and cleanup for modes
if fit_basis.startswith('sinusoidal'):
    ms = atleast_1d(ms)
    ns = atleast_1d(ns)
    if dp is None and 0 not in ns:
        printv("WARNING: Sensors are not paired! Consider including n=0.")

    # enforce correct helicity sign convention
    if not np.all(ms == 0) and not np.any(np.sign(ms) == helicity) and fit_basis.startswith('sinusoidal'):
        ms *= -1
        printv('WARNING: Flipping sign of m to conform to helicity {:+}'.format(helicity))
    nms = [(n, m) for m in ms for n in ns]

    # force global offset to be the first mode
    if (0, 0) in nms:
        nms.insert(0, nms.pop(nms.index((0, 0))))
    nms_arr = np.array(nms)

    # machine specific warnings and errors
    if is_device(root['SETTINGS']['EXPERIMENT']['device'], 'DIII-D'):
        if np.any([re.match(key, chan) for key in ['C.*', 'IL.*', 'IU.*']]):
            if fit_basis != 'sinusoidal-point':
                printe("WARNING: sinusoidal-point basis is used by DIII-D 3D coil operators")
    # dummy vars for gaussian rbf
    ncycle = 0
    mcycle = 0
elif fit_basis.startswith('gaussian'):
    # in this case, the ns and ms become the radial basis function centers
    # automatic range choices based on the region spanned by sensors
    xlim = (int(min(hstack((x1, x2))) / 10.0) * 10, ceil(max(hstack((x1, x2))) / 10.0) * 10)
    ylim = (int(min(hstack((y1, y2))) / 10.0) * 10, ceil(max(hstack((y1, y2))) / 10.0) * 10)
    if xlim[1] - xlim[0] > 180:
        xlim = (0, 360)
        xend = False  # no need for redundent basis function on 0 and 360
    else:
        xend = True  # if not full span, put a basis function on both edges
    if ylim[1] - ylim[0] > 180:
        ylim = (0, 360)
        yend = False  # no need for redundent basis function on 0 and 360
    else:
        yend = True  # if not full span, put a basis function on both edges
    ns = linspace(xlim[0], xlim[1], ncenters, xend, dtype=int)
    ms = linspace(ylim[0], ylim[1], mcenters, yend, dtype=int)
    if nepsilon is None or nepsilon == 0:
        if len(ns) < 2:
            nepsilon = np.inf
        else:
            nepsilon = np.mean(np.diff(ns))
    if mepsilon is None or mepsilon == 0:
        if len(ms) < 2:
            mepsilon = np.inf
        else:
            mepsilon = np.mean(np.diff(ms))
    nms = [(n, m) for m in ms for n in ns]
    nms_arr = np.array(nms)
    if nepsilon < np.inf:
        ncycle = max(1, int(8 * nepsilon / 360))
    else:
        ncycle = 0
    if mepsilon < np.inf:
        mcycle = max(1, int(8 * mepsilon / 360))
    else:
        mcycle = 0


def delta_degrees(theta1, theta2):
    """
    Find the angular width from a start to a stop, wrapping around 0 (only once) if necessary.

    :param theta1: float. Start angle (degrees)

    :param theta2: flaot. Stop angle (degrees)

    :return: dtheta: The angular distance from 1 to 2

    """
    t1, t2 = theta1, theta2
    dt = t2 - t1
    if dt > 180:
        dt -= 360
    if dt < -180:
        dt += 360
    return dt


delta_degrees = np.vectorize(delta_degrees)


# form basis matrix
def form_basis_function(n, m, x1, x2, y1, y2, fit_basis=fit_basis):
    """
    Helper function forming basis function sensor-vector for a given mode.

    :param n: int. Toroidal mode number

    :param m: int. Poloidal mode number

    :param x1: ndarray. Toroidal start of sensors

    :param x2: ndarray. Toroidal end of sensors

    :param y1: ndaraay. Poloidal start of sensors

    :param y2: Poloidal end of sensors

    :param fit_basis: string. Basis function type. Currently supports 'sinusoidal-point' and 'sinusoidal-integral'

    :return: ndarray. Basis function evaluated for each sensor.

    """
    if fit_basis == 'sinusoidal-point':
        # average of sinusoid across the (theta, phi) extent of the sensor
        dx = delta_degrees(x1, x2)
        dy = delta_degrees(y1, y2)
        if n == 0:
            if m == 0:
                fmn = np.ones_like(dx)
            else:
                fmn = exp(1j * m * np.deg2rad(y1 + dy / 2.0))
        else:
            if m == 0:
                fmn = exp(1j * n * np.deg2rad(x1 + dx / 2.0))
            else:
                fmn = exp(1j * m * np.deg2rad(y1 + dy / 2.0) + 1j * n * np.deg2rad(x1 + dx / 2.0))
    elif fit_basis == 'sinusoidal-integral':
        # average of sinusoid across the (theta, phi) extent of the sensor
        dx = delta_degrees(x1, x2)
        dy = delta_degrees(y1, y2)
        if n == 0:
            if m == 0:
                fmn = np.ones_like(dx)
            else:
                fmn = (exp(1j * m * np.deg2rad(y2)) - exp(1j * m * np.deg2rad(y1))) / (np.deg2rad(dy) * 1j * m)
        else:
            if m == 0:
                fmn = (exp(1j * n * np.deg2rad(x2)) - exp(1j * n * np.deg2rad(x1))) / (np.deg2rad(dx) * 1j * n)
            else:
                fmn = (
                    (exp(1j * m * np.deg2rad(y2)) - exp(1j * m * np.deg2rad(y1)))
                    * (exp(1j * n * np.deg2rad(x2)) - exp(1j * n * np.deg2rad(x1)))
                ) / (np.deg2rad(dx * dy) * n * m)
    elif fit_basis.startswith('gaussian'):
        dx = delta_degrees(x1, x2)
        dy = delta_degrees(y1, y2)
        xc = x1 + dx / 2.0
        yc = y1 + dy / 2.0
        fmn = 0
        for nc in range(-ncycle, ncycle + 1):
            for mc in range(-mcycle, mcycle + 1):
                if fit_basis == 'gaussian-point':
                    fmn += exp(-(((n + nc * 360 - xc) / nepsilon) ** 2) - ((m + mc * 360 - yc) / mepsilon) ** 2)
                if fit_basis == 'gaussian-integral':
                    if mepsilon == np.inf:
                        fmn += (
                            -0.5
                            * np.sqrt(np.pi)
                            * nepsilon
                            * (special.erf(-((n + nc * 360 - x2) / nepsilon)) - special.erf(-((n + nc * 360 - x1) / nepsilon)))
                        )
                    elif nepsilon == np.inf:
                        fmn += (
                            -0.5
                            * np.sqrt(np.pi)
                            * mepsilon
                            * (special.erf(-((m + mc * 360 - y2) / mepsilon)) - special.erf(-((m + mc * 360 - y1) / mepsilon)))
                        )
                    else:
                        fmn += (
                            -0.25
                            * np.pi
                            * nepsilon
                            * mepsilon
                            * (special.erf(-((n + nc * 360 - x2) / nepsilon)) - special.erf(-((n + nc * 360 - x1) / nepsilon)))(
                                special.erf(-((m + mc * 360 - y2) / mepsilon)) - special.erf(-((m + mc * 360 - y1) / mepsilon))
                            )
                        )
    else:
        raise OMFITexception("Currently only 'sinusoidal' and 'gaussian' bases is supported.")
    return fmn


# form the basis function matrix (design matrix)
A = []
ncomp = []  # this sorts out there are two modes or one mode component in the A matrix
for n, m in nms:
    # evaluate the basis function for each sensor
    fmn = form_basis_function(n, m, x1, x2, y1, y2)
    # design matrix signal_sigma normalization
    # this cannot be done here if the error is time dependent, it needs a new A matrix for each time point SM
    fmn /= sigma
    # subtract the same thing for the paired sensor if there is one
    if dp is not None:
        fmn = (fmn - form_basis_function(n, m, px1, px2, py1, py2) / psigma) / 2.0
    if all(fmn.imag == 0):
        A.append(fmn.real)
        ncomp.append(1)
    else:
        A.append(fmn.real)
        A.append(fmn.imag)
        ncomp.append(2)
        # check for aliasing due to equally spaced probes (sinusoidal specific?)
        try:
            U_a, w_a, Vh_a = np.linalg.svd(np.matrix(A).T)
            c_a = np.abs(w_a[0] / w_a[-1])
            if c_a > 1e19:
                raise ValueError("Bad sensor distribution")
        except ValueError as e:
            printe(" - Cannot fit both components of ill conditioned modes as ({:},{:})".format(n, m))
            printe("  > Fitting single component centered on first sensor")
            x0 = x1[0] + delta_degrees(x1[0], x2[0]) / 2.0
            y0 = y1[0] + delta_degrees(y1[0], y2[0]) / 2.0
            # evaluate the basis function for each sensor
            fmn = form_basis_function(n, m, x1 + x0, x2 + x0, y1 + y0, y2 + y0) / sigma
            # subtract the same thing for the paired sensor if there is one
            if dp is not None:
                fmn = (fmn - form_basis_function(n, m, px1 + x0, px2 + x0, py1 + y0, py2 + y0) / psigma) / 2.0
            A = A[:-2] + [fmn.real]
            ncomp[-1] = 1
A = np.matrix(A).T

if A.shape[1] > A.shape[0]:
    printw('Warning: Fitting {:} basis functions with {:} sensors'.format(shape(A)[1], shape(A)[0]))

# SVD of basis matrix (should store and plot)
U_a, w_a, Vh_a = np.linalg.svd(A)
c_a = np.abs(w_a[0] / w_a)
valid = c_a <= fit_cond
ds.attrs['fit_condition'] = fit_cond

# 2D fit for each svd structure
if fit_lsv:
    fit_coeffs = 0
    sigma = 0
    for i in range(cut):
        printv(" - Fitting structure {}".format(i + 1))
        b = U[:, i] / ds['signal_sigma'].values
        x, residual, rank_fit, s_a = numpy.linalg.lstsq(A, b, 1.0 / fit_cond)
        rank_a = shape(x)[0]
        cond_a = np.abs(s_a[0] / s_a[-1])
        cond_fit = max(c_a[valid])
        printv(' - Raw rank, condition number = {}, {:.3g}'.format(rank_a, cond_a))
        printv(' - Eff rank, condition number = {}, {:.3g}'.format(rank_fit, cond_fit))
        fit_coeffs += np.array(x)[:, None] * Vh[i] * s[i] * np.sqrt(P * T)
else:
    printv(" - Fitting signal")
    if synchronous:
        # assume constant omega
        b = np.matrix(np.ravel(ds['signal'] / ds['signal_sigma'])).T
    else:
        b = np.matrix(ds['signal'] / ds['signal_sigma'])
    # chunk the SVDs so we don't run into a memory error when doing kHz fits over many seconds
    ntime = b.shape[1]
    chunk_size = 50000
    x, residual, rank_fit, s_a = numpy.linalg.lstsq(A, b, 1.0 / fit_cond)
    rank_a = shape(x)[0]
    cond_a = np.abs(s_a[0] / s_a[-1])
    cond_fit = max(c_a[valid])
    printv(' - Raw rank, condition number = {}, {:.3g}'.format(rank_a, cond_a))
    printv(' - Eff rank, condition number = {}, {:.3g}'.format(rank_fit, cond_fit))
    fit_coeffs = np.array(x)

ds.attrs['raw_cn'] = cond_a
ds.attrs['eff_cn'] = cond_fit
# estimate error
w_inv_a_valid = 1 / w_a
w_inv_a_valid[~valid] = 0
# add extra zeros if the fit_cond enabled fiting more basis functions than sensors
w_inv_a_valid = np.hstack((w_inv_a_valid, [0.0] * max(Vh_a.shape[0] - w_a.shape[0], 0)))

fit_sigma2 = sum((np.array(Vh_a).T * w_inv_a_valid) ** 2, axis=0)[:, None]
fit_sigmas = np.sqrt(fit_sigma2)

# reform complex coefficients, handling the fact that some modes may not have both components
tcomp = np.cumsum(ncomp) - 1
fit_coeffs_c = []
fit_sigmas_c = []
j = 0
for i, nc in enumerate(ncomp):
    if nc == 1:
        fit_coeffs_c.append(fit_coeffs[j] + 1j * 0)
        fit_sigmas_c.append(fit_sigmas[j] + 1j * 0)
    if nc == 2:
        fit_coeffs_c.append(fit_coeffs[j] + 1j * fit_coeffs[j + 1])
        fit_sigmas_c.append(fit_sigmas[j] + 1j * fit_sigmas[j + 1])
    j += nc
fit_coeffs_c = np.array(fit_coeffs_c)
fit_sigmas_c = np.array(fit_sigmas_c)

# add time dimension if synchronous detection had collapsed it
fit_coeffs_c = fit_coeffs_c * np.ones_like(time)
fit_sigmas_c = fit_sigmas_c * np.ones_like(time)
fit_b = np.dot(A, fit_coeffs).real.reshape(ds['channel'].shape[0], -1)

ds['fit_signal'] = DataArray(fit_b, coords=ds['signal'].coords, dims=ds['signal'].dims) * ds['signal_sigma']
ds['fit_ns'] = DataArray(nms_arr[:, 0], coords={'mode': arange(len(nms))}, dims=('mode',))
ds['fit_ms'] = DataArray(nms_arr[:, 1], coords={'mode': arange(len(nms))}, dims=('mode',))
ds['fit_coeffs'] = DataArray(fit_coeffs_c, coords={'mode': arange(len(nms)), 'time': ds['time']}, dims=('mode', 'time'))
ds['fit_sigmas'] = DataArray(fit_sigmas_c, coords={'mode': arange(len(nms)), 'time': ds['time']}, dims=('mode', 'time'))

ds['residual'] = ds['signal'] - ds['fit_signal']
ds['chi_sq'] = ((ds['residual'] / ds['signal_sigma']) ** 2).sum('channel')
nu = b.shape[0] - rank_fit
ds['red_chi_sq'] = ds['chi_sq'] / nu

ds['basis'] = DataArray(
    A, coords={'basis_channel': arange(A.shape[0]), 'basis_mode': arange(A.shape[1])}, dims=('basis_channel', 'basis_mode')
)

printv(' - Mean reduced chi squared = {:.3e}'.format(np.nanmean(ds['red_chi_sq'])))

# store all the settings with the fit
for key, val in root['SETTINGS']['PHYSICS'].items():
    ds.attrs.setdefault(key, val)
# these may have been changed from defaults
ds.attrs['fit_neps'] = nepsilon
ds.attrs['fit_meps'] = mepsilon
# these are not settings but needed for reconstruction
ds.attrs['fit_ncycle'] = ncycle
ds.attrs['fit_mcycle'] = mcycle

root['OUTPUTS'].setdefault('FIT', OMFITtree())
root['OUTPUTS']['FIT'][fit_key] = ds
