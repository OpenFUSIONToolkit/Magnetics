# -*-Python-*-
# Created by logannc at 01 Mar 2017  14:34
"""
This script prepares magnetics data prior to fitting.
Preparation may include,
 - Trimming to times of interest
 - Isolating frequency bands
 - Detrending to remove pickup/drifts
 - Compensation for 3D coil vacuum fields
 - SVD conditioning (removes


Parameters
------------

:param channel_filter: string or list. Regular expression(s) that must be matched when fetching channel.

:param time_trim: tuple. Trims data within this time range (t1, t2)

:param cutoff_hz: tuple. Badpass filter data, keeping only the part between (f1, f2)

:param detrend_type: str. Choose none, baseline, linear, or endpoints

:param detrend_band: tuple. Baseline and linear detrending use this sub-interval of time

:param energy: float. Fraction of energy kept from the data matrix SVD (values below 1 remove uncorrelated noise)

:param integrate: bool. Integrates signals over time (reasonable for bdot sensors)

:param dc_comp: bool. Remove DC vacuum coupling between coils and sensors

:param dc_comp_coils: list of strings. Coils for which to remove the DC vacuum coupling

:param verbose: bool. Print status information as work progresses

"""
defaultVars(
    channel_filter=root['SETTINGS']['PHYSICS'].get('channels', '.*'),
    time_trim=root['SETTINGS']['PHYSICS'].get('prep_time_trim', (2.9, 3)),
    cutoff_hz=root['SETTINGS']['PHYSICS'].get('prep_cutoff_hz', (5, 1000)),
    detrend_type=root['SETTINGS']['PHYSICS'].get('prep_detrend_type', 'none'),
    detrend_band=root['SETTINGS']['PHYSICS'].get('prep_detrend_band', [(0, np.inf)]),
    energy=root['SETTINGS']['PHYSICS'].get('prep_energy', 0.98),
    integrate=False,
    dc_comp=root['SETTINGS']['PHYSICS'].get('prep_dc_comp', False),
    dc_comp_coils=root['SETTINGS']['PHYSICS'].get('comp_coils', []),
    verbose=True,
)


def printiv(s):
    if verbose:
        printi(s)


def printv(s):
    if verbose:
        print(s)


printiv("Preparing data")

# only prepare the desired signals
printv(' - Trimming channels and time')
if cutoff_hz[0] == 0:
    tpad = 0  # just a low-pass filter
else:
    tpad = 1.0 / cutoff_hz[0]  # give enough data for the high-pass filter to work properly
channels = []
for k in root['INPUTS']['RAW']['channel'].values:
    if np.any([re.match(cf, k) for cf in atleast_1d(channel_filter)]):
        if not all(isnan(root['INPUTS']['RAW']['signal'].sel(channel=k).values)):
            channels.append(k)
i_trim = where((root['INPUTS']['RAW']['time'] >= time_trim[0] - tpad) & (root['INPUTS']['RAW']['time'] <= time_trim[1] + tpad))[0]
ds = root['INPUTS']['RAW'].sel(channel=channels).isel(time=i_trim).transpose('channel', 'time')
t = ds['time'].values

# compensation
if dc_comp and 'dc_coupling' in root['INPUTS'].get('COUPLING', {}):
    printv(' - DC compensation')
    root['SCRIPTS']['fetch'].run(channel_filter=root['SETTINGS']['PHYSICS']['comp_coils'])
    # retrim in case time base changed
    i_trim = where((root['INPUTS']['RAW']['time'] >= time_trim[0]) & (root['INPUTS']['RAW']['time'] <= time_trim[1]))[0]
    ds = root['INPUTS']['RAW'].sel(channel=channels).isel(time=i_trim).transpose('channel', 'time')
    t = ds['time'].values
    # isolate coils of interest
    coil_channels = []
    for cf in atleast_1d(dc_comp_coils):
        coil_channels += [k for k in root['INPUTS']['RAW']['channel'].values if re.match(cf, k)]
    coil = root['INPUTS']['RAW']['signal'].isel(time=i_trim).sel(channel=coil_channels).rename({'channel': 'coil'})
    coup = (coil * root['INPUTS']['COUPLING']['dc_coupling']).sum(dim='coil')
    invalid_channels = [k for k in ds['channel'].values if k not in coup['channel'].values]
    if len(invalid_channels) == 0:
        ds['vacuum'] = coup.sel(channel=ds['channel'])
        ds['signal'] = ds['signal'] - ds['vacuum']
    else:
        printe(" WARNING: No DC coupling record for {:}\n -> Skipping DC compensation".format(invalid_channels))


