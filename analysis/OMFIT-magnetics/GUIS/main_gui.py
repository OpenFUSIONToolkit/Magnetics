# decide what to do with the magnetic data


def run_3D_mag():
    root['SCRIPTS']['init'].run()
    root['GUIS']['3D_mag_gui'].run()


def run_3D_coil():
    root['SCRIPTS']['init'].run()
    root['GUIS']['coil_gui'].run()


def run_spectrogram():
    root['SCRIPTS']['SPECTROGRAM']['spectrogram_init'].run()
    root['GUIS']['SPECTROGRAM']['spectrogram_driver'].run()


OMFITx.TitleGUI("Select what to do")

OMFITx.Button("High Frequency Fourier Analysis", run_spectrogram, help='Currently supports NSTX and NSTX-U')
OMFITx.Button("\tSpatial fits of 3D magnetics arrays or coils\t", run_3D_mag, help='Currently supports DIII-D')
OMFITx.Button(
    "Spatial fits of 3D coil currents",
    run_3D_coil,
    help='Currently supports DIII-D (just an alternate interface for the general worflow above',
)
OMFITx.Button("slcontour fits of 3D magnetics arrays or coils", root['GUIS']['slcontour_gui'], help='Runs DIII-D specific IDL analysis')
OMFITx.Button("Electromagnetic stress calculations", root['GUIS']['stress_gui'], help='Requires 2D fits of Br and Bp at the wall')
