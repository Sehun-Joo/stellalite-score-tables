"""Same penalized target likelihood, solved per chart (conditional on player skill).
There are no cross-chart terms in this second-stage objective, so it factorizes.
"""
import math
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize

def target_fit(theta,mu,a,p,j,y,J,target_fraction=.98):
    b0=(-math.log1p(-target_fraction)-mu)/a
    loga0=np.log(np.clip(a/.4,.25,8));x=theta[p]
    if np.any(j[1:]<j[:-1]):
        order=np.argsort(j,kind='stable');j,x,y=j[order],x[order],y[order]
    counts=np.bincount(j,minlength=J);ends=np.cumsum(counts);starts=np.r_[0,ends[:-1]]
    bb=np.zeros(J);aa=np.zeros(J);max_gradient=0.;evaluations=0
    for k in range(J):
        xx=x[starts[k]:ends[k]];yy=y[starts[k]:ends[k]]
        def fg(z):
            b,loga=z;slope=np.exp(loga);eta=slope*(xx-b);e=expit(eta)-yy
            loss=np.logaddexp(0,eta).sum()-np.dot(yy,eta)+.5*(b-b0[k])**2+.5*((loga-loga0[k])/.5)**2
            return loss,np.array([-slope*e.sum()+b-b0[k],np.dot(e,eta)+(loga-loga0[k])/.25])
        fit=minimize(fg,[b0[k],loga0[k]],jac=True,method='L-BFGS-B',bounds=[(-15,50),(math.log(.1),math.log(12))],options={'maxiter':1000,'ftol':1e-12,'gtol':1e-7,'maxls':50})
        if not fit.success:raise RuntimeError(f'Chart {k}: {fit.message}')
        bb[k]=fit.x[0];aa[k]=math.exp(fit.x[1]);evaluations+=fit.nfev
        if (k+1)%200==0:print(f'{100*target_fraction:.4f}%: {k+1}/{J} charts converged',flush=True)
    print(f'{100*target_fraction:.4f}%: all {J} charts converged ({evaluations} evaluations)',flush=True)
    return bb,aa
