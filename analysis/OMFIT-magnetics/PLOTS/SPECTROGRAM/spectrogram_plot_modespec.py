'''
script to plot the spectrogram calculated by spectrogram_prep.
2 options of plot:
1: contour plot of the mode numbers (no info about amplitude)
2: contour plot of the cross power, one mode at a time. The number of contour lines is read from
   "root['SETTINGS']['SPECTROGRAM']['levels']". In this version of the plot, the scale of the amplitude
   is different for each mode.
'''

# to allow for embedding the plot in an existing figure
defaultVars(fig=None)

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']
p1 = root['SETTINGS']['SPECTROGRAM']['p1']['tag']
p2 = root['SETTINGS']['SPECTROGRAM']['p2']['tag']
deltat = root['SETTINGS']['SPECTROGRAM']['SpecSingleDt']
tinterval = root['SETTINGS']['SPECTROGRAM']['SpecTotalDt']
newsampling = root['SETTINGS']['SPECTROGRAM']['newsampling']
integ = root['SETTINGS']['SPECTROGRAM']['integrate']
spect_name = root['SETTINGS']['SPECTROGRAM']['name']
prop_to_power = root['SETTINGS']['SPECTROGRAM']['prop_to_power']
what_to_plot = root['SETTINGS']['SPECTROGRAM']['what_to_plot']
levels_user = root['SETTINGS']['SPECTROGRAM']['levels']
log_levels = root['SETTINGS']['SPECTROGRAM']['log_plot']
min_level = root['SETTINGS']['SPECTROGRAM']['lev_min']
max_level = root['SETTINGS']['SPECTROGRAM']['lev_max']
forceupdate = root['SETTINGS']['SPECTROGRAM']['forceupdate']
root['SETTINGS']['SPECTROGRAM']['2pt'] = True


# import OMFITlib_spectrogram_utilities as spec_utils
myplot = root['PLOTS']['SPECTROGRAM']['plot_spectrogram_actual_plots'].importCode()


if what_to_plot == 'all':
    plotting_parameters = None
elif what_to_plot == '1,2,3,4':
    plotting_parameters = {'nrange': [1, 2, 3, 4], 'ncolor': ['black', 'red', 'green', 'blue']}
elif what_to_plot == 'selected':
    plotting_parameters = root['SETTINGS']['SPECTROGRAM']['plotting_parameters']
else:
    print('Not supported')

if forceupdate:
    root['SCRIPTS']['SPECTROGRAM']['fetch_NSTX'].run()

FFT_data = None
if 'SPECTROGRAM' in list(root['OUTPUTS']):
    if device in list(root['OUTPUTS']['SPECTROGRAM']):
        if shot in list(root['OUTPUTS']['SPECTROGRAM'][device]):
            base = root['OUTPUTS']['SPECTROGRAM'][device][shot]
            for spec in list(base):
                if (
                    (base[spec]['integ'] == integ)
                    & (base[spec]['deltat'] == deltat)
                    & (base[spec]['tinterval'] == tinterval)
                    & (base[spec]['newsampling'] == newsampling)
                    & (base[spec]['p1'] == p1)
                    & (base[spec]['p2'] == p2)
                ):
                    FFT_data = base[spec]

if FFT_data is None:
    root['SCRIPTS']['SPECTROGRAM']['spectrogram_prep'].run()
    FFT_data = root['OUTPUTS']['SPECTROGRAM'][device][shot][spect_name]

myplot.actual_spectrogram_plot(
    FFT_data,
    fig=fig,
    prop_to_power=prop_to_power,
    plotting_parameters=plotting_parameters,
    lu=levels_user,
    log_levels=log_levels,
    min_level=min_level,
    max_level=max_level,
)

cndev = device
if (device == 'NSTX') & (shot > 200000):
    cndev = 'NSTX-U'
cornernote(device=cndev, shot=shot, time='')
