Short Description
-----------------
Visualization and mode analysis for 3D magnetics, 3D coils and bdot sensors

Keywords
--------
Magnetics, Tearing Modes, 3D fields, error field correction, FFT, spectrogram

Long Description
----------------
This module can be used to fit toroidal and poloidal basis functions.
The fits use an least-squares SVD solution, allowing a condition number threshold
to limit mode inclusion sensitivities. The design matrix of this fit can use basis
functions that take into account the finite toroidal and poloidal extent of the
magnetic sensors or fit center points (as is standard practice for prescribing 3D coil currents).
Basis functions can also include a temporal element omega*t, where omega can be prescribed or
taken from an existing fit (i.e. a coil array rotation).

Raw data can be windowed, de-trended, and band-pass filtered. Noise is removed using a
conditioning of the channel-by-time data matrix, which removes the incoherent (noise)
component of the signal.

The module includes a number of visualizations helpful for describing and
understanding the diagnostic set.
It also includes a number of 1D and 2D visualizations of the data and
modal fits..

The module can also be used to produce spectrograms and perform FFT of bdot signals.

Typical workflows
-----------------
The 3D magneitcs part of this module is used to:

* Fetch raw magnetics and diagnostic data in human readable groupings (i.e. arrays)
* Prepare raw data by removing drifts, smoothing, isolating frequencies of interest, compensating vacuum pickup, etc.
* Fit 3D magnetics and/or coil currents to modal basis functions
* Plot the sensor geometries, raw and prepared signals, and fits

The spectrogram part of this module is used to:

* Fetch raw magnetics info and data for only 2 selected sensors 
* Compute FFT
* Plot the spectrogram
* Plot FFT details for a given time interval
* Plot relative phases for the complete array

Supported devices
-----------------
* DIII-D (3D)
* NSTX/NSTX-U (spectrogram)

Tutorials
---------
* `Google docs <https://docs.google.com/document/d/1CZAslgcUAz5g9boyXJ3vLDmwr7ljqJhUhW2gHFx_Riw/edit?usp=sharing>`_
* `PDF <https://docs.google.com/document/d/1CZAslgcUAz5g9boyXJ3vLDmwr7ljqJhUhW2gHFx_Riw/export?format=pdf>`_

Relevant publications
---------------------
* E.J. Strait, J.D. King, J.M. Hanson, and N.C. Logan, Review of Scientific Instruments 87, 11D423 (2016).
* J.D. King, E.J. Strait, R.L. Boivin, D. Taussig, M.G. Watkins, J.M. Hanson, N.C. Logan, C. Paz-Soldan, D.C. Pace, D. Shiraki, M.J. Lanctot, R.J. La Haye, L.L. Lao, D.J. Battaglia, A.C. Sontag, S.R. Haskey, J.G. Bak, R.J. La Haye, L.L. Lao, D.J. Battaglia, A.C. Sontag, S.R. Haskey, and J.G. Bak, Review of Scientific Instruments 85, 83503 (2014).
* E.J. Strait, Review of Scientific Instruments 77, 23502 (2006).

External resources
------------------
`DIII-D 3D coil documentation <https://diii-d.gat.com/diii-d/3DCoil>`_
