# -*-Python-*-
# Created by myersc at 12 May 2017  06:07

"""
This script plots the amplitudes and phases of the 3D coils.

Parameters

-----------

:param key: fit key under which to store the various 3D coil fits
            the code will generate key_C, key_IU, key_IL as necessary

"""

defaultVars(key=root['SETTINGS']['PHYSICS'].get('fit_key', ''), kwargs={})

coil_strs = []
if root['SETTINGS']['PHYSICS']['fit_C']:
    coil_strs += ['C']
if root['SETTINGS']['PHYSICS']['fit_IU']:
    coil_strs += ['IU']
if root['SETTINGS']['PHYSICS']['fit_IL']:
    coil_strs += ['IL']
nvals = np.array(root['OUTPUTS']['FIT'][key + '_' + coil_strs[0]]['fit_ns'])
nvals_plot = nvals[np.where(nvals != 0.0)]

labels = {'C': 'C-coils', 'IU': 'I-coils (upper)', 'IL': 'I-coils (lower)'}
tlims = root['SETTINGS']['PHYSICS']['prep_time_trim']
amp_thresh = 0.300  # kA

lw = 1.0
lw_ax = 0.75

f1 = plt.figure(num='3D Coils', figsize=(6.5, 7.5))
f1.clf()


def ax_text(ax, txt_str, TB='top', LR='left'):
    if TB == 'top':
        yt = 0.92
    elif TB == 'bottom':
        yt = 0.08
    else:
        raise ValueError(TB)
    if LR == 'left':
        xt = 0.04
    elif TB == 'right':
        xt = 0.96
    else:
        raise ValueError(LR)
    ax.text(xt, yt, txt_str, va=TB, ha=LR, transform=ax.transAxes)


# ------------------------------------------------------------------------------#
# --- Plot the plasma current:

ax1 = f1.add_subplot(4, 2, 1)
ax1.plot(tlims, [0.0, 0.0], 'k', lw=lw_ax)
Ip = root['INPUTS']['PLASMA_PARAMS']['Ip']
ax1.plot(Ip['time'] / 1.0e3, Ip / 1.0e6, 'k', lw=lw)
ax1.set_xlim(tlims)
plt.setp(ax1.get_xticklabels(), visible=False)
ylims = np.array([-0.2 * Ip.max(), 1.6 * Ip.max()]) / 1.0e6
ax1.set_ylim(ylims)
ax_text(ax1, 'Plasma current [MA]', TB='top', LR='left')

# ------------------------------------------------------------------------------#
# --- Plot the plasma density:

ax = f1.add_subplot(4, 2, 2, sharex=ax1)
ax.plot(tlims, [0.0, 0.0], 'k', lw=lw_ax)
density = OMFITmdsValue(
    server=root['SETTINGS']['EXPERIMENT']['device'], treename=None, TDI='density', shot=root['SETTINGS']['EXPERIMENT']['shot']
)
density = DataArray(density.data(), coords={'time': density.dim_of(0)}, dims=['time'], name='density')
ax.plot(density['time'] / 1.0e3, density, 'k', lw=lw)
plt.setp(ax.get_xticklabels(), visible=False)
ylims = np.array([-0.2 * density.max(), 1.6 * density.max()])
ax.set_ylim(ylims)
ax_text(ax, r'Plasma density [cm$^{-3}$]', TB='top', LR='left')

# ------------------------------------------------------------------------------#
# --- Plot the coil amplitudes:

abs_max = -1.0
for coil_str in coil_strs:
    ds = root['OUTPUTS']['FIT'][key + '_' + coil_str]
    amp_max = np.max(np.abs(ds['fit_coeffs']) / 1.0e3)
    if amp_max > abs_max:
        abs_max = amp_max