# device specific hacks
if is_device(root['SETTINGS']['EXPERIMENT']['device'], 'DIII-D'):
    if root['SETTINGS']['EXPERIMENT']['shot'] > 177705 and ('ESLD66M079' in ds or 'ESLD66M319' in ds):
        printw('** Swapping ESLD66M319 and ESLD66M079 signals for this shot due to 2019 wiring mix-up')
        tmp = copy.deepcopy(ds)
        for kswap in [['ESLD66M079', 'ESLD66M319'], ['ESLD66M319', 'ESLD66M079']]:
            ds['signal'].sel(channel=kswap[0]).values[:] = tmp['signal'].sel(channel=kswap[1]).values[:]


# trim auxiliary signals
aux_time = root['INPUTS']['PLASMA_PARAMS']['time'] / 1.0e3
i_trim = where((aux_time >= time_trim[0]) & (aux_time <= time_trim[1]))[0]
root['INPUTS']['PLASMA_PARAMS'] = root['INPUTS']['PLASMA_PARAMS'].isel(time=i_trim)

# integrate bdot signals
if integrate:
    printv(' - Integrating')
    dx = ds['time'].values[1] - ds['time'].values[0]
    ds['signal'].values = np.apply_along_axis(cumtrapz, 1, ds['signal'].values, dx=dx, initial=0)

# frequency filter the data
# do this prior to detrending
#  -> Motivating example: highpassing a one-way spike bdot signal will shift it off of the baseline
if len(t) > 1:
    nyqst = 0.5 / (t[1] - t[0])
else:
    nyqst = 1e99
if cutoff_hz[0] > 0 or cutoff_hz[1] < nyqst:
    # only need slightly better resolution than the nyquest, but don't decimate below 300 pts!
    step = int(min(max(1, int(nyqst / cutoff_hz[1])), np.ceil(t.shape[0] / 3e2)))
    if step > 1:
        printv(' - Downsampling x{:}'.format(step))
        ds = ds.sel(time=t[::step])
        t = ds['time'].values
    dt = t[1] - t[0]
    printv(' - Filtering')
    # butter smooth is an IIR instead of FIR filter, and is much faster for large time series
    if cutoff_hz[0] == 0:
        printv('   > Using a gaussian, causal, lowpass filter')
        # filter_func = lambda values: butter_smooth(t, values, cutoff=cutoff_hz[1], btype='low')
        sigma = 0.25 / (dt * cutoff_hz[1])  # 0.25 for consistency with smooth_by_convolution
        filter_func = lambda values: gaussian_filter1d(values, sigma, mode='nearest', truncate=4, causal=True)
    elif cutoff_hz[1] >= nyqst:
        printv('   > Using a gaussian, causal, highpass filter')
        # filter_func = lambda values: butter_smooth(t, values, cutoff=cutoff_hz[0], btype='high')
        sigma = 0.25 / (dt * cutoff_hz[0])  # 0.25 for consistency with smooth_by_convolution
        filter_func = lambda values: values - gaussian_filter1d(values, sigma, mode='nearest', truncate=4, causal=True)
    else:
        printv('   > Using a gaussian, causal, bandpass filter')
        # filter_func = lambda values: butter_smooth(
        #     t, butter_smooth(t, values, cutoff=cutoff_hz[0], btype='high'), cutoff=cutoff_hz[1], btype='low'
        # )
        sigma0 = 0.25 / (dt * cutoff_hz[0])  # 0.25 for consistency with smooth_by_convolution
        sigma1 = 0.25 / (dt * cutoff_hz[1])  # 0.25 for consistency with smooth_by_convolution

        def filter_func(values):
            values = gaussian_filter1d(values, sigma1, mode='nearest', truncate=4, causal=True)
            values -= gaussian_filter1d(values, sigma0, mode='nearest', truncate=4, causal=True)
            return values

    OMFITx.Refresh()
    ds['signal'].values = np.apply_along_axis(filter_func, 1, ds['signal'].values)

# remove padding that we used for the bandpass filter
tsel = t[(t >= time_trim[0]) * (t <= time_trim[1])]
ds = ds.sel(time=tsel)

