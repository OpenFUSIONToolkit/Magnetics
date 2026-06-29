# -*-Python-*-
# Created by logannc at 16 Oct 2019  16:56

"""
This script restores all the settings from a previous fit, enabling users to return to something
they may have tried before and tweak it to either get a new fit or simply overwrite the old one with
some improvements.

defaultVars parameters
----------------------
:param fit_name: str. Name of the old fit in OUTPUTS
"""

defaultVars(fit_name=root['SETTINGS']['PHYSICS'].get('fit_key', root['OUTPUTS']['FIT'].keys()[0]))


if fit_name not in root['OUTPUTS']['FIT'].keys():
    raise OMFITexception("{:} is not one of the fits available in OUTPUTS".format(fit_name))

printi("Restoring settings from fit {:}".format(fit_name))
ds = root['OUTPUTS']['FIT'][fit_name]

for key, val in ds.attrs.items():
    if key in root['SETTINGS']['EXPERIMENT']:
        printi(" EXPERIMENT: {:} > {:}".format(key, val))
        root['SETTINGS']['EXPERIMENT'][key] = val
    elif key in root['SETTINGS']['PHYSICS']:
        printi(" PHYSICS: {:} > {:}".format(key, val))
        root['SETTINGS']['PHYSICS'][key] = val
