# -*-Python-*-
# Created by munarettos at 04 Dec 2018  09:40

"""
This script plots initial results

"""

defaultVars(runid=root['SETTINGS']['SLCONTOUR']['runid'])

if runid != '':
    if runid == 'auto':
        runid = root['__scratch__']['runid']
    t1 = root['OUTPUTS']['SLCONTOUR'][runid]
else:
    t1 = root['__scratch__']
t2 = root['__scratch__']


names = t2.get('name', [])
if len(names) == 0:
    printe('No valid slcontour run to plot!')
    OMFITx.End()
if len(names) <= 6:
    nc = 1
elif len(names) <= 10:
    nc = 2
elif len(names) <= 15:
    nc = 3
else:
    nc = 4
nr = int(len(names) / nc)

'''
t1 has: x,nmode_ampl,nmode_phas,nmin,nmax,mode_n,mode_m,condno,shot,tmin,tmax,nmax,smooth,compensate,runid,base,btype,array,nmin,interactive
t2 has: xraw,yraw,x,y,yfit,phi1eff,phi2eff,name,mode_n,mode_m,condno,bplot,phip
'''

fig, ax = plt.subplots(ncols=nc, nrows=nr, sharex=True, sharey=True)
axf = ax.flatten()

x = np.array(t2['x']) * 1e-3
y = np.array(t2['y'])
yfit = np.array(t2['yfit'])
phi1 = np.array(t2['phi1eff'])
phi2 = np.array(t2['phi2eff'])
for i, name in enumerate(names):
    axf[i].plot(x, y[i], '-b')
    axf[i].plot(x, yfit[i], '-r')
    title_inside(name + ' ' + str(phi1[i]) + '-' + str(phi2[i]), ax=axf[i])

fig.suptitle(t1['shot'])
fig.tight_layout()
autofmt_sharex()

fig, ax = plt.subplots(ncols=1, nrows=3, sharex=True, sharey=False)
axf = ax.flatten()

x = np.array(t1['x']) * 1e-3
y1 = np.array(t1['nmode_ampl'])
y2 = np.array(t1['nmode_phas'])
mm = np.array(t1['mode_m'])
nn = np.array(t1['mode_n'])

if shape(mm) != ():
    for i, (m, n) in enumerate(zip(mm, nn)):
        axf[0].plot(x, y1[i])
        axf[1].plot(x, y2[i])
else:
    axf[0].plot(x, y1)
    axf[1].plot(x, y2)

bplot = np.array(t2['bplot'])[1, :, :]
phip = np.array(t2['phip'])


# aa=axf[2].contourf(x,phip,bplot,30,cmap='inferno')
vmax = np.percentile(abs(bplot).flatten(), 99)
aa = axf[2].imshow(bplot, cmap='RdBu_r', aspect='auto', extent=(min(x), max(x), min(phip), max(phip)), vmin=-vmax, vmax=vmax)
# aa=image(x,phip,bplot,ax=axf[2])
# axf[2].set_cmap='inferno'


for ind in [1, 2]:
    axf[ind].set_ylim(0, 360)
    axf[ind].set_yticks([0, 90, 180, 270])

fig.suptitle(t1['shot'])
fig.subplots_adjust(right=0.85, hspace=0, bottom=0.1, top=0.91)
cbar_ax = fig.add_axes([0.86, 0.1, 0.03, 0.27])

cb = fig.colorbar(aa, cax=cbar_ax)
cb.ax.set_title(r'$\delta$B [G]', x=2, y=1.01)
axf[2].set_xlabel('time [s]')
axf[0].set_ylabel(r'$\delta$B [G]')
axf[1].set_ylabel('phase [deg]')
axf[2].set_ylabel('phi [deg]')
