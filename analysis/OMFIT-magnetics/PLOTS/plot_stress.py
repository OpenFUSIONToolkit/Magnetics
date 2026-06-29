# -*-Python-*-
# Created by nelsonand at 18 Dec 2019  12:38
"""
This script plots the torques calculated by stress.py

Adapted from stress.MaxwellStress in https://github.com/logan-nc/pyMagnetics

Parameters
------------

:param torques: treeloc of torques Dataset

:param geom: string. Specify the geometric coordinate space in which the sensors are shown.
   - 'cyl' for (phi, theta) map (default)
   - 'flat' for (phi, z) mapping (good for center stack sensors)
   - 'sphere' for major radius and spherical angle

:param plot_kwargs: dictionary. Key word arguments passed to the axes plot method.

:param error_kwargs: dictionary. Passed to matplotlib errorbar function.

:param mesh_kwargs: dictionary. Additional kwargs passed to matplotlib pcolormesh.

:param surf: treeloc. location of d3d geometry info
"""

defaultVars(
    torques=root['OUTPUTS'].get('STRESS', {}).get(root['SETTINGS']['PHYSICS'].get('stress_fit_key', ''), None),
    geometry=root['SETTINGS']['PHYSICS'].get('stress_geom', 'cyl'),
    plot_kwargs={},
    error_kwargs={'alpha': 0.3},
    mesh_kwargs={'cmap': 'RdBu'},
    surf=root['DATA']['DIII-D']['machine'],
)

if torques is None:
    printe('No stress fit found to plot')
    OMFITx.End()
print('Plotting stress')

ns = torques.ns.values
ln = len(unique(ns))
nax = ln + 1
f, ax = plt.subplots(nax, 2, sharex=(not bool(time)), figsize=(10, 3 + 2 * nax))

if np.all([x in surf.keys() for x in ['R0', 'wall']]):  # basic geo calcs
    r = copy.deepcopy(surf['wall']['r'])
    z = copy.deepcopy(surf['wall']['z'])
    r0 = copy.deepcopy(surf['R0'])

    # just select outer wall
    z = z[r > r0]
    r = r[r > r0]

    mtheta = 180  # default

    # Fill out cross section points
    t = np.arctan2(z, r - r0)
    hfs = not np.any(np.abs(t) < np.pi / 2)
    if hfs:  # don't split a HFS surface
        t = t % (-2 * np.pi)  # order consistent with increasing z

    ts, rs, zs = np.array(list(zip(*sorted(zip(t, r, z)))))  # sorts by theta
    fun_r = scipy.interpolate.interp1d(ts, rs)
    fun_z = scipy.interpolate.interp1d(ts, zs)

    # translate Xsection class:
    theta = linspace(ts[0], ts[-1], mtheta + 1)
    r = fun_r(theta)
    z = fun_z(theta)

    # The angle and length of each segment
    angle = np.arctan2((z - np.roll(z, 1)), (r - np.roll(r, 1)))
    length = ((z - np.roll(z, 1)) ** 2.0 + (r - np.roll(r, 1)) ** 2.0) ** 0.5
    # move points to middle of segments
    angle = angle[1:]
    length = length[1:]
    r = r[1:] - np.diff(r) / 2
    z = z[1:] - np.diff(z) / 2
    # recalculate theta to be sure
    theta = np.arctan2(z, r - r0)
    if hfs:  # don't split a HFS surface
        theta = theta % (-2 * np.pi)
else:
    printe('Geometry data is missing!')

t = torques.time.values
theta = torques.theta.values  # theta
major = r.reshape(-1, 1)
minor = np.sqrt(z ** 2 + (r - r0) ** 2).reshape(-1, 1)
dl = length.reshape(-1, 1)
da = 2 * np.pi * major * dl

# exctract data
sphi = torques.sphi.values
tphi = torques.tphi.values
sigma_tphi = torques.sigma_tphi.values

stheta = torques.stheta.values
ttheta = torques.ttheta.values
sigma_ttheta = torques.sigma_ttheta.values

