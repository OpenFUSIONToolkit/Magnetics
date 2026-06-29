# -*-Python-*-
# Created by munarettos at 30 Nov 2018  11:23

defaultVars(
    interactive=root['SETTINGS']['SLCONTOUR']['interactive'],
    doplot=root['SETTINGS']['SLCONTOUR']['doplot'],
    shot=root['SETTINGS']['EXPERIMENT']['shot'],
    tmin=root['SETTINGS']['EXPERIMENT']['times'][0],
    tmax=root['SETTINGS']['EXPERIMENT']['times'][-1],
    server=root['SETTINGS']['REMOTE_SETUP']['serverPicker'],
)

# check to be on omega
if server != 'omega':
    printe("slcontour runs only on omega")
    server = 'omega'


interactive_input = None
outputs = ['slcontour_data_1D.sav']

# interactive
if interactive:
    run_dict = {}
    script = (
        '''
slcontour
''',
        'launch_slcontour.pro',
    )
    executable = '''
module purge
module load idl slcontour
xterm -e 'idl launch_slcontour.pro'
'''

# not interactive
else:
    run_dict = dict(shot=shot, tmin=tmin, tmax=tmax, **root['SETTINGS']['SLCONTOUR'])
    script = (
        '''
@/fusion/projects/codes/slcontour/version_20210519/common.pro
@/fusion/projects/codes/slcontour/version_20210519/common_modes.pro
print,{nmax}
slcontour,shot={shot},array="{array}",tmin={tmin},tmax={tmax},nmin={nmin},nmax={nmax},comp="{compensate}",base={base},btype={btype},tsmooth={smooth},/noplot,/save,/batch
restore,'slcontour_data_1D.sav'
save,x,nmode_ampl,nmode_phas,nmin,nmax,mode_n,mode_m,condno,filename='slcontour_data_1D.sav'
save,xraw,yraw,x,y,yfit,phi1eff,phi2eff,name,mode_n,mode_m,condno,bplot,phip,arrayname,ctype,filename='slcontour_fitinfo.sav'
exit
'''.format(
            **run_dict
        ),
        'launch_slcontour.pro',
    )
    executable = '''
module purge
module load idl slcontour
idl launch_slcontour.pro
'''
    outputs.append('slcontour_fitinfo.sav')

OMFITx.executable(root, outputs=outputs, executable=executable, script=script, server='omega')


# collect idl output and store in the OMFIT tree

tmp = OMFITidlSav('./slcontour_data_1D.sav')
tmp.load()
try:
    tmp2 = OMFITidlSav('./slcontour_fitinfo.sav')
    tmp2.load()
    runid = root['SETTINGS']['SLCONTOUR']['runid']
except Exception:
    runid = 'interactive'
if runid != '':
    if 'SLCONTOUR' not in root['OUTPUTS']:
        root['OUTPUTS']['SLCONTOUR'] = {}
    if runid == 'auto':
        runid = omfit_hash(repr(tuple(run_dict.values())), 10)
    root['OUTPUTS']['SLCONTOUR'][runid] = {}
    root['OUTPUTS']['SLCONTOUR'][runid].update(tmp)
    root['OUTPUTS']['SLCONTOUR'][runid].update(run_dict)
else:
    scratch.update(tmp)
    scratch.update(run_dict)
if runid != 'interactive':
    scratch.update(tmp2)  # leave the bigger data in the scratch in any case
root['__scratch__']['runid'] = runid

# plot the fit
if doplot:
    root['PLOTS']['plot_slcontour_fit'].run()


