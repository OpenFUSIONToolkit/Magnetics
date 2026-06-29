# -*-Python-*-
# Created by smunaret at 05 Oct 2021  15:02

"""
This script plot the power density spectrogram of a given signal using scipy.signal.spectrogram .


defaultVars parameters
----------------------
device    : device
shot      : shot number
p1        : tag of the signal to be plotted
deltat    : time window used to perform the FFT
tinterval : time interval of the plot
lev       : levels used for the countour plot
ax        : axes where to plot the contour. If None a new plot is created
fig       : figure where to plot the contour. If None a new plot is created
ylim      : frequnecy interval for the plot (in kHz)
"""

defaultVars(
    device=tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'}),
    shot=root['SETTINGS']['EXPERIMENT']['shot'],
    p1=root['SETTINGS']['SPECTROGRAM']['p1']['tag'],
    deltat=root['SETTINGS']['SPECTROGRAM']['SpecSingleDt'],
    tinterval=root['SETTINGS']['SPECTROGRAM']['SpecTotalDt'],
    newsampling=root['SETTINGS']['SPECTROGRAM']['newsampling'],
    lev=root['SETTINGS']['SPECTROGRAM']['levels_auto'],
    ax=None,
    fig=None,
    ylim=[0, root['SETTINGS']['SPECTROGRAM']['newsampling'] / 2e3],
    title=None,
)

import OMFITlib_spectrogram_utilities as spec_utils

if (fig is None) | (ax is None):
    fig, ax = subplots(1, 1)


root['SETTINGS']['SPECTROGRAM']['highn'] = False
root['SETTINGS']['SPECTROGRAM']['highf'] = False
root['SETTINGS']['SPECTROGRAM']['2pt'] = False
root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()
ds = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW'][p1]

t = ds['time']
d1 = ds['data']

time, d1 = spec_utils.downsampling(t, d1, tinterval=tinterval, newsampling=newsampling)

fs = 1.0 / (time[1] - time[0])
window = arange(time[0], time[-1], deltat)
f, t, a = scipy.signal.spectrogram(d1, fs=fs, window=window, scaling='density')
t += time[0] + deltat / 2.0
im = ax.contourf(t, f * 1e-3, a, cmap='inferno_r', levels=lev, extend='both', norm=matplotlib.colors.LogNorm())
if title is None:
    ax.set_title(shot)
else:
    ax.set_title(title)
ax.set_ylim(ylim[0], ylim[1])
ax.set_xlim(tinterval[0], tinterval[1])
ax.set_ylabel('frequency [kHz]')
ax.set_xlabel('time [s]')


fig.subplots_adjust(right=0.85, wspace=0.3, left=0.1)
axy = np.array(ax.get_position())
cax = fig.add_axes([0.86, axy[0, 1], 0.02, axy[1, 1] - axy[0, 1]])

cb = matplotlib.colorbar.Colorbar(cax, im)
nlev = len(lev)
ticks = [lev[0], lev[int(nlev / 2)], lev[-1]]
cb.set_ticks(ticks)
cb.set_ticklabels(['{:.1E}'.format(lev[0]), '{:.1E}'.format(lev[int(nlev / 2)]), '{:.1E}'.format(lev[-1])])

cb.ax.set_title(r'$(T/s)^2/Hz$')

cornernote(text=p1, time='', shot='', device='')
