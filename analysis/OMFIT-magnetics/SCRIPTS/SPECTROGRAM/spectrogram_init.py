import OMFITlib_spectrogram_utilities as sutils

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']

if device == 'NSTX':
    root['SETTINGS']['REMOTE_SETUP']['serverPicker'] = 'pppl_flux'
elif device == 'DIII-D':
    root['SETTINGS']['REMOTE_SETUP']['serverPicker'] = 'omega'


if root['SETTINGS']['EXPERIMENT']['shot'] is None:
    root['SETTINGS']['EXPERIMENT']['shot'] = 204718


try:
    sutils.refresh_deltat()
except Exception:
    print("Failed to initialize spectrogram settings. You will need to explicitly (re)set the sensors.")
