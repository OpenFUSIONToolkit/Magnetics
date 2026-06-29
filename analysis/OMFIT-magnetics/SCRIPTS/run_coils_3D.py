# -*-Python-*-
# Created by myersc at 14 May 2017  17:04
"""
This script fits the mode spectra of the various 3D coil sets.
Each fit is saved under key_C, key_IU, key_IL

Parameters

-----------

:param key: fit key under which to store the various 3D coil fits
            the code will generate key_C, key_IU, key_IL as necessary
            key is restored to its original value after the various fits
:param fit_C: fit the C-coils
:param fit_IU: fit the I-coils (upper)
:param fit_IL: fit the I-coils (lower)
:param plot_modes: plot the coil modes

"""
defaultVars(
    key=root['SETTINGS']['PHYSICS'].get('fit_key', 'coil_fit'),
    fit_C=root['SETTINGS']['PHYSICS'].get('fit_C', True),
    fit_IU=root['SETTINGS']['PHYSICS'].get('fit_IU', True),
    fit_IL=root['SETTINGS']['PHYSICS'].get('fit_IL', True),
    plot_modes=True,
)


def fit_3D_coil_set(coil_str):
    """
    Function to fit a single 3D coil set.

    :param coil_str: coil-set-specific suffix for fit_key and channel filter
    :return: None

    """
    SETTINGS = root['SETTINGS']['PHYSICS']
    SETTINGS['fit_key'] = key + '_' + coil_str
    original_basis = str(SETTINGS['fit_basis'])
    try:
        SETTINGS['fit_basis'] = 'sinusoidal-point'
        SETTINGS['channels'] = SETTINGS['channels_%s' % coil_str]
        root['SCRIPTS']['run_steps'].run(run_steps=(True, True, True, False))
    finally:
        SETTINGS['fit_basis'] = original_basis


try:
    if fit_C:
        fit_3D_coil_set(coil_str='C')
    if fit_IU:
        fit_3D_coil_set(coil_str='IU')
    if fit_IL:
        fit_3D_coil_set(coil_str='IL')

finally:
    root['SETTINGS']['PHYSICS']['fit_key'] = key

if plot_modes:
    root['PLOTS']['plot_coil_modes'].runNoGUI()