for i, n in enumerate(unique(torques.ns.values)):
    print('   --- n = {}'.format(n))
    # phi part
    (l,) = ax[0, 0].plot(t, tphi[i], label='n = {}'.format(n))
    ax[0, 0].fill_between(t, tphi[i] + sigma_tphi[i], tphi[i] - sigma_tphi[i], color=l.get_color(), **error_kwargs)
    ax[0, 0].ticklabel_format(useOffset=False, style='plain')
    tau = major * da * sphi[i].real
    # try to avoid spikes from drowning data
    if 'vmin' not in mesh_kwargs and 'vmax' not in mesh_kwargs:
        mesh_kwargs['vmax'] = np.max(np.abs(tau))
        mesh_kwargs['vmin'] = -mesh_kwargs['vmax']
    dtor = np.pi / 180  # aon
    pc = ax[i + 1, 0].pcolormesh(t, theta / dtor, tau, **mesh_kwargs)
    cb = f.colorbar(pc, ax=ax[i + 1, 0])
    cb.set_label(r'$\bar{\tau}$  (N/m$^2$)')
    ax[i + 1, 0].set_ylim(np.min(theta) / dtor, np.max(theta) / dtor)
    ax[i + 1, 0].set_ylabel(r'$\theta$ (deg)')
    ax[i + 1, 0].text(0.05, 0.95, 'n={}'.format(n), va='top', transform=ax[i + 1, 0].transAxes)
    ax[i + 1, 0].ticklabel_format(useOffset=False, style='plain')

    # theta part
    (l,) = ax[0, 1].plot(t, ttheta[i], label='n = {}'.format(n))
    ax[0, 1].fill_between(t, ttheta[i] + sigma_ttheta[i], ttheta[i] - sigma_ttheta[i], color=l.get_color(), **error_kwargs)
    ax[0, 1].ticklabel_format(useOffset=False, style='plain')
    tau = minor * da * stheta[i].real
    # try to avoid spikes from drowning data
    if 'vmin' not in mesh_kwargs and 'vmax' not in mesh_kwargs:
        mesh_kwargs['vmax'] = np.max(np.abs(tau))
        mesh_kwargs['vmin'] = -mesh_kwargs['vmax']
    pc = ax[i + 1, 1].pcolormesh(t, theta / dtor, tau, **mesh_kwargs)
    cb = f.colorbar(pc, ax=ax[i + 1, 1])
    cb.set_label(r'$\bar{\tau}$  (N/m$^2$)')
    ax[i + 1, 1].set_ylim(np.min(theta) / dtor, np.max(theta) / dtor)
    ax[i + 1, 1].set_ylabel(r'$\theta$ (deg)')
    ax[i + 1, 1].text(0.05, 0.95, 'n={}'.format(n), va='top', transform=ax[i + 1, 1].transAxes)
    ax[i + 1, 1].ticklabel_format(useOffset=False, style='plain')

yphi = np.max(np.abs(tphi)) + 1
ytheta = np.max(np.abs(ttheta)) + 1
ax[0, 0].set_ylabel(r'$T_\phi$ (Nm)')
ax[0, 1].vlines(0, *ax[0, 0].get_xlim())
ax[0, 0].set_ylim(-yphi, yphi)
ax[0, 0].legend()
ax[0, 1].set_ylabel(r'$T_\theta$ (Nm)')
ax[0, 1].vlines(0, *ax[0, 1].get_xlim())
ax[0, 1].set_ylim(-ytheta, ytheta)
ax[0, 1].legend()

# if stress was calculated only from midplane arrays, these lines show the rest of the poloidal angles:
ax[1, 0].set_ylim(-90, 90)
ax[1, 1].set_ylim(-90, 90)
# extend plot background
cmap = plt.get_cmap(mesh_kwargs['cmap'])
ax[1, 0].set_facecolor((cmap(0.5)))
ax[1, 1].set_facecolor((cmap(0.5)))


# fake colorbar to match x-spans
# note ax.set_visible(False) messes up tight_layout
for a, pc in zip(ax[0], [ax[1, 0].collections[0], ax[1, 1].collections[0]]):
    fakecb = f.colorbar(pc, ax=a)
    fakecb.ax.clear()
    fakecb.ax.set_axis_off()
for a in ax.ravel():
    a.set_xlabel('Time (ms)')
    a.set_xlim(np.min(t), np.max(t))

cornernote()
plt.tight_layout()
