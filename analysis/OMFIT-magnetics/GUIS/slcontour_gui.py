# -*-Python-*-
# Created by munarettos at 30 Nov 2018  11:39

OMFITx.CheckBox("root['SETTINGS']['SLCONTOUR']['interactive']", 'interactive', default=False, updateGUI=True)
OMFITx.CheckBox("root['SETTINGS']['SLCONTOUR']['doplot']", 'show plot', default=True, updateGUI=False)

if not root['SETTINGS']['SLCONTOUR']['interactive']:

    OMFITx.ComboBox(
        "root['SETTINGS']['SLCONTOUR']['runid']",
        {'Do not save': '', 'auto': 'auto'},
        'run id',
        default='',
        state='normal',
        help="Entering a runid forces the results to be saved. If the runid is 'auto' then the runid is an hash based on the settings of the fit, if the runid is '' the results are not saved.",
    )
    OMFITx.ShotTimeDevice(multiTimes=True)
    arrays = sorted(
        [
            'ESLD',
            'ESLDU',
            'ISLD',
            'MPID',
            'ISLD67A',
            'ISLD67B',
            'MPID67A',
            'MPID67B',
            'ISLD79A',
            'ISLD79B',
            'MPID79A',
            'MPID79B',
            'ISLD1A',
            'ISLD1B',
            'MPID1A',
            'MPID1B',
            'BTID',
            'ESL66M',
            'ISL66M',
            'MPI66M',
            'ISL67A',
            'ISL67B',
            'MPI67A',
            'MPI67B',
            'ISL1A',
            'MPI1A',
            'BTI66M',
            'CCOIL',
            'IUCOIL',
            'ILCOIL',
            'MPI66M_S',
            'CCOIL_S',
            'IUCOIL_S',
            'ILCOIL_S',
            'VERT5A',
            'VERT4A',
            'VERT3A',
            'VERT2A',
            'VERT1A',
            'VERT1B',
            'VERT2B',
            'VERT3B',
            'VERT4B',
            'VERT5B',
            'PCESLD',
            'PCISLD',
            'PCMPID',
            'PCISLD67A',
            'PCISLD67B',
            'PCMPID67A',
            'PCMPID67B',
            'PCC',
            'PCIU',
            'PCIL',
            'NRSESLD',
            'NRSISLD',
            'NRSMPID',
            'NRSISLD67A',
            'NRSISLD67B',
            'NRSMPID67A ',
            'NRSMPID67B',
            'ISLDVERT',
            'MPIDVERT',
            'ISLVERT',
            'MPIVERT',
            'DSL067',
            'DSL157',
            'MPI322',
            'MPI142',
            'MPI66M-D',
            'MPI1L-D',
            'MPI322-D',
            'ISLR01',
            'MPIR01',
            'ISLDR01',
            'PCISLDR01',
            'NRSISLDR01',
            'ISLD_LFS',
            'ISLD1AB',
            'ISLD_HFS',
            'MPIDR01',
            'PCMPIDR01',
            'NRSMPIDR01',
            'MPID_LFS',
            'MPID1AB',
            'MPID_HFS',
            'ISLD_TOR',
            'MPID_TOR',
            'ISLD_ALL',
            'MPID_ALL',
            'DSL_ALL',
            'MPI_ALL',
            'HIRES-D',
            'MPIR0-D',
            'MPIALL-D',
        ]
    )
    OMFITx.ComboBox(
        "root['SETTINGS']['SLCONTOUR']['array']", arrays, lbl='array', default='MPID', state='search', help='array used for the fit'
    )

    OMFITx.Entry("root['SETTINGS']['SLCONTOUR']['nmin']", 'n min', default=1, help='minimum n for the fit')
    OMFITx.Entry("root['SETTINGS']['SLCONTOUR']['nmax']", 'n max', default=3, help='maximum n for the fit')
    OMFITx.Entry(
        "root['SETTINGS']['SLCONTOUR']['compensate']",
        'compensate',
        default='N',
        help='I for I-coils compensation, C for C-coils compensation IC for both, N for none. Only DC compensation.',
    )
    OMFITx.Entry("root['SETTINGS']['SLCONTOUR']['base']", 'base', default=100, help='baseline time interval')
    OMFITx.ComboBox(
        "root['SETTINGS']['SLCONTOUR']['btype']",
        {
            '0:no baseline': 0,
            '1:early data': 1,
            '2:late data': 2,
            '3:interpolated': 3,
            '4:running average': 4,
            '5:leading average': 5,
            '6:advance average': 6,
            '7:RC filter': 7,
            '8:advance RC filter': 8,
            '9:single-freq. sine   fit': 9,
            '10:single-freq. square fit': 10,
            '11:arbitrary interval, single value': 11,
            '12:arbitrary interval, linear fit': 12,
            '13:interpolate between two intervals': 13,
        },
        lbl='btype',
        default=1,
        state='search',
        help='baseline method',
    )

    OMFITx.Entry("root['SETTINGS']['SLCONTOUR']['smooth']", 'smooth', default=0, help='smooth of the raw data')

OMFITx.Separator()
OMFITx.Button('Run SLCONTOUR', "root['SCRIPTS']['slcontour']")
OMFITx.Button('Plot SLCONTOUR', "root['PLOTS']['plot_slcontour_fit']")
