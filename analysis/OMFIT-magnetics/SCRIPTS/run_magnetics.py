# -*-Python-*-
# Created by nlogan at 16 Apr 2017  16:14

"""
This script Optionally runs each of the fetch, prep, and fit scripts.

Parameters
-----------

:param run_steps: list. Bool for whether or not to run each of the 3 scripts to fetch, prep, fit, and plot.

:param channels: string or list. Regular expression string(s) that filter subsets of channels used in each fit.

:param verbose: bool. Print status updates to console

"""
defaultVars(
    run_steps=root['SETTINGS']['PHYSICS'].get('run_steps', (True, True, True, True)),
    channels=root['SETTINGS']['PHYSICS'].get('channels', '.*'),
    verbose=True,
)

# basic variables
plot_modes = run_steps[3]
channels = atleast_1d(channels)
device = root['SETTINGS']['EXPERIMENT']['device']
predefined = dict((str(val), key) for key, val in root['DATA'][device]['channel_filters'].items())
fn = None
fit_key = root['SETTINGS']['PHYSICS']['fit_key']

# run each step for each channel filter
for channel_filter in channels:
    lbl = predefined.get(channel_filter, channel_filter)
    if len(channels) > 1:
        root['SETTINGS']['PHYSICS']['fit_key'] = fit_key + '_' + lbl
    for do, key in zip(run_steps, ['fetch', 'prep', 'fit']):
        if do:
            root['SCRIPTS'][key].run(channel_filter=channel_filter, verbose=verbose)
    if plot_modes:
        if len(channels) > 1:
            if fn is None:
                fn = FigureNotebook(0, 'Magnetics Mode Fits')
            fig, ax = fn.subplots(2, 1, label=lbl, sharex=True)
        else:
            fig, ax = plt.subplots(2, 1, sharex=True)
        root['PLOTS']['plot_fit_modes'].runNoGUI(axes=ax)
root['SETTINGS']['PHYSICS']['fit_key'] = fit_key