# detrend the data
detrend_type = detrend_type.lower()

if detrend_type == 'none':
    pass
elif (detrend_type == 'baseline') | (detrend_type == 'linear'):
    time_detrend = []
    sig_detrend = []

    time = ds['time']
    detrend_band = atleast_2d(detrend_band)
    for i in range(0, detrend_band.shape[0]):
        det_band = detrend_band[i]
        ind = np.where((time >= det_band[0]) & (time <= det_band[1]))
        td = ds['time'][ind]
        time_detrend = np.concatenate((time_detrend, td))

    for ch, dum in enumerate(channels):
        sig_det = []
        ind = np.where(np.in1d(time, time_detrend) == True)
        sd = ds['signal'].values[ch, ind]
        if ch == 0:
            sig_detrend = sd[0]
        else:
            sig_detrend = np.vstack((sig_detrend, sd[0]))

    if detrend_type == 'baseline':
        printv(' - Removing baseline')
        for ch, dum in enumerate(channels):
            det = np.mean(sig_detrend[ch])
            ds['signal'][ch] = ds['signal'][ch] - det

    elif detrend_type == 'linear':
        printv(' - Removing linear trend')
        for ch, dum in enumerate(channels):
            pfit = np.poly1d(np.polyfit(time_detrend, sig_detrend[ch], deg=1))
            ds['signal'].values[ch] = ds['signal'].values[ch] - pfit(ds['time'].values)

elif detrend_type == 'endpoints':
    printv(' - Removing endpoint trend')
    ds_band = ds.where((ds['time'] >= detrend_band[0]) & (ds['time'] <= detrend_band[1]))
    for i, s in enumerate(ds_band['signal'].values):
        valid = np.isfinite(s)
        if np.sum(valid) > 1:  # at least two points to fit a line
            pfit = np.poly1d(np.polyfit(t[valid][np.array((0, -1))], s[np.array((0, -1))], deg=1))
            ds['signal'].values[i] = ds['signal'].values[i] - pfit(t)[None, :]
else:
    raise ValueError("Valid detrend_type options are none, baseline, linear, or endpoints")

# SVD determines dominant spatial and temporal structures
P = len(ds['channel'])
T = len(ds['time'])
printv(' - Conditioning data matrix')
OMFITx.Refresh()
try:
    if T > 10000:
        raise MemoryError('No need to stress the system out trying - it can hang for a long time')
    U, s, Vh = np.linalg.svd(ds['signal'].values / np.sqrt(P * T))
except MemoryError:
    printw(f'WARNING: Could not allocate enough memory to condition the full {P} x {T} data matrix')
    step = max(2, int(ceil(T / 10000)))
    printw(f' > Downsampling time by {step} for an informational SVD, but keeping full energy in data')
    U, s, Vh = np.linalg.svd(ds['signal'].values[:, ::step] / np.sqrt(P * T))
    energy = 1.0  # don't use this SVD at all - it's size doesn't match for reforming data
energy_tot = np.sum(s**2)
cut = P
for sindx in range(1, len(s)):  # assume re-im pairs in synchronous detection
    energy_frac = np.sum(s[:sindx] ** 2) / energy_tot
    if energy_frac > energy:
        cut = sindx
        # attempt to keep (cos,sin) pairs together
        if sindx < len(s) - 1:
            if s[sindx + 1] ** 2 > 0.5 * s[sindx] ** 2:
                cut += 1
        break
ds['signal_precon_u'] = DataArray(U, coords={'signal_svd_index': arange(P), 'channel': ds['channel']}, dims=('signal_svd_index', 'channel'))
ds['signal_precon_svals'] = DataArray(s, coords={'signal_svd_index': arange(P)}, dims=['signal_svd_index'])
ds.attrs['signal_energy_limit'] = energy
ds.attrs['signal_effective_rank'] = cut
printv('   > SVD found {} coherent structures of interest'.format(cut))

# effectively filter the signal by removing incoherent noise
if energy < 1.0:
    smat = np.zeros((P, T))
    for i in range(cut):
        smat[i, i] = s[i]
    ds['signal'].values = np.dot(U, np.dot(smat, Vh)) * np.sqrt(P * T)

# save the modified data in the tree
root['INPUTS']['PREPARED'] = ds
