# -*-Python-*-
# Created by nlogan at 06 Mar 2017  16:59
"""
This script plots the spacial location of sensors corresponding to each channel meeting the designated
regular expression criterian.

Parameters

------------

:param key: str. Name of a fit Dataset(s) from OUTPUTS.

:param channel_filter: string. Only channels with names matching this regular expression are shown.

:param geometry: string. Specify the geometric coordinate space in which the sensors are shown.
   - 'rz' for a cross section view (default)
   - 'flat' for (phi, z) mapping (good for center stack sensors)
   - 'sphere' for major radius and spherical angle
   - 'cylindrical' for (phi, theta) map

:param axes: Axes. Matplotlib Axes objects into which the sensors are drawn.

:param legend_maxnum: int. Maximum number of lines to include in the legend.

:param plot_kwargs: dictionary. Key word arguments passed to the axes plot method.

:param exclude: bool.
    - True to plot only the included channels with good data
    - False to plot all seleted channels

"""
defaultVars(
    key='RAW', channel_filter=root['SETTINGS']['PHYSICS'].get('channels', '.*'), geometry='rz', axes=None, plot_kwargs={}, exclude=True
)

if axes is not None:
    fig, axes = axes.get_figure(), axes
else:
    fig, axes = plt.subplots(1, 1)

if key in root['INPUTS']:
    ds = root['INPUTS'][key]
else:
    ds = root['OUTPUTS']['FIT'][key]

channels = [k for k in ds['channel'].values if re.match(channel_filter, k)]
if exclude and 'PREPARED' in root['INPUTS']:
    for channel in list(channels):
        if channel not in root['INPUTS']['PREPARED']['channel'].values:
            channels.remove(channel)
        elif channel in root['SETTINGS']['PHYSICS']['fit_exclude']:
            channels.remove(channel)
device = root['SETTINGS']['EXPERIMENT']['device']


def no_wrap(a):
    """Avoid mis-plotting sensors that span the edges of angle ranges"""
    x = np.atleast_1d(a)
    if np.ptp(x) > 240:
        x[x == x.min()] += 360
    return x


l = None
for channel in channels:
    s = ds.sel(channel=channel)
    if geometry == 'rz':
        x = [s['r_end1'], s['r_end2']]
        y = [s['z_end1'], s['z_end2']]
    elif geometry == 'flat':
        x = [s['phi_end1'], s['phi_end2'], s['phi_end2'], s['phi_end1'], s['phi_end1']]
        y = [s['z_end1'], s['z_end1'], s['z_end2'], s['z_end2'], s['z_end1']]
    elif geometry == 'sphere':
        x = [s['phi_end1'], s['phi_end2'], s['phi_end2'], s['phi_end1'], s['phi_end1']]
        y = [s['alpha_end1'], s['alpha_end1'], s['alpha_end2'], s['alpha_end2'], s['alpha_end1']]
    else:  # default to  'cylindrical'
        x = no_wrap([s['phi_end1'], s['phi_end2'], s['phi_end2'], s['phi_end1'], s['phi_end1']])
        y = no_wrap([s['theta_end1'], s['theta_end1'], s['theta_end2'], s['theta_end2'], s['theta_end1']])
    if l is not None:
        plot_kwargs['color'] = l.get_color()
    (l,) = axes.plot(x, y, label=channel, picker=3, **plot_kwargs)

if geometry == 'rz':
    if 'wall' in root['DATA'][device]['machine'] and 'wall' not in [l.get_label() for l in axes.lines]:
        if 'color' in plot_kwargs:
            plot_kwargs.pop('color')
        wall = root['DATA'][device]['machine']['wall']
        axes.plot(wall['r'], wall['z'], label='wall', picker=3, **plot_kwargs)
    axes.set_xlabel("R (m)")
    axes.set_ylabel("z (m)")
    axes.set_aspect('equal')
elif geometry == 'flat':
    axes.set_xlabel("phi (deg)")
    axes.set_ylabel("z (m)")
elif geometry == 'sphere':
    axes.set_xlabel("phi (deg)")
    axes.set_ylabel("alpha (deg)")
    axes.set_xlim(0, 360)
    axes.set_ylim(-90, 90)
else:  # default to  geom=='cyl':
    axes.set_ylabel("theta (deg)")
    axes.set_xlabel("phi (deg)")
    axes.set_xlim(0, 360)
    axes.set_ylim(-180, 180)

cornernote(device=device, shot='', time='', text='')

# add interactivity


def sensor_pick(event):
    "Print sensor name when clicked"
    art = event.artist
    if isinstance(art, plt.matplotlib.lines.Line2D):
        print(art.get_label())


fig.canvas.mpl_connect('pick_event', sensor_pick)
print("Click a sensor to print its name")
