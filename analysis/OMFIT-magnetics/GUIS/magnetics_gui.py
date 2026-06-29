# -*-Python-*-
# Created by logannc at 02 Mar 2017  18:10

OMFITx.Entry(
    "root['SETTINGS']['EXPERIMENT']['device']", 'Device', check=is_string, postcommand=lambda location: root['SCRIPTS']['init'].run()
)

OMFITx.Entry("root['SETTINGS']['EXPERIMENT']['shot']", 'Shot', check=is_int, postcommand=lambda location: root['SCRIPTS']['init'].run())

if root['SETTINGS']['EXPERIMENT']['device'] != 'DIII-D':
    printe('only DIII-D is supported for the 3D analysis')
    OMFITx.End()


# variables
root.setdefault('INPUTS', OMFITtmp())
root['OUTPUTS'].setdefault('FIT', OMFITtree())
if 'RAW' not in root['INPUTS']:
    root['SCRIPTS']['init'].run()
channel_filters = root['DATA'][root['SETTINGS']['EXPERIMENT']['device']]['channel_filters']
phys = root['SETTINGS']['PHYSICS']
root['SETTINGS']['PHYSICS'].setdefault('run_steps', [True, True, True])
##


OMFITx.Label('Data')

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['channels']",
    channel_filters,
    default=list(channel_filters.values())[0],
    lbl='Channels',
    state='normal',
    help='Regular expression filter for channel names. \n' + 'Example: "M.*" for all channels starting with "M".',
)
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['fit_exclude']",
    "Exclude sensors",
    default=(),
    help='List of regular expressions. Sensors matching any of the items will be excluded when fitting.\n'
    + 'Example: ("MPID66M0.*", "MPID66M127")',
)

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['fetch_sigma']",
    [2e-5, 'EFIT', 'NOISE'],
    "Uncertainty estimate",
    default=2e-5,
    state='normal',
    help='Uncertainty of raw data. Set to,\n'
    + '- A number for a floor in Tesla independent of sensor or time\n'
    + '- "EFIT" for a 80 bit floor converted to Tesla using sensor (and day) dependent circuitry\n'
    + '- "NOISE" for the sensor and shot dependent standard deviation in a time prior to plasma breakdown',
)

OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['prep_time_trim']",
    "Trim window (s)",
    default=(0, 10),
    help="Prepared and fit data will be trimmed to be within these bounds",
)
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['prep_cutoff_hz']",
    "Bandpass filter (Hz)",
    default=(1, 500),
    help="High and low frequency cutoffs for band pass filtering the prepared data",
)


def is_inside_trim_window(vals):
    trim = root['SETTINGS']['PHYSICS']['prep_time_trim']
    v = [np.min(np.ravel(vals)), np.max(np.ravel(vals))]
    if v[0] < trim[0] or v[1] > trim[1]:
        return False
    return True


OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['prep_detrend_type']",
    ['None', 'Baseline', 'Linear', 'Endpoints'],
    "Detrend type",
    default='None',
    help="Detrending must happen inside of the trimmed bounds.\n"
    + "Baseline removes each channel's mean from within the band,\n"
    + "Linear removes a linear trend fit within the band, and\n"
    + "Enpoints removes a line connecting the endpoints of the band",
)
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['prep_detrend_band']",
    "Detrend window (s)",
    check=is_inside_trim_window,
    default=root['SETTINGS']['PHYSICS']['prep_time_trim'],
    help="Time window in which detrending functions are calculated",
)
OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['prep_energy']",
    "Fraction of energy included",
    default=1.0,
    help="Sets the minimum singular values kept in a SVD filter of the channel-by-time data matrix. \n"
    + "This filters the data for the most coherent spatial-temporal combinations of sensors of the \n"
    + "selected time window (use 1.0 if the time window includes disparate amplitude scales of interest).",
)

coil_filters = root['DATA'][root['SETTINGS']['EXPERIMENT']['device']].get('coil_filters', None)
if coil_filters is not None:
    OMFITx.CheckBox(
        "root['SETTINGS']['PHYSICS']['prep_dc_comp']", "DC compensation", default=False, help="Remove direct DC pickup from selected coils."
    )
    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['comp_coils']",
        coil_filters,
        default=list(coil_filters.values())[0],
        lbl='Compensate coils',
        state='normal',
        help='Regular expression filter for coil names. \n' + 'Example: "C.*" for all coils starting with "C".',
    )


def toggle_inputs_class(location):
    permanent = eval(location)
    if permanent:
        root['INPUTS'].__class__ = OMFITtree
    else:
        root['INPUTS'].__class__ = OMFITtmp


OMFITx.CheckBox(
    "root['SETTINGS']['SETUP']['inputs_persistent']",
    "Save INPUTS with project",
    default=False,
    postcommand=toggle_inputs_class,
    help="The data in each fit is always saved with the fit.\n"
    + "This is unnecessary unless you are preparing to do a lot of work offline.",
)

OMFITx.Label('Fit')

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['fit_key']",
    list(root['OUTPUTS']['FIT'].keys()) + [''],
    "Name of fit",
    default='n{:}_m{:}_f{:}_comp{:}'.format(
        root['SETTINGS']['PHYSICS']['fit_ns'],
        root['SETTINGS']['PHYSICS']['fit_ms'],
        root['SETTINGS']['PHYSICS']['prep_cutoff_hz'],
        root['SETTINGS']['PHYSICS']['prep_dc_comp'],
    ).replace(' ', ''),
    updateGUI=True,
    help="Result of the fit is placed in ['OUTPUTS']['FIT'] under this name",
    state='normal',
)

