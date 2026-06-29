'''
check if the desired spectrogram was already calculated and stored in the output tree.
If it was not, then it computes the spectrogram from the 2 selected sensors.
'''

# set variables
device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
p1 = root['SETTINGS']['SPECTROGRAM']['p1']['tag']
p2 = root['SETTINGS']['SPECTROGRAM']['p2']['tag']
deltat = root['SETTINGS']['SPECTROGRAM']['SpecSingleDt']
tinterval = root['SETTINGS']['SPECTROGRAM']['SpecTotalDt']
newsampling = root['SETTINGS']['SPECTROGRAM']['newsampling']
integ = root['SETTINGS']['SPECTROGRAM']['integrate']
spect_name = root['SETTINGS']['SPECTROGRAM']['name']

root['SETTINGS']['SPECTROGRAM']['2pt'] = True

# import shared routines
import OMFITlib_spectrogram_utilities as spec_utils


def calculate_spectrogram(x, d1, d2, dtheta, deltat=0.001, tinterval=None):

    nx = len(x)
    dt = np.round(1e9 * (x[-1] - x[0]) / (nx - 1)) / 1e9
    nt = int(np.round(deltat / dt))  # nt = time samples per slice

    nxbeg = 0
    nxend = nx - 1

    ns = (nxend - nxbeg - nt) * 2 / nt + 1  # ns = number of time slices
    i0 = (nxbeg + np.arange(0, ns, dtype=np.int_) * nt // 2)[:-1]  # i0 = base index of slice
    t_new = x[i0] + deltat / 2.0

    print('starting FFT')

    for i in i0:

        dd1 = d1[i : i + nt - 1]
        dd2 = d2[i : i + nt - 1]

        fs = round(1 / (x[1] - x[0]))

        f, power_dum, coherence_dum, mode_dum, rms_dum, n = spec_utils.calculate_fft(dd1, dd2, fs, dtheta)

        try:
            power = np.vstack([power, power_dum])
            coherence = np.vstack([coherence, coherence_dum])
            mode = np.vstack([mode, mode_dum])
            rms = np.vstack([rms, rms_dum])
        except:
            power = power_dum
            coherence = coherence_dum
            mode = mode_dum
            rms = rms_dum

    print('done')

    return t_new, f, power, coherence, mode, rms, n


try:
    base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']
    if (p1 not in list(base)) | (p2 not in list(base)):
        root['SETTINGS']['SPECTROGRAM']['highn'] = False
        root['SETTINGS']['SPECTROGRAM']['highf'] = False
        root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()
except:
    root['SCRIPTS']['SPECTROGRAM']['get_bdot_info'].run()
    root['SETTINGS']['SPECTROGRAM']['highn'] = False
    root['SETTINGS']['SPECTROGRAM']['highf'] = False
    root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()
    base = root['INPUTS']['SPECTROGRAM'][device][shot]['RAW']

t = base[p1]['time']
d1 = base[p1]['data']
d2 = base[p2]['data']
dtheta = base[p1]['tang'] - base[p2]['tang']

time, d1 = spec_utils.downsampling(t, d1, tinterval=tinterval, newsampling=newsampling)
time, d2 = spec_utils.downsampling(t, d2, tinterval=tinterval, newsampling=newsampling)

if integ:
    d1 = spec_utils.integrate(time, d1, deltat=0.1)
    d2 = spec_utils.integrate(time, d2, deltat=0.1)


t, f, power, coherence, mode, rms, n = calculate_spectrogram(time, d1, d2, dtheta=dtheta, deltat=deltat, tinterval=tinterval)

FFT_data = {
    'shot': shot,
    'time': t,
    'frequency': f,
    'mode': mode,
    'power': power,
    'n': n,
    'rms': rms,
    'integ': integ,
    'deltat': deltat,
    'tinterval': tinterval,
    'newsampling': newsampling,
    'p1': p1,
    'p2': p2,
}


if 'SPECTROGRAM' not in list(root['OUTPUTS']):
    root['OUTPUTS']['SPECTROGRAM'] = OMFITtree()
if device not in list(root['OUTPUTS']['SPECTROGRAM']):
    root['OUTPUTS']['SPECTROGRAM'][device] = OMFITtree()
if shot not in list(root['OUTPUTS']['SPECTROGRAM'][device]):
    root['OUTPUTS']['SPECTROGRAM'][device][shot] = OMFITtree()
if spect_name not in list(root['OUTPUTS']['SPECTROGRAM'][device][shot]):
    root['OUTPUTS']['SPECTROGRAM'][device][shot][spect_name] = OMFITtree()

root['OUTPUTS']['SPECTROGRAM'][device][shot][spect_name].update(FFT_data)
