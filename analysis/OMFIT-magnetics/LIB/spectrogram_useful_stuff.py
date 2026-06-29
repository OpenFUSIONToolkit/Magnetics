'''
Set of routines that are used by multiple scripts
'''


def downsampling(x_raw, d1_raw, tinterval=None, newsampling=2e5):

    if tinterval == None:
        tinterval = [x_raw[0], x_raw[-1]]

    print('downsampling to ' + str(int(newsampling * 1e-3)) + ' kHz...')
    indt = np.where((x_raw >= tinterval[0]) & (x_raw <= tinterval[1]))
    x_raw = x_raw[indt]
    d1_raw = d1_raw[indt]

    newsamp = int((x_raw[-1] - x_raw[0]) * newsampling)
    d1, x = scipy.signal.resample(d1_raw, newsamp, t=x_raw)

    return x, d1


def integrate(x, y, deltat=None):
    # ; (1) deltat is present: y is high-pass filtered before integration
    # ;	by subtracting a smoothed value = running average on deltat
    # ;		(suitable for long time records)
    # ; (2) deltat is absent: y is high-pass filtered simply by subtracting
    # ;	the average value over the entire x domain
    # ;		(suitable for short time records)

    print('==> Integrating data in time...')
    dt = (np.round(1e6 * (max(x) - min(x)) / (len(x) - 1))) * 1e-6  # dt = raw data sample interval

    if deltat is None:

        yave = np.mean(y)  # ***** just subtract average
        y -= yave

        yi = scipy.integrate.cumtrapz(y, x, initial=0)  # numerical integration

        # coef = np.polyfit(x,yi,1)
        # polyfn=np.poly1d(coef)
        # yi=yi-polyfn(x)                             #--- REMOVE LINEAR TREND (not used)

    else:  # ***** hi-pass filter
        npt = np.round(deltat / dt / 2.0) * 2.0 + 1  # np = points to average

        if npt > 1:
            ysmooth = scipy.ndimage.uniform_filter(y, size=npt)  # hi-pass filter:  smooth and subtract
            y = y - ysmooth

        yi = scipy.integrate.cumtrapz(y, x, initial=0)  # numerical integration

    # yi*=dt	                                        # multiply by dt (s) for time integral is included in cumtrapz

    return yi


def calculate_fft(d1, d2, fs, dtheta=None):

    f, y = scipy.signal.csd(d2, d1, fs=fs)  #### Cross-power spectrum density V**2/Hz

    # coherence = (abs(ydum)**2/y1dum/y2dum)          #alternative way to calculate the coherence
    fc, coherence = scipy.signal.coherence(d2, d1, fs=fs)  # , nperseg=nt-1)

    power = abs(y)
    phase = np.rad2deg(np.angle(y))

    if dtheta is None:
        return f, power, coherence, phase

    # ---------- Mode number
    mode = np.round(phase / dtheta)

    # RMS AMPLITUDES vs. TIME FOR EACH MODE NUMBER

    nmodes = np.ceil(180.0 / abs(dtheta) - 0.5) * 2
    mlo = int(-0.5 * nmodes)
    mhi = int(0.5 * nmodes)
    rms = []
    n = []

    for m in range(mlo, mhi + 1):  # sum over frequencies
        n.append(m)
        dum = sum(power.T * (mode == m).T)
        rms.append(dum)

    rms = np.array(rms)
    rms = np.sqrt(rms * (f[1] - f[0]))  # integrate vs. df   (rms is amplitude/sqrt(2))

    return f, power, coherence, mode, rms, n


def get_mode_2d(mirnov, siglist, tinterval=None, frequency=0, newsampling=2e5):

    t_fulla = np.array(mirnov[siglist[0]]['time'])
    ys_full = np.array([mirnov[d]['data'] for d in siglist])

    tor = np.array([mirnov[d]['tang'] for d in siglist])
    pol = np.array([mirnov[d]['pang'] for d in siglist])

    phases = []
    amps = []
    cohs = []
    d0 = 0

    for d, tpos in zip(ys_full, tor):

        t, dd = downsampling(t_fulla, d, tinterval=tinterval, newsampling=newsampling)

        if np.size(d0) == 1:
            d0 = dd

        fs = round(1 / (t[1] - t[0]))
        f, power_dum, coherence_dum, phase_dum = calculate_fft(d0, dd, fs)

        if frequency == 0:
            frequency = np.round(f[power_dum.argmax()])

        indf = np.abs(frequency - f).argmin()

        phases.append(phase_dum[indf])
        amps.append(power_dum[indf])
        cohs.append(coherence_dum[indf])

    phases = np.array(phases)
    amps = np.array(amps)
    cohs = np.array(cohs)

    pol[pol < 0] += 360
    phases[phases < 0] += 360

    data = {'phases': phases, 'amps': amps, 'cohs': cohs, 'tor': tor, 'pol': pol}

    return data, frequency


