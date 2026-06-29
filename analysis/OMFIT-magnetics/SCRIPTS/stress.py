# -*-Python-*-
# Created by nelsonand at 18 Dec 2019  14:06

"""
This script calculates the Maxwell Stress torques for a given Bp, Br fit

Adapted from stress.MaxwellStress in https://github.com/logan-nc/pyMagnetics

defaultVars parameters
----------------------
:param geom: string. Specify the geometric coordinate space in which the sensors are shown.
   - 'cyl' for (phi, theta) map (default)
   - 'flat' for (phi, z) mapping (good for center stack sensors)
   - 'sphere' for major radius and spherical angle

:param BpFit: treeloc of Bp fit (Must have corresponding Br fit!)

:param BrFit: treeloc of Br fit (Must have corresponding Bp fit!)

:param fit_name: string. Name of fit iteration.

:param scaleBr: float. To account for additional size of the Br saddle loop sensors, the Br amplitude may be adjusted by this factor.

:param plot: bool. Plot torques when finished. default = False
"""

defaultVars(
    geom=root['SETTINGS']['PHYSICS']['stress_geom'],
    BpFit=root['INPUTS']['STRESS']['Bp'],
    BrFit=root['INPUTS']['STRESS']['Br'],
    fit_name=root['SETTINGS']['PHYSICS']['stress_fit_key'],
    scaleBr=root['SETTINGS']['PHYSICS']['stress_scale_Br'],
    plot=False,
    btcyl=False,
)

########################################## Prepare Funcitons ##########################################

# subfuction for MaxwellStress
def b_n(bnm, sigma_bnm, nms, time, n, theta, geom, timeslc=None):
    """
    Return complex amplitude of a toroidal mode at the requested poloidal point(s).

    **Arguments:**
        bnm : from BxFit
        sigma_bnm : from BxFit
        nms : from BxFit
        time : from BxFit
        n : int.
            Toroidal mode number.
        theta : ndarray:
            Poloidal points.

    **Key Word Arguments:**
        time : float.
            Return only a single time slice.
        fitvector : int.
            Extrapolate the specified right-singular vecotr
            of the fit basis matrix instead of the full fit.
            (Indexing starts at 1!).

    **Returns:**
      tuple.
          Amplitude and uncertainty, each with dimensions theta by time.

    """
    theta = np.array(theta)  # accepts single values
    an, en = 0, 0
    for i, (nmode, mmode) in enumerate(nms):
        if n == nmode:
            if geom == 'sphere':
                thetafunc = lpmv(n, m, np.cos(theta + np.pi / 2))
            else:
                thetafunc = np.exp(-1j * mmode * theta).reshape(-1, 1)
            an += bnm[i].reshape(1, -1) * thetafunc.conj()  # b = an.conj()*exp(inphi)
            en = np.sqrt(en ** 2 + (sigma_bnm[i].reshape(1, -1) * thetafunc) ** 2)
    if timeslc != None:
        s = np.abs(time - timeslc).argmin()
        an = an[:, s]
        en = en[:, s]
    return an, en


