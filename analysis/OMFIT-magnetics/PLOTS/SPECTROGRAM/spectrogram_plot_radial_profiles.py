'''
script to plot q profile, rotation profile, Te, ne, ... at given times
to compare with spectrogram frequencies.
'''

# to allow for embedding the plot in an existing figure and to pass xaxis and fit choice directly

defaultVars(
    fig=None,
    xaxis=root['SETTINGS']['SPECTROGRAM']['xaxis'],
    efit=root['SETTINGS']['SPECTROGRAM']['EFIT'],
    plot_together=root['SETTINGS']['SPECTROGRAM']['plot_together'],
)

import OMFITlib_spectrogram_utilities as spec_utils

device = tokamak(root['SETTINGS']['EXPERIMENT']['device'], translation_dict={'NSTXU': 'NSTX'})
shot = root['SETTINGS']['EXPERIMENT']['shot']

mdshost = root['INPUTS']['SPECTROGRAM'][device][shot]['hn']['MDShost']

toi = root['SETTINGS']['SPECTROGRAM']['time_of_interest']
name = root['SETTINGS']['SPECTROGRAM']['name']
nforradprof = root['SETTINGS']['SPECTROGRAM']['nforradprof']
qtoplot = root['SETTINGS']['SPECTROGRAM']['qtoplot']


try:
    time = root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['time']
except:
    printe(f'No spectrogram data for shot {shot} on {device}')
    OMFITx.End()

(indn1,) = np.where(np.array(root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['n']) == 1)
(indn2,) = np.where(np.array(root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['n']) == 2)
(indn3,) = np.where(np.array(root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['n']) == 3)

n1 = root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['rms'][:, indn1]
n2 = root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['rms'][:, indn2]
n3 = root['OUTPUTS']['SPECTROGRAM'][device][shot][name]['rms'][:, indn3]


# create the trees to store CER, TS and FIT data

if not ('ANALYSIS' in list(root['OUTPUTS'])):
    root['OUTPUTS']['ANALYSIS'] = OMFITtree()
if not (device in list(root['OUTPUTS']['ANALYSIS'])):
    root['OUTPUTS']['ANALYSIS'][device] = OMFITtree()


if not ('TS' in list(root['OUTPUTS']['ANALYSIS'][device])):
    root['OUTPUTS']['ANALYSIS'][device]['TS'] = OMFITtree()
if not ('CER' in list(root['OUTPUTS']['ANALYSIS'][device])):
    root['OUTPUTS']['ANALYSIS'][device]['CER'] = OMFITtree()
if not ('FIT' in list(root['OUTPUTS']['ANALYSIS'][device])):
    root['OUTPUTS']['ANALYSIS'][device]['FIT'] = OMFITtree()

# fetch the data in different ways based on the device.
# this will allow to populate the "CER", "TS" and "FIT" trees in different
# ways based on the device, but it does not interfere with the plotting itself


if not (str(shot) in list(root['OUTPUTS']['ANALYSIS'][device]['CER'])):
    if device == 'NSTX':
        try:
            dataCER = spec_utils.get_CER_NSTX(shot)
        except Exception:
            printe('No CER data available')
            OMFITx.End()

    root['OUTPUTS']['ANALYSIS'][device]['CER'].update({str(shot): dataCER})
if not (str(shot) in list(root['OUTPUTS']['ANALYSIS'][device]['TS'])):
    if device == 'NSTX':
        dataTS = spec_utils.get_TS_NSTX(shot)

    root['OUTPUTS']['ANALYSIS'][device]['TS'].update({str(shot): dataTS})

if xaxis == 'psin':

    if device == 'NSTX':
        print(f'reading {efit}')
        q = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::QPSI').data()
        qpsin = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::PSIN').data()
        qt = OMFITmdsValue(mdshost, treename=efit, shot=shot, TDI=f'\{efit}::GTIME').data()
        dataFIT = OMFITtree()
        dataFIT.update({'source': efit, 'qpsi': q, 'psin': qpsin, 'gtime': qt})
    root['OUTPUTS']['ANALYSIS'][device]['FIT'].update({str(shot): dataFIT})

############


