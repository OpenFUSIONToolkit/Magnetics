# to allow embedding the plot in any figure,
defaultVars(
    fig=None,
    ax=None,
    device=tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'}),
    shot=root['SETTINGS']['EXPERIMENT']['shot'],
    efit=root['SETTINGS']['SPECTROGRAM']['EFIT'],
    spect_name=root['SETTINGS']['SPECTROGRAM']['name'],
    legend=True,
    xlabel='time [s]',
    ylabel='frequency [kHz]',
    whichq=['0', '1', '1.5', '2', '3', '4'],
    colorq=['blue', 'green', 'magenta', 'red', 'cyan', 'yellow'],
    markq=['', 'o', 'o', 'o', 'o', 'o'],
    lineq=['-', '', '', '', '', ''],
    plotting_parameters={'nrange': [1], 'ncolor': ['grey']},
    lu=root['SETTINGS']['SPECTROGRAM']['levels'],
    log_levels=root['SETTINGS']['SPECTROGRAM']['log_plot'],
    min_level=root['SETTINGS']['SPECTROGRAM']['lev_min'],
    max_level=root['SETTINGS']['SPECTROGRAM']['lev_max'],
)

if (fig is None) | (ax is None):
    fig, ax = subplots(1, 1)

import OMFITlib_spectrogram_utilities as spec_utils

myplot = root['PLOTS']['SPECTROGRAM']['plot_spectrogram_actual_plots'].importCode()

mdshost = root['INPUTS']['SPECTROGRAM'][device][shot]['hn']['MDShost']

try:
    FFT_data = root['OUTPUTS']['SPECTROGRAM'][device][shot][spect_name]
except Exception:
    printe('No spectrogram data in the tree')
    OMFITx.End()

myplot.plot_spectrogram(
    FFT_data,
    fig=fig,
    ax=ax,
    prop_to_power=True,
    plotting_parameters=plotting_parameters,
    lu=lu,
    log_levels=log_levels,
    min_level=min_level,
    max_level=max_level,
    xlabel=xlabel,
    ylabel=ylabel,
    plot_cn=False,
    add_cbar=False,
)

## check if qprofile analysis is required