# define stress calculation within function
def MawellStress(geom, BpFit, BrFit, surf=root['DATA']['DIII-D']['machine'], btcyl=False, order=1, scaleBr=1):
    """
    Script for the computation of 2D Maxwell Stress fits across the DIII-D vessel

    Adapted from stress.MaxwellStress @logan-nc

    .. note:: Maps to 'greater cylinder' with r=2.395, which is 3.3cm inside
        R0 midplane and just inside all points of R+/-1.


    **Arguments:**
        BpFit : obj.
            magnetics Dataset
        BrFit : obj.
            magnetics Dataset

    **Key Word Arguments:**
        surf  : treeloc
            location of d3d geometry info
        btcyl : bool.
            Use a simple cylindircal geometry to solve for the toroidal field:
            Bt = -(nr/mR)Bp. Otherwise, solve least squared problem on surface:
            dBt/dtheta = dBp/dphi.
        order : int.
            Order of spline for LocalFits (not supported yet).
        scaleBr : float
            Optional additional scaling factor for Br amplitude

    """
    print('Calculating Maxwell stress tensor across DIII-D LFS')

    # extract needed variales from BpFit, BrFit
    BpFit_ns = BpFit.fit_ns.values
    BpFit_ms = BpFit.fit_ms.values
    BpFit_bnm = [np.array(x) for x in BpFit.fit_coeffs.values]
    BpFit_sigma_bnm = [np.array(x) for x in BpFit.fit_sigmas.values]
    BpFit_nms = list(zip(BpFit_ns, BpFit_ms))
    BpFit_time = BpFit.time.values * 1e3  # convert to ms

    BrFit_ns = BrFit.fit_ns.values
    BrFit_ms = BrFit.fit_ms.values
    BrFit_bnm = [np.array(x) * scaleBr for x in BrFit.fit_coeffs.values]  # additional (optional) scaling factor for Br
    BrFit_sigma_bnm = [np.array(x) * scaleBr for x in BrFit.fit_sigmas.values]  # additional (optional) scaling factor for Br
    BrFit_nms = list(zip(BrFit_ns, BrFit_ms))
    BrFit_time = BrFit.time.values * 1e3  # convert to ms

    if any(BpFit_nms != BrFit_nms):
        raise ValueError('Bp and Br fits contain inconsistant mode numbers')
    if any(BpFit_time != BrFit_time):
        raise ValueError('Bp and Br fits contain inconsistent time axes')

    if np.all([x in surf.keys() for x in ['R0', 'wall']]):  # basic geo calcs
        r = copy.deepcopy(surf['wall']['r'])
        z = copy.deepcopy(surf['wall']['z'])
        r0 = copy.deepcopy(surf['R0'])

        # just select outer wall
        z = z[r > r0]  # change to thetas of sensors into the fit?? AON theta_end12 max and min
        r = r[r > r0]

        # just select range where sensors are defined
        sbndry_theta = np.concatenate((BpFit.theta_end1.values, BpFit.theta_end2.values, BrFit.theta_end1.values, BrFit.theta_end2.values))
        zmax = (max(r) - r0) * tan(radians(max(sbndry_theta)))
        zmin = (max(r) - r0) * tan(radians(min(sbndry_theta)))
        valid = (z < zmax) & (z > zmin)
        z = z[valid]
        r = r[valid]

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

    # basic info
    ns = np.array(BpFit_ns)
    minor = np.sqrt(z ** 2 + (r - r0) ** 2)
    major = r
    dl = length
    da = 2 * np.pi * major * dl
    mu0 = 4 * np.pi * 1e-7

    if geom == 'flat':
        x = z
    elif geom == 'sphere':
        x = np.arctan(r, z)
    else:
        x = theta

    print('Converting poloidal to toroidal field')
    BtFit = copy.deepcopy(BpFit)  ###### ASSUME THAT DEEPCOPY WILL GET FIXED!! ######
    BtFit_bnm = [np.array(x) for x in BtFit.fit_coeffs.values]
    BtFit_sigma_bnm = [np.array(x) for x in BtFit.fit_sigmas.values]
    BtFit_nms = list(zip(BtFit.fit_ns.values, BtFit.fit_ms.values))
    BtFit_time = BtFit.time.values * 1e3  # convert to ms

    if btcyl:
        # mimic perfect cylinder solution (-im/r)Bt = (in/R)Bp
        print('... using cylindrical approximation')
        for i, nm in enumerate(BpFit_nms):  # minor and major radii
            BtFit_bnm[i] *= (nm[0] * np.average(minor)) / (-nm[1] * np.average(major))
            BtFit_sigma_bnm[i] *= (nm[0] * np.average(minor)) / (-nm[1] * np.average(major))
    else:
        # Solve curlB=0 -> (-im/r)Bt = (in/R)Bp on surface
        print('... solving curlB=0 on surface')
        A = []
        t, p = np.meshgrid(x, np.linspace(0, np.pi / 5, 2 * len(BpFit_ns) + 1))
        b = np.zeros((len(t.ravel()), np.shape(BpFit_bnm)[-1])) * (1 + 1j)
        for (n, m), bnm in zip(BpFit_nms, BpFit_bnm):
            A.append((-1j * m * np.exp(1j * (n * p - m * t)) / minor).ravel())
            b += (1j * n * np.exp(1j * (n * p - m * t)) / major).reshape(-1, 1) * bnm.reshape(1, -1)  # .conj()

        A, b = np.matrix(A).T, np.array(b)
        btnm, res, rank, s = scipy.linalg.lstsq(A, b, cond=1e-3)  # need to use the scipy lstsq
        try:
            print('Condition number = {:.2e}'.format(s[0] / s[-1]))  # aon removed this!
        except FloatingPointError:
            printe('WARNING!!! DIVIDE BY ZERO ERROR ENCOUNTERED!', s)  # aon
        print('Rank = {}'.format(rank))
        BtFit_bnm = btnm
        for i, bnm in enumerate(BtFit_bnm):
            BtFit_sigma_bnm[i].real *= bnm.real / BpFit_bnm[i].real
            BtFit_sigma_bnm[i].imag *= bnm.imag / BpFit_bnm[i].imag
            nm = BtFit_nms[i]
            print(nm)
            if nm[1] == 0:
                cyl = inf
            else:
                cyl = (nm[0] * np.average(minor)) / (-nm[1] * np.average(major))
            avs = np.average(bnm.real / BpFit_bnm[i].real) + 1j * np.average(bnm.imag / BpFit_bnm[i].imag)
            print('mode {}, cyl approx = {:.3}, average sol = {:.3}'.format(nm, cyl, avs))

    print('Calculating torque')
    aphi = []
    sphi = []
    tphi = []
    wphi = []
    sigma_tphi = []
    sigma_wphi = []
    atheta = []
    stheta = []
    ttheta = []
    wtheta = []
    sigma_ttheta = []
    sigma_wtheta = []

    for n in ns:
        # get complex amplitudes (theta by time)
        br, sigmar = b_n(BrFit_bnm, BrFit_sigma_bnm, BrFit_nms, BrFit_time, n, x, geom)
        bp, sigmap = b_n(BpFit_bnm, BpFit_sigma_bnm, BpFit_nms, BpFit_time, n, x, geom)
        bt, sigmat = b_n(BtFit_bnm, BtFit_sigma_bnm, BtFit_nms, BtFit_time, n, x, geom)
        # amplitudes
        aphi.append(np.abs(bt) * np.abs(br))
        atheta.append(np.abs(bp) * np.abs(br))
        # stress cross sections (n by theta by time)
        # stress=(br.real*bt.real+br.imag*bt.imag)/(2*np.pi*mu0) WHY PI??? phi avarage
        if 0:  # plot phases for debugging
            fig, ax = subplots()
            ax.plot(numpy.angle(br[0]), label='br')
            ax.plot(numpy.angle(bt[0]), label='bt')
            ax.plot(numpy.angle(bp[0]), label='bp')
            ax.legend(frameon=False, loc=0)

        sphi.append((br * np.conj(bt)) / (mu0))  # is imaginary part energy?
        stheta.append((br * np.conj(bp)) / (mu0))
        # integrate da RS = intdldphiR RS = pi intdl RRS (n by time)
        tphi.append(np.sum((dl * np.pi * major ** 2).reshape(-1, 1) * sphi[-1].real, axis=0))
        wphi.append(np.sum((dl * np.pi * major ** 2).reshape(-1, 1) * sphi[-1].imag / (2 * n), axis=0))
        ttheta.append(np.sum((dl * np.pi * minor * major).reshape(-1, 1) * stheta[-1].real, axis=0))
        wtheta.append(np.sum((dl * np.pi * minor * major).reshape(-1, 1) * stheta[-1].imag / (2 * n), axis=0))

        # propogate errors
        sigma_sphi = (
            np.sqrt(
                (bt.real * sigmar.real) ** 2 + (br.real * sigmat.real) ** 2 + (bt.imag * sigmar.imag) ** 2 + (br.imag * sigmat.imag) ** 2
            )
            / mu0
            + 1j
            * np.sqrt(
                (bt.real * sigmar.imag) ** 2 + (br.real * sigmat.imag) ** 2 + (bt.imag * sigmar.real) ** 2 + (br.imag * sigmat.real) ** 2
            )
            / mu0
        )
        sigma_tphi.append(np.sqrt(np.sum(((dl * np.pi * major ** 2).reshape(-1, 1) * sigma_sphi.real) ** 2, axis=0)))
        sigma_wphi.append(np.sqrt(np.sum(((dl * np.pi * major ** 2).reshape(-1, 1) / (2 * n) * sigma_sphi.imag) ** 2, axis=0)))

        sigma_stheta = (
            np.sqrt(
                (bp.real * sigmar.real) ** 2 + (br.real * sigmap.real) ** 2 + (bp.imag * sigmar.imag) ** 2 + (br.imag * sigmap.imag) ** 2
            )
            / mu0
            + 1j
            * np.sqrt(
                (bp.real * sigmar.imag) ** 2 + (br.real * sigmap.imag) ** 2 + (bp.imag * sigmar.real) ** 2 + (br.imag * sigmap.real) ** 2
            )
            / mu0
        )
        sigma_ttheta.append(np.sqrt(np.sum(((dl * np.pi * minor * major).reshape(-1, 1) * sigma_stheta.real) ** 2, axis=0)))
        sigma_wtheta.append(np.sqrt(np.sum(((dl * np.pi * minor * major).reshape(-1, 1) / (2 * n) * sigma_stheta.imag) ** 2, axis=0)))

    # convert final results to Dataset
    ns = DataArray(ns, coords={'ns': ns}, dims=('ns'))
    theta = DataArray(x, coords={'theta': x}, dims=('theta'))
    time = DataArray(BpFit_time, coords={'time': BpFit_time}, dims=('time'))
    aphi = DataArray(np.array(aphi), coords={'ns': ns, 'theta': x, 'time': BpFit_time}, dims=('ns', 'theta', 'time'))
    sphi = DataArray(np.array(sphi), coords={'ns': ns, 'theta': x, 'time': BpFit_time}, dims=('ns', 'theta', 'time'))
    tphi = DataArray(np.array(tphi), coords={'ns': ns, 'time': BpFit_time}, dims=('ns', 'time'))
    wphi = DataArray(np.array(wphi), coords={'ns': ns, 'time': BpFit_time}, dims=('ns', 'time'))
    sigma_tphi = DataArray(np.array(sigma_tphi), coords={'ns': ns, 'time': BpFit_time}, dims=('ns', 'time'))
    atheta = DataArray(np.array(atheta), coords={'ns': ns, 'theta': x, 'time': BpFit_time}, dims=('ns', 'theta', 'time'))
    stheta = DataArray(np.array(stheta), coords={'ns': ns, 'theta': x, 'time': BpFit_time}, dims=('ns', 'theta', 'time'))
    ttheta = DataArray(np.array(ttheta), coords={'ns': ns, 'time': BpFit_time}, dims=('ns', 'time'))
    sigma_ttheta = DataArray(np.array(sigma_ttheta), coords={'ns': ns, 'time': BpFit_time}, dims=('ns', 'time'))

    torques = Dataset(
        {
            'aphi': aphi,
            'sphi': sphi,
            'tphi': tphi,
            'wphi': wphi,
            'sigma_tphi': sigma_tphi,
            'atheta': atheta,
            'stheta': stheta,
            'ttheta': ttheta,
            'sigma_ttheta': sigma_ttheta,
        },
        coords={'ns': ns, 'theta': theta, 'time': time},
    )

    return torques


########################################## Run Calculation ##########################################

root['OUTPUTS'].setdefault('STRESS', OMFITtree())
root['OUTPUTS']['STRESS'][fit_name] = MawellStress(
    geom=geom, BpFit=BpFit, BrFit=BrFit, surf=root['DATA']['DIII-D']['machine'], btcyl=btcyl, order=1, scaleBr=scaleBr
)

if plot:
    root['PLOTS']['plot_stress'].run()
