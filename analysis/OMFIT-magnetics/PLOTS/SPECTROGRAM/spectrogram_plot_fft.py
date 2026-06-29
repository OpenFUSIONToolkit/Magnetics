"""
Created on Tue Apr  6 10:45:21 2021
@author: smunaret

Script to plot the cross power and coherence between the 2 selected signals
"""

defaultVars(fig=None)

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
p1 = root['SETTINGS']['SPECTROGRAM']['p1']['tag']
p2 = root['SETTINGS']['SPECTROGRAM']['p2']['tag']
tinterval = root['SETTINGS']['SPECTROGRAM']['FFTinterval']
newsampling = root['SETTINGS']['SPECTROGRAM']['newsampling']
integ = root['SETTINGS']['SPECTROGRAM']['integrate']


import OMFITlib_spectrogram_utilities as spec_utils

try:
    base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']
except Exception:
    root['SCRIPTS']['SPECTROGRAM']['get_bdot_info'].run()
    root['SETTINGS']['SPECTROGRAM']['highn'] = False
    root['SETTINGS']['SPECTROGRAM']['highf'] = False
    root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()
    base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']

if (p1 not in list(base)) | (p2 not in list(base)):
    root['SCRIPTS']['SPECTROGRAM']['get_bdot_info'].run()
    root['SETTINGS']['SPECTROGRAM']['highn'] = False
    root['SETTINGS']['SPECTROGRAM']['highf'] = False
    root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()

time = base[p1]['time']
d1 = base[p1]['data']
d2 = base[p2]['data']
dtheta = base[p1]['tang'] - base[p2]['tang']

x, d1 = spec_utils.downsampling(time, d1, tinterval=tinterval, newsampling=newsampling)
x, d2 = spec_utils.downsampling(time, d2, tinterval=tinterval, newsampling=newsampling)

if integ:
    d1 = spec_utils.integrate(x, d1, deltat=0.1)
    d2 = spec_utils.integrate(x, d2, deltat=0.1)

fs = round(1 / (x[1] - x[0]))
f, power, coherence, mode, rms, n = spec_utils.calculate_fft(d1, d2, fs, dtheta)

if fig == None:
    fig = plt.figure(figsize=(8, 10))

ax1 = fig.use_subplot(411)
ax2 = fig.use_subplot(412)
ax3 = fig.use_subplot(413, sharex=ax2)
ax4 = fig.use_subplot(414, sharex=ax2)

ax1.plot(x, d1, label=p1)
ax1.plot(x, d2, label=p2)
ax1.set_xlim(tinterval)
ax1.set_xlabel = 'time [s]'
if integ:
    ax1.set_ylabel('B\n [$T$]')
else:
    ax1.set_ylabel('dB/dt\n [$T/s$]')
ax1.legend()

ax2.plot(f * 1e-3, power * 1e3)
ax3.plot(f * 1e-3, mode)
ax4.plot(f * 1e-3, coherence, lw=3)
if integ:
    ax2.set_ylabel('Cross-power\n [$T^2/Hz$]')
else:
    ax2.set_ylabel('Cross-power\n [$T^2/s^2/Hz$]')
ax3.set_ylabel('n mode')
ax4.set_ylabel('coherence')
ax4.set_ylim(0, 1.0)
ax4.set_xlabel('frequency [kHz]')
ax1.set_title(shot, fontsize=16)

cndev = device
if (device == 'NSTX') & (shot > 200000):
    cndev = 'NSTX-U'
cornernote(device=cndev, shot=shot, time='')
fig.tight_layout()

print('done plotting FFT')
