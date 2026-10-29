"""Offline-only complex RF companion. No production imports or feeder output.

Feature contract phase-iq-v1: real/imaginary preamble-normalized I/Q plus
power/log-power, N x 4 x 480. The old N x 2 x 480 contract is untouched.
"""
import numpy as np
from .dsp import PREAMBLE

CONTRACT='phase-iq-v1'
def phase_features(iq, amplitude_only=False):
    z=np.asarray(iq,np.complex64)
    if z.ndim!=2 or z.shape[1]!=480 or not np.isfinite(z).all():
        raise ValueError('Expected finite N x 480 complex RF')
    power=np.abs(z)**2
    scale=np.maximum(power[:,:32][:,PREAMBLE.astype(bool)].mean(1),1e-5)
    z=z/np.sqrt(scale[:,None])
    # A constant phase convention only: carrier progression remains observable.
    reference=z[:,[0,1,4,5,14,15,18,19]].sum(1)
    rotation=np.exp(-1j*np.angle(reference)).astype(np.complex64)
    z=z*rotation[:,None]
    p=power/scale[:,None]
    result=np.stack([np.clip(z.real,-8,8),np.clip(z.imag,-8,8),np.clip(p,0,12),np.log1p(p)],1).astype(np.float32)
    if amplitude_only:result[:,:2]=0
    return result

def make_model():
    import torch
    from torch import nn
    class PhaseCompanion(nn.Module):
        def __init__(self):
            super().__init__()
            self.entry=nn.Conv1d(16,16,5,padding=2)
            self.context=nn.Conv1d(16,16,1)
            self.blocks=nn.ModuleList([nn.Sequential(nn.Conv1d(16,16,5,padding=2*d,dilation=d,groups=16),nn.ReLU(),nn.Conv1d(16,16,1)) for d in (1,3)])
            self.out=nn.Conv1d(16,1,1)
            nn.init.zeros_(self.out.weight);nn.init.zeros_(self.out.bias)
        def forward(self,x):
            phases=x.reshape(-1,4,120,4).permute(0,1,3,2).reshape(-1,16,120)
            h=torch.relu(self.entry(phases))
            h=h+torch.tanh(self.context(h[:,:,:8].mean(-1,keepdim=True)))
            for block in self.blocks:h=torch.relu(h+block(h))
            power=x[:,2,32:].reshape(-1,112,4)
            conventional=(power[:,:,:2].sum(-1)-power[:,:,2:].sum(-1))*3
            return conventional+self.out(h).squeeze(1)[:,8:]
    return PhaseCompanion()
