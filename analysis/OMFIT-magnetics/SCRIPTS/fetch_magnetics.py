# -*-Python-*-
# Created by logannc at 01 Mar 2017  13:21
"""
This script fetches the raw data for magnetics diagnostics from their native MDSplus server and
stores it in the RAW INPUTS Dataset.

It will fetch all channels listed in the sensors table under the current machine's DATA that
match the channel_filter.

Parameters

------------

:param shot: int. Plasma shot for which to fetch data.

:param server: string. Server from which to fetch the MDSplus data.

:param treename: string. MDS tree in which the data resides.

:param channel_filter: string or list. Regular expression(s) that must be matched when fetching channel.

:param sigma_type: float. One sigma error bar associated with measurements (Tesla).

:param force: bool. Force regathering of all signals.

:param verbose: bool. Print status updates to console

"""
defaultVars(
    shot=root['SETTINGS']['EXPERIMENT']['shot'],
    server=root['SETTINGS']['EXPERIMENT']['device'],
    treename=None,
    channel_filter=root['SETTINGS']['PHYSICS'].get('channels', '.*'),
    sigma_type=root['SETTINGS']['PHYSICS'].get('fetch_sigma', 2e-5),
    force=False,
    verbose=True,
)


def printiv(s):
    if verbose:
        printi(s)


def printv(s):
    if verbose:
        print(s)


if shot is None:
    raise OMFITexception("Must specify a valid shot!")

printiv("Fetching data")

if (
    root['INPUTS']['RAW'].attrs.get('device', None) != server
    or root['INPUTS']['RAW'].attrs.get('shot', None) != shot
    or root['INPUTS']['RAW'].attrs.get('sigma_type', None) != sigma_type
):
    if 'signal' in root['INPUTS']['RAW']:
        del root['INPUTS']['RAW']['signal']
    if 'signal_sigma' in root['INPUTS']['RAW']:
        del root['INPUTS']['RAW']['signal_sigma']

signal = None
re_using = False
for key in root['INPUTS']['RAW']['channel'].values:
    if np.any([re.match(cf, key) for cf in atleast_1d(channel_filter)]):
        if 'signal' in root['INPUTS']['RAW'] and not force:
            if np.any(np.nan_to_num(root['INPUTS']['RAW']['signal'].sel(channel=key).values) != 0):
                re_using = True
                continue  # don't re-fetch
        printv('  - ' + key)
        val = OMFITmdsValue(server=server, treename=treename, TDI=key, shot=shot)
        if not val.check() and key in root['DATA']['DIII-D']['channel_alternates']:
            # try old name convention
            val = OMFITmdsValue(server=server, treename=treename, TDI=root['DATA']['DIII-D']['channel_alternates'][key], shot=shot)
        if val.check():
            y = val.dim_of(0) / 1e3
            da = DataArray([val.data()], coords={'channel': [key], 'time': y}, dims=('channel', 'time'), name='signal')
        else:
            printw('   > No {:} data available for {:} shot {:}'.format(key, server, shot))
            continue
        if signal is None:
            signal = 1 * da
        else:
            dt_old = signal['time'].values[1] - signal['time'].values[0]
            dt_new = da['time'].values[1] - da['time'].values[0]
            if dt_new < dt_old:
                printw(" > Interpolating previous signals data to higher sampling of new signal")
                signal = reindex_interp(
                    signal, time=da['time'].values, method='linear', interpolate_kws={'bounds_error': False, 'fill_value': np.nan}
                )
            elif dt_new > dt_old:
                printw(" > Interpolating this signal to higher sampling of previous signals")
                da = reindex_interp(
                    da, time=signal['time'].values, method='linear', interpolate_kws={'bounds_error': False, 'fill_value': np.nan}
                )
            else:  # this just makes double sure the time dims are exactly the same
                da = reindex_interp(
                    da, time=signal['time'].values, method='nearest', interpolate_kws={'bounds_error': False, 'fill_value': np.nan}
                )
            signal = xarray.concat([signal, da], dim='channel')