def refresh_deltat():
    p1 = root['SETTINGS']['SPECTROGRAM']['p1']['tag']
    p2 = root['SETTINGS']['SPECTROGRAM']['p2']['tag']
    shot = root['SETTINGS']['EXPERIMENT']['shot']
    device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
    try:
        base = root['INPUTS']['SPECTROGRAM'][device][shot]
    except:
        root['SCRIPTS']['SPECTROGRAM']['get_bdot_info'].run()
        base = root['INPUTS']['SPECTROGRAM'][device][shot]
    for what in list(base):
        if what not in ['hn', 'hf']:
            continue
        (ind,) = np.where(p1 == np.array(base[what]['cnam']))
        if size(ind) > 0:
            root['SETTINGS']['SPECTROGRAM']['p1']['phi'] = np.array(base[what]['tor'])[ind[0]]
            root['SETTINGS']['SPECTROGRAM']['p1']['theta'] = np.array(base[what]['pol'])[ind[0]]
        (ind,) = np.where(p2 == np.array(base[what]['cnam']))
        if size(ind) > 0:
            root['SETTINGS']['SPECTROGRAM']['p2']['phi'] = np.array(base[what]['tor'])[ind[0]]
            root['SETTINGS']['SPECTROGRAM']['p2']['theta'] = np.array(base[what]['pol'])[ind[0]]
    p1 = root['SETTINGS']['SPECTROGRAM']['p1']['phi']
    p2 = root['SETTINGS']['SPECTROGRAM']['p2']['phi']
    root['__scratch__']['delta_phi'] = int(float(p1) - float(p2))
    t1 = root['SETTINGS']['SPECTROGRAM']['p1']['theta']
    t2 = root['SETTINGS']['SPECTROGRAM']['p2']['theta']
    root['__scratch__']['delta_theta'] = int(float(t1) - float(t2))


def RZ2psi(RR, ZZ, tree='EFIT01', device='NSTX', shot=204715, t0=0.5):
    """
    maps data from 2d R,Z grid into psi space
    R,Z are coordinates of data array
    psi_n is the returned normalized psi vector
    """
    import scipy.interpolate as spint

    try:
        ds = root['OUTPUTS']['ANALYSIS'][device][tree][shot]
        time = ds['time']
        R = ds['R']
        Z = ds['Z']
        PSIRZ = ds['PSIRZ']
        SSIMAG = ds['SSIMAG']
        SSIBRY = ds['SSIBRY']

    except Exception:
        conn = MDSplus.Connection('skylark.pppl.gov:8501')
        conn.openTree(tree, int(shot))

        time = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:GTIME').data())
        R = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:R').data())
        Z = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:Z').data())
        PSIRZ = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:PSIRZ').data())
        SSIMAG = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:SSIMAG').data())
        SSIBRY = np.array(conn.get(f'\{tree}::TOP.RESULTS.GEQDSK:SSIBRY').data())

        conn.closeTree(tree, int(shot))

        if 'ANALYSIS' not in list(root['OUTPUTS']):
            root['OUTPUTS']['ANALYSIS'] = OMFITtree()
        if device not in list(root['OUTPUTS']['ANALYSIS']):
            root['OUTPUTS']['ANALYSIS'][device] = OMFITtree()
        if tree not in list(root['OUTPUTS']['ANALYSIS'][device]):
            root['OUTPUTS']['ANALYSIS'][device][tree] = OMFITtree()
        if shot not in list(root['OUTPUTS']['ANALYSIS'][device][tree]):
            root['OUTPUTS']['ANALYSIS'][device][tree][shot] = OMFITtree()
        ds = root['OUTPUTS']['ANALYSIS'][device][tree][shot]
        ds.update({'time': time, 'R': R, 'Z': Z, 'PSIRZ': PSIRZ, 'SSIMAG': SSIMAG, 'SSIBRY': SSIBRY})

    indt0 = np.abs(time - t0).argmin()

    z = Z[indt0]
    r = R[indt0]
    psirz = PSIRZ[indt0]
    ssimag = SSIMAG[indt0]
    ssibry = SSIBRY[indt0]

    pp = spint.interp2d(r, z, psirz)

    psi = pp(RR, ZZ)[0]
    psi_n = (ssimag - psi) / (ssimag - ssibry)

    return psi_n, psi


