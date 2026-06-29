'''
script to plot all the avilable bdot data.
Intended for helping making a choice of which 2 sensors use for the mode spectrogram.
'''

# to allow for embedding the plot in an existing figure
defaultVars(fig=None)

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
integ = root['SETTINGS']['SPECTROGRAM']['integrate']

if shot in list(root['INPUTS']['SPECTROGRAM'][device]):
    for what in ['hn', 'hf']:
        base = root['INPUTS']['SPECTROGRAM'][device][shot][what]
        print(what)
        print('name      tor      pol')
        for n, t, p in zip(base['cnam'], base['tor'], base['pol']):
            print(n, t, p)


root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run(is2pt=False, highf=True, highn=False)
root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run(is2pt=False, highf=False, highn=True)

for what in ['hn', 'hf']:
    ns = len(root['INPUTS']['SPECTROGRAM'][device][shot][what]['cnam'])
    nr = int(ns / 2.0)
    if ns % 2 != 0:
        nr += 1
    fig, ax = plt.subplots(nr, 2, sharex=True, sharey=True, figsize=(10, 12))
    axf = ax.flatten()

    for ind, sig in enumerate(root['INPUTS']['SPECTROGRAM'][device][shot][what]['cnam']):
        if not (sig in root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']):
            continue
        base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'][sig]
        x = base['time']
        y = base['data']
        tor = base['tang']
        pol = base['pang']
        axf[ind].plot(x, y)
        axf[ind].set_title(sig, fontsize=8)

        axf[ind].annotate('tor = ' + str(tor) + '; pol = ' + str(pol), xy=(0.05, 0.85), xycoords='axes fraction', fontsize=10)

    fig.tight_layout()
    fig.subplots_adjust(wspace=0.2)

if integ:
    # import shared routines for the numerical integration
    import OMFITlib_spectrogram_utilities as spec_utils

    for what in ['hn', 'hf']:
        fig, ax = plt.subplots(nr, 2, sharex=True, sharey=True, figsize=(10, 12))
        axf = ax.flatten()
        for ind, sig in enumerate(root['INPUTS']['SPECTROGRAM'][device][shot][what]['cnam']):
            base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'][sig]
            x = base['time']
            ydot = base['data']
            y = spec_utils.integrate(x, ydot, deltat=0.1)
            tor = base['tang']
            pol = base['pang']
            axf[ind].plot(x, y)
            axf[ind].set_title(sig, fontsize=8)

            axf[ind].annotate('tor = ' + str(tor) + '; pol = ' + str(pol), xy=(0.05, 0.85), xycoords='axes fraction', fontsize=10)

        fig.tight_layout()
        fig.subplots_adjust(wspace=0.2)