# SLCONTOUR HELP & ARRAYS
'''
pro slcontour,$
    shot=shotin,$
    tmin=tminin,tmax=tmaxin,ttmin=ttminin,ttmax=ttmaxin, $
    tbmin=tbminin,tbmax=tbmaxin, $
    array=arraynamein, mask=maskin, omit=omitin, $
    tsmooth=tsmoothin,postsmooth=psmoothin, $
    tslice=tslicein, $
    base=basein,btype=btypein,zmin=zminin,zmax=zmaxin, $
    nmin=nminin,nmax=nmaxin,nstep=nstepin, $
    mmin1=mminin, mmax1=mmaxin, mstep1=mstepin, $
    mmin2=mmin2in,mmax2=mmax2in,mstep2=mstep2in, $
    comp=ctypein,hc=hcdevicein, $
    small=small,large=large,batch=batch,backup=backup, $
    xout=xout,yout=yout,n_sli=n_out,ampl_sli=ampl_out,phas_sli=phas_out,$
    dbfile=dbfilein,noplot=noplot,dbug=dbug,dump=dump,DMP=DMP,save=save,$
    threed=threed

-->help
*********************** Keyword input **************************
------------------------------------------------------ INPUT PARAMETERS
  shot  tmax  tmax  ttmin, ttmax array  tsmooth  postsmooth  tslice
  zmin  zmax  base  btype  comp  hc
  nmin  nmax  nstep mmin   mmax  mstep  mmin2 mmax2  mstep2
--------------------------------------------------------- OUTPUT ARRAYS
  xout  yout              - phi, deltaB fit results (batch mode only)
  n_sli ampl_sli phas_sli - ampl & phase vs n at slice time (batch only)
  dbfile                  - name of database file to save 1-line output
  dump  DMP   save        - save data files for plotting or DMP archive
--------------------------------------------------------------- CONTROL
  /threed  - enable "3D" fitting (actually 2D in phi and theta)
  /batch   - batch run: keyword input only, exit after one run
  /noplot  - make output files but no plots (suitable for batch run)
  /backup  - parameters from backup file (supersedes parameter keywords)
  /small      - smaller windows for laptop screen

*********************** Command input **************************
   Enter commands, separated by "," or ";"  Abbreviations OK.
   Form is <command> or <command = value> or <command value>
********************** COMMANDS ********************************
help      view      backup    exit  -- Actions
stop      hardcopy  hc   hc1  hc2   -- Actions
replot    dump      DMPfiles        -- Actions
----------------------------------------------------------- SHOT & TIME
shot      [         ]               -- Shot number
refshot   refscale                  -- Vacuum shot & scale factor
tmin      xmin      tmax      xmax  -- Time limits for main plots
ttmin     xxmin     ttmax     xxmax -- Time limits for "zoom"
tslice    slice     autoslice       -- Analysis time slice
thetaslice    phislice         stype -- Spatial slice for 2D data
----------------------------------------------------------- INPUT ARRAY
array     find      list            -- Select, display array
omit      add       mask            -- Turn signals off/on
------------------------------------------------------ INPUT PROCESSING
tsmooth   smooth    presmooth       -- Smoothing time for raw data
base      btype                     -- Baseline time & method
compensate                          -- I&C coil compensation
--------------------------------------------------------- MODE ANALYSIS
nmin      nmax      nstep           -- Toroidal mode number limits
mmin      mmax      mstep           -- Poloidal mode number limits
mmin2     mmax2     mstep2          -- Poloidal mode secondary limits
zmin      zmax      zlim   nclevel  -- Contour limits, number of levels
residuals                           -- Quality of fit
ylog     tgfit               -- Semilog plot & growth rate
postsmooth               -- Smoothing of ampl & phase vs. t
db        autoslice           -- Output to database file
-----------------------------------------------------------------------

-->array
ESLD        ESLDU       ISLD        MPID        ISLD67A     ISLD67B
MPID67A     MPID67B     ISLD79A     ISLD79B     MPID79A     MPID79B
ISLD1A      ISLD1B      MPID1A      MPID1B      BTID        ESL66M
ISL66M      MPI66M      ISL67A      ISL67B      MPI67A      MPI67B
ISL1A       MPI1A       BTI66M      CCOIL       IUCOIL      ILCOIL
MPI66M_S    CCOIL_S     IUCOIL_S    ILCOIL_S    VERT5A      VERT4A
VERT3A      VERT2A      VERT1A      VERT1B      VERT2B      VERT3B
VERT4B      VERT5B      PCESLD      PCISLD      PCMPID      PCISLD67A
PCISLD67B   PCMPID67A   PCMPID67B   PCC         PCIU        PCIL
NRSESLD     NRSISLD     NRSMPID     NRSISLD67A  NRSISLD67B  NRSMPID67A
NRSMPID67B  ISLDVERT    MPIDVERT    ISLVERT     MPIVERT     DSL067
DSL157      MPI322      MPI142      MPI66M-D    MPI1L-D     MPI322-D
ISLR01      MPIR01      ISLDR01     PCISLDR01   NRSISLDR01  ISLD_LFS
ISLD1AB     ISLD_HFS    MPIDR01     PCMPIDR01   NRSMPIDR01  MPID_LFS
MPID1AB     MPID_HFS    ISLD_TOR    MPID_TOR    ISLD_ALL    MPID_ALL
DSL_ALL     MPI_ALL     HIRES-D     MPIR0-D     MPIALL-D
'''