if root['SETTINGS']['PHYSICS']['fit_key'] in root['OUTPUTS']['FIT']:
    OMFITx.Button(
        "Restore existing fit's settings",
        "root['SCRIPTS']['restore']",
        help="This fit is already in ['OUTPUTS']['FIT']!\n" + "This will restore all the settings from that fit to the active settings.",
    )

OMFITx.ComboBox(
    "root['SETTINGS']['PHYSICS']['fit_basis']",
    ['sinusoidal-integral', 'sinusoidal-point', 'gaussian-point', 'gaussian-integral'],
    "Basis functions",
    default='sinusoidal-integral',
    updateGUI=True,
    help="Type of basis function used in design matrix. Currently supports,\n"
    + "- sinusoidal-point: fits A exp(i m theta + i n phi) evaluated at sensors centers\n"
    + "- sinusoidal-integral: fits A exp(i m theta + i n phi) integrated over the sensor area",
)
if root['SETTINGS']['PHYSICS']['fit_basis'].startswith('sinusoidal'):
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_ns']",
        "Toroidal modes",
        default=[1, 2, 3],
        help='Toroidal mode numbers. Total number of modes must be less than half the number of channels',
    )
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_ms']",
        "Poloidal mode numbers",
        default=[0],
        help='Poloidal mode numbers. These do not correspond to internal or magnetic coordinate mode numbers.\n'
        'Use [0] if fitting a single toroidal array',
    )
elif root['SETTINGS']['PHYSICS']['fit_basis'].startswith('gaussian'):
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_ncenters']",
        "Number of toroidal centers",
        default=6,
        help='Toroidal Gaussian radial basis function centers.',
    )
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_neps']",
        "Toroidal widths (deg.)",
        default=0,
        help='Toroidal epsilon where the RBF ~ exp(-(phi/epsilon)**2). \n'
        + '0 defaults to approximate average distance between nodes (which is a good start).',
    )
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_mcenters']",
        "Number of poloidal centers",
        default=1,
        help='Poloidal Gaussian radial basis function centers.',
    )
    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['fit_meps']",
        "Poloidal widths (deg or m)",
        default=0,
        help='Poloidal epsilon where the RBF ~ exp(-(y/epsilon)**2). \n'
        + '0 defaults to approximate average distance between nodes (which is a good start).',
    )

OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['fit_omega_hz']",
    "Reference",
    default=None,
    help="A reference frequency (Hz) or name of an existing fit. \nA single fit will be made from all times,"
    + " with each channel correspondingly translated in the toroidal direction.\n "
    + "Using a previous fit references to the largest amplitude mode of that fit",
)

OMFITx.Entry(
    "root['SETTINGS']['PHYSICS']['fit_cond']",
    "Fit condition limit",
    default=10,
    help="Sets the condition number of the basis function matrix used for the lsq fitting.\n"
    + "Smaller condition numbers will ignore mode combinations the chosen channels are relatively \n"
    + "poor at constraining. Sufficiently larger numbers will blindly fit all modes chosen above",
)

OMFITx.CheckBox(
    "root['SETTINGS']['PHYSICS']['fit_lsv']",
    "Fit Left Singular Vectors",
    default=False,
    help="Fit only the spatial structures of each left singular vector from the \n"
    + "channel-by-time data matrix. These fits are then combined with the \n"
    + "right singular vectors to describe the time dependence.",
)

OMFITx.Separator()

step_options = SortedDict()
step_options["Fetch, Prep, Fit, and Plot"] = [True, True, True, True]
step_options["Fetch"] = [True, False, False, False]
step_options["Prep"] = [False, True, False, False]
step_options["Fit and Plot"] = [False, False, True, True]
step_options["Prep, Fit, and Plot"] = [False, True, True, True]
step_options["Prep and Fit"] = [False, True, True, False]
OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['run_steps']", step_options, "Run steps", default=[True, True, True, True], state="readonly")
OMFITx.Button("Run", "root['SCRIPTS']['run_steps']")

OMFITx.Separator()


def plot_sensors():
    """Plot sensors in R,z and the fit geometry"""
    fig, ax = subplots(1, 2)
    root['PLOTS']['plot_sensors'].run(geometry=phys['fit_geometry'], axes=ax[0])
    root['PLOTS']['plot_sensors'].run(geometry='rz', axes=ax[1])
    fig.tight_layout()


OMFITx.Button("Plot sensors", plot_sensors)
OMFITx.Button("Plot input signals", "root['PLOTS']['plot_signal']")

if phys['fit_key'] in root['OUTPUTS']['FIT']:
    OMFITx.Button("Plot SVD conditioning", "root['PLOTS']['plot_svds']")
    OMFITx.Button("Plot chi", lambda: root['PLOTS']['plot_fit'].run(key=phys['fit_key']))
    OMFITx.Button("Plot modes", lambda: root['PLOTS']['plot_fit_modes'].run(keys=[phys['fit_key']]))
    with OMFITx.same_row():
        OMFITx.ComboBox("root['SETTINGS']['PHYSICS']['plot_fix_coord']", ('theta', 'phi', 'z'), "Fix", default='theta', state="readonly")
        OMFITx.Entry("root['SETTINGS']['PHYSICS']['plot_fix_value']", "@", default=0, help='Degrees or meters')
        OMFITx.Button("Plot Field", "root['PLOTS']['plot_slice']")