if root['SETTINGS']['SPECTROGRAM']['xaxis'] == 'psin':

    ## populate the tree if the data are not already present
    try:
        data = root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]
    except Exception:
        data = spec_utils.get_CER_NSTX(shot=shot)

    ## get the needed data from the tree
    RR = (np.array(data['rad'])) * 1e-2
    ZZ = 0 * RR
    tm = data['time']
    vt = data['vt']
    vt[vt < 0] = 0
    if len(vt) > 11:
        vt = smooth(vt)
    psi_n = []

    ## convert major radius to psin
    for t0 in tm:
        psi_n1, dum = spec_utils.RZ2psi(RR, ZZ, efit, device, shot, t0)
        psi_n.append(psi_n1)

    ## get qprofile
    try:
        ds = root['OUTPUTS']['ANALYSIS'][device][efit][shot]
        q = ds['q']
        qpsin = ds['qpsin']
        qt = ds['time']
    except Exception:
        q = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::QPSI').data()
        qpsin = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::PSIN').data()
        qt = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::GTIME').data()

        if efit not in list(root['OUTPUTS']['ANALYSIS'][device]):
            root['OUTPUTS']['ANALYSIS'][device][efit] = OMFITtree()
        if shot not in list(root['OUTPUTS']['ANALYSIS'][device][efit]):
            root['OUTPUTS']['ANALYSIS'][device][efit][shot] = OMFITtree()
        ds = root['OUTPUTS']['ANALYSIS'][device][efit][shot]
        ds.update({'q': q, 'qpsin': qpsin, 'time': qt})

    ## convert velocities to frequencies
    ft = []
    for v in vt:
        ft.append(v / (2 * np.pi * RR))

    ## find frequencies at q of interest (q0, q=1, q=2, q=3)
    psin = np.array(psi_n)
    ft = np.array(ft)

    z = np.array(q)
    y = np.array(qpsin)
    x = np.array(qt)
    q0 = []
    q1 = []
    q2 = []
    q3 = []
    q4 = []
    x1 = []
    x2 = []
    x3 = []
    x4 = []

    q23 = []
    x23 = []
    for tt, qq, rr in zip(x, z, y):
        ind1 = np.argmin(np.abs(qq - 1))
        ind2 = np.argmin(np.abs(qq - 2))
        ind3 = np.argmin(np.abs(qq - 3))
        ind4 = np.argmin(np.abs(qq - 4))

        ind23 = np.argmin(np.abs(qq - 3.0 / 2.0))

        indtc = np.argmin(np.abs(tm - tt))
        vv = ft[indtc]
        pp = psin[indtc]

        indvt0 = np.argmin(np.abs(pp))
        indvt1 = np.argmin(np.abs(pp - rr[ind1]))
        indvt2 = np.argmin(np.abs(pp - rr[ind2]))
        indvt3 = np.argmin(np.abs(pp - rr[ind3]))
        indvt4 = np.argmin(np.abs(pp - rr[ind4]))

        indvt23 = np.argmin(np.abs(pp - rr[ind23]))

        q0.append(vv[indvt0])

        # if there are more then 5ms difference between EFIT and CER data, skip the q profile comparison
        if np.min(np.abs(tm - tt)) > 0.005:
            continue
        ## a non monotonic q profile can give a velocity for q=1 that is that of qmin, also if it is way greater than 1
        # if indvt1 != indvt0:
        if min(qq) < 1:
            q1.append(vv[indvt1])
            x1.append(tt)
        # if indvt2 != indvt0:
        if min(qq) < 2:
            q2.append(vv[indvt2])
            x2.append(tt)
        # if indvt3 != indvt0:
        if min(qq) < 3:
            q3.append(vv[indvt3])
            x3.append(tt)
        if min(qq) < 4:
            q4.append(vv[indvt4])
            x4.append(tt)

        # if indvt23 != indvt0:
        if min(qq) < 1.5:
            q23.append(vv[indvt23])
            x23.append(tt)

    # plot the frequencies at q of interest

    if (len(whichq) != len(colorq)) | (len(markq) != len(whichq)) | (len(lineq) != len(whichq)):
        printe('whichq and colorq do not match')
        whichq = ['0', '1', '1.5', '2', '3', '4']
        colorq = ['blue', 'green', 'magenta', 'red', 'cyan', 'yellow']
        markq = ['', 'o', 'o', 'o', 'o', 'o']
        lineq = ['-', '', '', '', '', '']

    whichq = np.array(whichq)
    colorq = np.array(colorq)
    markq = np.array(markq)
    lineq = np.array(lineq)

    if '0' in whichq:
        (indwq,) = np.where(whichq == '0')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]
        ax.plot(x, q0, linestyle=ls[0], marker=mark[0], color=col[0], label=r'rotation @ $\Psi _N$=0')

    if '1' in whichq:
        (indwq,) = np.where(whichq == '1')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]

        ax.plot(x1, q1, linestyle=ls[0], marker=mark[0], color=col[0], label='rotation @ q=1')
    if '1.5' in whichq:
        (indwq,) = np.where(whichq == '1.5')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]

        ax.plot(x23, q23, linestyle=ls[0], marker=mark[0], color=col[0], label='rotation @ q=3/2')
    if '2' in whichq:
        (indwq,) = np.where(whichq == '2')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]

        ax.plot(x2, q2, linestyle=ls[0], marker=mark[0], color=col[0], label='rotation @ q=2')
    if '3' in whichq:
        (indwq,) = np.where(whichq == '3')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]

        ax.plot(x3, q3, linestyle=ls[0], marker=mark[0], color=col[0], label='rotation @ q=3')

    if '4' in whichq:
        (indwq,) = np.where(whichq == '4')
        col = colorq[indwq]
        mark = markq[indwq]
        ls = lineq[indwq]

        ax.plot(x4, q4, linestyle=ls[0], marker=mark[0], color=col[0], label='rotation @ q=4')

    if legend:
        indplots = -1 * len(whichq)
        hand, lab = ax.get_legend_handles_labels()
        ax.legend(hand[indplots:], lab[indplots:], fancybox=True)
ax.set_xlim(root['SETTINGS']['SPECTROGRAM']['SpecTotalDt'])
ax.set_ylim(bottom=0)