def plot_amp(nval):
    subplot = 2 * nval + 1
    nindex = list(nvals).index(nval)
    ax = f1.add_subplot(4, 2, subplot, sharex=ax1)
    ax.plot(tlims, [0.0, 0.0], 'k', lw=lw_ax)
    for coil_str in coil_strs:
        ds = root['OUTPUTS']['FIT'][key + '_' + coil_str]
        amp = np.abs(ds['fit_coeffs'].sel(mode=nindex)) / 1.0e3
        ax.plot(ds['time'], amp, lw=lw)
    ax.set_ylim([-0.2 * abs_max, 1.6 * abs_max])
    ax_text(ax, r'Coil current $n=%d$ [kA]' % nval, TB='top', LR='left')
    return ax


for nval in nvals_plot:
    ax = plot_amp(nval)
    if nval < max(nvals):
        plt.setp(ax.get_xticklabels(), visible=False)
    else:
        ax.set_xlabel('Time [s]')

# ------------------------------------------------------------------------------#
# --- Plot the coil phases:

phase_roll = 352.5


def convert_phase(phase):
    phase = (180.0 / np.pi) * phase
    phase = (phase + 360.0) % 360.0
    phase[np.where(phase > phase_roll)] -= 360.0
    return phase


def plot_phase(nval):
    subplot = 2 * nval + 2
    nindex = list(nvals).index(nval)
    ax = f1.add_subplot(4, 2, subplot, sharex=ax1)
    for phase in range(0, 360 + 1, 90):
        ax.plot(tlims, [phase, phase], 'k:', lw=lw_ax)
    for coil_str in coil_strs:
        ds = root['OUTPUTS']['FIT'][key + '_' + coil_str]
        FC = ds['fit_coeffs']
        amp = np.abs(FC.sel(mode=nindex)) / 1.0e3
        phase = convert_phase(np.angle(FC.sel(mode=nindex)))
        inds = np.where(amp > amp_thresh)[0]
        ax.plot(ds['time'][inds], phase[inds], lw=lw, label=labels[coil_str])
    if 'IU' in coil_strs and 'IL' in coil_strs:
        FC_IU = root['OUTPUTS']['FIT'][key + '_IU']['fit_coeffs']
        FC_IL = root['OUTPUTS']['FIT'][key + '_IL']['fit_coeffs']
        phase_IU = convert_phase(np.angle(FC_IU.sel(mode=nindex)))
        phase_IL = convert_phase(np.angle(FC_IL.sel(mode=nindex)))
        amp_IU = np.abs(FC_IU.sel(mode=nindex)) / 1.0e3
        amp_IL = np.abs(FC_IL.sel(mode=nindex)) / 1.0e3
        amp = np.min(np.array([amp_IU, amp_IL]), axis=0)
        inds = np.where(amp > amp_thresh)[0]
        Iphasing = (360.0 + phase_IU - phase_IL) % 360.0
        Iphasing[np.where(Iphasing > phase_roll)] -= 360.0
        ds = root['OUTPUTS']['FIT'][key + '_IU']
        ax.plot(ds['time'][inds], Iphasing[inds], lw=lw, label='I-coil phasing')
    ax.set_ylim([-45.0, 495.0])
    ax.set_yticks([0.0, 90.0, 180.0, 270.0, 360.0])
    ax_text(ax, r'Phase $n=%d$ [deg]' % nval, TB='top', LR='left')
    if nval == 1:
        plt.legend(bbox_to_anchor=(1.0, 2.43), loc=4, ncol=2, borderaxespad=0.0)
    return ax


for nval in nvals_plot:
    ax = plot_phase(nval)
    if nval < max(nvals):
        plt.setp(ax.get_xticklabels(), visible=False)
    else:
        ax.set_xlabel('Time [s]')

# ------------------------------------------------------------------------------#
# --- Final adjustments:

device = root['SETTINGS']['EXPERIMENT']['device']
shot = root['SETTINGS']['EXPERIMENT']['shot']
f1.suptitle('%s %d' % (device, shot), x=0.25, y=0.96)

plt.subplots_adjust(left=0.07, right=0.97, bottom=0.08, top=0.88)

ax1.set_xlim(tlims)

# ==============================================================================#
# ==============================================================================#
