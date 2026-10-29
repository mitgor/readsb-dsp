"""Offline bundle ablations; no service imports or live configuration changes."""
import numpy as np
from .pipeline_native import FastSharedRescue
BUNDLES={
 'current':('timing','soft','matched'),
 'plus_acquisition':('timing','soft','matched'),
 'acquisition_no_timing':('soft','matched'),
 'acquisition_no_matched':('timing','soft'),
 'acquisition_no_soft':('timing','matched'),
 'plus_acquisition_sequence':('timing','soft','matched'),
}
class NoSequence:
 def decode(self,iq,starts,frequency):
  n=len(starts);return np.empty((n,14),np.uint8),np.empty((n,2),np.int8),np.zeros(n,bool),None,None
class BundleDecoder(FastSharedRescue):
 def __init__(self,h,name):
  if name not in BUNDLES:raise ValueError('Unknown bundle')
  super().__init__(h,current_only=name=='current');self.name=name
  self.legacy.classical.stages=BUNDLES[name]
  if name!='plus_acquisition_sequence':self.sequence=NoSequence()