if plot_together:
    tc = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['time'])
    rc = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['rad'])
    vt = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['vt'])
    ti = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['ti'])
    ni = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['den'])
    pi = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['pi'])

    ts = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['time'])
    rs = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['radius'])
    te = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['Tef'])
    te[np.where(te > 100)] = 0

    ne = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['nef'])
    pe = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['Pef'])

    if xaxis == 'psin':
        q = np.array(root['OUTPUTS']['ANALYSIS'][device]['FIT'][str(shot)]['qpsi'])
        qpsin = np.array(root['OUTPUTS']['ANALYSIS'][device]['FIT'][str(shot)]['psin'])
        qt = np.array(root['OUTPUTS']['ANALYSIS'][device]['FIT'][str(shot)]['gtime'])

    fig = plt.figure(figsize=(11, 13))
    ax1 = fig.use_subplot(311)
    ax3 = fig.use_subplot(323)
    if xaxis == 'psin':
        ax31 = ax3.twinx()
    ax4 = fig.use_subplot(324, sharex=ax3)
    ax5 = fig.use_subplot(325, sharex=ax3)
    ax6 = fig.use_subplot(326, sharex=ax3)

    col = cm.get_cmap('Set1', np.size(toi)).colors

    for ii, t0 in enumerate(toi):
        indc = np.argmin(np.abs(tc - t0))
        inds = np.argmin(np.abs(ts - t0))

        tc0 = tc[indc]
        ts0 = ts[inds]

        if xaxis == 'radius':
            xc = rc
            xs = rs
        elif xaxis == 'psin':
            indf = np.argmin(np.abs(qt - t0))
            qt0 = qt[indf]

            RR = rc * 1e-2  # convert cm to m
            ZZ = 0 * RR
            psi_n, psi = spec_utils.RZ2psi(RR, ZZ, tree=efit, shot=shot, t0=qt0)
            xc = psi_n

            RR = rs * 1e-2  # convert cm to m
            ZZ = 0 * RR
            psi_n, psi = spec_utils.RZ2psi(RR, ZZ, tree=efit, shot=shot, t0=qt0)
            xs = psi_n
        else:
            printe(f"{xaxis} is not supported.")
            OMFITx.End()

        ax1.axvline(tc0, color=col[ii], lw=2, ls='-', label='CER')
        ax1.axvline(ts0, color=col[ii], lw=2, ls=':', label='TS')

        if xaxis == 'psin':
            ax1.axvline(qt0, color=col[ii], lw=2, ls='--', label='fit')

        ax3.plot(xc, vt[indc] / (2 * np.pi * rc * 1e-2), label=r'$\Omega$', lw=2, color=col[ii], ls='-')

        lines, labels = ax3.get_legend_handles_labels()

        if xaxis == 'psin':
            ax31.plot(qpsin[indf], q[indf], label='q', lw=2, color=col[ii], ls='--')

            ax31.set_ylim(0, 10)
            ax31.axhline(1, ls=":")
            ax31.axhline(2, ls=":")
            ax31.axhline(3, ls=":")
            ax31.set_ylabel('q')

            lines2, labels2 = ax31.get_legend_handles_labels()
            lines += lines2
            labels += labels2

        ax3.set_ylabel(r'$\Omega$ [kHz]')

        ax4.plot(xc, ni[indc], label='ni', lw=2, color=col[ii], ls='-')
        ax4.plot(xs, ne[inds], label='ne', lw=2, color=col[ii], ls=':')
        ax4.set_ylabel(r'$n_i$,$n_e$')

        ax5.plot(xc, pi[indc], label='pi', lw=2, color=col[ii], ls='-')
        ax5.plot(xs, pe[inds], label='pe', lw=2, color=col[ii], ls=':')
        ax5.set_ylabel(r'$p_i$,$p_e$')

        ax6.plot(xc, ti[indc], label='Ti', lw=2, color=col[ii], ls='-')
        ax6.plot(xs, te[inds], label='Te', lw=2, color=col[ii], ls=':')
        ax6.set_ylabel(r'$T_i$,$T_e$')

        if ii == 0:
            han, lab = ax1.get_legend_handles_labels()
            time_legend = ax1.legend(han, lab, loc='upper left', fancybox=True)
            ax1.add_artist(time_legend)

            ax3.legend(lines, labels, fancybox=True)
            ax4.legend(fancybox=True)
            ax5.legend(fancybox=True)
            ax6.legend(fancybox=True)

            for ax in [ax1, ax3, ax4, ax5, ax6]:
                leg = ax.get_legend()
                for hand in leg.legendHandles:
                    hand.set_color('k')

    if xaxis == 'radius':
        ax3.set_xlim(90, 150)
        xlabel = 'R [cm]'

    elif xaxis == 'psin':
        ax3.set_xlim(0, 1.2)
        xlabel = r'$\Psi _N$'

    ax5.set_xlabel(xlabel)
    ax6.set_xlabel(xlabel)

    plt.setp(ax3.get_xticklabels(), visible=False)
    plt.setp(ax4.get_xticklabels(), visible=False)

    ax3.set_ylim(bottom=0)
    ax4.set_ylim(bottom=0)
    ax5.set_ylim(bottom=0)
    ax6.set_ylim(bottom=0)

    nrange_plot = []
    ncolor_plot = []
    if nforradprof[0]:
        nrange_plot.append(1)
        ncolor_plot.append('grey')
    if nforradprof[1]:
        nrange_plot.append(2)
        ncolor_plot.append('wheat')
    if nforradprof[2]:
        nrange_plot.append(3)
        ncolor_plot.append('springgreen')

    whichq = []
    colorq = []
    markq = []
    lineq = []
    if qtoplot[0]:
        whichq.append('0')
        colorq.append('blue')
        markq.append('')
        lineq.append('-')
    if qtoplot[1]:
        whichq.append('1')
        colorq.append('green')
        markq.append('o')
        lineq.append('')
    if qtoplot[2]:
        whichq.append('1.5')
        colorq.append('magenta')
        markq.append('o')
        lineq.append('')
    if qtoplot[3]:
        whichq.append('2')
        colorq.append('red')
        markq.append('o')
        lineq.append('')
    if qtoplot[4]:
        whichq.append('3')
        colorq.append('cyan')
        markq.append('o')
        lineq.append('')
    if qtoplot[5]:
        whichq.append('4')
        colorq.append('yellow')
        markq.append('o')
        lineq.append('')

    root['PLOTS']['SPECTROGRAM']['plot_velocities_on_spectrogram'].run(
        fig=fig,
        ax=ax1,
        device=device,
        shot=shot,
        efit=efit,
        legend=True,
        plotting_parameters={'nrange': nrange_plot, 'ncolor': ncolor_plot},
        whichq=whichq,
        colorq=colorq,
        markq=markq,
        lineq=lineq,
    )


