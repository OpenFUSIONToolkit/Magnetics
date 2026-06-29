"""
Created on Tue Apr  6 10:45:21 2021
Script to plot the relative phase between all the sensor of an array

@author: smunaret
"""

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
highn = root['SETTINGS']['SPECTROGRAM']['highn']
highf = root['SETTINGS']['SPECTROGRAM']['highf']
tinterval = root['SETTINGS']['SPECTROGRAM']['FFTinterval']
frequency = root['SETTINGS']['SPECTROGRAM']['frequency']
newsampling = root['SETTINGS']['SPECTROGRAM']['newsampling']

root['SETTINGS']['SPECTROGRAM']['2pt'] = False

import OMFITlib_spectrogram_utilities as spec_utils

printe('Possibly still some issues with retrieving MDSplus data without OMFIT crashing')


def plot_mode(mirnov, siglist, tinterval=None, frequency=0, newsampling=2e5, poloidal=False, fig=None):

    data, f = spec_utils.get_mode_2d(mirnov, siglist, tinterval=tinterval, frequency=frequency, newsampling=newsampling)

    pol = data['pol']
    tor = data['tor']
    phases = data['phases']
    amps = data['amps']
    cohs = data['cohs']

    if poloidal:
        tor_dum = [int(c) for c in tor]
        a, b = np.unique(tor_dum, return_counts=True)
        if max(b) == 1:
            return
        (ind,) = np.where(tor_dum == a[np.where(b > 1)][0])
        x = pol[ind]
        phases = phases[ind]
        amps = amps[ind]
        cohs = cohs[ind]
        x[x > 180] -= 360
    else:
        pol_dum = [int(c) for c in pol]
        a, b = np.unique(pol_dum, return_counts=True)
        (ind,) = np.where(pol_dum == a[np.where(b > 1)][0])
        x = tor[ind]
        phases = phases[ind]
        amps = amps[ind]
        cohs = cohs[ind]

    phases -= phases[np.argmax(x)]
    phases[phases < 0] += 360

    if fig == None:
        fig = plt.figure(figsize=(8, 9))

    ax1 = fig.use_subplot(211)
    ax2 = fig.use_subplot(413, sharex=ax1)
    ax3 = fig.use_subplot(414, sharex=ax1)

    fig.suptitle(
        'frequency = ' + str(f * 1e-3) + ' kHz, time = ' + '{0:6.5}'.format((tinterval[0] + (tinterval[1] - tinterval[0]) / 2.0)) + ' s'
    )
    normalize = matplotlib.colors.Normalize(vmin=0, vmax=1)
    ax1.scatter(x, phases, c=amps / max(amps), cmap='Blues', norm=normalize, edgecolor='k')
    ax2.scatter(x, amps, c=amps / max(amps), cmap='Blues', norm=normalize, edgecolor='k')
    ax3.scatter(x, cohs, c=amps / max(amps), cmap='Blues', norm=normalize, edgecolor='k')

    plt.setp(ax1.get_xticklabels(), visible=False)
    plt.setp(ax2.get_xticklabels(), visible=False)

    ax2.set_ylim(0, max(amps))
    ax3.set_ylim(0, 1)

    if poloidal:
        ax1.set_xlim(-180, 180)
    else:
        ax1.set_xlim(0, 360)
    ax1.set_ylim(0, 360)

    ax1.set_ylabel('phase')
    ax2.set_ylabel('amplitude')
    ax3.set_ylabel('coherence')
    if highn:
        ax1.set_title(str(shot) + ' high_n')
    else:
        ax1.set_title(str(shot) + ' high_f')


if not (highn | highf):
    highn = root['SETTINGS']['SPECTROGRAM']['highn'] = True
    root['__scratch__']['array_selected'] = 'High n'
root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()


what = 'hn'
if highf:
    what = 'hf'


siglist_all = root['INPUTS']['SPECTROGRAM'][device][shot][what]['cnam']
mirnov = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']
siglist = []
for sig in siglist_all:
    if sig in mirnov:
        siglist.append(sig)


plot_mode(mirnov, siglist, tinterval=tinterval, frequency=frequency, newsampling=newsampling, poloidal=False)
plot_mode(mirnov, siglist, tinterval=tinterval, frequency=frequency, newsampling=newsampling, poloidal=True)

cndev = device
if (device == 'NSTX') & (shot > 200000):
    cndev = 'NSTX-U'
cornernote(device=cndev, shot=shot, time='')
