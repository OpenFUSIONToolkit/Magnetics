"""
Created on Mon May 10 08:36:28 2021
GUI to plot spectrogram and analyze bdot signals
@author: smunaret
"""
# set variables
device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']

valid_devices = ['NSTX', 'NSTX-U']

# import routines
import OMFITlib_spectrogram_utilities as spec_utils

# GUI
OMFITx.TitleGUI('Magnetics Spectrogram')

# add a function for NSTX/NSTXU that assignes the proper device given a shot number.


def fixNSTXshotdevice(shot):
    if shot >= 200000:
        if is_device(root['SETTINGS']['EXPERIMENT']['device'], 'NSTX'):
            printi('NSTX/NSTX-U shot > 200000, set the device to NSTX-U')
            root['SETTINGS']['EXPERIMENT']['device'] = 'NSTX-U'
    else:
        if is_device(root['SETTINGS']['EXPERIMENT']['device'], ['NSTX-U', 'NSTXU']):
            printi('NSTX/NSTX-U shot < 200000, set the device to NSTX')
            root['SETTINGS']['EXPERIMENT']['device'] = 'NSTX'


####################################################################################


def checkDevice(device):
    device = tokamak(device, translation_dict={'NSTXU': 'NSTX'})
    if device == 'NSTX':
        fixNSTXshotdevice(root['SETTINGS']['EXPERIMENT']['shot'])
    return is_device(device, valid_devices)


def checkShot(shot):
    device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
    if device == 'NSTX':
        fixNSTXshotdevice(shot)
    return is_int(shot)


OMFITx.ShotTimeDevice(
    showTime=False,
    showDevice=valid_devices,
    checkDevice=checkDevice,
    checkShot=checkShot,
    updateGUI=True,
    postcommand=lambda location: root['SCRIPTS']['SPECTROGRAM']['spectrogram_init'].run(),
)


# check settings
if not checkDevice(device):
    OMFITx.Label(f'{device} is not currently supported', style='dangerous')
    OMFITx.Label(f'Currently support devices are: \n{valid_devices}')
    OMFITx.End()

options = []
try:
    options.extend(root['INPUTS']['SPECTROGRAM'][device][shot]['hn']['cnam'])
except Exception:
    pass
try:
    options.extend(root['INPUTS']['SPECTROGRAM'][device][shot]['hf']['cnam'])
except Exception:
    pass


if tokamak(device) == 'NSTX':
    defaultp1 = '\\bdot_l1dmivvhn14_raw'
    defaultp2 = '\\bdot_l1dmivvhn16_raw'
if tokamak(device) == 'NSTXU':
    defaultp1 = '\\top.mirnov.rawdata:fm_dt216_01:input_09'
    defaultp2 = '\\top.mirnov.rawdata:fm_dt216_01:input_05'

OMFITx.ComboBox(
    "root['SETTINGS']['SPECTROGRAM']['p1']['tag']",
    options,
    lbl='Sensor #1',
    check=is_string,
    default=defaultp1,
    postcommand=lambda location: spec_utils.refresh_deltat(),
    updateGUI=True,
    help='Select the two sensors used for the spectrogram and the FFT.\n'
    + 'A large "Delta toroidal" reduces the highest number of n that can be identified,\n'
    + 'a small "Delta toroidal" increases the maximum n but loses in resolution for the low n.\n'
    + '"Delta poloidal" informs you whether you are looking at sensors in the same toroidal array (good)\n'
    + 'or not (usually bad since the phase information contains a mix of n and m).\n'
    + 'The analysis does not handle poloidal arrays.',
)

OMFITx.ComboBox(
    "root['SETTINGS']['SPECTROGRAM']['p2']['tag']",
    options,
    lbl='Sensor #2',
    check=is_string,
    default=defaultp2,
    postcommand=lambda location: spec_utils.refresh_deltat(),
    updateGUI=True,
    help='Select the two sensors used for the spectrogram and the FFT.\n'
    + 'A large "Delta toroidal" reduces the highest number of n that can be identified,\n'
    + 'a small "Delta toroidal" increases the maximum n but loses in resolution for the low n.\n'
    + '"Delta poloidal" informs you whether you are looking at sensors in the same toroidal array (good)\n'
    + 'or not (usually bad since the phase information contains a mix of n and m).\n'
    + 'The analysis does not handle poloidal arrays.',
)

if abs(root['__scratch__']['delta_theta']) > 1:
    labelcolor = 'red'
else:
    labelcolor = 'limegreen'

OMFITx.Label(
    "Delta toroidal= " + str(root['__scratch__']['delta_phi']) + " Delta poloidal= " + str(root['__scratch__']['delta_theta']),
    bg=labelcolor,
)