else:
    for what in ['CER', 'TS']:
        print(what)
        fig, (ax1, aax1, aax2, aax3) = plt.subplots(4, figsize=(9, 13))
        if nforradprof[0]:
            ax1.plot(time, n1, 'b-', label='n1rms')
        if nforradprof[1]:
            ax1.plot(time, n2, 'r-', label='n2rms')
        if nforradprof[2]:
            ax1.plot(time, n3, 'c-', label='n3rms')
        ax1.legend(loc=2)
        ax1.set_title(shot)

        if what == 'CER':
            t = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['time'])
            r = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['rad'])
            vt = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['vt'])
            ti = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['ti'])
            pi = np.array(root['OUTPUTS']['ANALYSIS'][device]['CER'][str(shot)]['pi'])

            aax1.set_ylabel('f [kHz]')
            aax2.set_ylabel('ti')
            aax3.set_ylabel('Pi')

        elif what == 'TS':
            t = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['time'])
            r = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['radius'])
            te = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['Tef'])
            te[np.where(te > 100)] = 0
            ne = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['nef'])
            pe = np.array(root['OUTPUTS']['ANALYSIS'][device]['TS'][str(shot)]['Pef'])

            aax1.set_ylabel('ne')
            aax2.set_ylabel('te')
            aax3.set_ylabel('Pe')

        col = cm.get_cmap('Set1', np.size(toi)).colors

        for ii, t0 in enumerate(toi):
            ind = np.argmin(np.abs(t - t0))
            print(t[ind])

            if xaxis == 'radius':
                x = r
            elif xaxis == 'psin':
                RR = r * 1e-2  # convert cm to m
                ZZ = 0 * r
                psi_n, psi = spec_utils.RZ2psi(RR, ZZ, tree=efit, shot=shot, t0=t[ind])
                x = psi_n
            else:
                printe(f"{xaxis} is not supported.")
                OMFITx.End()

            ax1.axvline(t[ind], color=col[ii], lw=2)
            if what == 'CER':
                aax1.plot(x, vt[ind] / (2 * np.pi * r * 1e-2), label=t0, lw=2, color=col[ii])
                aax2.plot(x, ti[ind], label=t0, lw=2, color=col[ii])
                aax3.plot(x, pi[ind], label=t0, lw=2, color=col[ii])
            else:
                aax1.plot(x, ne[ind], label=t0, lw=2, color=col[ii])
                aax2.plot(x, te[ind], label=t0, lw=2, color=col[ii])
                aax3.plot(x, pe[ind], label=t0, lw=2, color=col[ii])

        if xaxis == 'radius':
            aax1.set_xlim(90, 150)
            aax2.set_xlim(90, 150)
            aax3.set_xlim(90, 150)

        elif xaxis == 'psin':
            aax1.set_xlim(0, 1.2)
            aax2.set_xlim(0, 1.2)
            aax3.set_xlim(0, 1.2)

        aax1.set_ylim(bottom=0)

cndev = device
if (device == 'NSTX') & (shot > 200000):
    cndev = 'NSTX-U'
if xaxis == 'psin':
    text = efit
else:
    text = ''
cornernote(text=text, device=cndev, shot=shot, time='')

fig.tight_layout()
