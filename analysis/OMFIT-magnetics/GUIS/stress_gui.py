# -*-Python-*-
# Created by nelsonand at 18 Dec 2019  11:30

"""
This GUI combines 2D poloidal and radial array fits
to evaluate the Maxwell Stress Tensor at the vessel wall.

defaultVars parameters
----------------------
"""

defaultVars()

root['INPUTS'].setdefault('STRESS', OMFITtree())
root['OUTPUTS'].setdefault('STRESS', OMFITtree())

OMFITx.Label(
    '''The Maxwell Stress Tensor workflow is extremenly sensitive
to the quaility of the magnetics fits. Please consult with an expert
before using or publishing any results from this module.''',
    fg='red',
)

OMFITx.Separator()

OMFITx.Label('Mawell Stress Tensor workflow GUI', width=80)

if len(root['OUTPUTS']['FIT']) < 2:
    OMFITx.Label('Br and Bp fits must be stored in OUTPUTS first!', fg='red')

elif root['SETTINGS']['EXPERIMENT']['device'] != 'DIII-D':
    OMFITx.Label('Only DIII-D geometries are supported', fg='red')

else:
    OMFITx.Entry("root['SETTINGS']['EXPERIMENT']['shot']", 'Shot', check=is_int, postcommand=lambda location: root['SCRIPTS']['init'].run())

    OMFITx.Separator()

    ### gather inputs for stress calculation ###
    root['SETTINGS']['PHYSICS'].setdefault('stress_Bp', '')
    root['SETTINGS']['PHYSICS'].setdefault('stress_Br', '')
    OMFITx.TreeLocationPicker("root['SETTINGS']['PHYSICS']['stress_Bp']", 'Bp fit', updateGUI=True)
    OMFITx.TreeLocationPicker("root['SETTINGS']['PHYSICS']['stress_Br']", 'Br fit', updateGUI=True)

    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['stress_fit_key']",
        list(root['OUTPUTS']['STRESS'].keys()) + [''],
        "Name of stress fit",
        default='initial_fit',
        updateGUI=True,
        help="Result of the fit is placed in ['OUTPUTS']['STRESS'] under this name",
        state='normal',
    )

    OMFITx.ComboBox(
        "root['SETTINGS']['PHYSICS']['stress_geom']",
        ['cyl', 'flat', 'sphere'],
        "Geometry",
        default='cyl',
        updateGUI=True,
        help="Geometry for Mawell Stress tensor calculation. Only 'cyl' has been tested!",
        state='normal',
    )

    OMFITx.Entry(
        "root['SETTINGS']['PHYSICS']['stress_scale_Br']",
        'Scale factor for Br',
        check=is_float,
        default=1.0,
        help="To account for additional size of the Br saddle loop sensors, the Br amplitude may be adjusted",
    )

    ### check to see if the Bp and Br fits are consistent ###
    if root['SETTINGS']['PHYSICS']['stress_Bp'] and root['SETTINGS']['PHYSICS']['stress_Br']:
        Bp = root['INPUTS']['STRESS']['Bp'] = copy.deepcopy(eval(root['SETTINGS']['PHYSICS']['stress_Bp']))
        Br = root['INPUTS']['STRESS']['Br'] = copy.deepcopy(eval(root['SETTINGS']['PHYSICS']['stress_Br']))
        if any(list(zip(Bp.fit_ns.values, Bp.fit_ms.values)) != list(zip(Br.fit_ns.values, Br.fit_ms.values))):
            OMFITx.Label('Bp and Br fits contain inconsistant mode numbers, please fix', fg='red')
            OMFITx.CheckBox(
                "root['SETTINGS']['PHYSICS']['stress_manual_modes']",
                'Set mode numbers manually (experts only!)',
                default=False,
                updateGUI=True,
                help="Enable option to reset the recorderded mode numbers manually.",
            )

            if root['SETTINGS']['PHYSICS']['stress_manual_modes']:  # user option to overwrite mode numbers from the magnetics module
                OMFITx.Entry(
                    "root['SETTINGS']['PHYSICS']['stress_manual_m']",
                    'm number for Bp and Br fits',
                    check=is_int,
                    default=1,
                    help="A single, forced m number for both fits.",
                )
                OMFITx.Entry(
                    "root['SETTINGS']['PHYSICS']['stress_manual_n']",
                    'n number for Bp and Br fits',
                    check=is_int,
                    default=1,
                    help="A single, forced n number for both fits.",
                )
                OMFITx.Button('Overwrite mode numbers', lambda: root['SCRIPTS']['stress_manual_modes'].run(), updateGUI=True)

        elif any(Bp.time.values != Br.time.values):
            OMFITx.Label('Bp and Br fits contain inconsistant time axes, please fix', fg='red')
        else:  # if everything is consistent, offer option to run the stress calculation:
            OMFITx.Button('Run stress calculation', lambda: root['SCRIPTS']['stress'].run(plot=True))

### plotting options ###
if root['SETTINGS']['PHYSICS']['stress_fit_key'] in root['OUTPUTS']['STRESS']:
    OMFITx.Button('Plot stress results', lambda: root['PLOTS']['plot_stress'].run())