def get_CER_NSTX(shot=204715):
    print('Getting CHERS data')
    tree = 'activespec'
    conn = MDSplus.Connection('skylark.pppl.gov:8501')
    conn.openTree(tree, int(shot))

    time = np.array(conn.get('\chers_best:time').data())
    rad = np.array(conn.get('\chers_best:radius').data())
    rs = np.array(conn.get('\chers_best:rs').data())

    ti = np.array(conn.get('\chers_best:ti').data())  # keV
    tis = np.array(conn.get('\chers_best:tis').data())
    dti = np.array(conn.get('\chers_best:dti').data())  # error bars

    vt = np.array(conn.get('\chers_best:vt').data())  # toroidal velocity km/s
    vts = np.array(conn.get('\chers_best:vts').data())
    dvt = np.array(conn.get('\chers_best:dvt').data())  # error bars

    nc = np.array(conn.get('\chers_best:nc').data())  # carbon density
    ncs = np.array(conn.get('\chers_best:ncs').data())
    dnc = np.array(conn.get('\chers_best:dnc').data())

    pi = np.array(conn.get('\chers_best:pi').data())  # ion pressure
    dpi = np.array(conn.get('\chers_best:dpi').data())

    ft = np.array(conn.get('\chers_best:ft').data())  # toroidal frequency
    dft = np.array(conn.get('\chers_best:dft').data())

    den = np.array(conn.get('\chers_best:den').data())  # electron density from Thomson cm^-3
    dden = np.array(conn.get('\chers_best:dden').data())

    zeff = np.array(conn.get('\chers_best:zeff').data())
    dzeff = np.array(conn.get('\chers_best:dzeff').data())  # error bar

    conn.closeTree(tree, int(shot))

    data = {
        'time': time,
        'rad': rad,
        'rs': rs,
        'ti': ti,
        'tis': tis,
        'dti': dti,
        'vt': vt,
        'vts': vts,
        'dvt': dvt,
        'nc': nc,
        'ncs': ncs,
        'dnc': dnc,
        'pi': pi,
        'dpi': dpi,
        'ft': ft,
        'dft': dft,
        'den': den,
        'dden': dden,
        'zeff': zeff,
        'dzeff': dzeff,
    }

    return data


def get_TS_NSTX(shot='204715'):
    print('Getting TS data')

    tree = 'ACTIVESPEC'
    conn = MDSplus.Connection('skylark.pppl.gov:8501')
    conn.openTree(tree, int(shot))

    treename = '\TS_BEST:'
    qual = np.array(conn.get(treename + 'QUALITY').data())
    radius = np.array(conn.get(treename + 'FIT_RADII').data())

    dr = np.array(conn.get(treename + 'FIT_R_WIDTH').data())
    time = np.array(conn.get(treename + 'TS_TIMES').data())

    Tef = np.array(conn.get(treename + 'FIT_TE').data()).T
    dTef = np.array(conn.get(treename + 'FIT_TE_ERR').data()).T
    nef = np.array(conn.get(treename + 'FIT_NE').data()).T
    dnef = np.array(conn.get(treename + 'FIT_NE_ERR').data()).T
    Pef = np.array(conn.get(treename + 'FIT_PE').data()).T
    dPef = np.array(conn.get(treename + 'FIT_PE_ERR').data()).T

    conn.closeTree(tree, int(shot))

    data = {
        'radius': radius,
        'dr': dr,
        'time': time,
        'Tef': Tef,
        'dTef': dTef,
        'nef': nef,
        'dnef': dnef,
        'Pef': Pef,
        'dPef': dPef,
        'quality': qual,
    }

    return data
