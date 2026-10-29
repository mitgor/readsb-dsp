"""Offline research features and bounded RF transformations; never imported by live paths."""
import numpy as np
from .dsp import features, PREAMBLE
from .classical import window, cancel_packet, pulse_train


def phase_features(iq):
    """Power/log-power plus preamble-referenced complex samples, constant-phase invariant."""
    x=features(iq)
    ref=iq[:, :32][:, PREAMBLE.astype(bool)].mean(1)
    scale=np.sqrt(np.maximum((np.abs(iq[:, :32][:, PREAMBLE.astype(bool)])**2).mean(1),1e-5))
    rotation=np.conj(ref)/np.maximum(np.abs(ref),1e-8)
    z=iq*rotation[:,None]/scale[:,None]
    return np.concatenate((x,np.stack((np.clip(z.real,-4,4),np.clip(z.imag,-4,4)),1)),1).astype(np.float32)


def shift_rows(chunks,shifts):
    return np.stack([window(z,np.array([8]),float(s))[0] for z,s in zip(chunks,shifts)])


def mix_real(chunks,pool,rng,probability=.7):
    """Mix independent captured RF snippets. Caller supplies SAME split only.
    Whole constituent includes real background; these are semi-synthetic examples.
    """
    out=chunks.copy();n=len(out);mask=rng.random(n)<probability
    ids=rng.integers(len(pool),size=n);delays=rng.integers(-400,401,size=n)
    ratios=10**(rng.uniform(-16,3,size=n)/20)
    phases=rng.uniform(-np.pi,np.pi,size=n);freqs=rng.uniform(-70000,70000,size=n)
    t=(np.arange(496)-8)/4e6
    for i in np.flatnonzero(mask):
        z=pool[ids[i]].copy();delay=int(delays[i]);shifted=np.zeros_like(z)
        lo=max(0,delay);hi=min(496,496+delay)
        shifted[lo:hi]=z[lo-delay:hi-delay]
        a=np.sqrt(np.mean(np.abs(out[i,8:488])**2));b=np.sqrt(np.mean(np.abs(z[8:488])**2))
        out[i]+=shifted*(a/max(float(b),1e-6))*ratios[i]*np.exp(1j*(phases[i]+2*np.pi*freqs[i]*t))
    return out,mask


def cancel_features(iq,start,payload):
    residual,fit=cancel_packet(iq,start,payload)
    if residual is None:return None,None,fit
    z=iq[start:start+480];base=z-residual
    scale=max(float(np.sqrt(np.mean(np.abs(base)**2))),1e-5)
    x=np.stack((z.real/scale,z.imag/scale,base.real/scale,base.imag/scale,pulse_train(payload))).astype(np.float32)
    return x,(base,scale),fit


def apply_cancellation(iq,start,payload,session):
    x,context,fit=cancel_features(iq,start,payload)
    if x is None:return None,fit
    base,scale=context
    correction=session.run(None,{'cancel_features':x[None]})[0][0]
    adjustment=(correction[0]+1j*correction[1])*scale
    residual=iq[start:start+480]-base-adjustment
    conventional=iq[start:start+480]-base
    ratio=float(np.vdot(residual,residual).real/max(np.vdot(iq[start:start+480],iq[start:start+480]).real,1e-12))
    relative=float(np.vdot(residual,residual).real/max(np.vdot(conventional,conventional).real,1e-12))
    # Bounded model output plus the original fit gate; never relax the stock-fit guard.
    if not np.isfinite(ratio) or ratio>.45 or relative>1.05:
        return None,{**fit,'reason':'neural_residual_rejected','neural_ratio':ratio,'relative_to_classical':relative}
    return residual.astype(np.complex64),{**fit,'neural_ratio':ratio,'relative_to_classical':relative}


def variable_windows(iq,starts,shifts):
    """Eight-tap fractional windows with one estimated shift per candidate.
    Batches the same calculation as classical.window without per-window Python work.
    """
    starts=np.asarray(starts,dtype=np.int64);shifts=np.asarray(shifts,dtype=np.float64)
    if starts.shape!=shifts.shape:raise ValueError('One shift per start required')
    integer=np.floor(shifts).astype(np.int64);fraction=shifts-integer
    taps=np.arange(-3,5);weights=np.sinc(taps[None,:]-fraction[:,None])*np.kaiser(8,5)
    weights=(weights/weights.sum(1,keepdims=True)).astype(np.float32)
    positions=starts[:,None]+integer[:,None]+np.arange(480)[None,:]
    out=np.zeros((len(starts),480),np.complex64)
    for j,tap in enumerate(taps):out+=iq[positions+tap]*weights[:,j,None]
    return out
