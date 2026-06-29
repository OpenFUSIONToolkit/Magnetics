# -*-Python-*-
# Created by myersc at 12 May 2017  06:48

"""
This GUI facilitates specialized plotting for the 3D coils.

"""

# variables
channel_filters = root['DATA'][root['SETTINGS']['EXPERIMENT']['device']]['channel_filters']
phys = root['SETTINGS']['PHYSICS']

OMFITx.Entry(
    "root['SETTINGS']['EXPERIMENT']['device']", 'Device', check=is_string, postcommand=lambda location: root['SCRIPTS']['init'].run()
)

OMFITx.Entry("root['SETTINGS']['EXPERIMENT']['shot']", 'Shot', check=is_int, postcommand=lambda location: root['SCRIPTS']['init'].run())

OMFITx.Separator()

OMFITx.Label('Data')

OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['fit_C']", "Fit C-coils", default=True)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['fit_IU']", "Fit I-coils (Upper)", default=True)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['fit_IL']", "Fit I-coils (Lower)", default=True)

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['channels_C']",
    ['C.*', 'PCC.*', 'RLC.*'],
    default='C.*',
    lbl='C-coil regex',
    state='normal',
    help='Regular expression filter for channel names. \n' + 'Example: "M.*" for all channels starting with "M".',
)
OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['channels_IU']",
    ['IU.*', 'PCIU.*'],
    default='IU.*',
    lbl='IU-coil regex',
    state='normal',
    help='Regular expression filter for channel names. \n' + 'Example: "M.*" for all channels starting with "M".',
)
OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['channels_IL']",
    ['IL.*', 'PCIL.*'],
    default='IL.*',
    lbl='IL-coil regex',
    state='normal',
    help='Regular expression filter for channel names. \n' + 'Example: "M.*" for all channels starting with "M".',
)

OMFITx.Separator()

OMFITx.Entry("root['SETTINGS']['PHYSICS']['prep_cutoff_hz']", "Filter (Low, High) Cutoff", default=(0.0, 500.0))
OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['prep_detrend_type']", ['None', 'Baseline', 'Linear'], "Detrend type", default='None')
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['prep_detrend_band']",
    "Detrend band",
    default=(0, 0.1),
    help="Time window in which baseline and linear trends are calculated or \n"
    + "frequency band (Hz) of lowpass trend. For example: LowPass (0, 1) subtracts the sub-1Hz trend.",
)
OMFITx.Entry("root['SETTINGS']['PHYSICS']['prep_time_trim']", "Trim to time window", default=(0, 10))

OMFITx.Separator()

OMFITx.Label('Fit')

OMFITx.Entry("root['SETTINGS']['PHYSICS']['fit_key']", "Key", default='coil_fit')
OMFITx.Entry("root['SETTINGS']['PHYSICS']['fit_ns']", "Toroidal modes", default=[1, 2, 3])
OMFITx.Entry("root['SETTINGS']['PHYSICS']['fit_ms']", "Poloidal modes", default=[0])
OMFITx.Entry("root['SETTINGS']['PHYSICS']['fit_energy']", "Percent energy included", default=0.98)
OMFITx.Entry("root['SETTINGS']['PHYSICS']['fit_cond']", "Fit condition limit", default=1e3)
OMFITx.CheckBox("root['SETTINGS']['PHYSICS']['fit_lsv']", "Fit Left Singular Vectors", default=False)


OMFITx.Separator()

OMFITx.Button("Run", "root['SCRIPTS']['run_coils']")

OMFITx.Separator()

OMFITx.Button("Plot 3D coil modes", lambda: root['PLOTS']['plot_coil_modes'].run(key=phys['fit_key']))
