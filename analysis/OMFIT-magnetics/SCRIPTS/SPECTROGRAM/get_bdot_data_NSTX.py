'''
Script to fetch the NSTX/NSTX-U data.
The number of signals is based on the plot to be done and the presence of the data in the tree.
The size and sampling rate of the fetched signals is set by tmin, tmax and tdelta.
'''
defaultVars(
    is2pt=root['SETTINGS']['SPECTROGRAM']['2pt'],
    highn=root['SETTINGS']['SPECTROGRAM']['highn'],
    highf=root['SETTINGS']['SPECTROGRAM']['highf'],
    forceupdate=root['SETTINGS']['SPECTROGRAM']['forceupdate'],
)

# set variables
device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
p1 = root['SETTINGS']['SPECTROGRAM']['p1']['tag']
p2 = root['SETTINGS']['SPECTROGRAM']['p2']['tag']
tmin = root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmin']
tmax = root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmax']
tdelta = root['SETTINGS']['SPECTROGRAM']['MDSplus']['tdelta']


if device != 'NSTX':
    raise OMFITexception("Currently only NSTX/NSTX-U is supported.")

if 'SPECTROGRAM' not in list(root['INPUTS']):
    root['SCRIPTS']['SPECTROGRAM']['get_bdot_info'].run()
if 'RAW' not in list(root['INPUTS']['SPECTROGRAM'][device][shot]):
    root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'] = OMFITtree()

# ==================================================================================
def nstxu_array_data(shot, what, forceupdate=False):

    print('--> Getting high-f data for NSTX shot ' + str(shot) + '... ')

    # --- Get the array metadata...positions and similar
    ds = root['INPUTS']['SPECTROGRAM'][device][shot][what]

    mdshost = ds['MDShost']
    datatree = ds['tree']
    tpos = ds['tor']
    polang = ds['pol']
    sig = ds['cnam']
    GainCor = ds['sig']
    nA = ds['na']

    tbreturned = {}

    for (tag, gain, na, tp, pola) in zip(sig, GainCor, nA, tpos, polang):
        print('Getting ' + tag + '...')
        if tag in list(root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']):
            if not forceupdate:
                t = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'][tag]['time']
                if (tmin >= t[0]) & (tmax <= t[-1]) & (tdelta >= (t[1] - t[0])):
                    continue
        # using the resample function of MDSplus introduces aliasing. It is necessary to fetch the whole signal and resample it here.
        # dumraw = OMFITmdsValue(mdshost, treename=datatree, shot=shot, TDI=f'resample({tag},{tmin},{tmax},{tdelta})')
        dumraw = OMFITmdsValue(mdshost, treename=datatree, shot=shot, TDI=tag)

        if dumraw.data() is not None:
            dumdata = dumraw.data() * float(gain) / float(na)
            time = dumraw.dim_of(0)

            tbreturned[tag] = {'time': time, 'data': dumdata, 'raw': dumraw.data(), 'tang': tp, 'pang': pola}

    return tbreturned


# ==================================================================================
def nstxu_single_data(shot, p1):

    print('--> Getting data for NSTX shot ' + str(shot) + '... ')
    print(p1)

    p1 = p1.lower()

    if p1.lower() in [options.lower() for options in root['INPUTS']['SPECTROGRAM'][device][shot]['hn']['cnam']]:
        # --- Get the array metadata...positions and similar
        ds = root['INPUTS']['SPECTROGRAM'][device][shot]['hn']

    elif p1.lower() in [options.lower() for options in root['INPUTS']['SPECTROGRAM'][device][shot]['hf']['cnam']]:
        # --- Get the array metadata...positions and similar
        ds = root['INPUTS']['SPECTROGRAM'][device][shot]['hf']

    else:
        printe(f'Cannot find data for {p1}')
        OMFITx.End(what='all')

    mdshost = ds['MDShost']
    datatree = ds['tree']
    tpos = ds['tor']
    polang = ds['pol']
    sig = ds['cnam']
    GainCor = ds['sig']

    nA = ds['na']

    (ind,) = np.where([c == p1 for c in sig])

    tpos = np.array(tpos)[ind]
    polang = np.array(polang)[ind]
    nA = np.array(nA)[ind]
    sig = np.array(sig)[ind]
    GainCor = np.array(GainCor)[ind]

    tbreturned = {}

    for (tag, gain, na, tp, pola) in zip(sig, GainCor, nA, tpos, polang):
        print('Getting ' + tag + '...')

        # dumraw = OMFITmdsValue(mdshost, treename=datatree, shot=shot, TDI=f'resample({tag},{tmin},{tmax},{tdelta})')
        dumraw = OMFITmdsValue(mdshost, treename=datatree, shot=shot, TDI=tag)
        dumdata = dumraw.data() * float(gain) / float(na)
        time = dumraw.dim_of(0)

        tbreturned[tag] = {'time': time, 'data': dumdata, 'raw': dumraw.data(), 'tang': tp, 'pang': pola}

    return tbreturned


data = {}

if is2pt:
    if p1 != '':
        if (p1 not in list(root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'])) | forceupdate:
            data = nstxu_single_data(shot, p1)
    if p2 != '':
        if (p2 not in list(root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'])) | forceupdate:
            data2 = nstxu_single_data(shot, p2)
            data.update(data2)
elif highn:
    data = nstxu_array_data(shot, 'hn', forceupdate)
elif highf:
    data = nstxu_array_data(shot, 'hf', forceupdate)
else:
    if p1 != '':
        if (p1 not in list(root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'])) | forceupdate:
            print('I am here')
            data = nstxu_single_data(shot, p1)
    # printi('Nothing to fetch')


root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'].update(data)
root['SETTINGS']['SPECTROGRAM']['forceupdate'] = False