if signal is not None:
    printi(' > Assessing uncertainty')
    if is_string(sigma_type):
        if sigma_type.lower() == 'noise':
            # initial idea was to estimate error from the noise in a small window
            variance_window = 10
            sigma = signal.where(signal['time'] < signal['time'][0] + variance_window).std(dim='time')
            printv(sigma.rename('noise').to_dataframe())
            printv('  > Mean noise is {:}'.format(np.mean(sigma.values)))
        # proportional error with a fixed floor for all channels, similar to EFIT implementation
        if sigma_type.lower() == 'efit':
            # device specific calculations
            if is_device(server, 'DIII-D'):
                signal_floor = []
                altkeys = root['DATA']['DIII-D']['channel_alternates']
                for key in signal['channel'].values:
                    header = {}
                    for d_type in ['rarray']:  # also available are 'real32', 'real64',
                        TDI = 'pthead2("{}",{}),__{}'.format(altkeys.get(key, key), shot, d_type)
                        header[d_type] = OMFITmdsValue('atlas', shot=shot, TDI=TDI).data()
                    na_inverse = header['rarray'][3]  # 1/NA
                    rcgvb = header['rarray'][4]  # (RC/G) (V/bit), note sensitivity = NA (RC/G) [V/T]
                    signal_floor.append(abs(80 * rcgvb * na_inverse))  # 80 bit floor in T
                sigma = DataArray(signal_floor, coords=[('channel', signal['channel'])], name='80bit_floor')
                printv(sigma.rename('80 bit floor').to_dataframe())
                if 0.0 in sigma.values:
                    printw('  > Replacing 0s with minimum positive sigma')
                    sigma.values[sigma.values <= 0] = np.min(sigma.values[sigma.values > 0])
                printv('  > Mean bit floor is {}'.format(np.mean(sigma.values)))
                # todo: add time dependent proportional error (this breaks fitting right now)
                # proportional_sigma = np.abs(signal.values) * 0.03
                # proportional_sigma[proportional_sigma < sigma] = sigma
                # sigma = DataArray(proportional_sigma, coords=signal.coords, dims=signal.dims)
            else:
                raise OMFITexception('Unknown sigma type for {} data. Try a constant value.'.format(server))
    elif is_numeric(sigma_type):
        # fixed error for all channels
        sigma = DataArray([sigma_type] * len(signal['channel']), coords=[('channel', signal['channel'].values)])
        printv('  > Fixing all raw uncertainties to constant {:}'.format(sigma_type))
    else:
        raise OMFITexception('Unknown sigma type')

    # is there a better way to simultaneously handle measurements on different time bases (i.e. coils and sensors)
    if 'time' in root['INPUTS']['RAW'] and not np.all(signal['time'].values == root['INPUTS']['RAW']['time'].values):
        dt_old = root['INPUTS']['RAW']['time'].values[1] - root['INPUTS']['RAW']['time'].values[0]
        dt_new = signal['time'].values[1] - signal['time'].values[0]
        if dt_new > dt_old:
            printw(" > Interpolating new signals to higher sampling of existing data")
            signal = reindex_interp(
                signal, time=root['INPUTS']['RAW']['time'], method='nearest', interpolate_kws={'bounds_error': False, 'fill_value': np.nan}
            )
        else:
            printw(" > Interpolating existing data to sampling of new signals")
            root['INPUTS']['RAW'] = reindex_interp(
                root['INPUTS']['RAW'], time=signal['time'], method='nearest', interpolate_kws={'bounds_error': False, 'fill_value': np.nan}
            )
    if 'signal' in root['INPUTS']['RAW']:
        # update arrays channel by channel
        for c in signal['channel'].values:
            i = where(root['INPUTS']['RAW']['signal']['channel'] == c)[0]
            root['INPUTS']['RAW']['signal'].values[i, :] = signal.sel(channel=c).values
            root['INPUTS']['RAW']['signal_sigma'].values[i] = sigma.sel(channel=c).values
    else:
        root['INPUTS']['RAW'] = root['INPUTS']['RAW'].update({'signal': signal, 'signal_sigma': sigma})
    root['INPUTS']['RAW'].attrs['shot'] = shot
    root['INPUTS']['RAW'].attrs['device'] = server
    root['INPUTS']['RAW'].attrs['sigma_type'] = sigma_type

    # check helicity of shot
    bt = OMFITmdsValue(server=server, treename=treename, TDI='bt', shot=shot)
    bt = DataArray(bt.data(), coords={'time': bt.dim_of(0)}, dims=('time',), name='Bt')
    ip = OMFITmdsValue(server=server, treename=treename, TDI='ip', shot=shot)
    ip = DataArray(ip.data(), coords={'time': ip.dim_of(0)}, dims=('time',), name='Ip')
    sign_bt = np.sign(np.nanmedian(bt.values))
    sign_ip = np.sign(np.nanmedian(ip.values))

    # Save some waveforms for plotting:
    root['INPUTS']['PLASMA_PARAMS'] = Dataset()
    root['INPUTS']['PLASMA_PARAMS']['Ip'] = ip
    root['INPUTS']['PLASMA_PARAMS']['Bt'] = bt.interp(time=ip['time'].values, kwargs=dict(fill_value=0))
    root['INPUTS']['PLASMA_PARAMS'].attrs['helicity'] = int(sign_bt / sign_ip)

else:
    if not re_using:
        raise OMFITexception("No data available for {:} in shot {:}".format(channel_filter, shot))
