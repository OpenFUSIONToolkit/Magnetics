# -*-Python-*-
# Created by logannc at 01 Mar 2017  13:20

# defaultVars()
device = root['SETTINGS']['EXPERIMENT']['device']
shot = root['SETTINGS']['EXPERIMENT']['shot']

if device != 'DIII-D':
    # device = root['SETTINGS']['EXPERIMENT']['device'] = 'DIII-D'
    printe('only DIII-D is supported for the 3D analysis')  # , forcing the device to be DIII-D')
    OMFITx.End()

printi('Initializing new RAW data set')

root.setdefault('INPUTS', OMFITtmp())

if device not in root['DATA']:
    printe("Magnetics sensor information is not known for {:}".format(device))
    # printe("Forcing device to {:}".format(list(root['DATA'].keys())[0]))
    # root['SETTINGS']['EXPERIMENT']['device'] = list(root['DATA'].keys())[0]
    # device = list(root['DATA'].keys())[0]

# get the ascii table
sensors = copy.copy(root['DATA'][device]['sensors'])

# form a Dataset
kwargs = dict(coords={'channel': sensors['data']['channel']}, dims=('channel',))
d = {}
for key in sensors['columns'][1:]:
    d[key] = DataArray(sensors['data'][key], name=key, **kwargs)

ds = Dataset(d)

# device specific tweaks can go here
# example: DIII-D slcontour data defines tilt as field angle,
# not probe surface angle and needs to be 90 deg. rotated for Br sensors if not fixed directly in txt file
if is_device(device, []):
    # index = ['ISLD' in key or 'ESL' in key for key in ds['channel'].values]
    # ds['tilt'][index] += 90 * np.sign(ds['tilt'][index] + 1e-10)  # Br surface angle not field angle
    pass

# add some convenient geometries
ds['delta_phi'][ds['delta_phi'] == 0] = 1.0
# actual max / min might switch based on tilts
ds['r_end1'] = ds['r'] - 0.5 * ds['length'] * np.cos(np.deg2rad(ds['tilt']))
ds['r_end2'] = ds['r'] + 0.5 * ds['length'] * np.cos(np.deg2rad(ds['tilt']))
ds['z_end1'] = ds['z'] - 0.5 * ds['length'] * np.sin(np.deg2rad(ds['tilt']))
ds['z_end2'] = ds['z'] + 0.5 * ds['length'] * np.sin(np.deg2rad(ds['tilt']))
ds['phi_end1'] = ds['phi'] - 0.5 * ds['delta_phi']
ds['phi_end2'] = ds['phi'] + 0.5 * ds['delta_phi']
ds['theta'] = np.rad2deg(np.arctan2(ds['z'], ds['r'] - root['DATA'][device]['machine']['R0']))
ds['theta_end1'] = np.rad2deg(np.arctan2(ds['z_end1'], ds['r_end1'] - root['DATA'][device]['machine']['R0']))
ds['theta_end2'] = np.rad2deg(np.arctan2(ds['z_end2'], ds['r_end2'] - root['DATA'][device]['machine']['R0']))

# save to tree
root['INPUTS']['RAW'] = ds


# DC compensation data
if is_device(device, 'DIII-D'):
    cmkeys = [('2013', 152472), ('2014', 159600), ('2017', 168823), ('2017b', 169800), ('2018', 172800)]
    message = f'No compensation data available for shot {shot}'
    cmfile = None
    for key, firstshot in cmkeys:
        if key == '2017b':
            caveat = ', after C259 repair'
        elif key == '2017':
            caveat = ', before C259 repair'
        else:
            caveat = ''
        if shot is not None and shot >= firstshot:
            message = f' - Using {key} compensation data{caveat}'
            cmfile = f'/fusion/projects/codes/slcontour/compensation/ic_comp/cm_{key}.sav'
    printi(message)

    root['INPUTS'].setdefault('COUPLING', Dataset())
    if cmfile is None:
        root['INPUTS']['COUPLING']['dc_coupling'] = DataArray()
        root['INPUTS']['COUPLING']['dc_coupling'].attrs['original_file'] = 'no_file_yet'
    else:
        if 'dc_coupling' in root['INPUTS']['COUPLING']:
            if root['INPUTS']['COUPLING']['dc_coupling'].attrs['original_file'] != cmfile:
                new = True
            else:
                new = False
        else:
            new = True

        if new:
            # clobber old coupling matrix, which might have had different channels/coils
            root['INPUTS']['COUPLING'] = Dataset()
            # get official compensation matrix
            root['SETTINGS']['REMOTE_SETUP']['serverPicker'] = 'omega'
            OMFITx.executable(root, inputs=[], outputs=['cm.sav'], executable='cp {:} cm.sav'.format(cmfile), quiet=False)
            tmp = OMFITidlSav('cm.sav')
            # use updated naming conventions
            old_to_new = dict([(v, k) for k, v in root['DATA']['DIII-D']['channel_alternates'].items()])
            pt_nms = [old_to_new.get(x, x) for x in tmp['pt_nms']]
            # save a DataArray in inputs
            da = DataArray(tmp['cm'], coords={'coil': tmp['coils'], 'channel': pt_nms}, dims=('coil', 'channel'))
            da.attrs['original_file'] = cmfile
            root['INPUTS']['COUPLING']['dc_coupling'] = da
else:
    root['INPUTS']['COUPLING'] = Dataset()

# AC compensation data