OMFITx.Button('Plot single sensors', "root['PLOTS']['SPECTROGRAM']['plot_bdots']")

OMFITx.Separator()


def is_2pt_list(vals):
    if size(vals) == 2:
        return True
    else:
        return False


def set_MDSplus_tint(location):
    t0, t1 = eval(location)
    root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmin'] = t0
    root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmax'] = t1
    root['SETTINGS']['SPECTROGRAM']['forceupdate'] = True


OMFITx.Entry(
    "root['__scratch__']['dtMDS']",
    'Time interval for raw signal [s]',
    default=[0, 2],
    check=is_2pt_list,
    help='time interval of the signal read from MDSplus',
    postcommand=set_MDSplus_tint,
)


def set_tdelta(location):
    root['SETTINGS']['SPECTROGRAM']['newsampling'] *= 1e3
    root['SETTINGS']['SPECTROGRAM']['forceupdate'] = True
    root['SETTINGS']['SPECTROGRAM']['MDSplus']['tdelta'] = 1.0 / float(root['SETTINGS']['SPECTROGRAM']['newsampling'])


OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['newsampling']",
    'Sampling rate [kHz]',
    # check=is_int,
    default=200,
    help='Sampling rate for the analysis. This loads a downsampled signal from MDSplus',
    preentry=lambda value: value * 1e-3,
    postcommand=set_tdelta,
)


OMFITx.CheckBox(
    "root['SETTINGS']['SPECTROGRAM']['integrate']", 'Integrate', help='If selected, the signals are software integrated', default=False
)


OMFITx.Separator()

OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['name']",
    'Spectrogram name',
    check=is_string,
    default='initial',
    help='name to identify the spectrogram in the tree',
)


def is_list(vals):
    if size(vals) == 2:
        if (vals[0] >= root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmin']) & (
            vals[1] <= root['SETTINGS']['SPECTROGRAM']['MDSplus']['tmax']
        ):
            return True
    else:
        printe('The requested interval is outside the available MDSplus data interval')
        return False


OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['SpecTotalDt']",
    'Spectrogram time interval (s)',
    check=is_list,
    default=[0, 1],
    help='Time interval of the spectrogram in s.\n It must be within the MDSplus range.',
)

OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['SpecSingleDt']",
    'Time window for each FFT (s)',
    check=is_float,
    default=0.001,
    help='Time window of each FFT of the spectrogram in s',
)


OMFITx.CheckBox(
    "root['SETTINGS']['SPECTROGRAM']['prop_to_power']",
    'Spectrogram contour proportional to power',
    help='If selected, the "Plot spectrogram" button plots contour surfaces based on the power of each mode.\n'
    + 'If not selected the contour surfaces are based only on the mode number.',
    default=True,
    updateGUI=True,
)


if root['SETTINGS']['SPECTROGRAM']['prop_to_power']:
    OMFITx.CheckBox(
        "root['SETTINGS']['SPECTROGRAM']['log_plot']",
        'Log (if checked) or linear contour',
        help='''
        If selected, the "Plot spectrogram" button plots contour surfaces on a log scale in base 10 from min to max,
        multiplied by the max amplitude of each mode. If not selected the contour surfaces are on a linear scale
        from 0 to 1 time the max amplitude of each mode.
        ''',
        default=True,
        updateGUI=True,
    )
    if root['SETTINGS']['SPECTROGRAM']['log_plot']:
        def_min = -4
        def_max = -1
    else:
        def_min = 0
        def_max = 1
    with OMFITx.same_row():
        OMFITx.Entry(
            "root['SETTINGS']['SPECTROGRAM']['lev_min']",
            'Min',
            default=def_min,
            help='Plot contour lines from min (or 10^min) * max mode amplitude',
        )
        OMFITx.Entry(
            "root['SETTINGS']['SPECTROGRAM']['lev_max']",
            'Max',
            default=def_max,
            help='Plot contour lines up to max (or 10^max) * max mode amplitude',
        )

    OMFITx.Entry(
        "root['SETTINGS']['SPECTROGRAM']['levels']",
        'Number of levels for the contour plot',
        default=20,
        check=is_int,
        help='Number of levels for the contour plot',
    )

OMFITx.ComboBox(
    "root['SETTINGS']['SPECTROGRAM']['what_to_plot']",
    ['all', '1,2,3,4', 'selected'],
    lbl='What to plot',
    help='Select the kind of plot the button "Plot spectrogram" will produce.',
    default='1,2,3,4',
)

OMFITx.Button('Select n to plot', "root['GUIS']['SPECTROGRAM']['spectrogram_n_to_plot']")

OMFITx.Button('Plot mode spectrogram', "root['PLOTS']['SPECTROGRAM']['plot_spectrogram']")

OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['levels_auto']",
    'Levels',
    default=logspace(-5, -1, 20, base=10),
    help='Levels for the power spectrogram contour plot.\n The default is logspace(-5, -1, 20, base=10) ',
)
OMFITx.Button('Plot sensor #1 power spectrogram', "root['PLOTS']['SPECTROGRAM']['plot_auto_spectrogram']")

OMFITx.Separator()


OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['FFTinterval']",
    'FFT time interval [s]',
    check=is_list,
    default=[0.4, 0.5],
    help='Time interval for the single FFT in s',
)

OMFITx.Button('Plot FFT', "root['PLOTS']['SPECTROGRAM']['plot_fft']")

OMFITx.Separator()

OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['frequency']",
    'frequency [kHz]',
    default=0,
    help='Set the frequency at which the relative phases are plotted.\n' + 'If 0,the frequency with the larger amplitude will be selected.',
    norm=1e3,
)


def set_array(location):
    if root['__scratch__']['array_selected'] == 'None':
        root['SETTINGS']['SPECTROGRAM']['highn'] = False
        root['SETTINGS']['SPECTROGRAM']['highf'] = False
    elif root['__scratch__']['array_selected'] == 'High n':
        root['SETTINGS']['SPECTROGRAM']['highn'] = True
        root['SETTINGS']['SPECTROGRAM']['highf'] = False
    elif root['__scratch__']['array_selected'] == 'High f':
        root['SETTINGS']['SPECTROGRAM']['highn'] = False
        root['SETTINGS']['SPECTROGRAM']['highf'] = True


if device == 'NSTX':
    OMFITx.ComboBox(
        "root['__scratch__']['array_selected']",
        ['None', 'High n', 'High f'],
        lbl='Array to plot',
        help='Select one',
        default='None',
        postcommand=set_array,
    )

OMFITx.Button('Plot phases', "root['PLOTS']['SPECTROGRAM']['plot_phases']")

OMFITx.Separator()

OMFITx.Entry(
    "root['SETTINGS']['SPECTROGRAM']['time_of_interest']",
    'times [s]',
    default=[0.5],
    help='Set the times to plot radial profiles',
)

OMFITx.ComboBox(
    "root['SETTINGS']['SPECTROGRAM']['xaxis']",
    ['radius', 'psin'],
    lbl='x axes',
    help='If selected, the x axis of the plots are PsiN.\n' + 'If not selected the x axis of the plots are major radius.',
    default='psin',
    updateGUI=True,
)


if root['SETTINGS']['SPECTROGRAM']['xaxis'] == 'psin':
    OMFITx.Entry(
        "root['SETTINGS']['SPECTROGRAM']['EFIT']",
        'Fit',
        default='EFIT01',
        help='Choose efit to use for the q profile and PsiN',
    )

    with OMFITx.same_row():
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][0]",
            'core',
            # help='If selected, n=1 is plotted on the spectrogram.',
            default=True,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][1]",
            'q=1',
            # help='If selected, n=1 is plotted on the spectrogram.',
            default=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][2]",
            'q=3/2',
            # help='Plot on the spectrogram what is selected.',
            default=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][3]",
            'q=2',
            # help='Plot on the spectrogram what is selected.',
            default=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][4]",
            'q=3',
            # help='Plot on the spectrogram what is selected.',
            default=False,
        )
        OMFITx.CheckBox(
            "root['SETTINGS']['SPECTROGRAM']['qtoplot'][5]",
            'q=4',
            help='Plot on the spectrogram what is selected.',
            default=False,
        )

with OMFITx.same_row():
    OMFITx.CheckBox(
        "root['SETTINGS']['SPECTROGRAM']['nforradprof'][0]",
        'n=1',
        default=True,
    )
    OMFITx.CheckBox(
        "root['SETTINGS']['SPECTROGRAM']['nforradprof'][1]",
        'n=2',
        # help='If selected, n=1 is plotted on the spectrogram.',
        default=False,
    )
    OMFITx.CheckBox(
        "root['SETTINGS']['SPECTROGRAM']['nforradprof'][2]",
        'n=3',
        help='Plot on the spectrogram what is selected.',
        default=False,
    )

OMFITx.CheckBox(
    "root['SETTINGS']['SPECTROGRAM']['plot_together']",
    'Plot TS and CER together',
    help='If selected, one single figure is plotted.',
    default=True,
)

OMFITx.Button('Plot radial profiles', "root['PLOTS']['SPECTROGRAM']['plot_radial_profiles']")
